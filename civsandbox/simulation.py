"""Deterministic state and fixed-tick scheduling, independent of Pygame."""
import math
import random

from dataclasses import asdict

from .actions import Action, ActionType, SOCIAL_ACTIONS, execute
from .decisions import DecisionProvider, RuleBasedDecisionProvider
from .resources import Resources
from .cooking import place_station
from .inventory import select_food, edible_count
from .wildlife import Wildlife
from .agents import Agent, PERSONALITIES
from .social import SocialSystem
from .world import generate_world, shortage_world
from .characters import CHARACTERS
from .occupancy import Occupancy
from .daynight import DayClock
from .survival import SurvivalRules
from .pacing import ActionProgress, ActionTiming


class Simulation:
    def __init__(self, seed: int = 42, decision_provider: DecisionProvider | None = None,
                 memory_enabled: bool = True, memory_path=None, scenario="default", event_limit=8192, decision_trace_limit=0, timing=None, day_clock=None, survival=None, wildlife_settings=None):
        if scenario not in ("default", "food_shortage"):
            raise ValueError("Unknown scenario")
        self.clock = day_clock or DayClock()
        self.survival = survival or SurvivalRules()
        self.scenario = scenario
        self.seed = seed
        self.rng = random.Random(seed)
        self.world = generate_world(self.rng)
        colors = [(245, 190, 65), (100, 190, 250), (240, 115, 145), (195, 150, 250)]
        self.agents = [Agent(f"npc-{i+1}", name, (2 + i*6, 2), colors[i])
                       for i, name in enumerate(name for name, _ in CHARACTERS.values())]
        for agent, (label, traits) in zip(self.agents, PERSONALITIES):
            agent.personality_name = label
            agent.personality = traits.copy()
        self.social = SocialSystem(self.agents, memory_enabled, memory_path)
        self.occupancy = Occupancy()
        self.progress = ActionProgress(timing or ActionTiming(), self.social, self.survival, self.occupancy)
        self.social.pacing = self.progress
        self.social.request_lifetime = max(12, self.progress.timing.eat_ticks+self.progress.timing.response_ticks+12)
        self._closed = False
        if scenario == "food_shortage":
            self.world = shortage_world(self.world)
            for i, (agent, food, hunger) in enumerate(zip(self.agents, (0, 5, 0, 4), (78, 12, 67, 18))):
                agent.position = (4+i, 2)
                agent.food = food
                agent.hunger = hunger
            self.resources = Resources(self.world, capacity=1, replenish_interval=80)
        else:
            self.resources = Resources(self.world)
        self.world, self.cooking_station = place_station(self.world, self.agents[0].position, {a.position for a in self.agents})
        self.resources.cooking_station = self.cooking_station
        self.wildlife = Wildlife(self.world, self.agents, seed, wildlife_settings, {self.cooking_station.position})
        self.resources.wildlife = self.wildlife
        self.progress.wildlife = self.wildlife
        self.decision_provider = decision_provider or RuleBasedDecisionProvider()
        if hasattr(self.decision_provider, "bind_social"):
            self.decision_provider.bind_social(self.social)
        if hasattr(self.decision_provider, "bind_routines"):
            self.decision_provider.bind_routines(self.clock, self.survival)
        if event_limit is not None and (type(event_limit) is not int or event_limit < 1):
            raise ValueError("event_limit must be positive or None")
        self.decision_trace_limit = decision_trace_limit
        self.decision_trace = []
        self.event_limit = event_limit
        self.events: list[dict] = []
        self._event_sequence = 0
        self.tick = 0
        self.paused = False

    @property
    def time_of_day(self):
        return self.clock.at(self.tick)

    def step(self) -> None:
        if self.paused:
            return
        self.tick += 1
        self.resources.replenish(self.tick)
        self.wildlife.advance(self.tick, self.world, self.agents)
        self.events.extend(self.wildlife.events)
        self.wildlife.events.clear()
        self.social.advance(self.tick)
        hunger_before_tick = {agent.id: agent.hunger for agent in self.agents}
        for agent in self.agents:
            if (self.tick-1) % self.progress.timing.needs_interval_ticks == 0:
                agent.advance_needs()
            transition = self.survival.update(agent, self.tick)
            if transition:
                self.progress.cancel_for(agent.id)
                if hasattr(self.decision_provider, "interrupt"):
                    self.decision_provider.interrupt(agent, "Temporary survival recovery", self.tick)
                if transition == "incapacitated":
                    self.social.cancel_for(agent)
                self.events.append({"tick": self.tick, "agent": agent.name, "actor_id": agent.id,
                                    "action": "SURVIVAL", "result": transition})
        if hasattr(self.decision_provider, "begin_tick"):
            self.decision_provider.begin_tick(self.tick, self.agents)
        for agent in self.agents:
            hunger_before = hunger_before_tick[agent.id]
            hunger_at_decision = agent.hunger
            if self.decision_trace_limit:
                context_summary = {"hunger": agent.hunger, "energy": agent.energy, "food": agent.food,
                                   "position": agent.position, "goal": asdict(agent.goal) if agent.goal else None,
                                   "visible_peers": [a.id for a in self.agents if a.id != agent.id
                                                     and sum(abs(x-y) for x,y in zip(a.position, agent.position)) <= 4],
                                   "memory_enabled": self.social.memory_enabled,
                                   "clock": asdict(self.time_of_day),
                                   "incapacitated": bool(agent.incapacitated_until)}
                if self.social.memory_enabled:
                    peers = set(context_summary["visible_peers"])
                    context_summary["directed_trust"] = {key: self.social.trust_for(agent, key) for key in peers}
                    context_summary["relevant_memory_count"] = len(self.social.relevant_memories(agent, peers))
                context_summary["personality"] = agent.personality.copy()
                context_summary["adjacent_peers"] = [
                    {"id": other.id, "looks_hungry": other.hunger >= self.survival.hungry, "carrying_food": edible_count(other) > 0, "carrying_berries": other.food > 0}
                    for other in self.agents if other.id != agent.id and self.social.nearby(agent, other)]
                context_summary["local_resource_stock"] = sum(
                    stock for position, stock in self.resources.stocks().items()
                    if sum(abs(x-y) for x,y in zip(position, agent.position)) <= 4)
                context_summary["resource_scope"] = (
                    "full map for rule policy" if not hasattr(self.decision_provider, "name") else "local")
            active_job = self.progress.jobs.get(agent.id)
            if active_job and hasattr(self.decision_provider, 'should_interrupt') and self.decision_provider.should_interrupt(agent,active_job.action):
                self.progress.cancel_for(agent.id)
                self.decision_provider.interrupt(agent,'Emergency interrupted an activity',self.tick)
                active_job=None
            if agent.incapacitated_until:
                action = Action(ActionType.REST if agent.energy < 100 else ActionType.WAIT,
                                reasoning="Temporary recovery; resting until able to act.")
            elif active_job:
                action = active_job.action
            elif self.progress.held(agent):
                action = Action(ActionType.WAIT)
            else:
                action = self.decision_provider.decide(agent, self.world, self.resources, self.rng)
            requested_action = action
            proposed_action = action.kind.value if isinstance(action, Action) and isinstance(action.kind, ActionType) else "invalid"
            rejected = False
            requested_target = action.target if isinstance(action, Action) else None
            if isinstance(action, Action) and action.kind == ActionType.MOVE_TO:
                from .actions import validate
                if validate(action, agent, self.world, self.resources, self.social):
                    if agent.hunger >= self.survival.inefficient_hunger and self.tick % self.survival.hunger_slowdown:
                        action = Action(ActionType.WAIT, reasoning="Hunger slows travel.")
                    else:
                        next_position = self.occupancy.next_step(agent, action.target, self.world, self.agents,
                                                                 [c.position for c in self.wildlife.living()])
                        action = Action(ActionType.MOVE_TO, next_position, action.reasoning) if next_position else Action(ActionType.WAIT)
            decision_source = getattr(self.decision_provider, "name", "rule-based")
            status = getattr(self.decision_provider, "status", {}).get(agent.id, {})
            if status.get("fallback"):
                decision_source = "rule-based"
            previous = agent.current_action
            food_item = select_food(agent, action.item) if isinstance(action, Action) and action.kind == ActionType.EAT else None
            if not self.progress.execute(action, agent, self.world, self.resources, self.tick, decision_source):
                rejected = True
                if isinstance(action, Action) and isinstance(action.kind, ActionType) and action.kind in SOCIAL_ACTIONS:
                    self.social.reject(action, agent)
                self.events.append({"tick": self.tick, "agent": agent.name,
                                    "action": "REJECTED", "reason": "action failed execution validation"})
                agent.goal = None
                action = Action(ActionType.WAIT)
                execute(action, agent, self.world, self.resources, self.tick, self.social)
            if hasattr(self.decision_provider,'on_action_result') and isinstance(requested_action,Action):
                pursuit_failed=(requested_action.kind==ActionType.HUNT and not self.progress.started
                                and not self.progress.completed and agent.id not in self.progress.jobs)
                self.decision_provider.on_action_result(agent,requested_action,self.progress.completed,
                                                        rejected or pursuit_failed,self.tick)
            # Record all executed actions; the UI filters repeated movement/wait.
            self.events.append({"tick": self.tick, "agent": agent.name,
                                "action": ("ACTIVITY" if agent.current_action in ("GATHER", "HUNT", "COOK") and not self.progress.completed else agent.current_action),
                                "activity_action": agent.current_action, "target": action.target, "item": food_item,
                                "actor_id": agent.id, "executed": self.progress.completed,
                                "accepted_start": self.progress.started,
                                "duration_seconds": self.progress.duration_ticks*.25,
                                "phase": "started" if self.progress.started else "completed" if self.progress.completed else "in_progress",
                                "decision_source": self.progress.sources.get(agent.id, decision_source), "public_reason": action.reasoning,
                                "destination": requested_target if action.kind == ActionType.MOVE_TO else None,
                                "hunger_before": hunger_before, "hunger_at_decision": hunger_at_decision,
                                "hunger_after": agent.hunger, "changed": previous != agent.current_action})
            if self.decision_trace_limit:
                self.decision_trace.append({"tick": self.tick, "character": agent.name,
                    "provider": decision_source, "configured_provider": getattr(self.decision_provider, "name", "rule-based"),
                    "fallback": bool(status.get("fallback")), "fallback_reason": status.get("reason", ""),
                    "context": context_summary, "selected_action": proposed_action,
                    "explanation": action.reasoning or f"Rule execution: {action.kind.value}; hunger {agent.hunger}, energy {agent.energy}.",
                    "validation": ("rejected; WAIT fallback" if rejected else
                                   "model rejected; fallback accepted" if status.get("reason") in
                                   ("malformed response", "action was not an offered choice", "decision became invalid before execution")
                                   or status.get("reason", "").startswith("stale decision") else "accepted"),
                    "outcome": agent.current_action, "position_after": agent.position, "food_after": agent.food})
                del self.decision_trace[:-self.decision_trace_limit]
            assert self.world.walkable(agent.position)
            assert 0 <= agent.hunger <= 100 and 0 <= agent.energy <= 100
            assert 0 <= agent.inventory.used <= agent.inventory.capacity

        self.events.extend(self.wildlife.events)
        self.wildlife.events.clear()
        self.events.extend(self.social.events)
        self.social.events.clear()
        if hasattr(self.decision_provider, "audit_events"):
            self.events.extend(self.decision_provider.audit_events)
            self.decision_provider.audit_events.clear()
        self.number_events()
        if self.event_limit is not None:
            del self.events[:-self.event_limit]

    def number_events(self):
        pending = []
        for event in reversed(self.events):
            if "event_id" in event:
                break
            pending.append(event)
        for event in reversed(pending):
            self._event_sequence += 1
            event["event_id"] = self._event_sequence

    def ai_summary(self):
        if hasattr(self.decision_provider, "summary"):
            return self.decision_provider.summary()
        return {"provider": "rule-based", "api_calls": 0, "max_calls": 0, "agents": {}}

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.progress.cancel_all()
        self.social.close()
        self.events.extend(self.wildlife.events)
        self.wildlife.events.clear()
        self.events.extend(self.social.events)
        self.social.events.clear()
        self.number_events()
        if hasattr(self.decision_provider, "close"):
            self.decision_provider.close()

    def snapshot(self) -> dict:
        return {"cooking_station": asdict(self.cooking_station), "chickens": [asdict(c) for c in self.wildlife.chickens.values()],
                "wildlife_respawns": self.wildlife.respawns.copy(),
                "hunt_cooldowns": self.wildlife.cooldowns.copy(),
                "pursuits": {key: asdict(p) for key,p in self.wildlife.pursuits.items()},
                "clock": asdict(self.time_of_day), "scenario": self.scenario, "seed": self.seed, "tick": self.tick, "ai": self.ai_summary(),
                "memory_enabled": self.social.memory_enabled, "social_tick": self.social.tick,
                "memory_persistence": self.social.persistence_status,
                "pending_requests": [asdict(r) for r in self.social.pending.values()],
                "agents": [{**asdict(agent), "food": agent.food} for agent in self.agents],
                "resources": [{**asdict(bush), "food": bush.quantity}
                              for bush in self.resources.bushes.values()],
                "resource_changes": [asdict(change) for change in self.resources.changes],
                "events": self.events.copy()}


class FixedTicker:
    """Accumulate elapsed time; a tick always represents 0.25 simulated seconds."""
    interval = 0.25
    speeds = (0.5, 1.0, 2.0, 4.0)

    def __init__(self):
        self.speed = 1.0
        self.accumulator = 0.0

    def advance(self, simulation: Simulation, elapsed: float, on_step=None) -> int:
        if not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("Elapsed time must be finite and nonnegative")
        if simulation.paused:
            return 0
        self.accumulator += elapsed * self.speed
        count = int((self.accumulator + 1e-12) / self.interval)
        for _ in range(count):
            simulation.step()
            if on_step is not None:
                on_step(simulation)
        self.accumulator = max(0.0, self.accumulator - count * self.interval)
        return count
