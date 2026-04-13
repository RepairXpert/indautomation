"""Fault code diagnosis engine — maps fault codes + symptoms to ranked root causes and fix steps.

Supports exact match, fuzzy match on code/name/tags/description, and falls back
to LM Studio Qwen for unknown faults.  Includes replacement parts suggestions
with supplier buy links for every matched fault.
"""
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from indauto.parts.catalog import get_parts_for_category

FAULT_DB_PATH = Path(__file__).resolve().parent.parent / "fault_db" / "codes.json"

_FAULT_DB: list[dict] | None = None


def load_fault_db() -> list[dict]:
    """Load fault database with module-level lazy cache to avoid re-reading 580KB on every call."""
    global _FAULT_DB
    if _FAULT_DB is None:
        if FAULT_DB_PATH.exists():
            with open(FAULT_DB_PATH, encoding="utf-8") as f:
                data = json.load(f)
            _FAULT_DB = data.get("faults", [])
        else:
            _FAULT_DB = []
    return _FAULT_DB


def _normalize(text: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _fuzzy_score(query: str, entry: dict) -> float:
    """Score how well a query matches a fault entry. Returns 0.0–1.0."""
    if not query:
        return 0.0
    q = _normalize(query)
    best = 0.0

    # Check code (exact or partial — both directions)
    code = _normalize(entry.get("code", ""))
    if code and q == code:
        return 1.0
    if code and (q in code or code in q):
        best = max(best, 0.85)

    # Check name — exact substring and word overlap
    name = _normalize(entry.get("name", ""))
    if q in name:
        best = max(best, 0.8)
    if name in q and name:
        best = max(best, 0.75)
    best = max(best, SequenceMatcher(None, q, name).ratio() * 0.7)

    # Multi-word query: check how many query words appear in name
    q_words = set(q.split())
    if len(q_words) > 1:
        name_words = set(name.split())
        overlap = q_words & name_words
        if overlap:
            best = max(best, len(overlap) / max(len(q_words), 1) * 0.8)

    # Check description
    desc = _normalize(entry.get("description", ""))
    if q in desc:
        best = max(best, 0.6)
    # Multi-word query words in description
    if len(q_words) > 1:
        desc_words = set(desc.split())
        overlap = q_words & desc_words
        if len(overlap) >= 2:
            best = max(best, len(overlap) / max(len(q_words), 1) * 0.65)

    # Check tags
    tags = [_normalize(t) for t in entry.get("tags", [])]
    for tag in tags:
        if q == tag:
            best = max(best, 0.75)
        elif q in tag or tag in q:
            best = max(best, 0.6)
    # Multi-word: check tag overlap
    if len(q_words) > 1:
        tag_set = set(tags)
        tag_overlap = q_words & tag_set
        if tag_overlap:
            best = max(best, len(tag_overlap) / max(len(q_words), 1) * 0.7)

    return best


def _symptom_score(symptoms: str, entry: dict) -> float:
    """Score how well free-text symptoms match a fault entry."""
    if not symptoms:
        return 0.0
    words = set(_normalize(symptoms).split())
    if not words:
        return 0.0

    # Build searchable text from entry
    search_fields = [
        entry.get("name", ""),
        entry.get("description", ""),
        " ".join(entry.get("tags", [])),
        " ".join(entry.get("probable_causes", [])),
        " ".join(entry.get("fix_steps", [])),
    ]
    entry_text = _normalize(" ".join(search_fields))
    entry_words = set(entry_text.split())

    # Stop words to ignore
    stop = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to",
            "for", "of", "and", "or", "not", "it", "be", "has", "have", "been",
            "with", "from", "by", "but", "if", "when", "that", "this", "its",
            "won't", "wont", "can't", "cant", "doesn't", "doesnt", "don't", "dont",
            "my", "i", "we", "no", "so", "do", "did", "does", "just", "get", "got"}
    meaningful = words - stop
    if not meaningful:
        return 0.0

    hits = sum(1 for w in meaningful if w in entry_words or
               any(w in ew for ew in entry_words))
    score = min(hits / len(meaningful), 1.0)

    # Bonus: check if the full symptom phrase appears in entry text
    symptom_norm = _normalize(symptoms)
    if symptom_norm in entry_text:
        score = max(score, 0.9)

    return score


def _equipment_match(equipment_type: str, entry: dict) -> bool:
    """Check if equipment type matches the entry."""
    if not equipment_type:
        return True  # No filter = match all
    et = _normalize(equipment_type)
    entry_types = [_normalize(t) for t in entry.get("equipment_types", [])]
    entry_single = _normalize(entry.get("equipment_type", ""))
    if entry_single == "general":
        return True
    return et in entry_types or et == entry_single or any(et in t for t in entry_types)


def diagnose_fault(equipment_type: str, fault_code: str, symptoms: str,
                   photo_analysis: dict | None, config: dict) -> dict:
    """Diagnose a fault from code, symptoms, and optional photo analysis.

    1. Exact match on fault code
    2. Fuzzy match across code/name/tags/description + symptom scoring
    3. Fall back to LM Studio Qwen for unknown faults

    Returns dict with: fault_code, fault_name, equipment_type, diagnosis,
    fix_steps, confidence, source, and optionally photo_insight, field_trick.
    """
    db = load_fault_db()

    # --- Phase 1: Exact code match ---
    code_clean = fault_code.strip().upper() if fault_code else ""
    for entry in db:
        if code_clean and entry.get("code", "").upper() == code_clean:
            result = _build_result(entry, equipment_type, 0.90, "fault_database")
            return _attach_photo(result, photo_analysis)

    # If the fault_code field looks like natural language (has spaces or is all
    # alpha), merge it into symptoms for better fuzzy matching
    combined_symptoms = symptoms or ""
    code_for_fuzzy = code_clean
    if fault_code and " " in fault_code.strip():
        combined_symptoms = f"{fault_code} {symptoms}".strip()
        code_for_fuzzy = ""  # Don't try to match it as a code

    # --- Phase 2: Fuzzy match ---
    scored = []
    for entry in db:
        if not _equipment_match(equipment_type, entry):
            continue  # Skip equipment mismatch unless general

        code_s = _fuzzy_score(code_for_fuzzy, entry) if code_for_fuzzy else 0.0
        symp_s = _symptom_score(combined_symptoms, entry)

        # Also try matching the original fault_code text against entry fields
        # for partial code lookups like "10036" or "piler auto"
        if fault_code and not code_for_fuzzy:
            code_s = max(code_s, _fuzzy_score(fault_code.strip(), entry))

        # Weighted combined score
        combined = max(code_s, symp_s * 0.9, (code_s * 0.6 + symp_s * 0.4))
        if combined > 0.3:
            scored.append((combined, entry))

    scored.sort(key=lambda x: x[0], reverse=True)

    if scored and scored[0][0] >= 0.4:
        best_score, best_entry = scored[0]
        confidence = min(best_score * 0.95, 0.92)
        result = _build_result(best_entry, equipment_type, confidence, "fuzzy_match")
        return _attach_photo(result, photo_analysis)

    # --- Phase 3: LLM fallback (with graceful degradation) ---
    result = _llm_diagnose(equipment_type, fault_code, symptoms, config)

    # Graceful degradation: if LLM failed and we had any fuzzy matches, prefer those
    if result.get("source") == "fallback" and scored and scored[0][0] >= 0.25:
        best_score, best_entry = scored[0]
        result = _build_result(best_entry, equipment_type, best_score * 0.7, "fallback_fuzzy")
        result["ai_note"] = "AI engine temporarily unavailable. Showing best database match."

    return _attach_photo(result, photo_analysis)


def _build_result(entry: dict, equipment_type: str, confidence: float, source: str) -> dict:
    """Build a diagnosis result dict from a fault DB entry."""
    result = {
        "fault_code": entry.get("code", "UNKNOWN"),
        "fault_name": entry.get("name", "Unknown Fault"),
        "equipment_type": equipment_type or entry.get("equipment_type", "unknown"),
        "description": entry.get("description", ""),
        "diagnosis": entry.get("probable_causes", []),
        "fix_steps": entry.get("fix_steps", []),
        "severity": entry.get("severity", "medium"),
        "confidence": confidence,
        "source": source,
    }
    if entry.get("field_trick"):
        result["field_trick"] = entry["field_trick"]

    # Attach replacement parts suggestions based on fault category
    parts_category = entry.get("parts_category", "")
    if parts_category:
        parts = get_parts_for_category(parts_category)
        if parts:
            result["parts_category"] = parts_category
            result["suggested_parts"] = parts
    return result


def _attach_photo(result: dict, photo_analysis: dict | None) -> dict:
    """Attach photo analysis and adjust confidence if available."""
    if photo_analysis:
        result["photo_insight"] = photo_analysis
        if photo_analysis.get("identified_issue"):
            result["confidence"] = min(result.get("confidence", 0.5) + 0.05, 0.99)
    return result


def _llm_diagnose(equipment_type: str, fault_code: str, symptoms: str, config: dict) -> dict:
    """AI diagnosis with cloud-first provider chain. Works 24/7 without local PC.

    Provider chain: MiniMax M2.7 → Groq → LM Studio (local) → fallback
    """
    import os
    import urllib.request

    prompt = f"""You are an industrial automation repair expert. Diagnose this fault.

Equipment type: {equipment_type or 'unknown'}
Fault code: {fault_code or 'none provided'}
Symptoms: {symptoms or 'none described'}

Respond in JSON with these exact keys:
- fault_name: short name for this fault
- diagnosis: array of probable causes, ordered most likely first
- fix_steps: array of step-by-step repair instructions in field-tech language
- severity: one of "critical", "high", "medium", "low"
- confidence: number 0-1 for your confidence

Be specific and practical. Include sensor checks, wiring checks, PLC input verification where relevant."""

    # Provider chain — cloud first, local last
    providers = [
        {
            "name": "minimax",
            "url": "https://api.minimaxi.chat/v1/chat/completions",
            "model": "MiniMax-M2.7",
            "key_env": "MINIMAX_API_KEY",
            "timeout": 30,
        },
        {
            "name": "groq",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "model": "llama-3.3-70b-versatile",
            "key_env": "GROQ_API_KEY",
            "timeout": 15,
        },
        {
            "name": "lm_studio",
            "url": config.get("lm_studio", {}).get("base_url", "http://127.0.0.1:1234/v1") + "/chat/completions",
            "model": config.get("lm_studio", {}).get("text_model", "qwen3.5-9b"),
            "key_env": None,
            "timeout": 60,
        },
    ]

    for provider in providers:
        try:
            api_key = os.environ.get(provider["key_env"], "") if provider["key_env"] else None
            if provider["key_env"] and not api_key:
                continue  # Skip if no key configured

            payload = json.dumps({
                "model": provider["model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 1000,
            }).encode()

            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            req = urllib.request.Request(provider["url"], data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=provider["timeout"]) as res:
                data = json.loads(res.read())
                content = data["choices"][0]["message"]["content"]
                # Strip thinking tags if present (MiniMax M2.7)
                if "<think>" in content:
                    content = content.split("</think>")[-1].strip()
                # Try to parse as JSON
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    # Extract JSON from markdown code blocks
                    import re as _re
                    match = _re.search(r"\{[^{}]*\}", content, _re.DOTALL)
                    if match:
                        parsed = json.loads(match.group())
                    else:
                        continue

                return {
                    "fault_code": fault_code or "UNKNOWN",
                    "fault_name": parsed.get("fault_name", "Unknown Fault"),
                    "equipment_type": equipment_type or "unknown",
                    "diagnosis": parsed.get("diagnosis", ["Unable to determine root cause"]),
                    "fix_steps": parsed.get("fix_steps", ["Inspect equipment manually"]),
                    "severity": parsed.get("severity", "medium"),
                    "confidence": parsed.get("confidence", 0.5),
                    "source": f"llm_{provider['name']}",
                }
        except Exception:
            continue  # Try next provider

    # All providers failed — return generic fallback
    return {
        "fault_code": fault_code or "UNKNOWN",
        "fault_name": "Diagnosis Unavailable",
        "equipment_type": equipment_type or "unknown",
        "diagnosis": [
            "AI engine temporarily unavailable — showing general inspection steps",
            "Manual inspection recommended — see steps below",
        ],
        "fix_steps": [
            "Check sensor LEDs at fault location — identify which sensor is involved",
            "Verify PLC input status for related signals — monitor live in PLC software",
            "Check wiring continuity from sensor to PLC input card with multimeter",
            "Toggle inhibit/reset switch and observe machine behavior",
            "Check VFD display for fault codes if drives are involved",
            "Contact equipment manufacturer with fault code for documentation",
        ],
        "severity": "medium",
        "confidence": 0.25,
        "source": "fallback",
        "ai_note": "All AI engines unavailable. Using generic troubleshooting steps.",
    }
