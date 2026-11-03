# AI Civilization Sandbox — Phase 1A

Manual character animation only. Independent of the existing simulation and API dependencies.

## macOS setup and launch

```sh
cd "/Users/phyokhantkyaw/Phyo-Workspace/AI Civilization Sandbox/phase1a"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Select Mira / Nyra / Kairo / Ren with 1 / 2 / 3 / 4. WASD or arrows move; diagonal speed is normalized. Escape exits. Default animation speed is 8 FPS; use `python app.py --fps 10` to change it.

## Inspecting artwork

```sh
python app.py --inspect
```

Tab toggles inspector. Up/down selects direction. Left/right steps idle and four walk frames. Space toggles playback. B cycles checkerboard, dark, and white backgrounds. Red lines mark the shared foot anchor. All five frames appear together and the selected frame appears enlarged below. Character selection remains available.

Original sheets are preserved byte-for-byte in `assets/characters/`. Derived frames are in `assets/processed/`. Regenerate with `python preprocess.py`. Delete the processed directory before launching if you want an automatic rebuild. `assets/inspection.json` records original dimensions, modes, alpha ranges, measured crop boundaries, and scale. `assets/all_frames.png` is the reviewed contact sheet.

## Actual source inspection

All four originals are 887 × 1774. Mira, Kairo, and Ren are RGB with baked pale/checker backgrounds. Nyra is RGBA with alpha ranging 0–255. Character identities match the supplied descriptions.

Rows are DOWN, LEFT, RIGHT, UP; columns are idle, then walks 1–4. Extraction derives row boundaries from image height, searches for low-occupancy column gutters near the expected divisions, and flood-removes only exterior-connected near-neutral pale pixels (minimum channel 215, channel spread at most 18). Enclosed white details are preserved. Existing alpha is retained. Significant connected foreground components define crop bounds so isolated alpha specks cannot distort alignment. The algorithm is tailored to these inspected sheets; review new sheets before reuse.

Each character uses one uniform scale across all 20 frames, targeting a maximum height of 180 pixels. Frames share a transparent 160 × 200 canvas, horizontal center, and baseline at y=190. Proportions remain unchanged. This suppresses crop/scale jitter; source pose differences and repeated-looking AI-generated walk poses remain. No artwork is redesigned. Very faint source edge halos may remain visible on dark inspection backgrounds.

## Modules

- `preprocess.py`: inspection, conservative background cleanup, extraction, normalization.
- `animator.py`: reusable direction and time-based animation indexing, independent of Pygame.
- `app.py`: input, movement, drawing, inspector, and application lifecycle.
- `tests/test_prototype.py`: extraction against all originals, anchoring, alpha preservation, timing, looping, idle/facing, and validation.

## Verification

```sh
python -m unittest discover -s tests -v
python app.py --smoke-test
```

The smoke test uses SDL dummy video/audio and renders all four characters in all directions, exercising idle, walk, inspector rendering, and clean shutdown. It does not validate physical keyboard delivery or a visible macOS window. Perform that final interactive check with `python app.py`.

Phase 1A intentionally contains no AI, API calls, autonomous NPC behavior, needs, resources, memory, relationships, or map simulation.

The prototype now reuses the main package’s identical extraction helpers. Keep it within the full project folder when launching. Its local build output layout and animation behavior are preserved. A pre-cleanup preprocessing backup is in delivery/overhaul_backup/phase1a_preprocess.py.
