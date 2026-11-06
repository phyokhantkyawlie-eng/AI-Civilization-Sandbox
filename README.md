# AI Civilization Sandbox

CSC472 Artificial Intelligence final project: a small offline Python/Pygame civilization with four original animated characters, survival routines, social interactions, memory and reproducible evaluation. **Its intelligence is local utility scoring, bounded task planning, BFS and finite-state rules. It does not use machine learning, neural networks or LLM reasoning. No API key or network connection is required to play or evaluate.**

## Setup and launch

Tested environment: macOS, Python 3.12, Pygame 2.6.1. Keep the existing virtual environment. For a new installation, install requirements.txt from available packages; package installation may require connectivity, while application operation does not.

```bash
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox"
source .venv/bin/activate
python -m civsandbox --mode observer --provider rule-based --seed 7
python -m civsandbox --mode participant --character mira --provider rule-based --seed 7
python -m civsandbox --scenario food_shortage --provider rule-based --seed 7
```

New environment only:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Launch the package with `python -m civsandbox`, including in VS Code. Running civsandbox/__main__.py directly does not establish package-relative imports; use the existing module launch configuration. `.env` is optional; `.env.example` contains offline settings. Legacy external-provider settings cannot activate networking. `mock` is an explicitly labeled local structured-decision test adapter, not a real model.

## Play

Mira (green gatherer), Nyra (purple observer), Kairo (blue adventurer) and Ren (red merchant) use the original idle/four-direction walk sprites. They manage hunger/energy, gather finite regenerating berries, eat, rest, conditionally hunt mobile chickens and cook real raw meat into a meal at the shared campfire. Personalities influence choices through numeric traits. Actual social sessions support requests, sharing, voluntary offers, refusal, authored offline speech, directed trust and bounded memories.

Observer Mode runs all four autonomously. Participant Mode controls one existing Agent through the same world, validators, timed actions and inventory rules; the other three stay autonomous. M switches modes without rebuilding the world. Incoming interactions require explicit choices and cancel safely when unattended. See [GAMEPLAY_GUIDE.md](GAMEPLAY_GUIDE.md).

| Controls | Purpose |
| --- | --- |
| WASD / arrows | Participant movement; arrows adjust speed in Observer Mode |
| E / I | Nearby actions/inspection; inventory/eating/rest |
| M / Backspace | Character/mode menu; cancel unfinished work |
| Space / − / + | Pause/resume; simulation speed |
| C / N | Timestamped conversations; village news |
| F1 / F3 | Help; optional raw diagnostics |
| F5 / F9 | Save full world; confirm load |

Default logical window: 1100×750. Use --window-scale 0.85 or 1.25 for compact/large presentation with remapped mouse targets. Detailed values, seed/ticks, scores and traces remain in F3 (P: planner; S: social).

## Save and load

F5 writes an atomic version-1 full-world checkpoint to data/world_save.json. F9 confirms before replacing play and loads paused. Needs, inventory, identities, resources, chickens, clock, social history, provider/mode and selection persist. Interrupted jobs, claims, requests, sessions and plans restart safely as idle, without unfinished rewards. The checkpoint is not a frame-exact replay of ongoing plans.

```bash
python -m civsandbox --load data/world_save.json
python -m civsandbox --save-file saves/another.civsave.json
```

Keep private saves in ignored data/, saves/ or *.civsave.json. Legacy social-only files are preserved; loading a full world never writes unrelated legacy histories. Full-world saves are explicit, not automatic at exit. Details and retention limits: [STAGE6_POLISH_PERSISTENCE.md](STAGE6_POLISH_PERSISTENCE.md).

## Offline evaluation

```bash
python -m pytest -q
python -m civsandbox.experiments --scenario normal_survival --runs 5 --ticks 12000 --seed 7 --memory-mode on
python -m civsandbox.experiments --scenario food_shortage --runs 5 --ticks 12000 --seed 7 --memory-mode on
python -m civsandbox.experiments --scenario social_memory --runs 5 --ticks 12000 --seed 7 --memory-mode paired
python -m civsandbox.experiments --scenario hunting_decisions --runs 5 --ticks 2400 --seed 7 --memory-mode on
python -m civsandbox.results
python -m civsandbox.results PATH_PRINTED_BY_RUNNER --show
```

Each batch exports genuine CSV/JSON into a new timestamped experiments directory. Trials use fresh providers, empty social history, neutral trust, matched seeds and no normal-game save path. Whole-trial counters stream independently of bounded engine logs. Reports include energy, hunger, activities, food conservation, hunting/cooking, social outcomes, trust and failed/invalid actions. Undefined rates are unavailable. Permanent NPC death is absent, so mortality survival is unavailable; operational availability is a separate proxy.

Final Stage 7 evidence: **55 actual trials**, plus two **30,000-tick** profiling runs, under blocked networking. The five memory pairs did not establish a benefit: average cooperation changed +0.00226, hunger +0.174 and energy −0.083 (ON minus OFF); four of five pairs matched on these metrics. Full results/limitations: [AI_EVALUATION.md](AI_EVALUATION.md). Generated final evidence and 11 charts are under artifacts/stage7/release_evaluation/ when present; these generated files are deliberately ignored by Git. They are reproducible with the commands above. Older stage artifacts are historical, not current measurements.

## Documentation and verification

- [ARCHITECTURE.md](ARCHITECTURE.md): actual algorithms and module responsibilities.
- [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md): engineering conventions, tests, privacy and recovery.
- [GAMEPLAY_GUIDE.md](GAMEPLAY_GUIDE.md): controls, survival, interactions and saves.
- [AI_EVALUATION.md](AI_EVALUATION.md), [EXPERIMENT.md](EXPERIMENT.md), [RESULTS_GUIDE.md](RESULTS_GUIDE.md): measured results, methods and charts.
- [DEMO_GUIDE.md](DEMO_GUIDE.md): 5–8 minute presentation with genuine prepared evidence.

Existing phase1a files and optional historical external adapters are preserved for recovery/compatibility. The normal factory and CLIs enable only rule-based/mock, and no external SDK is a runtime requirement. No private saves, keys or generated histories belong in commits. Native macOS play/Retina smoothness still requires the manual checklist; SDL dummy tests and chart inspection do not establish native visual approval.
