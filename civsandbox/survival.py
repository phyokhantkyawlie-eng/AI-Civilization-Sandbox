"""Configurable, reversible survival consequences; never creates food or kills NPCs."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SurvivalRules:
    hungry: int = 55
    inefficient_hunger: int = 85
    starvation: int = 100
    rest_energy: int = 20
    collapse_energy: int = 0
    recovery_ticks: int = 12
    grace_ticks: int = 120
    hunger_slowdown: int = 2

    def __post_init__(self):
        if any(type(v) is not int for v in self.__dict__.values()):
            raise ValueError("Survival settings must be integers")
        if not 0 <= self.hungry < self.inefficient_hunger < self.starvation <= 100:
            raise ValueError("Hunger thresholds must be ordered within 0–100")
        if not 0 <= self.collapse_energy < self.rest_energy < 70:
            raise ValueError("Energy thresholds must be ordered below rest recovery (70)")
        if self.recovery_ticks < 1 or self.grace_ticks < 1 or self.hunger_slowdown < 1:
            raise ValueError("Recovery, grace and slowdown must be positive")

    def update(self, agent, tick):
        """Return a transition for the simulation log; needs remain authoritative."""
        if agent.incapacitated_until:
            if tick >= agent.incapacitated_until and agent.energy > self.collapse_energy:
                agent.incapacitated_until = 0
                agent.recovery_grace_until = tick+self.grace_ticks
                return "recovered"
        elif agent.energy <= self.collapse_energy or (
                agent.hunger >= self.starvation and tick >= agent.recovery_grace_until):
            agent.incapacitated_until = tick+self.recovery_ticks
            agent.goal = None
            return "incapacitated"
        return None
