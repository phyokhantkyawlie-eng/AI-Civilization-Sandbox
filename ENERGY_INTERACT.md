# Energy balance and experimental gather presentation

This is a focused offline update to the existing game. Safe pre-change Git checkpoint: **b8c824d**. Original artwork, user saves, memory, inventory rules and hunger balance are preserved. The new animation remains installed for visual review; it has not been removed automatically.

## Old and new energy units

Energy remains 100 fully rested / 0 exhausted. Previously every needs update deducted one energy (normally -1 per simulated second), including work and rest; physical action costs were added on top. This caused excessive compounded drain. Now one centralized EnergyRules budget owns every deduction/recovery, and physical work/rest does not also pay passive energy.

| Activity | Previous | New default | Configuration |
| --- | --- | --- | --- |
| Idle / standing | 1 energy / simulated second | 0.02 energy / simulated second (50× slower) | ENERGY_IDLE_PER_SECOND |
| Walking | 1 energy / tile + passive | 0.1 energy / tile, inclusive | ENERGY_WALK_COST |
| Gathering | 2 energy / completion + passive during work | 1 energy / successful completion | ENERGY_GATHER_COST |
| Cooking | 0 explicit + passive during work | 0.5 energy / successful completion | ENERGY_COOK_COST |
| Hunt pursuit | 1 energy / moved tile + passive | 0.5 energy / moved tile, inclusive | ENERGY_HUNT_STEP_COST |
| Hunt catch | 8 energy / successful catch + passive | 4 energy / successful catch | ENERGY_HUNT_COST |
| Player chicken attack | 0 explicit per hit | 0.5 energy / accepted hit | ENERGY_ATTACK_COST |
| Rest | +8 per completed rest, minus ongoing passive | +8 per completed rest, no passive deduction | ENERGY_REST_GAIN |
| Conversations / meals | passive only | no additional cost while held/timed | — |

Default rest duration stays one simulated second; changing REST_SECONDS changes restoration per second, not gain per completion. Other durations and survival thresholds are unchanged. Idle/ordinary WAIT continues to consume a little energy. Default hunger stays +1 every three simulated seconds. Different behavior can change measured hunger over a trial, but the hunger rate/nutrition were not adjusted.

Energy costs support three decimal places. To keep the existing integer bar while preserving low rates, each agent owns energy_spent_micro in [0, 999999]: sub-unit expenditure carries until a full energy unit is used. Full recovery clears this debt; exhaustion never goes negative. Saves validate/persist it and energy rates; old version-1 saves without these fields initialize debt to zero and use new defaults. No database or additional needs copy was introduced.

## Actual extended checks

Old code was extracted from checkpoint b8c824d into an isolated temporary directory. Old/new rule-based runs used the same seeds **7 and 42**, initial scenarios and unchanged hunger settings, with no persisted history and networking blocked. Each trial ran **12,000 ticks / 3,000 simulated seconds / five 600-second days**. Four old plus four new trials ran, with no failed trials, food-conservation failures or API calls.

| Scenario (two seeds each) | Rest time old → new | Mean energy old → new | Gather completions old → new | Meals old → new | Incapacitations old → new |
| --- | --- | --- | --- | --- | --- |
| Normal village | 35.02% → 3.59% | 62.95 → 68.86 | 257 → 258 | 245 → 246 | 0 → 0 |
| Food shortage | 33.29% → 3.33% | 62.78 → 71.95 | 232 → 235 | 244 → 246 | 1 → 1 |

Rest percentage = REST-labelled NPC ticks / all 4 × 12,000 NPC ticks per trial, averaged over the two equal-length trials. Means use every NPC tick; completion counts/incapacitations are totals over the two seeds. These are pilot behavior checks, not proof that every map/seed is balanced. Routine night waiting remains; it is not an exhaustion loop.

Two additional new-balance **4,800-tick** scarce-berries trials (seeds 7/42) each completed **3 hunts, 3 cooks and 3 cooked meals**, plus 38 berry gathers and 38 berry meals. Food conservation held and API calls were zero. Scarcity still caused **24/17 temporary incapacitations** respectively; the higher energy allowance intentionally does not eliminate starvation. These controlled initial profiles use existing scenario rules, not forced hunt outcomes.

Genuine local evidence: artifacts/energy_interact/before.json, after.json and scarce_checks.json. Historical experiment outputs are preserved and must not be described as results from this new energy balance. New experiment exports/fingerprints include the energy configuration.

## What the animation really is

`interact_gather` contains **16 procedural visual states per character**: DOWN/LEFT/RIGHT/UP × REACH/CONTACT/COLLECT/RETURN. No new illustrated character frames were created. Existing flattened artwork lacks separate arm layers; the prototype therefore retains the exact neutral directional sprite and uses restrained glints and a small provisional berry/leaf motion toward/from the resource. It does **not** claim genuine arm articulation, new hand poses or a full-body bob as a reaching pose. No walking frames are cycled while stationary.

The optional module only reads accepted in-range GATHER jobs, waits for visual arrival and uses an existing cached idle pose. Feet/world position/depth sorting stay fixed. Smooth phase curves advance with simulation time, freeze on pause and fit complete cycles to the accepted action duration (normally four 0.875-second cycles over a 3.5-second gather, close to the requested one-second cycle). The configurable target is 1.0 second; phase/job identity is not restarted every tick. Very short jobs below 0.4 seconds use idle fallback. Cancellation, invalid/depleted targets, walking, conversations and other actions immediately use normal sprites.

Pickup accents during an accepted activity are provisional visual feedback, not awarded items. Existing executor completion alone updates real stock/inventory exactly once. Cooking, hunting, conversation and ordinary idle/walk art do not use this prototype. All animations/PNG loading remain cached; no source images are overwritten or regenerated.

## Preview, enable and disable

```bash
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox"
source .venv/bin/activate
python -m civsandbox --interact-preview
python -m civsandbox --mode participant --character mira --seed 7
python -m civsandbox --no-interact-animation
```

- **F7:** open/close the comparison preview in the existing window. The world is frozen with no catch-up backlog; the CLI preview does not load normal saved social history.
- **1–4:** Mira, Nyra, Kairo, Ren. Rows are down/left/right/up; columns compare idle, four phases and a live cycle. Preview bushes are explicitly presentation props, never resources.
- **Space:** pause/resume the preview only. It never causes gathering or inventory changes.
- **F6:** disable/enable instantly, including during gathering or preview. Disabled gathering uses existing idle animation and still completes normally.
- For future launches put ENABLE_INTERACT_ANIMATION=false in .env; set true to enable again. INTERACT_ANIMATION_SECONDS=1.0 configures the approximate cycle target (0.4–4 seconds supported). Command flag --no-interact-animation overrides the preference for one launch.

Separate generated QA contact sheets for all four characters and a live GIF are under artifacts/energy_interact/. They are optional ignored outputs, not original artwork or runtime dependencies.

## Safe future removal (only if requested)

Do not reset the whole project to b8c824d; that would also undo energy balancing and any later work. Disable with F6/flag first, then in a focused follow-up:

1. Remove the interact_animation import, InteractionView registry/sync/advance/reset hooks and optional frame/effect branch from rendering.py; draw_character should again use view.animator.frame directly.
2. Remove draw_interact_preview, its cached reference poses, F6/F7 handlers, preview-only input/timing guards, and the prototype-specific Renderer/run keyword arguments.
3. Remove --interact-preview / --no-interact-animation and their renderer arguments from __main__.py; remove the two presentation settings from config/.env.example and their help/documentation entries.
4. Remove only civsandbox/interact_animation.py and prototype-specific tests. Retain energy.py, energy configuration/save fields, action costs, energy regression/long-run tests and validated target-facing in pacing.py. Never remove original idle/walk PNGs, SpriteAnimator, CharacterView or physical gathering logic.
5. Run the full suite, a rule-based headless trial and gathering/cooking/Participant checks. Verify stock/item/timing conservation. Generated prototype preview artifacts may be archived separately; deletion is not needed to disable or remove runtime code.

## Verification and remaining visual limits

Baseline: **418 passed, 1 skipped**. Final main-project full suite: **446 passed, 1 skipped, zero failures in 56.78 seconds** (`python -m pytest -q -p no:cacheprovider`). All **28 new regression cases** also passed separately. The one skip is the historical live API test. Actual rule-based/mock CLI launches each passed 1,000 ticks with networking disabled, and the preview opened/closed through SDL dummy rendering with the world frozen at tick zero and no normal-history write. All **262** protected artwork/private/prototype/dependency file hashes remained unchanged. New tests cover rates, exact fractional costs, restoration, no duplicate charges/rewards, hunting/cooking, persistence, five-day survival, four phases/directions, pause/speed, stationary feet, arrival/facing, completion/cancellation, invalid targets, ON/OFF equivalent world state and live/CLI preview behavior. All tests prohibit network access.

SDL dummy renders and generated contact-sheet inspection are executed; native macOS/Retina smoothness still needs human review. This remains a modest resource-motion prototype: silhouette, limbs and facial expressions do not change, and up-facing accents can be partially hidden by the character. Stop this experiment with F6 if it feels visually unconvincing; no survival mechanic depends on it.

Manual check: preview each character/direction with F7/1–4 and pause; compare F6 on/off; gather in a normal game at .5×/1×/4×; pause or cancel mid-task; confirm feet/facing and exactly one resource transfer; check old walk/idle/conversation art and save/load. No automatic permanent removal was performed.

## Files changed

New: civsandbox/energy.py, civsandbox/interact_animation.py, tests/test_energy_interact.py, this guide. Updated: agents/actions/simulation/pacing/wildlife/config/savegame/experiments/__main__, rendering/participant_ui, four existing survival/Participant/chicken test modules, .env.example, README, GAMEPLAY_GUIDE and DEVELOPMENT_GUIDE. Original assets and private data are unchanged.
