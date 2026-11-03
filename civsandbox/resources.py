"""Finite bush stocks with a complete deterministic mutation ledger."""
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


class Resources:
    capacity = 5
    replenish_interval = 20

    def __init__(self, world: World, *, capacity=5, replenish_interval=20):
        self.capacity = capacity
        self.replenish_interval = replenish_interval
        self._food = {}
        self.changes: list[ResourceChange] = []
        for y, row in enumerate(world.tiles):
            for x, tile in enumerate(row):
                if tile == Tile.BUSH:
                    self._food[(x, y)] = self.capacity
                    self.changes.append(ResourceChange(0, (x, y), 0, self.capacity, "initial"))

    def available(self, position: Position) -> int:
        return self._food.get(position, 0)

    def stocks(self) -> dict[Position, int]:
        return self._food.copy()

    def collect(self, position: Position, tick: int, agent_id: str) -> bool:
        before = self.available(position)
        if before <= 0:
            return False
        self._food[position] = before - 1
        self.changes.append(ResourceChange(tick, position, before, before-1, "gather", agent_id))
        del self.changes[:-8192]
        return True

    def replenish(self, tick: int) -> None:
        if tick <= 0 or tick % self.replenish_interval:
            return
        for position, before in self._food.items():
            if before < self.capacity:
                self._food[position] += 1
                self.changes.append(ResourceChange(tick, position, before, before+1, "replenish"))
        del self.changes[:-8192]
