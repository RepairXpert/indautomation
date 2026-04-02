"""Photo-based diagnosis via LM Studio vision model."""
import base64
import json
import urllib.request


def analyze_photo(photo_bytes: bytes, equipment_type: str, fault_code: str, config: dict) -> dict:
    """Send equipment photo to vision LLM for analysis.

    Returns dict with: identified_issue, sensor_type, alignment_assessment,
    wiring_observations, target_condition, recommendations.
    """
    lm = config.get("lm_studio", {})
    base_url = lm.get("vision_base_url") or lm.get("base_url", "http://127.0.0.1:8766/v1")
    model = lm.get("vision_model", "glm-4v-flash")
    timeout = config.get("lm_studio", {}).get("timeout", 60)

    b64 = base64.b64encode(photo_bytes).decode()

    prompt = f"""You are an industrial automation repair expert examining equipment photos.

Equipment type: {equipment_type or 'unknown'}
Fault code: {fault_code or 'none'}

Analyze this photo and identify:
1. What type of sensor or component is shown (inductive prox, photoelectric, limit switch, VFD, motor, etc.)
2. Any visible alignment issues (sensor gap, target plate position, bracket angle)
3. Wiring condition (loose connections, damage, routing issues, color coding)
4. Target/actuator condition (bent, worn, corroded, misaligned)
5. Environmental concerns (dust, moisture, heat damage, contamination)
6. Your recommended fix based on what you see

Respond in JSON with keys:
- identified_issue: string summary of what you see wrong
- sensor_type: string identifying the component type
- alignment_assessment: string describing alignment condition
- wiring_observations: string describing wiring condition
- target_condition: string describing target/actuator state
- recommendations: array of specific fix recommendations"""

    try:
        payload = json.dumps({
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }],
            "temperature": 0.2,
            "max_tokens": 800,
        }).encode()

        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.loads(res.read())
            content = data["choices"][0]["message"]["content"]
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"identified_issue": content, "source": "raw_vision"}
    except Exception as e:
        return {"identified_issue": None, "error": str(e), "source": "vision_failed"}
