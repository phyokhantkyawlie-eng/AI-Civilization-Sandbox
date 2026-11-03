"""Reproducible, conservative extraction. Originals are never modified."""
from collections import deque
from pathlib import Path
import json
from PIL import Image, ImageDraw
import hashlib

ROOT = Path(__file__).resolve().parent.parent
NAMES = ('mira', 'nyra', 'kairo', 'ren')
DIRECTIONS = ('down', 'left', 'right', 'up')

def remove_background(image):
    image = image.convert('RGBA')
    # Keep genuine alpha, including Nyra's translucent edges.
    if image.getchannel('A').getextrema()[0] < 255:
        return image
    pixels = image.load()
    w, h = image.size
    seen = set()
    queue = deque([(x, y) for x in range(w) for y in (0, h-1)] +
                  [(x, y) for y in range(h) for x in (0, w-1)])
    while queue:
        x, y = queue.popleft()
        if (x, y) in seen or not (0 <= x < w and 0 <= y < h):
            continue
        seen.add((x, y))
        r, g, b, a = pixels[x, y]
        if min(r, g, b) < 215 or max(r, g, b)-min(r, g, b) > 18:
            continue
        pixels[x, y] = (r, g, b, 0)
        queue.extend(((x-1,y),(x+1,y),(x,y-1),(x,y+1)))
    return image

def extract(image):
    """Grid boundaries derive from actual dimensions, including remainder pixels."""
    w, h = image.size
    frames, records = [], []
    for row in range(4):
        strip = remove_background(image.crop((0, round(row*h/4), w, round((row+1)*h/4))))
        alpha = strip.getchannel('A')
        # Find the actual low-occupancy gutters near each nominal column boundary.
        counts = [sum(alpha.getpixel((x,y)) > 64 for y in range(strip.height)) for x in range(w)]
        edges = [0]
        for col in range(1,5):
            nominal = round(col*w/5)
            edges.append(min(range(nominal-20, nominal+21), key=lambda x: (counts[x], abs(x-nominal))))
        edges.append(w)
        for col in range(5):
            box = (edges[col], round(row*h/4), edges[col+1], round((row+1)*h/4))
            cell = strip.crop((edges[col],0,edges[col+1],strip.height))
            # Discard isolated generation/alpha specks, retaining substantial detached details.
            a = cell.getchannel('A')
            remaining = {(x,y) for y in range(cell.height) for x in range(cell.width) if a.getpixel((x,y)) > 32}
            components = []
            while remaining:
                seed = remaining.pop()
                group, queue = [seed], [seed]
                while queue:
                    x,y = queue.pop()
                    for pt in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                        if pt in remaining:
                            remaining.remove(pt); queue.append(pt); group.append(pt)
                if len(group) >= 40:
                    components.extend(group)
            if not components:
                raise ValueError(f'Empty frame {row}, {col}')
            bounds = (min(x for x,y in components), min(y for x,y in components), max(x for x,y in components)+1, max(y for x,y in components)+1)
            # Bounding box removes distant specks without eroding character edges.
            frames.append(cell.crop(bounds))
            records.append({'row': row, 'column': col, 'cell': box, 'foreground': bounds})
    return frames, records

def build(root=ROOT):
    root = Path(root)
    report = {}
    for name in NAMES:
        source = Image.open(root/'assets'/'characters'/f'{name}.png')
        frames, records = extract(source)
        # One uniform scale for every frame in this character, never per-frame resizing.
        scale = 180 / max(im.height for im in frames)
        output = root/'assets'/'processed'/name
        output.mkdir(parents=True, exist_ok=True)
        for i, frame in enumerate(frames):
            resized = frame.resize((round(frame.width*scale), round(frame.height*scale)), Image.Resampling.LANCZOS)
            canvas = Image.new('RGBA', (160, 200))
            if resized.width > 160:
                raise ValueError('Character exceeds canvas width')
            canvas.alpha_composite(resized, ((160-resized.width)//2, 190-resized.height))
            canvas.save(output/f'{DIRECTIONS[i//5]}_{i%5}.png')
        report[name] = {'sha256': hashlib.sha256((root/'assets'/'characters'/f'{name}.png').read_bytes()).hexdigest(), 'size': source.size, 'mode': source.mode, 'alpha': source.getchannel('A').getextrema() if 'A' in source.getbands() else None, 'scale': scale, 'frames': records}
    (root/'assets'/'inspection').mkdir(parents=True, exist_ok=True)
    (root/'assets'/'inspection'/'frames.json').write_text(json.dumps(report, indent=2))
    contact_sheet(root)
    return report

def contact_sheet(root=ROOT):
    """Show all 80 frames on dark and pale backgrounds, with shared foot lines."""
    for background, color in (("dark", (35, 45, 55)), ("light", (228, 233, 235))):
        sheet = Image.new('RGB', (820, 16*220), color)
        draw = ImageDraw.Draw(sheet)
        for index, name in enumerate(NAMES):
            for row, direction in enumerate(DIRECTIONS):
                y = (index*4+row)*220
                draw.text((5, y+3), f'{name} / {direction} | idle, walk 1-4', fill=(220, 135, 70))
                for col in range(5):
                    frame = Image.open(Path(root)/'assets'/'processed'/name/f'{direction}_{col}.png')
                    sheet.paste(frame, (col*164, y+20), frame)
                    draw.line((col*164, y+210, col*164+160, y+210), fill=(210, 90, 70))
        sheet.save(Path(root)/'assets'/'inspection'/f'contact-{background}.png')


if __name__ == '__main__':
    build()
    print('Extracted 80 frames; metadata and contact sheets: assets/inspection/')
