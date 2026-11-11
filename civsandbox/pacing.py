"""Gameplay timers use fixed simulation ticks, never wall-clock sleeps."""
from dataclasses import dataclass
from .survival import SurvivalRules
from .occupancy import Occupancy
from .wildlife import distance
from .actions import Action, ActionType, SOCIAL_ACTIONS, validate, execute


@dataclass(frozen=True)
class ActionTiming:
    needs_interval_ticks: int = 4
    gather_ticks: int = 14
    eat_ticks: int = 10
    greeting_ticks: int = 8
    request_ticks: int = 8
    response_ticks: int = 10
    social_cooldown_ticks: int = 40
    rest_ticks: int = 4
    cook_ticks: int = 20
    hunger_interval_multiplier: int = 3

    def __post_init__(self):
        if self.needs_interval_ticks < 1 or self.hunger_interval_multiplier < 1:
            raise ValueError("Needs interval must be positive")
        if any(type(value) is not int or value < 0 for value in self.__dict__.values()):
            raise ValueError("Action timing values must be nonnegative integers")

    def duration(self, action):
        return {ActionType.OFFER_FOOD: self.response_ticks, ActionType.COOK: self.cook_ticks, ActionType.REST: self.rest_ticks, ActionType.GATHER: self.gather_ticks, ActionType.EAT: self.eat_ticks,
                ActionType.TALK: self.greeting_ticks, ActionType.REQUEST_FOOD: self.request_ticks,
                ActionType.SHARE_FOOD: self.response_ticks,
                ActionType.REFUSE_REQUEST: self.response_ticks}.get(action.kind, 0)

    @classmethod
    def instant(cls):
        return cls(1, 0, 0, 0, 0, 0, 0, 0, 0, 1)


@dataclass
class InProgress:
    action: object
    finish_tick: int
    source: str
    participants: tuple[str, ...]
    duration_ticks: int
    session_id: str | None = None


class ActionProgress:
    def __init__(self, timing, social, survival=None, occupancy=None):
        self.timing, self.social = timing, social
        self.survival = survival or SurvivalRules()
        self.occupancy = occupancy or Occupancy()
        self.wildlife = None
        self.cooking_station = None
        self.duration_ticks = 0
        self.jobs = {}
        self.locks = {}
        self.cooldowns = {}
        self.sources = {}
        self.started = False
        self.completed = False
        self.session_id = None

    def duration_for(self, action, actor):
        multiplier = self.survival.hunger_slowdown if action.kind == ActionType.GATHER and actor.hunger >= self.survival.inefficient_hunger else 1
        return self.timing.duration(action)*multiplier

    def cancel_for(self, actor_id):
        owner = self.locks.get(actor_id)
        if owner in self.jobs:
            self.release(owner)

    def allowed_social(self, action, actor):
        if any(self.locks.get(key, actor.id) != actor.id for key in (actor.id, action.target)):
            return False
        answering = action.kind in (ActionType.SHARE_FOOD, ActionType.REFUSE_REQUEST)
        emergency = action.kind == ActionType.REQUEST_FOOD and actor.hunger >= 85 and actor.food == 0
        if not answering and not emergency and self.social.tick < max(self.cooldowns.get(actor.id, 0), self.cooldowns.get(action.target, 0)):
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
        return actor.id in self.locks or self.waiting_for_response(actor) or self.social.engaged(actor) or self.social.waiting_partner(actor)

    def execute(self, action, actor, world, resources, tick, source):
        self.started = self.completed = False
        self.session_id = None
        self.duration_ticks = 0
        job = self.jobs.get(actor.id)
        if job:
            self.session_id = job.session_id
            if job.action.kind == ActionType.HUNT:
                return self.advance_hunt(job, actor, world, resources, tick)
            self.duration_ticks = job.duration_ticks
            self.sources[actor.id] = job.source
            if tick < job.finish_tick:
                actor.current_action = job.action.kind.value
                return True
            action = job.action
            # Keep reservations through final validation and execution.
            success = execute(action, actor, world, resources, tick, self.social)
            self.release(actor.id, cancel_social=not success)
            self.completed = success
            if action.kind in SOCIAL_ACTIONS:
                for member in job.participants:
                    self.cooldowns[member] = self.social.tick+self.social.settings.agent_cooldown_ticks
            return success
        self.sources[actor.id] = source
        if self.held(actor) and not (self.social.needs_response(actor) and action.kind in (ActionType.SHARE_FOOD,ActionType.REFUSE_REQUEST,ActionType.EAT,ActionType.REST)):
            actor.current_action = "WAIT"
            return True
        if self.social.active_requests(actor) and action.kind == ActionType.MOVE_TO:
            actor.current_action = "WAIT"
            return True
        if not validate(action, actor, world, resources, self.social):
            return False
        if action.kind == ActionType.HUNT:
            self.wildlife = resources.wildlife
            self.wildlife.begin(actor, action.target)
            duration = self.duration_ticks = self.wildlife.settings.chase_ticks
            self.jobs[actor.id] = InProgress(action, tick+duration, source, (actor.id,), duration)
            self.locks[actor.id] = actor.id
            actor.current_action = "HUNT"
            self.started = True
            return True
        duration = self.duration_for(action, actor)
        session = None
        if action.kind in SOCIAL_ACTIONS:
            session, logical_duration = self.social.begin_session(action,actor,world,instant=duration==0)
            if session is None:
                return False
            duration = max(duration,logical_duration)
            self.session_id = session.id
        self.duration_ticks = duration
        if action.kind == ActionType.COOK:
            self.cooking_station = resources.cooking_station
            self.cooking_station.reserve(actor, tick, duration)
        if duration == 0:
            self.completed = execute(action, actor, world, resources, tick, self.social)
            return self.completed
        participants = (actor.id, action.target) if action.kind in SOCIAL_ACTIONS else (actor.id,)
        self.jobs[actor.id] = InProgress(action, tick+duration, source, participants, duration, session.id if session else None)
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

    def advance_hunt(self, job, actor, world, resources, tick):
        wildlife = self.wildlife
        pursuit = wildlife.pursuits.get(actor.id)
        self.sources[actor.id] = job.source
        self.duration_ticks = job.duration_ticks
        reason = None
        if pursuit is None or tick >= pursuit.deadline:
            reason = "pursuit timed out"
        elif not validate(job.action, actor, world, resources, self.social):
            reason = "target or hunter no longer eligible"
        elif actor.energy <= max(self.survival.rest_energy, wildlife.settings.minimum_energy):
            reason = "rest needed"
        elif actor.food and actor.hunger >= 30:
            reason = "carried berries take priority"
        elif (pursuit.steps >= wildlife.settings.chase_steps
              and distance(actor.position, wildlife.chickens[job.action.target].position) > 1):
            reason = "pursuit distance limit"
        if reason:
            wildlife.abort(actor.id, reason)
            self.release(actor.id)
            actor.current_action, actor.goal = "WAIT", None
            return True  # an ordinary failed pursuit, not an invalid world mutation
        chicken = wildlife.chickens[job.action.target]
        if distance(actor.position, chicken.position) <= 1:
            if not pursuit.catch_ready_tick:
                pursuit.catch_ready_tick = tick+wildlife.settings.catch_ticks
            dx, dy = chicken.position[0]-actor.position[0], chicken.position[1]-actor.position[1]
            actor.facing = ("right" if dx >= 0 else "left") if dx else ("down" if dy >= 0 else "up")
            if tick >= pursuit.catch_ready_tick:
                self.completed = execute(job.action, actor, world, resources, tick, self.social)
                self.release(actor.id)
                actor.goal = None
                self.duration_ticks = 0
                return self.completed
        else:
            pursuit.catch_ready_tick = 0
            routes = [(len(route), p) for p in world.neighbors(chicken.position)
                      if (route := world.path(actor.position, p))]
            if not routes:
                wildlife.abort(actor.id, "target unreachable")
                self.release(actor.id)
                actor.current_action, actor.goal = "WAIT", None
                return True
            slowed = actor.hunger >= self.survival.inefficient_hunger and tick % self.survival.hunger_slowdown
            if not slowed:
                extra = [c.position for c in wildlife.living()]
                step = self.occupancy.next_step(actor, min(routes)[1], world,
                                                self.social.agents.values(), extra)
                if step is not None:
                    move = Action(ActionType.MOVE_TO, step)
                    if execute(move, actor, world, resources, tick, self.social):
                        pursuit.steps += 1
        actor.current_action = "HUNT"
        return True

    def release(self, actor_id, cancel_social=True):
        job = self.jobs.pop(actor_id)
        if job.session_id and cancel_social:
            self.social.cancel_session(job.session_id,"activity interrupted")
        if job.action.kind == ActionType.COOK and self.cooking_station:
            self.cooking_station.release(actor_id)
        if job.action.kind == ActionType.HUNT and self.wildlife:
            self.wildlife.abort(actor_id, "activity cancelled")
        for member in job.participants:
            self.locks.pop(member, None)

    def cancel_all(self):
        for actor_id in list(self.jobs):
            self.release(actor_id)
