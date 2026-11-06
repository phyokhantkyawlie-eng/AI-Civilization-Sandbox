"""Optional 4-column idle extraction; never writes walking assets.

Inspected inputs use four rows and four stationary poses. Counts are explicit,
not inferred from dimensions. Originals (including their alpha) remain intact.
"""
from collections import deque
import hashlib
import json
from pathlib import Path
from statistics import median
from PIL import Image, ImageDraw
from .prepare_assets import ROOT, NAMES, DIRECTIONS

IDLE_COLUMNS = {name: 4 for name in NAMES}


def clean_idle_cell(cell, pale_background=False):
    cell = cell.convert('RGBA')
    if not pale_background:
        return cell
    # Ren has a baked pale background despite having an alpha channel.
    pixels = cell.load()
    w, h = cell.size
    queue = deque([(x,y) for x in range(w) for y in (0,h-1)] + [(x,y) for y in range(h) for x in (0,w-1)])
    seen = set()
    while queue:
        x,y = queue.popleft()
        if not (0 <= x < w and 0 <= y < h) or (x,y) in seen:
            continue
        seen.add((x,y))
        r,g,b,a = pixels[x,y]
        if min(r,g,b) < 195 or max(r,g,b)-min(r,g,b) > 28:
            continue
        pixels[x,y] = (r,g,b,0)
        queue.extend(((x-1,y),(x+1,y),(x,y-1),(x,y+1)))
    return cell


def foreground_bounds(cell):
    """Measure solid artwork, excluding distant translucent residue; keep edge padding."""
    alpha = cell.getchannel('A')
    remaining = {(x,y) for y in range(cell.height) for x in range(cell.width) if alpha.getpixel((x,y)) >= 128}
    kept = []
    while remaining:
        point = remaining.pop()
        group, queue = [point], [point]
        while queue:
            x,y = queue.pop()
            for pt in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if pt in remaining:
                    remaining.remove(pt); queue.append(pt); group.append(pt)
        if len(group) >= 40:
            kept.extend(group)
    if not kept:
        raise ValueError('Idle cell contains no substantial artwork')
    return (max(0,min(x for x,y in kept)-2), max(0,min(y for x,y in kept)-2),
            min(cell.width,max(x for x,y in kept)+3), min(cell.height,max(y for x,y in kept)+3))


def extract_idle(source, columns, *, pale_background=False):
    if type(columns) is not int or not 1 <= columns <= 32:
        raise ValueError('Explicit idle column count required')
    frames, records = {}, []
    w,h = source.size
    cleaned = clean_idle_cell(source, pale_background)
    alpha = cleaned.getchannel('A')
    row_counts = [sum(alpha.getpixel((x,y)) >= 128 for x in range(w)) for y in range(h)]
    row_edges = [0]
    for row in range(1,4):
        nominal = round(row*h/4)
        row_edges.append(min(range(nominal-40,nominal+41),key=lambda y:(row_counts[y],abs(y-nominal))))
    row_edges.append(h)
    for row,direction in enumerate(DIRECTIONS):
        frames[direction] = []
        top,bottom = row_edges[row],row_edges[row+1]
        strip = cleaned.crop((0,top,w,bottom))
        alpha = strip.getchannel('A')
        counts = [sum(alpha.getpixel((x,y)) >= 128 for y in range(strip.height)) for x in range(w)]
        edges = [0]
        radius = min(60, w//columns//4)
        for column in range(1,columns):
            nominal = round(column*w/columns)
            edges.append(min(range(nominal-radius,nominal+radius+1),key=lambda x:(counts[x],abs(x-nominal))))
        edges.append(w)
        for column in range(columns):
            box = (edges[column],top,edges[column+1],bottom)
            cell = strip.crop((edges[column],0,edges[column+1],strip.height))
            bounds = foreground_bounds(cell)
            # Reject a grid that cuts into solid art rather than silently clipping it.
            a = cell.getchannel('A')
            borders = [sum(a.getpixel((x,y)) >= 128 for y in range(cell.height)) for x in (0,cell.width-1)]
            borders += [sum(a.getpixel((x,y)) >= 128 for x in range(cell.width)) for y in (0,cell.height-1)]
            if max(borders) > 5:
                raise ValueError(f'Artwork reaches cell boundary: {direction}/{column}; review grid')
            crop = cell.crop(bounds)
            frames[direction].append(crop)
            records.append({'direction':direction,'column':column,'cell':box,'foreground':bounds})
    return frames, records


def build_idle(root=ROOT):
    root = Path(root)
    report = {}
    for name in NAMES:
        path = root/'assets'/'characters'/f'{name}_idle.png'
        if not path.exists():
            report[name] = {'status':'missing; static fallback'}
            continue
        with Image.open(path) as source:
            frames, records = extract_idle(source, IDLE_COLUMNS[name], pale_background=name=='ren')
            alpha = source.getchannel('A').getextrema() if 'A' in source.getbands() else None
            info = {'character':name,'source':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'size':source.size,'mode':source.mode,'alpha':alpha,
                    'counts':{d:len(frames[d]) for d in DIRECTIONS},'frames':records}
        # Match existing walking idle height with a single scale for the whole sheet.
        walk = Image.open(root/'assets'/'processed'/name/'down_0.png')
        target_height = walk.getbbox()[3]-walk.getbbox()[1]
        scale = target_height/median(frame.height for frame in frames['down'])
        info['scale'] = scale
        output = root/'assets'/'processed'/name/'idle'
        for direction in DIRECTIONS:
            (output/direction).mkdir(parents=True,exist_ok=True)
            for i,frame in enumerate(frames[direction]):
                # Use the boot region, avoiding hats/bags shifting the center of the canvas.
                mask = frame.getchannel('A').point(lambda a: 255 if a >= 128 else 0)
                bottom = mask.crop((0,round(frame.height*.86),frame.width,frame.height)).getbbox()
                anchor_x = (bottom[0]+bottom[2])/2 if bottom else frame.width/2
                size = (round(frame.width*scale),round(frame.height*scale))
                resized = frame.resize(size,Image.Resampling.LANCZOS)
                x,y = round(80-anchor_x*scale),190-size[1]
                if x < 0 or y < 0 or x+size[0] > 160:
                    raise ValueError(f'Idle art does not fit shared canvas: {name}/{direction}/{i}')
                canvas = Image.new('RGBA',(160,200))
                canvas.alpha_composite(resized,(x,y))
                canvas.save(output/direction/f'{i}.png')
        (output/'manifest.json').write_text(json.dumps(info,indent=2))
        report[name] = info
    inspection = root/'assets'/'inspection'
    inspection.mkdir(parents=True,exist_ok=True)
    (inspection/'idle-frames.json').write_text(json.dumps(report,indent=2))
    for theme,color in (('dark',(35,45,55)),('light',(228,233,235))):
        sheet=Image.new('RGB',(820,16*220),color)
        draw=ImageDraw.Draw(sheet)
        for n,name in enumerate(NAMES):
            for row,direction in enumerate(DIRECTIONS):
                y=(n*4+row)*220
                draw.text((5,y+3),f'{name} / {direction}: WALK idle reference | IDLE 0-3',fill=(210,130,70))
                for col in range(5):
                    path=(root/'assets'/'processed'/name/f'{direction}_0.png' if col==0 else root/'assets'/'processed'/name/'idle'/direction/f'{col-1}.png')
                    if path.exists():
                        frame=Image.open(path)
                        sheet.paste(frame,(col*164,y+20),frame)
                    draw.line((col*164,y+210,col*164+160,y+210),fill=(210,90,70))
        sheet.save(inspection/f'idle-contact-{theme}.png')
    return report

if __name__=='__main__':
    build_idle()
    print('Optional idle frames and inspection sheets prepared; walking assets unchanged.')
