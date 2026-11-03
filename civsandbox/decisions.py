"""Replaceable decision interface and deterministic rule-based implementation."""
import random
from typing import Protocol

from .daynight import DayClock
from .survival import SurvivalRules
from .actions import Action, ActionType, validate
from .agents import Agent, Goal
from .resources import Resources
from .world import World


class DecisionProvider(Protocol):
    def decide(self, agent: Agent, world: World, resources: Resources,
               rng: random.Random) -> Action: ...


class RuleBasedDecisionProvider:
    def __init__(self):
        self.social = None
        self.clock = DayClock()
        self.survival = SurvivalRules()
        self.tick = 0

    def bind_social(self, social):
        self.social = social

    def bind_routines(self, clock, survival):
        self.clock, self.survival = clock, survival

    def begin_tick(self, tick, agents):
        self.tick = tick

    def prefers_rest(self, agent):
        now = self.clock.at(self.tick)
        hour = now.hour+now.minute/60
        early = agent.personality.get("early_bird", 0.5)
        return hour >= 20+4*(1-early) or hour < 5+4*(1-early)

    def decide(self, agent, world, resources, rng) -> Action:
        if self.social and self.social.pacing:
            incoming = [r for r in self.social.active_requests(agent) if r.recipient_id == agent.id]
            if incoming and agent.energy > 5 and agent.hunger < self.survival.inefficient_hunger:
                response = self.social_choice(agent, world, resources, rng)
                if response:
                    return response
        if agent.food > 0 and agent.hunger >= 30:
            return Action(ActionType.EAT)
        if agent.energy <= self.survival.rest_energy or (agent.current_action == "REST" and agent.energy < 70):
            return Action(ActionType.REST)

        routine_rest = self.prefers_rest(agent)
        urgent_food = agent.hunger >= self.survival.hungry and agent.food == 0
        if routine_rest and not urgent_food:
            agent.goal = Goal("rest", agent.position)
            return Action(ActionType.REST if agent.energy < 90 else ActionType.WAIT,
                          reasoning="Night routine; urgent food needs take priority.")
        if agent.goal and agent.goal.purpose == "rest":
            agent.goal = None

        social_action = self.social_choice(agent, world, resources, rng)
        if social_action:
            return social_action

        # Preserve a food goal until stocked, depleted, or unreachable.
        needs_food = agent.food < (2 if self.clock.at(self.tick).daylight else 1)
        if needs_food:
            if agent.goal and agent.goal.purpose == "food":
                action = self.food_action(agent, agent.goal.target, world, resources)
                if action:
                    return action
            candidates = []
            for bush, stock in resources.stocks().items():
                if stock:
                    for approach in world.neighbors(bush):
                        route = world.path(agent.position, approach)
                        if approach == agent.position or route:
                            candidates.append((len(route), bush, approach))
            if candidates:
                _, bush, _ = min(candidates)
                agent.goal = Goal("food", bush)
                return self.food_action(agent, bush, world, resources)
            agent.goal = None
            return Action(ActionType.WAIT)

        if agent.goal and agent.goal.purpose in ("explore", "social"):
            action = Action(ActionType.MOVE_TO, agent.goal.target)
            if validate(action, agent, world, resources):
                return action
        destinations = [p for p in world.reachable(agent.position) if p != agent.position]
        if destinations:
            agent.goal = Goal("explore", rng.choice(destinations))
            return Action(ActionType.MOVE_TO, agent.goal.target)
        agent.goal = None
        return Action(ActionType.WAIT)

    @staticmethod
    def food_action(agent, bush, world, resources):
        gather = Action(ActionType.GATHER, bush)
        if validate(gather, agent, world, resources):
            return gather
        if resources.available(bush) <= 0:
            return None
        approaches = []
        for position in world.neighbors(bush):
            route = world.path(agent.position, position)
            if route:
                approaches.append((len(route), position))
        if approaches:
            return Action(ActionType.MOVE_TO, min(approaches)[1])
        return None

    def social_choice(self, agent, world, resources, rng):
        social = self.social
        if social is None:
            return None
        traits = agent.personality
        empathy = traits.get("empathy", 0.5)
        cooperation = traits.get("cooperation", 0.5)
        sharing = traits.get("sharing", 0.5)
        risk = traits.get("risk_aversion", 0.5)
        sociability = traits.get("sociability", 0.5)
        for request in social.active_requests(agent):
            if request.recipient_id != agent.id:
                continue
            share = Action(ActionType.SHARE_FOOD, request.requester_id, request_id=request.id)
            refuse = Action(ActionType.REFUSE_REQUEST, request.requester_id, request_id=request.id)
            trust = social.trust_for(agent, request.requester_id)
            willingness = (0.6*sharing + 0.2*empathy + 0.2*cooperation
                           + trust/200 - risk*0.25 - agent.hunger/200
                           - (0.2 if agent.food <= 1 else 0))
            if validate(share, agent, world, resources, social) and rng.random() < max(0.02, min(0.98, willingness)):
                return share
            if validate(refuse, agent, world, resources, social):
                return refuse
        peers = [other for other in social.agents.values()
                 if other.id != agent.id and social.nearby(agent, other)]
        if peers and agent.hunger >= self.survival.hungry and agent.food == 0:
            if any(r.requester_id == agent.id and any(p.id == r.recipient_id for p in peers)
                   for r in social.active_requests(agent)):
                return Action(ActionType.WAIT)
            recently_refused = {m["actor_id"] for m in social.relevant_memories(agent, {p.id for p in peers})
                                if m["result"] == "refused" and social.tick-m["tick"] < 12}
            candidates = [p for p in peers if p.food > 0 and p.id not in recently_refused
                          and validate(Action(ActionType.REQUEST_FOOD, p.id),
                                                       agent, world, resources, social)]
            if candidates and rng.random() < 0.8-risk*0.3:
                # Relationships influence preference only when recall is enabled.
                best_trust = max(social.trust_for(agent, p.id) for p in candidates)
                preferred = [p for p in candidates if social.trust_for(agent, p.id) == best_trust]
                return Action(ActionType.REQUEST_FOOD, rng.choice(preferred).id)
        if agent.food >= 2:
            talkable = [p for p in peers if validate(Action(ActionType.TALK, p.id), agent, world, resources, social)]
            if talkable and rng.random() < sociability*0.08*(1-risk*0.5):
                return Action(ActionType.TALK, rng.choice(talkable).id)
            # Social NPCs sometimes seek a visible neighbor; no distant NPC tracking.
            visible = [p for p in social.agents.values() if p.id != agent.id
                       and 1 < sum(abs(a-b) for a, b in zip(p.position, agent.position)) <= 4]
            if visible and sociability >= 0.8 and rng.random() < sociability*0.15:
                other = rng.choice(visible)
                approaches = [(len(route), p) for p in world.neighbors(other.position)
                              if (route := world.path(agent.position, p))]
                if approaches:
                    target = min(approaches)[1]
                    agent.goal = Goal("social", target)
                    return Action(ActionType.MOVE_TO, target)
        return None
