"""Bounded offline plans and inspectable utility proposals, with no world mutation."""
from dataclasses import dataclass, field
from .actions import Action, ActionType
from .inventory import select_food

@dataclass
class Candidate:
    goal: str
    target: object
    steps: list[Action]
    components: dict[str, float]
    reason: str
    rest_target: int = 70

    @property
    def utility(self):
        return sum(self.components.values())

@dataclass
class GoalPlan:
    goal: str
    target: object
    steps: list[Action]
    created: int
    deadline: int
    reason: str
    rest_target: int = 70
    last_progress: int = 0
    checkpoint: dict = field(default_factory=dict)

    def __post_init__(self):
        if not 1 <= len(self.steps) <= 6:
            raise ValueError('A plan must contain one to six tasks')

    def arm(self, actor, tick):
        self.last_progress = tick
        self.checkpoint = {'position': actor.position, 'items': actor.inventory.items.copy(), 'started': tick, 'meal': select_food(actor, self.steps[0].item) if self.steps and self.steps[0].kind == ActionType.EAT else None}

    def pop(self, actor, tick):
        self.steps.pop(0)
        self.arm(actor, tick)

    def satisfied(self, actor, tick, social=None):
        if not self.steps:
            return True
        step = self.steps[0]
        before = self.checkpoint.get('items', {})
        if step.kind == ActionType.MOVE_TO:
            return actor.position == step.target
        if step.kind == ActionType.GATHER:
            return actor.food > before.get('berries', 0)
        if step.kind == ActionType.HUNT:
            return actor.inventory.quantity('raw_chicken') > before.get('raw_chicken', 0)
        if step.kind == ActionType.COOK:
            return actor.inventory.quantity('raw_chicken') < before.get('raw_chicken', 0) and actor.inventory.quantity('cooked_chicken') > before.get('cooked_chicken', 0)
        if step.kind == ActionType.EAT:
            item = self.checkpoint.get('meal')
            return item is not None and actor.inventory.quantity(item) < before.get(item, 0)
        if step.kind == ActionType.REST:
            return actor.energy >= self.rest_target
        if step.kind == ActionType.WAIT:
            return tick - self.checkpoint.get('started', tick) >= 8 and (not (social and social.active_requests(actor)))
        return False
