# Procedural chickens, click attacks and hunger balance

Updated 11 November 2026. Extends the existing game; no external service, artwork or dependency was added. Existing directional idle/walk artwork and autonomous pursuit rules are retained.

## Controls and rules

Launch Participant Mode, approach a chicken and left-click its visible body. Health starts at 100; each discrete valid button-down removes 25. Same-tile/cardinal adjacency uses Manhattan distance <= 1 from the real player tile, independent of interpolated display position. Diagonal/distant clicks show “Too far away” and never auto-move. Mouse motion/holding/button-up do not attack. Window scaling is inverted once; the existing world origin is accounted for by drawn hit geometry (there is no scrolling camera).

Four hits defeat the chicken and transfer one raw item through the existing inventory. There must be a free slot and positive energy; current activities, paused worlds, incapacitation and another NPC's hunting claim block attacks safely. Death schedules the existing delayed replacement, once. NPC hunting remains the timed pursuit/catch action and uses the same shared defeat/reward implementation. E no longer offers player hunting; berries, campfire, inventory and social E actions remain available.

Clicks on controls, inspector, menus, speech cards and Participant HUD are consumed before world attacks. Silhouette hit regions exclude shadow, HP bar and transparent bounding corners. Frontmost chickens take priority, and opaque foreground NPC pixels block attacks behind them. Dead animals are never clickable. The HP bar stays visible while a living chicken is damaged.

## Animation

`chicken_animation.py` is presentation only. It reuses the existing CharacterView step queue instead of changing wildlife positions. It uses independent body/wing breathing, two alternating planted feet, gait bob, separate neck/head peck dips with ground crumbs, staggered blinking, layered tail feathers, facing and fleeing accents. Analytic phases derive from stable entity IDs without consuming simulation RNG. Damage causes a brief red flash/flinch; defeat closes the eyes, compresses the body and sinks it before removal. No whole-chicken rotation, new character frames or invented movement occurs.

A renderer observes only validated HP/alive transitions. Pause freezes animation/interpolation/death progress; accelerated simulation remains supported. Views are retained only for the existing bounded wildlife records and reset on load. Drawing uses primitives without per-frame image loading or new sprite surfaces. The optional QA GIF is generated from the actual same view code at 2× display scale: `artifacts/chicken_polish/procedural_chickens.gif`.

## Hunger and saves

Hunger remains 0 satisfied / 100 starving. New default `HUNGER_INTERVAL_MULTIPLIER=3` applies +1 hunger every third needs update (normally every 3 simulation seconds instead of 1). Energy still changes at its old cadence. Food nutrition, thresholds and recovery remain unchanged. All four agents and the human-controlled character use the same timer. Rendering FPS never drives needs. Set the multiplier to 1 explicitly to restore the old rate; the instant-action test fixture retains that old multiplier deliberately.

Full-world JSON checkpoints now include chicken HP/max HP and hunger timing. Partial health survives a round trip; loading never grants drops. Existing version-1 checkpoints without health load living chickens at full HP and dead chickens at zero; malformed/contradictory health is rejected. Existing private .env/saves and artwork are not rewritten. Historical experiment outputs remain intact and describe their original faster hunger balance; rerun experiments for comparisons with this revision.

## Executed verification

- Main-project pre-change baseline: **391 passed, 1 skipped**. The read-only sandbox caused two pytest cache-write warnings; no product/test failures occurred.
- New regressions cover four hits, no duplicate drops, diagonal/distant attacks, no auto-travel, paused/busy/full-inventory/claimed/missing targets, scaled mouse routing, held-button safety, UI/speech interception, foreground NPC occlusion, Observer safety, save/legacy health validation, interpolation, pause, death expiry and hunger timing/configuration.
- Four fresh offline runs: rule-based/default seed 7, rule-based/shortage seeds 7 and 42, mock/default seed 42; **4,800 ticks each**. Each retained four agents, valid live-chicken terrain/health and bounded inventories; API calls were zero with socket access blocked. Actual counts are in `artifacts/chicken_polish/offline_checks.json`: respectively 55/43/44/57 completed gathers and 50 meals each. No hunts occurred in these four resource-sufficient runs; autonomous hunting completion remains separately exercised by existing regression tests.
- Final main-project full suite: **418 passed, 1 skipped, zero failures in 35.09 s** (`python -m pytest -q -p no:cacheprovider`). All **27** new regression cases passed separately. The one skip is the historical live API test; no network/API smoke test was run. Both rule-based and mock main CLI launches also passed 1,000 ticks each with networking disabled. All **167** checked artwork/private file hashes remained unchanged.

## Manual visual checklist

SDL dummy render/input tests and inspection of the procedural contact sheet are executed; native macOS play/Retina smoothness is not claimed.

1. Launch below; inspect breathing/blinks/pecks, then walk near chickens and watch their independent feet, directional movement and fleeing. Check 0.5×/1×/4× and pause mid-step.
2. Left-click one nearby chicken four times: watch 75/50/25/0 HP, flinch/flash, brief defeat, exactly one raw item and eventual delayed replacement. Moving chickens require keeping actual tile range.
3. Click a diagonal/distant chicken, grass, its HP bar, UI and speech; check no damage or automatic movement. Holding the mouse alone must cause no extra hits.
4. E still gathers/cooks/talks; NPCs remain autonomous. F5/F9 retains damaged chicken health and does not duplicate meat. Loaded worlds are paused until resumed.
5. Observe hunger at 1×: +1 every three seconds under default settings; meals still reduce hunger by 35/65 and energy retains its previous rate.

```bash
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox"
source .venv/bin/activate
python -m civsandbox --mode participant --character mira --provider rule-based --seed 7
python -m pytest -q
```


## Files changed

- New `civsandbox/chicken_animation.py`: reusable articulated views and silhouette hit regions.
- `wildlife.py`, `actions.py`, `simulation.py`: HP, validated discrete attacks, shared atomic defeat/drop/respawn and events.
- `rendering.py`, `participant_ui.py`, `player.py`, `ui_state.py`: interpolated chicken drawing, scaled click routing/UI protection, controls and readable activity.
- `agents.py`, `pacing.py`, `config.py`, `.env.example`: separate configurable hunger cadence with unchanged energy.
- `savegame.py`: persist/validate partial HP and support legacy checkpoints.
- New `tests/test_chicken_click_animation.py` and updated `tests/test_participant.py`: combat, animation, input, persistence and balancing regressions.
- `README.md`, `GAMEPLAY_GUIDE.md`, `DEVELOPMENT_GUIDE.md`, this report: controls, engineering conventions and verification. Existing original artwork is unchanged.
