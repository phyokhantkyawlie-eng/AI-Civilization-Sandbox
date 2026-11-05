# Stage 3 — cooking and goal-oriented offline AI

## Implementation

The original simulation, four NPCs, sprite sheets, wildlife, memories, directed trust, inventory and provider interface remain in use. No external model or network requirement was added.

- A shared campfire is placed on a safe blocked tile. Every other previously reachable tile remains connected. Cooking from an adjacent tile acquires a single-owner lease, takes five simulation seconds by default, and converts one owned raw chicken into one cooked chicken only on validated completion. Canceled/invalid activities retain remaining ingredients and release the station. No fuel or crafting system was added.
- The central item catalog defines berries (35 hunger reduction), raw chicken (inedible) and cooked chicken (65). EAT can name an item or choose available nutrition with least waste. One item is removed per meal, needs stay clamped, and conversion works at full capacity without an extra slot.
- The existing offline provider now ranks utility proposals and retains a bounded goal queue. Goals include EAT, GATHER_FOOD, HUNT_FOOD, COOK_FOOD, REST, SOCIALIZE, HELP_OTHER, GET_HELP, EXPLORE and WAIT. The queue handles travel, gathering, hunting, station contention, cooking and eating through the existing executor.
- F3 then P opens the goal inspector: selected goal, top candidate utilities, public reason, remaining sequence and last replan/failure. Ordinary UI shows needs, inventory, activity and campfire Ready/Busy. Cooking uses the existing idle fallback and a real activity indicator.

## Selection and planning rules

Utilities are sums of named relative components, not probabilities or measured intelligence scores. Common terms include hunger urgency, actual nutrition, reserve deficit, fatigue, daylight/night preference, travel cost, station waiting, risk, nature affinity, resource focus, curiosity, sociability and directed trust where memory is enabled. Exact components are defined in decisions.py and exposed in provider debug state.

Critical hunger with available edible food prioritizes eating. Low energy prioritizes recovery over optional actions. Severe hunger excludes optional social/exploration goals; urgent empty-inventory food needs can interrupt a preferred night rest. Existing real requests are considered through the same social validator and willingness mechanism. No character-name scripts exist: Mira can hunt, Ren can share, and cautious Nyra can select a valid conversation. Controlled tests verify these capabilities under common rules.

Plans contain at most six tasks and use the existing BFS/occupancy system for movement. A retained plan is not rescored each tick. Completion, invalid targets/actions, urgent needs, incoming requests, 80 ticks without progress, or a 320-tick plan deadline cause completion/replanning. Ordinary failed-target retries wait 16 ticks; emergency eating/rest are not suppressed by that delay. Campfire contention waits within the plan, and existing bounded pursuits handle moving chickens. Exploration and selected social willingness use the seeded RNG; unselected utility proposals do not consume random draws.

Examples exercised by integration tests:

- MOVE_TO → GATHER → EAT berries.
- HUNT → MOVE_TO campfire approach → COOK → EAT cooked chicken.
- Travel to a nearby shelter approach when appropriate → repeated timed REST units.

## Actual headless evaluation

The existing experiment runner executed seeds 7, 8 and 9 in both MEMORY_OFF and MEMORY_ON: **six trials × 4,800 ticks = 28,800 ticks**. Each trial used fresh isolated history and a fresh local provider and ran for 1,200 simulation seconds (two calendar days). All completed without exceptions and used zero API calls. These are descriptive verification trials, not evidence of a general memory benefit.

| Seed | Memory | Gathers | Hunts started / succeeded | Cooks | Meals berries / chicken | Incapacitations | Failed plans | Mean hunger | First → last quarter hunger |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 7 | OFF | 115 | 1 / 1 | 1 | 124 / 1 | 14 | 92 | 44.37 | 23.98 → 50.19 |
| 7 | ON | 114 | 1 / 1 | 1 | 123 / 1 | 15 | 96 | 45.89 | 23.68 → 55.47 |
| 8 | OFF | 117 | 2 / 2 | 2 | 126 / 2 | 11 | 84 | 41.30 | 22.97 → 49.20 |
| 8 | ON | 117 | 2 / 2 | 2 | 126 / 2 | 11 | 84 | 41.30 | 22.97 → 49.20 |
| 9 | OFF | 118 | 1 / 1 | 1 | 127 / 1 | 13 | 97 | 43.08 | 23.59 → 52.91 |
| 9 | ON | 118 | 1 / 1 | 1 | 127 / 1 | 13 | 97 | 43.08 | 23.59 → 52.91 |

Counts refer to validated completions; accepted pursuit starts are counted separately. Hunger is 0–100, with 100 starving. Mean hunger averages all four NPCs at every tick. First/last quarters average the first/last 1,200 ticks of each run. Failed plans include invalidated targets/actions, unsuccessful pursuits and progress/deadline failures; emergency interruptions are a separate export field. A failed plan is not a crashed trial.

Conservation was checked independently in every trial:

- initial berries + completed gathers = final berries + berry meals;
- initial raw meat + successful hunts = final raw meat + cooking completions;
- initial cooked meat + cooking completions = final cooked meat + cooked meals.

Last-quarter hunger was higher than first-quarter hunger, and temporary incapacitations remain possible. The quarter windows also have different day/night composition, so this descriptive trend does not isolate scarcity or memory effects. Hunting remains conditional; cooking does not guarantee food for every NPC. Finite runs may end with pending plans or stored ingredients. There is no permanent death model. Fixed NPC update order, a single station, limited resources and a three-seed sample constrain interpretation. No experiment outcomes were scripted or substituted.

Genuine generated data: artifacts/stage3/final_experiment/summary.json and trials.csv; compact counts: artifacts/stage3/final_counts.json. Generated outputs are ignored by Git. Earlier exploratory outputs are not this final dataset. New exports include the food catalog, timing and campfire fingerprint; previous stages' reports describe different code.

## Tests and visual checks

Rechecked after interruption on **2026-11-05**. Final full suite in the main project: **251 passed, 1 skipped, 0 failed in 26.29 seconds** (34 new regression cases). Command:

```bash
PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/civsandbox-stage3-mpl .venv/bin/python -m pytest -p no:cacheprovider -q
```

A fresh main-project seed-7 MEMORY_ON run reproduced the saved initial-state hash and gather/hunt/cook/meal/incapacitation/failed-plan/hunger counters. All six CSV/JSON trial records were validated. Python's standard csv reader needs a larger field_size_limit for the exported long hunger-history fields; this is a reader size limit, not a trial failure. Both rule-based and mock normal CLIs completed an additional 2,400 ticks with networking, DNS and Google SDK imports blocked, four NPCs present, zero API calls and station leases released on shutdown.


The pre-stage suite passed 217 tests, with one archived live test skipped. New regression coverage includes conversion at full capacity, no duplicate cooking with another raw item, duration, cancellation, invalid targets, exclusive occupancy, bounded waiting, named meals/nutrition, pause/speed, complete chicken-meal execution, goal retention/invalidation, emergencies, personality effects, all four NPCs cooking, cautious conversation, memory-off isolation, read-only observations, connectivity and the debug panel. Legacy berry-conservation tests now count berry meals separately; the night-rest test accepts planned travel before resting. The wildlife opportunity fixture still lets the selected provider choose the hunt and checks conservation across raw, cooked and consumed meat.

The full suite prohibits socket/DNS requests. No live API test, dependency download or native interactive visual approval is claimed. SDL dummy images were rendered and inspected for cooking status and the planner panel; original artwork integrity remains covered by the suite.

Manual visual checklist: find the campfire; watch Ready/Busy during cooking; pause mid-cook and resume; compare 0.5×/1×/4× speeds; select each character and inspect inventory; use F3/P to follow a retained queue and a failed/replanned goal; verify original walking directions and idle cooking fallback.

## Launch, reproduce and recover

```bash
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox"
source .venv/bin/activate
python -m civsandbox --provider rule-based --scenario food_shortage --seed 7
python -m pytest -q
```

Reproduce the six measured trials with the existing isolated runner:

```bash
python -m civsandbox.experiments --provider rule-based --runs 3 --ticks 4800 --seed 7 --scenario food_shortage
```

Set COOK_SECONDS in the local environment to change cook duration. Do not overwrite a private .env or delete history to reproduce a trial; experiments isolate history automatically. Normal sessions restore social history, which can change decisions. Physical inventories/plans remain session state, and existing social food sharing still transfers berries. Full world saves, cooked-meal sharing, fuel, crafting, external AI and future gameplay stages are outside this change.

Pre-stage recovery commit: 7609a00. Private .env and saved-history fingerprints were checked unchanged; the virtualenv is retained and original NPC artwork has no Git diff.
