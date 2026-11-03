# Stage 2 — living chickens and conditional hunting

## Implemented

- Two living chickens by default, unique non-reused IDs, position, state/activity, life state, movement cadence, threat radius, bounded fear/calm periods and exclusive claims.
- Shared-grid IDLE → WANDER/FLEE → IDLE behavior: peck/rest, occasional movement, obstacle/water avoidance, fleeing active nearby villagers. Wildlife uses its own seed-derived RNG and the existing fixed tick, pause and speed system.
- Controlled replacement after a delay, accessible free spawns, a maximum population cap, bounded dead records and no birth-to-hunt event hook.
- HUNT through the existing Action model, shared validator and ActionProgress. The pursuit updates paths when the chicken moves, respects ordinary hunger slowdown and movement reservations, and has time/distance/energy limits. Final adjacent catch timing, life, ownership, energy and capacity are revalidated before any reward.
- One raw chicken per successful catch, one completion event, no duplicate rewards; failures/cancellations release claims, create one failure record, add no food and start cooldowns. Normal rules retain at most one raw reserve.
- Original programmatic chickens in existing render depth layers, peck/walk/flee indications, idle-sprite hunting feedback, actual disappearance after a catch, inventory/news updates. No new NPC art, combat animation, weapons or gore.

## Conditional policy and Stage 3 boundary

The offline rule policy first handles eligible social responses, eating, rest, night routines and nearby social opportunities. Hunting requires hunger at least max(65, configured hungry), zero carried berries/raw chicken, spare capacity and energy at least max(40, minimum hunt energy + 12). Only living unclaimed targets within six Manhattan tiles are considered. Reachable nearby berries are preferred. Personality risk/curiosity, hunger and travel cost determine utility; no character-name scripts or spawn events are used. The existing food goal is displaced only when its available berry opportunity is not nearby.

Raw chicken is a future cooking ingredient, **not edible yet**. It cannot reduce hunger or replace berries, and berry sharing remains compatible. Cooking/cooked chicken belong to Stage 3. The one-item reserve bounds hunting while that ingredient has no consumption loop. This is a current gameplay limitation, not an implied cooking feature. Berries remain available through the original regeneration system; hunting is never mandatory.

## Local configuration

Durations below use simulated seconds at 1x and freeze when paused. Env changes do not require editing existing private files if supplied inline in the launch environment.

| Setting | Default |
| --- | --- |
| CHICKEN_STARTING_POPULATION / CHICKEN_MAX_POPULATION | 2 / 4 |
| CHICKEN_RESPAWN_SECONDS | 60 |
| CHICKEN_MOVE_SECONDS / CHICKEN_FLEE_SECONDS | 3 / 1 |
| CHICKEN_THREAT_RADIUS | 2 tiles |
| HUNT_TIMEOUT_SECONDS / HUNT_MAX_STEPS | 20 / 12 |
| HUNT_CATCH_SECONDS | 2 seconds continuously adjacent |
| HUNT_COOLDOWN_SECONDS | 40 |
| HUNT_MIN_ENERGY | 12 |

The maximum is a cap, not a breeding target. Replacement restores the starting population after hunts. Population zero intentionally disables initial chickens. Failed free-tile searches retry after the configured delay. Invalid populations, nonpositive durations and catch times exceeding pursuit budgets are rejected. Recent dead records are retained up to 16 for inspection, while unique ID sequence numbers continue increasing.

## Actual seeded observations

Provider: local rule-based; fresh in-memory social histories; 2,400 ticks = 600 simulation seconds per run. Five seeds in each scenario, ten runs / 24,000 total ticks. Each trial started with two chickens; no production outcomes were scripted.

| Seed | Default attempts / successes / failures | Shortage attempts / successes / failures | Shortage replacements |
| --- | --- | --- | --- |
| 7 | 0 / 0 / 0 | 1 / 1 / 0 (Mira) | 1 |
| 21 | 0 / 0 / 0 | 0 / 0 / 0 | 0 |
| 42 | 0 / 0 / 0 | 0 / 0 / 0 | 0 |
| 84 | 0 / 0 / 0 | 0 / 0 / 0 | 0 |
| 123 | 0 / 0 / 0 | 0 / 0 / 0 | 0 |

Every run ended with two living chickens, no active pursuit, and zero API calls. No hunt began within four simulation ticks (one second) of any spawn in these checks. Every successful hunt matched one raw item in an inventory. Hunting was rare and none followed replacement, so there was no hunt-every-respawn pattern to fix. These small samples demonstrate conditional behavior; they do not estimate general hunting probabilities or guarantee a live demo outcome. Controlled tests, rather than fabricated natural events, exercise failed pursuits.

The genuine numeric run records are saved locally in `artifacts/stage2/seed_runs.json` (generated, ignored by Git). Existing experiments remain available; new configuration exports/fingerprints include wildlife settings, initial chickens and wildlife RNG state so older research output is not confused with this revision.

## Verification and manual QA

Before changes: 188 passed, 1 skipped. The final full suite in the main project passed **217 tests, with 1 archived live test skipped and 0 failures in 21.89 seconds**. Command:

```bash
PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/civsandbox-stage2-mpl .venv/bin/python -m pytest -p no:cacheprovider -q
```

The normal CLI additionally completed 2,400 ticks for both rule-based and mock providers, with network/DNS access and Google SDK imports blocked. Both retained all four NPCs and ended with two living chickens and zero API calls. Seed-7 shortage results were one raw item for rules and three for the explicitly offline mock; mock output is not a model response. Private environment/history fingerprints and original artwork were verified unchanged. Twenty-nine new regression cases cover spawns/caps/terrain/FSM, fear/calm, current-state eligibility, strict final timing, exclusive claims, moving-target replanning, failures/cancellations, timeout/distance limits, no duplicate meat, deterministic delayed respawn, conditional policy, no hunt-on-spawn, raw inventory compatibility, pause/speed, existing movement, local perception/schema, read-only observation views, configuration and render disappearance. The suite prohibits network/DNS attempts. No live external test or package download was made.

SDL dummy screenshots were rendered and inspected for pecking/fleeing visuals; automated drawing checks verify disappearance and notices. Native interactive visual QA was not performed. Manual checklist: watch wandering/pecking and approaching villagers; check blocked terrain and water; pause during a pursuit and resume at different speeds; inspect inventory/news; observe an escaped hunt and a catch; wait for delayed replacement and confirm healthy villagers ignore it. Original NPC sprite integrity and existing regression tests remain in the full suite.

## Launch and recovery

```bash
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox"
source .venv/bin/activate
python -m civsandbox --provider rule-based --seed 42
python -m civsandbox --provider rule-based --scenario food_shortage --seed 7
```

For a fresh comparable offline run, use a previously unused temporary history filename:

```bash
MEMORY_PATH=/tmp/civsandbox-stage2-fresh.json python -m civsandbox --headless --provider rule-based --scenario food_shortage --ticks 2400 --seed 7
python -m pytest -q
```

Existing normal-game social histories can change decisions; do not delete them to reproduce a check. Set CHICKEN_STARTING_POPULATION=0 for a no-wildlife comparison if needed. The pre-stage recovery point is Git commit `de99831`. No private data, artwork, environment or virtualenv is replaced.
