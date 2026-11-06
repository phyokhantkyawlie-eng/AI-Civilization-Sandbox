# CSC472 demonstration — about 7 minutes 40 seconds

Rehearse with the existing .venv from the project root. This is offline classical AI, not ML/LLM reasoning. Use a new temporary history directory to protect personal saves:

```bash
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox"
source .venv/bin/activate
CIV_DEMO_DIR="$(mktemp -d)"
MEMORY_PATH="$CIV_DEMO_DIR/social.json" python -m civsandbox --provider rule-based --seed 7 --save-file "$CIV_DEMO_DIR/world.civsave.json"
```

## 0:00–0:35 — Project and characters

Introduce four autonomous villagers: Mira green, Nyra purple, Kairo blue and Ren red. Explain local utility scoring, retained task plans, BFS and finite-state behavior. Numeric personalities influence choices, not guaranteed character scripts.

## 0:35–1:20 — Autonomous survival

Show names, clock, needs and inventory. Space pauses; use 2×/4× briefly to show completed gathering, eating and resting. Click a bush for real stock/regrowth. Food changes only at validated completion. Default abundance may produce no hunting; that is expected.

## 1:20–2:00 — Shortage and social outcomes

Close the first window; launch the same engine with another fresh history:

```bash
MEMORY_PATH="$CIV_DEMO_DIR/shortage.json" python -m civsandbox --provider rule-based --scenario food_shortage --seed 7 --save-file "$CIV_DEMO_DIR/shortage.civsave.json"
```

Show unequal supplies/needs and an actual request/response, then N/C history. Do not promise sharing: refusal is valid. Speech must come from accepted nearby sessions. Show directed trust and relevant bounded memory in F3 or nearby inspection.

## 2:00–2:45 — Chickens and conditional hunting

Explain wandering, pecking, fleeing, energy, pursuit cost, claims and cooking access. Stocked villagers prefer edible inventory; failure grants no meat. Use observed events rather than promising a hunt in this live minute.

For a short presentation, close the prior window and load the genuine prepared checkpoint:

```bash
python -m civsandbox --load artifacts/stage7/demo_cooking.civsave.json --save-file "$CIV_DEMO_DIR/cooking.civsave.json"
```

Its provenance is explicit: seed 7 autonomously reached accepted cooking at tick 677 after a successful hunt and genuine starvation recovery; a normal Participant handoff canceled unfinished cooking while retaining Mira's one real raw chicken. It is a prepared saved moment, not invented food or another natural trial. Generated evidence is ignored by Git; if this file is absent, rehearse a normal Participant hunt/cook or use the regeneration recipe below.

## 2:45–3:30 — Cooking

The save opens paused, controlling Mira beside the campfire. Resume, inspect raw inventory with I, then E → Cook. Choose cooking promptly after resuming; menus pause time. Wait for conversion, then eat. The verified script completed cooking at tick 698 and eating at 709, reducing hunger 100→35. A recovery interruption retains ingredients; do not hide it or invent a meal. Idle art plus an honest activity indicator is used because no full cooking sprite sheet exists.

## 3:30–4:20 — Social memory

Talk/request/offer through E when valid, or inspect an actual recorded interaction. Show consent/share/refuse choices if offered. No provider chooses the player's response. Explain that MEMORY_OFF hides past social recall/trust while retaining current needs, observations and requests. Refusal/cancellation must not be presented as a forced cooperative outcome.

## 4:20–5:10 — Explain an AI decision

F3 → P shows actual utilities, selected goal, public reason, queued steps and replanning. Explain needs → goal/retained plan → BFS travel → timed validation/execution → updates. Emergency needs can interrupt commitments. Weights are manual; seeded variation is not training or LLM reasoning.

## 5:10–5:50 — Participant Mode and persistence

M chooses another existing character without rebuilding state. Demonstrate WASD/E/I and the other three autonomous villagers. F5 saves; F9 confirms and restores paused, releasing unfinished work without free rewards. Choose a demo --save-file path to avoid replacing a personal slot.

## 5:50–7:05 — Genuine results

```bash
python -m civsandbox.results artifacts/stage7/release_evaluation --show
```

Show memory comparison, cooperation, gathering/hunting rates and food availability. State five seed pairs and 12,000 ticks per memory condition. There were 55 executions, but duplicated shortage-ON controls are not extra independent seeds. Mean request-response cooperation was 0.319 OFF / 0.321 ON; the tiny paired change has uncertainty including zero, and hunger/energy moved slightly unfavorably. Four pairs matched on these metrics. No benefit was established. Mortality survival is unavailable; operational availability is a separate proxy. SD bars show variation, not significance.

Use AI_EVALUATION.md for denominators. If evidence is absent, generate it first; never substitute placeholders.

## 7:05–7:40 — Verification and limits

Use FINAL_VERIFICATION.md for actual tests. Disclose five seeds, fixed personalities/order, known-map berry routing, contested gathers, coarse night rest, temporary corridor overlap, bounded histories and absent death/ML. Native visual smoothness needs a human check; SDL dummy tests do not establish it. Resource reservations/fairness and broader trials are possible future work, not implemented features.

## Optional genuine checkpoint regeneration

This waits for a real accepted cook, then performs the ordinary control handoff; it never adds items:

```bash
python - <<'PY'
from pathlib import Path
from civsandbox.simulation import Simulation
from civsandbox.savegame import save_game
sim = Simulation(7, scenario='food_shortage')
last = 0
for _ in range(2000):
    sim.step()
    fresh = [e for e in sim.events if e['event_id'] > last]
    last = max(e['event_id'] for e in fresh)
    cook = next((e for e in fresh if e.get('activity_action') == 'COOK' and e.get('accepted_start') and sim.social.agents[e['actor_id']].recovery_grace_until > sim.tick + sim.progress.timing.cook_ticks + 2), None)
    if cook:
        sim.set_participant(cook['actor_id'])
        save_game(sim, Path('artifacts/stage7/demo_cooking.civsave.json'), cook['actor_id'])
        print('Prepared actual cooking handoff at tick', sim.tick)
        break
else:
    raise RuntimeError('No cooking opportunity observed; do not fabricate one')
sim.close()
PY
```
