"""Environment configuration. Keys are never included in repr or status output."""
from dataclasses import dataclass, field
from pathlib import Path
import os
import math
from .pacing import ActionTiming

from dotenv import dotenv_values


@dataclass(frozen=True)
class Settings:
    provider: str = "mock"
    api_key: str = field(default="", repr=False)
    model: str = ""
    max_calls: int = 40
    cooldown_ticks: int = 40
    timeout_seconds: float = 8.0
    memory_enabled: bool = True
    memory_path: str = "data/social_memory.json"
    action_timing: ActionTiming = field(default_factory=ActionTiming)

    def __post_init__(self):
        if type(self.memory_enabled) is not bool:
            raise ValueError("memory_enabled must be boolean")
        if self.provider not in ("mock", "rule-based", "gemini"):
            raise ValueError("AI_PROVIDER must be mock, rule-based, or gemini")
        if self.max_calls < 0 or self.cooldown_ticks < 1 or not 0.1 <= self.timeout_seconds <= 60:
            raise ValueError("Invalid AI budget, cooldown, or timeout")

    @classmethod
    def load(cls, path: Path | None = None):
        # Anchor to the project, not the editor's working directory. Env wins.
        path = path or Path(__file__).resolve().parent.parent / ".env"
        values = {**dotenv_values(path), **os.environ}
        memory_flag = (values.get("MEMORY_ENABLED") or "true").strip().lower()
        if memory_flag not in ("true", "false"):
            raise ValueError("MEMORY_ENABLED must be true or false")
        defaults = {"needs_interval": 1, "gather": 3.5, "eat": 2.5, "greeting": 2, "request": 2, "response": 2.5, "social_cooldown": 10}
        timings = {}
        for name, default in defaults.items():
            seconds = float(values.get(name.upper()+"_SECONDS", default))
            if not math.isfinite(seconds) or seconds <= 0:
                raise ValueError("Action durations must be finite and positive")
            timings[name+"_ticks"] = math.ceil(seconds/.25)
        return cls(action_timing=ActionTiming(**timings), memory_enabled=memory_flag == "true",
                   memory_path=values.get("MEMORY_PATH") or "data/social_memory.json",
                   provider=values.get("AI_PROVIDER", "mock"),
                   api_key=values.get("GEMINI_API_KEY") or "",
                   model=values.get("GEMINI_MODEL") or "",
                   max_calls=int(values.get("MAX_AI_CALLS_PER_RUN", "40")),
                   cooldown_ticks=int(values.get("AI_DECISION_COOLDOWN_TICKS", "40")),
                   timeout_seconds=float(values.get("AI_TIMEOUT_SECONDS", "8")))


def create_provider(settings: Settings):
    from .ai import GeminiDecisionProvider, MockDecisionProvider
    from .decisions import RuleBasedDecisionProvider
    if settings.provider == "rule-based":
        return RuleBasedDecisionProvider()
    if settings.provider == "gemini":
        return GeminiDecisionProvider(settings)
    return MockDecisionProvider(settings)
