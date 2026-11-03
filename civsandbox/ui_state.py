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
        ("Hungry", (209, 155, 64)) if value >= thresholds.hungry else ("Full", (106, 164, 104)))


def energy_status(value, thresholds=StatusThresholds()):
    return ("Exhausted", (205, 85, 74)) if value <= thresholds.exhausted else (
        ("Tired", (209, 155, 64)) if value <= thresholds.tired else ("Rested", (98, 156, 177)))


def activity(agent, simulation):
    names = {a.id: a.name for a in simulation.agents}
    owner = simulation.progress.locks.get(agent.id)
    job = simulation.progress.jobs.get(owner)
    if job and len(job.participants) == 2:
        other = next(key for key in job.participants if key != agent.id)
        return "Talking to "+names[other]
    if simulation.progress.waiting_for_response(agent):
        return "Waiting for response"
    labels = {"GATHER": "Gathering berries", "EAT": "Eating", "REST": "Resting",
              "WAIT": "Looking for food", "TALK": "Greeting",
              "REQUEST_FOOD": "Asking for food", "SHARE_FOOD": "Sharing berries",
              "REFUSE_REQUEST": "Declining a request"}
    if agent.current_action == "MOVE_TO":
        return "Walking to berries" if agent.goal and agent.goal.purpose == "food" else "Walking to destination"
    return labels.get(agent.current_action, "Looking around")
