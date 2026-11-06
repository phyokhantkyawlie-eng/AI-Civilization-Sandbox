# Experiment runner — offline release

Use python -m civsandbox.experiments. Providers: rule-based and mock. Scenarios: normal_survival (default-world alias), food_shortage, social_memory (paired shortage comparison), hunting_decisions (seven initial profiles), plus default for compatibility. --runs chooses seeds seed…seed+runs−1 per stratum; --ticks chooses .25-second ticks. --memory-mode paired/on/off selects conditions. --profile applies only to hunting_decisions; other uses fail rather than silently ignoring it.

```bash
python -m civsandbox.experiments --provider rule-based --scenario social_memory --runs 5 --ticks 12000 --seed 7 --memory-mode paired
python -m civsandbox.experiments --scenario hunting_decisions --profile exhausted --runs 5 --ticks 2400 --seed 7 --memory-mode on
```

Each invocation creates a timestamped folder under experiments/ or --output-root. configuration.json records algorithm/provider/model=None, parameters, seeds and profiles. summary.json contains genuine rows, grouped statistics and paired differences; trials.csv exports the same rows. Failed rows retain an error type without sensitive exception text, and later trials continue. Exports update after each trial and on interruption. Summary replacement is atomic; an interrupted CSV may need regeneration from the intact summary.

Trials use fresh Observer agents/providers/plans/caches/RNGs, neutral trust, empty history and memory_path=None. Private .env/social/world saves are not loaded. Fingerprints include physical agents/personality/items, terrain/resources/station, clocks/settings and RNGs, excluding the treatment flag. Pairs require completed ON/OFF matches with identical hashes and matching scenario/profile/seed. D profiles do not overwrite one another in pairing.

Whole-trial counters stream independently of the 4,096-event engine window. Needs/activity totals use every completed NPC tick; trajectories cap at 1,001 points. No renderer or real-world sleep is needed. Legacy tick_seconds and hidden call-budget compatibility inputs cannot activate external behavior. External providers are rejected before trial construction; no SDK/key is required.

AI_EVALUATION.md defines every denominator and reports actual results. Undefined rates are null/unavailable. Means/sample SD use available completed observations. Approximate normal 95% mean intervals require at least five homogeneous seed-level observations; mixed profile/scenario pooled intervals are withheld. Paired differences are ON minus OFF. No significance test or universal memory benefit is claimed.

NPC death is absent: survival_rate remains null. Operational availability is separately labeled. Requested cooperation excludes voluntary offers and unresolved requests. Activity labels are exclusive per NPC tick; hunt time includes pursuit. Food conservation checks actual items. Current API-call counts are zero. Historical exports from earlier metric/algorithm versions must not be pooled as current trials.

Batch RAM/file size scales with the requested output-row count, although per-trial logs/traces/trajectories/ID tracking are bounded. Generated experiments/ and artifacts/ remain ignored. The final 55 executions include repeated deterministic B/C ON controls; they are not 55 independent observations of one effect.
