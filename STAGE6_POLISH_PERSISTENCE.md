# Stage 6 — Game feel, UI polish and persistence

## Before and after

Stage 5 had a text-heavy narrow inspector, overlapping news/reading areas and social-only JSON persistence. Stage 6 retains the existing world, rules, original four sprite sets and offline providers while giving ordinary play a clearer portrait/role/status hierarchy, distinct histories, meaningful resource feedback, contextual explanations and a separate full-world checkpoint.

The normal HUD shows title, day/time, Observer/Participant mode, selected portrait/name/role, activity, real work progress, readable hunger/energy bars, authoritative inventory, friendly goal and short directed-trust summary. Technical tick/seed, exact values, codes, scores, cooldowns, paths and decision details remain available through F3. Needs are unchanged: hunger rises toward 100; energy falls toward 0. Labels are Well fed/Hungry/Starving and Rested/Tired/Exhausted using the configured thresholds. Item quantities/slots remain visible because they are useful gameplay information.

Selected nameplates now have a clear border, retaining existing foot halos, depth sorting, overlap offsets and interpolation. New render views initialize from actual saved facing, without inventing movement. Cached original idle frames supply portraits; original walk sprites/fallbacks are preserved. Tree canopy contrast, berry fullness/depletion, shore edges, chicken outlines and nearby interaction rings are procedural decoration on the same collision/resource map. Common bush quantities 0–5 have matching berry dots. No tile geometry, resource balance, AI scoring or wildlife mechanics changed.

F1 opens controls/help; Save/Load/Help are clickable. E/I/M and existing Participant controls remain. Unavailable actions now explain their actual blocker (full inventory, depleted bush, missing raw meat, busy campfire, exhaustion, claimed chicken or hunt recovery). These messages do not authorize anything: submit/execution still validate. Menu eligibility is computed once while the world is paused, avoiding BFS on every render frame.

## Histories and notifications

N opens timestamped village news; C opens a separate timestamped conversation history. A distinct conversation reading card remains readable at speed without covering the selected inventory/news. Above-NPC speech still requires a real nearby accepted session. Historical lines are never replayed as new actions or live conversations after loading.

World news derives only from committed gathering, hunting, cooking, meals, recovery and meaningful food interactions; trust feedback reflects actual directed changes. Progress, movement, WAIT, repeated rest units and ordinary greetings do not spam news. Consecutive identical actor/work messages within 60 simulation ticks are grouped with a count and latest timestamp. Resource/inventory/need changes remain authoritative; logs cannot generate food.

Retention is explicit and bounded:

| Data | Retained in a full checkpoint |
| --- | ---: |
| World-news entries | Latest 200, including grouped counts |
| Accepted dialogue turns | Latest 120 |
| Memories per NPC | Existing latest 20 |
| Resource mutation ledger | Latest 512 diagnostic entries |

Raw runtime debug logs remain bounded by the existing engine limit and restart on load. The separate transient reading queue remains 64 pending lines / 60 presentation-history entries. No existing persisted private file is truncated, migrated or deleted by this stage. F5 replaces one supported world slot intentionally; choose a different save path to retain separate checkpoints.

## Full-world save format and safety

The separate format is **civsandbox-world, version 1**, atomic JSON. Default slot: **data/world_save.json**. F5/Save explicitly writes; F9/Load asks before replacing unsaved progress and restores paused for review. Full-world saving/loading is not automatic on startup/shutdown.

Saved state includes all four stable identities, needs, item quantities/capacity, positions/facing, personalities, directed trust/memories, recovery deadlines, exact terrain, bush stocks/capacities/regeneration clocks, campfire location, chicken IDs/population/FSM/repopulation timing/cooldowns, day/time, offline provider/configuration, local RNG state, memory mode, player mode/ID, selected NPC and the histories above. API keys, SDK/network objects, external providers and arbitrary executable state are excluded. No pickle or eval is used.

All fields are validated in a fresh candidate before live play is replaced. Checks reject duplicate NPC/chicken/bush identities, wrong character names, blocked/disconnected positions, impossible needs/items/capacities, stock overflow or inconsistent regrowth clocks, invalid trust/memory, unsupported providers/versions, malformed/duplicate-key/non-finite JSON and oversized files. Food is read from one authoritative inventory per NPC; histories/actions are never executed to reconstruct state. Saves are local editable data, not an anti-cheat or cryptographic provenance system.

Only **committed effects** persist. Queued player commands, provider plans/caches, active pursuits/claims, cooking leases, timed work and conversation/request sessions are released on load. Unfinished gathering/hunting/cooking produces no reward; uncooked ingredients remain owned. A completed transfer/conversion is already reflected once in inventory and is not replayed. Agents reevaluate goals. Two loads of the same checkpoint reproduce one another, but replanning means loading is not promised to match uninterrupted play bit for bit. Historical dialogue stays history; no unfinished speech is fabricated.

Writes use a same-directory temporary file, flush/fsync and atomic replacement. A failed replacement preserves the previous slot. Foreign, legacy or unsupported-format files are not overwritten. Loads fail with a readable message and leave current play intact. Files over 5 MB are rejected. Legacy social JSON stays separate: new ordinary games retain existing social-only shutdown behavior; a loaded world has no legacy memory_path and cannot overwrite unrelated social histories on close. Save continued world progress explicitly with F5.

Private data/, saves/, *.civsave.json and interrupted .world-* writes are ignored by Git. Put personal saves there. No database or new dependency is required; requirements.txt stays valid.

## Actual verification

Baseline: **312 passed, 1 skipped**. Final staging and main-project full suites: **360 passed, 1 skipped, zero failures** (main: 20.04 seconds). The historical live-API test remains skipped. Tests cover the HUD words/live inventory/guarded relationships, truthful bounded event projections, separate accepted-turn history, contextual reasons, cached menu validation, Save/Load/Help/N/C controls, failure-preserved play, real berry dots, saved idle facing, scaled mouse targets, complete round trips in both modes/providers, no item multiplication on repeated loads, pending work/hunt/conversation safety, completed meat/dead IDs/repopulation, corrupt data, atomic failure, legacy file preservation, reproducible checkpoint restarts and one-time regeneration from the saved tick. Existing survival/social/animation/AI/experiment tests still run.

Guarded headless CLI checks actually ran for both rule-based and mock providers: save at tick 600, load with zero ticks and compare all inventories, then continue to tick 700. Each reported zero API calls. Genuine details are in ignored artifacts/stage6/cli_checks.json. Generated world_checkpoint.json is a real fresh seeded simulation checkpoint, not a user's private save.

SDL dummy captures were generated for Observer/Participant HUDs, news, conversations, help, loaded state and compact/large windows. They were inspected for layout. The final dummy rendering sample measured 120 frames: mean **0.673 ms**, p95 **0.719 ms**; checkpoint validation/write **8.899 ms**, **59,089 bytes**. These measurements concern one fixed offscreen scene on this environment, not native desktop/GPU frame rate, interactive input latency or a guarantee for all machines. Raw measurements are artifacts/stage6/render_check.json. No live API experiment was run.

## Launch, save and load

```bash
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox"
source .venv/bin/activate
python -m civsandbox --mode observer --provider rule-based --seed 7
python -m civsandbox --mode participant --character mira --provider rule-based --seed 7
python -m civsandbox --load data/world_save.json
python -m civsandbox --mode participant --character mira --window-scale 0.85
python -m pytest -q
```

Use --window-scale 1 (default), 0.85 (compact) or 1.25 (large). Rendering retains a 1100×750 logical layout and remaps mouse coordinates; this does not change world positions/speed or regenerate assets. F1 lists controls. Use --save-file saves/another.civsave.json for another interactive slot. A loaded graphical world starts paused; click Resume/press Space.

For a headless checkpoint with a fresh, unique temporary MEMORY_PATH:

```bash
MEMORY_PATH=/tmp/civsandbox-my-fresh-check.json python -m civsandbox --headless --provider rule-based --ticks 600 --seed 7 --save saves/offline.civsave.json
python -m civsandbox --headless --load saves/offline.civsave.json --ticks 100
```

Use an unused temporary history filename to isolate a new run. CLI --load restores the saved mode/selection/provider unless explicitly overridden; headless loading always uses Observer Mode. --save is headless-only; --save-file selects the graphical slot. The experiment runner continues creating fresh Observer trials without normal-game persistence, so human input/save history cannot leak into paired conditions.

## Manual native visual QA and limits

Native macOS/Retina interactive visual approval was not performed. Verify:

1. At 1× and optional window scales, title/time/mode, portrait, status bars, inventory, goals, relationship summary and buttons stay readable; mouse targets align. Open F1, N, C and F3 and return cleanly.
2. Select all four original characters. Check colors, foot anchoring, nameplate/selection visibility, depth ordering, corridor overlaps and true walking/idle directions at .5×/1×/4×.
3. Watch real berry dots disappear only after completed gathers and regrow in simulation time; inspect a depleted bush. Chicken death removes its visual; real raw/cooked items and need bars change only after validated completion.
4. Inspect contextual highlights and unavailable-action explanations. Conversation bubbles stay local/accepted; the separate reader remains readable with timestamps. No connector lines return.
5. Save during a gather, hunt, cook and food request; load and confirm unchanged committed inventory, free campfire/claims, no automatic rewards, retained history and correct mode. Resume explicitly. Try a damaged/unsupported file and confirm current play remains intact.
6. In Participant Mode, use all existing controls and invitations; switch Observer/Participant before and after loading. Test focus changes and held movement keys. Verify pause/speed and scaling on the actual display.

Known limits: explicit single-slot checkpoints, bounded histories, fresh planning after load, fixed logical world size and manual native-display verification. Existing corridor recovery may briefly overlap NPCs; prolonged accelerated dialogue can outpace the bounded reading queue. No unrelated gameplay, new artwork, external AI, SQLite or later-stage features were added. Pre-stage recovery: Git commit dce1d43.

Final main-project checks also executed guarded rule-based/mock CLI checkpoint round trips with unchanged inventories and continuation to tick 700. Actual SDL dummy startup/clean shutdown succeeded for Observer Mode, compact Participant Mode and large-window full-world loading. These do not establish native visual approval. All 89 existing private configuration/history/artwork fingerprints stayed unchanged; git diff --check passed.
