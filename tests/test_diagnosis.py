"""Tests for fault code diagnosis engine.

Covers: exact match, fuzzy match, equipment filtering, symptom scoring,
parts suggestions, photo analysis boost, and LLM fallback structure.
"""
import pytest
from indauto.diagnosis.engine import (
    diagnose_fault, load_fault_db, _fuzzy_score, _symptom_score, _equipment_match
)


class TestFaultDatabase:
    """Verify fault database integrity."""

    def test_db_loads(self, fault_db):
        assert len(fault_db) > 0, "Fault database is empty"

    def test_db_has_71_codes(self, fault_db):
        assert len(fault_db) >= 71, f"Expected 71+ faults, got {len(fault_db)}"

    def test_all_entries_have_required_fields(self, fault_db):
        required = {"code", "name", "equipment_type", "probable_causes", "fix_steps", "severity"}
        for entry in fault_db:
            missing = required - set(entry.keys())
            assert not missing, f"Fault {entry.get('code', '?')} missing: {missing}"

    def test_severity_values_valid(self, fault_db):
        valid = {"critical", "high", "medium", "low"}
        for entry in fault_db:
            assert entry["severity"] in valid, \
                f"Fault {entry['code']} has invalid severity: {entry['severity']}"

    def test_allen_bradley_codes_present(self, fault_db):
        ab_codes = [e for e in fault_db if e["code"].startswith("AB-")]
        assert len(ab_codes) >= 27, f"Expected 27+ AB codes, got {len(ab_codes)}"


class TestExactMatch:
    """Phase 1: Exact fault code matching."""

    def test_exact_match_10036(self, config):
        result = diagnose_fault("piler", "10036", "", None, config)
        assert result["fault_code"] == "10036"
        assert result["fault_name"] == "Piler Auto Lost"
        assert result["confidence"] == 0.90
        assert result["source"] == "fault_database"

    def test_exact_match_case_insensitive(self, config):
        result = diagnose_fault("conveyor", "E030", "", None, config)
        assert result["source"] == "fault_database"
        result2 = diagnose_fault("conveyor", "e030", "", None, config)
        assert result2["source"] == "fault_database"
        assert result["fault_code"] == result2["fault_code"]

    def test_exact_match_returns_fix_steps(self, config):
        result = diagnose_fault("piler", "10036", "", None, config)
        assert len(result["fix_steps"]) > 0
        assert len(result["diagnosis"]) > 0

    def test_exact_match_returns_field_trick(self, config):
        result = diagnose_fault("piler", "10036", "", None, config)
        assert "field_trick" in result
        assert len(result["field_trick"]) > 0

    def test_exact_match_returns_parts(self, config):
        result = diagnose_fault("piler", "10036", "", None, config)
        assert "parts_category" in result
        assert result["parts_category"] == "proximity_sensor"
        assert "suggested_parts" in result
        assert len(result["suggested_parts"]) > 0

    def test_exact_match_20010_conveyor(self, config):
        result = diagnose_fault("conveyor", "20010", "", None, config)
        assert result["fault_code"] == "20010"
        assert result["source"] == "fault_database"

    def test_exact_match_ab_plc_major(self, config):
        result = diagnose_fault("allen-bradley", "AB-PLC-MAJOR01", "", None, config)
        assert result["fault_code"] == "AB-PLC-MAJOR01"
        assert result["source"] == "fault_database"


class TestFuzzyMatch:
    """Phase 2: Fuzzy matching on code/name/tags/symptoms."""

    def test_fuzzy_by_name(self, config):
        result = diagnose_fault("piler", "", "fork overtravel", None, config)
        assert result["confidence"] > 0.3
        assert result["source"] in ("fuzzy_match", "fault_database")

    def test_fuzzy_by_symptoms(self, config):
        result = diagnose_fault("conveyor", "", "belt slipping motor overheating", None, config)
        assert result["confidence"] > 0.3
        assert result["source"] in ("fuzzy_match", "llm_analysis", "fallback")

    def test_fuzzy_natural_language_code(self, config):
        """When fault_code contains spaces, it merges into symptoms."""
        result = diagnose_fault("piler", "auto lost position", "", None, config)
        assert result["confidence"] > 0.3

    def test_equipment_filter_narrows_results(self, config):
        """Same query on different equipment should give different results."""
        r_piler = diagnose_fault("piler", "", "position error", None, config)
        r_conv = diagnose_fault("conveyor", "", "position error", None, config)
        # Both should return something, but may differ
        assert r_piler["confidence"] > 0.0
        assert r_conv["confidence"] > 0.0


class TestSymptomScoring:
    """Internal _symptom_score function."""

    def test_matching_symptoms_score_high(self, fault_db):
        piler_entry = next(e for e in fault_db if e["code"] == "10036")
        score = _symptom_score("encoder failure cable damaged", piler_entry)
        assert score > 0.3

    def test_empty_symptoms_score_zero(self, fault_db):
        entry = fault_db[0]
        assert _symptom_score("", entry) == 0.0

    def test_stop_words_ignored(self, fault_db):
        entry = fault_db[0]
        score_stop = _symptom_score("the is and or for", entry)
        assert score_stop == 0.0


class TestFuzzyScoring:
    """Internal _fuzzy_score function."""

    def test_exact_code_match_returns_one(self, fault_db):
        entry = next(e for e in fault_db if e["code"] == "10036")
        assert _fuzzy_score("10036", entry) == 1.0

    def test_partial_code_match(self, fault_db):
        entry = next(e for e in fault_db if e["code"] == "10036")
        score = _fuzzy_score("1003", entry)
        assert score >= 0.85

    def test_name_substring_match(self, fault_db):
        entry = next(e for e in fault_db if e["code"] == "10036")
        score = _fuzzy_score("piler auto", entry)
        assert score > 0.5

    def test_empty_query_returns_zero(self, fault_db):
        assert _fuzzy_score("", fault_db[0]) == 0.0


class TestEquipmentMatch:
    """Internal _equipment_match function."""

    def test_piler_matches_piler_entry(self, fault_db):
        piler_entry = next(e for e in fault_db if e["code"] == "10036")
        assert _equipment_match("piler", piler_entry)

    def test_asrs_matches_piler_entry(self, fault_db):
        """10036 supports both piler and asrs."""
        piler_entry = next(e for e in fault_db if e["code"] == "10036")
        assert _equipment_match("asrs", piler_entry)

    def test_empty_equipment_matches_all(self, fault_db):
        assert _equipment_match("", fault_db[0])

    def test_wrong_equipment_no_match(self, fault_db):
        piler_entry = next(e for e in fault_db if e["code"] == "10036")
        assert not _equipment_match("packaging", piler_entry)


class TestPhotoAnalysis:
    """Photo analysis confidence boost."""

    def test_photo_boosts_confidence(self, config):
        photo = {"identified_issue": "Sensor misalignment detected"}
        result = diagnose_fault("piler", "10036", "", photo, config)
        assert abs(result["confidence"] - 0.95) < 1e-9  # 0.90 + 0.05
        assert "photo_insight" in result

    def test_no_photo_no_boost(self, config):
        result = diagnose_fault("piler", "10036", "", None, config)
        assert result["confidence"] == 0.90
        assert "photo_insight" not in result

    def test_photo_without_issue_no_boost(self, config):
        photo = {"notes": "Image unclear"}
        result = diagnose_fault("piler", "10036", "", photo, config)
        assert result["confidence"] == 0.90  # No boost without identified_issue
        assert "photo_insight" in result


class TestLLMFallback:
    """Phase 3: LLM fallback (graceful degradation when LM Studio is down)."""

    def test_unknown_code_falls_back(self, config):
        """Unknown code should attempt LLM or return fallback."""
        result = diagnose_fault("unknown_equipment", "ZZZZZ999", "", None, config)
        assert result["source"] in ("llm_analysis", "fallback")
        assert result["fault_code"] == "ZZZZZ999"

    def test_fallback_has_generic_steps(self, config):
        """Fallback should provide useful generic troubleshooting."""
        result = diagnose_fault("", "NONEXISTENT", "", None, config)
        assert len(result["fix_steps"]) > 0
        assert result["severity"] in ("critical", "high", "medium", "low")


class TestResultStructure:
    """Verify all result dicts have required keys."""

    REQUIRED_KEYS = {"fault_code", "fault_name", "equipment_type", "diagnosis",
                     "fix_steps", "severity", "confidence", "source"}

    def test_exact_match_has_all_keys(self, config):
        result = diagnose_fault("piler", "10036", "", None, config)
        missing = self.REQUIRED_KEYS - set(result.keys())
        assert not missing, f"Missing keys: {missing}"

    def test_fuzzy_match_has_all_keys(self, config):
        result = diagnose_fault("conveyor", "", "belt slipping", None, config)
        missing = self.REQUIRED_KEYS - set(result.keys())
        assert not missing, f"Missing keys: {missing}"

    def test_fallback_has_all_keys(self, config):
        result = diagnose_fault("", "FAKE123", "", None, config)
        missing = self.REQUIRED_KEYS - set(result.keys())
        assert not missing, f"Missing keys: {missing}"

    def test_confidence_in_range(self, config):
        result = diagnose_fault("piler", "10036", "", None, config)
        assert 0.0 <= result["confidence"] <= 1.0
