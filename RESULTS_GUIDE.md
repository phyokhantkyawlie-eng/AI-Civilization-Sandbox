# Results viewer

Generate genuine data with EXPERIMENT.md. List saved experiments with python -m civsandbox.results; --root selects another parent. Select a folder explicitly:

```bash
python -m civsandbox.results PATH_TO_EXPERIMENT
python -m civsandbox.results PATH_TO_EXPERIMENT --show
python -m civsandbox.results artifacts/stage7/release_evaluation --show
```

The viewer uses local Pandas/Matplotlib, reads summary.json, writes charts/PNG figures plus decision CSV/JSON, and optionally opens Matplotlib windows. No web framework/network is involved. --show blocks until windows close. Use MPLBACKEND=Agg without a graphical desktop; point MPLCONFIGDIR and XDG_CACHE_HOME at writable temporary directories in restricted environments.

Eleven figures are generated:

| Figure | Interpretation |
| --- | --- |
| cooperation | Requested shares / resolved responses; points, mean and sample SD |
| sharing_refusals | Actual committed shares/refusals |
| survival | Mortality survival correctly unavailable |
| hunger_over_time | Sampled trajectories; mean and ±1 sample SD across seeds |
| trust_changes | Directed changes from neutral initial trust |
| trial_summary | First 20 readable rows; full CSV/JSON retains all |
| survival_across_scenarios | Mortality unavailable; separate operational availability proxy |
| gathering_hunting_choices | Actual goal selections per simulated minute |
| cooking_consumption | Completed conversions/meals per simulated minute |
| memory_comparison | NPC-tick mean hunger/energy by memory condition |
| food_availability_over_time | Wild berries and carried edible items in separately labeled units |

When the release suite contains social_memory, memory plots use that matched scenario rather than pooling unrelated cases. Cross-profile labels disclose duration; rates normalize differing durations. D's unequal initial supplies are excluded from the crowded cross-scenario resource trajectories. SD shows dispersion, not a confidence interval or proof of significance; bands can extend beyond physical bounds without representing actual negative stock. Missing trajectories are never reconstructed from a scalar average. Older/missing metrics are labeled unavailable.

Decision exports are the final bounded trace window: character, actual provider/fallback, physical context, action, public explanation, validation and outcome. They are not hidden chain-of-thought or a full transcript. Rule-based, mock and fallback sources stay distinguishable; no current experiment uses an LLM.

CSV nested records are JSON strings. Use Pandas or increase csv.field_size_limit for long trajectory fields. Failed rows are retained but excluded from completed-outcome statistics. Pairing requires both conditions and equal initial hashes; summary.strata contains homogeneous statistics. The Stage 7 five-pair pilot established no memory benefit. Read AI_EVALUATION.md before presenting the numbers. Chart image inspection is separate from native Pygame visual approval.
