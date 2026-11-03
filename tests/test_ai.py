"""Offline AI contracts; all Gemini requests here use injected transports."""
from dataclasses import replace
import json
import random
import threading
import time
from types import SimpleNamespace

import pytest

from civsandbox.actions import Action, ActionType, validate
from civsandbox.agents import Agent
from civsandbox.ai import (DECISION_SCHEMA, GeminiDecisionProvider, MockDecisionProvider,
                           parse_decision)
from civsandbox.config import Settings, create_provider
from civsandbox.perception import observe
from civsandbox.resources import Resources
from civsandbox.simulation import Simulation
from civsandbox.world import Tile, World


def response(kind="WAIT", target=None, reasoning="A safe local choice."):
    return json.dumps({"action": kind, "target": target, "reasoning": reasoning})


def tiny_world():
    world = World(((Tile.GRASS, Tile.GRASS, Tile.BUSH),
                   (Tile.GRASS, Tile.GRASS, Tile.GRASS)))
    agent = Agent("a", "Ada", (0, 0), (0, 0, 0))
    return agent, world, Resources(world)


def settings(**kwargs):
    return Settings(provider="gemini", api_key="test-secret-not-a-real-key", model="test-model", **kwargs)


def wait_jobs(provider):
    for job in provider.pending.values():
        assert job.done.wait(2), "test transport did not finish"


@pytest.mark.parametrize("raw", ["not json", "{}", "null", "[]",
    response("UNKNOWN"), response("EAT", {"x": 0, "y": 0}),
    response("MOVE_TO"), response("MOVE_TO", {"x": True, "y": 0}),
    response("MOVE_TO", {"x": 1.5, "y": 0}), response("MOVE_TO", [1, 0]),
    response(reasoning=""), response(reasoning="a"*161),
    json.dumps({"action": "WAIT", "target": None, "reasoning": "ok", "code": "print(1)"}),
])
def test_strict_structured_output(raw):
    with pytest.raises((ValueError, TypeError)):
        parse_decision(raw)


def test_secret_redaction_and_typed_action():
    secret = "test-secret"
    action = parse_decision(response("MOVE_TO", {"x": 1, "y": 0}, secret), secret)
    assert action.kind == ActionType.MOVE_TO and action.target == (1, 0)
    assert secret not in action.reasoning
    assert secret not in repr(Settings(api_key=secret))


def test_local_context_excludes_distant_and_private_state():
    world = World((tuple([Tile.GRASS]*10 + [Tile.BUSH]),))
    resources = Resources(world)
    agent = Agent("a", "Ada", (0, 0), (0, 0, 0))
    near = Agent("b", "Basil", (2, 0), (0, 0, 0), hunger=99)
    far = Agent("c", "SecretNPC", (9, 0), (0, 0, 0))
    context, choices, local, stocks = observe(agent, world, resources, [agent, near, far])
    assert context["nearby_npcs"] == [{"id": "b", "name": "Basil", "position": [2, 0]}]
    assert context["resources"] == []
    assert all(t["position"][0] <= 4 for t in context["tiles"])
    assert all(c.target is None or c.target[0] <= 4 for c in choices)
    assert "SecretNPC" not in json.dumps(context)
    assert not local.walkable((5, 0)) and stocks.available((10, 0)) == 0
    assert all(validate(c, agent, local, stocks) for c in choices)
    assert context["agent"]["personality"] == agent.personality


def test_mock_plan_continues_without_requests_per_step():
    world = World((tuple([Tile.GRASS]*8),))
    agent = Agent("a", "Ada", (0, 0), (0, 0, 0))
    resources = Resources(world)
    provider = MockDecisionProvider(responses=[response("MOVE_TO", {"x": 4, "y": 0})])
    from civsandbox.actions import execute
    for tick in range(1, 5):
        provider.begin_tick(tick, [agent])
        action = provider.decide(agent, world, resources, random.Random(0))
        assert execute(action, agent, world, resources, tick)
    assert agent.position == (4, 0)
    assert provider.requests == 1 and provider.api_calls == 0
    assert provider.summary()["provider"] == "mock"


def test_invalid_mock_decision_falls_back_and_logs_reason():
    provider = MockDecisionProvider(responses=[response("MOVE_TO", {"x": -1, "y": 0})]*4)
    sim = Simulation(decision_provider=provider)
    sim.step()
    assert all(s["fallback"] for s in provider.status.values())
    assert all(s["reason"] == "action was not an offered choice" for s in provider.status.values())
    assert all(sim.world.walkable(a.position) for a in sim.agents)
    assert any(e["action"] == "AI_DECISION" and e["fallback"] for e in sim.events)


@pytest.mark.parametrize("failure", [ValueError("SECRET do not log"), ConnectionError("secret URL"),
                                    TimeoutError("secret key")])
def test_api_failures_are_sanitized_and_fallback_is_usable(failure):
    def transport(context):
        raise failure
    provider = GeminiDecisionProvider(settings(), transport=transport)
    agent, world, resources = tiny_world()
    rng = random.Random(0)
    provider.decide(agent, world, resources, rng)
    wait_jobs(provider)
    action = provider.decide(agent, world, resources, rng)
    assert validate(action, agent, world, resources)
    assert provider.status[agent.id]["reason"] == "API request failed"
    assert "SECRET" not in json.dumps(provider.summary())
    assert provider.api_calls == 1
    provider.close()


def test_rate_limit_backoff_uses_cooldown_and_budget():
    class RateLimit(Exception):
        code = 429
    def transport(context):
        raise RateLimit("sensitive response")
    provider = GeminiDecisionProvider(settings(max_calls=2, cooldown_ticks=5), transport=transport)
    agent, world, resources = tiny_world()
    provider.begin_tick(1, [agent])
    provider.decide(agent, world, resources, random.Random(0))
    wait_jobs(provider)
    provider.decide(agent, world, resources, random.Random(0))
    assert provider.status[agent.id]["reason"] == "rate limited"
    for tick in range(2, 6):
        provider.begin_tick(tick, [agent])
        provider.decide(agent, world, resources, random.Random(0))
    assert provider.api_calls == 1
    provider.begin_tick(6, [agent])
    provider.decide(agent, world, resources, random.Random(0))
    wait_jobs(provider)
    provider.decide(agent, world, resources, random.Random(0))
    provider.begin_tick(11, [agent])
    provider.decide(agent, world, resources, random.Random(0))
    assert provider.api_calls == 2
    assert provider.status[agent.id]["reason"] == "API budget exhausted"
    provider.close()


def test_global_budget_across_agents_and_missing_config():
    provider = GeminiDecisionProvider(settings(max_calls=2), transport=lambda c: response())
    sim = Simulation(decision_provider=provider)
    sim.step()
    wait_jobs(provider)
    assert provider.api_calls == 2
    assert any(s["reason"] == "API budget exhausted" for s in provider.status.values())
    sim.close()
    no_key = GeminiDecisionProvider(Settings(provider="gemini"))
    sim = Simulation(decision_provider=no_key)
    sim.step()
    assert no_key.api_calls == 0
    assert all(s["reason"] == "missing API key or model" for s in no_key.status.values())
    sim.close()


def test_response_revalidated_after_inventory_changes():
    provider = GeminiDecisionProvider(settings(), transport=lambda c: response("EAT"))
    agent, world, resources = tiny_world()
    agent.food = 1
    provider.decide(agent, world, resources, random.Random(0))
    wait_jobs(provider)
    agent.food = 0
    action = provider.decide(agent, world, resources, random.Random(0))
    assert action.kind != ActionType.EAT
    assert provider.status[agent.id]["reason"] == "decision became invalid before execution"
    provider.close()


def test_timeout_discards_late_results_and_retains_worker_slot():
    gate = threading.Event()
    now = [0.0]
    def transport(context):
        gate.wait(2)
        return response()
    provider = GeminiDecisionProvider(settings(timeout_seconds=1), transport=transport,
                                      clock=lambda: now[0])
    agent, world, resources = tiny_world()
    try:
        provider.decide(agent, world, resources, random.Random(0))
        now[0] = 1.1
        for tick in range(1, 200):
            provider.begin_tick(tick, [agent])
            provider.decide(agent, world, resources, random.Random(0))
        assert provider.api_calls == 1 and len(provider.pending) == 1
        assert provider.status[agent.id]["reason"] == "request timed out"
        gate.set()
        wait_jobs(provider)
        provider.decide(agent, world, resources, random.Random(0))
        assert agent.id not in provider.pending
        assert provider.status[agent.id]["decision"] == "none"  # late WAIT never accepted
    finally:
        gate.set()
        provider.close()


def test_pending_network_does_not_block_simulation_rendering_or_shutdown():
    gate = threading.Event()
    def transport(context):
        gate.wait(3)
        return response()
    provider = GeminiDecisionProvider(settings(), transport=transport)
    sim = Simulation(decision_provider=provider)
    try:
        start = time.monotonic()
        for _ in range(15):
            sim.step()
        import pygame
        from civsandbox.rendering import Renderer, handle_event
        from civsandbox.simulation import FixedTicker
        renderer = Renderer()
        renderer.draw(sim, FixedTicker())
        assert not handle_event(pygame.event.Event(pygame.QUIT), sim, FixedTicker())
        sim.close()
        assert time.monotonic()-start < 2
        assert sim.tick == 15 and provider.api_calls == 4 and provider.closed
        assert len(provider.pending) == 4
    finally:
        gate.set()
        wait_jobs(provider)
        sim.close()
        pygame.quit()


def test_settings_env_precedence_and_provider_factory(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("AI_PROVIDER=mock\nGEMINI_MODEL=test-model\nMAX_AI_CALLS_PER_RUN=7\n")
    monkeypatch.setenv("MAX_AI_CALLS_PER_RUN", "3")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    config = Settings.load(path)
    assert config.max_calls == 3 and config.model == "test-model"
    assert isinstance(create_provider(config), MockDecisionProvider)
    assert create_provider(replace(config, provider="rule-based")).__class__.__name__ == "RuleBasedDecisionProvider"
    assert isinstance(create_provider(replace(config, provider="gemini")), GeminiDecisionProvider)
    with pytest.raises(ValueError):
        Settings(max_calls=-1)
    with pytest.raises(ValueError):
        Settings(provider="unknown")


def test_official_sdk_uses_schema_timeout_and_no_retries(monkeypatch):
    from google import genai
    captured = {}
    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.models = self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            captured["closed"] = True
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text=response())
    monkeypatch.setattr(genai, "Client", FakeClient)
    provider = GeminiDecisionProvider(settings())
    assert parse_decision(provider.generate({"local": True})).kind == ActionType.WAIT
    assert captured["model"] == "test-model"
    assert captured["http_options"].timeout == 8000
    assert captured["http_options"].retry_options.attempts == 1
    assert captured["config"].response_json_schema == DECISION_SCHEMA
    assert captured["config"].response_mime_type == "application/json"
    assert captured["closed"]


def test_mock_reproducibility_and_no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline mock attempted a network call")
    import socket
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    a = Simulation(7, MockDecisionProvider())
    b = Simulation(7, MockDecisionProvider())
    for _ in range(150):
        a.step()
        b.step()
    assert a.snapshot() == b.snapshot()
    assert a.ai_summary()["api_calls"] == 0
    assert a.ai_summary()["requests"] < 4*150/4


def test_no_key_local_fallback_explores_and_manages_needs():
    provider = GeminiDecisionProvider(Settings(provider="gemini"))
    sim = Simulation(42, provider)
    for _ in range(400):
        sim.step()
    assert provider.api_calls == 0
    assert any(e["action"] == "GATHER" for e in sim.events)
    assert any(e["action"] == "EAT" for e in sim.events)
    assert all(sim.world.walkable(a.position) for a in sim.agents)
    sim.close()


def test_successful_gemini_plan_executes_without_step_calls():
    from civsandbox.actions import execute
    agent = Agent("a", "Ada", (0, 0), (0, 0, 0))
    world = World((tuple([Tile.GRASS]*8),))
    resources = Resources(world)
    provider = GeminiDecisionProvider(settings(), transport=lambda c: response("MOVE_TO", {"x": 4, "y": 0}))
    provider.decide(agent, world, resources, random.Random(0))
    wait_jobs(provider)
    for tick in range(1, 5):
        provider.begin_tick(tick, [agent])
        action = provider.decide(agent, world, resources, random.Random(0))
        assert execute(action, agent, world, resources, tick)
    assert agent.position == (4, 0) and provider.api_calls == 1
    assert not provider.status[agent.id]["fallback"]
    provider.close()


def test_pause_delayed_poll_accepts_response_completed_before_timeout():
    now = [0.0]
    provider = GeminiDecisionProvider(settings(), transport=lambda c: response(), clock=lambda: now[0])
    agent, world, resources = tiny_world()
    provider.decide(agent, world, resources, random.Random(0))
    wait_jobs(provider)
    now[0] = 100.0
    action = provider.decide(agent, world, resources, random.Random(0))
    assert action.kind == ActionType.WAIT and not provider.status[agent.id]["fallback"]
    provider.close()


def test_stale_but_still_legal_reply_uses_local_fallback():
    provider = GeminiDecisionProvider(settings(), transport=lambda _: response())
    agent, world, resources = tiny_world()
    provider.begin_tick(1, [agent])
    provider.decide(agent, world, resources, random.Random(0))
    wait_jobs(provider)
    provider.begin_tick(13, [agent])
    replacement = provider.decide(agent, world, resources, random.Random(0))
    assert validate(replacement, agent, world, resources)
    assert provider.status[agent.id]["reason"].startswith("stale decision")
    assert not provider.plans and provider.api_calls == 1


def test_nested_malformed_response_is_atomic():
    provider = MockDecisionProvider()
    agent, world, resources = tiny_world()
    raw = "["*1500 + "0" + "]"*1500
    assert provider.accept(raw, [], agent, world, resources) == (None, "malformed response")
    assert not provider.plans and agent.goal is None and agent.food == 0


def test_switch_to_unconfigured_gemini_labels_offline_rules():
    offline = create_provider(Settings(provider="gemini"))
    mock = create_provider(Settings(provider="mock"))
    sim = Simulation(decision_provider=offline)
    sim.step()
    assert sim.ai_summary()["mode"] == "offline rules"
    assert all(state["fallback"] for state in offline.status.values())
    assert mock.summary()["provider"] == "mock" and offline.api_calls == 0


def test_sdk_wire_format_and_public_explanation(monkeypatch):
    """Exercise installed SDK serialization and response decoding without a network."""
    import httpx
    seen = []
    def send(client, request, **kwargs):
        payload = json.loads(request.content)
        seen.append(payload)
        parts = [{"thought": True, "text": "private trace"},
                 {"text": response(reasoning="Save energy for gathering.")}]
        return httpx.Response(200, request=request, json={
            "candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP"}]})
    monkeypatch.setattr(httpx.Client, "send", send)
    provider = GeminiDecisionProvider(settings())
    action = parse_decision(provider.generate({"valid_actions": [{"action": "WAIT", "target": None}]}))
    assert action.reasoning == "Save energy for gathering."
    assert len(seen) == 1
    assert seen[0]["generationConfig"]["responseJsonSchema"] == DECISION_SCHEMA
