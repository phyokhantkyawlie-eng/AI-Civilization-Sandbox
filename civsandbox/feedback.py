"""Bounded visual feedback from committed simulation events only."""
from dataclasses import dataclass

ANIMATION_STATES = ("idle", "walk", "gather", "eat", "rest", "talk", "share", "cook")
ACTION_STATES = {"COOK": "cook", "HUNT": "idle", "GATHER": "gather", "EAT": "eat", "REST": "rest",
                 "REQUEST_FOOD": "talk", "REFUSE_REQUEST": "talk", "TALK": "talk", "SHARE_FOOD": "share"}
LABELS = {"COOK": "Cooked chicken", "HUNT": "Collected raw chicken", "GATHER": "Gathered food", "EAT": "Ate food", "REST": "Resting",
          "REQUEST_FOOD": "Asked for food", "SHARE_FOOD": "Shared food",
          "REFUSE_REQUEST": "Refused", "TALK": "Greeting"}
TEMPLATES = {"REQUEST_FOOD": "Could you spare some food?", "SHARE_FOOD": "Here is some food.",
             "REFUSE_REQUEST": "I need to keep my food.", "TALK": "Hello!"}


@dataclass(frozen=True)
class Notice:
    actor_id: str
    label: str
    speech: str
    reaction: str
    state: str
    expires: float


class Feedback:
    lifetime = 3.0

    def __init__(self):
        self.clock = 0.0
        self.last_event = 0
        self.notices = {}

    def advance(self, elapsed):
        self.clock += elapsed
        self.notices = {key: value for key, value in self.notices.items() if value.expires > self.clock}

    def consume(self, events):
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
            previous = self.notices.get(actor)
            if previous and previous.state == "rest" and action != "REST" and event.get("executed"):
                self.notices.pop(actor, None)
            if (event.get("executed") or event.get("accepted_start")) and action in LABELS:
                # Keep sustained rest unobtrusive; each rest transition gets one notice.
                if action == "REST" and not event.get("changed"):
                    continue
                speech = ""
                if action in TEMPLATES and event.get("phase") != "completed":
                    source = event.get("decision_source", "rule-based")
                    reason = event.get("public_reason")
                    if source == "gemini" and reason:
                        speech = "Gemini explanation: " + reason
                    else:
                        prefix = "Mock template" if source == "mock" else "Rule-based template"
                        speech = prefix + ": " + TEMPLATES[action]
                label = {"COOK": "Cooking chicken", "HUNT": "Pursuing chicken", "GATHER": "Gathering berries", "EAT": "Eating"}.get(action, LABELS[action]) if event.get("accepted_start") else LABELS[action]
                self.notices[actor] = Notice(actor, label, speech, "",
                                             ACTION_STATES[action], self.clock+max(self.lifetime, event.get("duration_seconds", 0)))
            if event.get("social"):
                result = event.get("result")
                recipient = event.get("target_id")
                reaction = {"pending": "Surprised", "shared one food": "Happy",
                            "refused": "Angry"}.get(result)
                if result == "expired":
                    recipient, reaction = actor, "Worried"
                if recipient and reaction:
                    # Reactions use a separate channel so an executed action stays visible.
                    self.notices[(recipient, "reaction")] = Notice(
                        recipient, "", "", reaction, "idle", self.clock+self.lifetime)

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
