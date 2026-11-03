import csv
import json

from civsandbox.config import Settings
from civsandbox.experiments import describe, metrics, run_batch, run_trial
from civsandbox.simulation import Simulation


def test_trial_isolation_and_reproducibility(monkeypatch):
    monkeypatch.setenv("MEMORY_PATH", "/invalid/normal/history.json")
    settings = Settings(provider="rule-based")
    a = run_trial(settings, 42, 120, False)
    b = run_trial(settings, 42, 120, True)
    c = run_trial(settings, 42, 120, False)
    assert a["initial_state_sha256"] == b["initial_state_sha256"] == c["initial_state_sha256"]
    for key in ("requests", "shares", "refusals", "average_hunger", "final_trust"):
        assert a[key] == c[key]
    assert a["gemini_calls"] == 0


def test_metrics_denominators_and_missing_survival():
    sim = Simulation()
    sim.events = [{"social": True, "result": result, "action": "social"} for result in
                  ("pending", "pending", "shared one food", "refused")]
    sim.events += [{"action": "WAIT", "hunger_after": 20}, {"action": "WAIT", "hunger_after": 40},
                   {"action": "REJECTED"}]
    m = metrics(sim, 60, 2, 1, .5)
    assert m["cooperation_rate"] == .5 and m["invalid_action_rate"] == .5
    assert m["average_hunger"] == 30 and m["survival_rate"] is None
    sim.events = []
    m = metrics(sim, 0, 0, 0, 0)
    assert m["cooperation_rate"] is m["average_hunger"] is m["invalid_action_rate"] is None


def test_exports_and_failed_trial_recovery(tmp_path, monkeypatch):
    import civsandbox.experiments as module
    original = module.run_trial
    count = 0
    def flaky(*args):
        nonlocal count
        count += 1
        if count == 1:
            raise RuntimeError("sensitive error")
        return original(*args)
    monkeypatch.setattr(module, "run_trial", flaky)
    path = tmp_path/"batch"
    rows = run_batch(Settings(), 2, 5, 42, path)
    payload = json.loads((path/"summary.json").read_text())
    assert len(rows) == 4 and payload["summary"]["failed_trials"] == 1
    assert len(list(csv.DictReader((path/"trials.csv").open()))) == 4
    assert len(payload["summary"]["paired_differences"]) == 1
    assert "sensitive error" not in (path/"summary.json").read_text()


def test_live_requires_explicit_opt_in(monkeypatch):
    import pytest
    from civsandbox.experiments import main
    monkeypatch.setattr("sys.argv", ["experiments", "--provider", "gemini"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_memory_off_context_invariant_and_fresh_caches():
    from civsandbox.ai import MockDecisionProvider
    from civsandbox.perception import observe
    provider = MockDecisionProvider()
    sim = Simulation(decision_provider=provider, memory_enabled=False, scenario="food_shortage")
    args = (sim.agents[0], sim.world, sim.resources, sim.agents)
    before = observe(*args, social=sim.social)[0]
    sim.social.record("npc-1", "npc-2", "TALK", "greeted", {"npc-1": 50})
    assert observe(*args, social=sim.social)[0] == before
    fresh = MockDecisionProvider()
    assert not fresh.plans and not fresh.status and not fresh.last_request
    assert describe([1])["sample_stddev"] is None
