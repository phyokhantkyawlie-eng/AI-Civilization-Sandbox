"""Environment configuration. Keys are never included in repr or status output."""
from dataclasses import dataclass, field
from pathlib import Path
import os
import math
from .pacing import ActionTiming
from .daynight import DayClock
from .survival import SurvivalRules
from .wildlife import WildlifeSettings

from dotenv import dotenv_values


@dataclass(frozen=True)
class Settings:
    provider: str = "rule-based"
    api_key: str = field(default="", repr=False)
    model: str = ""
    max_calls: int = 40
    cooldown_ticks: int = 40
    timeout_seconds: float = 8.0
    memory_enabled: bool = True
    memory_path: str = "data/social_memory.json"
    wildlife: WildlifeSettings = field(default_factory=WildlifeSettings)
    day_clock: DayClock = field(default_factory=DayClock)
    survival: SurvivalRules = field(default_factory=SurvivalRules)
    action_timing: ActionTiming = field(default_factory=ActionTiming)

    def __post_init__(self):
        if type(self.memory_enabled) is not bool:
            raise ValueError("memory_enabled must be boolean")
        if self.provider not in ("mock", "rule-based", "gemini"):
            raise ValueError("AI_PROVIDER must be mock, rule-based, or gemini")
        if self.max_calls < 0 or self.cooldown_ticks < 1 or not 0.1 <= self.timeout_seconds <= 60:
            raise ValueError("Invalid AI budget, cooldown, or timeout")

    @classmethod
    def load(cls, path: Path | None = None, *, provider: str | None = None):
        # Anchor to the project, not the editor's working directory. Env wins.
        path = path or Path(__file__).resolve().parent.parent / ".env"
        values = {**dotenv_values(path), **os.environ}
        selected = provider or values.get("AI_PROVIDER") or "rule-based"
        # Historical .env files must never activate the archived network adapter.
        if selected == "gemini":
            selected = "rule-based"
        memory_flag = (values.get("MEMORY_ENABLED") or "true").strip().lower()
        if memory_flag not in ("true", "false"):
            raise ValueError("MEMORY_ENABLED must be true or false")
        defaults = {"needs_interval": 1, "gather": 3.5, "eat": 2.5, "greeting": 2, "request": 2, "response": 2.5, "social_cooldown": 10, "rest": 1, "cook": 5}
        timings = {}
        for name, default in defaults.items():
            seconds = float(values.get(name.upper()+"_SECONDS", default))
            if not math.isfinite(seconds) or seconds <= 0:
                raise ValueError("Action durations must be finite and positive")
            timings[name+"_ticks"] = math.ceil(seconds/.25)
        def seconds_to_ticks(name, default):
            seconds = float(values.get(name, default))
            if not math.isfinite(seconds) or seconds <= 0:
                raise ValueError("Clock and recovery durations must be finite and positive")
            return math.ceil(seconds/.25)
        clock = DayClock(seconds_to_ticks("DAY_LENGTH_SECONDS", 600), int(values.get("DAY_START_HOUR", 8)))
        survival = SurvivalRules(
            hungry=int(values.get("SURVIVAL_HUNGRY", 55)),
            inefficient_hunger=int(values.get("HUNGER_SLOW_THRESHOLD", 85)),
            starvation=int(values.get("STARVATION_THRESHOLD", 100)),
            rest_energy=int(values.get("REST_ENERGY_THRESHOLD", 20)),
            collapse_energy=int(values.get("EXHAUSTION_THRESHOLD", 0)),
            recovery_ticks=seconds_to_ticks("RECOVERY_SECONDS", 3),
            grace_ticks=seconds_to_ticks("RECOVERY_GRACE_SECONDS", 30),
            hunger_slowdown=int(values.get("HUNGER_SLOWDOWN", 2)))
        wildlife = WildlifeSettings(
            starting_population=int(values.get("CHICKEN_STARTING_POPULATION", 2)),
            maximum_population=int(values.get("CHICKEN_MAX_POPULATION", 4)),
            respawn_ticks=seconds_to_ticks("CHICKEN_RESPAWN_SECONDS", 60),
            movement_ticks=seconds_to_ticks("CHICKEN_MOVE_SECONDS", 3),
            flee_ticks=seconds_to_ticks("CHICKEN_FLEE_SECONDS", 1),
            threat_radius=int(values.get("CHICKEN_THREAT_RADIUS", 2)),
            chase_ticks=seconds_to_ticks("HUNT_TIMEOUT_SECONDS", 20),
            chase_steps=int(values.get("HUNT_MAX_STEPS", 12)),
            catch_ticks=seconds_to_ticks("HUNT_CATCH_SECONDS", 2),
            cooldown_ticks=seconds_to_ticks("HUNT_COOLDOWN_SECONDS", 40),
            minimum_energy=int(values.get("HUNT_MIN_ENERGY", 12)))
        return cls(wildlife=wildlife, day_clock=clock, survival=survival, action_timing=ActionTiming(**timings), memory_enabled=memory_flag == "true",
                   memory_path=values.get("MEMORY_PATH") or "data/social_memory.json",
                   provider=selected, max_calls=0,
                   cooldown_ticks=int(values.get("AI_DECISION_COOLDOWN_TICKS", "40")))


def create_provider(settings: Settings):
    from .decisions import RuleBasedDecisionProvider
    if settings.provider == "rule-based":
        return RuleBasedDecisionProvider()
    if settings.provider == "mock":
        from .ai import MockDecisionProvider
        return MockDecisionProvider(settings)
    raise ValueError("External providers are disabled in the offline-first application")
