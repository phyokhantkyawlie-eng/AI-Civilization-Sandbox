# Stage 1 — meaningful survival and daily routines

## Implementation

Existing hunger/energy direction, passive need changes, movement/gather costs, berry eating effect, inventories, art, BFS, social structures and offline provider interface are preserved. New behavior extends the existing fixed-tick loop and ActionProgress scheduler.

- BerryBush records provide deterministic IDs, position, quantity/capacity, per-bush growth interval and progress. Compatibility stock APIs and bounded mutation records remain. Growth occurs on simulation-time interval boundaries, even without NPC visits, and same-tick calls are idempotent. Click a bush for its location, stock, countdown and progress bar.
- Rest now takes one simulated second per +8 energy completion. Gathering/eating/social actions retain existing nonblocking durations and latest-state validation. Completed gathering transfers one actual berry and emits one successful GATHER event; generic ACTIVITY progress records show work in progress. Competing gathers cannot duplicate the last berry.
- A configurable calendar derives day, time and phase from the existing tick. Default: 600 seconds/day, 08:00 start. Gradual dawn/dusk tint uses bounded cached surfaces. Numeric early_bird traits create different preferred rest windows; daylight encourages food stocking. Urgent food and eligible incoming requests override routine preferences. Rest happens on the current tile, not inside houses.
- High hunger slows gathering and logical travel. Starvation/exhaustion can cancel unfinished activities and requests and trigger temporary recovery. Recovery uses the same validated timed REST action, then a starvation grace window allows food seeking. It creates no food and applies no invented trust penalty. Continued scarcity may cause another temporary recovery. Death remains absent.
- Selected NPCs show authoritative needs, activity, goal and inventory; resource inspectors use actual bush records. The item registry has consumption metadata for later extension. Raw chicken and cooked chicken remain later-stage items; hunting and cooking were not added.

## Configuration

The existing private .env is retained. See .env.example for local settings:

| Setting | Default | Meaning |
| --- | --- | --- |
| REST_SECONDS | 1 | Time per completed +8 energy rest unit |
| DAY_LENGTH_SECONDS / DAY_START_HOUR | 600 / 8 | Calendar duration and starting hour |
| SURVIVAL_HUNGRY | 55 | Food urgency, observed hunger, request eligibility |
| HUNGER_SLOW_THRESHOLD / HUNGER_SLOWDOWN | 85 / 2 | Gathering duration multiplier and travel tick divisor |
| STARVATION_THRESHOLD / EXHAUSTION_THRESHOLD | 100 / 0 | Temporary recovery triggers |
| REST_ENERGY_THRESHOLD | 20 | Needs-based resting threshold; ordinary rest continues toward 70 |
| RECOVERY_SECONDS / RECOVERY_GRACE_SECONDS | 3 / 30 | Minimum recovery duration / subsequent starvation grace |

Recovery also requires energy above the exhaustion threshold. Night routines rest toward 90 energy, with needs still advancing. Threshold ordering and finite positive durations are validated. No stricter death mode or new save database exists. Clock, survival and timing settings are included in new experiment configuration exports; earlier reports describe earlier mechanics.

## Executed verification

Baseline before changes: 167 passed, 1 skipped. Final full suite in the main project: **188 passed, 1 skipped, 0 failed in 20.71 seconds** (21 new regression cases). Command:

```bash
PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/civsandbox-stage1-mpl .venv/bin/python -m pytest -p no:cacheprovider -q
```

The main CLI also completed 4,800 ticks to Day 3 at 08:00 with network/DNS access and Google SDK imports blocked, all four NPCs present, 27 bushes and zero API calls. Private environment/history fingerprints were verified unchanged; original artwork has no Git diff.

 New regression coverage includes regeneration/depletion, IDs and per-bush intervals, delayed/capacity-limited collection, competing gathers, food conservation, eating, timed rest, day phases, personality routines, urgency overrides, hungry work/travel, configured threshold consistency, pause/speed determinism, incapacitation recovery, social cancellation and cached lighting/resource inspection. The full suite also covers existing sharing, refusals, persistence, sprites and provider compatibility. All tests prohibit network connections. The historical live test remains skipped.

Two genuine seed-42 offline runs used 4,800 ticks each (two full calendar days, ending Day 3 at 08:00). Every NPC repeatedly gathered, ate and rested; both runs used zero API calls. Food balance includes both inventories and bushes:

| Scenario | Gathers | Eats | Requests | Shares | Refusals | Incapacitated / recovered | Food balance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Default | 150 | 144 | 0 | 0 | 0 | 0 / 0 | 135 initial + 149 regrown − 144 eaten = 140 final |
| Food shortage | 118 | 127 | 6 | 2 | 4 | 15 / 15 | 11 initial + 118 regrown − 127 eaten = 2 final |

These are observed smoke runs, not experimental claims or guaranteed social outcomes. Kairo ended the shortage run at hunger 100 while awake in recovery grace; scarcity remains meaningful and unequal. Headless checks used in-memory histories, so normal persisted history can change subsequent decisions.

SDL dummy previews of night lighting and the selected bush were rendered and inspected. Dummy tests exercise controls/inspection and sprite loading. Native interactive visual QA was not performed. Manual checks: watch dawn/dusk; pause mid-gather/rest and resume; compare 0.5×/1×/4×; click each NPC and a depleted bush; verify regrowth without visits; observe food shortage, temporary recovery and subsequent activity.

## Launch and recovery

```bash
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox"
source .venv/bin/activate
python -m civsandbox --provider rule-based --seed 42
python -m civsandbox --provider rule-based --scenario food_shortage --seed 42
```

A shorter calendar for a demonstration:

```bash
DAY_LENGTH_SECONDS=120 python -m civsandbox --provider rule-based --seed 42
```

For a fresh headless check, choose an unused temporary history filename:

```bash
MEMORY_PATH=/tmp/civsandbox-stage1-fresh.json python -m civsandbox --headless --provider rule-based --ticks 4800 --seed 42
python -m pytest -q
```

The pre-Stage-1 recovery point is local Git commit 34bec30. No private history or environment file needs to be deleted to run a fresh experiment. No artwork replacement, API call, wildlife, cooking or Participant Mode was introduced.
