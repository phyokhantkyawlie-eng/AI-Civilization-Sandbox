# Stage 5 — Participant Mode

## Implemented architecture

Observer Mode remains the default: four autonomous villagers. Participant Mode assigns human control to one existing stable ID (Mira, Ren, Nyra or Kairo), while the other three keep their selected offline decision provider. No fifth agent, copied inventory, second engine, new world or external API exists.

`Simulation.set_participant(id)` preserves the world, four Agent objects, position, needs, inventory, trust and memories. It safely cancels unfinished activities/leases/claims/sessions, interrupts old rule/mock plans, clears input and changes control ownership. `set_participant()` returns to autonomous observation without resetting the world. Completed effects are retained; unfinished work creates no rewards. Selection is transient, not a new physical save format.

New player.py supplies a bounded command slot, held cardinal direction, explicitly chosen rest continuation and pending human consent. Its decide method returns the same Action model as local providers. Simulation skips autonomous decide and planner-result callbacks for the controlled agent. Actual needs, movement cadence, occupancy, ActionProgress validation/timing, hunger slowdown, hunting/pursuit, cooking conversion and social executor are shared. The player receives no special food, energy, movement or inventory exemptions. Incapacitation cancels input and uses the same forced REST/recovery path. Choosing to rest continues timed units until recovered or explicitly stopped; movement ends that intent after the current rest unit, and Backspace cancels immediately.

New participant_ui.py is a Pygame presentation helper: character cards using cached existing art, contextual actions/inspection, inventory and explicit social choices. It reads authoritative objects and submits actions, never inventory/position changes. It clears held directions on menus/focus loss, caches previews/overlay and rejects stale menu-layout clicks. Existing rendering/interpolation, local bubbles, social history and debug inspection remain in place. ui_state.py gives human idle/walk labels; no second needs model was added.

## Controls and interaction flow

| Control | Behavior |
| --- | --- |
| M | Mode/character menu; choose any original NPC or Observer Mode |
| WASD / arrows | Participant grid movement in normal view |
| E | Nearby contextual actions and inspection |
| I | Inventory, edible-item actions and rest |
| Backspace | Cancel unfinished player activity and clear commands |
| Escape | Close a menu; decline a pending invitation/request; normal Participant view opens mode menu |
| Space | Explicit pause/resume outside menus |
| − / + (equals key) | Simulation speed; arrows retain speed controls in Observer Mode |
| Click / 1–6 | Choose displayed menu actions |
| Mouse wheel | Scroll longer context lists |
| C | Existing conversation history |
| F3, then P / S | Existing planner/social debug inspection; developer shortcuts retain priority there |

The normal HUD stays on the controlled character even if another NPC is clicked. Use contextual relationship inspection or developer inspection for others. The nearby hint identifies the first local opportunity; E lists all reachable nearby options, not only that first hint. Bush inspection shows actual stock/capacity/regrowth; chicken inspection shows identity/position/activity/alive status; campfire inspection shows availability; nearby NPC inspection uses guarded trust/relevant memories. Unavailable actions are dimmed or rejected with feedback. No typed natural-language commands are required. Quit with the window close button; Observer Mode retains Escape-to-exit outside menus.

Human requests, offers, greetings, gathering, hunting, cooking, eating and rest use existing typed actions. Raw chicken remains inedible and must convert through finite timed cooking. Invalid or stale choices cannot transfer food or move onto blocked terrain. Hunting claims and bounded pursuit rules are unchanged.

## AI-to-player consent and timeout policy

An AI may approach through the existing local policy, but a distant proposal does not freeze the human. Before a new nearby TALK, OFFER_FOOD or REQUEST_FOOD targeting the human starts, an invitation identifies the initiator and asks for consent. Accepting queues the original action for latest-state validation on the next tick; it never executes in a click handler. Other invitations defer while that accepted action starts. Busy/unavailable partners still fail normal eligibility rules.

- Talk: **Greet back (accept)** or decline. Greet-back authorizes the existing short authored reply; no autonomous provider chooses it for the human.
- Food offer: **Accept berry and thank** or decline. Inventory changes and the authored thanks require the real completed transfer.
- Request: first choose **Listen to the request** or decline. After the actual timed question completes and an addressed FoodRequest exists, choose **Share one berry** or **Refuse request** using its real ID. The response popup includes the actual delivered offline question. Sharing without food/capacity is rejected and leaves the choice open; it never selects refusal automatically.

The same common social rules produce actual transfers, trust and one memory per event. Player-initiated interactions and NPC responses to them use the existing provider/executor normally. Public explanations and unaccepted invitations produce no speech. Authored greeting/thanks lines are consequences of explicit choices, not generated external dialogue.

Ordinary menus and pending prompts transparently suspend the **whole shared simulation**, including hunger/resources/wildlife, without accumulating a catch-up backlog. Existing reading presentation remains nonblocking. A pending prompt cancels after **30 unpaused real seconds**, independent of simulation speed. Explicit pause freezes that countdown. Timeout/invitation decline/mode change releases reservations and records a real cancellation with zero trust change; timeout does not fabricate a refusal or transfer food. Actual answered food refusals retain ordinary shared trust consequences. Shutdown also clears unfinished input and cancels outstanding invitations safely.

## Actual verification

Baseline: **284 passed, 1 skipped**. Final staging and main-project full suites: **312 passed, 1 skipped, zero failures** (main: 17.82 seconds). The 28 new Participant Mode cases cover all four identities with populated trust/memory, both handoffs, cached rule/mock plans, no duplicated agents, three continuing AI sources, no autonomous choices for the human, movement/terrain/bounds/hunger slowdown, real frame interpolation/direction, timed gather/inventory capacity/eating/rest, hunt/cook conservation and duplicate rejection, canceled cooking, explicit offers and requests, trust/memory once, stale accepted actions, unattended cancellation, recovery, local context, character artwork/menu controls, stale clicks and pause/speed behavior. Historical live API testing remains skipped.

Four genuine isolated Observer Mode trials (seeds 7–8, 1,000 ticks per MEMORY_OFF/ON condition) completed with matching paired initial hashes, zero API calls and valid CSV/JSON exports. Outputs are artifacts/stage5/observer_trials/. These are autonomous Observer trials, not fabricated human gameplay outcomes.

Six controlled SDL dummy layouts were generated and inspected: character selection, Participant HUD, nearby actions, inventory, incoming offer and an actual food-request response. They verify layout/assets in the renderer, not native macOS interactive play or spontaneous social frequencies. Automated controlled scenarios test actual player commands through the existing executor; fixed chicken positions in timing tests are test fixtures, not claimed natural outcomes.

## Exact commands

```bash
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox"
source .venv/bin/activate
python -m civsandbox --mode participant --character mira --provider rule-based --seed 7
# Other character values: nyra, kairo, ren.
python -m civsandbox --mode observer --provider rule-based --scenario food_shortage --seed 7
python -m pytest -q
python -m civsandbox --headless --mode observer --provider rule-based --ticks 1000 --seed 42
python -m civsandbox.experiments --provider rule-based --runs 2 --ticks 1000 --seed 7 --scenario food_shortage
```

The graphical game can also enter Participant Mode using M from an ordinary launch. Headless CLI Participant Mode is rejected clearly because it has no human input source. Controller unit tests run headlessly through the Python API. Existing experiments always construct Observer Mode, fresh providers and isolated histories; menu pauses and human choices do not contaminate them. Use a fresh temporary MEMORY_PATH for isolated normal CLI checks; interactive play intentionally uses configured social history.

## Manual native visual checklist and limits

Native macOS interactive visual QA remains manual:

1. Launch Mira Participant Mode. Verify green outfit, controlled selection highlight, authoritative need bars/inventory and three moving autonomous NPCs.
2. Hold/release WASD/arrows at .5×/1×. Check collisions, foot anchoring, walk directions and return to idle. Open M or change window focus while holding a key; release input must not remain stuck.
3. E near a bush: inspect stock/regrowth, gather over time, then I to eat. Verify actual inventory changes only on completion and berries reduce hunger.
4. E near a chicken: hunt under normal limits; raw meat must not be edible. Approach the campfire, cook over time, eat the cooked item, and test Backspace cancellation without free food.
5. Use I to rest; watch energy recover. Try an unavailable/full-inventory action and read its rejection.
6. Near another NPC, test talk/request/offer, accepted and declined invitations, real food-request responses, 30-second unattended cancellation, history, trust and memories.
7. Pause mid-activity and at a response prompt. Change speed outside menus; prompt timeout remains real-time and menus clearly freeze everyone.
8. M: switch character, then Observer Mode. Verify the same four identities/positions/inventories/history continue, unfinished tasks release and all four become autonomous again.

Human participants can make poor survival choices; the game deliberately does not auto-eat or make unchosen social responses. Menus pause everyone, so human sessions cannot be compared directly with continuous Observer experiments. Optional social encounters depend on real proximity, needs, personality and availability; no guaranteed demo outcome is scripted. Existing corridor yielding may temporarily overlap NPCs; high-speed reading queues remain bounded. Full physical-world saving, pixel controls, new art, external AI and later-stage features are not added. Recovery before this stage: Git commit 422f618.

Final main-project checks: guarded rule-based and mock Observer CLI launches each advanced 1,000 ticks with four agents and zero API calls. Headless Participant CLI rejection was verified. Actual graphical entry-point startup/clean shutdown succeeded for all four character arguments using SDL dummy, networking/SDK imports blocked and fresh temporary social saves; this is not native macOS visual approval. A fresh 4,800-tick Observer seed-7 shortage run reproduced pre-Stage-5 hunting/cooking/gathering counts and final inventories. All 89 recorded private configuration/history/artwork hashes were unchanged, and git diff --check passed.
