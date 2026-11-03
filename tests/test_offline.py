"""Normal entry points must stay offline even with legacy configuration present."""
import builtins
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from civsandbox.config import Settings, create_provider

ROOT = Path(__file__).resolve().parents[1]


def test_default_and_legacy_configuration_are_offline(tmp_path, monkeypatch):
    for name in ("AI_PROVIDER", "GEMINI_API_KEY", "GEMINI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / ".env"
    assert Settings.load(path).provider == Settings().provider == "rule-based"
    path.write_text("AI_PROVIDER=gemini\nGEMINI_API_KEY=unused\nGEMINI_MODEL=unused\n"
                    "MAX_AI_CALLS_PER_RUN=not-a-number\nAI_TIMEOUT_SECONDS=invalid\n")
    settings = Settings.load(path)
    assert settings.provider == "rule-based"
    assert settings.api_key == settings.model == "" and settings.max_calls == 0
    assert Settings.load(path, provider="mock").provider == "mock"


def test_rule_factory_does_not_import_optional_adapter(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in ("ai", "civsandbox.ai") or name.startswith("google"):
            raise AssertionError("Optional adapter imported by rule factory")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert create_provider(Settings()).__class__.__name__ == "RuleBasedDecisionProvider"
    with pytest.raises(ValueError, match="External providers are disabled"):
        create_provider(Settings(provider="gemini"))


@pytest.mark.parametrize("provider", [None, "rule-based", "mock"])
def test_cli_runs_without_network_or_sdk(tmp_path, provider):
    # sitecustomize runs before package imports in the child process, including
    # optional imports. Fail immediately on any attempted connection or SDK use.
    (tmp_path / "sitecustomize.py").write_text('''
import builtins
import socket

def deny(*args, **kwargs):
    raise AssertionError("Network access attempted")
socket.socket.connect = deny
socket.socket.connect_ex = deny
socket.create_connection = deny
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == "google" or name.startswith("google."):
        raise AssertionError("Google SDK imported")
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
''')
    env = {**os.environ, "PYTHONPATH": str(tmp_path) + os.pathsep + str(ROOT),
           "AI_PROVIDER": "gemini", "MEMORY_PATH": str(tmp_path / "history.json")}
    provider_args = ["--provider", provider] if provider else []
    result = subprocess.run([sys.executable, "-m", "civsandbox", "--headless",
                             *provider_args, "--scenario", "food_shortage",
                             "--ticks", "100", "--seed", "42"],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state["tick"] == 100 and state["ai"]["api_calls"] == 0
    assert {a["name"] for a in state["agents"]} == {"Mira", "Ren", "Nyra", "Kairo"}


def test_archived_smoke_cannot_start_external_call(capsys):
    from civsandbox.smoke_test import run_smoke
    assert run_smoke(Settings(provider="gemini")) == 2
    assert "disabled" in capsys.readouterr().out
