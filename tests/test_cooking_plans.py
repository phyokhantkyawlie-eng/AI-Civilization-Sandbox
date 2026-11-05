"""Cooking conservation and goal-planner integration without external services."""
from collections import Counter
import random
import pytest

from civsandbox.actions import Action,ActionType,execute,validate
from civsandbox.cooking import CookingStation
from civsandbox.decisions import RuleBasedDecisionProvider
from civsandbox.inventory import ITEM_DEFINITIONS
from civsandbox.simulation import Simulation,FixedTicker
from civsandbox.wildlife import WildlifeSettings
from civsandbox.world import World,Tile


class FixedAction:
    def __init__(self,action):self.action=action
    def decide(self,actor,*args):return self.action if actor.id=='npc-1' else Action(ActionType.WAIT)


def station_fixture():
    sim=Simulation(7,wildlife_settings=WildlifeSettings(starting_population=0))
    actor=sim.agents[0]
    station=sim.cooking_station
    actor.position=sim.world.neighbors(station.position)[0]
    actor.inventory.add('raw_chicken')
    action=Action(ActionType.COOK,station.id)
    sim.decision_provider=FixedAction(action)
    return sim,actor,station,action


def test_station_is_shared_reachable_and_conversion_is_timed_atomic():
    sim,a,station,action=station_fixture()
    assert sim.resources.cooking_station is station
    assert not sim.world.walkable(station.position)
    assert sim.world.path(a.position, sim.world.neighbors(station.position)[0]) or a.position in sim.world.neighbors(station.position)
    assert validate(action,a,sim.world,sim.resources,sim.social)
    assert not execute(action,a,sim.world,sim.resources,0,sim.social)
    a.food=4  # one-for-one conversion also works at full capacity
    sim.step();finish=sim.progress.jobs[a.id].finish_tick
    assert station.occupied_by==a.id and station.ready_tick==finish
    while sim.tick<finish-1:sim.step()
    assert a.inventory.quantity('raw_chicken')==1 and a.inventory.quantity('cooked_chicken')==0
    sim.step()
    assert a.inventory.quantity('raw_chicken')==0 and a.inventory.quantity('cooked_chicken')==1
    assert a.inventory.used==5 and station.occupied_by is None
    assert len([e for e in sim.events if e['action']=='COOK' and e.get('executed')])==1
    assert not execute(action,a,sim.world,sim.resources,sim.tick,sim.social)


@pytest.mark.parametrize('reason',['cancel','move','ingredient','incapacitation'])
def test_cooking_cancellation_or_invalid_finish_does_not_generate_food(reason):
    sim,a,station,action=station_fixture()
    sim.step()
    if reason=='cancel':
        sim.progress.cancel_for(a.id)
        sim.decision_provider=FixedAction(Action(ActionType.WAIT))
    elif reason=='move':a.position=(0,0)
    elif reason=='ingredient':a.inventory.remove('raw_chicken')
    else:
        a.energy=0
        sim.step()
        sim.decision_provider=FixedAction(Action(ActionType.WAIT))
    for _ in range(22):sim.step()
    assert a.inventory.quantity('cooked_chicken')==0
    assert station.occupied_by is None
    if reason!='ingredient':assert a.inventory.quantity('raw_chicken')==1


def test_station_exclusive_occupancy_releases_for_next_cook():
    sim,a,station,action=station_fixture()
    b=sim.agents[1];b.position=a.position;b.inventory.add('raw_chicken')
    sim.step()
    assert not validate(action,b,sim.world,sim.resources,sim.social)
    assert not sim.progress.execute(action,b,sim.world,sim.resources,sim.tick,'rule-based')
    while a.id in sim.progress.jobs:sim.step()
    assert validate(action,b,sim.world,sim.resources,sim.social)
    assert sim.progress.execute(action,b,sim.world,sim.resources,sim.tick,'rule-based')
    assert station.occupied_by==b.id and b.inventory.quantity('raw_chicken')==1
    sim.close()
    assert station.occupied_by is None and b.inventory.quantity('raw_chicken')==1


@pytest.mark.parametrize('item', ['berries','cooked_chicken'])
def test_meals_consume_one_named_item_and_catalog_nutrition(item):
    sim,a,_,_=station_fixture()
    a.inventory.add(item,2);a.hunger=90
    before=a.inventory.items.copy()
    assert execute(Action(ActionType.EAT,item=item),a,sim.world,sim.resources,0,sim.social)
    assert a.inventory.quantity(item)==before[item]-1
    assert a.hunger==90-ITEM_DEFINITIONS[item].hunger_reduction
    assert a.inventory.quantity('raw_chicken')==1
    assert not execute(Action(ActionType.EAT,item='raw_chicken'),a,sim.world,sim.resources,0,sim.social)
    assert ITEM_DEFINITIONS['cooked_chicken'].hunger_reduction>ITEM_DEFINITIONS['berries'].hunger_reduction


@pytest.mark.parametrize('bad', [None,'missing',(2,2),[],True])
def test_invalid_station_targets_are_noops(bad):
    sim,a,station,_=station_fixture()
    before=a.inventory.items.copy()
    assert not execute(Action(ActionType.COOK,bad),a,sim.world,sim.resources,0,sim.social)
    assert a.inventory.items==before and station.occupied_by is None


def test_pause_and_speed_preserve_cooking_lease_and_completion():
    sim,a,station,action=station_fixture()
    sim.step();ticker=FixedTicker();ticker.speed=4
    sim.paused=True;before=sim.snapshot();ticker.advance(sim,100)
    assert sim.snapshot()==before
    sim.paused=False;ticker.advance(sim,5)
    assert a.inventory.quantity('cooked_chicken')==1 and station.occupied_by is None


def test_owned_raw_meat_plans_travel_cook_eat_without_free_actions():
    sim,a,station,_=station_fixture()
    sim.decision_provider=RuleBasedDecisionProvider()
    sim.decision_provider.bind_social(sim.social)
    a.position=(8,7);a.hunger=75;a.energy=90
    for other in sim.agents[1:]:other.food=0
    # Remove competing berries from the controlled opportunity, not from normal scenarios.
    for bush in sim.resources.bushes.values():bush.quantity=0
    sim.resources.replenish_interval=10000
    for bush in sim.resources.bushes.values():bush.regeneration_interval=10000
    selected=[]
    for _ in range(160):
        sim.step()
        if a.id in sim.decision_provider.plans:
            selected.append(sim.decision_provider.plans[a.id].goal)
        if any(e['action']=='EAT' and e.get('item')=='cooked_chicken' and e.get('actor_id')==a.id and e.get('executed') for e in sim.events):break
    assert 'COOK_FOOD' in selected
    actual=[e['action'] for e in sim.events if e.get('actor_id')==a.id and e.get('executed')]
    assert actual.index('COOK')<actual.index('EAT')
    assert a.inventory.quantity('raw_chicken')==a.inventory.quantity('cooked_chicken')==0
    assert a.hunger<75


def test_food_goal_retains_queue_instead_of_reselecting_each_tick():
    sim=Simulation(42)
    a=sim.agents[0]
    rule=sim.decision_provider
    sim.step();plan=rule.plans[a.id]
    for _ in range(5):
        sim.step()
        assert rule.plans[a.id] is plan
    assert len(plan.steps)<=6
    assert a.id in rule.debug and rule.debug[a.id]['utilities']


def test_missing_resource_invalidates_plan_and_bounded_retry_does_not_loop():
    sim=Simulation(42,wildlife_settings=WildlifeSettings(starting_population=0))
    a=sim.agents[0];rule=sim.decision_provider
    sim.step();target=rule.plans[a.id].target
    for bush in sim.resources.bushes.values():bush.quantity=0;bush.regeneration_interval=10000
    for _ in range(100):sim.step()
    assert rule.stats['failed']>=1
    assert rule.stats['failed']<20
    assert all(len(p.steps)<=6 for p in rule.plans.values())
    assert all(p.deadline-p.created<=320 for p in rule.plans.values())


def test_emergency_eating_preempts_optional_social_and_rest_over_exploration():
    sim=Simulation(scenario='food_shortage')
    a,b=sim.agents[:2];a.food=1;a.hunger=90;a.energy=0;b.food=0
    assert execute(Action(ActionType.REQUEST_FOOD,a.id),b,sim.world,sim.resources,0,sim.social)
    # At this location they may not be adjacent; move into the valid conversation first.
    rule=sim.decision_provider
    assert rule.decide(a,sim.world,sim.resources,sim.rng).kind==ActionType.EAT
    a.food=0
    assert rule.decide(a,sim.world,sim.resources,sim.rng).kind==ActionType.REST


def test_personality_changes_components_without_exemptions():
    sim=Simulation(7)
    a=sim.agents[0];a.hunger=60
    rule=sim.decision_provider
    a.personality['nature_affinity']=0
    low=next(c for c in rule.candidates(a,sim.world,sim.resources) if c.goal=='GATHER_FOOD')
    a.personality['nature_affinity']=1
    high=next(c for c in rule.candidates(a,sim.world,sim.resources) if c.goal=='GATHER_FOOD')
    assert high.utility>low.utility
    assert high.components['nature']>low.components['nature']
    a.energy=0
    for actor in sim.agents:
        actor.energy=0;actor.food=0
        assert rule.decide(actor,sim.world,sim.resources,random.Random(0)).kind==ActionType.REST


def test_memory_off_utility_does_not_depend_on_accumulated_social_history():
    sim=Simulation(7,scenario='food_shortage',memory_enabled=False)
    a=sim.agents[0];rule=sim.decision_provider
    before=[(c.goal,c.target,c.utility) for c in rule.candidates(a,sim.world,sim.resources)]
    sim.social.record('npc-2','npc-1','REFUSE_REQUEST','refused',{'npc-1':-80})
    after=[(c.goal,c.target,c.utility) for c in rule.candidates(a,sim.world,sim.resources)]
    assert before==after


def test_cooking_observation_cannot_mutate_world_and_schema_handles_items():
    from civsandbox.ai import parse_decision
    from civsandbox.perception import observe
    sim,a,station,action=station_fixture()
    sim.step();sim.resources.tick=station.ready_tick
    context,choices,world,resources=observe(a,sim.world,sim.resources,sim.agents,social=sim.social)
    assert context['cooking_station']['id']==station.id
    assert not execute(action,a,world,resources,station.ready_tick,sim.social)
    assert a.inventory.quantity('raw_chicken')==1
    assert parse_decision('{"action":"COOK","target":"campfire-1","reasoning":"Prepare owned meat"}').kind==ActionType.COOK
    assert parse_decision('{"action":"EAT","target":null,"item":"cooked_chicken","reasoning":"Eat a cooked meal"}').item=='cooked_chicken'


def test_complete_chicken_meal_plan_hunts_travels_cooks_and_eats():
    sim=Simulation(7)
    a=sim.agents[0];station=sim.cooking_station
    a.position=sim.world.neighbors(station.position)[0]
    a.hunger,a.energy=75,95
    chicken=sim.wildlife.living()[0]
    chicken.position=next(p for p in sim.world.neighbors(a.position) if p!=station.position)
    chicken.calm_until=chicken.next_move_tick=10000
    for other in sim.agents[1:]:other.food=0
    for bush in sim.resources.bushes.values():bush.quantity=0;bush.regeneration_interval=10000
    first=sim.decision_provider.decide(a,sim.world,sim.resources,sim.rng)
    assert first.kind==ActionType.HUNT
    plan=sim.decision_provider.plans[a.id]
    assert [s.kind for s in plan.steps]==[ActionType.HUNT,ActionType.MOVE_TO,ActionType.COOK,ActionType.EAT]
    for _ in range(120):
        sim.step()
        if any(e['action']=='EAT' and e.get('actor_id')==a.id and e.get('item')=='cooked_chicken' and e.get('executed') for e in sim.events):break
    meals=[e['action'] for e in sim.events if e.get('actor_id')==a.id and e.get('executed')]
    assert meals.index('HUNT')<meals.index('COOK')<meals.index('EAT')
    assert a.hunger<75 and not chicken.alive
    assert not a.inventory.quantity('raw_chicken') and not a.inventory.quantity('cooked_chicken')


def test_busy_station_wait_preserves_plan_then_cooks_after_release():
    sim,a,station,_=station_fixture()
    sim.decision_provider=RuleBasedDecisionProvider();sim.decision_provider.bind_social(sim.social)
    a.hunger,a.energy=75,90
    for other in sim.agents[1:]:other.food=0
    for bush in sim.resources.bushes.values():bush.quantity=0
    station.occupied_by='npc-2';station.ready_tick=10
    action=sim.decision_provider.decide(a,sim.world,sim.resources,sim.rng)
    assert action.kind==ActionType.WAIT
    plan=sim.decision_provider.plans[a.id]
    station.release('npc-2')
    assert sim.decision_provider.decide(a,sim.world,sim.resources,sim.rng).kind==ActionType.COOK
    assert sim.decision_provider.plans[a.id] is plan


def test_debug_plan_panel_and_idle_cooking_fallback():
    import pygame
    from civsandbox.rendering import Renderer,handle_event
    from civsandbox.feedback import Feedback
    sim,a,station,_=station_fixture()
    sim.decision_provider=RuleBasedDecisionProvider();sim.decision_provider.bind_social(sim.social)
    a.hunger=75
    sim.step()
    try:
        renderer=Renderer();renderer.selected_id=a.id
        handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_F3),sim,FixedTicker(),renderer)
        handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_p),sim,FixedTicker(),renderer)
        renderer.draw(sim,FixedTicker())
        assert renderer.debug and renderer.plan_debug
        assert Feedback.sprite_state('cook')=='idle'
        assert station.occupied_by==a.id
        assert sim.decision_provider.debug[a.id]['utilities']
    finally:sim.close();pygame.quit()


@pytest.mark.parametrize('index',range(4))
def test_every_personality_can_prepare_and_eat_owned_meat(index):
    sim=Simulation(21,wildlife_settings=WildlifeSettings(starting_population=0))
    actor=sim.agents[index]
    actor.position=sim.world.neighbors(sim.cooking_station.position)[0]
    actor.inventory.add('raw_chicken');actor.hunger=75;actor.energy=90
    for other in sim.agents:
        if other is not actor:other.food=0
    for bush in sim.resources.bushes.values():bush.quantity=0;bush.regeneration_interval=10000
    for _ in range(100):
        sim.step()
        if any(e['action']=='EAT' and e.get('actor_id')==actor.id and e.get('item')=='cooked_chicken' and e.get('executed') for e in sim.events):break
    assert actor.inventory.quantity('raw_chicken')==actor.inventory.quantity('cooked_chicken')==0
    assert actor.hunger<75


def test_cautious_agent_can_choose_a_real_social_opportunity():
    from civsandbox.daynight import DayClock
    sim=Simulation(42,scenario='food_shortage')
    actor=sim.agents[2]
    actor.food=2;actor.hunger=10;actor.energy=90
    sim.decision_provider.bind_routines(DayClock(start_hour=12),sim.survival)
    action=sim.decision_provider.decide(actor,sim.world,sim.resources,sim.rng)
    assert action.kind==ActionType.TALK
    assert validate(action,actor,sim.world,sim.resources,sim.social)


def test_an_emergency_meal_is_not_suppressed_by_a_failed_plan_retry_timer():
    sim=Simulation(7)
    actor=sim.agents[0];actor.food=1;actor.hunger=90
    rule=sim.decision_provider
    action=rule.decide(actor,sim.world,sim.resources,sim.rng)
    assert action.kind==ActionType.EAT
    rule.on_action_result(actor,action,False,True,sim.tick)
    assert rule.decide(actor,sim.world,sim.resources,sim.rng).kind==ActionType.EAT


def test_request_plan_identity_matches_the_actual_selected_recipient():
    sim=Simulation(42,scenario='food_shortage')
    a=sim.agents[0];a.hunger=78
    action=sim.decision_provider.decide(a,sim.world,sim.resources,sim.rng)
    if action.kind==ActionType.REQUEST_FOOD:
        assert sim.decision_provider.plans[a.id].target==action.target
        assert a.goal.target==action.target
    else:
        # Seeded willingness may decline; a real request must never be invented.
        assert action.kind in (ActionType.MOVE_TO,ActionType.GATHER,ActionType.HUNT)


def test_another_raw_item_cannot_bypass_the_next_cooking_timer():
    sim, actor, station, action = station_fixture()
    actor.inventory.add('raw_chicken')
    sim.step()
    finish = sim.progress.jobs[actor.id].finish_tick
    while sim.tick < finish:
        sim.step()
    assert actor.inventory.quantity('raw_chicken') == 1
    assert actor.inventory.quantity('cooked_chicken') == 1
    assert not execute(action, actor, sim.world, sim.resources, sim.tick, sim.social)
    assert station.occupied_by is None
    assert actor.inventory.quantity('raw_chicken') == actor.inventory.quantity('cooked_chicken') == 1


@pytest.mark.parametrize('scenario', ['default', 'food_shortage'])
def test_campfire_preserves_access_to_all_other_reachable_tiles(scenario):
    from civsandbox.world import generate_world, shortage_world
    original = generate_world(random.Random(21))
    if scenario == 'food_shortage':
        original = shortage_world(original)
    sim = Simulation(21, scenario=scenario)
    home = sim.agents[0].position
    reachable = set(sim.world.reachable(home))
    assert reachable == set(original.reachable(home)) - {sim.cooking_station.position}
    assert all(actor.position in reachable for actor in sim.agents)
    assert sim.world.tiles[sim.cooking_station.position[1]][sim.cooking_station.position[0]] == Tile.CAMPFIRE
