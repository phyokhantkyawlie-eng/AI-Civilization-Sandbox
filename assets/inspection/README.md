# Character artwork inspection

The four source files in `assets/characters/` are byte-for-byte copies of the supplied `_walk.png` files. Originals have not been edited. `frames.json` records their SHA-256 hashes, dimensions, modes, crop boundaries, and one uniform scale per character.

All sheets measure **887 × 1774**, with five columns and four rows. Rows are down, left, right, up. Column zero is idle; columns one through four are walk frames. Rounded row divisions handle fractional cell heights, and column boundaries use low-occupancy gutters near the nominal grid. Cells are not assumed to be 512 × 512.

Mira, Kairo, and Ren are **RGB** with baked pale/checkerboard backgrounds. Nyra is **RGBA** with alpha spanning 0–255. Exterior-connected near-neutral pale pixels are flood-removed from RGB rows; enclosed light artwork is retained. Nyra's genuine alpha is preserved. Significant foreground components determine bounds, preventing distant isolated specks from shifting the crop.

Each character receives one scale for all 20 frames, with maximum artwork height 180 pixels on transparent 160 × 200 canvases. All frames share the same bottom-center anchor `(80, 190)`. Runtime loading uniformly scales each entire canvas once to 40 × 50, anchored at `(20, 48)`. Frames never resize during playback. Natural limb motion and source pose differences remain.

Review `contact-dark.png` and `contact-light.png`: each contains all 80 labeled frames at the shared baseline. The main application uses exactly these derived frames, without importing or launching the separate existing `phase1a` prototype.

Remaining source-art limitations:

- Faint pale/color fringes can remain at antialiased edges, especially Nyra on contrasting backgrounds.
- Several poses look similar, particularly neutral and middle walk frames. The files supply four walk columns, but they are not uniformly distinct handcrafted animation poses.
- Source silhouettes and limb positions vary slightly. A fixed canvas, fixed scale, centered bounds, and common foot baseline prevent crop/scale jitter; the artwork itself is not redrawn or retouched.

Regenerate reproducibly from the preserved originals:

```bash
python -m civsandbox.prepare_assets
```

Pillow is used for this explicit preprocessing step. The game loads committed PNG frames through Pygame; it does not preprocess assets every launch.
