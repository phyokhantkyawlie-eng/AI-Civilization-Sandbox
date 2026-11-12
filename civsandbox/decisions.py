"""Replaceable decision interface and deterministic rule-based implementation."""
import random
from typing import Protocol

from .daynight import DayClock
from .inventory import edible_count, select_food, ITEM_DEFINITIONS
from .planning import Candidate, GoalPlan
from .dialogue import SessionState
from .world import Tile
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
        self.hunt_checks = {}
        self.plans = {}
        self.debug = {}
        self.retry_after = {}
        self.audit_events = []
        self.stats = {"selected":0,"completed":0,"failed":0,"interrupted":0,
                      "eligible_hunt_choices":0,"hunting_selected":0}

    def bind_social(self, social):
        self.social = social

    def bind_routines(self, clock, survival):
        if clock != self.clock or survival != self.survival:
            self.plans.clear()
            for state in self.debug.values():state["replan"]="Routine configuration changed"
        self.clock, self.survival = clock, survival

    def begin_tick(self, tick, agents):
        self.tick = tick

    def prefers_rest(self, agent):
        now = self.clock.at(self.tick)
        hour = now.hour+now.minute/60
        early = agent.personality.get("early_bird", 0.5)
        return hour >= 20+4*(1-early) or hour < 5+4*(1-early)

    def finish_plan(self, agent, result, reason, tick=None):
        plan = self.plans.pop(agent.id, None)
        if plan is None:
            return
        tick = self.tick if tick is None else tick
        if self.social and result != "completed":
            session=self.social.session_for(agent)
            if session and session.state in (SessionState.PROPOSED,SessionState.APPROACHING):
                self.social.cancel_session(session.id,reason)
        self.stats[result] += 1
        if result == 'failed':
            self.retry_after[agent.id] = (plan.goal, plan.target, tick + 16)
        self.audit_events.append({'tick': tick, 'agent': agent.name, 'actor_id': agent.id, 'action': 'PLAN', 'result': result, 'goal': plan.goal, 'reason': reason})
        del self.audit_events[:-128]
        self.debug.setdefault(agent.id, {})['replan'] = reason
        agent.goal = None

    def should_interrupt(self, agent, action):
        return agent.hunger >= self.survival.inefficient_hunger and edible_count(agent) > 0 and (action.kind != ActionType.EAT) or (agent.energy <= self.survival.rest_energy and action.kind not in (ActionType.EAT, ActionType.REST))

    def interrupt(self, agent, reason, tick):
        self.finish_plan(agent, 'interrupted', reason, tick)

    def on_action_result(self, agent, requested, completed, failed, tick):
        plan = self.plans.get(agent.id)
        if plan is None:
            return
        if failed:
            self.finish_plan(agent, 'failed', 'Action failed or pursuit ended', tick)
            return
        if completed and plan.steps and (requested.kind == plan.steps[0].kind):
            step = plan.steps[0]
            if step.kind == ActionType.MOVE_TO:
                if agent.position != plan.checkpoint.get('position'):
                    plan.last_progress = tick
                    plan.checkpoint['position'] = agent.position
                if agent.position != step.target:
                    return
            elif step.kind == ActionType.REST and agent.energy < plan.rest_target:
                plan.last_progress = tick
                return
            elif step.kind == ActionType.WAIT and (not plan.satisfied(agent, tick, self.social)):
                return
            plan.pop(agent, tick)
            if not plan.steps:
                self.finish_plan(agent, 'completed', 'Goal completed', tick)

    @staticmethod
    def approach(agent, target, world, include_target=False):
        choices = world.neighbors(target) + ([target] if include_target and world.walkable(target) else [])
        routes = []
        for p in choices:
            route = world.path(agent.position, p)
            if p == agent.position or route:
                routes.append((len(route), p))
        return min(routes) if routes else None

    @staticmethod
    def travel(agent, position):
        return [] if position == agent.position else [Action(ActionType.MOVE_TO, position)]

    def candidates(self, agent, world, resources):
        """Relative utility units: benefit/urgency minus travel, waiting and risk."""
        h = agent.hunger
        food = edible_count(agent)
        traits = agent.personality
        risk = traits.get('risk_aversion', 0.5)
        nature = traits.get('nature_affinity', 0.5)
        focus = traits.get('resource_focus', 0.5)
        daylight = self.clock.at(self.tick).daylight
        rest_night = self.prefers_rest(agent) and (not (h >= self.survival.hungry and food == 0))
        proposals = []

        def add(goal, target, steps, components, reason, rest_target=70):
            proposals.append(Candidate(goal, target, steps, components, reason, rest_target))
        item = select_food(agent)
        if item and h >= 30:
            benefit = min(h, ITEM_DEFINITIONS[item].hunger_reduction)
            add('EAT', item, [Action(ActionType.EAT, item=item)], {'base': 30, 'nutrition': benefit, 'hunger': h * 0.4}, 'Eat available nutrition before acquiring more')
        rest_needed = agent.energy <= self.survival.rest_energy or (agent.current_action == 'REST' and agent.energy < 70)
        if rest_needed or rest_night:
            target = agent.position
            if rest_night and agent.energy > 40:
                shelters = [(len(route), p) for y, row in enumerate(world.tiles) for x, tile in enumerate(row) if tile == Tile.HOUSE for p in world.neighbors((x, y)) if (route := world.path(agent.position, p)) and len(route) <= 4]
                if shelters:
                    target = min(shelters)[1]
            action = Action(ActionType.REST if agent.energy < (90 if rest_night else 70) else ActionType.WAIT)
            add('REST', target, self.travel(agent, target) + [action], {'fatigue': (100 - agent.energy) * 0.8, 'night': 110 if rest_night else 0, 'commitment': 20 if agent.current_action == 'REST' else 0}, 'Recover energy; preferred night schedule' if rest_night else 'Recover low energy', 90 if rest_night else 70)
        reserve = 2 if daylight else 1
        if food < reserve and agent.inventory.used < agent.inventory.capacity:
            options = []
            for bush, stock in resources.stocks().items():
                route = self.approach(agent, bush, world) if stock else None
                if route:
                    options.append((route[0], bush, route[1]))
            if options:
                cost, bush, position = min(options)
                steps = self.travel(agent, position) + [Action(ActionType.GATHER, bush)]
                if h >= 30:
                    steps.append(Action(ActionType.EAT, item='berries'))
                add('GATHER_FOOD', bush, steps, {'base': 25, 'hunger': h * 0.65, 'reserve': 8 * (reserve - food), 'nature': nature * 6, 'daylight': 8 if daylight else 0, 'travel': -cost * (1.5 + risk * 0.5)}, 'Reachable berries provide food and a small reserve')
        station = getattr(resources, 'cooking_station', None)
        raw = agent.inventory.quantity('raw_chicken')
        if raw and station:
            route = self.approach(agent, station.position, world, True)
            if route:
                steps = self.travel(agent, route[1]) + [Action(ActionType.COOK, station.id)]
                if h >= 30:
                    steps.append(Action(ActionType.EAT, item='cooked_chicken'))
                wait = max(0, (station.ready_tick or self.tick) - self.tick) if station.occupied_by not in (None, agent.id) else 0
                add('COOK_FOOD', station.id, steps, {'base': 40, 'hunger': h * 0.7, 'nutrition': ITEM_DEFINITIONS['cooked_chicken'].hunger_reduction / 10, 'resourcefulness': focus * 8, 'travel': -route[0] * 1.3, 'station_wait': -wait * 0.2}, 'Convert owned raw meat into a larger meal')
        hunt = self.hunting_choice(agent, world, resources, commit=False)
        if hunt and station and (route := self.approach(agent, station.position, world, True)):
            chicken = resources.wildlife.chickens[hunt.target]
            chase = self.approach(agent, chicken.position, world)
            cook_travel = self.approach(chicken, station.position, world, True)
            cost = cook_travel[0] if cook_travel else 999
            if chase and cook_travel:
                steps = [hunt] + [Action(ActionType.MOVE_TO, route[1]), Action(ActionType.COOK, station.id), Action(ActionType.EAT, item='cooked_chicken')]
                berry_costs = []
                for bush, stock in resources.stocks().items():
                    berry_route = self.approach(agent, bush, world) if stock else None
                    if berry_route:
                        berry_costs.append(berry_route[0])
                berry_cost = min(berry_costs, default=999)
                wait = max(0, (station.ready_tick or self.tick)-self.tick) if station.occupied_by not in (None, agent.id) else 0
                add('HUNT_FOOD', hunt.target, steps,
                    {'base': 36, 'hunger': h * .8,
                     'nutrition': ITEM_DEFINITIONS['cooked_chicken'].hunger_reduction * .2,
                     'curiosity': traits.get('curiosity', .5) * 12,
                     'risk': -risk * 20, 'pursuit': -chase[0] * 2,
                     'cook_travel': -cost * .7, 'work_time': -8,
                     'berries': -max(0, 10-berry_cost), 'station_wait': -wait * .2},
                    'Compare a bounded hunt and cooked meal against available berries')
        if self.social:
            incoming = [r for r in self.social.active_requests(agent) if r.recipient_id == agent.id]
            if incoming:
                add('HELP_OTHER', incoming[0].requester_id, [], {'response': 150, 'cooperation': traits.get('cooperation', 0.5) * 15}, 'Respond to a real nearby food request')
            peers = [p for p in self.social.agents.values() if p.id != agent.id and self.social.nearby(agent, p)]
            if food == 0 and h >= self.survival.hungry:
                refusals = {m['actor_id'] for m in self.social.relevant_memories(agent, {p.id for p in peers}) if m['result'] == 'refused' and self.social.tick - m['tick'] < 12}
                donors = [p for p in peers if p.food > 0 and p.id not in refusals and validate(Action(ActionType.REQUEST_FOOD, p.id), agent, world, resources, self.social)]
                if donors:
                    donor = max(donors, key=lambda p: (self.social.trust_for(agent, p.id), p.id))
                    add('GET_HELP', donor.id, [], {'request': 90, 'hunger': h * 0.3, 'risk': -risk * 8, 'trust': self.social.trust_for(agent, donor.id) * 0.1}, 'Ask a visible carrier before risking a trip')
            if agent.food >= 2 and h < self.survival.hungry and agent.energy > 30:
                needy = [p for p in peers if p.hunger >= self.survival.hungry and edible_count(p)==0
                         and validate(Action(ActionType.OFFER_FOOD,p.id),agent,world,resources,self.social)]
                if needy:
                    peer=max(needy,key=lambda p:(p.hunger,self.social.trust_for(agent,p.id),p.id))
                    add('HELP_OTHER',peer.id,[Action(ActionType.OFFER_FOOD,peer.id)],
                        {'need':peer.hunger*.4,'empathy':traits.get('empathy',.5)*35,
                         'sharing':traits.get('sharing',.5)*25,'cooperation':traits.get('cooperation',.5)*15,
                         'own_need':-h*.3,'risk':-risk*10},'Offer a real spare berry to a nearby hungry neighbor')
            # Plan a purpose before travelling to an observed human neighbor.
            # Ordinary NPC-to-NPC selection remains unchanged; no world-wide donors.
            human=self.social.agents.get(getattr(self.social,'human_id',None))
            separation=sum(abs(a-b) for a,b in zip(agent.position,human.position)) if human else 999
            if (human and human is not agent and 1<separation<=4
                    and self.social.available(agent,essential=True) and self.social.available(human,essential=True)):
                route=self.approach(agent,human.position,world)
                if route and food==0 and h>=self.survival.hungry and human.food>0 and agent.inventory.used<agent.inventory.capacity:
                    if not self.social.cooldown_reason(agent,human,'REQUEST_FOOD'):
                        add('GET_HELP',human.id,self.travel(agent,route[1])+[Action(ActionType.REQUEST_FOOD,human.id),Action(ActionType.WAIT)],
                            {'request':90,'hunger':h*.3,'risk':-risk*8,'travel':-route[0]*2,
                             'trust':self.social.trust_for(agent,human.id)*.1},
                            'Approach a visible berry carrier to request one berry')
                if (route and agent.food>=2 and h<self.survival.hungry and agent.energy>30
                        and human.hunger>=self.survival.hungry and edible_count(human)==0
                        and human.inventory.used<human.inventory.capacity
                        and not self.social.cooldown_reason(agent,human,'OFFER_FOOD')):
                    add('HELP_OTHER',human.id,self.travel(agent,route[1])+[Action(ActionType.OFFER_FOOD,human.id)],
                        {'need':human.hunger*.4,'empathy':traits.get('empathy',.5)*35,
                         'sharing':traits.get('sharing',.5)*25,'cooperation':traits.get('cooperation',.5)*15,
                         'own_need':-h*.3,'risk':-risk*10,'travel':-route[0]*2},
                        'Approach a visible hungry neighbor to offer a real spare berry')
            if food >= 2 and h < self.survival.hungry:
                talkable = [p for p in peers if not self.social.serious_dispute(agent,p.id) and validate(Action(ActionType.TALK, p.id), agent, world, resources, self.social)]
                if talkable:
                    peer = max(talkable, key=lambda p: (self.social.trust_for(agent, p.id), p.id))
                    add('SOCIALIZE', peer.id, [Action(ActionType.TALK, peer.id)], {'social': 10 + traits.get('sociability', 0.5) * 20, 'hunger': -h * 0.1}, 'Safe opportunity for a greeting')
            if station and food >= 1 and h < self.survival.hungry and agent.energy > 30:
                for peer in self.social.agents.values():
                    separation=sum(abs(a-b) for a,b in zip(agent.position,peer.position))
                    near_fire=max(sum(abs(a-b) for a,b in zip(a.position,station.position)) for a in (agent,peer))<=4
                    if (peer.id==agent.id or not 1<separation<=4 or not near_fire
                            or self.social.serious_dispute(agent,peer.id)
                            or not self.social.available(agent) or not self.social.available(peer)
                            or self.social.cooldown_reason(agent,peer,'TALK')):
                        continue
                    route=self.approach(agent,peer.position,world)
                    if route:
                        add('SOCIALIZE',peer.id,self.travel(agent,route[1])+[Action(ActionType.TALK,peer.id)],
                            {'company':18+traits.get('sociability',.5)*25,'travel':-route[0]*2,
                             'hunger':-h*.15},'Seek nearby company at the campfire')
            for peer in peers:
                if h<self.survival.inefficient_hunger and self.social.serious_dispute(agent,peer.id):
                    away=[p for p in world.reachable(agent.position) if sum(abs(a-b) for a,b in zip(p,peer.position))>=3
                          and sum(abs(a-b) for a,b in zip(p,agent.position))<=4]
                    if away:
                        destination=min(away,key=lambda p:(len(world.path(agent.position,p)),p))
                        add('AVOID',destination,self.travel(agent,destination),
                            {'recent_serious_refusal':28,'caution':risk*15},'Take a little space after a serious refusal')
        if food >= reserve and agent.energy > self.survival.rest_energy:
            add('EXPLORE', None, [], {'curiosity': 5 + traits.get('curiosity', 0.5) * 8}, 'Explore while needs are supplied')
        add('WAIT', None, [Action(ActionType.WAIT)], {'fallback': 1}, 'Wait for a valid opportunity')
        return proposals

    def decide(self, agent, world, resources, rng) -> Action:
        plan = self.plans.get(agent.id)
        if plan:
            while plan.steps and plan.satisfied(agent, self.tick, self.social):
                plan.pop(agent, self.tick)
            if not plan.steps:
                self.finish_plan(agent, 'completed', 'Goal completed')
                plan = None
        emergency_eat = agent.hunger >= self.survival.inefficient_hunger and edible_count(agent) > 0
        emergency_rest = agent.energy <= self.survival.rest_energy and (not emergency_eat)
        incoming = bool(self.social and any((r.recipient_id == agent.id for r in self.social.active_requests(agent))))
        urgent_food_over_rest = bool(plan and plan.goal == 'REST' and (plan.rest_target == 90) and (agent.hunger >= self.survival.hungry) and (edible_count(agent) == 0) and (agent.energy > self.survival.rest_energy))
        if plan and (urgent_food_over_rest or (emergency_eat and plan.goal != 'EAT') or (emergency_rest and plan.goal != 'REST') or (incoming and plan.goal != 'HELP_OTHER' and (not emergency_eat) and (not emergency_rest) and (agent.hunger < self.survival.inefficient_hunger))):
            self.finish_plan(agent, 'interrupted', 'Important survival need or incoming request')
            plan = None
        if plan and (self.tick >= plan.deadline or self.tick - plan.last_progress > 80):
            self.finish_plan(agent, 'failed', 'Plan deadline or progress limit')
            plan = None
        approach_session=self.social.session_for(agent) if self.social else None
        approaching_goal=bool(plan and plan.goal in ('SOCIALIZE','GET_HELP','HELP_OTHER')
                              and any(step.kind in (ActionType.TALK,ActionType.REQUEST_FOOD,ActionType.OFFER_FOOD) for step in plan.steps))
        if approaching_goal and approach_session is None:
            self.finish_plan(agent,'failed','Conversation reservation no longer available')
            plan=None
        if (plan and plan.goal in ('SOCIALIZE','GET_HELP','HELP_OTHER') and approach_session
                and approach_session.initiator_id==agent.id
                and approach_session.state in (SessionState.PROPOSED,SessionState.APPROACHING)):
            session=self.social.session_for(agent) if self.social else None
            peer=self.social.agents.get(plan.target) if self.social else None
            if (session is None or peer is None or session.state==SessionState.CANCELED
                    or not self.social.available(peer,session,session.intent and session.intent.item is not None)
                    or sum(abs(a-b) for a,b in zip(agent.position,peer.position))>6):
                self.finish_plan(agent,'failed','Partner unavailable during approach')
                plan=None
            elif not self.social.nearby(agent,peer):
                route=self.approach(agent,peer.position,world)
                if route:
                    terminal=self.social.intent_action(session)
                    plan.steps=[Action(ActionType.MOVE_TO,route[1]),terminal]+([Action(ActionType.WAIT)] if terminal.kind==ActionType.REQUEST_FOOD else [])
                else:
                    self.finish_plan(agent,'failed','Partner unreachable')
                    plan=None
            elif plan.steps[0].kind==ActionType.MOVE_TO:
                terminal=self.social.intent_action(session)
                plan.steps=[terminal]+([Action(ActionType.WAIT)] if terminal.kind==ActionType.REQUEST_FOOD else [])
                plan.arm(agent,self.tick)
        if plan:
            action = plan.steps[0]
            if action.kind == ActionType.COOK:
                station = getattr(resources, 'cooking_station', None)
                if station and station.id == action.target and (station.occupied_by not in (None, agent.id)):
                    return Action(ActionType.WAIT, reasoning='Waiting for the shared campfire')
            if not validate(action, agent, world, resources, self.social):
                self.finish_plan(agent, 'failed', 'Next task or target became invalid')
                plan = None
        if plan is None:
            proposals = self.candidates(agent, world, resources)
            if emergency_eat:
                proposals = [c for c in proposals if c.goal == 'EAT']
            elif emergency_rest:
                proposals = [c for c in proposals if c.goal == 'REST']
            elif agent.hunger >= self.survival.inefficient_hunger:
                proposals = [c for c in proposals if c.goal not in ('SOCIALIZE', 'EXPLORE', 'HELP_OTHER')]
            retry = self.retry_after.get(agent.id)
            if not (emergency_eat or emergency_rest):
                proposals = [c for c in proposals if not (retry and retry[:2] == (c.goal, c.target) and self.tick < retry[2])]
            # Sample once when choosing a new eligible food goal, never on a
            # retained plan, render frame or chicken-spawn event.
            for candidate in proposals:
                if candidate.goal == 'HUNT_FOOD':
                    candidate.components['seeded_preference'] = rng.uniform(-12, 26)
                    self.hunt_checks[agent.id] = self.tick+20
                    self.stats['eligible_hunt_choices'] += 1
            ranked = sorted(proposals, key=lambda c: (-c.utility, c.goal, str(c.target)))
            debug = self.debug.setdefault(agent.id, {})
            debug['utilities'] = [{'goal': c.goal, 'score': round(c.utility, 2), 'components': c.components} for c in ranked[:5]]
            for candidate in ranked:
                steps = list(candidate.steps)
                if candidate.goal in ('HELP_OTHER', 'GET_HELP') and not steps:
                    response = self.social_choice(agent, world, resources, rng)
                    if response is None:
                        continue
                    candidate.target = response.target
                    steps = [response] + ([Action(ActionType.WAIT)] if response.kind == ActionType.REQUEST_FOOD else [])
                elif candidate.goal=='HELP_OTHER' and any(step.kind==ActionType.OFFER_FOOD for step in steps):
                    willingness=.6*agent.personality.get('sharing',.5)+.2*agent.personality.get('empathy',.5)+.2*agent.personality.get('cooperation',.5)
                    if rng.random()>=max(.02,min(.98,willingness)):
                        continue
                elif candidate.goal == 'EXPLORE':
                    destinations = [p for p in world.reachable(agent.position) if p != agent.position]
                    if not destinations:
                        continue
                    candidate.target = rng.choice(destinations)
                    steps = [Action(ActionType.MOVE_TO, candidate.target)]
                if not steps:
                    continue
                terminal=next((step for step in reversed(steps) if step.kind in (ActionType.TALK,ActionType.REQUEST_FOOD,ActionType.OFFER_FOOD)),None)
                if terminal:
                    peer=self.social.agents.get(terminal.target)
                    purpose=('campfire' if station_near(resources,agent,peer) else 'greeting') if terminal.kind==ActionType.TALK else terminal.kind.value.lower()
                    if self.social.propose(agent,terminal.target,purpose,world,action=terminal,reason=candidate.reason) is None:
                        continue
                plan = GoalPlan(candidate.goal, candidate.target, steps, self.tick, self.tick + 320, candidate.reason, candidate.rest_target)
                plan.arm(agent, self.tick)
                self.plans[agent.id] = plan
                purpose = {'GATHER_FOOD': 'food', 'HUNT_FOOD': 'hunt', 'COOK_FOOD': 'cook', 'REST': 'rest', 'SOCIALIZE': 'social', 'EXPLORE': 'explore'}.get(plan.goal, plan.goal.lower())
                agent.goal = Goal(purpose, plan.target) if plan.target is not None else None
                self.stats['selected'] += 1
                self.audit_events.append({'tick':self.tick,'agent':agent.name,'actor_id':agent.id,
                                          'action':'GOAL_SELECTED','goal':plan.goal,
                                          'target':plan.target,'reason':plan.reason})
                if plan.goal == 'HUNT_FOOD':
                    self.stats['hunting_selected'] += 1
                    self.audit_events.append({'tick': self.tick, 'agent': agent.name,
                                              'actor_id': agent.id, 'action': 'PLAN',
                                              'result': 'selected', 'goal': plan.goal,
                                              'target': plan.target, 'reason': plan.reason})
                debug.update(goal=plan.goal, reason=plan.reason)
                break
        if plan is None:
            return Action(ActionType.WAIT)
        purpose = {'GATHER_FOOD': 'food', 'HUNT_FOOD': 'chicken meal', 'COOK_FOOD': 'cook', 'REST': 'rest', 'SOCIALIZE': 'social', 'EXPLORE': 'explore'}.get(plan.goal, plan.goal.lower())
        agent.goal = Goal(purpose, plan.target) if plan.target is not None else None
        self.debug.setdefault(agent.id, {})['sequence'] = [step.kind.value for step in plan.steps]
        step = plan.steps[0]
        if step.kind == ActionType.COOK:
            station = getattr(resources, 'cooking_station', None)
            if station and station.occupied_by not in (None, agent.id):
                return Action(ActionType.WAIT, reasoning='Waiting for the shared campfire')
        return step if step.kind == ActionType.WAIT else Action(step.kind, step.target, plan.reason, step.request_id, step.item)

    def hunting_choice(self, agent, world, resources, commit=True):
        wildlife = getattr(resources, "wildlife", None)
        if (wildlife is None or edible_count(agent) or agent.inventory.quantity("raw_chicken")
                or agent.hunger < self.survival.hungry
                or agent.energy < max(40, wildlife.settings.minimum_energy+12)
                or agent.inventory.used >= agent.inventory.capacity
                or self.tick < self.hunt_checks.get(agent.id, 0)):
            return None
        if commit:self.hunt_checks[agent.id] = self.tick+20
        risk = agent.personality.get("risk_aversion", .5)
        station = getattr(resources, 'cooking_station', None)
        if station is None or not self.approach(agent, station.position, world, True):
            return None
        candidates = []
        for chicken in wildlife.chickens.values():
            if (not chicken.alive or sum(abs(a-b) for a,b in zip(agent.position, chicken.position)) > 6
                    or not wildlife.can_hunt(agent, chicken.id, world)):
                continue
            paths = [len(route) for p in world.neighbors(chicken.position)
                     if (route := world.path(agent.position, p))]
            # Adjacent targets have no travel cost.
            steps = 0 if agent.position in world.neighbors(chicken.position) else min(paths, default=999)
            if steps > int(7-4*risk):
                continue
            score = ((agent.hunger-55)/45*.5 + agent.personality.get("curiosity", .5)*.2
                     + (1-risk)*.3 - steps*.06 - risk*.2)
            if score >= .25:
                candidates.append((-score, steps, chicken.id))
        if candidates:
            target = min(candidates)[2]
            if commit:agent.goal = Goal("hunt", target)
            return Action(ActionType.HUNT, target,
                          "Hungry, no carried meals, energy and cooking access; bounded pursuit for a cooked meal.")
        return None

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
        if peers and agent.hunger >= self.survival.hungry and edible_count(agent) == 0:
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


def station_near(resources, actor, peer):
    station=getattr(resources,'cooking_station',None)
    return bool(station and peer and max(sum(abs(a-b) for a,b in zip(p.position,station.position))
                                       for p in (actor,peer))<=4)
