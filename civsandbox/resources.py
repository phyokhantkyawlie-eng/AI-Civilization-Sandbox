"""Finite bush records, deterministic regeneration and a bounded mutation ledger."""
from dataclasses import dataclass

from .world import Position, Tile, World


@dataclass(frozen=True)
class ResourceChange:
    tick: int
    position: Position
    before: int
    after: int
    reason: str
    agent_id: str | None = None


@dataclass
class BerryBush:
    id: str
    position: Position
    quantity: int
    capacity: int
    regeneration_interval: int
    regeneration_progress: int = 0

    @property
    def ticks_until_regeneration(self):
        return self.regeneration_interval-self.regeneration_progress if self.quantity < self.capacity else None


class Resources:
    capacity = 5
    replenish_interval = 20

    def __init__(self, world: World, *, capacity=5, replenish_interval=20):
        if type(capacity) is not int or capacity < 1 or type(replenish_interval) is not int or replenish_interval < 1:
            raise ValueError("Resource capacity and interval must be positive integers")
        self.tick = 0
        self.capacity = capacity
        self.replenish_interval = replenish_interval
        self.bushes: dict[Position, BerryBush] = {}
        self.changes: list[ResourceChange] = []
        for y, row in enumerate(world.tiles):
            for x, tile in enumerate(row):
                if tile == Tile.BUSH:
                    self.bushes[(x, y)] = BerryBush(f"bush-{x}-{y}", (x, y), capacity, capacity, replenish_interval)
                    self.changes.append(ResourceChange(0, (x, y), 0, self.capacity, "initial"))

    def available(self, position: Position) -> int:
        bush = self.bushes.get(position)
        return bush.quantity if bush else 0

    def stocks(self) -> dict[Position, int]:
        return {position: bush.quantity for position, bush in self.bushes.items()}

    def collect(self, position: Position, tick: int, agent_id: str) -> bool:
        before = self.available(position)
        if before <= 0:
            return False
        bush = self.bushes[position]
        bush.quantity = before-1
        bush.regeneration_progress = self.tick % bush.regeneration_interval
        self.changes.append(ResourceChange(tick, position, before, before-1, "gather", agent_id))
        del self.changes[:-8192]
        return True

    def replenish(self, tick: int) -> None:
        # Absolute ticks make repeated calls idempotent; skipped ticks catch up.
        if type(tick) is not int or tick < self.tick:
            raise ValueError("Resource time must advance monotonically")
        for position, bush in self.bushes.items():
            interval = bush.regeneration_interval
            boundaries = range((self.tick//interval+1)*interval, tick+1, interval)
            for boundary in boundaries:
                if bush.quantity >= bush.capacity:
                    break
                before = bush.quantity
                bush.quantity += 1
                self.changes.append(ResourceChange(boundary, position, before, bush.quantity, "replenish"))
            bush.regeneration_progress = tick % interval if bush.quantity < bush.capacity else 0
        self.tick = tick
        del self.changes[:-8192]
