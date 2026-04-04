"""Shared fixtures for IndAutomation tests."""
import json
import sys
from pathlib import Path

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from indauto.diagnosis.engine import load_fault_db, diagnose_fault


@pytest.fixture
def fault_db():
    """Load the fault database."""
    return load_fault_db()


@pytest.fixture
def config():
    """Minimal config for tests (no LM Studio dependency)."""
    return {
        "lm_studio": {
            "base_url": "http://127.0.0.1:1234/v1",
            "text_model": "qwen3.5-9b",
            "timeout": 5,
        }
    }
