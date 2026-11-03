"""Run with python -m civsandbox; headless mode never imports Pygame."""
import argparse
import json
import math

from .simulation import Simulation
from .config import Settings, create_provider


def main():
    parser = argparse.ArgumentParser(description="AI Civilization Sandbox — Offline")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--ticks", type=int, default=100, help="Headless tick count (default: 100)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scenario", choices=("default", "food_shortage"), default="default")
    parser.add_argument("--provider", choices=["mock", "rule-based"])
    parser.add_argument("--animation-fps", type=float, default=8.0)
    args = parser.parse_args()
    if not math.isfinite(args.animation_fps) or args.animation_fps <= 0:
        parser.error("--animation-fps must be finite and positive")
    if args.ticks < 0:
        parser.error("--ticks must be nonnegative")
    try:
        settings = Settings.load(provider=args.provider)
    except (ValueError, TypeError):
        parser.error("Invalid offline configuration; check .env settings")
    from pathlib import Path
    memory_path = Path(settings.memory_path)
    if not memory_path.is_absolute():
        memory_path = Path(__file__).resolve().parent.parent / memory_path
    simulation = Simulation(args.seed, create_provider(settings), settings.memory_enabled, memory_path, scenario=args.scenario, timing=settings.action_timing, day_clock=settings.day_clock, survival=settings.survival, wildlife_settings=settings.wildlife)
    try:
        if args.headless:
            for _ in range(args.ticks):
                simulation.step()
            simulation.close()
            print(json.dumps(simulation.snapshot(), sort_keys=True))
        else:
            from .rendering import run
            run(simulation, args.animation_fps)
    finally:
        simulation.close()


if __name__ == "__main__":
    main()
