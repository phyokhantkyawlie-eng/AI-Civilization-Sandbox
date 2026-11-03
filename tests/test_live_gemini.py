"""Retained marker for historical test reports; this build never runs live tests."""
import pytest


@pytest.mark.skip(reason="External API tests disabled by offline-first project direction")
def test_live_gemini_smoke():
    pass
