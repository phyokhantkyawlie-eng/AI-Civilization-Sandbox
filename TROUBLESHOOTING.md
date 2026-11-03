# Troubleshooting

## Package import error in VS Code

Open the project root, select .venv/bin/python, and use F5 with the supplied module launch configuration. From the activated terminal run python -m civsandbox. Directly executing civsandbox/__main__.py loses its package context.

## Missing packages or artwork

From the project root run python -m pip install -r requirements.txt using Python 3.12. Keep assets/ beside civsandbox/. The sprites loader resolves assets relative to the package location, independent of the terminal directory. Asset preprocessing is optional and is documented in assets/inspection/README.md.

## Legacy API configuration

No key or Google SDK is required. Old AI_PROVIDER=gemini settings resolve to the local rule provider. The CLI accepts only rule-based or mock, and the historical external smoke entry point is disabled. The private .env is retained; do not share or commit it.

## Different results for the same normal-game seed

The normal game restores its configured social history. Use a fresh MEMORY_PATH for a fresh session or use the experiment runner, which isolates every condition and trial. Offline experimental outcomes reproduce with the same code/configuration and fresh seed. Wall-clock duration varies.

## Empty or older results

An interrupted run may have no completed rows. The viewer now reports a controlled error for an empty export. Select a populated experiment directory. Legacy exports without hunger trajectories or decision traces show unavailable data. Generate new offline trials to collect those fields. Survival is unavailable throughout because death is not modeled.

## Plot display or cache problems

Use MPLBACKEND=Agg python -m civsandbox.results experiments/DIRECTORY to export PNGs without a display. Omit Agg and add --show to open native windows. If the font cache directory is unwritable, set MPLCONFIGDIR to a writable directory, for example /tmp/civsandbox-mpl. SDL_VIDEODRIVER=dummy enables automated Pygame rendering tests without a visible window.

## Overlap and saved history

Movement reservations can permit temporary passing after three contested ticks. This prevents corridor deadlocks, while labels separate shared occupants. Exiting cleanly saves the last 20 memories per NPC and directed trust. A corrupt history file is preserved and its failure is shown. Choose a new MEMORY_PATH to begin fresh; retain the old file for diagnosis.
