"""Readable presentation mappings from authoritative gameplay state."""
from dataclasses import dataclass


@dataclass(frozen=True)
class StatusThresholds:
    hungry: int = 55
    starving: int = 85
    tired: int = 30
    exhausted: int = 10

    def __post_init__(self):
        if not 0 <= self.hungry < self.starving <= 100 or not 0 <= self.exhausted < self.tired <= 100:
            raise ValueError("Status thresholds must be ordered within 0–100")


def hunger_status(value, thresholds=StatusThresholds()):
    return ("Starving", (205, 85, 74)) if value >= thresholds.starving else (
        ("Hungry", (209, 155, 64)) if value >= thresholds.hungry else ("Well fed", (106, 164, 104)))


def energy_status(value, thresholds=StatusThresholds()):
    return ("Exhausted", (205, 85, 74)) if value <= thresholds.exhausted else (
        ("Tired", (209, 155, 64)) if value <= thresholds.tired else ("Rested", (98, 156, 177)))


def activity(agent, simulation):
    if agent.incapacitated_until:
        return "Recovering (temporary)"
    if agent.goal and agent.goal.purpose == "rest":
        return "Night rest"
    names = {a.id: a.name for a in simulation.agents}
    session = simulation.social.session_for(agent)
    if session and simulation.social.waiting_partner(agent):
        return "Waiting for "+names[session.initiator_id]
    if session and simulation.social.engaged(agent):
        peer = next(key for key in session.participants if key != agent.id)
        return "Talking to "+names[peer]
    owner = simulation.progress.locks.get(agent.id)
    job = simulation.progress.jobs.get(owner)
    if job and len(job.participants) == 2:
        other = next(key for key in job.participants if key != agent.id)
        return "Talking to "+names[other]
    if simulation.progress.waiting_for_response(agent):
        return "Waiting for response"
    labels = {"ATTACK": "Attacking chicken", "COOK": "Cooking chicken", "HUNT": "Pursuing chicken", "GATHER": "Gathering berries", "EAT": "Eating", "REST": "Resting",
              "WAIT": "Looking for food", "TALK": "Greeting",
              "REQUEST_FOOD": "Asking for food", "SHARE_FOOD": "Sharing berries",
              "REFUSE_REQUEST": "Declining a request"}
    if simulation.player and simulation.player.agent_id == agent.id:
        if agent.current_action == 'WAIT':
            return 'Waiting for your input'
        if agent.current_action == 'MOVE_TO':
            return 'Walking'
    if agent.current_action == "MOVE_TO":
        return "Walking to berries" if agent.goal and agent.goal.purpose == "food" else "Walking to destination"
    return labels.get(agent.current_action, "Looking around")


CHARACTER_ROLES = {'npc-1':'Gatherer','npc-2':'Merchant','npc-3':'Observer','npc-4':'Adventurer'}


def inventory_lines(agent):
    from .inventory import ITEM_NAMES
    return [f'{ITEM_NAMES[item]} x {count}' for item,count in sorted(agent.inventory.items.items()) if count] or ['Empty']


def goal_label(agent, simulation):
    if not agent.goal:
        return 'Choose an action' if simulation.player and simulation.player.agent_id==agent.id else 'Considering next task'
    purpose = agent.goal.purpose.lower().replace('player ','')
    return {'food':'Find berries','gather':'Gather berries','hunt':'Prepare a chicken meal',
            'chicken meal':'Prepare a chicken meal','cook':'Cook a meal','cook_food':'Cook a meal',
            'rest':'Recover energy','eat':'Eat a meal','social':'Meet a neighbor','socialize':'Meet a neighbor',
            'help_other':'Help a neighbor','get_help':'Ask for food','explore':'Explore the village',
            'wait':'Wait for an opportunity','avoid':'Take some space',
            'talk':'Talk to a neighbor','offer_food':'Offer food','request_food':'Ask for food'}.get(purpose,'Complete the current task')


def relationship_summary(agent, social):
    if not social.memory_enabled:
        return 'History unavailable'
    values = [(value,key) for key,value in agent.trust.items()]
    if values:
        value,key = max(values)
        if value>0:
            return ('Trusts ' if value>=6 else 'Building trust with ')+social.agents[key].name
        value,key = min(values)
        if value<0:
            return 'Low trust in '+social.agents[key].name
    return 'Getting acquainted'


def action_progress(agent, simulation):
    owner = simulation.progress.locks.get(agent.id)
    job = simulation.progress.jobs.get(owner)
    if not job or job.duration_ticks<=0:
        return None
    elapsed = simulation.tick-(job.finish_tick-job.duration_ticks)
    return max(0.0,min(1.0,elapsed/job.duration_ticks))


def unavailable_reason(action, actor, simulation):
    """Explanation only; shared validate remains the sole permission boundary."""
    from .actions import Action,ActionType
    if not isinstance(action,Action):
        return 'Choose a supported action.'
    if actor.incapacitated_until:
        return 'Recovering. Wait until you can act again.'
    if action.kind==ActionType.EAT:
        return 'Already well fed.' if actor.hunger==0 else 'No edible item of that type. Raw chicken must be cooked.'
    if action.kind in (ActionType.GATHER,ActionType.HUNT) and actor.inventory.used>=actor.inventory.capacity:
        return 'Inventory full. Eat or share an item first.'
    if actor.energy<=0:
        return 'Exhausted. Recover energy before working.'
    if action.kind==ActionType.GATHER:
        if simulation.resources.available(action.target)<=0:
            return 'This bush is depleted. Wait for berries to regrow.'
        return 'Stand beside the berry bush to gather.'
    if action.kind==ActionType.COOK:
        if actor.inventory.quantity('raw_chicken')==0:
            return 'Cooking requires one raw chicken.'
        if simulation.cooking_station.occupied_by not in (None,actor.id):
            return 'The campfire is busy. Wait for the other cook.'
        return 'Stand beside the campfire with enough energy.'
    if action.kind==ActionType.HUNT:
        chicken=simulation.wildlife.chickens.get(action.target)
        if chicken is None or not chicken.alive:
            return 'This chicken is no longer available.'
        if actor.energy<simulation.wildlife.settings.minimum_energy:
            return 'Too tired to hunt. Rest first.'
        if chicken.claimed_by not in (None,actor.id):
            return 'Another villager is pursuing this chicken.'
        if simulation.tick<simulation.wildlife.cooldowns.get(actor.id,0):
            return 'Take a break before hunting again.'
        return 'Move closer to a reachable chicken.'
    if action.kind==ActionType.REST:
        return 'Already fully rested.'
    if action.kind in (ActionType.OFFER_FOOD,ActionType.SHARE_FOOD) and not actor.food:
        return 'No berries to share.'
    return 'Unavailable now. Check distance or finish the current interaction.'
