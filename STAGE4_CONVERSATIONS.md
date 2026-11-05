# Stage 4 — Natural social encounters and readable conversations

## Implemented

The existing SocialSystem now owns shared, uniquely numbered sessions: PROPOSED → APPROACHING → ENGAGED; food questions wait in WAITING_FOR_PARTNER, actual outcomes pass through RESOLVING, then COMPLETED or CANCELED. Metadata records both identities, purpose, logical start/deadline, turn, outcome and cooldown. No second social-effect/event system was introduced.

Only selected social intent creates an approach reservation. The partner must exist, be reachable and available. Both actors stop and face one another on acceptance; exclusive session slots and timed activity locks prevent simultaneous conflicting exchanges. Healthy partners wait during a bounded approach. Separation, invalid targets, unavailable partners, incapacitation, urgency and timeouts release reservations safely. Requests remain addressed, expiring objects; answers use their actual request IDs.

Authored offline dialogue uses purpose, numeric personality, current needs/berries, guarded trust and relevant memories, with a separate seed-derived RNG. Templates cannot change the world. Offers/questions describe intent; statements that food was given and recipient thanks follow successful validated transfers only. Atomic executor helpers without sessions produce no speech. Unaccepted intent, distant passersby, arbitrary provider explanations and independent timers cannot create dialogue.

The existing utility policy now considers nearby hungry neighbors for voluntary one-berry OFFER_FOOD, reachable company within four tiles of the campfire, and taking space after a recent serious refusal. Willingness remains personality/needs/trust based with seeded decisions, not a guaranteed character script. Both ordinary greeting trust changes are +1 before personal trust-gain scaling. Successful help adds +6 receiver trust (+14 when starving) and +2 giver trust. Refusal costs requester trust 0 for an empty giver, −2 ordinarily, or −4 when a starving requester meets a giver with at least two berries. Actual bounded trust deltas and memories are recorded once per social event. Ordinary refusal is not extreme betrayal.

## Pacing and controls

Short lines last max(3 seconds, 1 + characters / 18) by default. Logical duration is rounded up to .25-second ticks; a greeting uses two turns, while question/consider/outcome/acknowledgment exchanges take longer. Existing configured action durations are lower bounds. No blocking sleeps are used. Headless runs advance logical turns immediately with simulation ticks.

The renderer separately holds each accepted line for its minimum real reading duration, independent of .5×/1×/4× speed. Pause freezes simulation and reading. Above-character speech is restricted to the still-engaged original session. Once the NPCs finish or move, the remaining text stays in the conversation panel instead of becoming walking speech. A bounded queue holds 64 pending lines; recent history retains 60 delivered turns. At sustained high speeds the reading queue can lag and discard its oldest pending lines when full. This deliberately bounds memory; it is not a transcript recorder. C history shows the latest delivered turns and may therefore be ahead of the reading queue.

- Space / Pause: freeze or resume both clocks.
- Left/right arrows or −/+: simulation speed.
- Click an NPC: needs, activity, inventory and personality.
- C: conversation history; mouse wheel scrolls earlier turns.
- F3, then S: session identity/state, partner, logical start, current turn, cooldown, directed trust and changes, transitions and top utility scores.
- F3, then P: existing planner debug view.

Normal dialogue uses natural authored text, not technical session-state names. The activity summary and interaction badges remain visible; templates are labeled authored offline. No language model or network is involved.

## Configuration

All settings are local and optional; see .env.example. Keep the existing private .env.

| Setting | Default | Meaning |
| --- | ---: | --- |
| SOCIAL_AGENT_COOLDOWN_SECONDS | 10 | Agent conversation cooldown |
| SOCIAL_PAIR_COOLDOWN_SECONDS | 24 | Pair cooldown after speech |
| SOCIAL_REQUEST_RETRY_SECONDS | 20 | Addressed request retry |
| SOCIAL_REPEAT_SECONDS | 40 | Suppress repeated speaker/pair lines |
| SOCIAL_APPROACH_TIMEOUT_SECONDS | 12 | Bounded approach |
| SOCIAL_RESPONSE_TIMEOUT_SECONDS | 16 | Request lifetime after question |
| SOCIAL_AVOID_SECONDS | 20 | Recent serious-refusal avoidance window |
| DIALOGUE_MIN_SECONDS | 3 | Minimum real reading time |
| DIALOGUE_CHARACTERS_PER_SECOND | 18 | Reading-speed estimate |

If the new agent cooldown is absent, legacy SOCIAL_COOLDOWN_SECONDS remains its default. Unspoken canceled proposals use short 1-second agent / 2-second pair cooldowns. Starving empty-handed requesters cap pair/request cooldown waiting to ten seconds after the previous attempt ends; this bypass does not override busy partners or create guaranteed sharing. Essential lines may reuse the least-recent template when all variants are suppressed. Cooldowns and current-session observations exist in both memory conditions; historical trust, help recollection and avoidance are guarded off in MEMORY_OFF.

## Actual verification

Baseline before changes: **251 passed, 1 skipped**. Final staging and main-project full suites: **272 passed, 1 skipped, 0 failures** (main: 16.51 seconds). New coverage verifies proximity, stopping/facing, busy/conflicting partners, cancellation cleanup, ordered turns, pause and speed, cooldowns including shorter configuration, one-time transfers, truthful thanks, failed gifts, trust/memory, no fabricated speech, deterministic sessions, memory-off avoidance, campfire approach and UI controls. The skipped historical live test stays disabled.

Six isolated rule-based food_shortage trials, seeds 7–9 × MEMORY_OFF/ON, each ran 2,400 ticks (600 simulation seconds). Socket/DNS calls were blocked during verification. CSV/JSON exports, equal paired initial fingerprints and berry/raw/cooked conservation were checked. Trials started fresh without normal save history. Counts below are per condition; the two conditions happened to match for each seed.

| Seed | Completed / canceled sessions | Turns | Requests | Requested shares | Refusals | Voluntary transfers | Thanks | Campfire chats |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 7 | 6 / 0 | 22 | 5 | 0 | 5 | 0 | 0 | 0 |
| 8 | 3 / 1 | 11 | 1 | 0 | 1 | 1 | 1 | 0 |
| 9 | 2 / 1 | 9 | 2 | 0 | 2 | 0 | 0 | 0 |

Across all six trials: **22 completed sessions, 4 canceled, 84 turns, 16 requests, 16 refusals, 2 voluntary transfers and 2 thanks**. No requests expired; zero API calls. No requested shares or natural campfire sessions were observed. Separate controlled regression fixtures verify successful requested sharing and campfire approach; those are not counted as natural trial outcomes. The pilot has only three seeds and shows no measured memory effect.

Average hunger per seed was 42.594, 35.149 and 36.361 in both conditions. Temporary incapacitations were 5, 1 and 1 per respective condition; permanent death remains unimplemented. There were 208 rejected actions across all six trials. An instrumented seed-7 check identified all 45 rejections there as final GATHER validation failures: finite resources can disappear during timed work. Rejections safely fall back and do not create food; the report does not claim all planned work succeeds.

Genuine output files are in ignored artifacts/stage4/final_verification/{configuration.json,summary.json,trials.csv}; compact counts are artifacts/stage4/final_counts.json. Saved SDL dummy captures in artifacts/stage4/ illustrate dialogue, C history and F3/S layout using a controlled fixture, not natural outcomes. Original artwork and private histories are preserved.

## Run and reproduce

```bash
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox"
source .venv/bin/activate
python -m civsandbox --provider rule-based --scenario food_shortage --seed 8
python -m pytest -q
python -m civsandbox.experiments --provider rule-based --runs 3 --ticks 2400 --seed 7 --scenario food_shortage
```

The experiment command creates a new timestamped directory and never loads normal game history. Normal interactive play does load configured social history, so it need not match a fresh trial. Use a fresh temporary MEMORY_PATH for isolated CLI headless checks.

## Manual visual QA and limits

SDL dummy rendering and screenshot inspection succeeded; native interactive macOS visual approval was not performed. Launch normally and check: both actors stop/facing before speech; readable unclipped bubbles near each map edge; at most one session per actor; no walking popups; .5×/1×/4× reading duration; pause mid-turn preserves text; C scrolling; F3/S trust/cooldowns/transitions; activity labels; return to walking after completion/cancellation; original four colors/foot anchors; two simultaneous independent encounters remain readable. The oldest pending reading lines can be dropped under prolonged acceleration as described above.

This is a small authored vocabulary, not open-ended dialogue. Disagreement/apology narratives, external AI, new artwork, marriage/factions and full world-save persistence are not added. Social JSON keeps its existing schema and stores actual interaction memories/trust; sessions and presentation queues are transient. The pre-stage recovery point is Git commit 02ab707.

Final main-project checks also executed 1,000-tick rule-based and mock CLI launches with sockets, DNS and external SDK imports blocked, using fresh temporary history files. Each advanced four agents successfully. A fresh main-project seed-7 MEMORY_OFF trial matched the saved export for all non-wall-time metrics, hunger trajectories and initial fingerprint. All 89 recorded private configuration/history/artwork file hashes remained unchanged. `git diff --check` passed.
