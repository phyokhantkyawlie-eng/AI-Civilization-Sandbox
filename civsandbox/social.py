"""Validated social interactions, directed relationships, and bounded memories."""
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile


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


class SocialSystem:
    memory_limit = 20
    request_lifetime = 12
    interaction_range = 1

    def __init__(self, agents, memory_enabled=True, memory_path=None):
        self.agents = {a.id: a for a in agents}
        self.memory_enabled = memory_enabled
        self.memory_path = Path(memory_path) if memory_path else None
        self.pending: dict[str, FoodRequest] = {}
        self.pacing = None
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
        for request in list(self.pending.values()):
            if self.tick >= request.expires_tick:
                del self.pending[request.id]
                self.record(request.requester_id, request.recipient_id, "REQUEST_FOOD", "expired",
                            {request.requester_id: -2}, request.id)

    def cancel_for(self, agent):
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
        if kind == "REQUEST_FOOD":
            self.sequence += 1
            request = FoodRequest(f"request-{self.sequence}", agent.id, other_id,
                                  self.tick, self.tick+self.request_lifetime, agent.hunger >= 70)
            self.pending[request.id] = request
            self.record(agent.id, other_id, kind, "pending", {}, request.id)
        elif kind in ("SHARE_FOOD", "REFUSE_REQUEST"):
            del self.pending[action.request_id]
            if kind == "SHARE_FOOD":
                agent.inventory.transfer_to(self.agents[other_id].inventory, "berries")
                self.record(agent.id, other_id, kind, "shared one food",
                            {other_id: 12, agent.id: 2}, action.request_id)
            else:
                self.record(agent.id, other_id, kind, "refused", {other_id: -8}, action.request_id)
        elif kind == "TALK":
            self.record(agent.id, other_id, kind, "greeted", {agent.id: 1, other_id: 2})

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
                            or memory.action not in {"REQUEST_FOOD", "SHARE_FOOD", "REFUSE_REQUEST", "TALK"}
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
        for request in list(self.pending.values()):
            self.record(request.requester_id, request.recipient_id, "REQUEST_FOOD", "session ended",
                        {}, request.id)
        self.pending.clear()
        self.save()
