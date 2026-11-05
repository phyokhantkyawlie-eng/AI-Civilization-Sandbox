"""Typed action requests and one shared validation/execution boundary."""
from dataclasses import dataclass
from enum import Enum

from .inventory import ITEM_DEFINITIONS, select_food
from .agents import Agent
from .resources import Resources
from .world import Position, World


class ActionType(str, Enum):
    MOVE_TO = "MOVE_TO"
    GATHER = "GATHER"
    HUNT = "HUNT"
    COOK = "COOK"
    EAT = "EAT"
    REST = "REST"
    WAIT = "WAIT"
    REQUEST_FOOD = "REQUEST_FOOD"
    SHARE_FOOD = "SHARE_FOOD"
    REFUSE_REQUEST = "REFUSE_REQUEST"
    TALK = "TALK"


@dataclass(frozen=True)
class Action:
    kind: ActionType
    target: Position | str | None = None
    reasoning: str = ""
    request_id: str | None = None
    item: str | None = None


SOCIAL_ACTIONS = {ActionType.REQUEST_FOOD, ActionType.SHARE_FOOD,
                  ActionType.REFUSE_REQUEST, ActionType.TALK}


def valid_position(target) -> bool:
    return (isinstance(target, tuple) and len(target) == 2
            and all(type(value) is int for value in target))


def validate(action: Action, agent: Agent, world: World, resources: Resources, social=None, *, final=False) -> bool:
    if not isinstance(action, Action) or not isinstance(action.kind, ActionType):
        return False
    if action.item is not None and (action.kind != ActionType.EAT or not isinstance(action.item, str)):
        return False
    if agent.incapacitated_until and action.kind not in (ActionType.REST, ActionType.WAIT):
        return False
    if social is not None and social.pacing and social.active_requests(agent):
        if action.kind not in (ActionType.SHARE_FOOD, ActionType.REFUSE_REQUEST,
                               ActionType.EAT, ActionType.REST, ActionType.WAIT):
            return False
    if action.kind in SOCIAL_ACTIONS:
        if action.request_id is not None and not isinstance(action.request_id, str):
            return False
        return social is not None and social.rejection_reason(action, agent) is None
    if action.request_id is not None:
        return False
    if action.kind in (ActionType.MOVE_TO, ActionType.GATHER):
        if not valid_position(action.target):
            return False
        if action.kind == ActionType.MOVE_TO:
            return (agent.energy > 0 and world.walkable(action.target)
                    and bool(world.path(agent.position, action.target)))
        return (agent.energy > 0 and agent.inventory.used < agent.inventory.capacity
                and resources.available(action.target) > 0
                and agent.position in world.neighbors(action.target))
    if action.kind == ActionType.HUNT:
        wildlife = getattr(resources, "wildlife", None)
        return wildlife is not None and wildlife.can_hunt(agent, action.target, world, final=final)
    if action.kind == ActionType.COOK:
        station = getattr(resources, "cooking_station", None)
        return (station is not None and action.target == station.id
                and station.can_cook(agent, world, resources.tick, final=final))
    if action.target is not None:
        return False
    if action.kind == ActionType.EAT:
        return agent.hunger > 0 and select_food(agent, action.item) is not None
    if action.kind == ActionType.REST:
        return agent.energy < 100
    return action.kind == ActionType.WAIT


def execute(action: Action, agent: Agent, world: World, resources: Resources, tick: int, social=None) -> bool:
    """Invalid actions are atomic no-ops. MOVE_TO advances one BFS step."""
    if not validate(action, agent, world, resources, social, final=True):
        return False
    if action.kind == ActionType.HUNT:
        if not resources.wildlife.complete(agent, action.target):
            return False
    elif action.kind == ActionType.COOK:
        if not agent.inventory.convert("raw_chicken", "cooked_chicken"):
            return False
        resources.cooking_station.release(agent.id)
    elif action.kind in SOCIAL_ACTIONS:
        social.perform(action, agent)
    elif action.kind == ActionType.MOVE_TO:
        next_position = world.path(agent.position, action.target)[0]
        dx, dy = next_position[0]-agent.position[0], next_position[1]-agent.position[1]
        agent.facing = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}[(dx, dy)]
        agent.position = next_position
        agent.energy = max(0, agent.energy - 1)
    elif action.kind == ActionType.GATHER:
        resources.collect(action.target, tick, agent.id)
        agent.inventory.add("berries")
        agent.energy = max(0, agent.energy - 2)
    elif action.kind == ActionType.EAT:
        item = select_food(agent, action.item)
        agent.inventory.remove(item)
        agent.hunger = max(0, agent.hunger - ITEM_DEFINITIONS[item].hunger_reduction)
    elif action.kind == ActionType.REST:
        agent.energy = min(100, agent.energy + 8)
    agent.current_action = action.kind.value
    return True
