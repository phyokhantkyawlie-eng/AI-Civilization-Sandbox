# NPC-initiated dialogue agency

## Cause and fix

The old planner replaced the final step of a social approach with TALK, losing food intentions. The portrait controller also discarded the incoming invitation after acknowledgment and returned to the ordinary player-led topic menu. Listening to an offer could transfer food immediately.

The existing InteractionSession now retains a typed ConversationIntent: kind, item, quantity and selected context, alongside its original initiator, recipient, lifecycle, request ID and outcome. An explicit intent_resolution records the final response once. The offline provider reserves this session before travel; moving targets retain the original terminal action. No second conversation system, provider API or transfer mechanism was introduced.

A human acknowledgment means **Listen**, never transaction consent. The NPC speaks first, using its retained intention. Until resolution, choices are limited to:

| NPC intention | Player responses |
| --- | --- |
| Request one berry | Give one berry, refuse, explain having none when applicable, or end |
| Offer one berry | Accept or politely decline |
| Casual talk, check on player, thanks | Respond warmly, briefly, or end |

Resolved conversations end after the reader finishes the outcome lines. Player-initiated visits retain their ordinary topic menu. NPC-to-NPC encounters retain simulation-time bubbles and shared rules. Portrait artwork and animation assets are unchanged.

## Selection and safety

Food requests require the offline policy to select seeking help; offers require a real spare berry, observed need, the existing personality willingness decision and survival priorities. The policy may approach a visible human within four tiles. Selection is not guaranteed; food gathering and other goals compete. Current physical observations remain available with memory disabled.

A selected TALK may become a check-in when the player visibly needs food/rest, or gratitude when guarded memory contains an actual previous gift from that player. Gratitude is not selected from historical data when memory is disabled. A presented, resolved thank-you is suppressed for the same remembered help within the existing bounded session history. These are authored offline templates, not generated model dialogue.

All responses still use ActionProgress and the common validator/executor. Transfers remain one berry and are validated again at completion. Missing stock/capacity disables acceptance; stock lost during an accepted action causes safe failure. No result wording claims a transfer before execution. Actual food events update the existing directed trust and memories once. Declining an offer records a no-transfer interaction. Cancellation removes requests, reservations and unfinished jobs and retains social cooldowns. Unanswered invitations cannot be overwritten by another NPC.

World time remains frozen during portrait reading. The existing local action clock runs only the validated selected social job. Save/load continues to release unfinished conversations rather than replaying them; completed inventories and memories remain authoritative.

## Run and manually verify

```bash
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox"
source .venv/bin/activate
python -m civsandbox --mode participant --character mira --scenario food_shortage --provider rule-based --seed 7
```

1. Carry berries and remain within four tiles of a hungry villager without berries. Allow ordinary offline decisions to run; an invitation depends on competing needs and cooldowns.
2. Listen: the approaching NPC's portrait should ask for one berry. Only request responses should appear. Compare inventories before listening, after listening, and after the timed Give response: only the completed response transfers one berry.
3. Repeat after cooldown and refuse, or answer without berries. No food should move; inspect the actual refusal memory and trust result.
4. As a hungry character without food, remain near a well-supplied cooperative villager. If they offer, listening should show their offer without transferring it. Accept or decline explicitly. A full inventory disables acceptance.
5. Observe casual/check-in dialogue; after actually helping a character, a later selected greeting can thank you. End or cancel and check that both characters can move again.
6. Initiate a visit yourself: confirm the ordinary Ask for berries/Offer/Small talk menu remains. Switch to Observer Mode and confirm NPC-to-NPC bubbles still work.
7. Check portrait identity, readable pacing, facing, name labels, mouse/keyboard selection, pause/resume and leaving mid-action on macOS.

No native visual approval is claimed for this fix. Automated SDL tests exercise the existing portrait/UI integration. Controlled regressions use real rule-policy approaches for requests and offers, and separately labeled fixture providers for exhaustive outcomes; they do not guarantee outcomes in ordinary gameplay.

```bash
python -m pytest -q tests/test_npc_dialogue_agency.py tests/test_portrait_dialogue.py
python -m pytest -q -p no:cacheprovider
MEMORY_PATH=/tmp/civsandbox-agency-fresh.json python -m civsandbox --headless --provider rule-based --scenario food_shortage --ticks 1000 --seed 7
```

Use a fresh temporary history filename to keep normal saved history isolated. Networking is prohibited by the full test suite's socket/DNS fixture. No external service or credential is required. Main-project recovery checkpoint before this fix: `49cbd8b`; private histories and existing assets are preserved.

## Executed results

Final main-project run: **523 passed, 1 skipped, zero failures in 64.47 seconds**, using `python -m pytest -q -p no:cacheprovider`. This includes 22 new agency regressions plus the preserved portrait, social, planner, persistence and rendering suites. The historical live API test remains skipped. The full suite prohibits network attempts, including caught connection failures.

Rule-based and mock main-project CLI checks each completed **1,000 ticks**, seed 7, food_shortage, with all four agents, networking blocked and separate temporary history paths. `compileall` and Git whitespace checks succeeded. Checksums verified **1,940 existing asset, private-data, configuration and prototype files unchanged**. All 12 applied source/test/documentation files matched staging. No native interactive visual result is claimed; follow the checklist above.
