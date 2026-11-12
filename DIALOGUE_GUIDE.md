# Portrait dialogue — implementation and verification

This feature extends the existing offline Pygame game. Pre-change recovery checkpoint: **a50f3aa** (including the verified energy balance, chicken interactions and optional gather prototype). No external AI service, new dependency, replacement world sprite, trading or quest system was added.

## Launch and test all four characters

```bash
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox"
source .venv/bin/activate
python -m civsandbox --mode participant --character mira --scenario food_shortage --provider rule-based --seed 7
```

Approach a villager and **left-click their world sprite**, or choose their Talk / request / offer option through E. Range uses the existing Manhattan distance <= 1; clicks never auto-move anyone. Busy, recovering, occupied or distant targets produce a clear message. Chicken clicks retain their existing attack behavior.

For immediate, real-session demonstrations in the same application:

```bash
python -m civsandbox --dialogue-demo mira --provider rule-based --seed 7
python -m civsandbox --dialogue-demo nyra --provider rule-based --seed 7
python -m civsandbox --dialogue-demo kairo --provider rule-based --seed 7
python -m civsandbox --dialogue-demo ren --provider rule-based --seed 7
```

These initialize the existing food_shortage scenario, with an already-adjacent original character under human control (Ren, Kairo, Nyra, Mira respectively). They neither teleport an existing game nor guarantee a gift/refusal. Initial inventories/needs remain those of food_shortage. The demo uses no saved social history; its default manual save slot is data/dialogue_demo.civsave.json, separate from normal world_save.json. No file is written merely by opening/closing it. --load, --headless and another preview cannot be combined with --dialogue-demo.

A full inventory may disable Ask for Berries; having no berries disables Offer. This is real validation, not a broken button. End the conversation and eat/manage supplies as usual when needed. Closing the portrait interface returns to the same living simulation.

## Reading and controls

- The active speaker's supplied adult portrait and nameplate accompany one accepted turn at a time. The small header identifies both participants and labels the authored offline source.
- Text reveals at 48 characters per real second. First click / Enter / Space reveals the current page; the next continues. Long text wraps and pages without changing layout. Turns never auto-skip.
- Mouse hover, arrows/W/S, Enter and number keys select choices. Scroll or keyboard navigation reveals additional choices on small viewports. Disabled choices explain why they are unavailable.
- **Leave**, Escape or Backspace closes the visit. Leaving during an unfinished exchange cancels it without a transfer. Completed exchanges remain completed; they are never undone or repeated.
- World movement, attack clicks, menus and debug shortcuts cannot receive input through the modal. World speed is preserved; no catch-up backlog is applied on exit.

Choices include Small Talk, Ask for Berries, Offer One Berry, How Are You Doing and Goodbye. A hungry neighbor adds Do You Need Food. Thank You for Helping appears only when an actual relevant help memory is accessible. Cooked-meal gifts, multi-item gifts and apologies are not invented: existing social transfers support one berry, and there is no underlying apology/trading rule yet.

## Portrait asset system

The four supplied PNGs were copied byte-for-byte into assets/portraits. assets/portraits/manifest.json records their identities, dimensions, mode and SHA-256 integrity hashes.

| Stable ID | Character / file | Dimensions | Mode |
| --- | --- | --- | --- |
| npc-1 | Mira / mira.png | 1164 × 1351 | RGBA |
| npc-2 | Ren / ren.png | 1174 × 1339 | RGBA |
| npc-3 | Nyra / nyra.png | 1116 × 1409 | RGBA |
| npc-4 | Kairo / kairo.png | 1164 × 1351 | RGBA |

All contain transparent and opaque pixels. PortraitManager lazily loads originals once, fits the entire supplied image within its available box without stretching/cropping, and bounds scaled variants to a 48-entry LRU cache. Future expression filenames use mira_happy.png etc.; missing expressions reuse the neutral/base image. No expression variants or face filters were fabricated. Missing/corrupt base files instead display the original sprite and name. Original world walk/idle artwork is untouched.

The view derives geometry from its canvas dimensions; existing --window-scale 0.85 / 1.25 input mapping also applies. Tests cover 640×480 through 1440×900 surfaces. Portrait hats/hands/accessories remain inside the fitted image above the text panel; any intrinsic crop in the supplied original is preserved. Parchment panels, bronze/gold corners, shadows, focus highlights and a restrained portrait slide are drawn locally; no external UI assets/fonts are required. Cached system fonts fall back through Pygame when necessary.

## Actions, decisions and actual outcomes

The new DialogueController owns presentation/input state, not inventories, needs, trust or memory. Every selected mechanical action uses the existing Action validator, ActionProgress scheduler and executor:

| Choice | Existing action / consequence |
| --- | --- |
| Small Talk / How / Need Food / Thank | TALK with an authored context topic |
| Ask for Berries | REQUEST_FOOD, then the selected decision provider chooses a real response |
| Offer One Berry | OFFER_FOOD; current capacity/proximity/stock checked again at completion |
| Give One Berry / Sorry, I Cannot | SHARE_FOOD / REFUSE_REQUEST referencing the real addressed request ID |
| Listen / Accept invitation | The initiating NPC's actual previously selected action |
| Goodbye / Leave | Complete or cancel the existing session; no invented transfer |

An offered berry follows the existing valid-gift rule; there is no new recipient bargaining algorithm. When the player asks for food, the selected existing offline provider decides once. Personality, needs, supplies, guarded trust and memories retain their existing influence. A different survival choice, malformed response or provider exception is reported as an unavailable/canceled request, never converted into a fake share/refusal. Final validation rejects changed inventories, positions, identities or request state safely; failed execution is logged.

portrait_templates.py provides concise authored variations using the existing seeded dialogue RNG, character style, current needs/supplies/activity/goals, guarded trust and actual past help. It never decides acceptance. Successful/refusal wording is generated by the social system only after the validated outcome. Repeated painting/input navigation never consumes decision RNG or regenerates dialogue.

Greeting trust/memory is recorded once per modal conversation; repeated topics do not farm it. Acknowledgment remains available when reopening during a cooldown, but does not add another greeting reward. Actual gifts/refusals retain their existing directed trust/memory effects. Request retry limits remain in force. Memory-disabled mode reads neutral trust/empty recall and hides historical-thanks choices.

## Explicit pause and timing policy

Ordinary world time freezes while player dialogue is active: Simulation.step and FixedTicker cannot advance needs, resources, wildlife, background jobs or NPC-to-NPC sessions. Existing social/session state remains the single source of truth.

A local UI action clock advances **only the selected social job** in 0.25-second units, at human-readable 1× timing. Acceptance/completion still pass the common validator/executor; no physical social result occurs early. Accepted turns are published through the same social event path when the reader continues. Request deadlines stay at frozen world/social time, so slow reading or the old real-time prompt countdown cannot expire a player interaction. World timestamps can therefore be identical across several read turns; that is intentional.

The modal preserves the previous manual pause flag and speed. Closing releases the shared session/locks and clears held human input. An interrupted, replaced or invalidated job cannot be completed by a stale UI driver. Loading a full-world checkpoint releases unfinished sessions as before; committed inventory/memory remains, without replaying rewards. Preview-like demos do not replace the ordinary social system.

## Incoming and autonomous conversations

Existing nearby NPC proposals/prompts open the initiating character's portrait. The human explicitly accepts/declines invitations and answers actual food requests; no NPC chooses for the human. Unsupported or expired requests cannot be answered. Full inventory disables accepting an offered berry.

NPC-to-NPC encounters retain their normal simulation-time approach, facing, idle animations and speech bubbles. They never open a portrait modal in Observer Mode. Player portrait turns are tagged for portrait presentation: they remain in conversation history but are not replayed as duplicate world bubbles afterward. Other NPC speech remains untouched.

Histories retain the existing bounds (120 saved dialogue turns, 200 news records, 20 memories per NPC; normal engine event/session retention). A modal visit permits at most 64 authored turns, then offers a manual Continue Another Time exit. No unread turn or persisted history is discarded to enforce that limit. UI queues, portrait variants and panel surfaces are bounded.

## Executed verification

Pre-change full baseline: **446 passed, 1 skipped**. Focused regressions cover asset integrity/mapping/alpha/fallback/cache/scaling; dialogue opening/painting/paging/names/keyboard/mouse/scroll/exit; actual sharing/refusal/capacity; incoming consent; proximity/facing/idle animation; pause and background jobs; one-time trust/memory/rewards; stale/invalid/expired requests; provider failures; memory-off isolation; save/load; bounded visits and exclusive modal ownership. **Final main suite: 501 passed, 1 skipped, zero failures in 59.15 seconds** (`python -m pytest -q -p no:cacheprovider`), including 55 new regressions. Actual rule-based/mock CLI launches each ran 1,000 ticks with four agents and zero API calls. All four actual demo commands opened one valid session, closed cleanly with the lease released, and did not create their isolated history files. Networking was blocked during these checks. All 262 protected existing files and the four supplied portrait hashes matched after verification.

Generated examples under artifacts/portrait_dialogue are actual SDL-rendered accepted sessions, not fabricated outcomes. rendered_examples.json includes the seed-7 Ren request: inventories stayed 0/5, Ren refused, and the player's directed trust changed by -2 through the normal rules. Tests also exercise both share/refuse outcomes using the actual rule provider across seeded controlled initial conditions; fixture-controlled responses are separate test doubles, not claimed real AI results.

All work remains offline. The historical live API test remains skipped. SDL screenshots/input checks are executed; native macOS/Retina visual approval is **not** claimed. A native demo launch reached its rendering loop, but computer-use tooling could not bind the Python app; that test process was deliberately stopped. The manual checklist below remains necessary for native interaction/Retina review.

Manual review: launch each four demo commands; inspect portrait identity/hat/hands/aspect; reveal and page text; navigate disabled and scrolled choices; ask/offer food and inspect real inventory/trust/memory; leave mid-action; receive an NPC invitation; resume and walk; check Observer NPC bubbles; repeat at --window-scale 0.85 and 1.25. No forced acceptance, expression animation, quests or extra gameplay systems were added.

## Files

New modules: portraits.py, dialogue_view.py, dialogue_controller.py and portrait_templates.py. New assets: four original supplied PNGs plus portrait manifest/readme. New regressions: tests/test_portrait_dialogue.py. Updated integration: social.py, dialogue.py, pacing.py, simulation.py, feedback.py, rendering.py, participant_ui.py and __main__.py; one existing Participant timeout test now checks the explicit no-timeout portrait policy. README, GAMEPLAY_GUIDE and DEVELOPMENT_GUIDE link this guide. Requirements, original sprite art, energy/hunger tuning, inventory models and saved private data are preserved.

## NPC-led intention repair

Incoming Listen now acknowledges an invitation only. Its original session retains the offline-selected request, offer, casual greeting, observed check-in or memory-supported thanks through approach and portrait opening. The NPC speaks first, then the player sees only appropriate responses. Accepting an offered berry is a separate validated timed action; declining or canceling never transfers food. Completed outcomes end naturally after reading. Player-led menus and NPC-to-NPC bubbles are preserved. See [NPC_DIALOGUE_AGENCY.md](NPC_DIALOGUE_AGENCY.md) for implementation boundaries, verification and manual checks.
