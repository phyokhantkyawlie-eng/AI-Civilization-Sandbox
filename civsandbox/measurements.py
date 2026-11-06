"""Streaming evaluation counters; bounded engine logs never truncate trial totals."""
from collections import Counter


class Measurements:
    def __init__(self):
        self.events = Counter()
        self.completed = Counter()
        self.meals = Counter()
        self.goals = Counter()
        self.activity_ticks = Counter()
        self.invalid_by_action = Counter()
        self.failed_reasons = Counter()
        self.last_event = 0
        self.hunger_sum = self.energy_sum = self.samples = self.ticks = 0
        self.incapacitated_ticks = 0
        self.spawn_ticks = {}
        self.credited_targets = set()
        self.max_spawn_sequence = 0
        self.duplicate_spawn_ids = self.duplicate_rewards = 0
        self.spawn_delay_sum = self.spawn_delay_count = 0
        self.minimum_spawn_delay = None
        self.first_120_attempts = 0
        self.activity_runs = {}
        self.longest_runs = Counter()

    def ingest(self, events):
        for event in events:
            action = event['action']
            self.events[action] += 1
            if event.get('social'):
                self.events['social:'+event.get('result','')] += 1
            if event.get('executed'):
                self.completed[action] += 1
                if action=='EAT':
                    self.meals[event.get('item') or 'berries'] += 1
                if action=='HUNT':
                    target = event.get('target')
                    if target in self.credited_targets:
                        self.duplicate_rewards += 1
                    self.credited_targets.add(target)
            if 'hunger_after' in event:
                self.events['opportunities'] += 1
            if action=='REJECTED':
                self.invalid_by_action[event.get('requested_action','unavailable')] += 1
            if action=='AI_DECISION' and event.get('reason') in (
                    'malformed response','action was not an offered choice',
                    'decision became invalid before execution'):
                self.events['model_rejected'] += 1
            if action=='GOAL_SELECTED':
                self.goals[event['goal']] += 1
            if action=='PLAN' and event.get('result')=='failed':
                self.failed_reasons[event['reason']] += 1
            if action=='SESSION':
                self.events['session:'+event.get('state','')] += 1
                if event.get('state')=='COMPLETED' and event.get('purpose')=='campfire':
                    self.events['campfire_completed'] += 1
            if action=='DIALOGUE' and event.get('purpose')=='thanks':
                self.events['thanks'] += 1
            if action=='SURVIVAL' and event.get('result')=='incapacitated':
                self.events['incapacitations'] += 1
            if action=='CHICKEN_SPAWN':
                target = event['target']
                sequence = int(target.split('-')[-1])
                self.duplicate_spawn_ids += sequence<=self.max_spawn_sequence
                self.max_spawn_sequence = max(sequence,self.max_spawn_sequence)
                self.spawn_ticks[target] = event['tick']
                self.events['repopulations'] += event['tick']>0
            if event.get('activity_action')=='HUNT' and event.get('accepted_start'):
                self.events['hunt_attempts'] += 1
                self.first_120_attempts += event['tick']<=120
                spawned = self.spawn_ticks.get(event.get('target'))
                if spawned is not None:
                    delay = event['tick']-spawned
                    self.spawn_delay_count += 1
                    self.spawn_delay_sum += delay
                    self.minimum_spawn_delay = delay if self.minimum_spawn_delay is None else min(delay,self.minimum_spawn_delay)
                    self.events['near_spawn_hunts'] += delay<=1
                    self.events['near_repopulation_hunts'] += delay<=1 and spawned>0

    def capture(self, sim):
        fresh = []
        for event in reversed(sim.events):
            if event['event_id']<=self.last_event:
                break
            fresh.append(event)
        self.ingest(reversed(fresh))
        if fresh:
            self.last_event = fresh[0]['event_id']
        self.ticks += 1
        self.samples += len(sim.agents)
        self.hunger_sum += sum(a.hunger for a in sim.agents)
        self.energy_sum += sum(a.energy for a in sim.agents)
        for actor in sim.agents:
            label = ('recovering' if actor.incapacitated_until else 'conversation' if sim.social.engaged(actor)
                     else actor.current_action.lower())
            self.activity_ticks[label] += 1
            self.incapacitated_ticks += bool(actor.incapacitated_until)
            previous,length = self.activity_runs.get(actor.id,(None,0))
            length = length+1 if label==previous else 1
            self.activity_runs[actor.id] = (label,length)
            self.longest_runs[label] = max(self.longest_runs[label],length)
        # Old defeated IDs cannot be targeted again; the world retains at most
        # 16 defeated records. Monotonic spawn IDs catch reuse without a growing set.
        retained = set(sim.wildlife.chickens)
        self.spawn_ticks = {key:value for key,value in self.spawn_ticks.items() if key in retained}
        self.credited_targets.intersection_update(retained)
