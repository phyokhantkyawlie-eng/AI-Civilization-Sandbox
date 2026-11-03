# AI Civilization Sandbox

CSC472 Artificial Intelligence final project for a two-student team. **Animated characters integrated into the existing main simulation:** Mira, Nyra, Kairo, and Ren use the supplied four-direction artwork, observed grid movement, and smooth render-only interpolation. Existing needs, resource rules, numeric personalities, stable IDs, provider architecture, and saved social histories remain available; this integration adds no Gemini, social-memory, or advanced action-animation features.



## Current survival loop — Stage 1

The existing NPCs now follow a tick-driven daily routine: needs → goal → travel → timed work → actual inventory/resource effects → reevaluation. Hunger still rises toward 100, energy falls toward 0, eating one berry removes 35 hunger, and completed rest restores 8 energy. There are no duplicated UI need or food values.

- Berry bushes have stable position-based IDs, quantity, capacity, interval and growth progress. Click one to inspect them. Available/depleted artwork remains distinct. Default regrowth adds one berry every 20 ticks (5 seconds); shortage bushes use 80 ticks (20 seconds). Growth uses shared simulation-time boundaries, remains capped, and does not require NPC visits.
- Gather (3.5 seconds), eat (2.5 seconds), rest (1 second per recovery unit), and existing social activities use the existing nonblocking scheduler. Inventory and stock change only at completion after validation. `GATHER` outcome events occur only on success; `ACTIVITY` records describe accepted/in-progress gathering without claiming food was collected.
- A day lasts 600 simulation seconds by default, starting at 08:00. Morning is 06–12, afternoon 12–18, evening 18–20, night 20–06. Dawn/dusk lighting is cached and affects presentation only. Early-bird personality values vary preferred sleep/wake windows. Daylight favors a two-berry reserve; other hours favor one. Food urgency and incoming requests can override routine rest.
- At hunger 85+, gathering takes twice as long and travel advances at half its usual tick cadence. Hunger 100 or energy 0 triggers temporary recovery. NPCs rest through the same executor, recover after at least 3 seconds once energy is positive, then have 30 seconds of starvation grace to seek food. Exhaustion still interrupts at energy 0. Food is never created by recovery. No permanent death is implemented.

All values above are configurable through `.env.example` (do not overwrite a private `.env`). `REST_SECONDS`, `DAY_LENGTH_SECONDS`, `DAY_START_HOUR`, survival thresholds, slowdown and recovery durations are local configuration. Pause freezes clock, growth, needs and activities; speed changes simulated time consistently. Berries remain the only Stage 1 item. The existing item registry now includes consumption metadata and can later add raw/cooked chicken without a second inventory.

Launch with the existing command below, optionally adding `--scenario food_shortage`. For a faster day/night demonstration use `DAY_LENGTH_SECONDS=120 python -m civsandbox --provider rule-based`. See [STAGE1_SURVIVAL.md](STAGE1_SURVIVAL.md) for verification and limitations.

## Current direction: offline-first (Stage 0)

The normal game uses local Python rules. No API key, Google SDK, or network connection is required at runtime. `rule-based` is the default; `mock` remains an explicitly labeled offline test adapter. An old `AI_PROVIDER=gemini` setting resolves to rules. Normal game and experiment CLIs reject external providers, and the historical live smoke entry point is disabled. Existing private `.env` and social saves are preserved. Installation requires locally available packages or a prior dependency install.

```bash
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox"
source .venv/bin/activate
python -m civsandbox --provider rule-based --seed 42
```

Use `--scenario food_shortage` for the social scenario and `--headless --ticks 1000` for a terminal run. See [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) for current architecture, limitations and recovery, and [STAGE0_VERIFICATION.md](STAGE0_VERIFICATION.md) for executed checks. Historical API implementation notes below describe retained adapter code, not supported normal-game functionality.

## Setup on macOS / VS Code

Tested with Python 3.12.13, Pygame 2.6.1, Pillow 13.0.0, pytest 9.2.0, and python-dotenv 1.2.4. Use Python 3.12 for the tested Pygame wheel.

```bash
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox"
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m civsandbox --provider rule-based --seed 42
```

In VS Code, open this folder and select `.venv/bin/python` using **Python: Select Interpreter**. Run commands from the project root. Upgrade an existing virtual environment with `python -m pip install -r requirements.txt`. The `.vscode/launch.json` configuration launches the main package offline with the rule-based provider using F5. Do not use Run Python File on `civsandbox/__main__.py`: its relative imports require module launch (`python -m civsandbox`).

## Controls and display

- Space: pause/resume (starts running).
- Up/Down: select 0.5x, 1x, 2x, or 4x speed.
- Escape or window close: exit cleanly.
- Click a villager: inspect the **State**, **Traits**, **Trust**, and **Memory** tabs. Click a tab or press Tab to switch; use the mouse wheel in Memory to page older/newer records. State includes needs, food, actual grid position, current action, last executed movement destination, displayed facing direction, and current goal type. Traits shows numeric personality; Trust shows outgoing trust and recent interactions; Memory shows who interacted, timestamp, result, and the actual effect on this NPC’s trust. Selection follows moving NPCs. Repeated clicks cycle through shared tiles; empty space deselects.

The 1100x750 window retains the 24x18 village with grass, dirt paths, trees, berry bushes, houses, and water. Grass and dirt are walkable; other terrain is blocked. Four supplied characters replace the placeholder circles. Names appear near them, and selected characters have a foot-level highlight. Objects and characters are drawn in foot-depth order so foreground terrain occludes correctly. The sidebar retains the live event log and existing inspection tabs.

## Character integration

The main application is `python -m civsandbox`, not the separate existing `phase1a` prototype. For this stage use the explicit rule-based command above; it requires no API key and makes no Gemini requests. NPCs choose reachable resource/exploration goals through the existing provider and follow BFS routes. Needs, resting, and terrain validation remain intact; no scripted movement sequence drives animation.

| Stable ID | Current character | Original preserved personality | Artwork |
| --- | --- | --- | --- |
| npc-1 | Mira | Generous | assets/characters/mira.png |
| npc-2 | Ren | Selfish | assets/characters/ren.png |
| npc-3 | Nyra | Cautious | assets/characters/nyra.png |
| npc-4 | Kairo | Friendly | assets/characters/kairo.png |

Only names and artwork mapping change. Existing numeric needs, inventories, colors, personalities, spawn tiles, tick rate, and directed relationships remain attached to the same IDs. Old saved memories use stable IDs and continue to load. Dirt recolors previously clear grass lanes; it introduces no new blocked tiles and preserves map connectivity.

`SpriteAnimator` in `civsandbox/animation.py` selects idle (column zero) or four walking frames for down/left/right/up using elapsed seconds. Animation speed is configurable:

```bash
python -m civsandbox --provider rule-based --seed 42 --animation-fps 10
```

The renderer observes every completed simulation tick through an optional fixed-ticker callback. `CharacterView` queues each actual cardinal move, interpolates the character feet, and preserves intermediate corners even when multiple simulation ticks occur in a single frame. No visual coordinate is written back to the NPC. Rendering trails logical tile updates while interpolating; the inspector reports actual model position and action. Facing follows the displayed observed movement, and idle retains the last facing. Pause freezes visual movement and displays idle. Walking resumes with the simulation.

Frames use one uniform character scale and a common foot anchor. Runtime frame canvases stay 40 × 50; sprites are loaded/scaled once, never resized per animation frame. World layering and sprite hit boxes follow interpolated feet, so clicking the displayed artwork selects its real NPC. There are no gathering, eating, resting, talking, sharing, or emotional animation sets yet: stationary actions use facing-specific idle art.

The four originals are **887 × 1774**, not 512-pixel cells. RGB backgrounds on Mira/Kairo/Ren required conservative cleanup; Nyra has real alpha. All 80 processed frames are bundled in `assets/processed/`. Review `assets/inspection/contact-dark.png`, `contact-light.png`, `frames.json`, and `README.md` for source hashes, extraction bounds, alpha inspection, and remaining halos/similar source poses. Original files are preserved unchanged.

```bash
# Only needed when deliberately regenerating assets:
python -m civsandbox.prepare_assets
```


## Headless mode and tests

```bash
python -m civsandbox --headless --ticks 1000 --seed 42
python -m pytest -q
```

Headless mode prints JSON with the seed, completed ticks, complete NPC state, bush stocks, resource mutation ledger, action events, and AI provider status. It never imports Pygame or needs a display. Tick counts must be nonnegative; the default is 100. Identical seeds, tick counts, and initial social histories reproduce offline mock and rule-based runs. The CLI restores history on launch, so use a new MEMORY_PATH for a fresh run; reusing a history file intentionally changes the initial state. Live Gemini runs depend on model output and network completion timing and are not guaranteed reproducible. The CLI loads `.env` from the project root; process environment variables override it. Mock is the default and needs no key or network. `Simulation()` constructed directly still defaults to Phase 2 rules for compatibility.

## Phase 2 rules and priorities

Each new physical world starts at hunger 25, energy 90, and zero food. Hunger 100 means starving; energy 0 means exhausted. Inventory capacity is five. Phase 4 adds numeric personality effects to social choices; the original physical needs/actions remain in place.

These are the original physical priorities, also used for local AI fallbacks. Phase 4 inserts personality-based social responses, food requests, and interaction choices after eating/resting and before gathering/exploration (documented below). Every unpaused tick, the simulation increments its tick, replenishes resources when due, then processes NPCs in stable ID creation order. Each NPC first gains 1 hunger and loses 1 energy, clamped to 0–100, then chooses and executes exactly one action:

1. **Eat:** if hunger is at least 30 and food is carried, eat one unit, reducing hunger by 35. This takes priority even when exhausted.
2. **Rest:** if energy is at most 20, rest. Continue resting until energy reaches at least 70 at decision time; each REST adds 8 energy (net +7 after the needs update). Eating may interrupt rest.
3. **Acquire food:** when carrying fewer than two units, keep a useful food goal. Choose the closest reachable stocked bush by BFS distance to an adjacent walkable tile; ties use coordinates. Walk to its approach, then gather. A goal persists through movement, rest, and meals until stocked, depleted, or unreachable. Depleted goals trigger replanning. If food is needed but no reachable stocked bush exists, WAIT and retry on the next tick.
4. **Explore:** when stocked, retain a reachable exploration goal until arrival. Then choose a new seeded random reachable tile. Higher-priority needs can interrupt exploration.
5. **Wait:** if no useful valid action exists, WAIT. A provider request rejected by validation is logged and replaced with WAIT.

High hunger therefore triggers eating immediately when food exists; an NPC without food seeks a resource. Low hunger does not prevent stocking two units for later. Starvation is represented by capped hunger, without damage or death in this phase.

### Action contracts

`Action` and `ActionType` define reusable physical and social requests. Physical actions remain MOVE_TO, GATHER, EAT, REST, and WAIT; social contracts are documented below. One shared validator/executor handles requests from every decision provider. Invalid actions have no execution side effects; per-tick needs still advance independently.

- MOVE_TO requires a distinct reachable walkable coordinate and positive energy. It follows one cardinal BFS step per tick and costs 1 extra energy. The destination may be several tiles away.
- GATHER requires a stocked bush exactly one cardinal tile away, free inventory space, and positive energy. It transfers one food unit and costs 2 extra energy, clamped at zero.
- EAT requires food and positive hunger; consumes one unit.
- REST requires energy below 100.
- WAIT always succeeds with no action-specific effect.
- Targetless actions reject supplied targets; targeted actions reject malformed, blocked, unreachable, or otherwise invalid targets as appropriate.

Bushes start with five food each. On ticks divisible by 20, each bush below capacity regains one unit. There is no wall-clock regeneration. The resource ledger records initialization, every gather, and every replenishment with tick, coordinate, before/after quantities, reason, and gathering NPC ID. Sequential validation prevents two NPCs taking the same last food unit.

## Architecture

```text
civsandbox/
  __init__.py
  __main__.py       CLI / graphical or headless entry point
  world.py          Immutable tiles, map generation, BFS, reachability
  agents.py         NPC attributes, numeric personalities, goals, needs update
  characters.py     Stable NPC name/art identity mapping
  animation.py      Pure animation timing and observed movement interpolation
  sprites.py        Cached Pygame frame loading and uniform scaling
  prepare_assets.py Reproducible extraction and inspection contact sheets
  social.py         Requests, directed trust, bounded memories, JSON persistence
  resources.py      Finite bush stock and complete mutation ledger
  actions.py        Typed requests, validation, execution
  decisions.py      DecisionProvider protocol and rule-based provider
  ai.py             Structured output, mock/Gemini providers, plan scheduler
  perception.py     Local observations and offered valid actions
  config.py         .env settings and provider factory
  smoke_test.py     Disabled historical API entry point
  simulation.py     Tick orchestration, snapshots, action log, fixed scheduler
  rendering.py      Pygame drawing, inspector, controls, application loop
tests/
  test_simulation.py
  test_behavior.py
  test_rendering.py
  test_ai.py
  test_live_gemini.py
  test_social.py
  test_animation.py
requirements.txt
.env.example
.gitignore
README.md
```

`Simulation(seed=42, decision_provider=...)` accepts a provider implementing `decide(agent, world, resources, rng) -> Action`. All three providers return the same `Action` dataclass (action kind, optional tile/NPC target, short reasoning, and optional request ID). Providers select actions; the shared validator/executor owns movement, inventory, and need effects. AI providers additionally receive each simulation tick and a list of NPCs for local observation.

Simulation state has no Pygame dependency. The fixed scheduler still advances four ticks per second at 1x independently of rendering (capped at 60 FPS). Pausing preserves the partial tick and freezes needs, actions, resources, and logs. Speed affects tick frequency; headless execution advances exact ticks without waiting.

## Provider and memory configuration

The default is `rule-based`. `AI_PROVIDER=mock` or `--provider mock` selects the offline structured-decision test adapter. CLI selection overrides `.env`. API keys, model names, API budgets, and API timeouts in legacy `.env` files are ignored by normal configuration loading. The rule factory does not import the optional adapter.

`.env` is optional. If needed, create it only when absent (do not overwrite an existing private file):

```bash
[ -f .env ] || cp .env.example .env
```

`MEMORY_ENABLED`, `MEMORY_PATH`, and action timing settings remain supported. Normal sessions restore bounded social history; use a fresh history path or experiments for a fresh controlled run.

The isolated `GeminiDecisionProvider` class remains in `ai.py` for compatibility with offline adapter-contract tests. It cannot be selected through the application factory or CLIs. Its optional SDK is no longer in `requirements.txt`. No live API test is part of this build.

## Phase 4 social rules

### Personalities

The four stable identities now have distinct initial traits. Traits are numeric values in 0–1; labels summarize them and do not determine outcomes by themselves.

| NPC | Personality | Empathy | Cooperation | Sharing | Risk aversion | Sociability | Trust gain rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Mira | Generous | .95 | .90 | .95 | .20 | .55 | 1.0 |
| Ren | Selfish | .15 | .20 | .10 | .30 | .25 | 1.0 |
| Nyra | Cautious | .55 | .50 | .50 | .90 | .30 | .4 |
| Kairo | Friendly | .80 | .85 | .80 | .25 | .95 | 1.0 |

Curiosity is also stored per NPC. Cautious positive trust gains are smaller; negative consequences are unchanged. All new directed relationships start at zero, unless loaded from a previous social-history file. `A.trust[B]` and `B.trust[A]` are independent integer values clamped to -100…100.

### Social actions and lifecycle

All social actions require a real, distinct NPC within Manhattan distance one (including shared tiles). They use no extra energy beyond the usual per-tick needs cost. The shared action validator is the only execution entry point; invalid requests do not transfer food or change trust. The simulation logs rejected attempts, including a failed interaction record when both NPC identities are real.

- **REQUEST_FOOD:** target another NPC by ID. The requester must have inventory room and cannot create a duplicate active request to the same recipient. It creates a unique ID and expires 12 simulation ticks later. Its active packet includes participants, creation/expiry timestamps, and whether the requester reported hunger at least 70. Requesting does not automatically cause a response or transfer.
- **SHARE_FOOD:** target the requester and include the exact request ID. Only the addressed recipient may answer, while nearby and before expiry. The giver must carry food and the receiver must have inventory room. Exactly one food transfers, conserving total inventory. The request is consumed and cannot be answered twice.
- **REFUSE_REQUEST:** the same identity, distance, ID, and expiry rules apply. It consumes the request without changing inventory.
- **TALK:** target a nearby NPC. This phase models a greeting event, not generated dialogue.

Expiry removes unanswered requests. Moving out of range invalidates answers until the NPCs return within range or the request expires. Pending requests end on shutdown and are not restored into a new physical world. Their IDs remain unique across persisted sessions.

Base trust consequences arise only from actual interactions: a received food unit gives +12 toward the giver, the giver gets +2 toward the receiver; refusal gives the requester -8 toward the refuser; expiry gives the requester -2 toward the unanswered recipient; a greeting gives its initiator +1 and recipient +2. Positive gains are multiplied by the owner’s trust-gain-rate trait and rounded to an integer with minimum one. Final scores are clamped, and memory records store the **actual** applied delta. Requests, invalid attempts, and session-end cancellations have zero trust effect.

### Provider-owned decisions

The engine defines validation, transfers, request deadlines, and consequences. It never schedules a particular NPC to share, refuse, or succeed. A provider must select the social action.

The rule-based provider and offline mock use trait-weighted seeded choices after addressing immediate eating/resting needs. They consider nearby incoming requests first. Share probability is clamped to .02–.98 from:

`0.6*sharing + 0.2*empathy + 0.2*cooperation + recalled_trust/200 - 0.25*risk_aversion - hunger/200 - (0.2 if carrying at most one food else 0)`

A failed willingness draw or unavailable food leads to a valid refusal. Hungry NPCs (hunger at least 55, zero food) may ask a nearby peer, preferring more trusted peers when recall is enabled. Stocked NPCs sometimes greet peers at a sociability/risk-weighted rate; highly social NPCs may approach a visible neighbor before continuing exploration. These are tendencies, not fixed social outcomes.

Gemini receives numeric traits, current needs/goals, immediate active requests, offered valid actions, and—only with recall enabled—relevant memory and directed relationship history. Its structured response goes through the existing offered-choice check and current-state validation. A response that arrives after expiry, resource loss, or movement is rejected safely. Existing cooldowns, budgets, nonblocking workers, and local fallbacks remain in effect. Mock decisions remain labeled mock; no mock result is claimed as genuine Gemini behavior.

### Bounded recall and persistence

Each NPC stores its latest 20 important interaction records. Records contain actor/target IDs, persistent simulation timestamp, action, result, and that NPC’s directed relationship effect. Only memories involving currently visible peers are retrieved for Gemini, at most six per context. The UI can page all 20 audit records.

`MEMORY_ENABLED=true|false` controls **historical recall**, not the physical world or audit collection:

- When true, decision providers can use relevant memories and historical trust.
- When false, the AI context omits both memory and relationship fields entirely. Other prompt fields, valid-action generation, and rule-based fallback preferences do not consult historical trust. Active requests and current physical observations remain available.
- Interactions still update auditable trust/memory records, and the inspector/headless output may show those audit records. They are never passed back to the AI while recall is disabled. This separation allows later experiments to observe outcomes without giving the agent historical knowledge.

The CLI loads `MEMORY_PATH` at startup and saves versioned JSON atomically on clean shutdown. Relative paths resolve from the project root; the default is `data/social_memory.json`, ignored by Git. Only directed relationships, bounded memories, the social clock, and the request ID sequence persist. World layout, needs, inventories, positions, live requests, keys, prompts, and provider internals do not persist. File validation finishes before any restored state is applied; corrupt/incompatible files are preserved. Save/load status appears in the UI and `memory_persistence` in headless JSON.

The social memory clock continues across launches so memories remain chronologically meaningful. The current physical simulation tick starts at zero; social events include both the local `tick` and persistent `social_tick`. `Simulation(..., memory_enabled=False, memory_path=...)` exposes the same controls to Python callers. Direct `Simulation()` instances remain in-memory by default for isolated tests.

Example memory-disabled run with a separate history file:

```bash
MEMORY_ENABLED=false MEMORY_PATH=data/no-recall-review.json python -m civsandbox --provider mock
```

For fresh comparisons choose a new history path for each run. Reusing an existing file deliberately resumes social history; it does not guarantee an identical full snapshot for the same seed.

## Verification

Current full-project suite: **122 passed, 1 skipped**, including the five unchanged `phase1a` prototype tests. Phase 4 previously passed 99 tests. The skipped case is the opt-in live Gemini smoke test; no genuine Gemini social decisions are claimed from offline tests. Existing physical simulation, timing, resources, no-key fallback, SDK configuration, responsiveness, inspector, and shutdown checks remain passing.

Prior social tests cover numeric personalities, independent/clamped trust, request identity/distance/expiry/duplicate rules, full and empty inventories, one-shot sharing and food conservation, refusal/expiry/failure events, bounded relevant recall, JSON save/load, monotonic timestamps, request cleanup/unique IDs, corrupt-file preservation, atomic restoration, save failures, disabled-memory prompt equality despite changed history, preserved immediate requests, trust-free fallback choices, social structured output, expired model responses, selected-provider execution, cautious trust growth, personality tendencies, and inspector tabs/paging. Test-only explicit action fixtures verify contracts; production social scenarios are not scripted.

Before character integration, a fresh in-memory 3,000-tick seed-42 mock run used zero API calls and produced 21 actual greetings. It produced no food requests or transfers on the resource-rich default map; no sharing result is fabricated. Those Phase 4 screenshots remain historical artifacts. Separate headless checks verify rule-based and no-key Gemini fallback, persistence, and memory-disabled operation. Native macOS Pygame rendering is checked and visually inspected.

Character tests additionally cover source hashes/dimensions/alpha, 80 normalized frames and contact sheets, correct character mapping and distinct images, all four walk frames per direction, turning, idle facing, FPS/delta validation, frame-rate independence, retained obstacle corners and idle gaps, pause/resume, unknown-state snapping, walkable dirt, every-tick observation, autonomous boundary-safe movement, unchanged NPC state under observation, and clicking interpolated artwork. The actual main application also ran for 180 native macOS Cocoa frames with NPC selection, an inspected screenshot, clean shutdown, and persistence verified. A 1,000-tick rule-based headless run completed with all four character identities and zero API calls. The optional live Gemini test remains skipped.

## Current limitations

NPCs can overlap, logical movement remains tile-based with renderer interpolation, and houses remain decorative blocked tiles. Supplied art has some similar-looking walk poses and faint edge fringes; see the asset inspection report. TALK is a greeting without conversation generation. Interactions are local and choices may produce few requests when food is plentiful; personality labels never guarantee outcomes. Only the latest 20 memories per NPC persist, and history is saved on clean exit rather than every tick, so a crash can lose unsaved history. Social history is not a full-world save. In-run event logs grow in memory.

Gemini behavior remains dependent on account/model availability, quotas, and network timing. In-flight SDK HTTP requests cannot be forcibly cancelled by Python threads; bounded slots, deadlines, and daemon workers preserve responsiveness. The experiment runner and results viewer are documented below. Survival/death mechanics remain unavailable.

Stop after this main-project character integration for review. No additional AI or animation phases are implemented.

## Stage 1 stabilization and visual QA

The baseline suite passed 122 tests with one opt-in Gemini test skipped. A straight-walk playback check found that the animation restarted at every tile and lost two walk frames. Rendering now consumes elapsed time on either side of each fixed tick, keeping walk phase across adjacent steps and accounting for speed changes. A second fix corrects the inspector caption when a rule-based villager is already selected.

A native Cocoa window check exercised sprite selection, Space pause/resume, both speed keys and Escape using injected Pygame events. The captured frame showed the four mapped characters with transparent backgrounds and aligned feet. The renderer loads and scales 80 character images once per renderer instance. Terrain and berry stocks are drawn from simulation state using Pygame primitives. Automated checks cover directional rows, frame anchors, idle gaps, obstacle corners and interpolation.

A fresh 300-tick seed-42 rule-based run completed with zero API calls. All sampled NPC positions were walkable. Two or more NPCs occupied the same tile on 26 ticks, so one character can obscure another. Repeated clicks cycle selection. The previously documented edge fringes and similar source poses remain visible at inspection scale.

## Stage 2 food shortage

Run either scenario in the existing graphical application from the project root. VS Code also offers a Food shortage launch configuration.

```bash
python -m civsandbox --provider rule-based --scenario default --seed 42
MEMORY_PATH=data/shortage.json python -m civsandbox --provider rule-based --scenario food_shortage --seed 42
MEMORY_PATH="$(mktemp -d)/history.json" python -m civsandbox --provider rule-based --scenario food_shortage --headless --ticks 1000 --seed 42 > shortage-run.json
```

On the default map, abundant bushes allow NPCs to stock up before reaching the hunger threshold for asking. The shortage places Mira, Ren, Nyra and Kairo on adjacent tiles along a connected lane. Their starting food quantities are 0, 5, 0 and 4, and their hunger levels are 78, 12, 67 and 18. Two reachable berry bushes each hold one unit and replenish every 80 ticks.

Within conversation distance, a villager can observe signs of hunger and whether another NPC carries food. Exact peer inventory and hunger remain private. After eating/resting priorities, the rule policy handles incoming requests, then hungry villagers may ask an adjacent food carrier. Requesters wait while the addressee remains nearby. With recall enabled, they prefer trusted peers and avoid asking a recently remembered refuser again for 12 ticks. Existing personality and reserve rules determine each response.

In the JSON output, count interaction outcomes from events with `social=true`. The request ID links opening and resolution. Participant events include directed trust deltas and the IDs receiving a memory. Each executed action records hunger before needs advance, at decision time and after execution. The CLI uses the configured history file across launches, so use a fresh path for independent comparisons.

Observed rule-based runs from fresh histories, 1,000 ticks each:

| Scenario | Seed | Requests | Shares | Refusals | Greetings |
| --- | ---: | ---: | ---: | ---: | ---: |
| Default | 7 | 0 | 0 | 0 | 6 |
| Default | 42 | 0 | 0 | 0 | 10 |
| Default | 99 | 0 | 0 | 0 | 8 |
| Food shortage | 7 | 15 | 2 | 13 | 0 |
| Food shortage | 42 | 17 | 1 | 16 | 2 |
| Food shortage | 99 | 15 | 1 | 14 | 1 |

## Stage 3 Gemini verification

The historical external smoke test is disabled in the current offline-first build. Use `python -m civsandbox --headless --provider rule-based --ticks 1000 --seed 42` instead.

The application labels missing Gemini configuration as **offline rules**. The selected villager's inspector shows its executed action, provider mode, fallback status, public explanation or fallback reason, and recent AI events for that villager. Responses expire after 12 simulation ticks even if their action remains legal. The wall-clock timeout, current-state validation, bounded workers, per-agent cooldown, and per-run budget also apply. The 12-tick limit gives a decision the same maximum lifetime as a social request. Fast headless runs and increased simulation speed can therefore discard more replies.

Offline checks exercise the installed google-genai 2.34.0 serializer and decoder using an intercepted HTTP request, including filtering private thought parts. They also exercise deeply nested invalid JSON, stale but legal decisions, provider switching, offline fallback, rate limits, and rendering with blocked requests. The real endpoint, account access and model quality require the opt-in smoke test.

## Stage 4 experiments

Paired social-memory trials run through `python -m civsandbox.experiments --provider rule-based --runs 3 --ticks 300 --scenario food_shortage`. See EXPERIMENT.md for metrics, denominators, isolated histories, output files, live-call authorization and limitations.

## Stage 5 visual polish and occupancy

The village now uses cached programmatic grass/path textures, flowers, layered tree crowns, berry clusters and house details. Original PNGs, character scale, foot anchors and animation timing are reused. Nameplates render above scenery and separate vertically when villagers share a logical tile. Foot-level offsets keep shared occupants identifiable without changing their simulation coordinates. Clickable Pause/Resume and speed buttons accompany the existing keyboard controls and inspector tabs.

Movement reservations use the current occupied tiles in stable NPC order. An available detour is preferred. If no unoccupied route exists, an NPC waits three contested ticks, then may pass on its ordinary walkable route. This deliberately permits temporary overlap to recover in one-tile corridors and at shared interaction destinations. All resulting steps pass through existing action validation and the renderer's tick observer. This changes movement trajectories and can change social outcomes, so earlier experiment counts describe earlier code.

The normal game retains its latest 8,192 simulation events and resource changes. Experiment trials reserve a finite event window proportional to their requested duration so metrics cover the whole trial. Older normal-game events are unavailable after trimming. Character images load once per renderer, ground textures and name labels are cached, and movement routing executes on simulation ticks.

Before this stage, terrain used flat colors, controls were keyboard-only and villagers could move directly into occupied tiles. After this stage, the village has decorative texture and fuller vegetation, clickable controls, occupancy-aware detours, bounded waiting and shared-location visual separation. Corridor recovery intentionally permits passing rather than promising exclusive occupancy under every layout.

Stage 5 verification passed 141 tests with the optional live Gemini check skipped. Native Cocoa rendering ran for 160 frames while injected mouse events exercised selection, pause/resume and both speed buttons. Regression tests cover detours, bounded corridor waiting, deterministic replay, legal positions, bounded histories and reuse of cached ground surfaces.

## Stage 6 social feedback

Executed GATHER, EAT, REST, REQUEST_FOOD, SHARE_FOOD, REFUSE_REQUEST and TALK events now create temporary notices attached to stable NPC IDs. Repeated resting ticks do not refresh the same rest notice. Each actor has at most one action card and one reaction card. Cards expire after three wall-clock seconds, including while paused. Placement stays within the map, avoids other cards and character/name areas, and uses a connector to the speaker. If all available placement slots are occupied, a card can be omitted for that frame.

Rule-based and mock social speech use explicitly attributed templates. Gemini speech cards display the accepted public explanation, labeled “Gemini explanation”. It is explanatory text rather than additional model-generated dialogue. Invalid and merely proposed actions do not create action cards. Reaction labels follow explicit consequences: receiving a pending request gives Surprised, receiving food gives Happy, receiving refusal gives Angry, and an unanswered request expiring gives its requester Worried. These labels are event annotations, not a psychological model.

The social log shows local tick, actor, target, result and outgoing trust deltas for both participants. Each participant's recorded delta already incorporates personality scaling and trust clamping. Named presentation hooks are idle, walk, gather, eat, rest, talk and share. All states except walk use existing facing-specific idle frames. The original sprites and walk animator are reused.

Visual feedback reads numbered committed events so trimming old history cannot replay notifications. It does not change needs, actions, RNG, relationships or model calls. Test coverage includes rejected-action suppression, expiry without replay, Gemini attribution, recipient identity, fallback states and bounded non-overlapping layout.

## Stage 7 results viewer

Generate and inspect evaluation charts with `python -m civsandbox.results` to list saved experiments, then `python -m civsandbox.results experiments/DIRECTORY --show`. The same command without --show exports PNG charts for presentation. New trials retain hunger trajectories and recent decision records. RESULTS_GUIDE.md explains unavailable historical fields, metric denominators and interpretation.

## Final delivery and presentation

Use DEMO_GUIDE.md for the three demonstration modes and a 5–8 minute presentation. ARCHITECTURE.md summarizes modules and data flow. TROUBLESHOOTING.md covers launch, configuration, history and plotting issues. FINAL_VERIFICATION.md records executed final checks and remaining verification requirements. EXPERIMENT.md and RESULTS_GUIDE.md document scientific metrics and interpretation.

## Gameplay pacing, inventory and user interface overhaul

The main screen now uses the display name **Starfall Village** and shows day/time, village status, speed, selected villager, readable activity, needs bars, berries and short village news. Press **F3** (or Fn+F3 if macOS intercepts the key) to open the existing developer view with tick, seed, provider details, API budget, personality, trust, memories and detailed events. Press F3 again to return. Play/pause and speed buttons retain their keyboard equivalents. Click a berry bush to inspect actual quantity and its next regrowth time. Normal panel clicks preserve selection.

Hunger remains 0 for no hunger and 100 for starvation. The hunger bar grows toward danger, with Full below 55, Hungry from 55 and Starving from 85. Energy grows toward full rest, with Exhausted at 10 or below and Tired at 30 or below. The pure StatusThresholds value in ui_state.py configures these thresholds. These are presentation labels, not new need variables.

### Gameplay clock and timed effects

All activity timers run on fixed simulation ticks. At 1×, one tick is .25 seconds. Pause freezes progression, and speed scales progression uniformly. The village clock advances one displayed minute per simulated second starting at 08:00. Rendering interpolation and feedback cannot transfer food or alter trust.

Defaults are 3.5 seconds to gather, 2.5 seconds to eat, 2 seconds to greet, 2 seconds to deliver a request, and 2.5 seconds to answer it. A typical request-response exchange takes 4.5–4.75 seconds depending on NPC turn order. Both participants stop and face one another. An active request holds the conversation location while allowing eating, resting and a response. Conflicting social activities are excluded from valid choices. A completed social interaction starts a 10-second cooldown for both participants.

Needs increase once per simulated second. The original +1 hunger and -1 passive energy update remain intact at that interval, while movement/gathering retain their extra energy costs and resting retains per-tick recovery. This rate was adjusted because the old four-updates-per-second rate combined with longer gathering/eating kept villagers in a near-continuous food loop. Regeneration rules remain unchanged: default bushes replenish one unit every 20 ticks and shortage bushes every 80 ticks.

An action is validated and reserved at its start. Its inventory, hunger and social consequences execute once at completion after revalidation. If a source depletes or a request becomes invalid, the completion is rejected safely. Started events explicitly differ from completed events; food-conservation counts use executed completion events. Feedback can display a validated in-progress activity before its final effects. Speech/action indicators now age in simulated time and freeze during pause. The request lifetime extends to at least 32 ticks by default to permit eating and answering within the conversation.

The .env configuration accepts:

```dotenv
GATHER_SECONDS=3.5
EAT_SECONDS=2.5
GREETING_SECONDS=2
REQUEST_SECONDS=2
RESPONSE_SECONDS=2.5
SOCIAL_COOLDOWN_SECONDS=10
NEEDS_INTERVAL_SECONDS=1
```

Positive durations round up to fixed ticks. ActionTiming supplies the same configuration to Python callers. Its instant() mode exists for low-level atomic provider fixtures. The normal application uses paced defaults. Experiment configuration records timing values and each trial uses the same timings; earlier saved experiments describe earlier gameplay and should not be pooled with new runs without version control.

### Item inventory and compatibility

inventory.py implements item IDs, names, quantities, total capacity, validated add/remove and atomic transfer. Berries are the single supported item. Each agent owns one inventory; the existing food attribute remains a validated compatibility view of its berry quantity. Gathering, eating and sharing use inventory operations. Public snapshots retain food and also include inventory. Refusal never changes inventory.

Inventories belong to physical session state and reset with a new world. Existing JSON social history continues to persist trust and memories only. No database or full-world save has been introduced. Pending activities are canceled on shutdown without applying unfinished effects.

pacing.py adds a gameplay activity scheduler around the existing atomic action executor. It reserves participants and retains the original decision source while an action runs. Existing providers still return Action objects. Pending model requests avoid starting a long fallback harvest that would prevent timely consumption of a model reply. Incoming social requests interrupt cached movement goals and remove movement from the current action menu.

### Cleanup and verification

The phase1a prototype still has its launch path and five tests, so it is retained. Its identical extraction helpers now delegate to civsandbox.prepare_assets. Its own build layout and animation code are preserved. Launch it within the full project. The previous preprocessing file is backed up in delivery/overhaul_backup/phase1a_preprocess.py before consolidation. Original artwork and normal saved histories were not deleted. Existing delivery ZIPs and recorded experimental outputs remain historical snapshots.

Baseline: 149 tests passed, 1 opt-in live test skipped. The updated suite passes 161 tests with 1 skip. Old atomic fixtures explicitly select instant timing where appropriate; gameplay tests exercise the normal paced flow. Food conservation tests count only executed completions. Added checks cover durations, once-only effects, pause/speed, social reservations, pair cooldowns, face orientation, latest-state validation, inventory constraints/transfers, UI status mapping, bush inspection, seeded replay, and pending Gemini compatibility with a fake transport. The prototype's five standalone unittest checks passed.

Two 300-tick CLI checks with rule-based and mock providers completed under food_shortage, each with zero API calls. The native Cocoa run exercised selection, F3, pause/resume, speed changes and inspection of bush (10, 3). Screenshots were reviewed for needs bars, attributed speech, inventory and resource state. No live model test or new research experiment was run.

Manual presentation checks:
- Open the normal panel and F3 view, check typography and projector scaling.
- Select each NPC and compare bar severity, activity and berries with F3 values.
- Watch a request and response: both participants remain nearby and face each other.
- Pause during gathering/eating, then resume at 1× and 2×; effects occur only at completion.
- Click stocked and depleted bushes; compare berry quantity, appearance and countdown.
- Observe a refused request and a successful share when chosen; verify refusal preserves food and sharing conserves total inventory.
- Close/reopen with your normal history and verify trust/memory restoration; inventories start fresh.

Limitations remain explicit: temporary corridor passing can allow overlap, cooldowns can reduce social opportunities, source poses have minor inconsistencies, and current inventories are not saved across physical sessions. Pending/stale model decisions may be rejected while the simulation progresses. Current numerical experiment outcomes differ from archived releases after timing changes.
