"""Local observations and valid choices; unknown terrain is never routed through."""
from dataclasses import asdict

from .actions import Action, ActionType, validate
from .world import Tile, World


class VisibleResources:
    def __init__(self, stocks):
        self._stocks = stocks

    def stocks(self):
        return self._stocks.copy()

    def available(self, position):
        return self._stocks.get(position, 0)


def observe(agent, world, resources, agents=(), radius=4, social=None):
    x, y = agent.position
    visible = {(tx, ty) for ty in range(max(0, y-radius), min(world.height, y+radius+1))
               for tx in range(max(0, x-radius), min(world.width, x+radius+1))
               if abs(tx-x)+abs(ty-y) <= radius}
    local_world = World(tuple(tuple(tile if (tx, ty) in visible else Tile.WATER
                                   for tx, tile in enumerate(row))
                             for ty, row in enumerate(world.tiles)))
    local_resources = VisibleResources({p: food for p, food in resources.stocks().items()
                                        if p in visible})
    candidates = [Action(kind) for kind in (ActionType.EAT, ActionType.REST, ActionType.WAIT)]
    candidates += [Action(ActionType.MOVE_TO, p) for p in local_world.reachable(agent.position)
                   if p != agent.position]
    candidates += [Action(ActionType.GATHER, p) for p in local_resources.stocks()]
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
                  "position": list(agent.position),
                  "goal": asdict(agent.goal) if agent.goal else None},
        "visibility": "Manhattan radius 4; no vision occlusion; unknown tiles unavailable",
        "nearby_npcs": [{"id": a.id, "name": a.name, "position": list(a.position),
                        **({"looks_hungry": a.hunger >= 55, "carrying_food": a.food > 0}
                           if social and social.nearby(agent, a) else {})} for a in agents
                        if a.id != agent.id and a.position in visible],
        "tiles": [{"position": [tx, ty], "terrain": world.tiles[ty][tx].value}
                  for tx, ty in sorted(visible)],
        "resources": [{"position": list(p), "food": food}
                      for p, food in local_resources.stocks().items()],
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
    return {"action": action.kind.value, "target": target, "request_id": action.request_id}
