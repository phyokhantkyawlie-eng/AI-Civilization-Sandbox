"""Stage 1 contracts: deterministic time, finite food and reversible consequences."""
import random

import pytest

from civsandbox.actions import Action, ActionType, execute, validate
from civsandbox.config import Settings
from civsandbox.daynight import DayClock
from civsandbox.decisions import RuleBasedDecisionProvider
from civsandbox.resources import Resources
from civsandbox.simulation import Simulation, FixedTicker
from civsandbox.survival import SurvivalRules
from civsandbox.world import World, Tile


class FixedAction:
    def __init__(self, action):
        self.action = action

    def decide(self, *args):
        return self.action


def near_bush():
    sim = Simulation(decision_provider=FixedAction(Action(ActionType.WAIT)))
    actor = sim.agents[0]
    bush = next(iter(sim.resources.bushes.values()))
    actor.position = sim.world.neighbors(bush.position)[0]
    return sim, actor, bush


def test_bush_identity_progress_idempotence_and_skipped_ticks():
    sim, actor, bush = near_bush()
    other = Simulation(sim.seed)
    assert [(b.id, b.position) for b in sim.resources.bushes.values()] == [
        (b.id, b.position) for b in other.resources.bushes.values()]
    assert len({b.id for b in sim.resources.bushes.values()}) == len(sim.resources.bushes)
    for _ in range(bush.capacity):
        assert sim.resources.collect(bush.position, 0, actor.id)
    assert not sim.resources.collect(bush.position, 0, actor.id)
    sim.resources.replenish(19)
    assert (bush.quantity, bush.regeneration_progress, bush.ticks_until_regeneration) == (0, 19, 1)
    sim.resources.replenish(20)
    assert bush.quantity == 1 and bush.regeneration_progress == 0
    count = len(sim.resources.changes)
    sim.resources.replenish(20)
    assert len(sim.resources.changes) == count
    sim.resources.replenish(200)
    assert bush.quantity == bush.capacity and bush.ticks_until_regeneration is None
    assert all(change.after <= bush.capacity for change in sim.resources.changes)


def test_each_bush_has_its_own_growth_interval():
    world = World(((Tile.BUSH, Tile.GRASS, Tile.BUSH),))
    resources = Resources(world, capacity=1)
    a, b = resources.bushes.values()
    b.regeneration_interval = 40
    resources.collect(a.position, 0, 'a')
    resources.collect(b.position, 0, 'b')
    resources.replenish(20)
    assert a.quantity == 1 and b.quantity == 0 and b.regeneration_progress == 20
    resources.replenish(40)
    assert b.quantity == 1


def test_gather_commits_one_food_event_only_after_time_and_respects_capacity():
    sim, actor, bush = near_bush()
    sim.decision_provider = FixedAction(Action(ActionType.GATHER, bush.position))
    actor.food = 4
    stock = bush.quantity
    sim.step()
    finish = sim.progress.jobs[actor.id].finish_tick
    while sim.tick < finish-1:
        sim.step()
    assert actor.food == 4 and bush.quantity == stock
    assert not [e for e in sim.events if e['action'] == 'GATHER' and e.get('actor_id') == actor.id]
    sim.step()
    events = [e for e in sim.events if e['action'] == 'GATHER' and e.get('actor_id') == actor.id]
    assert len(events) == 1 and events[0]['executed']
    assert (actor.food, bush.quantity) == (5, stock-1)
    assert not validate(Action(ActionType.GATHER, bush.position), actor, sim.world, sim.resources, sim.social)


def test_competing_timed_gathers_cannot_duplicate_last_berry():
    sim, a, bush = near_bush()
    b = sim.agents[1]
    b.position = a.position
    for _ in range(bush.capacity-1):
        sim.resources.collect(bush.position, 0, 'setup')
    # Test the shared scheduler with the same resource state at acceptance.
    action = Action(ActionType.GATHER, bush.position)
    assert sim.progress.execute(action, a, sim.world, sim.resources, 1, 'rule-based')
    assert sim.progress.execute(action, b, sim.world, sim.resources, 1, 'rule-based')
    finish = sim.progress.jobs[a.id].finish_tick
    assert sim.progress.execute(action, a, sim.world, sim.resources, finish, 'rule-based')
    assert not sim.progress.execute(action, b, sim.world, sim.resources, finish, 'rule-based')
    assert a.food+b.food+bush.quantity == 1
    assert not sim.progress.locks


def test_rest_is_timed_and_eating_uses_authoritative_inventory():
    sim = Simulation(decision_provider=FixedAction(Action(ActionType.REST)))
    a = sim.agents[0]
    a.energy = 25
    sim.step()
    assert a.energy == 25
    for _ in range(sim.progress.timing.rest_ticks-1):
        sim.step()
    assert a.energy == 25
    sim.step()
    assert a.energy == 33  # resting is not charged a simultaneous passive drain
    a.food, a.hunger = 1, 60
    sim.decision_provider = FixedAction(Action(ActionType.EAT))
    sim.step()
    assert a.inventory.quantity('berries') == 1
    finish = sim.progress.jobs[a.id].finish_tick
    while sim.tick < finish-1:
        sim.step()
    before = a.hunger
    sim.step()
    passive = int((sim.tick-1) % sim.progress.timing.needs_interval_ticks == 0)
    assert a.food == a.inventory.quantity('berries') == 0
    assert a.hunger == max(0, before+passive-35)


@pytest.mark.parametrize('hour,period', [(6,'morning'), (12,'afternoon'), (18,'evening'), (20,'night'), (0,'night')])
def test_calendar_periods_and_next_day(hour, period):
    clock = DayClock(2400, 0)
    now = clock.at(hour*100)
    assert (now.hour, now.period, now.day) == (hour, period, 1)
    assert clock.at(2400).day == 2
    assert clock.at(2400).hour == 0


def test_night_routine_is_personality_sensitive_and_urgent_food_overrides():
    sim, a, bush = near_bush()
    rule = RuleBasedDecisionProvider()
    rule.bind_social(sim.social)
    rule.bind_routines(DayClock(start_hour=21), sim.survival)
    rule.begin_tick(0, sim.agents)
    a.food, a.hunger, a.energy = 1, 10, 80
    a.personality['early_bird'] = 1
    assert rule.decide(a, sim.world, sim.resources, random.Random(1)).kind in (ActionType.REST, ActionType.MOVE_TO)
    assert rule.plans[a.id].goal == "REST" and rule.plans[a.id].steps[-1].kind == ActionType.REST
    a.personality['early_bird'] = 0
    assert not rule.prefers_rest(a)
    a.personality['early_bird'] = 1
    a.food, a.hunger = 0, 60
    assert rule.decide(a, sim.world, sim.resources, random.Random(1)).kind == ActionType.GATHER
    a.food = 1
    assert rule.decide(a, sim.world, sim.resources, random.Random(1)).kind == ActionType.EAT


def test_daylight_builds_food_reserve_evening_does_not_force_it():
    sim, a, bush = near_bush()
    a.food, a.hunger, a.energy = 1, 10, 90
    rule = RuleBasedDecisionProvider()
    rule.bind_routines(DayClock(start_hour=12), sim.survival)
    assert rule.decide(a, sim.world, sim.resources, random.Random(0)).kind == ActionType.GATHER
    rule.bind_routines(DayClock(start_hour=18), sim.survival)
    assert rule.decide(a, sim.world, sim.resources, random.Random(0)).kind != ActionType.GATHER


def test_high_hunger_slows_work_and_travel_without_changing_food_effects():
    sim, a, bush = near_bush()
    action = Action(ActionType.GATHER, bush.position)
    a.hunger = 40
    normal = sim.progress.duration_for(action, a)
    a.hunger = 85
    assert sim.progress.duration_for(action, a) == normal*2
    a.hunger = 90
    a.position = (2, 2)
    sim.decision_provider = FixedAction(Action(ActionType.MOVE_TO, (4, 2)))
    sim.step()
    assert a.position == (2, 2)
    sim.step()
    assert a.position == (3, 2)
    a.food = 1
    assert execute(Action(ActionType.EAT), a, sim.world, sim.resources, sim.tick, sim.social)
    assert a.hunger == 56


@pytest.mark.parametrize('hunger,energy', [(100,80), (30,0)])
def test_incapacitation_recovers_without_food_creation_or_death(hunger, energy):
    sim = Simulation()
    a = sim.agents[0]
    a.hunger, a.energy = hunger, energy
    a.food = 1
    sim.step()
    assert a.incapacitated_until and a.current_action == 'REST'
    assert not validate(Action(ActionType.EAT), a, sim.world, sim.resources, sim.social)
    before = sim.snapshot()
    sim.paused = True
    for _ in range(20):
        sim.step()
    assert sim.snapshot() == before
    sim.paused = False
    while sim.tick < 1+sim.survival.recovery_ticks:
        sim.step()
    assert not a.incapacitated_until and a.energy > 0
    assert a.recovery_grace_until > sim.tick
    assert sum(e['action']=='SURVIVAL' and e['actor_id']==a.id and e['result']=='recovered' for e in sim.events) == 1
    for _ in range(20):
        sim.step()
    assert len(sim.agents) == 4
    if hunger == 100:
        assert a.hunger < 100 and a.food == 0  # resumes real eating


def test_starvation_can_seek_food_during_grace_instead_of_collapse_loop():
    sim, a, bush = near_bush()
    sim.decision_provider = RuleBasedDecisionProvider()
    sim.decision_provider.bind_social(sim.social)
    a.hunger = 100
    for _ in range(80):
        sim.step()
    assert a.hunger < 100
    assert any(e['action']=='GATHER' and e.get('actor_id')==a.id for e in sim.events)
    assert sum(e['action']=='SURVIVAL' and e.get('actor_id')==a.id and e['result']=='incapacitated' for e in sim.events) == 1


def test_collapse_cancels_social_reservations_without_food_transfer():
    sim = Simulation(scenario='food_shortage', decision_provider=FixedAction(Action(ActionType.WAIT)))
    a, b = sim.agents[:2]
    assert execute(Action(ActionType.REQUEST_FOOD, b.id), a, sim.world, sim.resources, 0, sim.social)
    request = next(iter(sim.social.pending.values()))
    share = Action(ActionType.SHARE_FOOD, a.id, request_id=request.id)
    assert sim.progress.execute(share, b, sim.world, sim.resources, 0, 'rule-based')
    total = a.food+b.food
    a.energy = 0
    trust_before = [agent.trust.copy() for agent in (a,b)]
    memories_before = [len(agent.memories) for agent in (a,b)]
    sim.step()
    assert [agent.trust for agent in (a,b)] == trust_before
    assert [len(agent.memories) for agent in (a,b)] == [count+1 for count in memories_before]
    assert not sim.social.pending and b.id not in sim.progress.jobs
    assert a.food+b.food == total
    assert not validate(share, b, sim.world, sim.resources, sim.social)
    assert sum(e.get('result')=='cancelled: incapacitated' for e in sim.events) == 1


def test_speed_and_pause_advance_same_clock_resource_and_jobs():
    a, b = Simulation(42), Simulation(42)
    ticker = FixedTicker()
    ticker.speed = 4
    ticker.advance(a, 2)
    for _ in range(32):
        b.step()
    assert a.snapshot() == b.snapshot()
    a.paused = True
    before = a.snapshot()
    ticker.advance(a, 100)
    assert a.snapshot() == before


def test_configures_clock_survival_and_rest(tmp_path, monkeypatch):
    values = {'DAY_LENGTH_SECONDS':'120', 'DAY_START_HOUR':'19', 'REST_SECONDS':'2',
              'HUNGER_SLOW_THRESHOLD':'80', 'STARVATION_THRESHOLD':'99',
              'RECOVERY_SECONDS':'4', 'RECOVERY_GRACE_SECONDS':'40'}
    for name in values:
        monkeypatch.delenv(name, raising=False)
    path = tmp_path/'.env'
    path.write_text('\n'.join(f'{key}={value}' for key,value in values.items()))
    settings = Settings.load(path)
    assert settings.day_clock == DayClock(480,19)
    assert settings.action_timing.rest_ticks == 8
    assert settings.survival.inefficient_hunger == 80
    assert settings.survival.recovery_ticks == 16 and settings.survival.grace_ticks == 160
    for values in ({'recovery_ticks':0}, {'starvation':85}, {'rest_energy':0}, {'hunger_slowdown':0}):
        with pytest.raises(ValueError):
            SurvivalRules(**values)
    with pytest.raises(ValueError):
        DayClock(0)


def test_night_and_resource_inspector_use_live_state_and_cached_lighting():
    import pygame
    from civsandbox.rendering import Renderer
    sim, a, bush = near_bush()
    sim.clock = DayClock(start_hour=22)
    try:
        renderer = Renderer()
        renderer.selected_id = a.id
        renderer.draw(sim, FixedTicker())
        assert sim.time_of_day.darkness in renderer.lighting_cache
        cached = dict(renderer.lighting_cache)
        sim.resources.collect(bush.position, sim.tick, a.id)
        renderer.selected_id, renderer.selected_bush = None, bush.position
        renderer.draw(sim, FixedTicker())
        assert renderer.lighting_cache == cached
        assert sim.resources.available(bush.position) == bush.quantity
        a.hunger, a.energy = 100, 0
        sim.step()
        renderer.selected_id, renderer.selected_bush = a.id, None
        renderer.draw(sim, FixedTicker())
        from civsandbox.ui_state import activity
        assert activity(a, sim) == 'Recovering (temporary)'
    finally:
        sim.close()
        pygame.quit()


def test_configured_hunger_threshold_matches_observation_and_policy():
    from civsandbox.perception import observe
    sim = Simulation(scenario='food_shortage', survival=SurvivalRules(hungry=45))
    a, b = sim.agents[:2]
    a.hunger = 50
    context, *_ = observe(b, sim.world, sim.resources, sim.agents, social=sim.social)
    assert next(p for p in context['nearby_npcs'] if p['id']==a.id)['looks_hungry']
    # A zero RNG roll permits an eligible request; it cannot create a share.
    class AskRng:
        def random(self): return 0
        def choice(self, choices): return choices[0]
    action = sim.decision_provider.decide(a, sim.world, sim.resources, AskRng())
    assert action.kind == ActionType.REQUEST_FOOD
    assert a.food == 0 and b.food == 5
