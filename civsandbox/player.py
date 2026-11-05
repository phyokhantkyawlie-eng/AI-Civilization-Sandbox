"""Human choices for an existing agent; all effects remain in the shared executor."""
from dataclasses import dataclass

from .actions import Action, ActionType, SOCIAL_ACTIONS, validate
from .agents import Goal


@dataclass
class PlayerPrompt:
    actor_id: str
    action: Action
    request_id: str | None = None
    remaining_seconds: float = 30.0


class PlayerController:
    name = 'player'

    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.command = None
        self.direction = None
        self.resting = False
        self.pending = None
        self.approved = None
        self.responding_request = None
        self.message = 'WASD/arrows: move. E: interact. I: inventory. M: modes.'

    def clear(self):
        self.command = self.direction = None
        self.resting = False

    def submit(self, action, sim):
        actor = sim.social.agents[self.agent_id]
        if self.pending:
            self.message = 'Answer the current invitation first.'
            return False
        if sim.progress.held(actor) and not sim.social.needs_response(actor):
            self.message = 'Finish this activity or press Backspace to cancel.'
            return False
        if not validate(action, actor, sim.world, sim.resources, sim.social):
            from .ui_state import unavailable_reason
            self.message = unavailable_reason(action,actor,sim)
            return False
        self.clear()
        self.command = action
        self.resting = action.kind == ActionType.REST
        self.message = 'Selected: '+action.kind.value.replace('_', ' ').lower()
        return True

    def decide(self, actor, world, resources, rng):
        if self.command:
            action, self.command = self.command, None
            actor.goal = Goal('player '+action.kind.value.lower(), action.target or actor.position)
            return action
        if self.direction:
            dx, dy = self.direction
            actor.goal = None
            return Action(ActionType.MOVE_TO, (actor.position[0]+dx, actor.position[1]+dy), 'Player grid movement')
        if self.resting and actor.energy < 100:
            return Action(ActionType.REST, reasoning='Player chose to rest until recovered')
        self.resting = False
        actor.goal = None
        return Action(ActionType.WAIT, reasoning='Waiting for player input')

    def cancel(self, sim):
        self.clear()
        sim.progress.cancel_for(self.agent_id)
        sim.social.cancel_for(sim.social.agents[self.agent_id], "Player canceled activity")
        self.responding_request = None
        self.message = 'Activity canceled; unfinished ingredients and resources are retained.'

    def intercept(self, action, actor, sim):
        """Request human consent before an NPC starts a new social action."""
        if (not isinstance(action, Action) or not isinstance(action.kind, ActionType)
                or actor.id == self.agent_id or action.kind not in SOCIAL_ACTIONS
                or action.target != self.agent_id
                or action.kind in (ActionType.SHARE_FOOD, ActionType.REFUSE_REQUEST)):
            return False
        if self.approved:
            owner, accepted, deadline = self.approved
            if sim.tick > deadline:
                self.approved = None
            elif owner == actor.id and accepted == action:
                self.approved = None
                return False
            else:
                return True  # Defer other invitations until this accepted action starts.
        if not validate(action, actor, sim.world, sim.resources, sim.social):
            return False
        self.clear()
        self.pending = PlayerPrompt(actor.id, action)
        self.message = actor.name+' would like to interact. World paused for your choice.'
        return True

    def refresh(self, sim):
        if self.pending:
            return
        actor = sim.social.agents[self.agent_id]
        for request in sim.social.active_requests(actor):
            if request.recipient_id == actor.id and request.id != self.responding_request:
                self.clear()
                self.pending = PlayerPrompt(request.requester_id,
                                            Action(ActionType.REQUEST_FOOD, actor.id), request.id)
                self.message = sim.social.agents[request.requester_id].name+' asks for a berry.'
                return

    def answer(self, sim, accept):
        prompt = self.pending
        if prompt is None:
            return False
        actor = sim.social.agents[self.agent_id]
        if prompt.request_id:
            action = Action(ActionType.SHARE_FOOD if accept else ActionType.REFUSE_REQUEST,
                            prompt.actor_id, request_id=prompt.request_id,
                            reasoning='Player response to an actual request')
            if not validate(action, actor, sim.world, sim.resources, sim.social):
                self.message = 'Cannot share now; choose refusal or cancel.'
                return False
            self.pending = None
            self.responding_request = prompt.request_id
            return self.submit(action, sim)
        self.pending = None
        if accept:
            self.approved = (prompt.actor_id, prompt.action, sim.tick+64)
            self.message = 'Invitation accepted; the action will be revalidated.'
        else:
            self.decline(sim, prompt, 'Player declined invitation')
        return True

    def decline(self, sim, prompt, reason):
        peer = sim.social.agents[prompt.actor_id]
        session = sim.social.session_for(peer)
        if session:
            sim.social.cancel_session(session.id, reason)
        if prompt.request_id and prompt.request_id in sim.social.pending:
            sim.social.cancel_for(sim.social.agents[self.agent_id], reason)
        if hasattr(sim.decision_provider, 'interrupt'):
            sim.decision_provider.interrupt(peer, reason, sim.tick)
        if not prompt.request_id:
            # Actual requests already receive one cancellation event/memory from
            # SocialSystem; an invitation needs its own cancellation record.
            sim.social.record(self.agent_id, peer.id, 'TALK', reason, {})
        pair = tuple(sorted((self.agent_id, peer.id)))
        sim.social.pair_cooldowns[pair] = sim.social.tick+sim.social.settings.pair_cooldown_ticks
        self.message = reason+'; no food transferred.'

    def advance_prompt(self, elapsed, sim):
        if not self.pending:
            return
        self.pending.remaining_seconds -= elapsed
        if self.pending.remaining_seconds <= 0:
            prompt, self.pending = self.pending, None
            self.decline(sim, prompt, 'Unattended interaction canceled after 30 seconds')


def nearby_options(sim):
    """Current physical context, never an inventory or world-state copy."""
    if not sim.player:
        return []
    actor = sim.social.agents[sim.player.agent_id]
    options = []
    for position, bush in sim.resources.bushes.items():
        if actor.position in sim.world.neighbors(position):
            options.append((f'Bush: gather ({bush.quantity}/{bush.capacity})', Action(ActionType.GATHER, position), ('bush', position)))
    for chicken in sim.wildlife.living():
        if sum(abs(a-b) for a, b in zip(actor.position, chicken.position)) <= 1:
            options.append(('Chicken: hunt', Action(ActionType.HUNT, chicken.id), ('chicken', chicken.id)))
    station = sim.cooking_station
    if actor.position in sim.world.neighbors(station.position):
        options.append(('Campfire: cook raw chicken', Action(ActionType.COOK, station.id), ('station', station.id)))
    for peer in sim.agents:
        if peer is actor or not sim.social.nearby(actor, peer):
            continue
        for label, kind in (('Talk', ActionType.TALK), ('Ask for a berry', ActionType.REQUEST_FOOD),
                            ('Offer a berry', ActionType.OFFER_FOOD)):
            options.append((peer.name+': '+label, Action(kind, peer.id), ('npc', peer.id)))
    return options
