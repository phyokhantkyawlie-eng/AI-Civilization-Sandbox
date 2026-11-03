# Development guide — offline wildlife Stage 2

## Direction and launch

Extend the existing game. Local Python intelligence is authoritative; no network, API key, or Google SDK is needed for normal operation. Do not replace the four original characters or create a second application. External adapters in `ai.py` are archived compatibility code, excluded from the normal provider factory and CLI. `smoke_test.py` cannot make a live request. Do not enable live tests.

```bash
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox"
source .venv/bin/activate
python -m civsandbox --provider rule-based --seed 42
python -m civsandbox --provider rule-based --scenario food_shortage --seed 42
python -m pytest -q
```

For a new environment, use Python 3.12 and install `requirements.txt` from available packages before launch. Existing installed packages and `.venv` are retained. `.env` is optional; its example contains local settings only. Legacy `AI_PROVIDER=gemini` resolves to rules, and legacy credentials/model/budget/timeout are ignored. Explicit CLI selection takes precedence. `mock` is an offline structured-decision test adapter, not a language model.

## Responsibilities and boundaries

| Responsibility | Existing implementation and convention |
| --- | --- |
| World | `world.py`: 24×18 terrain, connectivity, seeded map construction and BFS. `resources.py`: finite bush stocks, deterministic replenishment, bounded change ledger. |
| Agents | `agents.py`: stable IDs, numeric personalities, bounded needs, Goal, directed trust and memories. `inventory.py` is authoritative item storage; `Agent.food` is a berries compatibility view. |
| Decisions | `decisions.py`: `decide(agent, world, resources, rng) -> Action`. Normal factory is `config.create_provider`. Use the simulation RNG, not global randomness or wall-clock time. |
| Planning | Existing persistent Goal plus `food_action`, BFS, and `occupancy.py` break goals into legal tile steps. `pacing.py` reserves and completes timed activities; no separate planner module is necessary now. |
| Executor | `actions.py`: shared `validate` and atomic `execute`. `ActionProgress` validates at acceptance and completion. Providers may manage goals, but must not move NPCs, transfer items, alter resources or apply social consequences. |
| Simulation | `simulation.py`: .25-second ticks; needs, resources, decisions, reservations, execution, invariants and numbered bounded events. It does not import Pygame. |
| Social | `social.py`: addressed expiring requests, nearby validation, transfers/refusals, directed trust consequences and bounded memory. Read history only through memory-enabled accessors. |
| Presentation | `rendering.py`, `animation.py`, `sprites.py`, `feedback.py`, `ui_state.py`: cached art, render-only interpolation, inspector, controls and event-driven notices. Visual coordinates never update logical positions. |
| Persistence/evaluation | Social JSON saves on clean exit; invalid history is preserved. Experiments use fresh providers, RNGs and no normal save path. `results.py` reads genuine exports and makes charts. |
| Wildlife / player controller | `wildlife.py`: chicken FSM, finite population, claims/deadlines. Updated once by Simulation in the same world. Human controller remains future work. |

All providers return the existing frozen Action model: MOVE_TO, GATHER, EAT, REST, WAIT, REQUEST_FOOD, SHARE_FOOD, REFUSE_REQUEST, TALK, HUNT. Do not bypass validation for a new decision source. Invalid actions must have no effects and receive a safe WAIT fallback. Decision explanations are public summaries, never unexecuted dialogue.

## Verified existing behavior

- Mira (npc-1, generous/green), Ren (npc-2, selfish/red), Nyra (npc-3, cautious/purple), Kairo (npc-4, friendly/blue). IDs own history; names and art follow `characters.py`.
- Hunger/energy 0–100, finite five-item berries inventories, gathering/eating/resting, deterministic regrowth and reachable food-shortage opportunities.
- Policy priorities: respond to incoming requests when safe; eat when hungry and stocked; recover low energy; consider social actions; retain useful food goals; explore or WAIT. Social willingness combines personality, needs and directed trust with seeded probabilities. Memory-off reads neutral trust/empty recall.
- Default action durations: gather 3.5 s, eat 2.5 s, rest 1 s per +8 unit, greeting/request 2 s, response 2.5 s; social cooldown 10 s. Needs change once per simulated second. Duration settings map to ticks, not rendering frames.
- Social partners are held during exchanges, face each other, and release on completion/cancellation. Requests, sharing, refusal and greetings create actual events; accepted activity indicators are distinct from committed outcomes. Template dialogue is labeled as rule based.
- Existing idle and four-direction walk frames remain intact. Other named animation states use idle fallbacks and indicators. 80 normalized frames load once per renderer at 40×50 with a common foot anchor; cached world graphics are reused.
- Space/buttons pause or resume, arrows/buttons adjust speed, clicking selects villagers or bushes, F3 opens detailed inspection. Memories/trust remain in the detailed tabs.

## Gaps to preserve for later survival stages

Temporary incapacitation and timed recovery now exist, but no death/health model does, so mortality/survival metrics remain unavailable. Berries are the only edible item; raw chicken is a bounded ingredient reserve. Cooking and a human decision controller remain future work. Social history persists, but physical world/inventory state is not a full game save. Rules use full-map resource knowledge, unlike the local structured adapter context. The current needs policy is priority based with a weighted social utility, not a general utility scorer across every action. Goal planning is limited to existing food/exploration/social routes. Corridor yielding deliberately permits temporary tile overlap after three blocked ticks. Resource/social/event histories are bounded audit windows, not unlimited archives. These remain limitations after Stage 1.

## Verification and future changes

Run the full pytest suite, then a fresh offline headless check. To avoid altering normal saved history:

```bash
MEMORY_PATH=/tmp/civsandbox-stage0-check.json python -m civsandbox --headless --provider rule-based --ticks 1000 --seed 42
```

Use a previously unused temporary filename for a fresh run. For reproducible paired trials use the existing experiment runner, which isolates history automatically. Tests prohibit socket/DNS attempts, including caught failures; CLI regression subprocesses additionally prohibit Google SDK imports. SDK serialization tests use fake HTTP only and skip when the optional historical SDK is absent. The historical live test always skips.

Automated SDL dummy tests exercise real frame loading, directions, interpolation, pause/resume, speed, inspection and shutdown. They do not establish human visual approval. Manual checklist: launch both scenarios, check four character colors and foot anchors, watch turns and corridor passing at .5×/1×/4×, pause mid-walk/activity and resume, inspect inventory/trust/memory, click a bush, and confirm dialogue appears only for actual exchanges and expires after simulation time advances.

## Recovery and privacy

The main project previously had no Git repository. Pre-change source, artwork, tests and prior experiments are preserved in `delivery/offline_stage0_before.zip` (verified ZIP integrity, 284 files). Git commit `fcfbfbf` preserves the pre-offline application and safe ignore rules. Use `git show fcfbfbf:path/to/file` for a read-only comparison or extract the ZIP into a separate folder. Never overwrite the current project or private saves merely to inspect the baseline.

Commit source, original/normalized artwork, tests, example settings and documentation. Ignore `.venv`, caches, `.env` variants, `data/`, `delivery/`, and generated `experiments/`/`artifacts/`. Do not delete ignored files. Normal `.env` and `data/` are excluded from recovery archives and Git; retain separate private backups as needed. Never include API keys, personal records or saved social histories in commits. No remote repository or upload is configured by this stage.

## Stage 1 survival conventions

`daynight.py` derives day/time/phase from the existing simulation tick; never store a second ticking wall clock. `survival.py` owns configurable consequence thresholds. Each agent stores only recovery deadlines, alongside existing authoritative hunger, energy and inventory. The renderer reads these values and derives labels; lighting surfaces are cached by bounded alpha (0–48).

`Resources.bushes` is the authoritative collection of BerryBush records. Existing `available`/`stocks` APIs remain compatible. Growth progress follows the global tick modulo each bush's interval, resets visually when full, and repeated regeneration calls for the same tick cannot duplicate berries. Regeneration catches up across skipped absolute ticks. Bush IDs derive from coordinates, preserving reproducibility. Mutation ledgers retain the existing 8,192-record limit.

Rules receive clock/survival settings through optional `bind_routines` and tick hooks, keeping the `decide(...) -> Action` contract. Numeric `early_bird` traits influence routine preferences. Priorities remain needs and valid social responses before optional routine behavior; urgent hunger bypasses night rest. Night rest occurs at the current walkable tile; entering houses and sleep animations are not implemented.

The scheduler now times rest, freezes duration at activity acceptance, and lengthens hungry gathering. Hunger slows logical travel cadence; interpolation still follows observed steps. Completed gather events are distinct from generic ACTIVITY progress records, so measurement and presentation cannot claim premature collection. ItemDefinition metadata lives in the existing inventory registry; future items must use that same inventory and executor.

Incapacitation cancels unfinished reservations and pending requests with a recorded cancellation, without transferring food or applying invented trust changes. Forced recovery uses validated REST actions. A minimum recovery deadline plus positive energy permits waking; starvation grace then allows food seeking. Continued scarcity may cause another temporary recovery, but there is no permanent unconscious state or death. Pause freezes every deadline. Experiments serialize clock, survival and timing configuration to distinguish this revision from historical results.

Stage 1 verification: 188 passed, 1 skipped, 0 failures; two 4,800-tick seeded offline runs conserved food. See STAGE1_SURVIVAL.md for observed runs and executed checks. Git commit `34bec30` preserves the complete pre-Stage-1 offline baseline. Private `.env`, normal histories and original artwork remain untouched.

## Stage 2 wildlife conventions

`Simulation.wildlife` and `Resources.wildlife` reference the same manager, not a second simulation. Chickens use the existing World and an isolated seed-derived wildlife RNG; no rendering frame or spawn callback chooses NPC goals. Never reuse a defeated chicken ID. Initial spawning and replacements select reachable free tiles; replacement targets the configured initial population, bounded by the maximum. A failed spawn retries after the same configured delay. Dead inspection records are bounded to 16; events drain into the normal bounded simulation log.

HUNT targets a chicken ID, not a coordinate or NPC. Shared validation distinguishes offered high-level eligibility from final timed/proximity validation. The existing ActionProgress holds the actor reservation, maintains a bounded Pursuit, replans through the existing BFS/Occupancy and moves via the existing MOVE_TO executor. Chicken movement can break the catch window. Completion alone transfers one raw item and marks the chicken dead; claims, deadlines, cooldowns and cancellation prevent duplicated rewards. Generic ACTIVITY events identify accepted pursuits; one completed HUNT event records the reward, and one HUNT_FAILED event records each abandoned attempt. Observation views offer visible IDs only and cannot execute final hunts.

Conditional rule utility combines hunger, curiosity, risk and travel cost. It never reads spawn events, character names, social histories when disabled, or hidden target positions outside the six-tile hunting perception range. Existing berry planning retains its documented full-map knowledge. A reachable nearby berry approach (within 6 + floor(4×risk) steps) prevents hunting. Candidate travel is bounded by floor(7 − 4×risk) steps; score must be at least .35. A five-second decision-check interval and 40-second post-attempt cooldown bound reconsideration. No new character scripts exist.

Raw chicken uses the existing Inventory and item registry with zero hunger reduction. Agent.food remains exclusively berries; neither eating nor social food sharing consumes raw meat. One raw reserve prevents pointless repeated hunting before Stage 3 cooking exists. Do not invent cooking, illness or raw-meat hunger benefits in Stage 2. Physical wildlife/inventory state is not persisted by the existing social-history save.

Population and pursuit configuration is recorded in new experiment exports, and initial fingerprints now include chickens and wildlife RNG state. See STAGE2_WILDLIFE.md for actual checks and frequencies. Pre-Stage-2 recovery point: Git commit `de99831`. Native interactive QA remains manual; SDL renders and automated movement/asset checks are executed.
