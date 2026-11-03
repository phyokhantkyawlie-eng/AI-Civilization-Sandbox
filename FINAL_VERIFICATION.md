# Final CSC472 verification — 3 November 2026

## Executed checks

The main-project baseline passed 148 tests with one opt-in live test skipped. Final code passed 149 tests with one skip and zero failures. The added regression reproduces an empty interrupted experiment export that formerly crashed the viewer. The viewer now handles it as a controlled input error. A stale README claim about the absence of the experiment runner was corrected.

Four CLI runs each completed 1,000 ticks: rule-based/default, rule-based/food_shortage, mock/default and mock/food_shortage. Each reported zero API calls and saved history to isolated temporary paths. All civsandbox modules imported. The original four artwork hashes matched the extraction manifest; existing tests checked all 80 normalized frames, foot baselines, four-direction playback and interpolation.

Six fresh food-shortage trials ran with seeds 42–44 and 120 ticks under each memory condition. Initial physical/RNG hashes matched within every pair. Configuration, CSV and JSON exports were read successfully and six Matplotlib chart files were generated. Survival remains unavailable. Experimental outputs are in experiments/final_verification_20261103.

Native macOS Cocoa checks opened both village scenarios, exercised selection, pause/resume, speed changes and clean shutdown using injected Pygame events, and saved screenshots. The Matplotlib results entry point opened seven native windows, including its decision inspector. Screenshots and plots were visually reviewed during QA. Automated event injection verifies handlers, not a student's physical keyboard/mouse delivery during presentation.

## Verification boundaries

Live Gemini was not called. SDK serialization, structured parsing, thought-part filtering, budgets, rate limits, stale replies, network failures and responsiveness were tested offline with replaced transports. Real model access, credentials, quotas, latency and live decision quality require an explicitly authorized live smoke test using a privately configured key and model.

Before presenting, manually check display readability on the classroom projector, physical mouse/keyboard input, screen scaling and window placement. Confirm the selected experiment folder and that the provider label matches the intended demonstration.

## Known limits

Death is not modeled, so survival is unavailable. TALK and speech templates are simplified interactions. Reactions annotate explicit events. Three seed pairs are descriptive pilot data. Gemini timing and sampling can vary. Corridor recovery may temporarily permit shared tiles, and visual offsets can change when occupancy changes. Source artwork has some similar poses and edge fringes.

The game saves social history on clean shutdown, not a full-world save. A crash can lose recent history. Normal event/resource journals retain 8,192 entries; experimental action logs have a finite window sized for the requested duration. Recent decision traces retain 100 entries per trial. Older exports can lack trajectories and traces. Rule-based resource search uses full-map information, while model/mock perception is local, which matters in provider comparisons.

## Delivery

The source archive includes supplied artwork, processed sprites, tests, dependencies, documentation and genuine offline experiment examples. It excludes .env files, normal-game data/, virtual environments, Git internals and caches. API-key-shaped strings are checked before creating the archive. The existing installed environment and normal saved history stay in place.

Run the three modes using DEMO_GUIDE.md. Refer to TROUBLESHOOTING.md for launch and configuration issues, ARCHITECTURE.md for the module map, EXPERIMENT.md for metric denominators, and RESULTS_GUIDE.md for charts and decision inspection.
