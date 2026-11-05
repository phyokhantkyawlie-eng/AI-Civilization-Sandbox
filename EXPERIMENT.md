# Social memory experiment

Research question: How does access to social memory affect cooperation and decisions under food scarcity?

From the activated project environment:

```bash
python -m civsandbox.experiments --provider rule-based --runs 3 --ticks 300 --seed 42 --scenario food_shortage
python -m civsandbox.experiments --provider mock --runs 2 --ticks 100 --seed 42
```

Each seed produces MEMORY_OFF and MEMORY_ON trials. Each trial creates a fresh provider, simulation, RNG, relationship map and memory history, with no persistence path. The initial-state hash covers the physical map, agents, resources and RNG state. Seeds increment from --seed. Memory-off context excludes interaction history and trust, and the local policy's trust lookup returns zero. Current observations and active requests remain available. Provider caches never carry between trials.

Each timestamped UTC output folder contains configuration.json, trials.csv and summary.json. JSON uses null for unavailable quantities; CSV uses empty cells. Final directed trust is a JSON object in each CSV row. A failed trial is retained and excluded from statistical summaries, and subsequent trials continue. Keyboard interruption saves completed rows. Trial errors expose exception types only.

Metric definitions:

- Requests count social events with result pending, excluding duplicated executed-action logs.
- Shares count completed one-unit food transfers. Refusals count completed refusals.
- Cooperation rate is shares / (shares + refusals). Expired/unanswered requests are reported separately. This measures willingness among resolved responses, not overall welfare.
- Survival rate is unavailable. The simulation does not model death, so reporting 100% would not measure survival.
- Average hunger is the sum of post-tick hunger across NPCs divided by NPC-tick observations. Initial hunger is excluded.
- Final trust contains every NPC's outgoing trust values, including audit trust when recall is off.
- Invalid action rate is engine rejections plus rejected model choices divided by completed NPC action opportunities. An invalid choice followed by a valid fallback counts once as invalid. Cooldowns and timeouts are not invalid actions.
- Gemini calls count dispatched generation attempts, including failed requests.
- Fallback count counts NPC-ticks whose provider status indicates fallback, including pending requests and cooldowns. Rule-based selection has zero AI fallbacks.
- Duration includes measured trial wall seconds and simulated seconds (completed ticks × .25). Failed partial trials retain completed tick counts.

Condition means, sample standard deviations and paired MEMORY_ON minus MEMORY_OFF differences use completed trials. Pairs require both trials and identical initial hashes. Each metric has its own available-value count. At least five observations are required to display approximate 95% normal confidence intervals for a mean or mean paired difference. These intervals assume independent seed-level observations and are descriptive approximations. Small samples cannot support strong conclusions. No significance tests are claimed.

Offline seeds reproduce decisions and outcomes given identical configuration and code. Wall durations vary. Gemini model sampling and network timing make live outputs stochastic. Live trials run at .25 wall seconds per tick, allowing pending requests time to complete. The existing 12-tick stale-response rule still applies.

External-provider CLI execution is disabled in the offline-first build. Use rule-based or mock. API columns remain in the export schema for compatibility and are zero for current offline runs. Historical external-provider notes are archival only.

Normal game history is ignored even if MEMORY_PATH is configured. Trials start with neutral trust and empty memories. Avoid interpreting audit trust stored in MEMORY_OFF as knowledge the agents could access. Initial food inequality, fixed NPC processing order, limited personalities, a single map scenario, and the absence of death mechanics constrain generalization.

The initial offline pilot used seeds 42–44 for 300 ticks per condition. Observed requests/shares/refusals were 8/0/8, 24/1/23 and 18/1/17 for MEMORY_OFF, and 6/1/5, 10/2/8 and 10/1/9 for MEMORY_ON. This small pilot demonstrates the export pipeline and is insufficient to establish a memory benefit. The full suite passed 137 tests with the optional live test skipped.

## Stage 3 survival counters

New per-trial exports add gathering_actions (committed gathers), hunting_attempts (accepted pursuit starts), hunting_successes (committed rewards), cooking_completions (committed raw-to-cooked conversions), meals_consumed (committed EAT counts by item), incapacitations (entered recovery states), failed_plans and interrupted_plans. These are counts, not rates. Missing planner statistics on a provider are unavailable rather than fabricated. initial_food_items/final_food_items permit conservation checks. Existing hunger_series and average_hunger retain their definitions: average across every sampled NPC tick; no sample means unavailable. Catalog/cook timing and the initial campfire are now part of configuration/fingerprints. Old result files do not contain these counters and must not be presented as Stage 3 measurements.
