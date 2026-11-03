"""Reproducible, conservative extraction. Originals are never modified."""
from pathlib import Path
import json
from PIL import Image

ROOT = Path(__file__).resolve().parent
NAMES = ('mira', 'nyra', 'kairo', 'ren')
DIRECTIONS = ('down', 'left', 'right', 'up')

# The prototype remains runnable from its own directory inside the full project.
import sys
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))
from civsandbox.prepare_assets import remove_background, extract

def build():
    report = {}
    for name in NAMES:
        source = Image.open(ROOT/'assets'/'characters'/f'{name}.png')
        frames, records = extract(source)
        # One uniform scale for every frame in this character, never per-frame resizing.
        scale = 180 / max(im.height for im in frames)
        output = ROOT/'assets'/'processed'/name
        output.mkdir(parents=True, exist_ok=True)
        for i, frame in enumerate(frames):
            resized = frame.resize((round(frame.width*scale), round(frame.height*scale)), Image.Resampling.LANCZOS)
            canvas = Image.new('RGBA', (160, 200))
            if resized.width > 160:
                raise ValueError('Character exceeds canvas width')
            canvas.alpha_composite(resized, ((160-resized.width)//2, 190-resized.height))
            canvas.save(output/f'{DIRECTIONS[i//5]}_{i%5}.png')
        report[name] = {'size': source.size, 'mode': source.mode, 'alpha': source.getchannel('A').getextrema() if 'A' in source.getbands() else None, 'scale': scale, 'frames': records}
    (ROOT/'assets'/'inspection.json').write_text(json.dumps(report, indent=2))
    return report

if __name__ == '__main__':
    build()
    print('Extracted 80 frames; inspection metadata: assets/inspection.json')
