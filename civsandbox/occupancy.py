"""Deterministic local reservations with bounded yielding in tight passages."""
from collections import deque


def route_avoiding(world, start, goal, occupied):
    queue = deque([start])
    parents = {start: None}
    while queue:
        current = queue.popleft()
        if current == goal:
            path = []
            while current != start:
                path.append(current)
                current = parents[current]
            return path[::-1]
        for neighbor in world.neighbors(current):
            if neighbor not in occupied and neighbor not in parents:
                parents[neighbor] = current
                queue.append(neighbor)
    return []


class Occupancy:
    """Wait at most three contested ticks, then permit passing on the normal route."""
    def __init__(self):
        self.waits = {}

    def next_step(self, agent, destination, world, agents, extra_occupied=()):
        occupied = {other.position for other in agents if other.id != agent.id} | set(extra_occupied)
        normal = world.path(agent.position, destination)
        if normal and normal[0] not in occupied:
            self.waits[agent.id] = 0
            return normal[0]
        route = route_avoiding(world, agent.position, destination, occupied)
        if route:
            self.waits[agent.id] = 0
            return route[0]
        if not normal:
            return None
        count = self.waits.get(agent.id, 0)+1
        self.waits[agent.id] = count
        if count > 3:
            self.waits[agent.id] = 0
            return normal[0]
        return None
