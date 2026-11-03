"""Tile world and breadth-first pathfinding; no graphics dependencies."""
from collections import deque
from dataclasses import dataclass
from enum import Enum
import random

Position = tuple[int, int]


class Tile(Enum):
    GRASS = "grass"
    DIRT = "dirt"
    TREE = "tree"
    BUSH = "bush"
    WATER = "water"
    HOUSE = "house"


@dataclass(frozen=True)
class World:
    tiles: tuple[tuple[Tile, ...], ...]

    def __post_init__(self):
        if not self.tiles or not self.tiles[0] or any(
            len(row) != len(self.tiles[0]) for row in self.tiles
        ):
            raise ValueError("World must be a nonempty rectangle")

    @property
    def width(self):
        return len(self.tiles[0])

    @property
    def height(self):
        return len(self.tiles)

    def walkable(self, position: Position) -> bool:
        x, y = position
        return (0 <= x < self.width and 0 <= y < self.height
                and self.tiles[y][x] in (Tile.GRASS, Tile.DIRT))

    def neighbors(self, position: Position) -> list[Position]:
        x, y = position
        return [p for p in ((x+1, y), (x, y+1), (x-1, y), (x, y-1))
                if self.walkable(p)]

    def path(self, start: Position, goal: Position) -> list[Position]:
        """Return shortest four-direction route excluding start; [] if unreachable."""
        if not self.walkable(start) or not self.walkable(goal):
            return []
        frontier = deque([start])
        parents = {start: None}
        while frontier:
            current = frontier.popleft()
            if current == goal:
                route = []
                while current != start:
                    route.append(current)
                    current = parents[current]
                return route[::-1]
            for neighbor in self.neighbors(current):
                if neighbor not in parents:
                    parents[neighbor] = current
                    frontier.append(neighbor)
        return []

    def reachable(self, start: Position) -> list[Position]:
        if not self.walkable(start):
            return []
        frontier = deque([start])
        seen = {start}
        result = []
        while frontier:
            current = frontier.popleft()
            result.append(current)
            for neighbor in self.neighbors(current):
                if neighbor not in seen:
                    seen.add(neighbor)
                    frontier.append(neighbor)
        return result


def generate_world(rng: random.Random) -> World:
    """Build a 24x18 village with clear central walking lanes."""
    tiles = [[Tile.GRASS for _ in range(24)] for _ in range(18)]
    for y in range(18):
        for x in range(24):
            if x % 6 != 2 and y % 5 != 2:
                tiles[y][x] = rng.choices(
                    [Tile.GRASS, Tile.TREE, Tile.BUSH], [80, 12, 8]
                )[0]
    for y in range(10, 15):
        for x in range(17, 22):
            tiles[y][x] = Tile.WATER
    for x, y in ((4, 4), (10, 4), (16, 4), (4, 13)):
        tiles[y][x] = Tile.HOUSE
    # Recolor existing clear grass lanes without changing terrain connectivity.
    for y in range(18):
        for x in range(24):
            if tiles[y][x] == Tile.GRASS and (x % 6 == 2 or y % 5 == 2):
                tiles[y][x] = Tile.DIRT
    return World(tuple(tuple(row) for row in tiles))


def shortage_world(world: World) -> World:
    """Two berry patches bordering the village's continuous east-west lane."""
    rows = [[Tile.GRASS if tile == Tile.BUSH else tile for tile in row] for row in world.tiles]
    for x in (6, 10):
        rows[3][x] = Tile.BUSH
    return World(tuple(tuple(row) for row in rows))
