"""Structured decisions, local planning, and bounded nonblocking Gemini requests."""
from dataclasses import dataclass, field
import json
import re
import random
import threading
import time

from .actions import Action, ActionType, SOCIAL_ACTIONS, validate
from .agents import Goal
from .config import Settings
from .decisions import RuleBasedDecisionProvider
from .perception import action_dict, observe

DECISION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["action", "target", "reasoning"],
    "properties": {
        "action": {"type": "string", "enum": [a.value for a in ActionType]},
        "target": {"anyOf": [{"type": "null"}, {"type": "string"}, {
            "type": "object", "additionalProperties": False,
            "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
            "required": ["x", "y"]}]},
        "request_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "reasoning": {"type": "string", "minLength": 1, "maxLength": 160},
    },
}


def safe_text(value, secret=""):
    if secret:
        value = value.replace(secret, "[redacted]")
    value = re.sub(r"AIza[\w-]+", "[redacted]", value)
    value = "".join(c if c.isprintable() else " " for c in value)
    return " ".join(value.split())[:160]


def parse_decision(raw: str, secret="") -> Action:
    """Strict parsing; never evaluate or execute model-generated code."""
    if not isinstance(raw, str) or len(raw) > 4096:
        raise ValueError("Invalid decision payload")
    data = json.loads(raw)
    if (not isinstance(data, dict) or not {"action", "target", "reasoning"} <= set(data)
            or set(data)-{"action", "target", "reasoning", "request_id"}):
        raise ValueError("Malformed decision")
    if (not isinstance(data["reasoning"], str) or not 1 <= len(data["reasoning"]) <= 160
            or not data["reasoning"].strip()):
        raise ValueError("Invalid reasoning")
    kind = ActionType(data["action"])
    target = data["target"]
    request_id = data.get("request_id")
    if request_id is not None and (not isinstance(request_id, str) or not request_id):
        raise ValueError("Invalid request ID")
    if kind in SOCIAL_ACTIONS:
        if not isinstance(target, str) or not target or len(target) > 80:
            raise ValueError("Invalid NPC target")
        if (kind in (ActionType.SHARE_FOOD, ActionType.REFUSE_REQUEST)) != (request_id is not None):
            raise ValueError("Request ID does not match action")
    else:
        if request_id is not None:
            raise ValueError("Unexpected request ID")
        if target is not None:
            if (not isinstance(target, dict) or set(target) != {"x", "y"}
                    or any(type(v) is not int for v in target.values())):
                raise ValueError("Invalid target")
            target = (target["x"], target["y"])
        if (kind in (ActionType.MOVE_TO, ActionType.GATHER)) != (target is not None):
            raise ValueError("Target does not match action")
    return Action(kind, target, safe_text(data["reasoning"], secret), request_id)


@dataclass
class Job:
    started: float
    choices: list[Action]
    submitted_tick: int
    done: threading.Event = field(default_factory=threading.Event)
    raw: str | None = None
    error: str | None = None
    expired: bool = False
    finished: float | None = None


class PlanningDecisionProvider:
    """Main-thread scheduler shared by offline mock and Gemini providers."""
    name = "mock"

    def __init__(self, settings=None):
        self.settings = settings or Settings()
        self.tick = 0
        self.agents = ()
        self.api_calls = 0
        self.requests = 0
        self.last_request = {}
        self.plans = {}
        self.status = {}
        self.audit_events = []
        self.rule = RuleBasedDecisionProvider()
        self.closed = False
        self.social = None

    def bind_social(self, social):
        self.social = social
        self.rule.bind_social(social)

    def begin_tick(self, tick, agents):
        self.tick, self.agents = tick, agents

    def report(self, agent, action=None, explanation=None, fallback=False, reason=""):
        state = self.status.setdefault(agent.id, {"decision": "none", "explanation": ""})
        if action is not None:
            state.update(decision=action.kind.value, explanation=explanation or action.reasoning)
        state.update(fallback=fallback, reason=reason)
        marker = (state["decision"], state["explanation"], fallback, reason)
        if state.get("_marker") != marker:
            state["_marker"] = marker
            self.audit_events.append({"tick": self.tick, "agent": agent.name,
                                      "action": "AI_DECISION", "provider": self.name,
                                      **{k: v for k, v in state.items() if k != "_marker"}})

    def summary(self):
        return {"provider": self.name, "api_calls": self.api_calls,
                "max_calls": self.settings.max_calls, "requests": self.requests,
                "agents": {key: {k: v for k, v in state.items() if k != "_marker"}
                           for key, state in self.status.items()}}

    def accept(self, raw, choices, agent, world, resources):
        try:
            action = parse_decision(raw, self.settings.api_key)
        except (ValueError, TypeError, KeyError, RecursionError):
            return None, "malformed response"
        if not any(action.kind == c.kind and action.target == c.target and action.request_id == c.request_id for c in choices):
            return None, "action was not an offered choice"
        if not validate(action, agent, world, resources, self.social):
            return None, "decision became invalid before execution"
        self.plans[agent.id] = action
        if isinstance(action.target, tuple):
            agent.goal = Goal("ai", action.target)
        self.report(agent, action, fallback=False)
        return action, ""

    def usable_plan(self, agent, world, resources):
        action = self.plans.get(agent.id)
        if not action:
            return None
        complete = (action.kind in ({ActionType.EAT, ActionType.WAIT} | SOCIAL_ACTIONS)
                    or (action.kind == ActionType.REST and agent.energy >= 70)
                    or (action.kind == ActionType.GATHER and agent.food >= 2))
        if complete or not validate(action, agent, world, resources, self.social):
            self.plans.pop(agent.id, None)
            return None
        return action

    def decide(self, agent, world, resources, rng):
        context, choices, local_world, local_resources = observe(
            agent, world, resources, self.agents, social=self.social)
        # Emergency needs interrupt long-running AI goals without another API call.
        if (agent.food and agent.hunger >= 70) or agent.energy <= 5:
            self.plans.pop(agent.id, None)
            return self.fallback(agent, local_world, local_resources, rng, "urgent need")
        if self.social and any(r.recipient_id == agent.id for r in self.social.active_requests(agent)):
            self.plans.pop(agent.id, None)
        action, reason = self.poll(agent, local_world, local_resources)
        if action:
            return action
        plan = self.usable_plan(agent, local_world, local_resources)
        if plan:
            self.report(agent, plan, fallback=False)
            return plan
        if not reason and self.tick - self.last_request.get(agent.id, -10**9) >= self.settings.cooldown_ticks:
            self.last_request[agent.id] = self.tick
            action, reason = self.request(context, choices, agent, local_world, local_resources)
            if action:
                return action
        return self.fallback(agent, local_world, local_resources, rng, reason or "decision cooldown")

    def local_action(self, agent, world, resources, rng):
        search_goal = agent.goal
        action = self.rule.decide(agent, world, resources, rng)
        if action.kind != ActionType.WAIT or (self.social and self.social.active_requests(agent)):
            return action
        # No known food is different from no food anywhere: explore visible terrain.
        if search_goal and search_goal.purpose == "search":
            move = Action(ActionType.MOVE_TO, search_goal.target)
            if validate(move, agent, world, resources, self.social):
                agent.goal = search_goal
                return move
        destinations = [p for p in world.reachable(agent.position) if p != agent.position]
        if destinations and agent.energy > 0:
            agent.goal = Goal("search", rng.choice(destinations))
            return Action(ActionType.MOVE_TO, agent.goal.target)
        return action

    def fallback(self, agent, world, resources, rng, reason):
        action = self.local_action(agent, world, resources, rng)
        if reason == "request pending" and action.kind == ActionType.GATHER:
            # Leave a pending high-level choice time to arrive before starting a long harvest.
            action = Action(ActionType.WAIT)
        self.report(agent, fallback=True, reason=reason)
        return action

    def poll(self, agent, world, resources):
        return None, ""

    def close(self):
        self.closed = True


class MockDecisionProvider(PlanningDecisionProvider):
    """Deterministic offline stand-in. Never calls or impersonates Gemini."""
    name = "mock"

    def __init__(self, settings=None, responses=None):
        super().__init__(settings)
        self.responses = iter(responses) if responses is not None else None

    def request(self, context, choices, agent, world, resources):
        if self.closed:
            return None, "provider closed"
        self.requests += 1
        if self.responses is not None:
            raw = next(self.responses, "{}")
        else:
            chosen = self.local_action(agent, world, resources, random.Random(self.tick))
            raw = json.dumps({**action_dict(chosen), "reasoning": "Offline mock: local needs and resources."})
        return self.accept(raw, choices, agent, world, resources)


class GeminiDecisionProvider(PlanningDecisionProvider):
    name = "gemini"
    max_inflight = 4

    def __init__(self, settings=None, transport=None, clock=time.monotonic):
        super().__init__(settings)
        self.transport = transport or self.generate
        self.clock = clock
        self.pending: dict[str, Job] = {}

    def summary(self):
        result = super().summary()
        result["mode"] = ("online" if self.settings.api_key and self.settings.model
                          else "offline rules")
        return result

    def request(self, context, choices, agent, world, resources):
        if self.closed:
            return None, "provider closed"
        if agent.id in self.pending:
            return None, "request pending"
        if not self.settings.api_key or not self.settings.model:
            return None, "missing API key or model"
        if self.api_calls >= self.settings.max_calls:
            return None, "API budget exhausted"
        if len(self.pending) >= self.max_inflight:
            return None, "request capacity reached"
        job = Job(self.clock(), choices, self.tick)
        self.pending[agent.id] = job
        self.api_calls += 1  # Reserve before dispatch; failures also consume budget.
        self.requests += 1
        threading.Thread(target=self.run_job, args=(job, context), daemon=True,
                         name="gemini-decision").start()
        return None, "request pending"

    def run_job(self, job, context):
        try:
            job.raw = self.transport(context)
        except Exception as error:
            # Exception messages and raw responses can contain credentials: never log them.
            job.error = "rate limited" if getattr(error, "code", None) == 429 else "API request failed"
        finally:
            job.finished = self.clock()
            job.done.set()

    def poll(self, agent, world, resources):
        job = self.pending.get(agent.id)
        if not job:
            return None, ""
        end = job.finished if job.done.is_set() else self.clock()
        if end - job.started >= self.settings.timeout_seconds:
            job.expired = True
        if job.expired:
            if job.done.is_set():
                self.pending.pop(agent.id)
            # Retain an unfinished job's slot; never spawn unbounded timed-out workers.
            return None, "request timed out"
        if not job.done.is_set():
            return None, "request pending"
        self.pending.pop(agent.id)
        if job.error:
            return None, job.error
        if self.tick - job.submitted_tick >= 12:
            return None, "stale decision (12 simulation ticks elapsed)"
        return self.accept(job.raw, job.choices, agent, world, resources)

    def generate(self, context):
        from google import genai
        from google.genai import types
        # No automatic retries: every SDK request is accounted for in the run budget.
        with genai.Client(api_key=self.settings.api_key, http_options=types.HttpOptions(
            timeout=int(self.settings.timeout_seconds * 1000),
            retry_options=types.HttpRetryOptions(attempts=1),
        )) as client:
            response = client.models.generate_content(
                model=self.settings.model,
                contents=json.dumps(context),
                config=types.GenerateContentConfig(
                    system_instruction=("Choose one offered valid action for this villager. "
                        "Manage hunger and energy; gather food nearby or explore visible tiles. "
                        "MOVE_TO persists until arrival, REST until recovered, GATHER until stocked. "
                        "Social actions use NPC ID targets. SHARE_FOOD and REFUSE_REQUEST require an active "
                        "request_id; do not invent one. Consider numeric personality, current needs, active "
                        "requests, and any supplied relevant memories and directed relationships. "
                        "No history fields means historical knowledge is unavailable. "
                        "Social actions execute once. Use only observed information. Give one short player-facing reason based on visible facts. Omit internal deliberation and code."),
                    response_mime_type="application/json", response_json_schema=DECISION_SCHEMA,
                    max_output_tokens=512, temperature=0.2,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            return response.text
