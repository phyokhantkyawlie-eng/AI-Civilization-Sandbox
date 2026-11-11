"""Small wildlife FSM and bounded population/claim rules in the shared grid."""
from dataclasses import dataclass
from enum import Enum
import random

from .world import Tile


def distance(first, second):
    return abs(first[0]-second[0])+abs(first[1]-second[1])


@dataclass(frozen=True)
class WildlifeSettings:
    starting_population: int = 2
    maximum_population: int = 4
    respawn_ticks: int = 240
    movement_ticks: int = 12
    flee_ticks: int = 4
    threat_radius: int = 2
    chase_ticks: int = 80
    chase_steps: int = 12
    catch_ticks: int = 8
    cooldown_ticks: int = 160
    minimum_energy: int = 12

    def __post_init__(self):
        if any(type(value) is not int for value in self.__dict__.values()):
            raise ValueError("Wildlife settings must be integers")
        if not 0 <= self.starting_population <= self.maximum_population <= 20:
            raise ValueError("Require 0 <= starting <= maximum chicken population <= 20")
        if any(value < 1 for key, value in self.__dict__.items()
               if key not in ("starting_population", "maximum_population")):
            raise ValueError("Wildlife durations, distances and energy must be positive")
        if self.minimum_energy > 100 or self.catch_ticks >= self.chase_ticks:
            raise ValueError("Invalid hunt energy or catch/chase durations")


class ChickenState(str, Enum):
    IDLE = "IDLE"
    WANDER = "WANDER"
    FLEE = "FLEE"


@dataclass
class Chicken:
    id: str
    position: tuple[int, int]
    state: ChickenState = ChickenState.IDLE
    activity: str = "pecking"
    alive: bool = True
    threat_radius: int = 2
    movement_ticks: int = 12
    next_move_tick: int = 0
    fear_until: int = 0
    calm_until: int = 0
    moving: bool = False
    facing: int = 1
    claimed_by: str | None = None
    hp: int = 100
    max_hp: int = 100


@dataclass
class Pursuit:
    chicken_id: str
    deadline: int
    steps: int = 0
    catch_ready_tick: int = 0


class Wildlife:
    def __init__(self, world, agents, seed=42, settings=None, reserved_tiles=()):
        self.settings = settings or WildlifeSettings()
        self.reserved_tiles = set(reserved_tiles)
        self.rng = random.Random(f"{seed}:chickens")
        self.chickens: dict[str, Chicken] = {}
        self.pursuits: dict[str, Pursuit] = {}
        self.cooldowns: dict[str, int] = {}
        self.respawns: list[int] = []
        self.events: list[dict] = []
        self.sequence = 0
        self.tick = 0
        self.home = agents[0].position if agents else (0, 0)
        for _ in range(self.settings.starting_population):
            if not self.spawn(world, agents):
                self.respawns.append(self.settings.respawn_ticks)

    def living(self):
        return [chicken for chicken in self.chickens.values() if chicken.alive]

    def spawn(self, world, agents):
        if len(self.living()) >= self.settings.maximum_population:
            return False
        occupied = {a.position for a in agents} | {c.position for c in self.living()} | self.reserved_tiles
        reachable = set(world.reachable(self.home))
        choices = sorted(p for p in reachable if p not in occupied)
        # Prefer quiet grass in the accessible village, without blocking a spawn.
        quiet = [p for p in choices if world.tiles[p[1]][p[0]] == Tile.GRASS
                 and all(distance(p, a.position) > 3 for a in agents)]
        if not choices:
            return False
        position = self.rng.choice(quiet or choices)
        self.sequence += 1
        chicken = Chicken(f"chicken-{self.sequence}", position,
                          threat_radius=self.settings.threat_radius,
                          movement_ticks=self.settings.movement_ticks,
                          next_move_tick=self.tick+self.settings.movement_ticks)
        self.chickens[chicken.id] = chicken
        self.events.append({"tick": self.tick, "action": "CHICKEN_SPAWN", "target": chicken.id,
                            "position": position, "result": "spawned"})
        # Preserve recent defeated entities for inspection, without an endless graveyard.
        dead = [c.id for c in self.chickens.values() if not c.alive]
        for key in dead[:-16]:
            del self.chickens[key]
        return True

    def advance(self, tick, world, agents):
        if type(tick) is not int or tick < self.tick:
            raise ValueError("Wildlife time must advance monotonically")
        if tick == self.tick:
            return
        self.tick = tick
        for due in list(self.respawns):
            if tick < due:
                continue
            self.respawns.remove(due)
            if len(self.living()) < self.settings.starting_population:
                if not self.spawn(world, agents):
                    self.respawns.append(tick+self.settings.respawn_ticks)
        occupied = {a.position for a in agents}
        for chicken in self.living():
            chicken.moving = False
            threats = [a.position for a in agents if not a.incapacitated_until
                       and a.current_action != "REST"
                       and distance(a.position, chicken.position) <= chicken.threat_radius]
            if chicken.state == ChickenState.FLEE and tick >= chicken.fear_until:
                chicken.state, chicken.activity = ChickenState.IDLE, "resting"
                chicken.calm_until = tick+16  # bounded escape burst followed by a short rest
                chicken.next_move_tick = tick+12
            if threats and tick >= chicken.calm_until and chicken.state != ChickenState.FLEE:
                chicken.state, chicken.activity = ChickenState.FLEE, "fleeing"
                chicken.fear_until = tick+12
                chicken.next_move_tick = tick
            if tick < chicken.next_move_tick:
                continue
            blocked = occupied | {c.position for c in self.living() if c.id != chicken.id} | self.reserved_tiles
            choices = [p for p in world.neighbors(chicken.position) if p not in blocked]
            destination = chicken.position
            if chicken.state == ChickenState.FLEE:
                if choices and threats:
                    score = lambda p: min(distance(p, threat) for threat in threats)
                    best = max(score(p) for p in choices)
                    if best >= score(chicken.position):
                        destination = self.rng.choice([p for p in choices if score(p) == best])
                chicken.next_move_tick = tick+self.settings.flee_ticks
            elif chicken.state == ChickenState.WANDER:
                chicken.state, chicken.activity = ChickenState.IDLE, self.rng.choice(("pecking", "resting"))
                chicken.next_move_tick = tick+chicken.movement_ticks
            else:
                if choices and self.rng.random() < .5:
                    destination = self.rng.choice(choices)
                    chicken.state, chicken.activity = ChickenState.WANDER, "walking"
                else:
                    chicken.activity = self.rng.choice(("pecking", "resting"))
                chicken.next_move_tick = tick+chicken.movement_ticks
            if destination != chicken.position:
                chicken.facing = 1 if destination[0] >= chicken.position[0] else -1
                chicken.position = destination
                chicken.moving = True

    def can_hunt(self, actor, target, world, *, final=False):
        chicken = self.chickens.get(target) if isinstance(target, str) else None
        if (not chicken or not chicken.alive or actor.incapacitated_until
                or chicken.claimed_by not in (None, actor.id)
                or actor.energy < self.settings.minimum_energy
                or actor.inventory.used >= actor.inventory.capacity
                or self.tick < self.cooldowns.get(actor.id, 0)):
            return False
        pursuit = self.pursuits.get(actor.id)
        if pursuit and (pursuit.chicken_id != target or self.tick >= pursuit.deadline):
            return False
        if final:
            return (pursuit is not None and chicken.claimed_by == actor.id
                    and pursuit.catch_ready_tick > 0 and self.tick >= pursuit.catch_ready_tick
                    and distance(actor.position, chicken.position) <= 1)
        return (actor.position == chicken.position or bool(world.path(actor.position, chicken.position)))

    def begin(self, actor, target):
        chicken = self.chickens[target]
        chicken.claimed_by = actor.id
        self.pursuits[actor.id] = Pursuit(target, self.tick+self.settings.chase_ticks)

    def abort(self, actor_id, reason):
        pursuit = self.pursuits.pop(actor_id, None)
        if pursuit is None:
            return
        chicken = self.chickens.get(pursuit.chicken_id)
        if chicken and chicken.claimed_by == actor_id:
            chicken.claimed_by = None
        self.cooldowns[actor_id] = self.tick+self.settings.cooldown_ticks
        self.events.append({"tick": self.tick, "action": "HUNT_FAILED", "actor_id": actor_id,
                            "target": pursuit.chicken_id, "result": reason})

    def can_attack(self, actor, target):
        chicken = self.chickens.get(target) if isinstance(target, str) else None
        return bool(chicken and chicken.alive and chicken.hp > 0
                    and not actor.incapacitated_until and actor.energy > 0
                    and chicken.claimed_by in (None, actor.id)
                    and distance(actor.position, chicken.position) <= 1
                    and actor.inventory.used < actor.inventory.capacity)

    def attack(self, actor, target):
        """One validated discrete hit. The final hit atomically rewards once."""
        if not self.can_attack(actor, target):
            return False
        chicken = self.chickens[target]
        chicken.hp -= chicken.max_hp//4
        chicken.state, chicken.activity = ChickenState.FLEE, "fleeing"
        chicken.fear_until = self.tick+12
        chicken.calm_until = 0
        chicken.next_move_tick = self.tick+1
        self.events.append({"tick": self.tick, "action": "CHICKEN_HIT",
                            "actor_id": actor.id, "target": target, "hp": chicken.hp,
                            "executed": True, "result": "hit"})
        if chicken.hp == 0:
            self._defeat(actor, chicken)
        return True

    def _defeat(self, actor, chicken):
        # Capacity is validated before damage/hunt; no concurrent mutation here.
        if not chicken.alive or not actor.inventory.add("raw_chicken"):
            raise ValueError("Defeat requires a living target and inventory capacity")
        chicken.hp, chicken.alive, chicken.claimed_by = 0, False, None
        chicken.activity, chicken.moving = "defeated", False
        self.pursuits.pop(actor.id, None)
        self.cooldowns[actor.id] = self.tick+self.settings.cooldown_ticks
        self.respawns.append(self.tick+self.settings.respawn_ticks)

    def complete(self, actor, target):
        # Called only by the common executor after final validation.
        chicken = self.chickens[target]
        if not chicken.alive or actor.inventory.used >= actor.inventory.capacity:
            return False
        self._defeat(actor, chicken)
        actor.energy = max(0, actor.energy-8)
        return True


class VisibleWildlife:
    """Restrict offered HUNT choices and local planning to visible, living targets."""
    def __init__(self, wildlife, visible):
        self._source = wildlife
        self.settings = wildlife.settings
        self.chickens = {c.id: c for c in wildlife.living() if c.position in visible}

    def can_hunt(self, actor, target, world, *, final=False):
        # Observation views offer actions but never authorize world mutation.
        return not final and target in self.chickens and self._source.can_hunt(actor, target, world)
