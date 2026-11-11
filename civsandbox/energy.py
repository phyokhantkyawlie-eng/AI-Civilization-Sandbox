"""Central offline energy budget: integer needs with deterministic sub-unit debt."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class EnergyRules:
    idle_per_second: float = .02
    walk_cost: float = .1
    gather_cost: float = 1.0
    cook_cost: float = .5
    hunt_step_cost: float = .5
    hunt_cost: float = 4.0
    attack_cost: float = .5
    rest_gain: int = 8

    def __post_init__(self):
        for name,value in self.__dict__.items():
            if type(value) not in (int,float) or not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError('Energy rates must be finite values from 0 to 100')
            if abs(value*1000-round(value*1000))>1e-8:
                raise ValueError('Energy rates support at most three decimal places')
        if type(self.rest_gain) is not int or self.rest_gain < 1:
            raise ValueError('Rest restoration must be a positive integer')

    def spend(self, actor, amount):
        # One authoritative integer bar plus persisted micro-unit debt; no float drift.
        units = actor.energy_spent_micro + round(amount*1_000_000)
        whole, remainder = divmod(units,1_000_000)
        actor.energy = max(0,actor.energy-whole)
        actor.energy_spent_micro = remainder if actor.energy else 0

    def recover(self, actor):
        actor.energy = min(100,actor.energy+self.rest_gain)
        if actor.energy == 100:
            actor.energy_spent_micro = 0

    def passive(self, actor, seconds, busy=False):
        # Physical actions pay their own inclusive cost, not passive + action costs.
        if not busy and actor.current_action not in ('MOVE_TO','HUNT','GATHER','COOK','ATTACK','REST'):
            self.spend(actor,self.idle_per_second*seconds)


DEFAULT_ENERGY = EnergyRules()
