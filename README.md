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
| Left-click chicken | Participant attack within one Manhattan tile; 25 HP per click |
| M / Backspace | Character/mode menu; cancel unfinished work |
| Space / − / + | Pause/resume; simulation speed |
| C / N | Timestamped conversations; village news |
| F1 / F3 | Help; optional raw diagnostics |
| F5 / F9 | Save full world; confirm load |

Default logical window: 1100×750. Use --window-scale 0.85 or 1.25 for compact/large presentation with remapped mouse targets. Detailed values, seed/ticks, scores and traces remain in F3 (P: planner; S: social).

## Procedural chickens and comfortable survival

Chickens now have articulated, entirely programmatic idle/walk/peck animations, blinking, hit flashes and a brief defeat animation. No new artwork, services or dependencies are required. In Participant Mode, left-click the visible chicken: each valid click deals 25 of 100 HP, four hits grant one raw chicken. Range uses the player’s actual tile (same/cardinal neighbor); diagonal or distant clicks do not move the player. UI/speech clicks and held mouse movement never attack. E retains gathering, cooking and social options; it no longer offers player hunting. Autonomous NPCs retain timed pursuit/catch behavior.

Hunger still means 0 satisfied / 100 starving. It now rises one-third as often (default +1 every 3 simulated seconds), while meals and survival thresholds keep their existing values. Energy now uses the reduced, centralized rates described below. Set `HUNGER_INTERVAL_MULTIPLIER` in optional .env (default 3, old rate 1). This multiplies `NEEDS_INTERVAL_SECONDS`; rendering FPS never controls needs. Historical Stage 7 measurements used the earlier balance and must not be presented as fresh results from this revision. Details/tests: [CHICKEN_POLISH.md](CHICKEN_POLISH.md).

## Energy balance and optional gather prototype

Energy now drains at 0.02 units per idle simulated second and 0.1 per walking tile, with inclusive configurable costs for gathering (1), cooking (0.5), pursuit steps (0.5), catches (4) and player hits (0.5). Rest remains +8 per completed one-second rest. Physical actions/rest do not also pay passive drain. Hunger retains the prior 3× slower balance.

The experimental `interact_gather` presentation uses the unchanged original directional idle art plus small resource-contact/pickup effects. It has **16 procedural direction/phase states per character**, not newly illustrated reaching arms. Only accepted, stationary, in-range berry gathering plays it; the executor still controls all timing and rewards. No original PNG is changed.

```bash
python -m civsandbox --interact-preview
python -m civsandbox --no-interact-animation
```

F7 opens/closes the frozen-world preview; 1–4 selects Mira/Nyra/Kairo/Ren; Space pauses the preview. **F6 disables/enables the prototype immediately**, with original idle fallback. Persistent preference: `ENABLE_INTERACT_ANIMATION=false` in optional .env. Cycle setting: `INTERACT_ANIMATION_SECONDS=1.0`, fitted to whole cycles per gathering action. Full energy units, actual five-day comparisons, limitations and safe removal instructions: [ENERGY_INTERACT.md](ENERGY_INTERACT.md).

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

## Animated idle artwork integration (November 2026)

The existing simulation now loads optional directional idle sequences alongside its unchanged walking assets. No additional game application is needed.

```sh
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox"
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m civsandbox --provider rule-based --mode observer --animation-fps 8 --idle-fps 4
```

Press **F8** (or **Fn+F8** on macOS) for the animation overlay. **1–4** selects Mira, Nyra, Kairo, Ren. **B** cycles dark, light, and grass backgrounds. All four directional rows display the old walking idle reference, the new idle poses, and an automatic one-second WALK / two-second IDLE preview. F8 closes the overlay. The real simulation continues underneath, and the overlay reports the directions and animation states of active conversation participants. Pause/resume with Space; animation freezes while paused. The preview only reads simulation state.

For normal gameplay verification, close the overlay and observe villagers approach, stop, face each other, and speak. The existing social session sets `agent.facing`; the renderer applies it after the interpolated character reaches its destination. Both participants then loop their matching directional idle sequences. Speech bubbles, reading time, session locks, positions, and social outcomes remain controlled by the existing simulation. Resting, waiting, gathering, eating, and cooking use generic idle while stationary; there are no new action-specific animations.

### Supplied idle sheets

| Character | Stored original | Dimensions | Original mode / alpha range | Idle frames per direction |
|---|---|---|---|---|
| Mira | `assets/characters/mira_idle.png` | 1086 × 1448 | RGBA / 0–255 | 4 |
| Nyra | `assets/characters/nyra_idle.png` | 1024 × 1536 | RGBA / 0–254 | 4 |
| Kairo | `assets/characters/kairo_idle.png` | 1086 × 1448 | RGBA / 0–255 | 4 |
| Ren | `assets/characters/ren_idle.png` | 1086 × 1448 | RGBA / 202–252 | 4 |

The uploaded `kario_idle.png` is mapped to Kairo and preserved byte-for-byte under the canonical filename. Every sheet has DOWN, LEFT, RIGHT, UP rows with four stationary poses: 16 frames per character, 64 total. Pose variation is subtle; these are supplied poses, with no invented blink frames or generated artwork.

`python -m civsandbox.prepare_idle_assets` processes only idle assets. `IDLE_COLUMNS` explicitly declares the inspected counts; new artwork must be reviewed before changing those counts. Row and column gutters are measured near the declared grid, and solid-art boundary intersections are rejected. A declared count of one supports a genuinely static directional idle. The original PNGs are untouched.

Mira, Nyra, and Kairo retain their original alpha inside measured crops. Solid foreground components establish bounds with edge padding so distant translucent residue cannot distort sizing. Ren's alpha is mostly opaque even in the background: only exterior-connected near-neutral pale pixels are cleared (minimum RGB channel 195, maximum channel spread 28). Enclosed pale details and foreground alpha remain intact. Conservative extraction leaves faint fringes, most noticeable around Ren on dark backgrounds; aggressive outline removal was avoided. New art has some source proportion/pose differences from the walking sheets, so transitions can show those differences despite consistent scale and grounding.

Processed assets are separate: `assets/processed/<character>/idle/<direction>/<index>.png`, plus a manifest with exact counts, source hash, crop rectangles, and scale. One scale is used for each whole idle sheet, matched to the existing front walking-idle height. Boot-region centers align horizontally, with the same 160 × 200 canvas and y=190 ground baseline as walking. In-game surfaces retain the existing 40 × 50 dimensions and foot anchor.

`CharacterAssets` loads/caches frames once. A missing or incomplete optional idle set falls back to that character's original static directional poses, with one debug log per unavailable character per asset load. `SpriteAnimator` keeps its existing walking interface and FPS, adds optional `idle_frames` and configurable `idle_fps`, and resets progression only on state or facing transitions. `CharacterView` advances idle using render delta time, including time split at fixed simulation boundaries, and finishes visual travel before switching to idle.

### Verification

```sh
python -m pytest -q
```

Automated coverage includes idle mapping/discovery, four directions, looping, transitions, last-facing preservation, static/missing/incomplete fallbacks, cached surfaces, fixed-tick versus render timing, pause, ground/canvas consistency, and real conversations without simulation changes. Existing walking tests remain in place. The saved-facing test now expects the optional idle pose when present.

Inspection artifacts:

- `assets/inspection/idle-frames.json`: original inspection and measured extraction metadata.
- `assets/inspection/idle-contact-dark.png` and `idle-contact-light.png`: all 64 idle frames alongside 16 walking reference poses.
- `assets/inspection/idle-conversation.png`: rendered Mira/ Ren conversation with directional idle and a real speech bubble.
- `assets/inspection/idle-preview.png`: the in-game F8 overlay.

SDL dummy video was used for automated rendering and screenshots. Native macOS window, keyboard, and perceived loop smoothness require the interactive checks above. No gameplay features or Participant Mode changes were included in this integration.

Actual integration verification: full suite **386 passed, 1 skipped** (31.56 seconds); the skipped test requires a live API. After final optional-manifest validation and preview filtering adjustments, focused animation/regression tests were rerun: **55 passed** (1.92 seconds). Existing walking and inspection assets: **88 files matched byte-for-byte** against the project originals. Dark/light contact sheets and existing-game screenshots were generated; the dark contact sheet, Ren detail, conversation, and preview screenshots were visually reviewed.
