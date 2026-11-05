"""Social rules use explicit action fixtures; production decisions remain provider-owned."""
from dataclasses import asdict
import json
import random

import pytest

from civsandbox.actions import Action, ActionType, execute, validate
from civsandbox.agents import Agent, PERSONALITIES
from civsandbox.ai import GeminiDecisionProvider, MockDecisionProvider, parse_decision
from civsandbox.config import Settings
from civsandbox.decisions import RuleBasedDecisionProvider
from civsandbox.perception import action_dict, observe
from civsandbox.resources import Resources
from civsandbox.simulation import Simulation
from civsandbox.social import SocialSystem
from civsandbox.world import Tile, World


def group(memory_enabled=True, path=None):
    agents = [Agent("a", "Ada", (0, 0), (0, 0, 0), hunger=75),
              Agent("b", "Basil", (1, 0), (0, 0, 0), food=3, hunger=10),
              Agent("c", "Cleo", (5, 0), (0, 0, 0))]
    world = World((tuple([Tile.GRASS]*6),))
    social = SocialSystem(agents, memory_enabled, path)
    social.advance(1)
    return agents, world, Resources(world), social


def request_food(agents, world, resources, social):
    assert execute(Action(ActionType.REQUEST_FOOD, "b"), agents[0], world, resources, 1, social)
    return next(iter(social.pending.values()))


def test_distinct_initial_numeric_personalities_and_neutral_directed_trust():
    sim = Simulation()
    assert [a.personality_name for a in sim.agents] == ["Generous", "Selfish", "Cautious", "Friendly"]
    assert len({tuple(a.personality.items()) for a in sim.agents}) == 4
    assert all(0 <= v <= 1 for a in sim.agents for v in a.personality.values())
    assert all(a.trust == {b.id: 0 for b in sim.agents if b.id != a.id} for a in sim.agents)
    assert all(not a.memories for a in sim.agents)


def test_request_share_conservation_and_directed_memories():
    agents, world, resources, social = group()
    request = request_food(agents, world, resources, social)
    assert request.requester_id == "a" and request.recipient_id == "b" and request.urgent
    before = sum(a.food for a in agents)
    share = Action(ActionType.SHARE_FOOD, "a", request_id=request.id)
    assert execute(share, agents[1], world, resources, 1, social)
    assert (agents[0].food, agents[1].food) == (1, 2)
    assert sum(a.food for a in agents) == before
    assert agents[0].trust["b"] == 6 and agents[1].trust["a"] == 2
    assert agents[2].trust["a"] == agents[2].trust["b"] == 0
    assert agents[0].memories[-1].trust_delta == 6
    assert agents[1].memories[-1].trust_delta == 2
    assert agents[0].memories[-1].actor_id == "b" and agents[0].memories[-1].target_id == "a"
    assert agents[0].memories[-1].tick == 1
    assert not social.pending
    assert not execute(share, agents[1], world, resources, 1, social)
    assert sum(a.food for a in agents) == before


def test_refusal_expiry_and_invalid_answer_events():
    agents, world, resources, social = group()
    request = request_food(agents, world, resources, social)
    refuse = Action(ActionType.REFUSE_REQUEST, "a", request_id=request.id)
    assert execute(refuse, agents[1], world, resources, 1, social)
    assert agents[0].trust["b"] == -2 and agents[1].trust["a"] == 0
    assert sum(a.food for a in agents) == 3
    social.advance(social.tick + social.settings.request_retry_ticks)
    second = request_food(agents, world, resources, social)
    social.advance(second.expires_tick-1)
    assert validate(Action(ActionType.REFUSE_REQUEST, "a", request_id=second.id),
                    agents[1], world, resources, social)
    social.advance(second.expires_tick)
    expired = Action(ActionType.SHARE_FOOD, "a", request_id=second.id)
    assert not execute(expired, agents[1], world, resources, social.tick, social)
    social.reject(expired, agents[1])
    assert agents[0].trust["b"] == -2  # proportionate refusal, expiry and invalid attempts do not punish trust
    assert any(e["result"] == "expired" for e in social.events)
    assert any(e["result"].startswith("failed:") for e in social.events)


@pytest.mark.parametrize("action,actor", [
    (Action(ActionType.REQUEST_FOOD, "missing"), 0),
    (Action(ActionType.REQUEST_FOOD, "a"), 0),
    (Action(ActionType.REQUEST_FOOD, "c"), 0),
    (Action(ActionType.TALK, (1, 0)), 0),
    (Action(ActionType.TALK, "c"), 0),
    (Action(ActionType.TALK, "b", request_id="unexpected"), 0),
    (Action(ActionType.SHARE_FOOD, "a"), 1),
    (Action(ActionType.REFUSE_REQUEST, "a", request_id="bogus"), 1),
    (Action(ActionType.SHARE_FOOD, "a", request_id=[]), 1),
    (Action(ActionType.WAIT, request_id="bogus"), 0),
])
def test_invalid_social_actions_do_not_change_physical_or_historical_state(action, actor):
    agents, world, resources, social = group()
    before = [asdict(a) for a in agents]
    assert not execute(action, agents[actor], world, resources, 1, social)
    assert [asdict(a) for a in agents] == before
    assert not social.pending and not social.events


def test_duplicate_requests_wrong_actor_empty_stock_full_receiver_and_distance():
    agents, world, resources, social = group()
    req = request_food(agents, world, resources, social)
    assert not execute(Action(ActionType.REQUEST_FOOD, "b"), agents[0], world, resources, 1, social)
    answer = Action(ActionType.SHARE_FOOD, "a", request_id=req.id)
    assert not execute(answer, agents[2], world, resources, 1, social)
    agents[1].food = 0
    assert not execute(answer, agents[1], world, resources, 1, social)
    agents[1].food, agents[0].food = 1, 5
    assert not execute(answer, agents[1], world, resources, 1, social)
    agents[0].food, agents[0].position = 0, (4, 0)
    assert not execute(answer, agents[1], world, resources, 1, social)
    assert req.id in social.pending


def test_talk_trust_bounds_and_bounded_relevant_recall():
    agents, world, resources, social = group()
    for tick in range(1, 130):
        social.advance(tick)
        assert execute(Action(ActionType.TALK, "b"), agents[0], world, resources, tick, social)
    assert agents[0].trust["b"] == agents[1].trust["a"] == 100
    assert len(agents[0].memories) == len(agents[1].memories) == social.memory_limit
    assert len(social.relevant_memories(agents[0], {"b"})) == 6
    assert social.relevant_memories(agents[0], {"c"}) == []
    assert agents[0].memories[-1].trust_delta == 0  # actual clipped effect recorded
    for _ in range(100):
        social.advance(social.tick + social.settings.request_retry_ticks)
        req = request_food(agents, world, resources, social)
        execute(Action(ActionType.REFUSE_REQUEST, "a", request_id=req.id),
                agents[1], world, resources, social.tick, social)
    assert agents[0].trust["b"] == -100 and agents[1].trust["a"] == 100


def test_memory_disabled_context_has_no_history_or_trust_proxy():
    agents, world, resources, social = group(False)
    before, choices_before, _, _ = observe(agents[0], world, resources, agents, social=social)
    # Change history only, leaving physical state, goals and immediate requests identical.
    social.record("a", "b", "TALK", "greeted", {"a": 87, "b": -35})
    after, choices_after, _, _ = observe(agents[0], world, resources, agents, social=social)
    assert before == after and choices_before == choices_after
    assert "memories" not in after["social"] and "relationships" not in after["social"]
    assert social.relevant_memories(agents[0], {"b"}) == []
    assert social.trust_for(agents[0], "b") == 0
    assert agents[0].trust["b"] == 87  # audit storage is independent of recall
    social.memory_enabled = True
    context, _, _, _ = observe(agents[0], world, resources, agents, social=social)
    assert context["social"]["relationships"] == {"b": 87}
    assert len(context["social"]["memories"]) == 1
    assert "c" not in context["social"]["relationships"]  # distant Cleo excluded


def test_memory_off_keeps_immediate_requests_and_physical_state():
    agents, world, resources, social = group(False)
    req = request_food(agents, world, resources, social)
    context, choices, _, _ = observe(agents[1], world, resources, agents, social=social)
    assert context["agent"]["food"] == 3
    assert context["social"]["active_requests"][0]["id"] == req.id
    assert Action(ActionType.SHARE_FOOD, "a", request_id=req.id) in choices
    assert Action(ActionType.REFUSE_REQUEST, "a", request_id=req.id) in choices
    assert not {"memories", "relationships", "trust"} & context["agent"].keys()


def test_atomic_persistence_restore_monotonic_time_and_no_physical_restore(tmp_path):
    path = tmp_path / "social.json"
    agents, world, resources, social = group(path=path)
    req = request_food(agents, world, resources, social)
    execute(Action(ActionType.SHARE_FOOD, "a", request_id=req.id), agents[1], world, resources, 1, social)
    social.advance(20)
    social.close()
    assert social.persistence_status == "saved"
    again, _, _, restored = group(path=path)
    assert again[0].trust == agents[0].trust and again[0].memories == agents[0].memories
    assert again[0].food == 0 and again[1].food == 3  # only social history is restored
    assert restored.tick == 21 and restored.sequence == social.sequence
    assert restored.pending == {}
    assert "api_key" not in path.read_text()
    assert list(tmp_path.glob(".social-*")) == []


def test_disabled_memory_still_saves_and_loads_audit_but_never_recalls(tmp_path):
    path = tmp_path / "social.json"
    agents, world, resources, social = group(False, path)
    execute(Action(ActionType.TALK, "b"), agents[0], world, resources, 1, social)
    social.save()
    reloaded, world, resources, restored = group(False, path)
    assert reloaded[0].memories and reloaded[0].trust["b"] == 1
    context, _, _, _ = observe(reloaded[0], world, resources, reloaded, social=restored)
    assert "memories" not in context["social"] and "relationships" not in context["social"]


@pytest.mark.parametrize("contents", ["{broken", '{"version":99}',
    '{"version":1,"tick":0,"sequence":0,"agents":{}}'])
def test_corrupt_history_is_preserved_without_partial_state(tmp_path, contents):
    path = tmp_path / "social.json"
    path.write_text(contents)
    agents, _, _, social = group(path=path)
    assert social.load_failed and all(not a.memories for a in agents)
    social.close()
    assert path.read_text() == contents


def test_invalid_trust_file_does_not_partially_restore(tmp_path):
    path = tmp_path / "social.json"
    agents, _, _, social = group(path=path)
    social.record("a", "b", "TALK", "greeted", {"a": 5, "b": 4})
    social.save()
    payload = json.loads(path.read_text())
    payload["agents"]["c"]["trust"]["a"] = 101
    path.write_text(json.dumps(payload))
    restored, _, _, service = group(path=path)
    assert service.load_failed
    assert all(all(v == 0 for v in a.trust.values()) and not a.memories for a in restored)


def test_rule_traits_influence_choices_without_fixed_social_outcomes():
    counts = []
    for label, traits in PERSONALITIES[:2]:
        shares = 0
        for seed in range(100):
            agents, world, resources, social = group()
            agents[1].personality_name, agents[1].personality = label, traits.copy()
            request_food(agents, world, resources, social)
            provider = RuleBasedDecisionProvider()
            provider.bind_social(social)
            shares += provider.decide(agents[1], world, resources, random.Random(seed)).kind == ActionType.SHARE_FOOD
        counts.append(shares)
    assert 0 < counts[1] < counts[0] < 100  # tendencies, not guaranteed personality outcomes


def test_disabled_memory_rule_decisions_ignore_historical_trust():
    decisions = []
    for trust in (-100, 100):
        agents, world, resources, social = group(False)
        request_food(agents, world, resources, social)
        agents[1].trust["a"] = trust
        provider = RuleBasedDecisionProvider()
        provider.bind_social(social)
        decisions.append(provider.decide(agents[1], world, resources, random.Random(5)))
    assert decisions[0] == decisions[1]


def test_social_schema_and_request_id_round_trip():
    action = Action(ActionType.SHARE_FOOD, "a", "There is spare food.", "request-1")
    assert parse_decision(json.dumps({**action_dict(action), "reasoning": action.reasoning})) == action
    for bad in [Action(ActionType.TALK, (0, 0)), Action(ActionType.SHARE_FOOD, "a"),
                Action(ActionType.REQUEST_FOOD, "b", request_id="invented")]:
        with pytest.raises(ValueError):
            parse_decision(json.dumps({**action_dict(bad), "reasoning": "test"}))


def test_gemini_context_recall_gate_and_expired_reply_revalidation():
    captured = []
    agents, world, resources, social = group(False)
    req = request_food(agents, world, resources, social)
    def transport(context):
        captured.append(context)
        return json.dumps({"action": "SHARE_FOOD", "target": "a", "request_id": req.id,
                           "reasoning": "I have food available."})
    provider = GeminiDecisionProvider(Settings(api_key="offline-test", model="test"), transport=transport)
    provider.bind_social(social)
    provider.begin_tick(1, agents)
    provider.decide(agents[1], world, resources, random.Random(0))
    assert provider.pending["b"].done.wait(2)
    assert "memories" not in captured[0]["social"] and "relationships" not in captured[0]["social"]
    social.advance(req.expires_tick)
    action = provider.decide(agents[1], world, resources, random.Random(0))
    assert action.kind != ActionType.SHARE_FOOD
    assert provider.status["b"]["reason"] == "decision became invalid before execution"
    provider.close()


def test_selected_mock_provider_drives_social_transfer_and_no_engine_script():
    provider = MockDecisionProvider(responses=[
        json.dumps({"action": "REQUEST_FOOD", "target": "npc-2", "reasoning": "Ask nearby."}),
        json.dumps({"action": "SHARE_FOOD", "target": "npc-1", "request_id": "request-1", "reasoning": "Share."}),
        json.dumps({"action": "WAIT", "target": None, "reasoning": "Wait."}),
        json.dumps({"action": "WAIT", "target": None, "reasoning": "Wait."}),
    ])
    from civsandbox.pacing import ActionTiming
    sim = Simulation(decision_provider=provider, timing=ActionTiming.instant())
    sim.agents[0].position, sim.agents[1].position = (2, 2), (3, 2)
    sim.agents[1].food = 3
    sim.step()
    assert (sim.agents[0].food, sim.agents[1].food) == (1, 2)
    assert sim.agents[0].trust["npc-2"] == 6
    assert any(e.get("social") and e["action"] == "SHARE_FOOD" for e in sim.events)
    class WaitProvider:
        def decide(self, *args):
            return Action(ActionType.WAIT)
    passive = Simulation(decision_provider=WaitProvider())
    passive.agents[0].position = passive.agents[1].position = (2, 2)
    passive.agents[1].food = 3
    for _ in range(30):
        passive.step()
    assert all(not a.memories and all(v == 0 for v in a.trust.values()) for a in passive.agents)
    assert (passive.agents[0].food, passive.agents[1].food) == (0, 3)


def test_memory_setting_validation(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("MEMORY_ENABLED=false\nMEMORY_PATH=custom.json\n")
    monkeypatch.delenv("MEMORY_ENABLED", raising=False)
    monkeypatch.delenv("MEMORY_PATH", raising=False)
    config = Settings.load(path)
    assert not config.memory_enabled and config.memory_path == "custom.json"
    path.write_text("MEMORY_ENABLED=maybe\n")
    with pytest.raises(ValueError):
        Settings.load(path)


def test_cautious_personality_builds_positive_trust_more_slowly():
    sim = Simulation()
    sim.social.record("npc-1", "npc-2", "TALK", "greeted", {"npc-2": 12})
    sim.social.record("npc-1", "npc-3", "TALK", "greeted", {"npc-3": 12})
    assert sim.agents[1].trust["npc-1"] == 12
    assert 0 < sim.agents[2].trust["npc-1"] < 12


def test_save_failure_is_reported_without_crashing(tmp_path):
    parent_file = tmp_path / "not-a-directory"
    parent_file.write_text("keep")
    _, _, _, social = group(path=parent_file / "history.json")
    social.close()
    assert social.persistence_status == "save failed"
    assert parent_file.read_text() == "keep"


def test_pending_requests_end_on_close_and_ids_are_not_reused(tmp_path):
    path = tmp_path / "social.json"
    agents, world, resources, social = group(path=path)
    first = request_food(agents, world, resources, social)
    social.close()
    assert not social.pending and agents[0].memories[-1].result == "session ended"
    fresh, world, resources, restored = group(path=path)
    assert not restored.pending
    second = request_food(fresh, world, resources, restored)
    assert first.id != second.id


def test_expired_social_ai_action_is_not_repeated_as_cached_plan():
    agents, world, resources, social = group()
    request = request_food(agents, world, resources, social)
    provider = MockDecisionProvider(responses=[json.dumps({
        "action": "SHARE_FOOD", "target": "a", "request_id": request.id,
        "reasoning": "Respond once."})])
    provider.bind_social(social)
    provider.begin_tick(1, agents)
    action = provider.decide(agents[1], world, resources, random.Random(0))
    assert execute(action, agents[1], world, resources, 1, social)
    provider.begin_tick(2, agents)
    next_action = provider.decide(agents[1], world, resources, random.Random(0))
    assert next_action.kind != ActionType.SHARE_FOOD
    assert provider.requests == 1  # no extra request for this one-shot social action
