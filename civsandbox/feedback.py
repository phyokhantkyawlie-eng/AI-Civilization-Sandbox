"""Bounded visual feedback from committed simulation events only."""
from dataclasses import dataclass
from collections import deque

ANIMATION_STATES = ("idle", "walk", "gather", "eat", "rest", "talk", "share", "cook")
ACTION_STATES = {"COOK": "cook", "HUNT": "idle", "GATHER": "gather", "EAT": "eat", "REST": "rest",
                 "REQUEST_FOOD": "talk", "REFUSE_REQUEST": "talk", "TALK": "talk", "SHARE_FOOD": "share"}
LABELS = {"COOK": "Cooked chicken", "HUNT": "Collected raw chicken", "GATHER": "Gathered food", "EAT": "Ate food", "REST": "Resting",
          "REQUEST_FOOD": "Asked for food", "SHARE_FOOD": "Shared food",
          "REFUSE_REQUEST": "Refused", "TALK": "Greeting"}


@dataclass(frozen=True)
class Notice:
    actor_id: str
    label: str
    speech: str
    reaction: str
    state: str
    expires: float
    session_id: str | None = None


class Feedback:
    lifetime = 3.0

    def __init__(self):
        self.clock = 0.0
        self.last_event = 0
        self.notices = {}
        self.dialogue_queue = deque(maxlen=64)
        self.history = deque(maxlen=60)
        self.current_dialogue = None
        self.reading_remaining = 0.0
        self.social = None

    def advance(self, elapsed):
        self.clock += elapsed
        self.notices = {key: value for key, value in self.notices.items() if value.expires > self.clock}

    def advance_reading(self, elapsed, paused=False):
        if paused:
            return
        while self.current_dialogue is not None and elapsed >= self.reading_remaining:
            elapsed -= self.reading_remaining
            self.current_dialogue = None
            self.start_next_line()
        if self.current_dialogue is not None:
            self.reading_remaining -= elapsed

    def start_next_line(self):
        if self.current_dialogue is None and self.dialogue_queue:
            self.current_dialogue = self.dialogue_queue.popleft()
            self.reading_remaining = self.current_dialogue['reading_seconds']

    def speech_notice(self):
        entry = self.current_dialogue
        if entry is None or self.social is None:
            return None
        actor = self.social.agents.get(entry['actor_id'])
        session = self.social.session_for(actor) if actor else None
        if not session or session.id != entry['session_id'] or not self.social.engaged(actor):
            return None
        return Notice(actor.id,'',entry['text'],'','talk',self.clock+1,session.id)

    def consume(self, events, social=None):
        if social is not None:
            self.social = social
        fresh = []
        for event in reversed(events):
            if event.get("event_id", 0) <= self.last_event:
                break
            fresh.append(event)
        for event in reversed(fresh):
            self.last_event = event["event_id"]
            actor = event.get("actor_id")
            action = event.get("activity_action", event["action"])
            if action == "HUNT_FAILED":
                self.notices[actor] = Notice(actor, "Hunt ended", "", "", "idle", self.clock+self.lifetime)
            if action == 'DIALOGUE':
                session = self.social.sessions.get(event.get('session_id')) if self.social else None
                index = event.get('turn')
                if (session and event.get('session_validated') and type(index) is int
                        and 0 <= index < len(session.turns)):
                    turn = session.turns[index]
                    if turn.delivered and turn.speaker_id == actor and turn.text == event.get('text'):
                        entry = {key:event[key] for key in ('tick','session_id','actor_id','target_id','turn','text','reading_seconds')}
                        self.history.append(entry)
                        self.dialogue_queue.append(entry)
                        self.start_next_line()
                continue
            # Social action notices are represented by verified session dialogue only.
            if action in ('TALK','REQUEST_FOOD','SHARE_FOOD','REFUSE_REQUEST','OFFER_FOOD'):
                if (event.get('social') and self.social and event.get('session_id') in self.social.sessions
                        and event.get('result') in ('shared one food','offered one food')):
                    recipient=event.get('target_id')
                    self.notices[(recipient,'reaction')]=Notice(recipient,'','','Happy','idle',self.clock+self.lifetime)
                continue
            previous = self.notices.get(actor)
            if previous and previous.state == "rest" and action != "REST" and event.get("executed"):
                self.notices.pop(actor, None)
            if (event.get("executed") or event.get("accepted_start")) and action in LABELS:
                # Keep sustained rest unobtrusive; each rest transition gets one notice.
                if action == "REST" and not event.get("changed"):
                    continue
                speech = ""
                label = {"COOK": "Cooking chicken", "HUNT": "Pursuing chicken", "GATHER": "Gathering berries", "EAT": "Eating"}.get(action, LABELS[action]) if event.get("accepted_start") else LABELS[action]
                self.notices[actor] = Notice(actor, label, speech, "",
                                             ACTION_STATES[action], self.clock+max(self.lifetime, event.get("duration_seconds", 0)))

    def state_for(self, actor_id, moving):
        if moving:
            return "walk"
        notice = self.notices.get(actor_id)
        return notice.state if notice else "idle"

    @staticmethod
    def sprite_state(state):
        if state not in ANIMATION_STATES:
            raise ValueError("Unknown animation state")
        return "walk" if state == "walk" else "idle"
