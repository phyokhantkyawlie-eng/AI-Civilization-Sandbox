import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pytest
from civsandbox.inventory import Inventory
from civsandbox.actions import Action, ActionType
from civsandbox.pacing import ActionTiming
from civsandbox.simulation import Simulation, FixedTicker
from civsandbox.ui_state import hunger_status, energy_status


class FixedAction:
    def __init__(self, action):
        self.action = action
    def decide(self, *args):
        return self.action


def test_inventory_atomic_transfer_capacity_and_validation():
    a, b = Inventory(items={"berries": 3}), Inventory(items={"berries": 4})
    assert not a.transfer_to(b, "berries", 2)
    assert a.used == 3 and b.used == 4
    assert a.transfer_to(b, "berries") and (a.used, b.used) == (2, 5)
    assert not b.add("berries") and not a.remove("berries", 3)
    for quantity in (-1, 0, True, 1.5):
        with pytest.raises(ValueError):
            a.add("berries", quantity)
    with pytest.raises(ValueError):
        Inventory(items={"berries": 6})


def test_eating_has_one_delayed_commit_and_pause_speed_are_consistent():
    sim = Simulation(decision_provider=FixedAction(Action(ActionType.EAT)))
    actor = sim.agents[0]
    actor.food, actor.hunger = 1, 60
    ticker = FixedTicker()
    ticker.advance(sim, .25)
    assert actor.food == 1 and actor.current_action == "EAT"
    sim.paused = True
    ticker.advance(sim, 100)
    assert sim.tick == 1 and actor.food == 1
    sim.paused = False
    ticker.speed = 2
    ticker.advance(sim, 1)
    assert sim.tick == 9 and actor.food == 1
    ticker.advance(sim, .25)
    assert sim.tick == 11 and actor.food == 0 and actor.hunger < 60
    for _ in range(20):
        sim.step()
    assert sum(e["action"] == "EAT" and e["executed"] and e.get("item", "berries") == "berries" for e in sim.events) == 1


def test_gather_is_delayed_and_revalidated_when_bush_depletes():
    sim = Simulation()
    bush = next(iter(sim.resources.stocks()))
    actor = sim.agents[0]
    actor.position = sim.world.neighbors(bush)[0]
    sim.decision_provider = FixedAction(Action(ActionType.GATHER, bush))
    sim.step()
    assert actor.food == 0
    for _ in range(sim.resources.available(bush)):
        sim.resources.collect(bush, sim.tick, "test")
    # Complete before the first regeneration tick.
    for _ in range(14):
        sim.step()
    assert actor.food == 0
    assert any(e["action"] == "REJECTED" and e["agent"] == actor.name for e in sim.events)


def test_social_locks_face_each_other_and_cooldown():
    sim = Simulation(scenario="food_shortage", decision_provider=FixedAction(Action(ActionType.TALK, "npc-2")))
    a, b = sim.agents[:2]
    a.hunger = b.hunger = 10
    sim.step()
    assert sim.progress.locks[a.id] == sim.progress.locks[b.id] == a.id
    assert (a.facing, b.facing) == ("right", "left")
    assert not a.memories
    finish = sim.progress.jobs[a.id].finish_tick
    while sim.tick < finish:
        sim.step()
    greetings = [e for e in sim.events if e.get("social") and e["action"] == "TALK" and e.get("result") == "greeted"]
    assert len(greetings) == 1
    for _ in range(10):
        sim.step()
    assert len([e for e in sim.events if e.get("social") and e["action"] == "TALK" and e.get("result") == "greeted"]) == 1


def test_food_shortage_conservation_and_deterministic_paced_state():
    a, b = Simulation(7, scenario="food_shortage"), Simulation(7, scenario="food_shortage")
    initial = sum(actor.food for actor in a.agents)
    for _ in range(250):
        a.step()
        b.step()
    assert a.snapshot() == b.snapshot()
    gathered = sum(c.reason == "gather" for c in a.resources.changes)
    eaten = sum(e["action"] == "EAT" and e["executed"] and e.get("item", "berries") == "berries" for e in a.events)
    assert initial+gathered-eaten == sum(actor.food for actor in a.agents)


def test_status_thresholds_and_inspectable_resource():
    import pygame
    from civsandbox.rendering import Renderer, ORIGIN, TILE_SIZE, handle_event
    sim = Simulation()
    try:
        r = Renderer()
        assert not r.debug
        assert hunger_status(0)[0] == "Full" and hunger_status(100)[0] == "Starving"
        assert energy_status(0)[0] == "Exhausted" and energy_status(100)[0] == "Rested"
        bush = next(iter(sim.resources.stocks()))
        r.select_at((ORIGIN[0]+bush[0]*TILE_SIZE+18, ORIGIN[1]+bush[1]*TILE_SIZE+18), sim)
        assert r.selected_bush == bush and r.selected_id is None
        r.select_at((906, 300), sim)
        assert r.selected_bush == bush
        r.draw(sim, FixedTicker())
        handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F3), sim, FixedTicker(), r)
        assert r.debug
        r.draw(sim, FixedTicker())
    finally:
        sim.close()
        pygame.quit()


def test_request_response_completes_once_and_repeated_pair_waits_for_cooldown():
    from civsandbox.decisions import RuleBasedDecisionProvider
    sim = Simulation(42, scenario="food_shortage")
    # Genuine seeded policy has opportunities; no response outcome is forced.
    for _ in range(120):
        sim.step()
    requests = [e for e in sim.events if e.get("social") and e.get("result") == "pending"]
    answers = [e for e in sim.events if e.get("social") and e.get("result") in ("refused", "shared one food")]
    assert requests and answers
    assert len({e["request_id"] for e in answers}) == len(answers)
    assert all(answer["tick"] >= requests[0]["tick"]+sim.progress.timing.response_ticks for answer in answers)


def test_settings_load_gameplay_timers(tmp_path, monkeypatch):
    from civsandbox.config import Settings
    path = tmp_path/".env"
    path.write_text("GATHER_SECONDS=4\nSOCIAL_COOLDOWN_SECONDS=12\nNEEDS_INTERVAL_SECONDS=1\n")
    for name in ("GATHER_SECONDS", "SOCIAL_COOLDOWN_SECONDS", "NEEDS_INTERVAL_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    config = Settings.load(path)
    assert config.action_timing.gather_ticks == 16
    assert config.action_timing.social_cooldown_ticks == 48
    assert config.action_timing.needs_interval_ticks == 4


def test_cooldown_also_protects_recipient_and_pending_request_stops_move():
    from civsandbox.actions import validate
    sim = Simulation(scenario="food_shortage")
    actor, other = sim.agents[:2]
    sim.social.advance(1)
    sim.progress.cooldowns[other.id] = 30
    assert not validate(Action(ActionType.TALK, other.id), actor, sim.world, sim.resources, sim.social)
    sim.progress.cooldowns.clear()
    from civsandbox.actions import execute
    assert execute(Action(ActionType.REQUEST_FOOD, other.id), actor, sim.world, sim.resources, 1, sim.social)
    before = other.position
    assert sim.progress.execute(Action(ActionType.MOVE_TO, (10, 2)), other,
                                sim.world, sim.resources, 2, "rule-based")
    assert other.position == before


def test_started_gather_and_eat_have_no_premature_inventory_effect():
    sim = Simulation(decision_provider=FixedAction(Action(ActionType.EAT)))
    actor = sim.agents[0]
    actor.food = 2
    sim.step()
    starts = [e for e in sim.events if e.get("accepted_start") and e.get("actor_id") == actor.id]
    assert len(starts) == 1 and starts[0]["action"] == "EAT" and not starts[0]["executed"]
    assert actor.food == 2
    for _ in range(sim.progress.timing.eat_ticks):
        sim.step()
    completions = [e for e in sim.events if e.get("executed") and e["action"] == "EAT" and e.get("actor_id") == actor.id]
    assert len(completions) == 1 and actor.food == 1


def test_provider_choices_exclude_movement_during_pending_conversation():
    from civsandbox.actions import execute, validate
    from civsandbox.perception import observe
    sim = Simulation(scenario="food_shortage")
    a, b = sim.agents[:2]
    assert execute(Action(ActionType.REQUEST_FOOD, b.id), a, sim.world, sim.resources, 0, sim.social)
    context, choices, _, _ = observe(b, sim.world, sim.resources, sim.agents, social=sim.social)
    assert not any(action.kind == ActionType.MOVE_TO for action in choices)
    assert any(action.kind == ActionType.REFUSE_REQUEST for action in choices)


def test_pending_gemini_request_does_not_start_a_long_fallback_harvest():
    import json
    import threading
    from civsandbox.ai import GeminiDecisionProvider
    from civsandbox.config import Settings
    gate = threading.Event()
    def transport(context):
        gate.wait(2)
        choice = next((a for a in context["valid_actions"] if a["action"] == "GATHER"),
                      {"action": "WAIT", "target": None})
        return json.dumps({**choice, "reasoning": "A visible berry bush is ready."})
    provider = GeminiDecisionProvider(Settings(api_key="test", model="test"), transport=transport)
    sim = Simulation(decision_provider=provider)
    actor = sim.agents[0]
    bush = next(iter(sim.resources.stocks()))
    actor.position = sim.world.neighbors(bush)[0]
    try:
        sim.step()
        assert actor.id not in sim.progress.jobs and actor.food == 0
        gate.set()
        for job in provider.pending.values():
            assert job.done.wait(2)
        sim.step()
        assert sim.progress.jobs[actor.id].action.kind == ActionType.GATHER
        assert sim.progress.jobs[actor.id].source == "gemini"
    finally:
        gate.set()
        sim.close()
