"""Generate the project's original pixel art and sound assets. Build-time only: Pillow.
No downloaded art, no font files, and no image-model dependency at runtime.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import random
import struct
import wave
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets'
OUT.mkdir(exist_ok=True)
PALETTES = [
    ('#244e46','#39715a','#578869','#958266','#ae9876','#214951','#3b6d78','#405654'),
    ('#50665a','#647e68','#83987b','#b8a579','#d0c391','#285c72','#3f8393','#536976'),
    ('#9baabb','#b9c7ce','#d7e4df','#8992a4','#b0b6bf','#42718a','#719bb3','#647487'),
    ('#a88d63','#c0a573','#d9bc80','#917456','#ac9068','#3b7673','#58a29b','#806957'),
    ('#464d59','#606776','#737e87','#757482','#95929b','#34475e','#47667e','#49434f'),
    ('#3a494e','#4b5d5e','#627473','#6d6e66','#92907c','#26404c','#3c6470','#46565e'),
    ('#493a65','#624b82','#87679d','#87729d','#aa8daf','#3e3776','#705fa8','#463558'),
]
TILES = Image.new('RGBA',(160,112))
for row,p in enumerate(PALETTES):
    for typ in range(5):
        for var in range(2):
            im=Image.new('RGBA',(16,16)); d=ImageDraw.Draw(im); rng=random.Random(row*100+typ*10+var)
            if typ==0:
                d.rectangle((0,0,15,15),fill=p[0])
                for _ in range(12):
                    x,y=rng.randrange(16),rng.randrange(16)
                    d.line((x,y,x+1,y),fill=p[rng.choice((1,1,2))])
                if var:
                    for x,y in ((3,5),(11,11)): d.line((x,y,x,y-2),fill=p[2]); d.point((x+1,y-1),fill=p[1])
            elif typ==1:
                d.rectangle((0,0,15,15),fill=p[3])
                for _ in range(15):
                    x,y=rng.randrange(16),rng.randrange(16); d.rectangle((x,y,x+1,y),fill=p[4])
                if var: d.line((2,5,5,5),fill=p[0]); d.line((9,12,12,12),fill=p[0])
            elif typ==2:
                d.rectangle((0,0,15,15),fill=p[5])
                for x,y in ((2,3),(10,8),(0,13)): d.line((x+var*2,y,x+4+var*2,y),fill=p[6])
            elif typ==3:
                d.rectangle((0,0,15,15),fill=p[7]); d.line((0,0,15,0),fill=p[2]); d.line((0,8,15,8),fill=p[0]); d.line((7,0,7,7),fill=p[0]); d.line((2,8,2,15),fill=p[0]); d.line((13,8,13,15),fill=p[0]); d.point((4,3),fill=p[1]); d.point((10,12),fill=p[2])
            else:
                d.rectangle((0,0,15,15),fill='#4c4243')
                for y in range(0,16,4):
                    d.rectangle((1,y,14,y+2),fill='#947653'); d.line((2,y,12,y),fill='#b29165'); d.point((3,y+1),fill='#51433e'); d.point((12,y+1),fill='#51433e')
                d.line((0,0,0,15),fill='#c1a471');d.line((15,0,15,15),fill='#c1a471')
            TILES.alpha_composite(im,((typ*2+var)*16,row*16))
TILES.save(OUT/'tiles.png')

art={}
def canvas(w,h):
    im=Image.new('RGBA',(w,h));return im,ImageDraw.Draw(im)
def register(name,im):art[name]=im

coats=['#5c9ca2','#b87961','#89966b','#aa9255','#8881b3','#739dad','#b5708a','#9295a8']
for n in range(9):
    for frame in range(3):
        im,d=canvas(20,28); skin='#ecc99a'; hair=['#292f42','#735140','#d3c29a','#353b46'][n%4]; coat='#d0a970' if n==8 else coats[n]
        step=[0,1,-1][frame]; boot='#242c3e'
        d.ellipse((4,23,16,27),fill=(5,13,25,85))
        d.rectangle((6,20,9,24+max(0,step)),fill=boot); d.rectangle((11,20,14,24+max(0,-step)),fill=boot)
        d.rectangle((5,11,15,20),fill='#202d42');d.rectangle((6,11,14,19),fill=coat)
        d.rectangle((3,12,5,17),fill=coat);d.rectangle((15,12,17,17),fill=coat)
        d.rectangle((4,18,5,20),fill=skin);d.rectangle((15,18,16,20),fill=skin)
        d.rectangle((7,12,8,19),fill='#ebd3a2');d.rectangle((5,19,15,21),fill='#394653')
        d.rectangle((6,4,14,11),fill=skin);d.rectangle((5,3,15,7),fill=hair);d.rectangle((6,2,13,5),fill=hair)
        d.rectangle((5,5,6,9),fill=hair);d.rectangle((14,5,15,9),fill=hair)
        d.point((8,8),fill='#26384a');d.point((12,8),fill='#26384a');d.line((9,11,11,11),fill='#bd9379')
        if n==8:
            d.rectangle((5,11,15,13),fill='#6ec5bb');d.rectangle((14,13,16,18),fill='#51a3a0');d.line((17,12,17,23),fill='#d8e6d3')
        else:
            d.rectangle((5,1,14,3),fill=coat);d.line((3,4,16,4),fill=coat)
        register(('hero' if n==8 else f'npc_{n}')+f'_{frame}',im)

for name in ('slime','wolf','sentinel','wisp','mimic'):
    im,d=canvas(32,32);d.ellipse((3,24,29,31),fill=(4,10,25,80))
    if name=='slime':
        d.ellipse((3,10,29,28),fill='#1c546c');d.ellipse((4,9,27,25),fill='#58aaad');d.ellipse((7,10,17,15),fill='#afe6cf');d.rectangle((10,18,12,21),fill='#233c55');d.rectangle((20,18,22,21),fill='#233c55');d.line((14,23,18,23),fill='#c0e5cf')
    elif name=='wolf':
        d.polygon([(2,18),(7,10),(14,8),(23,12),(29,18),(26,24),(7,25)],fill='#87909f');d.polygon([(6,13),(4,3),(12,10)],fill='#c8bdb9');d.polygon([(19,10),(27,3),(25,17)],fill='#c8bdb9');d.rectangle((8,21,11,28),fill='#454b68');d.rectangle((23,22,26,28),fill='#454b68');d.rectangle((11,14,14,16),fill='#f2c568');d.rectangle((22,14,25,16),fill='#f2c568');d.rectangle((15,20,20,24),fill='#333b53');d.line((16,23,19,23),fill='#dbd2c6')
    elif name=='sentinel':
        d.rectangle((9,7,22,21),fill='#5d6680');d.rectangle((11,3,21,12),fill='#adb1bc');d.rectangle((9,7,23,10),fill='#363f59');d.line((12,8,20,8),fill='#f5b976');d.rectangle((5,12,9,23),fill='#9aa0ad');d.rectangle((24,12,27,23),fill='#9aa0ad');d.rectangle((9,22,13,29),fill='#aeb2bf');d.rectangle((19,22,23,29),fill='#aeb2bf');d.rectangle((14,12,19,19),fill='#c39670');d.rectangle((2,10,4,29),fill='#e0d2aa');d.line((1,17,6,17),fill='#9d7780')
    elif name=='wisp':
        d.polygon([(15,1),(20,11),(28,14),(23,25),(18,29),(14,25),(8,27),(3,18),(9,8)],fill='#756aa3');d.polygon([(15,6),(19,15),(23,19),(18,26),(10,23),(8,16)],fill='#acb3e3');d.rectangle((10,16,12,18),fill='#31385b');d.rectangle((19,16,21,18),fill='#31385b');d.point((5,5),fill='#d3f3ed');d.point((28,4),fill='#d3f3ed')
    else:
        d.rectangle((4,9,28,25),fill='#59455b');d.rectangle((5,8,27,16),fill='#cba279');d.rectangle((6,18,26,24),fill='#9b754f');d.rectangle((4,15,28,19),fill='#242637')
        for x in range(7,28,5):d.polygon([(x,16),(x+3,16),(x+1,21)],fill='#ead8bd')
        d.rectangle((9,11,11,13),fill='#f2896f');d.rectangle((21,11,23,13),fill='#f2896f')
    register(name,im)

im,d=canvas(40,48);d.ellipse((6,38,36,47),fill=(4,12,20,70));d.rectangle((18,23,23,43),fill='#624e42');d.rectangle((20,25,23,39),fill='#90674d')
for bounds,fill in [((3,17,35,36),'#204c47'),((0,11,31,28),'#2e6250'),((9,4,38,29),'#3c7457'),((8,1,31,19),'#578a64')]: d.ellipse(bounds,fill=fill)
for x,y in ((11,9),(17,5),(24,12),(6,21),(27,20),(15,24)):d.line((x,y,x+4,y),fill='#719875')
register('tree',im)
im,d=canvas(24,16);d.ellipse((0,3,23,15),fill='#295848');d.ellipse((3,0,20,12),fill='#4e8060');d.line((6,4,11,4),fill='#7aa779');register('bush',im)
im,d=canvas(24,18);d.polygon([(2,14),(5,4),(14,1),(22,8),(21,16)],fill='#7a8290');d.polygon([(5,4),(14,1),(19,5),(11,8)],fill='#adb1ae');d.line((2,15,20,17),fill='#46566a');register('rock',im)
im,d=canvas(16,16)
for x,y,c in ((4,7,'#eccb96'),(10,3,'#aa9fd3'),(12,12,'#d99caa')):
 d.line((x,y,x,y+3),fill='#5a9772');d.rectangle((x-1,y-1,x+1,y+1),fill=c);d.point((x,y),fill='#f4e9b6')
register('flower',im)
im,d=canvas(64,64);d.ellipse((5,51,59,63),fill=(3,10,23,70));d.rectangle((10,25,53,55),fill='#6d6261');d.rectangle((13,27,50,52),fill='#b2a085');d.rectangle((14,33,50,35),fill='#716456');d.rectangle((14,47,50,50),fill='#80705b');d.polygon([(4,30),(14,10),(48,10),(59,30)],fill='#3e4155')
for y in range(12,30,4):
 offset=int((30-y)/2); d.rectangle((5+offset,y,58-offset,y+2),fill='#976779' if (y//4)%2 else '#b27781')
d.line((3,30,60,30),fill='#d8a2a0');d.rectangle((40,3,48,15),fill='#77727e');d.line((39,3,49,3),fill='#b4aca8');d.rectangle((26,38,36,55),fill='#403846');d.rectangle((28,40,34,55),fill='#75604b');d.point((33,47),fill='#ecc985')
for x in (16,42):
 d.rectangle((x,38,x+7,44),fill='#484559');d.rectangle((x+1,39,x+6,43),fill='#e8c78c');d.line((x+4,39,x+4,43),fill='#8a7564')
register('house',im)
im,d=canvas(40,64);d.ellipse((3,53,37,62),fill=(3,10,23,60));d.rectangle((8,13,32,56),fill='#717888');d.rectangle((11,14,28,55),fill='#9297a0')
for y in range(16,55,7):d.line((9,y,31,y),fill='#5d687c');d.line((17+(y//7%2)*6,y,17+(y//7%2)*6,y+6),fill='#717888')
d.polygon([(3,17),(20,0),(37,17)],fill='#6b6084');d.line((3,17,37,17),fill='#b8a3b9');d.rectangle((16,44,25,57),fill='#374256');d.rectangle((17,24,23,32),fill='#efcd85');d.line((20,24,20,32),fill='#625874');register('tower',im)
im,d=canvas(32,34);d.ellipse((2,26,29,33),fill='#4c5369');d.polygon([(16,0),(27,15),(21,27),(11,28),(5,17)],fill='#4b8499');d.polygon([(16,2),(17,24),(8,17)],fill='#a8e7d1');d.polygon([(17,3),(25,15),(18,24)],fill='#6cb7b7');register('crystal',im)
im,d=canvas(32,24);d.ellipse((2,12,29,23),fill='#555368');
for x,y in ((7,12),(14,9),(22,12),(25,18),(14,21),(5,18)):d.rectangle((x-2,y-1,x+2,y+2),fill='#8d929c')
d.polygon([(11,18),(11,9),(15,3),(17,10),(21,7),(22,15),(18,20)],fill='#e78861');d.polygon([(14,18),(15,10),(18,13),(18,19)],fill='#f4d897');register('camp',im)
for name,opened in (('chest',False),('chest_open',True)):
 im,d=canvas(24,24);d.ellipse((1,18,23,23),fill=(5,12,25,75));d.rectangle((3,9,21,20),fill='#6e4a49');d.rectangle((4,8,20,14),fill='#b18156');d.rectangle((5,15,19,19),fill='#9a694b');d.line((3,14,21,14),fill='#e0b76e');d.rectangle((6,9,7,20),fill='#d5a662');d.rectangle((17,9,18,20),fill='#d5a662');d.rectangle((11,13,14,17),fill='#edcb83')
 if opened:d.rectangle((4,11,20,14),fill='#34334b');d.rectangle((4,4,20,8),fill='#9a694b')
 register(name,im)
im,d=canvas(32,40);d.ellipse((1,29,30,39),fill='#797791');d.ellipse((4,28,28,36),fill='#b0a5b3');d.rectangle((11,17,21,30),fill='#817f9c');d.ellipse((6,12,26,21),fill='#b9adc5');d.polygon([(16,0),(24,9),(16,16),(8,9)],fill='#bbdbcb');d.polygon([(16,3),(20,9),(16,13)],fill='#77bfc2');register('shrine',im)
for name,c in (('portal','#83ccb8'),('portal_pending','#9393ad')):
 im,d=canvas(32,42);d.ellipse((0,31,31,41),fill=(6,14,24,90));d.rectangle((3,9,8,35),fill='#747990');d.rectangle((24,9,29,35),fill='#747990');d.rectangle((6,4,25,11),fill='#8e96a3');d.rectangle((9,2,22,5),fill='#b3b5b8');d.rectangle((9,12,23,34),fill=(*tuple(int(c.lstrip('#')[i:i+2],16) for i in (0,2,4)),80));d.line((12,14,20,14),fill=c);d.line((16,18,16,31),fill=c);d.line((12,27,16,31),fill=c);d.line((20,27,16,31),fill=c);register(name,im)
for name,c in (('potion','#db8e99'),('ether','#8ebccc'),('sword','#c6d8d5'),('charm','#bdabd6'),('key','#e5c995')):
 im,d=canvas(20,20)
 if name in ('potion','ether'):
  d.rectangle((7,2,12,5),fill='#ac9377');d.rectangle((8,5,11,9),fill='#dddcd3');d.ellipse((4,8,15,18),fill='#4f5e72');d.ellipse((5,10,14,17),fill=c);d.line((6,11,6,13),fill='#f7e5d1')
 elif name=='sword':d.polygon([(13,1),(17,2),(6,15),(4,13)],fill=c);d.line((4,10,10,16),fill='#d5ad75',width=2);d.line((3,16,6,13),fill='#926b68',width=3)
 elif name=='key':d.ellipse((3,2,12,11),outline=c,width=3);d.line((10,10,16,16),fill=c,width=3);d.point((15,13),fill=c)
 else:d.ellipse((4,2,15,15),outline='#ddccab',width=2);d.polygon([(10,5),(15,12),(10,18),(5,12)],fill=c)
 register(name,im)

atlas=Image.new('RGBA',(512,512)); index={};x=y=2;row_h=0
for name,im in art.items():
 if x+im.width+2>512:x=2;y+=row_h+2;row_h=0
 assert y+im.height<=512
 atlas.alpha_composite(im,(x,y));index[name]={'rect':[x,y,im.width,im.height]};x+=im.width+2;row_h=max(row_h,im.height)
atlas.save(OUT/'atlas.png');(OUT/'atlas.json').write_text(json.dumps(index,indent=2),encoding='utf8')

# A quiet original 24-second chiptune loop (no sampled recordings).
rate=22050; seconds=24; notes=[57,64,69,71,69,64,60,64,55,62,67,69,67,62,59,62]
with wave.open(str(OUT/'wander.wav'),'wb') as wav:
 wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(rate)
 data=bytearray()
 for n in range(rate*seconds):
  t=n/rate; beat=int(t/.75);u=(t% .75)/.75;note=notes[beat%len(notes)];freq=440*2**((note-69)/12)
  env=min(1,u*25)*max(0,1-u)**1.6
  melody=math.sin(2*math.pi*freq*t)*.095*env + math.sin(2*math.pi*freq*2*t)*.025*env
  bass=math.sin(2*math.pi*(110 if beat%16<8 else 98)*t)*.035
  fade=min(1,t/.1,(seconds-t)/.1)
  data.extend(struct.pack('<h',int(max(-1,min(1,(melody+bass)*fade))*32767)))
 wav.writeframes(data)
print(f'Generated {len(art)} original sprites, 70 terrain tiles, and original music.')
