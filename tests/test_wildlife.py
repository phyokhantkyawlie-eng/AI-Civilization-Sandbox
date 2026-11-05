"""Shared-world wildlife, conditional policy, and atomic hunting contracts."""
from dataclasses import replace
import json
import random

import pytest

from civsandbox.actions import Action, ActionType, execute, validate
from civsandbox.agents import Agent
from civsandbox.config import Settings
from civsandbox.decisions import RuleBasedDecisionProvider
from civsandbox.simulation import Simulation, FixedTicker
from civsandbox.wildlife import Wildlife, WildlifeSettings, ChickenState, distance
from civsandbox.world import World, Tile


class ControlledProvider:
    def __init__(self, action):
        self.action = action

    def decide(self, actor, *args):
        return self.action if actor.id == 'npc-1' else Action(ActionType.WAIT)


def hunt_fixture(**overrides):
    settings = replace(WildlifeSettings(starting_population=1, maximum_population=1,
                                       catch_ticks=4, chase_ticks=24, cooldown_ticks=16,
                                       respawn_ticks=20), **overrides)
    sim = Simulation(42, wildlife_settings=settings)
    actor = sim.agents[0]
    actor.position, actor.hunger = (3,2), 75
    chicken = sim.wildlife.living()[0]
    chicken.position = (4,2)
    # A controlled resting target verifies timing/atomicity, not a production outcome.
    chicken.calm_until = chicken.next_move_tick = 10000
    action = Action(ActionType.HUNT, chicken.id)
    sim.decision_provider = ControlledProvider(action)
    return sim, actor, chicken, action


def completed_hunts(sim):
    return [e for e in sim.events if e['action']=='HUNT' and e.get('executed')]


def test_default_population_unique_free_reachable_spawns():
    for seed in (7,21,42):
        sim = Simulation(seed)
        chickens = sim.wildlife.living()
        assert len(chickens) == 2
        assert len({c.id for c in chickens}) == len({c.position for c in chickens}) == 2
        occupied = {a.position for a in sim.agents}
        reachable = set(sim.world.reachable(sim.agents[0].position))
        assert all(c.position not in occupied and c.position in reachable for c in chickens)
        while sim.wildlife.spawn(sim.world, sim.agents):
            pass
        assert len(sim.wildlife.living()) == sim.wildlife.settings.maximum_population


def test_blocked_or_occupied_map_never_spawns_illegally():
    world = World(((Tile.WATER,Tile.GRASS,Tile.TREE),))
    actor = Agent('a','Ada',(1,0),(1,2,3))
    flock = Wildlife(world,[actor])
    assert not flock.living() and len(flock.respawns)==2
    flock.advance(1000,world,[actor])
    assert not flock.living() and len(flock.respawns)==2


def test_wildlife_moves_once_per_step_inside_terrain_and_avoids_occupants():
    sim = Simulation(21)
    previous = {c.id:c.position for c in sim.wildlife.living()}
    activities = set()
    states = set()
    for tick in range(1,500):
        sim.wildlife.advance(tick,sim.world,sim.agents)
        positions=[]
        for c in sim.wildlife.living():
            assert sim.world.walkable(c.position)
            assert distance(previous[c.id],c.position)<=1
            assert c.position not in {a.position for a in sim.agents}
            previous[c.id]=c.position
            positions.append(c.position)
            activities.add(c.activity);states.add(c.state)
        assert len(set(positions))==len(positions)
    assert {'pecking','walking','resting'} <= activities
    assert {ChickenState.IDLE,ChickenState.WANDER} <= states


def test_nearby_active_agent_triggers_flee_then_bounded_calm():
    world = World(tuple((Tile.GRASS,)*7 for _ in range(5)))
    actor = Agent('a','Ada',(2,2),(1,2,3))
    flock = Wildlife(world,[actor],settings=WildlifeSettings(starting_population=1))
    c=flock.living()[0]
    c.position,c.next_move_tick=(3,2),0
    flock.advance(1,world,[actor])
    assert c.state == ChickenState.FLEE and c.activity=='fleeing'
    assert distance(c.position,actor.position)>1 and c.moving
    end=c.fear_until
    flock.advance(end,world,[actor])
    assert c.state==ChickenState.IDLE and c.activity=='resting'
    assert c.calm_until>end


def test_success_is_delayed_exclusive_and_rewards_exactly_once():
    sim,a,c,action=hunt_fixture()
    assert validate(action,a,sim.world,sim.resources,sim.social)
    assert not execute(action,a,sim.world,sim.resources,0,sim.social)
    sim.step()
    assert c.alive and a.inventory.quantity('raw_chicken')==0 and c.claimed_by==a.id
    b=sim.agents[1];b.position=(4,3)
    assert not validate(action,b,sim.world,sim.resources,sim.social)
    assert not sim.progress.execute(action,b,sim.world,sim.resources,sim.tick,'rule-based')
    assert not execute(action,a,sim.world,sim.resources,sim.tick,sim.social)
    sim.step()
    ready=sim.wildlife.pursuits[a.id].catch_ready_tick
    while sim.tick<ready-1:sim.step()
    assert c.alive and not completed_hunts(sim)
    sim.step()
    assert not c.alive and c.claimed_by is None
    assert a.inventory.quantity('raw_chicken')==1 and len(completed_hunts(sim))==1
    assert not execute(action,a,sim.world,sim.resources,sim.tick,sim.social)
    assert sim.wildlife.cooldowns[a.id]>sim.tick
    assert not sim.wildlife.pursuits and not sim.progress.locks


def test_latest_target_proximity_is_required_and_chase_repaths():
    sim,a,c,action=hunt_fixture()
    sim.step();sim.step()
    ready=sim.wildlife.pursuits[a.id].catch_ready_tick
    c.position=(3,4)
    before=a.position
    sim.step()
    assert a.position==(3,3) and distance(before,a.position)==1
    assert sim.wildlife.pursuits[a.id].catch_ready_tick==0
    c.position=(15,2)
    while sim.tick<ready:sim.step()
    assert a.inventory.quantity('raw_chicken')==0 and c.alive


@pytest.mark.parametrize('invalid', [None, '', 'missing', (4,2), ['chicken-1']])
def test_invalid_hunt_targets_are_atomic(invalid):
    sim,a,c,_=hunt_fixture()
    before=(a.energy,a.inventory.items.copy(),c.alive,c.claimed_by)
    assert not execute(Action(ActionType.HUNT,invalid),a,sim.world,sim.resources,1,sim.social)
    assert before==(a.energy,a.inventory.items,c.alive,c.claimed_by)


@pytest.mark.parametrize('failure', ['energy','capacity','incapacitated','dead'])
def test_failed_eligibility_or_completion_creates_no_meat(failure):
    sim,a,c,action=hunt_fixture()
    sim.step()
    if failure=='energy':a.energy=19
    elif failure=='capacity':a.food=5
    elif failure=='incapacitated':a.energy=0
    else:c.alive=False
    sim.step()
    assert a.inventory.quantity('raw_chicken')==0 and not completed_hunts(sim)
    assert c.claimed_by is None and not sim.wildlife.pursuits
    assert len([e for e in sim.events if e['action']=='HUNT_FAILED'])==1
    for _ in range(4):sim.step()
    assert len([e for e in sim.events if e['action']=='HUNT_FAILED'])==1


@pytest.mark.parametrize('mode', ['timeout','distance'])
def test_chases_end_and_release_claims_with_cooldown(mode):
    overrides={'chase_ticks':6,'catch_ticks':2} if mode=='timeout' else {'chase_steps':2}
    sim,a,c,action=hunt_fixture(**overrides)
    c.position=(20,16)
    for _ in range(12):sim.step()
    assert not sim.wildlife.pursuits and c.claimed_by is None and c.alive
    assert a.inventory.quantity('raw_chicken')==0
    failures=[e for e in sim.events if e['action']=='HUNT_FAILED']
    assert len(failures)==1
    assert ('timed out' if mode=='timeout' else 'distance limit') in failures[0]['result']
    assert not validate(action,a,sim.world,sim.resources,sim.social)


def test_respawns_are_delayed_deterministic_and_have_new_identity():
    a,actor,c,_=hunt_fixture()
    b,_,_,_=hunt_fixture()
    for _ in range(6):a.step();b.step()
    assert not c.alive and len(a.wildlife.respawns)==1
    due=a.wildlife.respawns[0]
    while a.tick<due-1:
        a.step();b.step()
        assert not a.wildlife.living()
    a.step();b.step()
    assert a.snapshot()==b.snapshot()
    new=a.wildlife.living()
    assert len(new)==1 and new[0].id!=c.id
    assert new[0].position not in {actor.position for actor in a.agents}
    assert a.world.walkable(new[0].position)
    for _ in range(100):a.step()
    assert len(a.wildlife.living())<=1 and len(a.wildlife.respawns)==0


def test_policy_ignores_well_fed_exhausted_stocked_or_cautious_distant_agents():
    sim,a,c,_=hunt_fixture()
    rule=RuleBasedDecisionProvider()
    # Scarce berries, visible living target: choice still depends on the actor.
    for bush in sim.resources.bushes.values():bush.quantity=0
    a.hunger,a.energy=85,90
    assert rule.hunting_choice(a,sim.world,sim.resources).kind==ActionType.HUNT
    cases=[{'hunger':20},{'energy':10},{'food':2}]
    for changes in cases:
        rule=RuleBasedDecisionProvider();a.hunger,a.energy,a.food=85,90,0
        for name,value in changes.items():setattr(a,name,value)
        assert rule.hunting_choice(a,sim.world,sim.resources) is None
    a.hunger,a.energy,a.food=85,90,0
    a.inventory.add('raw_chicken')
    assert RuleBasedDecisionProvider().hunting_choice(a,sim.world,sim.resources) is None
    a.inventory.remove('raw_chicken')
    a.personality={'risk_aversion':.95,'curiosity':.1}
    c.position=(7,2)
    assert RuleBasedDecisionProvider().hunting_choice(a,sim.world,sim.resources) is None


def test_nearby_berries_do_not_veto_an_eligible_hunt():
    sim,a,c,_=hunt_fixture()
    bush=next(iter(sim.resources.bushes.values()))
    a.position=sim.world.neighbors(bush.position)[0]
    c.position=next(p for p in sim.world.neighbors(a.position) if p!=a.position)
    assert RuleBasedDecisionProvider().hunting_choice(a,sim.world,sim.resources).kind == ActionType.HUNT


def test_spawning_never_triggers_hunting_in_satisfied_population():
    sim=Simulation(7,wildlife_settings=WildlifeSettings(starting_population=0,respawn_ticks=4))
    for actor in sim.agents:
        actor.food=3;actor.hunger=0
    # Repeated world-rule spawn opportunities are deliberately independent of policy.
    for _ in range(4):
        assert sim.wildlife.spawn(sim.world,sim.agents)
        for _ in range(8):sim.step()
    assert not any(e.get('activity_action')=='HUNT' for e in sim.events)
    assert all(c.alive and c.claimed_by is None for c in sim.wildlife.living())


def test_raw_meat_does_not_change_berries_or_become_edible_before_stage3():
    sim,a,c,action=hunt_fixture()
    for _ in range(6):sim.step()
    assert a.food==0 and a.inventory.quantity('raw_chicken')==1
    assert not validate(Action(ActionType.EAT),a,sim.world,sim.resources,sim.social)
    a.food=1
    assert execute(Action(ActionType.EAT),a,sim.world,sim.resources,sim.tick,sim.social)
    assert a.food==0 and a.inventory.quantity('raw_chicken')==1


def test_pause_speed_and_existing_npc_paths_stay_reproducible():
    a,b=Simulation(84),Simulation(84)
    ticker=FixedTicker();ticker.speed=4
    ticker.advance(a,5)
    for _ in range(80):b.step()
    assert a.snapshot()==b.snapshot()
    a.paused=True;before=a.snapshot();ticker.advance(a,100)
    assert a.snapshot()==before
    for _ in range(100):
        b.step()
        assert all(b.world.walkable(actor.position) for actor in b.agents)
        assert all(b.world.walkable(c.position) for c in b.wildlife.living())


def test_local_hunt_choices_and_schema_reject_unseen_or_malformed_targets():
    from civsandbox.ai import parse_decision
    from civsandbox.perception import observe
    sim,a,c,action=hunt_fixture()
    context,choices,_,_=observe(a,sim.world,sim.resources,sim.agents,social=sim.social)
    assert any(choice.kind==ActionType.HUNT for choice in choices)
    raw=json.dumps({'action':'HUNT','target':c.id,'reasoning':'Nearby scarce-food supply.'})
    assert parse_decision(raw).target==c.id
    c.position=(20,16)
    context,choices,_,_=observe(a,sim.world,sim.resources,sim.agents,social=sim.social)
    assert not context['nearby_chickens'] and not any(choice.kind==ActionType.HUNT for choice in choices)
    with pytest.raises(ValueError):
        parse_decision(json.dumps({'action':'HUNT','target':{'x':1,'y':2},'reasoning':'bad target'}))


def test_wildlife_configuration_and_validation(tmp_path,monkeypatch):
    values={'CHICKEN_STARTING_POPULATION':'3','CHICKEN_MAX_POPULATION':'5',
            'CHICKEN_RESPAWN_SECONDS':'30','HUNT_TIMEOUT_SECONDS':'15','HUNT_CATCH_SECONDS':'1'}
    for name in values:monkeypatch.delenv(name,raising=False)
    path=tmp_path/'.env';path.write_text('\n'.join(f'{k}={v}' for k,v in values.items()))
    settings=Settings.load(path).wildlife
    assert settings.starting_population==3 and settings.maximum_population==5
    assert (settings.respawn_ticks,settings.chase_ticks,settings.catch_ticks)==(120,60,4)
    for kwargs in ({'starting_population':5}, {'respawn_ticks':0}, {'catch_ticks':100}, {'minimum_energy':101}):
        with pytest.raises(ValueError):WildlifeSettings(**kwargs)


def test_natural_hunting_opportunity_is_conditional_and_meat_is_conserved():
    sim=Simulation(7,scenario='food_shortage')
    # Controlled scarcity creates an opportunity; the provider still chooses the hunt.
    actor=sim.agents[0]
    chicken=sim.wildlife.living()[0]
    actor.position=(3,2);actor.hunger=75;actor.energy=90
    chicken.position=(4,2)
    for bush in sim.resources.bushes.values():bush.quantity=0
    for other in sim.agents[1:]:other.food=0
    attempts=0;last=0;successes=0;cooked_meals=0
    for _ in range(2400):
        sim.step()
        fresh=[]
        for event in reversed(sim.events):
            if event['event_id']<=last:break
            fresh.append(event)
        last=sim.events[-1]['event_id']
        for event in fresh:
            if event.get('activity_action')=='HUNT' and event.get('accepted_start'):
                attempts+=1
                actor=next(a for a in sim.agents if a.id==event['actor_id'])
                assert actor.hunger>=65 and actor.energy>=40 and actor.food==0
                assert actor.inventory.quantity('raw_chicken')==0
            successes+=int(event['action']=='HUNT' and event.get('executed',False))
            cooked_meals+=int(event['action']=='EAT' and event.get('executed',False) and event.get('item')=='cooked_chicken')
    assert attempts>0
    assert successes==sum(a.inventory.quantity('raw_chicken')+a.inventory.quantity('cooked_chicken') for a in sim.agents)+cooked_meals
    assert all(a.inventory.quantity('raw_chicken')<=1 for a in sim.agents)
    assert sim.ai_summary()['api_calls']==0


def test_rendered_chickens_have_states_and_disappear_on_validated_hunt():
    import pygame
    from civsandbox.rendering import Renderer
    sim,a,c,_=hunt_fixture()
    try:
        r=Renderer()
        r.draw(sim,FixedTicker())
        assert c.id in r.chicken_rects
        c.activity='pecking'
        r.draw(sim,FixedTicker())
        c.state=ChickenState.FLEE
        r.draw(sim,FixedTicker())
        c.state=ChickenState.IDLE
        for _ in range(6):sim.step()
        assert not c.alive
        r.selected_id=a.id
        r.draw(sim,FixedTicker())
        assert c.id not in r.chicken_rects
        assert r.feedback.notices[a.id].label=='Hunted'
    finally:
        sim.close();pygame.quit()


def test_wildlife_clock_is_monotonic_and_same_tick_is_idempotent():
    from dataclasses import asdict
    sim=Simulation(42)
    sim.wildlife.advance(1,sim.world,sim.agents)
    before=[asdict(c) for c in sim.wildlife.living()]
    rng=sim.wildlife.rng.getstate()
    sim.wildlife.advance(1,sim.world,sim.agents)
    assert before==[asdict(c) for c in sim.wildlife.living()]
    assert rng==sim.wildlife.rng.getstate()
    with pytest.raises(ValueError):sim.wildlife.advance(0,sim.world,sim.agents)


def test_observation_view_cannot_execute_final_hunt():
    from civsandbox.perception import observe
    sim,a,c,action=hunt_fixture()
    sim.step();sim.step()
    ready=sim.wildlife.pursuits[a.id].catch_ready_tick
    # Hold a ready final state without asking the real scheduler to complete it.
    sim.wildlife.tick=ready
    _,_,local_world,local_resources=observe(a,sim.world,sim.resources,sim.agents,social=sim.social)
    assert not execute(action,a,local_world,local_resources,ready,sim.social)
    assert c.alive and a.inventory.quantity('raw_chicken')==0
