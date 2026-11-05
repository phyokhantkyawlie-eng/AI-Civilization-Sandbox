"""Small, validated item inventory. Quantities are the single source of truth."""
from dataclasses import dataclass, field

@dataclass(frozen=True)
class ItemDefinition:
    name: str
    hunger_reduction: int = 0


# Nutrition lives here; raw meat is an ingredient, never an edible item.
ITEM_DEFINITIONS = {"berries": ItemDefinition("Berries", hunger_reduction=35),
                    "raw_chicken": ItemDefinition("Raw chicken"),
                    "cooked_chicken": ItemDefinition("Cooked chicken", hunger_reduction=65)}
ITEM_NAMES = {key: definition.name for key, definition in ITEM_DEFINITIONS.items()}


@dataclass
class Inventory:
    capacity: int = 5
    items: dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        if type(self.capacity) is not int or self.capacity < 0:
            raise ValueError("Capacity must be a nonnegative integer")
        if any(key not in ITEM_NAMES or type(value) is not int or value < 0 for key, value in self.items.items()):
            raise ValueError("Invalid inventory items")
        if self.used > self.capacity:
            raise ValueError("Inventory exceeds capacity")
        self.items = self.items.copy()

    @property
    def used(self):
        return sum(self.items.values())

    def quantity(self, item):
        if item not in ITEM_NAMES:
            raise ValueError("Unknown item")
        return self.items.get(item, 0)

    def _validate(self, item, quantity):
        if item not in ITEM_NAMES or type(quantity) is not int or quantity < 1:
            raise ValueError("Item and positive integer quantity required")

    def add(self, item, quantity=1):
        self._validate(item, quantity)
        if self.used+quantity > self.capacity:
            return False
        self.items[item] = self.quantity(item)+quantity
        return True

    def remove(self, item, quantity=1):
        self._validate(item, quantity)
        if self.quantity(item) < quantity:
            return False
        remaining = self.quantity(item)-quantity
        if remaining:
            self.items[item] = remaining
        else:
            self.items.pop(item, None)
        return True

    def transfer_to(self, other, item, quantity=1):
        self._validate(item, quantity)
        if other is self or self.quantity(item) < quantity or other.used+quantity > other.capacity:
            return False
        self.remove(item, quantity)
        other.add(item, quantity)
        return True

    def convert(self, source, result):
        """Atomic one-for-one conversion; full inventories need no extra slot."""
        self._validate(source, 1)
        self._validate(result, 1)
        if source == result or self.quantity(source) < 1:
            return False
        self.remove(source)
        self.add(result)
        return True

    def set_quantity(self, item, quantity):
        if type(quantity) is not int or quantity < 0 or self.used-self.quantity(item)+quantity > self.capacity:
            raise ValueError("Invalid quantity")
        if quantity:
            self.items[item] = quantity
        else:
            self.items.pop(item, None)


def edible_count(agent):
    return sum(agent.inventory.quantity(key) for key,definition in ITEM_DEFINITIONS.items()
               if definition.hunger_reduction > 0)


def select_food(agent, requested=None):
    if requested is not None:
        definition=ITEM_DEFINITIONS.get(requested)
        return requested if definition and definition.hunger_reduction > 0 and agent.inventory.quantity(requested)>0 else None
    available=[key for key,definition in ITEM_DEFINITIONS.items()
               if definition.hunger_reduction > 0 and agent.inventory.quantity(key)>0]
    # Prefer sufficient nutrition with the least waste; otherwise use the largest meal.
    return min(available,key=lambda key:(max(0,agent.hunger-ITEM_DEFINITIONS[key].hunger_reduction),
                                        max(0,ITEM_DEFINITIONS[key].hunger_reduction-agent.hunger),key)) if available else None
