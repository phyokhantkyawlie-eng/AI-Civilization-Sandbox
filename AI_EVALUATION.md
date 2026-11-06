# Offline AI evaluation — final release

## Question and implemented algorithms

How does access to social memories and historical directed trust affect cooperation and decision-making in a resource-limited village? The agents use authored local utility scoring, bounded forward task queues, BFS, finite-state actions, social memory and trust rules. No weights are trained, no neural network runs, and no LLM/external API supplies decisions or dialogue. See ARCHITECTURE.md for the actual pipeline and information limits.

## Reproducible scenarios and controls

All research runs are headless Observer Mode: four original agents, no player intervention, fresh providers/caches/RNGs, neutral initial trust, empty social history and no normal-game persistence path. Experiments deliberately use recorded default Settings rather than silently loading private .env gameplay overrides. Configurations, initial agent states, seeds and physical/RNG fingerprints are exported.

| Scenario | Actual release trials | Duration per trial | Setup |
| --- | ---: | ---: | --- |
| A normal_survival | 5 | 12,000 ticks / 3,000 seconds | Ordinary berries, four agents, two living chickens |
| B food_shortage | 5 | 12,000 ticks / 3,000 seconds | Reduced berries, unequal food and needs |
| C social_memory | 10: five OFF/ON pairs | 12,000 ticks / 3,000 seconds | Same shortage setup; only historical social access changes |
| D hunting_decisions | 35: seven profiles × five seeds | 2,400 ticks / 600 seconds | Controlled initial needs, carried food and wild-food supply |

Seeds are **7–11** for every group. The provider is **rule-based**; model is unavailable because no model exists. All 55 actual trials completed, used zero API calls and passed three-item food conservation. B and C/MEMORY_ON repeat the same seeds/configuration and reproduce the same outcomes; do not treat them as ten independent statistical seeds. The suite has 55 executions, not 55 independent samples for a single hypothesis.

C pairs match initial world, agents/personality/inventory, resources, time/configuration and RNG hashes. MEMORY_OFF reads neutral trust and empty recall through guarded accessors; recorded audit trust is not exposed to its policy/context. Both conditions retain current observations, needs, inventory, incoming requests, commitments, mechanical retries and cooldowns. Histories are isolated across trials. Matching seeds does not force equal future draws after behavior diverges. Memory also changes eligible authored greeting banks; text length can affect session duration. The experiment assesses the joint social-access mode, not an isolated trust coefficient or a language model.

D uses the same shortage geometry/personality values, with two reachable chickens initially placed three to four tiles from villagers to create an encounter opportunity. Their normal movement/fear FSM remains active; no target is immobilized and no hunt or reward is forced. Profiles initialize all four agents as follows:

| Profile | Hunger | Energy | Carried food | Wild berries |
| --- | ---: | ---: | --- | --- |
| well_fed | 25 | 90 | none | five per bush, ordinary regrowth |
| moderate | 65 | 90 | none | same |
| hungry | 90 | 90 | none | same |
| exhausted | 90 | 15 | none | same |
| carried_berries | 90 | 90 | two berries each | same |
| carried_meal | 90 | 90 | one cooked meal each | same |
| scarce_berries | 90 | 90 | none | initially empty, 240-tick regrowth |

These are initial conditions, not ongoing interventions. Agents may eat/rest and change eligibility later. Hunger/energy and carried-food profiles permit controlled contrasts; the scarcity profile changes both initial stock and regrowth as a combined supply condition.

## Metric definitions

- Requests: completed creation of actual addressed food requests; shares/refusals: committed responses. Cooperation = requested shares / (requested shares + refusals). No resolved response means unavailable, not zero. Expired, canceled and unanswered requests are separate; voluntary offers are separately counted and excluded from this historical request-response rate.
- Mean hunger/energy: sum of post-tick values across all NPCs / completed NPC-tick samples. Initial values are excluded; zero ticks gives unavailable. Samples = four × completed ticks.
- Mortality survival: **unavailable**, because NPC death is not modeled. Operational availability = 1 − incapacitated NPC-ticks / all NPC-ticks; it is a separate reversible-incapacitation proxy, not a mortality survival rate.
- Goal choices: actual GOAL_SELECTED events, distinct from steps or completed work. Hunting attempts: accepted pursuit starts; successes: validated raw rewards; failed hunts: HUNT_FAILED events. Pending pursuits at cutoff are reported separately.
- Gathered food, cooking and meals: completed actions, with meals broken down by item. Inventory conservation checks initial berries + gathers − berry meals = final berries; initial raw + hunt successes − cooks = final raw; initial cooked + cooks − cooked meals = final cooked. Social transfers conserve totals.
- Activity time: one exclusive label per agent per completed tick: recovering, engaged conversation, or current action. NPC-seconds = NPC-ticks × .25. Pursuit time includes movement/waiting inside HUNT. Counts sum to all sampled NPC-ticks; overlapping labels are not double-counted.
- Trust change: final minus initial directed value for each of 12 ordered NPC pairs. Mean trust change averages those 12 edges. MEMORY_OFF audit changes are measurements, not accessible historical input.
- Social frequency: completed sessions / simulated world minutes. Canceled sessions and dialogue turns have separate counters.
- Invalid-action rate: engine rejections plus rejected structured choices / completed NPC action opportunities (including work/WAIT updates). It is not the proportion of goals that fail. Failed plans and failure categories are separate.
- Spawn timing: delay from a target's own spawn to an accepted hunt. Startup and replacement cases are distinguished. A starving NPC choosing a valid hunt immediately at startup is not evidence of a global spawn-trigger policy.
- Legacy gemini_calls is always zero for supported offline providers. Fallback count retains its original meaning: NPC-ticks whose adapter status indicates fallback, including cooldown fallback. It is not the number of invalid actions. Rule-based trials have zero adapter fallbacks.

Trial totals stream independently of a **4,096-event** retained engine window. Trajectories sample at max(1, ceil(duration/1000)) ticks, also including first/final samples, for at most 1,001 points. Averages and activity totals still use every completed tick. The last 100 decision traces are a bounded illustration, not a full transcript.

## Actual results

| Group | Requests | Requested shares | Refusals | Voluntary offers | Hunts / successes | Cooks | Incapacitations | Mean hunger | Mean energy |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| A normal, ON | 4 | 1 | 3 | 0 | 0 / 0 | 0 | 0 | 29.712 | 63.245 |
| B shortage, ON | 95 | 26 | 54 | 9 | 15 / 15 | 15 | 243 | 49.801 | 58.618 |
| C shortage, OFF | 92 | 24 | 51 | 9 | 16 / 16 | 16 | 240 | 49.628 | 58.701 |
| C shortage, ON | 95 | 26 | 54 | 9 | 15 / 15 | 15 | 243 | 49.801 | 58.618 |

Counts are sums of five trials per row; need values are means of trial averages. A gathered 1,766 berries; B gathered 1,463. Operational availability averaged 1.000 in A, 0.98785 in B/C ON and 0.98800 in C OFF. These values do not imply measured mortality survival.

The mean per-trial cooperation rate was **0.319179 OFF** and **0.321434 ON**. The paired ON-minus-OFF difference was **+0.002256** (0.226 percentage points), approximate 95% normal interval **[−0.002165, +0.006677]**. Paired mean hunger difference was **+0.173908** (interval [−0.166952, +0.514769]); energy was **−0.083171** (interval [−0.246186, +0.079844]); mean directed trust change difference was **+0.233333**. Four of five pairs matched on these metrics; seed 10 accounted for the differences. Pooled resolved-request rates, 24/75 OFF and 26/80 ON, have different weighting and must not be substituted for the paired per-trial effect.

**This pilot does not establish a memory benefit.** The cooperation difference is tiny, intervals include zero, and average hunger/energy moved slightly unfavorably. Five pairs are a small descriptive sample, not strong causal evidence or a significance result. Approximate intervals use mean ±1.96 × sample SD / sqrt(n), only for at least five homogeneous seed-level observations. Mixed scenario/profile pooled intervals are withheld. Charts show per-trial variation and ±1 sample SD, not confidence bands for a proven effect.

D observed:

| Profile (five trials each) | Attempts | Successes | Attempts in first 30 simulated seconds |
| --- | ---: | ---: | ---: |
| well_fed | 0 | 0 | 0 |
| moderate | 0 | 0 | 0 |
| hungry | 2 | 2 | 2 |
| exhausted | 2 | 2 | 2 |
| carried_berries | 0 | 0 | 0 |
| carried_meal | 0 | 0 | 0 |
| scarce_berries | 24 | 18 | 10 |

D totals: 28 attempts, 22 successes, six failures, 21 cooking completions and 2,377 gathers. Zero moderate hunts in this small mobile-wildlife sample does not mean hunting is impossible with berries; targeted policy tests verify that eligibility. In a matching exhaustion probe, the two eventual hunts started at ticks 49 and 114 with **74 and 54 energy**, after recovery from initial energy 15. They were not hunts executed while exhausted.

Across B and D, respectively 15 and 21 repopulations occurred; **zero hunts started within one tick of replacement**. Eleven near-startup hunts occurred in hungry/scarce D settings, where hunger/supply justified eligibility. Well-fed controls ignored the same encounter opportunities. Source inspection confirms spawn events do not command decisions. No duplicate chicken IDs or meat rewards were detected.

## Long runs, loops and memory inspection

Two additional fresh seed-42 runs each advanced **30,000 ticks / 7,500 simulated seconds** under tracemalloc, with no network and no player. Normal: mean hunger 29.339, energy 62.835, 874 gathers, no hunts/incapacitations and zero invalid actions. Shortage: hunger 51.702, energy 57.871, 742 gathers, five successful hunts/cooks, 132 incapacitations and 658 rejected actions. Conservation passed in both.

From tick 5,000 to 30,000, traced live allocations grew from 2,275,175 to 2,708,413 bytes in normal and 2,270,492 to 2,547,293 in shortage. Retained engine events stayed at 4,096; journals stayed within 200 news/120 conversations, sessions within 62, NPC memories within 80 total, and wildlife/measurement ID tracking remained bounded. Resource journals grew from 333→1,774 and 246→1,486 within their 8,192 cap, explaining deliberate retained-history growth. This is an inspection of tracked Python allocations, not total process RSS or proof of no possible leak. Tracemalloc overhead/concurrent jobs make those wall durations unsuitable as native FPS estimates.

Investigation found frequent night-rest goal reselection: brief WAIT plans reevaluate roughly every two seconds while resting is preferred. Agents still resumed useful work, with no normal-run incapacitation; this is a coarse routine policy, not a deadlocked pursuit. Shortage trial rejections were overwhelmingly contested GATHER completions (1,094 of 1,095), with one TALK revalidation. Finite stock can disappear while another agent works; rejection is safe but causes wasted time. No weights were tuned to manufacture better experimental results. These remain useful future improvement targets.

## Reproduce and inspect

```bash
python -m civsandbox.experiments --scenario normal_survival --runs 5 --ticks 12000 --seed 7 --memory-mode on
python -m civsandbox.experiments --scenario food_shortage --runs 5 --ticks 12000 --seed 7 --memory-mode on
python -m civsandbox.experiments --scenario social_memory --runs 5 --ticks 12000 --seed 7 --memory-mode paired
python -m civsandbox.experiments --scenario hunting_decisions --runs 5 --ticks 2400 --seed 7 --memory-mode on
python -m civsandbox.results PATH_PRINTED_BY_RUNNER --show
```

Use --provider rule-based or mock; mock is explicitly different adapter data. --profile selects one hunting profile and is rejected with other scenarios. --memory-mode on/off runs one condition, paired runs both. Each CLI batch creates a new timestamped directory and incrementally exports CSV/JSON/configuration, retaining failed rows without sensitive error text. Statistical pairing keys include scenario/profile/seed and require identical initial hashes. Legacy tick_seconds/call-budget arguments remain compatibility inputs; they cannot cause a network call or wall-clock sleep.

Final generated evidence is in artifacts/stage7/: release_evaluation/{normal,shortage,memory,hunting}, combined genuine summary/CSV, 11 charts, long_run_profile.json, exhaustion_check.json and demo_timeline.json. These are ignored generated files, not required to launch the game. Separate CLI commands regenerate batches/charts; the combined suite is a concatenation of those genuine rows, not synthetic trials. See RESULTS_GUIDE.md for chart interpretation.

## Limits and verification status

The suite covers five seeds, four fixed personalities, one small village family, fixed processing order and authored weights. Memory access bundles episodic recall/trust and can affect conversation pacing/random-stream branching. Requested cooperation excludes voluntary offers; conditional rates have different denominators. Hunting profiles are controlled initial states, not natural starting populations. NPC death, learning, unrestricted perception and open-ended dialogue are absent. Rule-based and mock outputs must not be pooled as one algorithm.

Fully automated checks exercise physics, survival, social outcomes, memory isolation, wildlife, cooking, Participant handoffs, save/load and offline operation. SDL dummy rendering tests/figure inspection are distinct from native macOS graphical approval. Native visual smoothness, Retina scaling and subjective game feel remain manual verification items. The final test count and recovery commit are recorded in FINAL_VERIFICATION.md. No live API experiment was run.
