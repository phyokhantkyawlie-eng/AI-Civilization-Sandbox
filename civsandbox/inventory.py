"""Small, validated item inventory. Quantities are the single source of truth."""
from dataclasses import dataclass, field

ITEM_NAMES = {"berries": "Berries"}


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

    def set_quantity(self, item, quantity):
        if type(quantity) is not int or quantity < 0 or self.used-self.quantity(item)+quantity > self.capacity:
            raise ValueError("Invalid quantity")
        if quantity:
            self.items[item] = quantity
        else:
            self.items.pop(item, None)
