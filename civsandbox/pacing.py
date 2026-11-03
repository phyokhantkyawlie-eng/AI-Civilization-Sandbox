"""Gameplay timers use fixed simulation ticks, never wall-clock sleeps."""
from dataclasses import dataclass
from .actions import ActionType, SOCIAL_ACTIONS, validate, execute


@dataclass(frozen=True)
class ActionTiming:
    needs_interval_ticks: int = 4
    gather_ticks: int = 14
    eat_ticks: int = 10
    greeting_ticks: int = 8
    request_ticks: int = 8
    response_ticks: int = 10
    social_cooldown_ticks: int = 40

    def __post_init__(self):
        if self.needs_interval_ticks < 1:
            raise ValueError("Needs interval must be positive")
        if any(type(value) is not int or value < 0 for value in self.__dict__.values()):
            raise ValueError("Action timing values must be nonnegative integers")

    def duration(self, action):
        return {ActionType.GATHER: self.gather_ticks, ActionType.EAT: self.eat_ticks,
                ActionType.TALK: self.greeting_ticks, ActionType.REQUEST_FOOD: self.request_ticks,
                ActionType.SHARE_FOOD: self.response_ticks,
                ActionType.REFUSE_REQUEST: self.response_ticks}.get(action.kind, 0)

    @classmethod
    def instant(cls):
        return cls(1, 0, 0, 0, 0, 0, 0)


@dataclass
class InProgress:
    action: object
    finish_tick: int
    source: str
    participants: tuple[str, ...]


class ActionProgress:
    def __init__(self, timing, social):
        self.timing, self.social = timing, social
        self.jobs = {}
        self.locks = {}
        self.cooldowns = {}
        self.sources = {}
        self.started = False
        self.completed = False

    def allowed_social(self, action, actor):
        if any(self.locks.get(key, actor.id) != actor.id for key in (actor.id, action.target)):
            return False
        answering = action.kind in (ActionType.SHARE_FOOD, ActionType.REFUSE_REQUEST)
        if not answering and self.social.tick < max(self.cooldowns.get(actor.id, 0), self.cooldowns.get(action.target, 0)):
            return False
        # An addressed request reserves the conversation slot until answered/expired.
        for request in self.social.pending.values():
            members = {request.requester_id, request.recipient_id}
            if actor.id in members or action.target in members:
                if not answering or members != {actor.id, action.target}:
                    return False
        return True

    def waiting_for_response(self, actor):
        return any(r.requester_id == actor.id for r in self.social.active_requests(actor))

    def held(self, actor):
        return actor.id in self.locks or self.waiting_for_response(actor)

    def execute(self, action, actor, world, resources, tick, source):
        self.started = self.completed = False
        job = self.jobs.get(actor.id)
        if job:
            self.sources[actor.id] = job.source
            if tick < job.finish_tick:
                actor.current_action = job.action.kind.value
                return True
            action = job.action
            # Keep reservations through final validation and execution.
            success = execute(action, actor, world, resources, tick, self.social)
            self.release(actor.id)
            self.completed = success
            if action.kind in SOCIAL_ACTIONS:
                for member in job.participants:
                    self.cooldowns[member] = self.social.tick+self.timing.social_cooldown_ticks
            return success
        self.sources[actor.id] = source
        if self.held(actor):
            actor.current_action = "WAIT"
            return True
        if self.social.active_requests(actor) and action.kind == ActionType.MOVE_TO:
            actor.current_action = "WAIT"
            return True
        if not validate(action, actor, world, resources, self.social):
            return False
        duration = self.timing.duration(action)
        if duration == 0:
            self.completed = execute(action, actor, world, resources, tick, self.social)
            return self.completed
        participants = (actor.id, action.target) if action.kind in SOCIAL_ACTIONS else (actor.id,)
        self.jobs[actor.id] = InProgress(action, tick+duration, source, participants)
        for member in participants:
            self.locks[member] = actor.id
        if len(participants) == 2:
            other = self.social.agents[action.target]
            dx, dy = other.position[0]-actor.position[0], other.position[1]-actor.position[1]
            actor.facing = ("right" if dx > 0 else "left") if dx else ("down" if dy >= 0 else "up")
            other.facing = {"right": "left", "left": "right", "up": "down", "down": "up"}[actor.facing]
        actor.current_action = action.kind.value
        self.started = True
        return True

    def release(self, actor_id):
        job = self.jobs.pop(actor_id)
        for member in job.participants:
            self.locks.pop(member, None)

    def cancel_all(self):
        for actor_id in list(self.jobs):
            self.release(actor_id)
