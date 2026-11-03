"""Paired, isolated social-memory trials around the existing simulation."""
import argparse
import csv
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time

from .config import Settings, create_provider
from .ai import safe_text
from .simulation import Simulation

METRICS = ("requests", "shares", "refusals", "cooperation_rate", "survival_rate",
           "average_hunger", "invalid_action_rate", "gemini_calls", "fallback_count",
           "wall_seconds")


def rate(numerator, denominator):
    return numerator / denominator if denominator else None


def initial_fingerprint(sim):
    """Hash physical/RNG state, excluding the experimental treatment flag."""
    state = {"world": [[t.value for t in row] for row in sim.world.tiles],
             "agents": sim.snapshot()["agents"], "resources": sim.resources.stocks().__repr__(),
             "rng": repr(sim.rng.getstate())}
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def metrics(sim, hunger_sum, samples, fallback_count, elapsed):
    social = [e for e in sim.events if e.get("social")]
    requests = sum(e.get("result") == "pending" for e in social)
    shares = sum(e.get("result") == "shared one food" for e in social)
    refusals = sum(e.get("result") == "refused" for e in social)
    executed = sum("hunger_after" in e for e in sim.events)
    model_rejected = sum(e["action"] == "AI_DECISION" and e.get("reason") in (
        "malformed response", "action was not an offered choice",
        "decision became invalid before execution") for e in sim.events)
    invalid = sum(e["action"] == "REJECTED" for e in sim.events) + model_rejected
    return {"requests": requests, "shares": shares, "refusals": refusals,
            "cooperation_rate": rate(shares, shares+refusals),
            "survival_rate": None, "average_hunger": rate(hunger_sum, samples),
            "invalid_actions": invalid, "action_opportunities": executed,
            "invalid_action_rate": rate(invalid, executed),
            "gemini_calls": sim.ai_summary()["api_calls"], "fallback_count": fallback_count,
            "expired_requests": sum(e.get("result") == "expired" for e in social),
            "unanswered_requests": len(sim.social.pending),
            "final_trust": {a.id: a.trust.copy() for a in sim.agents},
            "wall_seconds": elapsed, "simulation_seconds": sim.tick*.25}


def run_trial(settings, seed, ticks, memory, scenario="food_shortage", tick_seconds=0.25):
    provider = create_provider(replace(settings, memory_enabled=memory))
    sim = Simulation(seed, provider, memory_enabled=memory, memory_path=None, scenario=scenario, event_limit=max(4096, ticks*32), decision_trace_limit=100, timing=settings.action_timing)
    row = {"seed": seed, "condition": "MEMORY_ON" if memory else "MEMORY_OFF",
           "provider": settings.provider, "model": safe_text(settings.model, settings.api_key) if settings.provider == "gemini" else None,
           "status": "running", "initial_state_sha256": initial_fingerprint(sim)}
    started = time.perf_counter()
    hunger_sum = samples = fallbacks = 0
    hunger_series = []
    try:
        for _ in range(ticks):
            sim.step()
            hunger_sum += sum(a.hunger for a in sim.agents)
            samples += len(sim.agents)
            hunger_series.append({"tick": sim.tick, "mean_hunger": sum(a.hunger for a in sim.agents)/len(sim.agents)})
            states = sim.ai_summary()["agents"]
            fallbacks += sum(bool(s.get("fallback")) for s in states.values())
            if settings.provider == "gemini":
                time.sleep(tick_seconds)
        row["status"] = "completed"
    except Exception as error:
        row.update(status="failed", error=type(error).__name__)
    finally:
        # Measure before session-end cancellations. Every trial owns its own provider and history.
        row.update(metrics(sim, hunger_sum, samples, fallbacks, time.perf_counter()-started))
        row["completed_ticks"] = sim.tick
        row["hunger_series"] = hunger_series
        row["recent_decisions"] = sim.decision_trace
        sim.close()
    return row


def describe(values):
    values = [v for v in values if v is not None]
    n = len(values)
    mean = statistics.mean(values) if n else None
    sd = statistics.stdev(values) if n >= 2 else None
    # Normal approximation is explicitly withheld for tiny samples.
    ci = None
    if n >= 5:
        margin = 1.96*sd/math.sqrt(n)
        ci = [mean-margin, mean+margin]
    return {"n": n, "mean": mean, "sample_stddev": sd, "approximate_95_ci_mean": ci}


def summarize(rows):
    completed = [r for r in rows if r["status"] == "completed"]
    modes = {mode: {m: describe([r[m] for r in completed if r["condition"] == mode])
                    for m in METRICS} for mode in ("MEMORY_OFF", "MEMORY_ON")}
    by_seed = {}
    for row in completed:
        by_seed.setdefault(row["seed"], {})[row["condition"]] = row
    differences = {m: [] for m in METRICS}
    paired = []
    for seed, pair in by_seed.items():
        if len(pair) != 2:
            continue
        off, on = pair["MEMORY_OFF"], pair["MEMORY_ON"]
        if off["initial_state_sha256"] != on["initial_state_sha256"]:
            continue
        delta = {m: on[m]-off[m] if on[m] is not None and off[m] is not None else None for m in METRICS}
        paired.append({"seed": seed, "on_minus_off": delta})
        for m in METRICS:
            differences[m].append(delta[m])
    return {"conditions": modes, "paired_differences": paired,
            "paired_summary": {m: describe(v) for m, v in differences.items()},
            "failed_trials": sum(r["status"] == "failed" for r in rows),
            "total_gemini_calls": sum(r.get("gemini_calls", 0) for r in rows),
            "total_fallback_npc_ticks": sum(r.get("fallback_count", 0) for r in rows),
            "warnings": ["Survival unavailable: the simulation has no death mechanic.",
                         "Confidence intervals use a normal approximation across seed-level trials.",
                         "Fewer than 5 complete pairs: descriptive pilot only." if len(paired) < 5
                         else "Seed sampling and model stochasticity limit generalization."]}


def export(output, config, rows):
    payload = {"configuration": config, "trials": rows, "summary": summarize(rows)}
    path = output/"summary.json"
    temporary = output/"summary.tmp"
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False))
    temporary.replace(path)
    fields = list(dict.fromkeys(k for row in rows for k in row))
    if fields:
        with (output/"trials.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v
                                 for k, v in row.items()})


def run_batch(settings, runs, ticks, seed, output, scenario="food_shortage", tick_seconds=.25):
    output.mkdir(parents=True, exist_ok=False)
    config = {"provider": settings.provider, "model": safe_text(settings.model, settings.api_key) if settings.provider == "gemini" else None,
              "runs": runs, "ticks": ticks, "seeds": list(range(seed, seed+runs)),
              "action_timing_ticks": settings.action_timing.__dict__, "scenario": scenario, "max_ai_calls_per_trial": settings.max_calls,
              "cooldown_ticks": settings.cooldown_ticks, "timeout_seconds": settings.timeout_seconds,
              "gemini_tick_wall_seconds": tick_seconds, "conditions": ["MEMORY_OFF", "MEMORY_ON"]}
    (output/"configuration.json").write_text(json.dumps(config, indent=2))
    rows = []
    try:
        for index in range(runs):
            for memory in (False, True):
                trial_seed = seed+index
                print(f"Seed {trial_seed}, MEMORY_{'ON' if memory else 'OFF'}", file=sys.stderr, flush=True)
                try:
                    row = run_trial(settings, trial_seed, ticks, memory, scenario, tick_seconds)
                except Exception as error:
                    row = {"seed": trial_seed, "condition": "MEMORY_ON" if memory else "MEMORY_OFF",
                           "status": "failed", "error": type(error).__name__}
                rows.append(row)
                export(output, config, rows)
    finally:
        export(output, config, rows)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("rule-based", "mock"), default="rule-based")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--ticks", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scenario", choices=("food_shortage",), default="food_shortage")
    parser.add_argument("--max-ai-calls", type=int, default=40)
    parser.add_argument("--output-root", type=Path, default=Path("experiments"))
    args = parser.parse_args()
    if args.runs < 1 or args.ticks < 0 or args.max_ai_calls < 0:
        parser.error("runs must be positive; ticks and call budget must be nonnegative")
    settings = Settings(provider=args.provider, max_calls=args.max_ai_calls)
    output = args.output_root/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    try:
        rows = run_batch(settings, args.runs, args.ticks, args.seed, output, args.scenario)
    except KeyboardInterrupt:
        print(f"Interrupted; completed trials saved in {output}", file=sys.stderr)
        return 130
    except OSError:
        print("Could not write experiment output", file=sys.stderr)
        return 1
    print(output)
    return int(any(r["status"] != "completed" for r in rows))


if __name__ == "__main__":
    raise SystemExit(main())
