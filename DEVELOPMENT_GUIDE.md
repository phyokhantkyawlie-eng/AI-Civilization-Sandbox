# Development guide — offline Participant Mode Stage 5

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
| Decisions | `decisions.py`: utility candidates, emergency priorities and `decide(agent, world, resources, rng) -> Action`. Factory remains `config.create_provider`; use the simulation RNG for controlled choices. |
| Planning | `planning.py` supplies Candidate and bounded GoalPlan models. The provider retains task queues; BFS/occupancy execute travel and `pacing.py` reserves/completes activities. |
| Executor | `actions.py`: shared `validate` and atomic `execute`. `ActionProgress` validates at acceptance and completion. Providers may manage goals, but must not move NPCs, transfer items, alter resources or apply social consequences. |
| Simulation | `simulation.py`: .25-second ticks; needs, resources, decisions, reservations, execution, invariants and numbered bounded events. It does not import Pygame. |
| Social | `social.py`: addressed expiring requests, nearby validation, transfers/refusals, directed trust consequences and bounded memory. Read history only through memory-enabled accessors. |
| Presentation | `rendering.py`, `animation.py`, `sprites.py`, `feedback.py`, `ui_state.py`: cached art, render-only interpolation, inspector, controls and event-driven notices. Visual coordinates never update logical positions. |
| Persistence/evaluation | Social JSON saves on clean exit; invalid history is preserved. Experiments use fresh providers, RNGs and no normal save path. `results.py` reads genuine exports and makes charts. |
| Wildlife / player controller | `wildlife.py`: chicken FSM, finite population, claims/deadlines. Updated once by Simulation in the same world. player.py supplies human action choices for exactly one existing Agent; ParticipantUI routes in-game input to it. |

All providers return the existing frozen Action model: MOVE_TO, GATHER, EAT, REST, WAIT, REQUEST_FOOD, SHARE_FOOD, REFUSE_REQUEST, TALK, OFFER_FOOD, HUNT, COOK. EAT optionally names an edible item; Agent.food remains the berries compatibility view. Do not bypass validation for a new decision source. Invalid actions must have no effects and receive a safe WAIT fallback. Decision explanations are public summaries, never unexecuted dialogue.

## Verified existing behavior

- Mira (npc-1, generous/green), Ren (npc-2, selfish/red), Nyra (npc-3, cautious/purple), Kairo (npc-4, friendly/blue). IDs own history; names and art follow `characters.py`.
- Hunger/energy 0–100, finite five-item berries inventories, gathering/eating/resting, deterministic regrowth and reachable food-shortage opportunities.
- Policy priorities: respond to incoming requests when safe; eat when hungry and stocked; recover low energy; consider social actions; retain useful food goals; explore or WAIT. Social willingness combines personality, needs and directed trust with seeded probabilities. Memory-off reads neutral trust/empty recall.
- Default action durations: gather 3.5 s, eat 2.5 s, rest 1 s per +8 unit, greeting/request 2 s, response 2.5 s; social cooldown 10 s. Needs change once per simulated second. Duration settings map to ticks, not rendering frames.
- Social partners are held during exchanges, face each other, and release on completion/cancellation. Requests, sharing, refusal and greetings create actual events; accepted activity indicators are distinct from committed outcomes. Template dialogue is labeled as rule based.
- Existing idle and four-direction walk frames remain intact. Other named animation states use idle fallbacks and indicators. 80 normalized frames load once per renderer at 40×50 with a common foot anchor; cached world graphics are reused.
- Space/buttons pause or resume, arrows/buttons adjust speed, clicking selects villagers or bushes, F3 opens detailed inspection. Memories/trust remain in the detailed tabs.

## Gaps to preserve for later survival stages

Temporary incapacitation and timed recovery now exist, but no death/health model does, so mortality/survival metrics remain unavailable. Berries and cooked chicken are edible; raw chicken must be cooked. Participant Mode now controls one existing agent through the same scheduler; Observer Mode remains the experiment default. Social history persists, but physical world/inventory state is not a full game save. Rules use full-map resource knowledge, unlike the local structured adapter context. Utility ranking now covers survival and social goals with bounded multistep queues. It is a lightweight task planner, not a general-purpose search over arbitrary world states. Corridor yielding deliberately permits temporary tile overlap after three blocked ticks. Resource/social/event histories are bounded audit windows, not unlimited archives. These remain limitations after Stage 1.

## Verification and future changes

Run the full pytest suite, then a fresh offline headless check. To avoid altering normal saved history:

```bash
MEMORY_PATH=/tmp/civsandbox-stage0-check.json python -m civsandbox --headless --provider rule-based --ticks 1000 --seed 42
```

Use a previously unused temporary filename for a fresh run. For reproducible paired trials use the existing experiment runner, which isolates history automatically. Tests prohibit socket/DNS attempts, including caught failures; CLI regression subprocesses additionally prohibit Google SDK imports. SDK serialization tests use fake HTTP only and skip when the optional historical SDK is absent. The historical live test always skips.

Automated SDL dummy tests exercise real frame loading, directions, interpolation, pause/resume, speed, inspection and shutdown. They do not establish human visual approval. Manual checklist: launch both scenarios, check four character colors and foot anchors, watch turns and corridor passing at .5×/1×/4×, pause mid-walk/activity and resume, inspect inventory/trust/memory, click a bush, and confirm accepted dialogue uses real reading time, freezes on pause and remains in conversation history after logical completion.

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

Conditional rule utility combines hunger, curiosity, risk and travel cost. It never reads spawn events, character names, social histories when disabled, or hidden target positions outside the six-tile hunting perception range. Existing berry planning retains its documented full-map knowledge. Stage 4.5 replaces the old nearby-berry veto with a utility penalty, so a stocked bush does not forbid hunting. Candidate travel is bounded by floor(7 − 4×risk) steps; eligibility score must be at least .25, hunger at least the configured hungry threshold, with no carried edible food/raw reserve and a reachable cooking station. A five-second decision-check interval and 40-second post-attempt cooldown bound reconsideration. No new character scripts exist.

Raw chicken uses the existing Inventory and item registry with zero hunger reduction. Agent.food remains exclusively berries; neither eating nor social food sharing consumes raw meat. One raw reserve prevents pointless repeated hunting before Stage 3 cooking exists. Do not invent cooking, illness or raw-meat hunger benefits in Stage 2. Physical wildlife/inventory state is not persisted by the existing social-history save.

Population and pursuit configuration is recorded in new experiment exports, and initial fingerprints now include chickens and wildlife RNG state. See STAGE2_WILDLIFE.md for actual checks and frequencies. Pre-Stage-2 recovery point: Git commit `de99831`. Native interactive QA remains manual; SDL renders and automated movement/asset checks are executed.

## Stage 3 cooking and utility conventions

`cooking.py` owns the shared CookingStation lease and read-only observation. Placement inserts one blocked CAMPFIRE tile only when all other previously reachable tiles remain connected. Every NPC cooks from an adjacent walkable tile using the same validation. Ingredients stay in inventory until the timed executor atomically converts one raw item into one cooked item. Full inventories can convert one-for-one. Cancellation, invalid completion and shutdown release leases without creating food. Nutrition belongs in ITEM_DEFINITIONS (berries 35, cooked chicken 65, raw 0), not in presentation classes.

`planning.py` is a small bounded queue, not a second simulation or provider. The existing rule provider ranks Candidate components, handles emergency tiers, retains a GoalPlan and receives executor result callbacks. Plans contain at most six tasks, last at most 320 ticks (80 seconds), and fail after 80 ticks without progress. Failed-target retries normally wait 16 ticks; valid emergency meals/rest bypass that retry delay. WAIT plans reevaluate after eight ticks. Cooking contention waits within the existing plan. Moving chicken pursuits still belong to the tested hunting scheduler, not duplicated planning code.

Public debug state exposes actual candidate utilities, selected reasons, remaining tasks and replan reasons (F3 then P). Emergency interruptions are counted separately from failed plans. Invalidated targets, rejected tasks, bounded pursuit failures and stalled/expired plans are ordinary recorded failures, not simulation exceptions. Every physical effect remains in the common validator/executor. Decisions may update goals and queues, never inventories, positions, energy or resource stocks.

Numeric nature_affinity and resource_focus extend existing personality traits. No action depends on character names or receives identity-specific exemptions. Social willingness and directed trust still use the existing guarded memory accessors; experiments construct fresh providers/queues and isolated history for each condition. Candidate scoring does not consume random numbers for unselected goals. Exploration and selected social responses use seeded randomness.

The existing experiment runner now exports actual gather/hunt/cook/meal/incapacitation/failed-plan counters plus initial/final inventories. Fingerprints include the campfire, and configuration includes the nutrition catalog and cook timing. Do not compare older generated datasets as though they used this planner. Physical inventories, cooking leases and plans remain session state; social JSON persistence is unchanged. Berry sharing remains the supported social food transfer; cooked-meal sharing and full world saves are not added.

The pre-Stage-3 recovery point is Git commit `7609a00`. See STAGE3_COOKING_AI.md for measured verification, controls and known limitations.

Stage 3 final verification after interruption: 251 passed, 1 skipped, no failures. Six isolated 4,800-tick trials conserved berries/raw/cooked items; a fresh main-project trial reproduced saved seed-7 metrics. Normal rule/mock headless launches were checked with networking and SDK imports blocked. Native interactive QA remains manual.

## Stage 4 conversation conventions

Extend SocialSystem rather than creating another interaction log. `dialogue.py` contains typed session/turn metadata, SocialSettings and small authored banks; SocialSystem alone owns lifecycle, physical eligibility, cooldowns, events, trust and memories. The provider may propose a selected social goal, but proposals produce no speech or food. ActionProgress validates acceptance and completion, holds/faces both actors, and releases jobs and soft session reservations on cancellation. All transfers still use the shared executor and Inventory.

Only delivered DIALOGUE events from a real accepted session enter Feedback. Never turn WAIT timers, public decision explanations or rejected proposals into speech. Feedback has a 64-line pending presentation queue and 60-line history; renderer reading time is real seconds, logical sessions use fixed ticks, and pause freezes both. A completed/left session is readable in the panel instead of floating over moving characters. Headless execution never waits for presentation. Native visual QA remains manual.

Use guarded `trust_for` and `relevant_memories` for choices and templates, including avoidance. Cooldowns/repetition are interaction pacing in both memory conditions; they do not expose historical trust. Relevant past help must come from an actual earlier transfer. Do not invent disagreement, apology or gratitude outcomes. New voluntary OFFER_FOOD transfers one existing berry and uses the same validation/capacity rules as responses.

See STAGE4_CONVERSATIONS.md for settings, measured outcomes and limitations. The pre-Stage-4 recovery commit is `02ab707`; normal private saves and original art remain intact.

## Stage 4.5 presentation and food-goal conventions

`Renderer.draw_feedback` derives card geometry from current `character_rects`, which are rebuilt from interpolated CharacterView positions each frame. No world-wide layout search, cached screen anchor or connector line is permitted. Keep activity labels compact, hide them during visual movement/offscreen/overlap, prioritize accepted speech, and keep history independent. Feedback clears superseded activity notices and rechecks live session proximity before showing speech. Do not change authoritative simulation coordinates to place UI.

HUNT_FOOD utility includes hunger/nutrition, numeric curiosity/risk, pursuit cost, cooking travel/wait and available berry alternatives. On new eligible goal selection only, the provider samples uniform −12 to +26 utility units using the seeded simulation RNG; debug utilities record that component. A retained plan does not sample again. A five-second eligibility check interval and existing 40-second hunt cooldown prevent retry thrashing. Carried meals/raw ingredients, energy, bounded local pursuit and cooking access still gate hunting. Claim/reward/FSM/cooking rules are unchanged. Hunt selections create PLAN audit events; no spawn event commands a goal. The previous Stage 2/3 scarcity-only policy is historical.

See STAGE4_5_ACTIVITY_HUNTING.md for actual observations and limitations. Pre-change recovery: commit 3277b36. Preserve private histories and original art.

## Stage 5 control ownership

Simulation owns optional PlayerController; Agent identity and physical state are never duplicated. `set_participant(id)` cancels unfinished activities/leases/sessions, interrupts old provider plans and clears input, then assigns that same existing ID. `set_participant()` returns to Observer Mode. Do not retain simultaneous human and autonomous goals for one agent. Cached mock/rule plans must support interruption at handoff.

Only the source of Action choices changes. PlayerController returns Action or WAIT; Simulation sends it through the same occupancy, hunger cadence, ActionProgress and shared executor. The controlled agent skips autonomous decide/on_action_result and policy emergency interruptions; actual incapacitation and forced recovery still apply and clear input. The other three keep the existing provider. The human may cancel unfinished work explicitly, preserving uncommitted ingredients/resources. Never mutate inventory/positions from UI code.

ParticipantUI is a Pygame-only helper for mode cards, context actions, inspection and inventory. It reads authoritative state and submits Actions. It caches original-art previews/overlay, clears held directions on menus/focus loss, and prevents stale menu layouts from executing clicks. Normal HUD inspection stays on the player; F3 retains developer inspection. Contexts are nearby physical objects; choosing an unavailable action gives feedback and cannot bypass validation.

Incoming new TALK/OFFER_FOOD/REQUEST_FOOD actions targeting the human pause for consent before starting. Accepting stores one bounded action, revalidated in the next simulation tick; it never executes from UI. Greet-back/accept-and-thank choices authorize the existing authored turns, not autonomous decisions. After an actual addressed request completes its question, share/refuse uses the real request ID and common social executor. Player-initiated actions and AI responses to them retain normal rules. Temporary invitations alone produce no speech or food. A remote approach cannot freeze the human before consent.

Menus and pending-response prompts suspend the shared fixed-tick world transparently; they do not accumulate a catch-up backlog. Prompt reading/countdown uses real UI seconds independent of speed, and explicit pause freezes it. After 30 unpaused real seconds, cancellation releases sessions and records an actual zero-trust-change cancellation, never an invented answer/transfer. No real-time waits run in Simulation. Headless CLI/experiments stay Observer Mode; programmatic controller tests call submit/answer/advance_prompt explicitly. Participant mode/session/input is transient and not added to social JSON persistence.

See STAGE5_PARTICIPANT.md. Pre-change recovery commit: 422f618. Preserve existing original/normalized assets, private .env and normal social histories.
