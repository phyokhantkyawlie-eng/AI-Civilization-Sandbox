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
        ("Hungry", (209, 155, 64)) if value >= thresholds.hungry else ("Full" if value == 0 else "Okay", (106, 164, 104)))


def energy_status(value, thresholds=StatusThresholds()):
    return ("Exhausted", (205, 85, 74)) if value <= thresholds.exhausted else (
        ("Tired", (209, 155, 64)) if value <= thresholds.tired else ("Rested" if value >= 90 else "Okay", (98, 156, 177)))


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
    labels = {"COOK": "Cooking chicken", "HUNT": "Pursuing chicken", "GATHER": "Gathering berries", "EAT": "Eating", "REST": "Resting",
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
