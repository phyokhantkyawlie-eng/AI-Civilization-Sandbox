"""Accepted physical encounters, bounded sessions, and independent reading time."""
from collections import Counter
from dataclasses import replace
import pytest

from civsandbox.actions import Action,ActionType,execute,validate
from civsandbox.dialogue import SocialSettings,SessionState,choose_line
from civsandbox.feedback import Feedback
from civsandbox.simulation import Simulation,FixedTicker
from civsandbox.world import World,Tile


class ExchangeProvider:
    def __init__(self,kind=ActionType.TALK,answer=ActionType.SHARE_FOOD):
        self.kind,self.answer=kind,answer
        self.social=None
        self.started=False
    def bind_social(self,social):self.social=social
    def decide(self,actor,*args):
        incoming=[r for r in self.social.active_requests(actor) if r.recipient_id==actor.id]
        if incoming:return Action(self.answer,incoming[0].requester_id,request_id=incoming[0].id)
        if actor.id=='npc-1' and not self.started:
            self.started=True
            return Action(self.kind,'npc-2')
        return Action(ActionType.WAIT)


def pair(kind=ActionType.TALK,answer=ActionType.SHARE_FOOD,settings=None):
    sim=Simulation(7,decision_provider=ExchangeProvider(kind,answer),social_settings=settings)
    a,b=sim.agents[:2]
    a.position,b.position=(4,2),(5,2)
    a.hunger,b.hunger=10,10
    if kind==ActionType.REQUEST_FOOD:a.hunger=60;b.food=3
    if kind==ActionType.OFFER_FOOD:a.food=3;b.hunger=60;b.food=0
    return sim,a,b


def until_finished(sim,limit=200):
    for _ in range(limit):
        sim.step()
        if sim.social.sessions and all(s.state in (SessionState.COMPLETED,SessionState.CANCELED)
                                       for s in sim.social.sessions.values()):return
    raise AssertionError('Session did not terminate')


def test_greeting_requires_proximity_stops_both_faces_and_orders_turns():
    sim,a,b=pair();positions=(a.position,b.position)
    sim.step()
    session=sim.social.session_for(a)
    assert session is sim.social.session_for(b) and session.state==SessionState.ENGAGED
    assert (a.facing,b.facing)==('right','left')
    for _ in range(8):
        sim.step()
        assert (a.position,b.position)==positions
        assert not a.memories
    until_finished(sim)
    lines=[e for e in sim.events if e['action']=='DIALOGUE']
    assert [e['actor_id'] for e in lines]==[a.id,b.id]
    assert [e['turn'] for e in lines]==[0,1]
    assert lines[1]['tick']>lines[0]['tick']
    assert session.outcome=='greeted'
    assert len([m for m in a.memories if m.result=='greeted'])==1
    assert a.trust[b.id]==b.trust[a.id]==1


def test_distant_and_busy_recipients_do_not_produce_speech():
    sim,a,b=pair();b.position=(20,2)
    assert not validate(Action(ActionType.TALK,b.id),a,sim.world,sim.resources,sim.social)
    intent=sim.social.propose(a,b.id,'greeting',sim.world)
    assert intent.state==SessionState.APPROACHING
    assert not [e for e in sim.social.events if e['action']=='DIALOGUE']
    sim.social.cancel_session(intent.id,'partner too far')
    b.position=(5,2);b.energy=40
    assert sim.progress.execute(Action(ActionType.REST),b,sim.world,sim.resources,0,'rule-based')
    assert not validate(Action(ActionType.TALK,b.id),a,sim.world,sim.resources,sim.social)
    assert not [e for e in sim.social.events if e['action']=='DIALOGUE']


def test_conflicting_sessions_are_rejected_and_cancellation_releases_locks():
    sim,a,b=pair();sim.step();session=sim.social.session_for(a)
    c=sim.agents[2];c.position=(5,3)
    assert sim.social.propose(c,b.id,'greeting',sim.world) is None
    assert not validate(Action(ActionType.TALK,b.id),c,sim.world,sim.resources,sim.social)
    sim.social.cancel_session(session.id,'test cancellation')
    assert session.state==SessionState.CANCELED
    assert not sim.social.active_sessions and not sim.progress.locks
    assert not sim.progress.jobs
    count=len([e for e in sim.social.events if e['action']=='SESSION' and e['state']=='CANCELED'])
    sim.social.cancel_session(session.id,'again')
    assert count==len([e for e in sim.social.events if e['action']=='SESSION' and e['state']=='CANCELED'])


@pytest.mark.parametrize('answer',[ActionType.SHARE_FOOD,ActionType.REFUSE_REQUEST])
def test_request_response_transfer_and_memories_once_with_truthful_outcomes(answer):
    sim,a,b=pair(ActionType.REQUEST_FOOD,answer)
    initial=a.food+b.food
    until_finished(sim)
    session=next(iter(sim.social.sessions.values()))
    assert session.state==SessionState.COMPLETED
    assert a.food+b.food==initial
    result='shared one food' if answer==ActionType.SHARE_FOOD else 'refused'
    outcomes=[e for e in sim.events if e.get('social') and e.get('result')==result]
    assert len(outcomes)==1 and outcomes[0]['session_id']==session.id
    assert len([m for m in a.memories if m.result==result])==1
    lines=[e for e in sim.events if e['action']=='DIALOGUE']
    assert [e['turn'] for e in lines]==list(range(len(lines)))
    if answer==ActionType.SHARE_FOOD:
        assert a.food==1 and b.food==2
        completion=outcomes[0]['tick']
        gifts=[e for e in lines if e['text'] in ('Here, take one berry.','This berry is for you.','Here is a berry to help.')]
        assert len(gifts)==1 and gifts[0]['tick']>=completion
        assert any('hank' in e['text'] or 'appreciate' in e['text'] for e in lines)
    else:
        assert a.food==0 and b.food==3
        assert -4<=a.trust[b.id]<=0
        assert not any(e['text'].startswith('Here') for e in lines)


def test_voluntary_offer_uses_real_inventory_and_creates_thanks():
    sim,a,b=pair(ActionType.OFFER_FOOD)
    until_finished(sim)
    assert (a.food,b.food)==(2,1)
    events=[e for e in sim.events if e.get('result')=='offered one food']
    assert len(events)==1 and set(events[0]['memory_created_for'])=={a.id,b.id}
    assert any(e['action']=='DIALOGUE' and e['actor_id']==b.id and ('hank' in e['text'] or 'appreciate' in e['text']) for e in sim.events)


def test_failed_transfer_never_speaks_as_though_food_was_given():
    sim,a,b=pair(ActionType.OFFER_FOOD);sim.step()
    a.food=0
    until_finished(sim)
    assert b.food==0
    assert not any(e.get('result')=='offered one food' for e in sim.events)
    assert not any(e['action']=='DIALOGUE' and e['text'].startswith('Here') for e in sim.events)
    assert next(iter(sim.social.sessions.values())).state==SessionState.CANCELED


def test_pause_freezes_logical_session_and_real_reading_queue():
    sim,a,b=pair();sim.step()
    feedback=Feedback();feedback.consume(sim.events,sim.social)
    assert feedback.speech_notice() is not None
    sim.paused=True;before=sim.snapshot();remaining=feedback.reading_remaining
    FixedTicker().advance(sim,100)
    feedback.advance_reading(100,paused=True)
    assert sim.snapshot()==before and feedback.reading_remaining==remaining


def test_fast_speed_keeps_reading_time_and_uses_history_when_people_leave():
    import pygame
    from civsandbox.rendering import Renderer,advance_frame
    sim,a,b=pair()
    renderer=Renderer();ticker=FixedTicker();ticker.speed=4
    try:
        advance_frame(renderer,ticker,sim,.25);renderer.draw(sim,ticker)
        first=renderer.feedback.current_dialogue
        seconds=renderer.feedback.reading_remaining
        assert seconds>=3
        advance_frame(renderer,ticker,sim,.25);renderer.draw(sim,ticker)
        assert renderer.feedback.current_dialogue is first
        assert abs(renderer.feedback.reading_remaining-(seconds-.25))<1e-8
        until_finished(sim)
        renderer.draw(sim,ticker)
        assert renderer.feedback.speech_notice() is None
        assert renderer.feedback.history and renderer.feedback.current_dialogue
    finally:sim.close();pygame.quit()


def test_no_dialogue_for_fake_session_or_provider_explanation():
    feedback=Feedback()
    events=[{'event_id':1,'actor_id':'npc-1','action':'TALK','executed':True,'public_reason':'Hello'},
            {'event_id':2,'actor_id':'npc-1','action':'DIALOGUE','session_id':'missing',
             'session_validated':True,'turn':0,'text':'Made up','reading_seconds':3}]
    feedback.consume(events)
    assert not feedback.history and feedback.speech_notice() is None


def test_cooldowns_are_per_agent_pair_and_request_with_emergency_recovery():
    sim,a,b=pair(ActionType.REQUEST_FOOD,ActionType.REFUSE_REQUEST)
    until_finished(sim)
    request=Action(ActionType.REQUEST_FOOD,b.id)
    assert not validate(request,a,sim.world,sim.resources,sim.social)
    sim.social.advance(sim.tick+41)
    a.hunger=90
    assert sim.social.cooldown_reason(a,b,'REQUEST_FOOD') is None
    assert sim.social.cooldown_reason(a,b,'TALK') is not None


def test_approach_timeout_has_no_speech_and_no_permanent_reservation():
    sim,a,b=pair();b.position=(8,2)
    session=sim.social.propose(a,b.id,'greeting',sim.world)
    sim.social.advance(session.deadline)
    assert session.state==SessionState.CANCELED and not sim.social.active_sessions
    assert not any(e['action']=='DIALOGUE' for e in sim.social.events)


def test_template_history_is_guarded_when_memory_is_disabled():
    from civsandbox.dialogue import BANKS
    sim,a,b=pair();sim.social.memory_enabled=False
    sim.social.record(b.id,a.id,'SHARE_FOOD','shared one food',{a.id:50})
    sim.social.advance(1)
    line=choose_line(sim.social,a,b,'greeting')
    assert line not in BANKS['helped'] and line not in BANKS['warm']
    sim.social.memory_enabled=True
    assert choose_line(sim.social,a,b,'greeting') in BANKS['helped']


def test_read_duration_and_repetition_suppression_are_configurable():
    settings=SocialSettings(minimum_line_seconds=4,characters_per_second=10)
    assert settings.reading_seconds('Hi')==4
    assert settings.reading_seconds('x'*80)==9
    sim,a,b=pair(settings=settings)
    first=choose_line(sim.social,a,b,'greeting')
    sim.social.repeated_lines[(a.id,b.id,first)]=sim.social.tick
    assert choose_line(sim.social,a,b,'greeting')!=first
    with pytest.raises(ValueError):SocialSettings(pair_cooldown_ticks=0)


@pytest.mark.parametrize('seed',[7,42])
def test_headless_sessions_and_physical_turns_are_deterministic(seed):
    a,b=Simulation(seed,scenario='food_shortage'),Simulation(seed,scenario='food_shortage')
    for _ in range(240):a.step();b.step()
    assert a.snapshot()==b.snapshot()
    lines=[e for e in a.events if e['action']=='DIALOGUE']
    assert lines
    for line in lines:
        assert sum(abs(x-y) for x,y in zip(line['speaker_position'],line['partner_position']))<=1
        assert line['session_id'] in a.social.sessions


def test_serious_negative_memory_causes_bounded_avoidance_but_memory_off_does_not():
    from civsandbox.decisions import RuleBasedDecisionProvider
    sim,a,b=pair(ActionType.REQUEST_FOOD)
    a.hunger=90
    assert execute(Action(ActionType.REQUEST_FOOD,b.id),a,sim.world,sim.resources,0,sim.social)
    request=next(iter(sim.social.pending.values()))
    assert execute(Action(ActionType.REFUSE_REQUEST,a.id,request_id=request.id),b,sim.world,sim.resources,0,sim.social)
    assert a.trust[b.id]==-4 and sim.social.serious_dispute(a,b.id)
    a.hunger=40;a.food=2
    rule=RuleBasedDecisionProvider();rule.bind_social(sim.social)
    assert any(c.goal=='AVOID' for c in rule.candidates(a,sim.world,sim.resources))
    sim.social.memory_enabled=False
    assert not sim.social.serious_dispute(a,b.id)
    assert not any(c.goal=='AVOID' for c in rule.candidates(a,sim.world,sim.resources))
    sim.social.memory_enabled=True
    sim.social.advance(sim.social.settings.avoid_ticks+1)
    assert not sim.social.serious_dispute(a,b.id)


def test_shared_campfire_company_is_a_real_approach_then_conversation():
    from civsandbox.decisions import RuleBasedDecisionProvider
    sim,a,b=pair()
    station=sim.cooking_station.position
    # Find reachable walkable neighbors with two to four tiles between the partners.
    choices=[p for p in sim.world.reachable(station if sim.world.walkable(station) else sim.world.neighbors(station)[0])
             if sum(abs(x-y) for x,y in zip(p,station))<=3]
    positions=next((p,q) for p in choices for q in choices if 2<=sum(abs(x-y) for x,y in zip(p,q))<=3)
    a.position,b.position=positions
    a.food=b.food=2;a.hunger=b.hunger=10
    a.personality['sociability']=1
    sim.decision_provider=RuleBasedDecisionProvider();sim.decision_provider.bind_social(sim.social)
    first=sim.decision_provider.decide(a,sim.world,sim.resources,sim.rng)
    assert first.kind==ActionType.MOVE_TO
    session=sim.social.session_for(a)
    assert session and session.purpose=='campfire' and session.state==SessionState.APPROACHING
    assert not session.turns
    for _ in range(48):
        sim.step()
        if any(e['action']=='DIALOGUE' and e.get('session_id')==session.id for e in sim.events):break
    assert any(e['action']=='DIALOGUE' and e.get('session_id')==session.id for e in sim.events)


def test_history_ui_and_session_debug_controls_are_available():
    import pygame
    from civsandbox.rendering import Renderer,handle_event
    sim,a,b=pair();sim.step()
    try:
        r=Renderer();r.selected_id=a.id;r.draw(sim,FixedTicker())
        handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_c),sim,FixedTicker(),r)
        r.draw(sim,FixedTicker());assert r.history_open
        handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_F3),sim,FixedTicker(),r)
        handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_s),sim,FixedTicker(),r)
        r.draw(sim,FixedTicker());assert r.social_debug
    finally:sim.close();pygame.quit()


def test_configured_cooldowns_can_be_shorter_than_the_old_default():
    settings=SocialSettings(agent_cooldown_ticks=4,pair_cooldown_ticks=8,request_retry_ticks=8)
    sim,a,b=pair(settings=settings)
    until_finished(sim)
    ended=sim.social.tick
    assert sim.progress.cooldowns[a.id]==ended+4
    sim.social.advance(sim.tick+8)
    assert validate(Action(ActionType.TALK,b.id),a,sim.world,sim.resources,sim.social)


def test_social_configuration_loads_without_api_dependencies(tmp_path,monkeypatch):
    from civsandbox.config import Settings
    values={'SOCIAL_AGENT_COOLDOWN_SECONDS':'2','SOCIAL_PAIR_COOLDOWN_SECONDS':'6',
            'SOCIAL_REQUEST_RETRY_SECONDS':'9','DIALOGUE_MIN_SECONDS':'4',
            'DIALOGUE_CHARACTERS_PER_SECOND':'12'}
    for name in values:monkeypatch.delenv(name,raising=False)
    path=tmp_path/'.env';path.write_text('\n'.join(f'{k}={v}' for k,v in values.items()))
    settings=Settings.load(path).social
    assert (settings.agent_cooldown_ticks,settings.pair_cooldown_ticks,settings.request_retry_ticks)==(8,24,36)
    assert settings.minimum_line_seconds==4 and settings.characters_per_second==12
