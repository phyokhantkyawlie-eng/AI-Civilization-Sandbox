# Project architecture

The application entry point is python -m civsandbox. It constructs environment settings, the selected provider, and a Simulation, then starts either the Pygame loop or exact headless ticks.

- world.py owns tile connectivity and BFS. resources.py owns finite bush stock and its mutation journal.
- agents.py owns identity, numeric personality, needs, goals, directed trust and bounded memories. characters.py maps stable IDs to Mira, Ren, Nyra and Kairo.
- decisions.py chooses seeded rule actions. ai.py supplies the local mock adapter and an isolated historical Gemini adapter. The normal factory and CLIs enable only local providers.
- actions.py validates and executes all actions. occupancy.py supplies deterministic occupied-route detours and bounded corridor yielding.
- social.py owns addressed food requests, expiry, transfers, relationship consequences and JSON history persistence.
- simulation.py orchestrates fixed ticks, state validation, logs and optional decision tracing. It has no graphics dependency.
- animation.py interpolates observed tile steps and selects existing idle/walk frames. sprites.py caches normalized assets. rendering.py draws the village, inspector, controls and feedback. feedback.py consumes only numbered committed events.
- experiments.py creates isolated paired trials with fresh providers and RNGs. results.py reads saved outputs using Pandas and generates Matplotlib charts and a decision viewer.

The rendering loop observes simulation steps through a callback. It never writes visual coordinates back into NPC state. Requests receive local information, and memory-disabled access excludes relevant history and accumulated trust. Archived async adapter responses pass offered-choice and latest-state validation before execution. Public explanations are distinct from private model thought parts.

The normal game persists social history on clean shutdown. Experiments use no normal-game persistence path. All four art files are preserved, and assets/inspection documents reproducible extraction and remaining source-art limitations.

The gameplay overhaul adds inventory.py for authoritative item storage, pacing.py for tick-based reservations and completion, and ui_state.py for readable activity/status mapping. The agent food property remains a berries compatibility view. Simulation schedules validated activities, applies the atomic executor once at completion, then publishes committed events. The renderer shows accepted in-progress phases separately from outcomes. F3 exposes the detailed developer panel alongside the default user HUD.
