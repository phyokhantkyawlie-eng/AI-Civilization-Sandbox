"""Local observations and valid choices; unknown terrain is never routed through."""
from dataclasses import asdict

from .inventory import ITEM_DEFINITIONS, edible_count
from .actions import Action, ActionType, validate
from .world import Tile, World
from .wildlife import VisibleWildlife
from .cooking import CookingObservation


class VisibleResources:
    def __init__(self, stocks, wildlife=None, cooking_station=None, tick=0):
        self._stocks = stocks
        self.wildlife = wildlife
        self.cooking_station = cooking_station
        self.tick = tick

    def stocks(self):
        return self._stocks.copy()

    def available(self, position):
        return self._stocks.get(position, 0)


def observe(agent, world, resources, agents=(), radius=4, social=None):
    hungry = social.pacing.survival.hungry if social and social.pacing else 55
    x, y = agent.position
    visible = {(tx, ty) for ty in range(max(0, y-radius), min(world.height, y+radius+1))
               for tx in range(max(0, x-radius), min(world.width, x+radius+1))
               if abs(tx-x)+abs(ty-y) <= radius}
    local_world = World(tuple(tuple(tile if (tx, ty) in visible else Tile.WATER
                                   for tx, tile in enumerate(row))
                             for ty, row in enumerate(world.tiles)))
    local_resources = VisibleResources({p: food for p, food in resources.stocks().items()
                                        if p in visible},
                                      VisibleWildlife(resources.wildlife, visible) if getattr(resources, "wildlife", None) else None,
                                      CookingObservation(**asdict(resources.cooking_station)) if getattr(resources,"cooking_station",None) and resources.cooking_station.position in visible else None,
                                      getattr(resources,"tick",0))
    candidates = [Action(kind) for kind in (ActionType.EAT, ActionType.REST, ActionType.WAIT)]
    candidates += [Action(ActionType.EAT,item=key) for key,d in ITEM_DEFINITIONS.items() if d.hunger_reduction>0]
    if local_resources.cooking_station:
        candidates.append(Action(ActionType.COOK,local_resources.cooking_station.id))
    candidates += [Action(ActionType.MOVE_TO, p) for p in local_world.reachable(agent.position)
                   if p != agent.position]
    candidates += [Action(ActionType.GATHER, p) for p in local_resources.stocks()]
    if local_resources.wildlife:
        candidates += [Action(ActionType.HUNT, key) for key in local_resources.wildlife.chickens]
    if social:
        for other in agents:
            if other.id != agent.id and other.position in visible:
                candidates += [Action(kind, other.id) for kind in (ActionType.REQUEST_FOOD, ActionType.TALK)]
        for request in social.active_requests(agent):
            if request.recipient_id == agent.id:
                candidates += [Action(kind, request.requester_id, request_id=request.id)
                               for kind in (ActionType.SHARE_FOOD, ActionType.REFUSE_REQUEST)]
    choices = [a for a in candidates if validate(a, agent, local_world, local_resources, social)]
    context = {
        "agent": {"id": agent.id, "name": agent.name, "personality_name": agent.personality_name, "personality": agent.personality.copy(),
                  "hunger": agent.hunger, "energy": agent.energy, "food": agent.food,
                  "inventory": agent.inventory.items.copy(),
                  "position": list(agent.position),
                  "goal": asdict(agent.goal) if agent.goal else None},
        "visibility": "Manhattan radius 4; no vision occlusion; unknown tiles unavailable",
        "nearby_npcs": [{"id": a.id, "name": a.name, "position": list(a.position),
                        **({"looks_hungry": a.hunger >= hungry, "carrying_food": edible_count(a) > 0, "carrying_berries": a.food > 0}
                           if social and social.nearby(agent, a) else {})} for a in agents
                        if a.id != agent.id and a.position in visible],
        "tiles": [{"position": [tx, ty], "terrain": world.tiles[ty][tx].value}
                  for tx, ty in sorted(visible)],
        "resources": [{"position": list(p), "food": food}
                      for p, food in local_resources.stocks().items()],
        "cooking_station": asdict(local_resources.cooking_station) if local_resources.cooking_station else None,
        "nearby_chickens": [{"id": c.id, "position": list(c.position), "state": c.state.value}
                            for c in local_resources.wildlife.chickens.values()] if local_resources.wildlife else [],
        "valid_actions": [action_dict(a) for a in choices],
    }
    if social:
        context["social"] = {
            "tick": social.tick,
            "interaction_range": social.interaction_range,
            "active_requests": [asdict(r) for r in social.active_requests(agent)],
        }
        if social.memory_enabled:
            peers = {a.id for a in agents if a.id != agent.id and a.position in visible}
            context["social"]["relationships"] = {p: social.trust_for(agent, p) for p in sorted(peers)}
            context["social"]["memories"] = social.relevant_memories(agent, peers)
    return context, choices, local_world, local_resources


def action_dict(action):
    target = action.target
    if isinstance(target, tuple):
        target = {"x": target[0], "y": target[1]}
    return {"action": action.kind.value, "target": target, "request_id": action.request_id,
            **({"item":action.item} if action.item is not None else {})}
