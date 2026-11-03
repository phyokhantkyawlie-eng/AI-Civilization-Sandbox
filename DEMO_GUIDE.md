# CSC472 presentation plan

Suggested running time is 7 minutes 20 seconds. Prepare the virtual environment and open the three demonstration modes before presenting. All commands start from the project root with source .venv/bin/activate.

## 0:00–0:40 · Introduce the sandbox

Explain that four autonomous agents share a small resource-limited village. The research question asks whether access to social memory changes cooperation and decision-making. Identify Mira, Nyra, Kairo and Ren by their original green, purple, blue and red artwork.

## 0:40–1:20 · Explain the architecture

Use ARCHITECTURE.md. Show the pipeline from observations through a provider, a structured action, validation, execution and world updates. Explain that the fixed-tick simulation runs separately from graphics and can run headlessly.

## 1:20–2:20 · Mode A, civilization and needs

```bash
MEMORY_PATH=/tmp/csc472-demo-a.json python -m civsandbox --provider rule-based --scenario default --seed 42
```

Use a new history filename for a fresh rehearsal. Point out autonomous BFS movement, food gathering, eating and resting. Pause with Space, change speed with arrows or buttons, and click a character to inspect needs and personality. Describe hunger/energy management as survival-related behavior and disclose that death is not modeled.

## 2:20–3:30 · Mode B, food shortage and social decisions

```bash
MEMORY_PATH=/tmp/csc472-demo-b.json python -m civsandbox --provider rule-based --scenario food_shortage --seed 42
```

Point out unequal food and hunger, requests, responses, food transfers or refusals, trust changes and attributed speech bubbles. A refusal is a valid outcome. Present what the agents actually do during the run rather than promising a particular share. Speech templates and reaction labels are explicitly attributed to rules/events.

## 3:30–4:20 · Local decision-making

Show decisions.py: needs priorities, persistent goals, BFS, and personality/trust-weighted social willingness. Show the Action interface and shared validator. Explain that the game is offline-first; mock means an offline test adapter, never a real model. External adapters are archived and not enabled by normal launch commands.

## 4:20–5:00 · Social memory

Use the Trust and Memory inspector tabs. Explain directed relationships, relevant bounded recall and MEMORY_ENABLED. Historical audit values can be collected even when the provider cannot recall them. Each experiment trial begins with neutral relationships, empty history and a fresh provider.

## 5:00–6:30 · Mode C, measured results

```bash
python -m civsandbox.results experiments/final_verification_20261103 --show
```

Show cooperation, shares/refusals, hunger trajectories and directed trust. Use the trial table and recent-decision slider. State the provider, three seed pairs and 120-tick duration. Explain per-run variation and standard-deviation bands. Survival is marked unavailable. This is a small offline pilot, not a strong causal conclusion about model intelligence.

To regenerate a fresh paired pilot:

```bash
python -m civsandbox.experiments --provider rule-based --runs 3 --ticks 120 --seed 42 --scenario food_shortage
```

## 6:30–7:20 · Limits and future work

Discuss the single village scenario, four fixed personalities, stable NPC processing order, temporary corridor overlap, small samples and absent death mechanics. Future work could evaluate more seeds/scenarios and more complete local utility scoring. End with the executed verification results in FINAL_VERIFICATION.md.

The gameplay overhaul adds paced activities, a normal needs/inventory panel and F3 developer details. Allow several seconds to gather/eat and complete social exchanges. Click bushes to show stock/regrowth. Stored experiment examples and the Stage 8 ZIP are pre-overhaul snapshots. Explain their code version when presenting them; no new research experiment was executed during the overhaul.
