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
    parser.add_argument('--interact-preview', action='store_true', help='Preview the optional gather prototype (F7)')
    parser.add_argument('--no-interact-animation', action='store_true', help='Use existing idle sprites for gathering')
    parser.add_argument("--idle-fps", type=float, default=4.0)
    parser.add_argument("--window-scale", type=float, choices=(.85,1.0,1.25), default=1.0)
    parser.add_argument('--mode', choices=('observer', 'participant'), default=None)
    parser.add_argument('--character', choices=('mira', 'nyra', 'kairo', 'ren'), default='mira')
    parser.add_argument('--load', metavar='FILE', help='Load a versioned full-world checkpoint')
    parser.add_argument('--save-file', metavar='FILE', help='In-game F5/F9 checkpoint path')
    parser.add_argument('--save', metavar='FILE', help='Save a checkpoint after a headless run')
    args = parser.parse_args()
    if args.interact_preview and args.headless:
        parser.error('--interact-preview requires graphics')
    if args.save and not args.headless:
        parser.error('--save requires --headless; use --save-file for an interactive save slot')
    if args.headless and args.mode == 'participant':
        parser.error('Headless CLI uses Observer Mode; Participant Mode requires interactive input')
    if not math.isfinite(args.animation_fps) or args.animation_fps <= 0:
        parser.error("--animation-fps must be finite and positive")
    if not math.isfinite(args.idle_fps) or args.idle_fps <= 0:
        parser.error("--idle-fps must be finite and positive")
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
    from .savegame import load_game, save_game, SaveError
    if args.load:
        try:
            simulation = load_game(args.load)
        except SaveError as error:
            parser.error(str(error))
        if args.provider:
            simulation.decision_provider = create_provider(settings)
            simulation.decision_provider.bind_social(simulation.social)
            simulation.decision_provider.bind_routines(simulation.clock,simulation.survival)
        if not args.headless:
            simulation.paused = True
    else:
        simulation = Simulation(args.seed, create_provider(settings), settings.memory_enabled, None if args.interact_preview else memory_path, scenario=args.scenario, timing=settings.action_timing, day_clock=settings.day_clock, survival=settings.survival, wildlife_settings=settings.wildlife, social_settings=settings.social, energy_rules=settings.energy)
    simulation.save_path = Path(args.save_file or args.load or Path(__file__).resolve().parent.parent/'data'/'world_save.json')
    if args.mode == 'observer' or args.headless and simulation.player:
        simulation.set_participant()
    if args.mode == 'participant':
        from .characters import CHARACTERS
        simulation.set_participant(next(key for key, (_, art) in CHARACTERS.items() if art == args.character))
    try:
        if args.headless:
            for _ in range(args.ticks):
                simulation.step()
            if args.save:
                try:
                    save_game(simulation,args.save)
                except SaveError as error:
                    parser.error(str(error))
            simulation.close()
            print(json.dumps(simulation.snapshot(), sort_keys=True))
        else:
            from .rendering import run
            run(simulation, args.animation_fps,args.window_scale,args.idle_fps,
                enable_interact_animation=settings.enable_interact_animation and not args.no_interact_animation,
                interact_animation_seconds=settings.interact_animation_seconds,
                interact_preview=args.interact_preview)
    finally:
        simulation.close()


if __name__ == "__main__":
    main()
