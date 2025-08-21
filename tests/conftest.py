# tests/conftest.py

import os
import sys
from pathlib import Path

import pytest

# Add project root to sys.path so 'import ai_analysis' works
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_collection_modifyitems(config, items):
    if not os.getenv("OPENAI_API_KEY"):
        skip_ai = pytest.mark.skip(reason="OPENAI_API_KEY not set")
        for item in items:
            if "needs_openai" in item.keywords:
                item.add_marker(skip_ai)
