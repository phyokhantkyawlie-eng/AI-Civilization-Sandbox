"""One shared, timed cooking lease. Ingredients stay owned until completion."""
from dataclasses import dataclass
from .world import World, Tile

@dataclass
class CookingStation:
    id: str
    position: tuple[int, int]
    occupied_by: str | None = None
    ready_tick: int | None = None

    def nearby(self, actor):
        return sum((abs(a - b) for a, b in zip(actor.position, self.position))) == 1

    def can_cook(self, actor, world, tick, *, final=False):
        x, y = self.position
        valid_pad = (0 <= x < world.width and 0 <= y < world.height
                     and world.tiles[y][x] in (Tile.CAMPFIRE, Tile.GRASS, Tile.DIRT))
        if (actor.incapacitated_until or actor.energy <= 0 or not valid_pad
                or not self.nearby(actor) or actor.inventory.quantity('raw_chicken') < 1
                or self.occupied_by not in (None, actor.id)):
            return False
        return not final or (self.occupied_by == actor.id and self.ready_tick is not None
                             and tick >= self.ready_tick)

    def reserve(self, actor, tick, duration):
        self.occupied_by, self.ready_tick = (actor.id, tick + duration)

    def release(self, actor_id):
        if self.occupied_by == actor_id:
            self.occupied_by = self.ready_tick = None

def place_station(world, home, occupied=()):
    """Add a blocked fire tile while preserving all other reachable village tiles."""
    reachable=set(world.reachable(home))
    center=(world.width//2,world.height//2)
    choices=sorted((p for p in reachable if p not in occupied),
                   key=lambda p:(abs(p[0]-center[0])+abs(p[1]-center[1]),p))
    for position in choices:
        rows=[list(row) for row in world.tiles]
        rows[position[1]][position[0]]=Tile.CAMPFIRE
        candidate=World(tuple(tuple(row) for row in rows))
        if set(candidate.reachable(home))==reachable-{position}:
            return candidate,CookingStation('campfire-1',position)
    raise ValueError('No safe reachable cooking station location')


@dataclass(frozen=True)
class CookingObservation:
    id: str
    position: tuple[int, int]
    occupied_by: str | None
    ready_tick: int | None
    nearby = CookingStation.nearby

    def can_cook(self, actor, world, tick, *, final=False):
        return not final and CookingStation.can_cook(self, actor, world, tick)
