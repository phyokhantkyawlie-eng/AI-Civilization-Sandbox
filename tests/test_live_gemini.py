"""Skipped unless explicitly requested; makes at most one real API call."""
import os

import pytest


@pytest.mark.skipif(os.getenv("RUN_GEMINI_SMOKE") != "1", reason="live Gemini test is opt-in")
def test_live_gemini_smoke():
    from civsandbox.smoke_test import run_smoke
    assert run_smoke() == 0
