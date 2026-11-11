# Gameplay guide

## Start or observe

Activate the existing .venv from the project root and run `python -m civsandbox --seed 7`. All four villagers act autonomously. Add `--scenario food_shortage` for unequal inventories and greater survival/social pressure. Use M to choose Observer Mode or take control of Mira, Ren, Nyra or Kairo. Their identity, needs, inventory and history remain the same objects; no fifth character is created.

Mira is the green generous gatherer; Ren the red practical merchant; Nyra the cautious purple observer; Kairo the curious blue adventurer. These are numeric tendencies, not scripts guaranteeing their choices. Every character can use the same survival actions.

## Controls and readable state

WASD/arrows move in Participant Mode. E opens nearby object actions/inspection; I opens inventory, eating and rest. Use mouse/numbered choices and scroll long lists. Backspace cancels unfinished work. Escape closes menus; in normal Participant view it opens the mode menu. Space pauses, −/+ changes speed, M changes mode, F1 explains controls. Observer arrows retain speed controls. F3 exposes optional diagnostics, P plans and S social sessions; developer shortcuts have priority in that view.

Hunger 0 means satisfied; 100 starving. Energy 100 means rested; zero exhausted. The HUD reads the actual model, showing bars, inventory, activity, goal and relationship summary. Gold outlines identify selection/nearby interaction opportunities. Berry dots show real available stock and depleted bushes regrow on simulation time. No API key or typing a natural-language command is needed.

## Survive and interact

- Approach a bush and press E to gather. Work takes time and transfers one actual berry only at completion, respecting capacity. Eat it through I; berries reduce hunger by 35.
- Chickens wander, peck, rest and flee. In Participant Mode, left-click the chicken itself within one Manhattan tile (same/cardinal neighbor). Each valid discrete click deals 25/100 HP; four hits grant one raw chicken. No auto-travel or held-button damage occurs. A free inventory slot and energy are required; busy/paused/incapacitated characters cannot attack, and another NPC’s active hunting claim is respected. E no longer offers chicken hunting. Autonomous NPCs retain conditional, timed pursuits; failure gives no meat.
- Raw chicken cannot be eaten. Stand beside the campfire, choose Cook in E and wait for conversion. One raw becomes one cooked item exactly once. Cooked chicken reduces hunger by 65 when eaten.
- I offers timed rest until recovery; movement ends that intent after the current rest unit, and Backspace cancels immediately. Needs still advance. Hunger now rises one-third as often by default (+1 every 3 simulated seconds); energy keeps its previous cadence. High hunger slows useful activity; exhaustion/starvation can cause temporary recovery. No permanent NPC death exists.
- E near another villager offers talk, food request, voluntary offer and relationship inspection. Requests can be answered with sharing or refusal; supplies and proximity remain real constraints. Directed trust means A's opinion of B can differ from B's opinion of A.

An incoming invitation asks for consent before it starts. Greet-back/accept-and-thank choices authorize the authored reply; actual food requests get a separate share/refuse choice after the question. No provider answers for the controlled character. Unattended prompts cancel after 30 unpaused real seconds, without inventing food or a refusal. Menus transparently pause the whole shared world and discard catch-up backlog. Manual pause also freezes the prompt countdown.

## Histories and saves

N shows timestamped important village news; C shows separate accepted conversations. The reading card may lag behind fast simulation; it is labeled history rather than floating over a walking NPC. News groups repeated work and omits minor WAIT/movement/rest spam. F3 retains detailed raw traces.

F5/Save writes data/world_save.json. F9/Load confirms replacement and restores paused; press Resume/Space to continue. Use `python -m civsandbox --load data/world_save.json`, or `--save-file saves/another.civsave.json` for another slot. Loaded jobs, claims, sessions and plans release safely; unfinished work gives no reward and owned ingredients remain. Loading does not overwrite unrelated legacy social files. Full-world saves are manual, not automatic at exit.

Keep personal files in ignored data/, saves/ or *.civsave.json. Checkpoints retain latest 200 news entries, 120 dialogue turns, 20 memories per NPC and 512 resource-ledger records. A single slot is replaced intentionally; choose separate paths for separate worlds. See the Stage 6 report for atomic validation/error behavior.

## Display and limitations

The logical world is 1100×750. `--window-scale 0.85` fits smaller displays; 1.25 makes a larger window. Mouse targets are remapped with the presentation. Native macOS/Retina sizing and smoothness require manual checking. Existing corridor recovery can briefly overlap villagers, and prolonged acceleration can outrun the bounded reading queue. Hunger management and valid refusals are real outcomes; neither cooperation nor every hunt is guaranteed. Quit with the window close button; Observer Mode also supports Escape outside menus.
