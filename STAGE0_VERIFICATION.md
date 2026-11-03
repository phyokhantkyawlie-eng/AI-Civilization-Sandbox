# Stage 0 verification — 2026-11-03

Main project: `/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox`.

## Executed checks

| Check | Actual result |
| --- | --- |
| Unmodified baseline pytest | 161 passed, 1 skipped; two sandbox cache-write warnings |
| Final full pytest | 167 passed, 1 skipped, 0 failed, 22.11 seconds; cache disabled |
| Historical prototype unittest rerun | 5 passed (also collected by full pytest) |
| Headless default / rules / seed 42 | 1,000 ticks; four named NPCs; 40 gathers, 32 eats, 433 rests; zero API calls |
| Headless shortage / rules / seed 42 | 1,000 ticks; 2 requests, 1 share, 1 refusal; zero API calls |
| Headless shortage / mock / seed 42 | 1,000 ticks; 9 requests, 2 shares, 7 refusals; zero API calls; mock is not genuine model output |
| Sprite integrity and loading | Existing tests verified original hashes, 80 RGBA frames, mapping, common foot baseline and Pygame loading |
| Animation/UI contracts | Dummy SDL tests passed for direction rows, idle/walk, interpolation, pause/resume, speed, selection and clean shutdown |
| Recovery archive | ZIP integrity verified; 284 pre-change files |

Final suite command (from main project):

```bash
PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/civsandbox-stage0-mpl .venv/bin/python -m pytest -p no:cacheprovider -q
```

The full suite prohibits Python socket connections, UDP sends and DNS requests; attempted access fails even when caught by adapter fallback. Headless checks used startup guards that also prohibited Google SDK imports, with fresh temporary social history per run. Both local providers and the default CLI were covered by subprocess regression tests. No live API request or package download was made. The installed historical SDK remains untouched; its two serialization tests use fake HTTP and become skips when it is absent. The historical live test always skips.

The final 1,000-tick counts above are observed completed actions, not scripted success criteria or a scientific batch. Fresh seed/config/history are needed to reproduce them; normal sessions may restore old social history. No policy or timing changes were made in this stage.

## Changes and limitations

Normal defaults and factory/CLI selection are offline. Legacy external-provider configuration cannot enable network requests through those entry points. `.env.example` and required dependencies are local-only; the old smoke command is disabled. A test order dependency was fixed by initializing dummy SDL drivers in test setup. Existing artwork, inventory, pacing, social history structures and provider interface remain intact.

Native interactive visual QA was not performed. Use the manual checklist in DEVELOPMENT_GUIDE.md. General action utility scoring, health/death, wildlife, cooking, Participant Mode and physical game saves remain future work. No such features were introduced.

Pre-change Git recovery commit: `fcfbfbf`. Archive: `delivery/offline_stage0_before.zip`. `.env`, private saved histories and generated output are excluded from Git. The existing private environment and saved-data file fingerprints were checked after verification; no contents changed.
