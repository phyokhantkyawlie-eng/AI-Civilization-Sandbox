# Evaluation results and decision viewer

Generate fresh paired offline data from the activated project root:

```bash
python -m civsandbox.experiments --provider rule-based --runs 3 --ticks 120 --seed 42
python -m civsandbox.results
python -m civsandbox.results experiments/EXPERIMENT_DIRECTORY
python -m civsandbox.results experiments/EXPERIMENT_DIRECTORY --show
```

The first command prints the saved folder. The second lists available experiments. Supply one folder to select it. Chart generation writes six PNG files under its charts directory. --show opens Matplotlib chart windows and a recent-decision window with an index slider. No web server is required. Use MPLBACKEND=Agg when exporting on a headless machine and omit --show.

Pandas reads the genuine trial rows in summary.json. The viewer includes failed trials in the table, with unavailable fields left unavailable, but excludes failures from plotted means. configuration.json and trials.csv remain the runner's original data. charts/decisions.json and decisions.csv contain retained decision records. The most recent 100 NPC decisions per trial are saved by new runner executions. An older experiment without trajectory or decision data displays an unavailable notice and an empty decision export. Regenerating charts never reruns a simulation or contacts Gemini.

## Charts

- Cooperation shows shares / (shares + refusals), one point per defined trial, a mean mark and sample standard deviation when at least two observations exist. Zero resolved responses produce unavailable rates.
- Sharing and refusal charts show per-trial event counts and variation.
- Survival is unavailable because no death mechanic exists.
- Hunger over time shows the post-tick mean across four NPCs. Thin lines represent trials and colored lines the condition mean. Bands represent one sample standard deviation across trials. Scalar average hunger in older exports cannot reconstruct this series.
- Directed trust changes start from neutral zero in isolated runner trials. Bars show the mean final outgoing trust for each ordered NPC pair and sample variation. MEMORY_OFF scores are audit outcomes, not information provided to agents.
- The trial table shows seed, condition, provider/model, requests, shares, refusals, cooperation, survival, average hunger, invalid actions, API calls and fallback NPC-ticks. Full model names and numerical precision remain in source JSON.

Dots and standard-deviation bars show variability, not confidence intervals. Existing summary.json paired summaries contain MEMORY_ON minus MEMORY_OFF differences and approximate mean confidence intervals only when at least five paired observations are available. Pairing requires matching initial-state hashes. A three-pair pilot is too small for strong conclusions.

## Decision transparency

Records identify the character, configured provider, executing provider, fallback flag/reason, selected action, validation result and actual outcome. They include sampled pre-decision needs, goal, personality, visible peers, adjacent food/hunger cues, local resource quantity and recall-gated trust/memory count. Full rule-based policy has map-wide resource access. Mock and Gemini use local perception.

Context records are sampled at the execution tick. An asynchronous Gemini action may have been requested earlier; this summary is not a verbatim original prompt. Public model explanations come from accepted structured output. Rule summaries report the executed action and needs. Mock explanations explicitly identify the offline mock. Fallback entries identify their source separately. Invalid proposals are replaced safely and receive a validation note. Private model thought parts and API credentials are excluded.

## Metrics and interpretation

Cooperation divides shares by resolved shares plus refusals. Average hunger divides post-tick NPC hunger totals by NPC-tick observations. Invalid action rate divides recorded invalid choices by completed NPC action opportunities. API calls count dispatched generation attempts, including failures. Fallback counts measure NPC-ticks under fallback, including pending/cooldown execution, rather than distinct API failures. Survival has no denominator because it is unavailable. See EXPERIMENT.md for the complete definitions.

Compare matched seeds and inspect per-trial variation before discussing averages. More sharing can coexist with higher hunger, so cooperation and welfare should be discussed together. Fixed NPC processing order, map layout, starting food inequality, occupancy recovery, scenario duration, local visibility, and provider fallbacks can confound conclusions. Code changes affect trajectories; do not pool earlier and current experiments without identifying the versions. Rule/mock outputs reproduce with fresh identical seeds and configuration. Gemini outputs also depend on model sampling, latency and stale-response rejection.

External-provider CLI execution is disabled in the offline-first build. Use rule-based or mock. API columns remain in the export schema for compatibility and are zero for current offline runs. Historical external-provider notes are archival only.
