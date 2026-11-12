"""NPC invitations preserve selected intentions; listening never approves a gift."""
import pytest
from civsandbox.actions import Action, ActionType
from civsandbox.decisions import RuleBasedDecisionProvider
from civsandbox.dialogue import ConversationIntent, IntentKind, SessionState
from civsandbox.dialogue_controller import DialogueController
from civsandbox.simulation import Simulation
from test_participant import invited
from test_portrait_dialogue import settle, scene


def acknowledge(sim):
    c=DialogueController()
    assert c.open_incoming(sim)
    c.continue_line(sim)
    assert c.choose('accept',sim)
    # The accepted NPC action supplies the first actual spoken turn.
    if c.owner:c.advance(60,sim)
    assert c.current.speaker_id==c.peer_id
    first=c.current.text
    settle(c,sim)
    return c,first


@pytest.mark.parametrize('answer,result,delta', [('share','shared',-1),('refuse','refused',0),('none','refused',0)])
def test_request_is_npc_led_and_resolves_exactly_once(answer,result,delta):
    sim,player,npc=invited(ActionType.REQUEST_FOOD)
    if answer=='none':player.food=0
    before=(player.food,npc.food)
    c,first=acknowledge(sim);session=c.session(sim)
    assert session.intent.kind==IntentKind.REQUEST_FOOD
    assert session.intent.item=='berries' and session.intent.quantity==1
    assert 'berry' in first.lower() or 'berries' in first.lower()
    keys={x.key for x in c.choices(sim)}
    assert {'share','refuse'}<=keys and not keys & {'request','offer','how','smalltalk'}
    assert c.choose(answer,sim)
    assert (player.food,npc.food)==before  # no effect until timed completion
    settle(c,sim)
    assert not c.active and session.intent_resolution==result
    assert (player.food,npc.food)==(before[0]+delta,before[1]-delta)
    expected='shared one food' if answer=='share' else 'refused'
    for actor in (player,npc):assert len([m for m in actor.memories if m.result==expected])==1
    for _ in range(5):c.advance(60,sim);c.continue_line(sim)
    assert not c.choose(answer,sim)
    assert len([e for e in sim.events if e.get('action')=='INTENT_RESOLVED' and e.get('session_id')==session.id])==1
    assert not sim.social.pending and not sim.social.active_sessions


@pytest.mark.parametrize('accept', [True,False])
def test_offer_requires_explicit_consent_and_conserves_food(accept):
    sim,player,npc=invited(ActionType.OFFER_FOOD);before=(player.food,npc.food)
    c,first=acknowledge(sim);session=c.session(sim)
    assert session.intent.kind==IntentKind.OFFER_FOOD
    assert (player.food,npc.food)==before
    assert {x.key for x in c.choices(sim)}=={'accept_offer','decline_offer'}
    assert 'berry' in first.lower() or 'berries' in first.lower()
    assert c.choose('accept_offer' if accept else 'decline_offer',sim)
    settle(c,sim)
    assert not c.active
    assert (player.food,npc.food)==(before[0]+int(accept),before[1]-int(accept))
    assert session.intent_resolution==('accepted' if accept else 'declined')
    assert len([e for e in sim.events if e.get('result')=='offered one food'])==int(accept)
    if not accept:assert len([m for m in player.memories if m.result=='declined offer'])==1


@pytest.mark.parametrize('when',['before_listen','before_accept','during_action'])
def test_lost_offer_stock_never_creates_food(when):
    sim,player,npc=invited(ActionType.OFFER_FOOD)
    if when=='before_listen':npc.food=0
    c,_=acknowledge(sim)
    if when=='before_accept':npc.food=0
    before=player.food
    if when=='during_action':
        assert c.choose('accept_offer',sim);npc.food=0;settle(c,sim)
    else:
        assert not next(x for x in c.choices(sim) if x.key=='accept_offer').enabled
        assert not c.choose('accept_offer',sim)
        assert c.choose('decline_offer',sim);settle(c,sim)
    assert player.food==before and npc.food==0
    assert not any(e.get('result')=='offered one food' for e in sim.events)
    assert not sim.progress.locks and not sim.social.active_sessions


@pytest.mark.parametrize('hungry,intent',[(False,IntentKind.CASUAL_TALK),(True,IntentKind.CHECK_ON_PLAYER)])
def test_factual_talk_intent_and_contextual_replies(hungry,intent):
    sim,player,npc=invited(ActionType.TALK)
    # Rebuild this test invitation with the selected physical observation.
    sim.social.cancel_session(sim.social.session_for(npc).id,'test setup')
    sim.social.agent_cooldowns.clear();sim.social.pair_cooldowns.clear()
    player.hunger=65 if hungry else 10
    session=sim.social.propose(npc,player.id,'greeting',sim.world,action=Action(ActionType.TALK,player.id))
    sim.player.pending.session_id=session.id
    c,first=acknowledge(sim)
    assert session.intent.kind==intent and first
    assert {x.key for x in c.choices(sim)}=={'reply_warm','reply_brief','goodbye'}
    assert c.choose('reply_warm',sim);settle(c,sim)
    assert not c.active and session.intent_resolution=='responded'


def test_player_led_menu_remains_available():
    sim,player,npc,c=scene();settle(c,sim)
    assert not c.npc_initiated
    assert {'request','offer','smalltalk','how'}<={x.key for x in c.choices(sim)}
    c.close(sim)


def test_cancel_releases_reservations_and_applies_cooldown():
    sim,player,npc=invited(ActionType.REQUEST_FOOD)
    c,_=acknowledge(sim);session=c.session(sim);before=(player.food,npc.food)
    c.close(sim,canceled=True)
    assert session.state==SessionState.CANCELED and session.intent_resolution=='canceled'
    assert not sim.social.active_sessions and not sim.social.pending and not sim.progress.locks
    assert (player.food,npc.food)==before
    assert sim.social.cooldown_reason(npc,player,'REQUEST_FOOD')


class OneRealNPC:
    """Test isolation only: selected actor uses the unchanged real offline policy."""
    name='rule-based'
    def __init__(self,actor_id):self.rules=RuleBasedDecisionProvider();self.actor_id=actor_id
    def bind_social(self,social):self.rules.bind_social(social)
    def bind_routines(self,*args):self.rules.bind_routines(*args)
    def begin_tick(self,*args):self.rules.begin_tick(*args)
    def on_action_result(self,*args):self.rules.on_action_result(*args)
    def decide(self,actor,*args):
        return self.rules.decide(actor,*args) if actor.id==self.actor_id else Action(ActionType.WAIT)


def test_real_policy_retains_request_from_approach_through_portrait_and_response():
    ai=OneRealNPC('npc-3');sim=Simulation(7,ai,scenario='food_shortage')
    sim.set_participant('npc-1');player=sim.agents[0];npc=sim.agents[2]
    player.position=(4,2);player.food=3;player.hunger=25
    npc.position=(7,2);npc.food=0;npc.hunger=72;npc.energy=90
    sim.agents[1].position=(18,2);sim.agents[3].position=(20,2)
    sim.step();session=sim.social.session_for(npc)
    assert session and session.intent.kind==IntentKind.REQUEST_FOOD
    intent=session.intent
    assert intent.context['position']==(7,2) and intent.context['recipient_position']==(4,2)
    assert session.state==SessionState.APPROACHING
    for _ in range(80):
        if sim.player.pending:break
        sim.step()
    assert sim.player.pending and session.intent is intent
    assert sim.player.pending.action.kind==ActionType.REQUEST_FOOD
    assert npc.position!=(7,2) and sim.social.nearby(npc,player)
    c,_=acknowledge(sim)
    assert c.session(sim) is session and session.intent is intent
    assert c.choose('share',sim);settle(c,sim)
    assert session.intent_resolution=='shared' and npc.food==1 and player.food==2


@pytest.mark.parametrize('item,quantity', [('berries',0),('berries',2),('raw_chicken',1),(None,1),('berries',True)])
def test_intent_rejects_unsupported_transfer_metadata(item,quantity):
    with pytest.raises(ValueError):ConversationIntent(IntentKind.REQUEST_FOOD,item,quantity)


def test_gratitude_requires_actual_help_and_respects_memory_setting():
    # Complete a real player gift through the common timed executor first.
    sim,player,npc,c=scene();settle(c,sim);player.food=2;npc.food=0
    assert c.choose('offer',sim);settle(c,sim);c.close(sim)
    assert any(m.actor_id==player.id and m.result=='offered one food' for m in npc.memories)
    talk=Action(ActionType.TALK,player.id)
    intent=sim.social.make_intent(npc,player,talk)
    assert intent.kind==IntentKind.THANK_PLAYER and intent.context['help_tick']==sim.tick
    sim.social.memory_enabled=False
    assert sim.social.make_intent(npc,player,talk).kind==IntentKind.CASUAL_TALK
    sim.social.memory_enabled=True
    # Allow real simulation time to release cooldowns, without invented speech.
    from test_participant import WaitingAI
    sim.decision_provider=WaitingAI()
    for _ in range(150):sim.step()
    npc.hunger=player.hunger=20;npc.energy=player.energy=90
    session=sim.social.propose(npc,player.id,'greeting',sim.world,action=talk)
    assert session and session.intent.kind==IntentKind.THANK_PLAYER
    from civsandbox.player import PlayerPrompt
    sim.player.pending=PlayerPrompt(npc.id,talk,session_id=session.id)
    c,first=acknowledge(sim)
    assert 'thank' in first.lower()
    assert c.choose('reply_brief',sim);settle(c,sim)
    assert session.intent_resolution=='responded'
    assert sim.social.make_intent(npc,player,talk).kind==IntentKind.CASUAL_TALK


def test_cancel_during_accepted_gift_releases_without_transfer():
    sim,player,npc=invited(ActionType.OFFER_FOOD);c,_=acknowledge(sim)
    before=(player.food,npc.food)
    assert c.choose('accept_offer',sim);c.advance(.25,sim)
    c.close(sim,canceled=True)
    assert (player.food,npc.food)==before
    assert not sim.progress.jobs and not sim.progress.locks and not sim.social.active_sessions


def test_real_policy_offer_retains_purpose_during_travel():
    ai=OneRealNPC('npc-1');sim=Simulation(7,ai,scenario='food_shortage')
    sim.set_participant('npc-2');npc=sim.agents[0];player=sim.agents[1]
    npc.position=(7,2);npc.food=3;npc.hunger=20;npc.energy=90
    player.position=(4,2);player.food=0;player.hunger=70
    sim.agents[2].position=(18,2);sim.agents[3].position=(20,2)
    sim.step();session=sim.social.session_for(npc)
    assert session and session.intent.kind==IntentKind.OFFER_FOOD
    for _ in range(80):
        if sim.player.pending:break
        sim.step()
    assert sim.player.pending.action.kind==ActionType.OFFER_FOOD
    c,_=acknowledge(sim)
    assert c.session(sim) is session and player.food==0 and npc.food==3
    assert c.choose('decline_offer',sim);settle(c,sim)
    assert session.intent_resolution=='declined' and player.food==0 and npc.food==3


def test_second_npc_cannot_replace_addressed_invitation():
    sim,player,npc=invited(ActionType.REQUEST_FOOD)
    prompt=sim.player.pending;other=sim.agents[2];other.position=(4,3)
    assert sim.player.intercept(Action(ActionType.TALK,player.id),other,sim)
    assert sim.player.pending is prompt
    assert sim.social.session_for(player).initiator_id==npc.id
