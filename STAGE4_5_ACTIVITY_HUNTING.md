# Stage 4.5 — Activity anchors and conditional hunting

## Scope and files

This focused change extends the working Stage 4 game. No new UI, external AI, wildlife FSM, animation system, inventory or cooking pipeline replaces the existing implementation. No character artwork or private save file was edited.

Changed source: civsandbox/rendering.py, feedback.py, decisions.py. Regression coverage: tests/test_activity_hunting_balance.py plus updated expectations in test_feedback.py and test_wildlife.py. Documentation: README.md, DEVELOPMENT_GUIDE.md and this report. Generated measurements/captures remain ignored under artifacts/stage4_5/.

## Bubble fix

The verified defect was the old layout fallback: if space above/below an NPC was occupied, it searched a grid over the whole world, placed a card far away, and drew a connector back to the character. This appeared to leave a card fixed elsewhere as NPCs moved.

The new layout computes each card from the owning NPC's current sprite rectangle, rebuilt every frame from CharacterView's interpolated position. It uses a short above-head offset and viewport clamping only, with no global search and no connector lines. Offscreen owners and expired notices are hidden. Activity labels are compact (Gathering, Eating, Resting, Cooking, Hunting); completed outcomes are brief. Superseded activity notices clear when a different action executes. Activity labels hide during visual movement or crowding. Accepted dialogue is laid out first and secondary cards are hidden rather than relocated. At the viewport's top edge, keeping speech on-screen can bring it closer to the character/name.

Speech still requires an actual nearby engaged shared session, with both actors stopped/facing through the existing scheduler. Live proximity is checked again before presentation. Existing reading time, pause handling, C history and bounded presentation queue are unchanged. UI placement never writes simulation coordinates.

## Hunting adjustment

The previous policy completely rejected hunting whenever a nearby stocked berry bush existed. That hard veto is removed. Existing high-level utility selection now compares a chicken meal with gathering, including:

- Hunger (eligibility begins at the configured hungry threshold, normally 55).
- No carried edible meals or raw chicken reserve; carried cooked meals are eaten first.
- At least max(40, minimum hunt energy + 12) energy, an inventory slot and valid local target.
- Existing six-tile visibility and risk-dependent reachable pursuit-distance limit.
- Reachable cooking station, travel to it, its current wait, and expected cooked nutrition.
- Berry approach distance as a penalty, instead of an absolute prohibition.
- Numeric curiosity and risk aversion, with no identity-specific hunting scripts.

HUNT_FOOD utility uses base 36, hunger × .8, cooked nutrition × .2, curiosity × 12, risk × −20, pursuit steps × −2, cooking travel × −.7, work cost −8, available berry penalty −max(0, 10 − nearest berry approach steps), and current station waiting cost −.2 per tick. The existing local eligibility score threshold is .25. Debug mode shows the actual components.

For a new eligible goal only, a seeded uniform adjustment from −12 to +26 utility units introduces bounded preference variation. Candidate inspection and retained plans do not sample randomness. Goal commitment, emergency interruptions, bounded pursuit/claims and current cook queues remain intact. Eligibility checks are spaced by five seconds; completed/failed hunts retain the existing 40-second cooldown. Spawn events never call the policy or grant hunting preference. World effects still require the unchanged common validator/executor and timed cooking conversion.

## Actual tests

Before changes: **272 passed, 1 skipped**. Updated full staging and main-project suites: **284 passed, 1 skipped, zero failures** (main: 17.56 seconds). Added focused tests cover fractional render anchors across frames, no connector drawing, offscreen/moving suppression, expiration/superseded activity, local crowding, accepted-session speech/proximity, hunting with berries, hunger utility, energy/meal/cooking gates, seeded variation without goal oscillation and food conservation. Existing tests retain failed hunt, no duplicate reward, claims, respawning, well-fed no-hunt-on-spawn, cooking cancellation, social compatibility and deterministic offline checks. The historical live API test stays skipped.

SDL dummy activity and accepted-dialogue screenshots were rendered and inspected. They use controlled UI fixtures and are not natural gameplay evidence. Native interactive macOS visual QA was not performed.

## Genuine seeded observations

Ten fresh isolated rule-based runs, seeds 7, 8, 9, 21, 42 in both default and food_shortage, each ran **4,800 ticks / 1,200 simulation seconds**. No persisted history loaded. Socket/DNS calls were prohibited. These are actual outcomes; no chicken placements or decision outcomes were scripted in these runs.

| Scenario | Seed | Eligible choices | Hunt decisions / attempts | Successes | Failures | Gathers | Cooking |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| Default | 7 | 0 | 0 / 0 | 0 | 0 | 144 | 0 |
| Default | 8 | 0 | 0 / 0 | 0 | 0 | 143 | 0 |
| Default | 9 | 0 | 0 / 0 | 0 | 0 | 145 | 0 |
| Default | 21 | 0 | 0 / 0 | 0 | 0 | 145 | 0 |
| Default | 42 | 0 | 0 / 0 | 0 | 0 | 145 | 0 |
| Food shortage | 7 | 6 | 4 / 4 | 4 | 0 | 111 | 3 |
| Food shortage | 8 | 2 | 2 / 2 | 2 | 0 | 117 | 2 |
| Food shortage | 9 | 1 | 1 / 1 | 1 | 0 | 115 | 1 |
| Food shortage | 21 | 0 | 0 / 0 | 0 | 0 | 118 | 0 |
| Food shortage | 42 | 4 | 3 / 3 | 3 | 0 | 117 | 3 |

Totals: **10 hunting decisions, 10 attempts, 10 successes, 0 failed/pending hunts, 1,300 gathers and 9 cooking completions**. One acquired raw item was still unconverted at the run cutoff; cooking count is not invented to match hunts. Four hunt selections had stocked berries (nearest approach 4, 1, 15 and 0 steps). The earliest hunt decision was 97 ticks / 24.25 seconds after its target spawned. No immediate hunt-on-spawn was observed. Mira, Ren and Kairo hunted; Nyra did not in these seeds. No endless pursuits or rapid hunting/gathering switches were observed; tests separately verify retained goals and bounded failure behavior.

Living population was sampled initially and every 400 ticks / 100 simulation seconds. All default samples had two chickens. Shortage samples ranged from one to two; no sampled extinction occurred. These are point samples, not individual survival probabilities. Full sample trajectories are in hunting_runs.json. Repopulation is unchanged.

Eligible choices count goal-selection occasions where an allowed HUNT_FOOD candidate was scored; they are not ticks. Ten of the thirteen natural eligible choices selected hunting. This small scarcity-biased sample is **not** a measured 15–25% general preference rate. Most default NPCs ate/gathered before becoming hungry enough to qualify, so there were no default eligible opportunities.

A separate controlled policy probe (adjacent stationary target, existing Mira traits, stocked berries, reachable cooking) selected goals with independent seeds 0–99. At hunger 60, 19/100 selected hunting; at hunger 65, 21/100; at hunger 85, 26/100. Remaining choices gathered. These are actual decision-only fixture measurements, not natural encounters, completed hunts or evidence that all characters have the same rate. No quota is enforced.

Every natural run verified berry, raw and cooked conservation:

- Final berries = initial berries + committed gathers − berry meals.
- Final raw = initial raw + successful hunts − completed cooking.
- Final cooked = initial cooked + completed cooking − cooked meals.

Sharing/offering conserves totals. All runs reported zero API calls. Outputs: artifacts/stage4_5/hunting_runs.json and controlled_policy_probe.json. The saved offline verification script reproduces ten runs; timing and historical Stage 4 datasets are not presented as this revision's data.

## Launch and reproduce

```bash
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox"
source .venv/bin/activate
python -m civsandbox --provider rule-based --scenario food_shortage --seed 7
python -m pytest -q
PYTHONPATH=. python -u artifacts/stage4_5/verify_hunting.py
```

The verification script overwrites only its generated hunting_runs.json report; normal .env, histories and assets are untouched. Interactive play uses configured saved social history and may differ from isolated measurements.

## Manual visual checklist and limits

1. Watch gathering/eating/resting/cooking: a compact label sits above the owning head, with no diagonal lines.
2. Follow a departing NPC: activity hides during travel; it never remains elsewhere on the map.
3. Observe a map-edge NPC and crowded pair: cards stay local/on-screen, or secondary activity disappears.
4. Watch an accepted conversation: both stop/facing, speech belongs to the correct speaker, and C history remains readable.
5. Pause/resume and try .5×/1×/4×: text/state preserve correctly and expired/canceled activities clear.
6. Inspect F3/P food goals; compare a stocked/cooked-meal carrier, tired NPC and hungry empty-handed NPC near chickens.
7. Confirm raw meat appears only after successful hunting, cooks over time and disappears exactly once on conversion.

Default abundance may produce no hunts, as observed. Tiny natural eligible samples cannot establish population-wide rates; controlled probes use one personality/layout. Zero failed hunts in this pilot does not guarantee successful future pursuits. Existing bounded dialogue queue may lag at high acceleration, corridor recovery can briefly overlap NPCs, and native visual smoothness still requires the checklist. No Stage 5 work was added. Pre-change recovery commit: 3277b36.

Final main-project verification also reproduced the saved seed-7 shortage counts, population samples and final inventories with network/SDK imports blocked. Rule-based and mock CLI launches each completed 1,000 headless ticks with four agents and fresh temporary histories. All 89 recorded private configuration/history/artwork hashes remained unchanged. `git diff --check` passed.
