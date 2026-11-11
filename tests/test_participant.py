"""Human commands use the existing scheduler, physical world and validators."""
import pytest

from civsandbox.actions import Action, ActionType
from civsandbox.simulation import Simulation, FixedTicker
from civsandbox.player import nearby_options


class WaitingAI:
    def __init__(self):
        self.calls = []

    def decide(self, actor, *args):
        self.calls.append(actor.id)
        return Action(ActionType.WAIT)


def controlled():
    ai = WaitingAI()
    sim = Simulation(7, decision_provider=ai)
    sim.set_participant('npc-1')
    return sim, sim.agents[0], ai


def complete(sim, limit=200):
    sim.step()
    for _ in range(limit):
        if not sim.progress.jobs:
            return
        sim.step()
    raise AssertionError('Action did not finish')


@pytest.mark.parametrize('key', ['npc-1','npc-2','npc-3','npc-4'])
def test_selection_reuses_agent_and_leaves_physical_history_intact(key):
    sim = Simulation(42)
    original = list(sim.agents)
    actor = sim.social.agents[key]
    actor.food = 2
    from civsandbox.social import Memory
    peer_id = next(a.id for a in sim.agents if a is not actor)
    actor.trust[peer_id] = 7
    actor.memories.append(Memory(0,peer_id,key,'TALK','greeted',1))
    original_world, original_resources = sim.world, sim.resources
    before = (actor.position,actor.hunger,actor.energy,actor.inventory.items.copy(),actor.trust.copy(),actor.memories[:])
    sim.set_participant(key)
    assert sim.social.agents[key] is actor and sim.agents == original and len(sim.agents)==4
    assert before == (actor.position,actor.hunger,actor.energy,actor.inventory.items,actor.trust,actor.memories)
    sim.set_participant()
    assert sim.player is None and sim.agents == original
    assert sim.world is original_world and sim.resources is original_resources


def test_three_ai_continue_but_never_choose_for_player():
    sim, actor, ai = controlled()
    before = actor.position
    for _ in range(12):
        sim.step()
    assert actor.id not in ai.calls
    assert set(ai.calls) == {a.id for a in sim.agents if a is not actor}
    assert actor.position == before and actor.food==0
    assert actor.hunger > 25 and actor.energy < 90
    assert all(e['decision_source']=='player' for e in sim.events if e.get('actor_id')==actor.id and 'decision_source' in e)


def test_direct_grid_movement_collisions_and_hunger_slowdown():
    sim, actor, _ = controlled()
    actor.position = (0,0)
    sim.player.direction = (-1,0)
    sim.step()
    assert actor.position == (0,0)
    sim.player.direction = (1,0)
    sim.step()
    assert actor.position == (1,0)
    blocked = next(p for y,row in enumerate(sim.world.tiles) for x,tile in enumerate(row)
                   if not sim.world.walkable(p:=(x,y)))
    assert not sim.player.submit(Action(ActionType.MOVE_TO,blocked),sim)
    actor.hunger=90
    before=actor.position
    sim.step()  # odd tick uses the same slow-travel rule
    assert actor.position==before


def test_gather_capacity_timing_eat_and_rest_use_actual_inventory():
    sim, actor, _ = controlled()
    bush = next(iter(sim.resources.bushes.values()))
    actor.position = sim.world.neighbors(bush.position)[0]
    stock=bush.quantity
    assert sim.player.submit(Action(ActionType.GATHER,bush.position),sim)
    sim.step()
    assert actor.food==0 and bush.quantity==stock
    complete(sim)
    assert actor.food==1
    assert len([e for e in sim.events if e['action']=='GATHER' and e.get('executed')])==1
    actor.hunger=65
    assert sim.player.submit(Action(ActionType.EAT,item='berries'),sim)
    complete(sim)
    assert actor.food==0 and actor.hunger<65
    actor.food=actor.inventory.capacity
    assert not sim.player.submit(Action(ActionType.GATHER,bush.position),sim)
    actor.energy=30
    assert sim.player.submit(Action(ActionType.REST),sim)
    for _ in range(12):sim.step()
    assert actor.energy>30


def test_hunt_cook_meal_conserves_food_and_no_duplicate_meat():
    from test_wildlife import hunt_fixture
    sim, actor, chicken, hunt = hunt_fixture()
    sim.set_participant(actor.id)
    assert not sim.player.submit(hunt,sim)  # E/context hunting is replaced by discrete clicks.
    for _ in range(4):
        assert sim.player_attack(chicken.id)
    assert not chicken.alive and actor.inventory.quantity('raw_chicken')==1
    assert not sim.player.submit(hunt,sim)
    assert not sim.player.submit(Action(ActionType.EAT,item='raw_chicken'),sim)
    station=sim.cooking_station
    actor.position=sim.world.neighbors(station.position)[0]
    assert sim.player.submit(Action(ActionType.COOK,station.id),sim)
    sim.step()
    assert actor.inventory.quantity('raw_chicken')==1
    complete(sim)
    assert actor.inventory.quantity('raw_chicken')==0 and actor.inventory.quantity('cooked_chicken')==1
    assert not sim.player.submit(Action(ActionType.COOK,station.id),sim)
    actor.hunger=75
    assert sim.player.submit(Action(ActionType.EAT,item='cooked_chicken'),sim)
    complete(sim)
    assert actor.inventory.used==0 and actor.hunger<75


def test_cancel_handoff_does_not_complete_work_or_keep_commands():
    sim, actor, ai = controlled()
    actor.inventory.add('raw_chicken')
    actor.position=sim.world.neighbors(sim.cooking_station.position)[0]
    assert sim.player.submit(Action(ActionType.COOK,sim.cooking_station.id),sim)
    sim.step()
    sim.player.direction=(1,0)
    sim.set_participant()
    assert sim.cooking_station.occupied_by is None and not sim.progress.jobs
    assert actor.inventory.quantity('raw_chicken')==1 and actor.inventory.quantity('cooked_chicken')==0
    sim.step()
    assert actor.id in ai.calls
    sim.set_participant(actor.id)
    assert sim.player.command is None and sim.player.direction is None


class Initiator(WaitingAI):
    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        self.sent = False

    def decide(self, actor, *args):
        self.calls.append(actor.id)
        if actor.id=='npc-2' and not self.sent:
            self.sent=True
            return Action(self.kind,'npc-1')
        return Action(ActionType.WAIT)


def invited(kind):
    sim = Simulation(7,decision_provider=Initiator(kind))
    a,b=sim.agents[:2]
    a.position,b.position=(4,2),(5,2)
    a.hunger=b.hunger=10
    a.food=2;b.food=3
    sim.set_participant(a.id)
    sim.step()
    assert sim.player.pending and sim.input_blocked
    return sim,a,b


@pytest.mark.parametrize('accept',[False,True])
def test_ai_offer_needs_explicit_consent_and_real_transfer(accept):
    sim,a,b=invited(ActionType.OFFER_FOOD)
    initial=(a.food,b.food)
    before=sim.snapshot()
    assert FixedTicker().advance(sim,20)==0 and sim.snapshot()==before
    assert sim.player.answer(sim,accept)
    for _ in range(80):sim.step()
    assert (a.food,b.food)==((initial[0]+1,initial[1]-1) if accept else initial)
    assert len([m for m in a.memories if m.result=='offered one food'])==int(accept)
    assert (a.trust[b.id]>0)==accept


@pytest.mark.parametrize('share',[False,True])
def test_player_answers_actual_request_without_ai_response(share):
    sim,a,b=invited(ActionType.REQUEST_FOOD)
    assert sim.player.answer(sim,True)  # listen, not a food decision
    for _ in range(40):
        sim.step()
        if sim.input_blocked:break
    assert sim.player.pending.request_id and sim.social.pending
    request=next(iter(sim.social.pending.values()))
    before=a.food+b.food
    assert sim.player.answer(sim,share)
    for _ in range(80):sim.step()
    assert not sim.social.pending and a.food+b.food==before
    result='shared one food' if share else 'refused'
    assert len([m for m in a.memories if m.result==result])==1
    assert a.id not in sim.decision_provider.calls
    assert len([e for e in sim.events if e.get('social') and e.get('request_id')==request.id and e.get('result')==result])==1


def test_unattended_prompt_cancels_without_sharing_or_invented_answer():
    sim,a,b=invited(ActionType.OFFER_FOOD)
    before=a.food+b.food
    sim.player.advance_prompt(30,sim)
    assert not sim.input_blocked
    assert a.food+b.food==before
    assert not any(m.result=='offered one food' for m in a.memories)
    assert any('Unattended' in m.result for m in a.memories)


def test_incapacitation_is_not_disabled_for_human():
    sim,actor,_=controlled()
    actor.energy=0
    sim.step()
    assert actor.incapacitated_until and not sim.player.submit(Action(ActionType.MOVE_TO,(3,2)),sim)
    for _ in range(30):sim.step()
    assert not actor.incapacitated_until and actor.energy>0


def test_context_uses_real_nearby_objects_only():
    sim,actor,_=controlled()
    bush=next(iter(sim.resources.bushes.values()))
    actor.position=sim.world.neighbors(bush.position)[0]
    assert any(action.kind==ActionType.GATHER and action.target==bush.position for _,action,_ in nearby_options(sim))
    actor.position=(0,0)
    assert not any(action.kind==ActionType.GATHER and action.target==bush.position for _,action,_ in nearby_options(sim))


def test_existing_rule_and_mock_plans_are_cleared_at_handoff():
    from civsandbox.ai import MockDecisionProvider
    for provider in (None, MockDecisionProvider()):
        sim=Simulation(42,decision_provider=provider)
        sim.step()
        rule=getattr(sim.decision_provider,'rule',sim.decision_provider)
        assert sim.agents[0].id in rule.plans
        sim.set_participant('npc-1')
        assert 'npc-1' not in rule.plans
        before=sim.agents[0].position
        for _ in range(8):sim.step()
        assert sim.agents[0].position==before
        assert 'npc-1' not in rule.plans
        sim.close()


def test_stale_accepted_offer_is_revalidated_without_free_food():
    sim,a,b=invited(ActionType.OFFER_FOOD)
    assert sim.player.answer(sim,True)
    b.food=0
    before=a.food
    for _ in range(30):sim.step()
    assert a.food==before
    assert not any(m.result=='offered one food' for m in a.memories)


def test_ai_approaches_human_before_consent_without_freezing_them_remotely():
    from test_conversations import pair
    from civsandbox.decisions import RuleBasedDecisionProvider
    from civsandbox.dialogue import SessionState
    sim,a,b=pair()
    station=sim.cooking_station.position
    choices=[p for p in sim.world.reachable(a.position)
             if sum(abs(x-y) for x,y in zip(p,station))<=3]
    a.position,b.position=next((p,q) for p in choices for q in choices
                             if 2<=sum(abs(x-y) for x,y in zip(p,q))<=3)
    a.food=b.food=2;a.hunger=b.hunger=10
    a.personality['sociability']=1
    sim.decision_provider=RuleBasedDecisionProvider();sim.decision_provider.bind_social(sim.social)
    sim.set_participant(b.id)
    action=sim.decision_provider.decide(a,sim.world,sim.resources,sim.rng)
    session=sim.social.session_for(a)
    assert action.kind==ActionType.MOVE_TO and session.state==SessionState.APPROACHING
    assert not sim.progress.held(b) and not sim.input_blocked
    for _ in range(48):
        sim.step()
        if sim.input_blocked:break
    assert sim.input_blocked and sim.social.nearby(a,b)
    assert not session.turns


def test_menu_input_pause_speed_inspection_and_character_previews():
    import pygame
    from civsandbox.rendering import Renderer,handle_event,advance_frame
    sim=Simulation(42);ticker=FixedTicker();r=Renderer()
    key=lambda value:pygame.event.Event(pygame.KEYDOWN,key=value)
    try:
        handle_event(key(pygame.K_m),sim,ticker,r)
        r.draw(sim,ticker)
        assert r.participant_ui.menu=='modes' and len(r.participant_ui.previews)==4
        before=sim.snapshot();advance_frame(r,ticker,sim,2)
        assert sim.snapshot()==before
        handle_event(key(pygame.K_1),sim,ticker,r)
        assert sim.player.agent_id=='npc-1' and r.participant_ui.menu is None
        handle_event(key(pygame.K_RIGHT),sim,ticker,r)
        assert sim.player.direction==(1,0) and ticker.speed==1
        handle_event(pygame.event.Event(pygame.KEYUP,key=pygame.K_RIGHT),sim,ticker,r)
        assert sim.player.direction is None
        handle_event(key(pygame.K_EQUALS),sim,ticker,r)
        assert ticker.speed==2
        handle_event(key(pygame.K_i),sim,ticker,r)
        r.draw(sim,ticker)
        assert r.participant_ui.menu=='inventory'
        assert handle_event(key(pygame.K_ESCAPE),sim,ticker,r)
        assert r.participant_ui.menu is None
        actor=sim.agents[0]
        bush=next(iter(sim.resources.bushes.values()))
        actor.position=sim.world.neighbors(bush.position)[0]
        handle_event(key(pygame.K_e),sim,ticker,r)
        r.draw(sim,ticker)
        target=next(choice for _,choice in r.participant_ui.options if choice==('bush',bush.position))
        r.participant_ui.choose(target,sim,r);r.draw(sim,ticker)
        assert r.participant_ui.menu=='inspect'
        handle_event(key(pygame.K_ESCAPE),sim,ticker,r)
        handle_event(key(pygame.K_m),sim,ticker,r);r.draw(sim,ticker)
        handle_event(key(pygame.K_5),sim,ticker,r)
        assert sim.player is None
    finally:
        sim.close();pygame.quit()


def test_prompt_ui_timeout_and_pause_do_not_accelerate_simulation():
    import pygame
    from civsandbox.rendering import Renderer,advance_frame
    sim,a,b=invited(ActionType.OFFER_FOOD);r=Renderer();ticker=FixedTicker();ticker.speed=4
    try:
        r.draw(sim,ticker)
        tick=sim.tick
        advance_frame(r,ticker,sim,3)
        assert sim.tick==tick and sim.player.pending.remaining_seconds==27
        sim.paused=True;advance_frame(r,ticker,sim,100)
        assert sim.player.pending.remaining_seconds==27
        sim.paused=False;advance_frame(r,ticker,sim,27)
        assert not sim.input_blocked and sim.tick==tick
        assert a.food==2 and b.food==3
    finally:
        sim.close();pygame.quit()


@pytest.mark.parametrize('kind',[ActionType.TALK,ActionType.OFFER_FOOD])
def test_human_initiates_social_actions_through_same_timed_rules(kind):
    sim,a,_=controlled();b=sim.agents[1]
    a.position,b.position=(4,2),(5,2)
    a.food=3;b.food=0;a.hunger=b.hunger=10
    assert sim.player.submit(Action(kind,b.id),sim)
    sim.step()
    assert not sim.input_blocked and a.food==3 and b.food==0
    assert (a.facing,b.facing)==('right','left')
    for _ in range(80):sim.step()
    expected='greeted' if kind==ActionType.TALK else 'offered one food'
    assert len([m for m in a.memories if m.result==expected])==1
    assert a.food+b.food==3 and b.food==int(kind==ActionType.OFFER_FOOD)


def test_direct_input_uses_existing_interpolation_and_walk_rows():
    import pygame
    from civsandbox.rendering import Renderer,advance_frame
    sim,actor,_=controlled();r=Renderer();t=FixedTicker()
    try:
        r.sync_characters(sim)
        sim.player.direction=(1,0)
        advance_frame(r,t,sim,.25)
        assert actor.position==(3,2)
        advance_frame(r,t,sim,.125)
        assert r.characters[actor.id].position==(2.5,2.0)
        assert r.characters[actor.id].animator.direction=='right'
        assert r.characters[actor.id].animator.moving
    finally:
        sim.close();pygame.quit()


def test_real_context_button_gathers_and_stale_menu_buttons_cannot_fire():
    import pygame
    from civsandbox.rendering import Renderer,handle_event
    sim,a,_=controlled();r=Renderer();t=FixedTicker()
    try:
        bush=next(iter(sim.resources.bushes.values()))
        a.position=sim.world.neighbors(bush.position)[0]
        r.participant_ui.open('context',sim);r.draw(sim,t)
        rect,action=next((rect,action) for rect,action in r.participant_ui.buttons
                         if isinstance(action,Action) and action.kind==ActionType.GATHER)
        handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=rect.center),sim,t,r)
        assert r.participant_ui.menu is None and sim.player.command==action
        complete(sim)
        assert a.food==1
        r.participant_ui.open('modes',sim)
        # A key arriving before a new frame may not select stale context actions.
        handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_1),sim,t,r)
        assert r.participant_ui.menu=='modes' and sim.player.command is None
    finally:
        sim.close();pygame.quit()


def test_switching_between_two_characters_clears_old_input_and_pending_work():
    sim,a,_=controlled()
    old=sim.player
    assert old.submit(Action(ActionType.WAIT),sim)
    old.direction=(1,0)
    sim.set_participant('npc-2')
    assert sim.player.agent_id=='npc-2' and sim.player is not old
    assert old.command is old.direction is old.pending is old.approved is None
    assert len(sim.agents)==4 and sim.agents[0] is a


def test_canceling_a_player_request_does_not_claim_incapacitation():
    from civsandbox.actions import execute
    sim,a,_=controlled();b=sim.agents[1]
    a.position,b.position=(4,2),(5,2)
    assert execute(Action(ActionType.REQUEST_FOOD,b.id),a,sim.world,sim.resources,0,sim.social)
    sim.player.cancel(sim)
    events=[e for e in sim.social.events if e.get('result','').startswith('canceled:')]
    assert len(events)==1 and 'Player canceled' in events[0]['result']
    assert not sim.social.pending and not a.incapacitated_until


def test_request_timeout_records_one_cancellation_memory_per_agent():
    sim,a,b=invited(ActionType.REQUEST_FOOD)
    sim.player.answer(sim,True)
    for _ in range(40):
        sim.step()
        if sim.input_blocked:break
    assert sim.player.pending.request_id
    sim.player.advance_prompt(30,sim)
    assert not sim.social.pending and not sim.input_blocked
    for actor in (a,b):
        assert len([m for m in actor.memories if 'Unattended' in m.result])==1
