"""Validated social interactions, directed relationships, and bounded memories."""
from dataclasses import asdict, dataclass
import json
import random
import math
import os
from pathlib import Path
import tempfile
from .dialogue import SocialSettings, SessionState, InteractionSession, DialogueTurn, choose_line


@dataclass(frozen=True)
class Memory:
    tick: int
    actor_id: str
    target_id: str
    action: str
    result: str
    trust_delta: int


@dataclass(frozen=True)
class FoodRequest:
    id: str
    requester_id: str
    recipient_id: str
    created_tick: int
    expires_tick: int
    urgent: bool
    session_id: str | None = None


class SocialSystem:
    memory_limit = 20
    request_lifetime = 12
    interaction_range = 1

    def __init__(self, agents, memory_enabled=True, memory_path=None, seed=42, settings=None):
        self.agents = {a.id: a for a in agents}
        self.memory_enabled = memory_enabled
        self.memory_path = Path(memory_path) if memory_path else None
        self.pending: dict[str, FoodRequest] = {}
        self.pacing = None
        self.settings = settings or SocialSettings()
        self.dialogue_rng = random.Random(f'{seed}:authored-dialogue')
        self.sessions = {}
        self.active_sessions = {}
        self.session_sequence = 0
        self.pair_cooldowns = {}
        self.request_cooldowns = {}
        self.agent_cooldowns = {}
        self.repeated_lines = {}
        self.last_pair_end = {}
        self.events = []
        self.tick = 0
        self.session_tick = 0
        self.offset = 0
        self.sequence = 0
        self.persistence_status = "in-memory"
        self.load_failed = False
        for agent in agents:
            agent.trust = {other.id: 0 for other in agents if other.id != agent.id}
        if self.memory_path:
            self.load()

    def nearby(self, first, second):
        return sum(abs(a-b) for a, b in zip(first.position, second.position)) <= self.interaction_range

    def advance(self, tick):
        self.session_tick = tick
        self.tick = self.offset + tick
        for session in list(self.sessions.values()):
            if session.state in (SessionState.COMPLETED, SessionState.CANCELED):
                continue
            actors = [self.agents[key] for key in session.participants]
            if any(a.incapacitated_until for a in actors):
                self.cancel_session(session.id, 'partner recovering')
                continue
            if session.state in (SessionState.PROPOSED, SessionState.APPROACHING):
                if not all(self.available(a,session,session.purpose in ("request_food","offer_food","share_food","refuse_request")) for a in actors):
                    self.cancel_session(session.id,"partner became unavailable")
                    continue
                if self.tick >= session.deadline:
                    self.cancel_session(session.id, 'approach timed out')
                continue
            urgent = any(a.energy <= self.pacing.survival.rest_energy or
                         (a.hunger >= self.pacing.survival.inefficient_hunger and a.food > 0)
                         for a in actors) if self.pacing else False
            if not self.nearby(*actors) or urgent:
                self.cancel_session(session.id, 'separated or urgent survival need')
                continue
            self.deliver_turns(session)
            if session.state == SessionState.RESOLVING and self.tick >= session.finish_tick:
                self.complete_session(session)
        for request in list(self.pending.values()):
            if self.tick >= request.expires_tick:
                del self.pending[request.id]
                self.record(request.requester_id, request.recipient_id, "REQUEST_FOOD", "expired",
                            {}, request.id)
                if request.session_id:
                    self.cancel_session(request.session_id, "request expired")

    def session_for(self, actor):
        key = self.active_sessions.get(actor.id)
        return self.sessions.get(key)

    def engaged(self, actor):
        session = self.session_for(actor)
        return bool(session and session.state in (SessionState.ENGAGED, SessionState.WAITING_FOR_PARTNER, SessionState.RESOLVING))

    def waiting_partner(self, actor):
        session = self.session_for(actor)
        return bool(session and session.state == SessionState.APPROACHING
                    and session.recipient_id == actor.id and self.available(actor,session))

    def needs_response(self, actor):
        return any(r.recipient_id == actor.id for r in self.active_requests(actor))

    def available(self, actor, session=None, essential=False):
        if actor.incapacitated_until:
            return False
        active = self.session_for(actor)
        if active and (session is None or active.id != session.id):
            return False
        if self.pacing:
            owner = self.pacing.locks.get(actor.id)
            job = self.pacing.jobs.get(owner)
            if job and (not session or job.session_id != session.id):
                return False
            if not essential and (actor.energy <= self.pacing.survival.rest_energy or actor.hunger >= self.pacing.survival.inefficient_hunger):
                return False
        return True

    def cooldown_reason(self, actor, other, kind):
        answering = kind in ('SHARE_FOOD', 'REFUSE_REQUEST')
        if answering:
            return None
        emergency = kind == 'REQUEST_FOOD' and actor.hunger >= 85 and actor.food == 0
        floor = 40 if emergency else 0
        limits = [self.agent_cooldowns.get(actor.id, 0), self.agent_cooldowns.get(other.id, 0),
                  self.pair_cooldowns.get(tuple(sorted((actor.id, other.id))), 0)]
        if kind == 'REQUEST_FOOD':
            limits.append(self.request_cooldowns.get((actor.id, other.id), 0))
        if emergency:
            last_end = max(self.last_pair_end.get(tuple(sorted((actor.id,other.id))), -10000),
                           self.request_cooldowns.get((actor.id,other.id),-10000)-self.settings.request_retry_ticks)
            limits = [min(value,last_end+floor) for value in limits]
        return 'social cooldown' if self.tick < max(limits, default=0) else None

    def transition(self, session, state, reason=''):
        if session.state == state:
            return
        previous = session.state
        session.state = state
        self.events.append({'tick':self.session_tick, 'action':'SESSION', 'session_id':session.id,
                            'actor_id':session.initiator_id, 'target_id':session.recipient_id,
                            'previous':previous.value, 'state':state.value, 'reason':reason, 'purpose':session.purpose})

    def propose(self, actor, other_id, purpose, world):
        other = self.agents.get(other_id)
        kind = purpose.upper() if purpose.upper() in ("REQUEST_FOOD","OFFER_FOOD","SHARE_FOOD","REFUSE_REQUEST") else "TALK"
        essential = kind != "TALK"
        if other is None or other is actor or not self.available(actor,essential=essential) or not self.available(other,essential=essential):
            return None
        if self.cooldown_reason(actor, other, kind):
            return None
        if not world.path(actor.position, other.position) and not self.nearby(actor, other):
            return None
        self.session_sequence += 1
        session = InteractionSession(f'session-{self.session_sequence}', actor.id, other.id, purpose,
                                     SessionState.PROPOSED, self.tick, self.tick+self.settings.approach_timeout_ticks,
                                     target_position=other.position)
        self.sessions[session.id] = session
        self.active_sessions[actor.id] = self.active_sessions[other.id] = session.id
        self.transition(session, SessionState.APPROACHING)
        self.trim_sessions()
        return session

    def trim_sessions(self):
        inactive = [key for key,s in self.sessions.items() if s.state in (SessionState.COMPLETED,SessionState.CANCELED)]
        for key in inactive[:-60]:
            del self.sessions[key]

    def add_turn(self, session, speaker, partner, purpose, due, essential=True, instant=False):
        text = choose_line(self, speaker, partner, purpose, essential)
        if text is None:
            return due
        seconds = self.settings.reading_seconds(text)
        duration = 0 if instant else math.ceil(seconds/.25)
        session.turns.append(DialogueTurn(speaker.id,text,due,duration,purpose=purpose))
        return due+duration

    def deliver_turns(self, session):
        if (session.state not in (SessionState.ENGAGED,SessionState.RESOLVING)
                or any(self.active_sessions.get(key)!=session.id for key in session.participants)
                or not self.nearby(*(self.agents[key] for key in session.participants))):
            return
        for index,turn in enumerate(session.turns):
            if turn.delivered or turn.due_tick > self.tick:
                continue
            turn.delivered = True
            session.current_turn = index
            partner = next(key for key in session.participants if key != turn.speaker_id)
            self.repeated_lines[(turn.speaker_id,partner,turn.text)] = self.tick
            self.events.append({'tick':self.session_tick, 'action':'DIALOGUE', 'session_id':session.id,
                                'actor_id':turn.speaker_id, 'target_id':partner, 'turn':index,
                                'text':turn.text, 'purpose':turn.purpose, 'source':'authored offline', 'session_validated':True,
                                'reading_seconds':self.settings.reading_seconds(turn.text),
                                'speaker_position':self.agents[turn.speaker_id].position,
                                'partner_position':self.agents[partner].position})

    def begin_session(self, action, actor, world, instant=False):
        other = self.agents[action.target]
        session = self.session_for(actor)
        if session is None:
            session = self.propose(actor, other.id, action.kind.value.lower(), world)
        if session is None or set(session.participants) != {actor.id,other.id}:
            return None, 0
        self.transition(session, SessionState.ENGAGED)
        kind = action.kind.value
        duration_end = self.tick
        if kind == 'TALK':
            purpose = 'campfire' if session.purpose == 'campfire' else 'greeting'
            duration_end = self.add_turn(session, actor, other, purpose, self.tick, False, instant)
            duration_end = self.add_turn(session, other, actor, 'reply', duration_end, False, instant)
        elif kind == 'REQUEST_FOOD':
            duration_end = self.add_turn(session, actor, other, 'question', self.tick, True, instant)
        elif kind == 'OFFER_FOOD':
            duration_end = self.add_turn(session, actor, other, 'offer', self.tick, True, instant)
        else:
            duration_end = self.add_turn(session, actor, other, 'consider', self.tick, True, instant)
        self.deliver_turns(session)
        return session, duration_end-self.tick

    def resolve_session(self, session, actor, other, result, instant=False):
        session.outcome = result
        self.transition(session, SessionState.RESOLVING)
        due = self.tick
        if result in ('shared one food','offered one food'):
            due = self.add_turn(session,actor,other,'shared',due,True,instant)
            due = self.add_turn(session,other,actor,'thanks',due,True,instant)
        elif result == 'refused':
            due = self.add_turn(session,actor,other,'refusal',due,True,instant)
            due = self.add_turn(session,other,actor,'acknowledge',due,True,instant)
        session.finish_tick = due
        self.deliver_turns(session)
        if instant or due <= self.tick:
            self.complete_session(session)

    def complete_session(self, session):
        self.transition(session, SessionState.COMPLETED, session.outcome or 'completed')
        self.release_session(session)

    def release_session(self, session):
        pair = tuple(sorted(session.participants))
        spoken = any(turn.delivered for turn in session.turns)
        self.last_pair_end[pair] = self.tick
        self.pair_cooldowns[pair] = max(self.pair_cooldowns.get(pair,0), self.tick+(self.settings.pair_cooldown_ticks if spoken else 8))
        for key in session.participants:
            if self.active_sessions.get(key) == session.id:
                del self.active_sessions[key]
            self.agent_cooldowns[key] = max(self.agent_cooldowns.get(key,0), self.tick+(self.settings.agent_cooldown_ticks if spoken else 4))
        session.cooldown_until = self.pair_cooldowns[pair]

    def cancel_session(self, session_id, reason):
        session = self.sessions.get(session_id)
        if session is None or session.state in (SessionState.COMPLETED,SessionState.CANCELED):
            return
        session.outcome = reason
        self.transition(session,SessionState.CANCELED,reason)
        self.release_session(session)
        if self.pacing:
            for owner,job in list(self.pacing.jobs.items()):
                if job.session_id == session_id:
                    self.pacing.release(owner,cancel_social=False)
        for request in list(self.pending.values()):
            if request.session_id == session_id:
                del self.pending[request.id]
                self.record(request.requester_id,request.recipient_id,'REQUEST_FOOD','canceled: '+reason,{},request.id)

    def serious_dispute(self, actor, peer_id):
        return any(m['action']=='REFUSE_REQUEST' and m['trust_delta'] <= -4
                   and self.tick-m['tick'] < self.settings.avoid_ticks
                   for m in self.relevant_memories(actor,{peer_id}))

    def cancel_for(self, agent):
        session = self.session_for(agent)
        if session:
            self.cancel_session(session.id, 'partner recovering')
        for request in list(self.active_requests(agent)):
            del self.pending[request.id]
            self.record(request.requester_id, request.recipient_id, "REQUEST_FOOD",
                        "cancelled: incapacitated", {}, request.id)

    def trust_for(self, agent, other_id):
        return agent.trust.get(other_id, 0) if self.memory_enabled else 0

    def relevant_memories(self, agent, other_ids, limit=6):
        if not self.memory_enabled:
            return []
        return [asdict(m) for m in agent.memories
                if (m.target_id if m.actor_id == agent.id else m.actor_id) in other_ids][-limit:]

    def active_requests(self, agent):
        return [r for r in self.pending.values()
                if agent.id in (r.requester_id, r.recipient_id) and self.tick < r.expires_tick]

    def rejection_reason(self, action, agent):
        if self.agents.get(agent.id) is not agent:
            return "invalid acting NPC"
        if action.request_id is not None and not isinstance(action.request_id, str):
            return "invalid request ID"
        other = self.agents.get(action.target) if isinstance(action.target, str) else None
        if other is None or other.id == agent.id:
            return "invalid NPC target"
        if agent.incapacitated_until or other.incapacitated_until:
            return "NPC temporarily incapacitated"
        if not self.nearby(agent, other):
            return "NPC out of interaction range"
        session = self.session_for(agent)
        essential = action.kind.value != 'TALK'
        if session and set(session.participants) != {agent.id,other.id}:
            return 'conflicting conversation'
        if not self.available(agent,session,essential) or not self.available(other,session,essential):
            return 'partner busy or needs rest'
        if self.cooldown_reason(agent,other,action.kind.value):
            return 'social cooldown'
        if self.pacing and not self.pacing.allowed_social(action, agent):
            return "conversation busy or cooling down"
        kind = action.kind.value
        if kind in ("SHARE_FOOD", "REFUSE_REQUEST"):
            request = self.pending.get(action.request_id)
            if (not request or request.recipient_id != agent.id or request.requester_id != other.id
                    or self.tick >= request.expires_tick):
                return "request unavailable or expired"
            if kind == "SHARE_FOOD" and (agent.food <= 0 or other.inventory.used >= other.inventory.capacity):
                return "food unavailable or recipient inventory full"
        elif action.request_id is not None:
            return "unexpected request ID"
        if kind == "OFFER_FOOD" and (agent.food <= 0 or other.inventory.used >= other.inventory.capacity):
            return "food unavailable or recipient inventory full"
        if kind == "REQUEST_FOOD":
            if agent.inventory.used >= agent.inventory.capacity:
                return "requester inventory full"
            if any(r.requester_id == agent.id and r.recipient_id == other.id
                   for r in self.active_requests(agent)):
                return "duplicate active request"
        return None

    def perform(self, action, agent):
        """Called only after shared action validation on the simulation thread."""
        kind, other_id = action.kind.value, action.target
        session = self.session_for(agent)
        instant = self.pacing is None or self.pacing.timing.duration(action) == 0
        if kind == "REQUEST_FOOD":
            self.sequence += 1
            request = FoodRequest(f"request-{self.sequence}", agent.id, other_id,
                                  self.tick, self.tick+max(self.request_lifetime,self.settings.response_timeout_ticks), agent.hunger >= 70,
                                  session.id if session else None)
            self.pending[request.id] = request
            self.request_cooldowns[(agent.id,other_id)] = self.tick+self.settings.request_retry_ticks
            if session:
                session.request_id = request.id
                self.transition(session,SessionState.WAITING_FOR_PARTNER)
            self.record(agent.id, other_id, kind, "pending", {}, request.id)
        elif kind in ("SHARE_FOOD", "REFUSE_REQUEST"):
            del self.pending[action.request_id]
            if kind == "SHARE_FOOD":
                agent.inventory.transfer_to(self.agents[other_id].inventory, "berries")
                self.record(agent.id, other_id, kind, "shared one food",
                            {other_id: 14 if self.agents[other_id].hunger >= 85 else 6, agent.id: 2}, action.request_id)
            else:
                self.record(agent.id, other_id, kind, "refused",
                            {other_id: -4 if self.agents[other_id].hunger >= 85 and agent.food >= 2 else -2 if agent.food else 0}, action.request_id)
        elif kind == "OFFER_FOOD":
            agent.inventory.transfer_to(self.agents[other_id].inventory, "berries")
            self.record(agent.id,other_id,kind,'offered one food',
                        {other_id:14 if self.agents[other_id].hunger>=85 else 6,agent.id:2})
        elif kind == "TALK":
            self.record(agent.id, other_id, kind, "greeted", {agent.id: 1, other_id: 1})
        if session and kind != 'REQUEST_FOOD':
            result = {'SHARE_FOOD':'shared one food','OFFER_FOOD':'offered one food','REFUSE_REQUEST':'refused','TALK':'greeted'}[kind]
            self.resolve_session(session,agent,self.agents[other_id],result,instant)

    def record(self, actor_id, target_id, action, result, changes, request_id=None):
        effects = {}
        for owner_id in (actor_id, target_id):
            owner = self.agents[owner_id]
            partner = target_id if owner_id == actor_id else actor_id
            before = owner.trust.get(partner, 0)
            delta = changes.get(owner_id, 0)
            if delta > 0:
                delta = max(1, round(delta*owner.personality.get("trust_gain_rate", 1.0)))
            after = max(-100, min(100, before+delta))
            owner.trust[partner] = after
            effects[owner_id] = after-before
            owner.memories.append(Memory(self.tick, actor_id, target_id, action, result, after-before))
            del owner.memories[:-self.memory_limit]
        self.events.append({"tick": self.session_tick, "social_tick": self.tick, "agent": self.agents[actor_id].name,
                            "actor_id": actor_id, "target_id": target_id,
                            "action": action, "result": result, "trust_changes": effects,
                            "session_id": self.active_sessions.get(actor_id),
                            "request_id": request_id, "memory_created_for": [actor_id, target_id], "social": True})

    def reject(self, action, agent):
        reason = self.rejection_reason(action, agent)
        other = self.agents.get(action.target) if isinstance(action.target, str) else None
        if other and other.id != agent.id:
            self.record(agent.id, other.id, action.kind.value, f"failed: {reason}", {}, action.request_id)
        else:
            self.events.append({"tick": self.session_tick, "social_tick": self.tick, "agent": agent.name, "actor_id": agent.id,
                                "action": action.kind.value, "result": "failed: invalid NPC target",
                                "social": True})

    def load(self):
        path = self.memory_path
        try:
            if not path.exists():
                self.persistence_status = "new history"
                return
            data = json.loads(path.read_text())
            if data["version"] != 1 or type(data["tick"]) is not int or data["tick"] < 0:
                raise ValueError("Invalid history header")
            if type(data["sequence"]) is not int or data["sequence"] < 0:
                raise ValueError("Invalid request sequence")
            if set(data["agents"]) != set(self.agents):
                raise ValueError("History roster mismatch")
            restored = {}
            for owner_id, entry in data["agents"].items():
                if set(entry["trust"]) != set(self.agents)-{owner_id}:
                    raise ValueError("Invalid relationships")
                if any(type(v) is not int or not -100 <= v <= 100 for v in entry["trust"].values()):
                    raise ValueError("Invalid trust value")
                if not isinstance(entry["memories"], list):
                    raise ValueError("Invalid memories")
                memories = []
                for raw in entry["memories"][-self.memory_limit:]:
                    memory = Memory(**raw)
                    if (type(memory.tick) is not int or not 0 <= memory.tick <= data["tick"]
                            or memory.actor_id not in self.agents or memory.target_id not in self.agents
                            or memory.actor_id == memory.target_id
                            or owner_id not in (memory.actor_id, memory.target_id)
                            or memory.action not in {"REQUEST_FOOD", "SHARE_FOOD", "REFUSE_REQUEST", "TALK", "OFFER_FOOD"}
                            or not isinstance(memory.result, str) or len(memory.result) > 100
                            or type(memory.trust_delta) is not int or not -200 <= memory.trust_delta <= 200):
                        raise ValueError("Invalid memory record")
                    memories.append(memory)
                restored[owner_id] = (entry["trust"], memories)
            # Apply only after the entire file has passed validation.
            for owner_id, (trust, memories) in restored.items():
                self.agents[owner_id].trust = trust.copy()
                self.agents[owner_id].memories = memories
            self.offset = self.tick = data["tick"]
            self.sequence = data["sequence"]
            self.persistence_status = "loaded"
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            self.load_failed = True
            self.persistence_status = "load failed; original file preserved"

    def save(self):
        if not self.memory_path or self.load_failed:
            return
        temporary = None
        try:
            self.memory_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"version": 1, "tick": self.tick, "sequence": self.sequence,
                       "agents": {a.id: {"trust": a.trust, "memories": [asdict(m) for m in a.memories]}
                                  for a in self.agents.values()}}
            with tempfile.NamedTemporaryFile(mode="w", dir=self.memory_path.parent,
                                             prefix=".social-", delete=False) as stream:
                temporary = stream.name
                json.dump(payload, stream, sort_keys=True, indent=2)
            os.replace(temporary, self.memory_path)
            self.persistence_status = "saved"
        except OSError:
            self.persistence_status = "save failed"
        finally:
            if temporary and os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    self.persistence_status = "save failed"

    def close(self):
        for session in list(self.sessions.values()):
            self.cancel_session(session.id,"session ended")
        for request in list(self.pending.values()):
            self.record(request.requester_id, request.recipient_id, "REQUEST_FOOD", "session ended",
                        {}, request.id)
        self.pending.clear()
        self.save()
