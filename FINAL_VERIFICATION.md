# Final release verification — Stage 7

Verification date: 6 November 2026 (Asia/Bangkok). This report describes the offline release, superseding the pre-overhaul report formerly at this path. Recovery before cleanup: local tag codex/stage7-baseline, commit d88109d.

## Fully verified through executed checks

- Baseline: 360 passed, one historical live test skipped. Final staging and main-project suites: **374 passed, 1 skipped, zero failures** each (27.39 s and 27.85 s respectively). The full suite prohibits socket/DNS attempts, including caught failures. Installed optional SDK serialization tests use fake transport; no live API test ran. SDK absence may cause additional compatibility skips in another environment.
- Existing simulation/actions/resources/social/wildlife/cooking/animation/Participant/save-load tests all run in that full suite. New evaluation coverage verifies streaming totals past log trimming, true activity denominators, scenario/profile pairing, fresh trials, memory-off policy isolation, offline-only providers, configuration validation, bounded trajectories and spawn latency.
- **55 actual evaluation executions** completed: normal (five), shortage (five), memory (five paired seeds / ten executions), hunting (seven profiles × five). All used rule-based decisions, zero API calls and valid food-conservation checks. CSV/JSON row consistency and 11 chart files were checked. B and C ON duplicate deterministic controls and are not independent extra samples.
- **Two 30,000-tick** fresh long runs checked normal/shortage conservation, log/history/session/identity bounds and traced allocations. Counts and limitations are in AI_EVALUATION.md and artifacts/stage7/long_run_profile.json.
- A practical seed-7 demonstration reached genuine hunting/raw meat and cooking. Rehearsal detected a legitimate starvation interruption at the first cook. The prepared save instead uses the later natural recovery window at tick 677, with explicit normal Participant handoff and one real raw chicken. Explicit test commands completed one player cook at tick 698 and one player meal at 709, hunger 100→35; all three other agents continued autonomously. No inventory or needs were injected.
- Chart generation/PNG inspection used genuine exports. No fabricated placeholders replaced unavailable metrics. Mortality survival remains unavailable; operational availability is separately labeled. Memory's tiny measured effect does not establish a benefit.

- Main-project CLI rechecks: rule-based/default and mock/food_shortage each advanced 1,000 ticks; normal, paired-memory and exhausted-hunting experiment commands completed. Genuine saved exports regenerated 11 PNG charts. The prepared Participant cook/meal was independently rerun through tick 709. All 183 protected artwork/private/prototype file hashes remained unchanged. Tracked source/document credential scanning and the offline dependency check passed.

## Release changes and cleanup

Existing experiment orchestration now supports A/B/C/D scenarios, paired/on/off memory and controlled hunting profiles. measurements.py streams totals with bounded tracking; results.py generates all 11 current figures. Initial physical/configuration/RNG hashes and metadata are exported; only matching complete strata/seed pairs enter paired differences. Failed trials remain visible and later trials continue.

GOAL_SELECTED events and requested-action rejection labels improve explainability without changing utility weights/RNG/world effects. The obsolete external-runner wait path/metadata and verified unused rendering/test imports were removed. Existing tested optional adapters, future Action provider boundary, requirements, artwork, .venv, phase1a and private files are preserved. Main runtime/evaluation does not require Google SDK or credentials. No broad refactor or unrelated gameplay was added.

## Partially verified / manual

Native macOS Pygame play, Retina scaling, subjective readability/game feel and desktop FPS still require actual graphical inspection. SDL dummy rendering tests and chart image inspection are not native visual approval. Follow the Stage 6 checklist plus GAMEPLAY_GUIDE/DEMO_GUIDE. The Matplotlib --show viewer also requires a local graphical backend; headless PNG generation is verified.

Check on a real display: all four original sprites/facing/foot anchors; ordinary/debug HUDs; .5×/1×/4× motion; compact/large scaling and click alignment; C/N histories; consent/timeout handling; gathering/hunting/cooking/meal feedback; Participant/Observer handoffs; F5/F9 save safety and quit.

## Remaining limitations

No death/health model, ML/LLM, general-purpose search planner or unrestricted visual perception exists. The rule policy knows the resource map. Fixed NPC order, four personalities, five experimental seeds and conversation timing/random-stream effects constrain interpretation. Contested finite stock causes safe GATHER rejection/wasted time; night rest reselects brief WAIT goals frequently. Corridor recovery may temporarily overlap NPCs. Histories/trajectories are bounded; full-world loading releases unfinished work and replans rather than replaying it exactly. Python allocation growth stayed within deliberate journal limits, but this is not proof of no possible memory leak or a native performance benchmark.

## Exact launch and evaluation commands

```bash
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox"
source .venv/bin/activate
python -m civsandbox --mode observer --provider rule-based --seed 7
python -m civsandbox --mode participant --character mira --provider rule-based --seed 7
python -m civsandbox --scenario food_shortage --provider rule-based --seed 7
python -m pytest -q
python -m civsandbox.experiments --scenario social_memory --provider rule-based --runs 5 --ticks 12000 --seed 7 --memory-mode paired
python -m civsandbox.results artifacts/stage7/release_evaluation --show
```

Use an unused temporary MEMORY_PATH for isolated CLI checks, or the experiment runner (which never loads normal saves). Generated evidence remains local/ignored and can be regenerated. AI_EVALUATION.md records actual measurements, GAMEPLAY_GUIDE.md explains play, ARCHITECTURE.md explains the actual algorithms and DEMO_GUIDE.md gives the 5–8 minute presentation.
