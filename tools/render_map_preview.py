"""Render authoritative OFFLINE map data with the same atlas. Not a Godot screenshot.
Optional developer utility; requires Pillow only when regenerating the preview.
"""
from pathlib import Path
import json
import sys
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine.world import World
from engine.storage import Store
from engine.director import Director

def main():
    w=World(Store(':memory:'))
    w.start('海边的永雨城，游荡的旅人沿着灯火寻找记忆。')
    d=Director(w);d.configure({'offline':True});d.cfg['cooldown']=0
    for _ in range(3):d.step()
    r=w.region();tile=24;canvas=Image.new('RGBA',(r['width']*tile,r['height']*tile),'#142235')
    tiles=Image.open(ROOT/'assets/tiles.png').convert('RGBA');atlas=Image.open(ROOT/'assets/atlas.png').convert('RGBA');defs=json.loads((ROOT/'assets/atlas.json').read_text())
    biomes=['forest','coast','snow','desert','ruins','industrial','dream'];row=biomes.index(r['biome'])
    for y,line in enumerate(r['tiles']):
        for x,typ in enumerate(line):
            variant=(x*7+y*13)%2;sx=(typ*2+variant)*16
            image=tiles.crop((sx,row*16,sx+16,row*16+16)).resize((tile,tile),Image.Resampling.NEAREST)
            canvas.alpha_composite(image,(x*tile,y*tile))
    objects=[(e['y'],e['x'],e['kind']) for e in r['props']]
    for e in r['entities']:
        kind=e['kind'];name='portal' if kind=='exit' else f'npc_{e["appearance"]}_0' if kind=='npc' else e['monster'] if kind=='enemy' else kind
        objects.append((e['y'],e['x'],name))
    objects.append((w.state['player']['y'],w.state['player']['x'],'hero_0'))
    for y,x,name in sorted(objects):
        sx,sy,sw,sh=defs[name]['rect'];im=atlas.crop((sx,sy,sx+sw,sy+sh));im=im.resize((int(sw*1.5),int(sh*1.5)),Image.Resampling.NEAREST)
        canvas.alpha_composite(im,(int((x+.5)*tile-im.width/2),int((y+1)*tile-im.height)))
    # A visible caption explicitly distinguishes this reference render from native-client testing.
    frame=Image.new('RGB',(1248,940),'#0c1421');frame.paste(canvas.convert('RGB'),(0,52))
    draw=ImageDraw.Draw(frame)
    try:font=ImageFont.truetype('DejaVuSans.ttf',18)
    except OSError:font=ImageFont.load_default()
    draw.text((22,15),'EVERWEAVE  /  offline map-data preview',fill='#e7c795',font=font)
    draw.text((22,916),'Original pixel atlas + deterministic region compiler. Not a Godot runtime screenshot.',fill='#a0b5c8',font=font)
    out=ROOT/'docs/map-preview.png';frame.save(out);w.store.close();print(out)
if __name__=='__main__':main()
