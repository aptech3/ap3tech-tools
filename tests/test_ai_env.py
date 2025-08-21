# tests/test_ai_env.py

import importlib


def test_ai_env_missing(monkeypatch):
    # Simulate missing key
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Import a non-GUI module to keep CI headless-safe
    ai = importlib.import_module("ai_analysis")

    # Minimal assertion that the AI entrypoint exists and can be referenced
    assert hasattr(ai, "process_bank_statements_ai")
