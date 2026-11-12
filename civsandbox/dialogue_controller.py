"""Player portrait presentation/input adapter over existing social sessions.

The world tick is frozen. Only a selected, validated social job is advanced on a
local 0.25-second UI action clock; it never advances needs, wildlife or other
sessions. Social deadlines stay at frozen world time. Turn reading is manual.
"""
from collections import deque
from dataclasses import dataclass
from .actions import Action,ActionType,SOCIAL_ACTIONS,validate
from .dialogue import SessionState


@dataclass(frozen=True)
class Choice:
    key: str
    label: str
    enabled: bool = True
    reason: str = ''


@dataclass(frozen=True)
class Line:
    speaker_id: str
    text: str
    turn: int | None = None


class DialogueController:
    def __init__(self):
        self.serial=0
        self.reset()

    def reset(self):
        self.active=False;self.peer_id=None;self.player_id=None;self.session_id=None
        self.social_ref=None;self.queue=deque(maxlen=64);self.queued=0;self.current=None
        self.phase='idle';self.owner=None;self.action=None;self.job_ref=None;self.elapsed=0.0
        self.origin=0;self.waiting=False;self.end_after_lines=False;self.incoming=None

    def actors(self,sim):
        return sim.social.agents.get(self.player_id),sim.social.agents.get(self.peer_id)

    def flush(self,sim):
        sim.events.extend(sim.social.events);sim.social.events.clear()
        if hasattr(sim.decision_provider,'audit_events'):
            sim.events.extend(sim.decision_provider.audit_events);sim.decision_provider.audit_events.clear()
        sim.number_events()
        if sim.event_limit is not None:del sim.events[:-sim.event_limit]

    def can_open(self,sim,peer_id,incoming=False):
        if not sim.player:return 'Take control of a villager first.'
        if sim.social.modal_pair and not self.active:return 'Finish the current conversation first.'
        if sim.player.pending and not incoming:return 'Answer the current invitation first.'
        if not isinstance(peer_id,str):return 'Choose another villager.'
        actor=sim.social.agents[sim.player.agent_id];peer=sim.social.agents.get(peer_id)
        if peer is None or peer is actor:return 'Choose another villager.'
        if not sim.social.nearby(actor,peer):return 'Move closer to talk (one tile away).'
        if actor.incapacitated_until or peer.incapacitated_until:return 'A villager is recovering. Try again when they are ready.'
        session=sim.social.session_for(actor)
        if session and set(session.participants)!={actor.id,peer.id}:return 'Finish the current conversation first.'
        other_session=sim.social.session_for(peer)
        if other_session and other_session is not session:return peer.name+' is already speaking with someone.'
        for a in (actor,peer):
            owner=sim.progress.locks.get(a.id)
            if owner in sim.progress.jobs:return a.name+' is busy. Finish the activity or try again shortly.'
        return ''

    def activate(self,sim,peer_id):
        self.player_id=sim.player.agent_id;self.peer_id=peer_id;self.social_ref=sim.social
        sim.social.modal_pair=(self.player_id,self.peer_id)
        sim.player.clear();sim.player.approved=None;sim.player.responding_request=None;self.active=True;self.phase='initiating';self.serial+=1
        a,b=self.actors(sim);sim.progress.face_pair(a,b)

    def open(self,sim,peer_id,action=None):
        if self.active:return False,'Finish this conversation first.'
        reason=self.can_open(sim,peer_id)
        if reason:return False,reason
        self.activate(sim,peer_id)
        if not self.start(sim,sim.social.agents[self.player_id],action or Action(ActionType.TALK,peer_id),'greeting'):
            self.close(sim,canceled=True)
            return False,'This interaction is unavailable right now.'
        return True,''

    def open_incoming(self,sim):
        prompt=sim.player.pending if sim.player else None
        if not prompt or self.active:return False
        reason=self.can_open(sim,prompt.actor_id,incoming=True)
        if prompt.request_id:
            request=sim.social.pending.get(prompt.request_id)
            if (request is None or sim.social.tick>=request.expires_tick
                    or request.requester_id!=prompt.actor_id or request.recipient_id!=sim.player.agent_id):
                reason='That food request is no longer available.'
        if reason:
            sim.player.pending=None;sim.player.decline(sim,prompt,reason);self.flush(sim)
            sim.player.message=reason
            return False
        self.activate(sim,prompt.actor_id);self.incoming=prompt;sim.player.pending=None
        a,b=self.actors(sim)
        session=sim.social.session_for(b)
        if session is None:session=sim.social.propose(b,a.id,prompt.action.kind.value.lower(),sim.world)
        if session is None:
            self.close(sim,canceled=True);return False
        self.session_id=session.id
        sim.social.transition(session,SessionState.ENGAGED,'Player opened the addressed invitation')
        if prompt.request_id:
            texts=[t.text for t in session.turns if t.delivered and t.purpose=='question']
            text=texts[-1] if texts else 'Could you spare one berry?'
        else:
            text={ActionType.TALK:'May I stop for a conversation?',ActionType.REQUEST_FOOD:'May I ask you for some food?',ActionType.OFFER_FOOD:'May I offer you a berry?'}.get(prompt.action.kind,'May I speak with you?')
        self.current=Line(b.id,text);self.queued=len(session.turns);self.phase='showing';self.serial+=1
        self.flush(sim);return True

    def session(self,sim):return sim.social.sessions.get(self.session_id)

    def collect(self,sim):
        session=self.session(sim)
        if session:
            while self.queued<len(session.turns):
                index=self.queued;turn=session.turns[index]
                self.queue.append(Line(turn.speaker_id,turn.text,index));self.queued+=1
        if self.current is None and self.queue:self.show_next(sim)

    def show_next(self,sim):
        self.current=self.queue.popleft();self.phase='showing';self.waiting=False;self.serial+=1
        if self.current.turn is not None:
            sim.social.present_modal_turn(self.session(sim),self.current.turn)
            self.flush(sim)

    def start(self,sim,actor,action,topic='smalltalk'):
        if self.owner or actor.id in sim.progress.jobs:return False
        if not isinstance(action,Action) or action.kind not in SOCIAL_ACTIONS:return False
        if not validate(action,actor,sim.world,sim.resources,sim.social):return False
        sim.social.modal_topic=topic
        if not sim.progress.execute(action,actor,sim.world,sim.resources,sim.tick,'player' if actor.id==self.player_id else getattr(sim.decision_provider,'name','rule-based')):return False
        session=sim.social.session_for(actor)
        if session is None:return False
        self.session_id=session.id;self.owner=actor.id;self.action=action;self.job_ref=sim.progress.jobs.get(actor.id)
        self.origin=sim.tick;self.elapsed=0;self.phase='resolving'
        self.collect(sim);self.flush(sim)
        if actor.id not in sim.progress.jobs:self.finished(sim,True)
        return True

    def advance(self,elapsed,sim):
        if not self.active:return
        if (self.social_ref is not sim.social or not sim.player or sim.player.agent_id!=self.player_id):
            self.close(sim,canceled=True);return
        a,b=self.actors(sim);session=self.session(sim)
        if (not a or not b or a.incapacitated_until or b.incapacitated_until or not sim.social.nearby(a,b)
                or not session or session.state==SessionState.CANCELED and not self.end_after_lines):
            self.close(sim,canceled=True);return
        if not self.owner:return
        self.elapsed+=max(0,elapsed)
        tick=self.origin+int((self.elapsed+1e-9)/.25)
        job=sim.progress.jobs.get(self.owner)
        if not job or job is not self.job_ref:
            self.finished(sim,False);return
        if tick>=job.finish_tick:
            actor=sim.social.agents[self.owner]
            reason=sim.social.rejection_reason(self.action,actor)
            success=sim.progress.execute(self.action,actor,sim.world,sim.resources,job.finish_tick,'player-dialogue')
            if not success:
                sim.events.append({'tick':sim.tick,'actor_id':actor.id,'agent':actor.name,
                                   'action':'REJECTED','requested_action':self.action.kind.value,
                                   'reason':reason or 'Social action failed final validation'})
            self.finished(sim,success)

    def finished(self,sim,success):
        actor=sim.social.agents.get(self.owner);action=self.action
        self.owner=None;self.action=None;self.job_ref=None;self.elapsed=0
        if actor and actor.id!=self.player_id and hasattr(sim.decision_provider,'on_action_result'):
            sim.decision_provider.on_action_result(actor,action,success,not success,sim.tick)
        self.collect(sim);self.flush(sim)
        if not success:
            self.close(sim,canceled=True,reason='Social action failed final validation');return
        if action.kind==ActionType.REQUEST_FOOD and actor.id==self.player_id:
            a,b=self.actors(sim)
            # Actual selected provider decides once. Other survival choices are not
            # silently converted to a scripted refusal or a successful transfer.
            try:response=sim.decision_provider.decide(b,sim.world,sim.resources,sim.rng)
            except Exception:response=None
            if (isinstance(response,Action) and response.kind in (ActionType.SHARE_FOOD,ActionType.REFUSE_REQUEST)
                    and response.target==a.id and self.start(sim,b,response)):
                pass
            else:
                sim.social.cancel_session(self.session_id,'Recipient is not ready to answer')
                self.queue.append(Line(b.id,'I cannot answer that request right now. Please try again later.'))
                self.end_after_lines=True
        elif action.kind==ActionType.REQUEST_FOOD and actor.id!=self.player_id:
            from .player import PlayerPrompt
            session=self.session(sim)
            self.incoming=PlayerPrompt(actor.id,action,session.request_id)
        if self.waiting:
            if self.queue:self.show_next(sim)
            elif self.owner is None:self.phase='choosing'

    def continue_line(self,sim):
        if not self.active:return
        if self.queue:self.show_next(sim)
        elif self.end_after_lines:self.close(sim,canceled=False)
        elif self.owner:self.waiting=True;self.phase='resolving'
        else:self.phase='choosing'

    def choices(self,sim):
        if not self.active or self.phase!='choosing':return []
        a,b=self.actors(sim)
        if a is None or b is None:return []
        if self.incoming:
            if self.incoming.request_id:
                share=Action(ActionType.SHARE_FOOD,b.id,request_id=self.incoming.request_id)
                valid=validate(share,a,sim.world,sim.resources,sim.social)
                return [Choice('share','Give one berry',valid,'' if valid else 'You need a berry and your neighbor needs room.'),Choice('refuse','Sorry, I cannot'),Choice('goodbye','Leave conversation')]
            valid=validate(self.incoming.action,b,sim.world,sim.resources,sim.social)
            reason='There is no room for the offered berry.' if self.incoming.action.kind==ActionType.OFFER_FOOD else 'This invitation is no longer available.'
            return [Choice('accept','Listen / accept invitation',valid,'' if valid else reason),Choice('decline','Not right now')]
        # Keep an active visit bounded without discarding unread or persisted turns.
        session=self.session(sim)
        if session is None:return []
        if len(session.turns)>=60:
            return [Choice('goodbye',"Let us continue another time")]
        result=[]
        for key,label,kind in (('smalltalk','Small talk',ActionType.TALK),('request','Ask for berries',ActionType.REQUEST_FOOD),('offer','Offer one berry',ActionType.OFFER_FOOD),('how',"How are you doing?",ActionType.TALK)):
            action=Action(kind,b.id);reason=sim.social.rejection_reason(action,a)
            if reason=='food unavailable or recipient inventory full':reason='You need a berry and your neighbor needs room.'
            result.append(Choice(key,label,reason is None,reason or ''))
        if b.hunger>=sim.survival.hungry:result.append(Choice('need_food','Do you need food?'))
        memories=sim.social.relevant_memories(a,{b.id})
        if any(m['actor_id']==b.id and m['target_id']==a.id and m['result'] in ('shared one food','offered one food') for m in memories):
            result.append(Choice('thank_help','Thank you for helping me'))
        result.append(Choice('goodbye','Goodbye'))
        return result

    def choose(self,key,sim):
        choice=next((c for c in self.choices(sim) if c.key==key),None)
        if not choice or not choice.enabled:return False
        a,b=self.actors(sim)
        if key=='goodbye':self.close(sim);return True
        if key=='decline':
            prompt=self.incoming;self.incoming=None
            sim.player.decline(sim,prompt,'Player declined invitation');self.close(sim,canceled=True);return True
        action=None;actor=a;topic=key
        if self.incoming:
            prompt=self.incoming;self.incoming=None
            if key in ('share','refuse'):
                action=Action(ActionType.SHARE_FOOD if key=='share' else ActionType.REFUSE_REQUEST,b.id,request_id=prompt.request_id)
            else:actor=b;action=prompt.action
        else:
            action=Action({'request':ActionType.REQUEST_FOOD,'offer':ActionType.OFFER_FOOD}.get(key,ActionType.TALK),b.id)
        self.current=None;self.queue.clear();self.waiting=False
        if not self.start(sim,actor,action,topic):
            self.close(sim,canceled=True);return False
        return True

    def close(self,sim,canceled=False,reason='Player left conversation'):
        if self.social_ref is sim.social:
            session=self.session(sim)
            if session:
                if canceled or self.owner or session.request_id in sim.social.pending:
                    sim.social.cancel_session(session.id,reason)
                elif session.state not in (SessionState.CANCELED,SessionState.COMPLETED):sim.social.complete_session(session)
            sim.social.modal_pair=None;sim.social.modal_topic='greeting'
            if sim.player:
                sim.player.clear()
                sim.player.message='Conversation canceled; unfinished exchanges were not completed.' if canceled else 'Conversation ended.'
            for key in (self.player_id,self.peer_id):
                actor=sim.social.agents.get(key)
                if actor:
                    if hasattr(sim.decision_provider,'interrupt'):sim.decision_provider.interrupt(actor,'Player dialogue ended',sim.tick)
            self.flush(sim)
        self.reset();self.serial+=1
