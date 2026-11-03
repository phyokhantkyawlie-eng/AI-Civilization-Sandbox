"""NPC state, independent of rendering and decision providers."""
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .social import Memory

from .world import Position
from .inventory import Inventory


@dataclass(frozen=True)
class Goal:
    purpose: str
    target: Position


@dataclass(init=False)
class Agent:
    id: str
    name: str
    position: Position
    color: tuple[int, int, int]
    hunger: int = 25
    energy: int = 90
    inventory: Inventory = field(default_factory=Inventory)
    facing: str = "down"
    current_action: str = "WAIT"
    goal: Goal | None = None
    personality: dict[str, float] = field(default_factory=lambda: {
        "sociability": 0.5, "curiosity": 0.5, "cooperation": 0.5,
    })

    personality_name: str = "Balanced"
    trust: dict[str, int] = field(default_factory=dict)
    memories: list["Memory"] = field(default_factory=list)

    def __init__(self, id, name, position, color, hunger=25, energy=90, food=0,
                 current_action="WAIT", goal=None, personality=None, personality_name="Balanced",
                 trust=None, memories=None):
        self.id, self.name, self.position, self.color = id, name, position, color
        self.hunger, self.energy = hunger, energy
        self.inventory = Inventory()
        self.food = food
        self.facing = "down"
        self.current_action, self.goal = current_action, goal
        self.personality = personality if personality is not None else {
            "sociability": 0.5, "curiosity": 0.5, "cooperation": 0.5}
        self.personality_name = personality_name
        self.trust = trust if trust is not None else {}
        self.memories = memories if memories is not None else []

    @property
    def food(self):
        """Compatibility view used by existing providers and experiments."""
        return self.inventory.quantity("berries")

    @food.setter
    def food(self, value):
        self.inventory.set_quantity("berries", value)

    def advance_needs(self) -> None:
        self.hunger = min(100, self.hunger + 1)
        self.energy = max(0, self.energy - 1)


PERSONALITIES = (
    ("Generous", {"empathy": 0.95, "cooperation": 0.9, "sharing": 0.95,
                  "trust_gain_rate": 1.0, "risk_aversion": 0.2, "sociability": 0.55, "curiosity": 0.5}),
    ("Selfish", {"empathy": 0.15, "cooperation": 0.2, "sharing": 0.1,
                 "trust_gain_rate": 1.0, "risk_aversion": 0.3, "sociability": 0.25, "curiosity": 0.5}),
    ("Cautious", {"empathy": 0.55, "cooperation": 0.5, "sharing": 0.5,
                  "trust_gain_rate": 0.4, "risk_aversion": 0.9, "sociability": 0.3, "curiosity": 0.3}),
    ("Friendly", {"empathy": 0.8, "cooperation": 0.85, "sharing": 0.8,
                  "trust_gain_rate": 1.0, "risk_aversion": 0.25, "sociability": 0.95, "curiosity": 0.7}),
)
