"""Reproduce the pinned CC0 starter library; normal operation is entirely offline.

Run --download to fetch missing source packages, or --verify to check shipped files.
Only PNG/OGG and license text are imported, never code or shortcut files.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine.asset_cache import encode_rgba
LIB=ROOT/'assets/library'
CACHE=ROOT/'userdata/library-ingest'

TOWN={0:('grass','ground','grass meadow'),1:('grass_detail','ground','grass stones'),2:('flowers','decoration','flowers meadow'),4:('pine','vegetation','pine tree'),16:('round_tree','vegetation','tree orchard'),28:('bush','vegetation','bush'),29:('mushrooms','decoration','mushrooms forest'),43:('stone_path','ground','stone path'),45:('fence','decoration','wood fence'),47:('post','decoration','wood post'),63:('roof_gable','part','roof blue gable'),83:('sign','object','wood sign'),84:('window','part','wood window'),85:('door','object','wood door closed'),94:('beehive','object','beehive honey'),104:('well','object','well water'),107:('bucket','item','bucket water'),115:('pickaxe','item','pickaxe tool'),116:('fork','item','pitchfork tool')}
DUNGEON={0:('floor','ground','brown dungeon floor'),12:('rubble','ground','rubble stone floor'),14:('stone','ground','stone wall floor'),29:('torch','decoration','torch warm fire'),32:('crystal_fire','decoration','magic cyan flame'),36:('stairs','object','stone stairs'),42:('paving','ground','sandstone paving'),54:('stairs_down','object','stairs entrance down'),55:('stairs_up','object','stairs exit up'),63:('crate','object','wood crate'),64:('hammer','item','hammer tool'),65:('tablet','object','stone tablet'),74:('cauldron','object','metal cauldron'),75:('shelf','decoration','shelf wooden cabinet'),84:('mage','npc','mage wizard purple'),85:('villager','npc','villager merchant'),86:('worker','npc','worker engineer'),89:('chest','object','chest closed'),91:('chest_open','object','chest open'),96:('knight','hero','knight armored'),97:('guard','npc','guard soldier'),98:('elf','hero','elf adventurer'),99:('witch','npc','witch mage'),100:('healer','npc','healer priest'),101:('switch','object','switch button'),104:('sword','item','sword weapon'),108:('slime','enemy','slime green monster'),109:('adventurer','hero','human adventurer'),110:('demon','enemy','demon red boss'),112:('ranger','hero','ranger green'),113:('flask','item','bottle grey'),114:('green_flask','item','potion green'),115:('red_flask','item','medicine potion red'),116:('blue_flask','item','potion blue'),121:('spider','enemy','spider monster'),122:('ghost','enemy','ghost monster'),124:('rat','enemy','rat brown'),125:('grey_rat','enemy','rat grey'),129:('staff','item','staff wand magic')}


def digest(data):return hashlib.sha256(data).hexdigest()

def ogg_metadata(data):
    header=data.find(b'\x01vorbis')
    if header<0:raise ValueError('Vorbis identification packet missing')
    channels=data[header+11];rate=int.from_bytes(data[header+12:header+16],'little')
    cursor=0;frames=0
    while cursor+27<=len(data) and data[cursor:cursor+4]==b'OggS':
        granule=int.from_bytes(data[cursor+6:cursor+14],'little')
        if granule<2**63:frames=max(frames,granule)
        count=data[cursor+26];cursor+=27+count+sum(data[cursor+27:cursor+27+count])
    return dict(channels=channels,sample_rate=rate,duration_seconds=round(frames/rate,4))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download',action='store_true')
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    sources=json.loads((LIB/'sources.json').read_text(encoding='utf-8'))
    if args.verify:
        index=json.loads((LIB/'index.json').read_text(encoding='utf-8'))
        for key,entry in index['assets'].items():
            path=ROOT/entry['file']
            assert path.resolve().is_relative_to((LIB/'blobs').resolve()),key
            assert digest(path.read_bytes())==entry['sha256'],key
        print('LIBRARY_VERIFY_OK',len(index['assets']))
        return
    CACHE.mkdir(parents=True,exist_ok=True)
    from PIL import Image
    (LIB/'blobs').mkdir(parents=True,exist_ok=True)
    (LIB/'licenses').mkdir(parents=True,exist_ok=True)
    assets=json.loads((LIB/'index.json').read_text(encoding='utf-8'))['assets'] if (LIB/'index.json').exists() else {}
    def add(key,data,suffix,source,name,kind,roles,tags,**meta):
        sha=digest(data);rel=Path('assets/library/blobs')/(sha+suffix)
        if key in assets and assets[key]['sha256']!=sha:raise ValueError('Asset IDs are immutable; assign a new versioned ID: '+key)
        path=ROOT/rel
        if path.exists():assert digest(path.read_bytes())==sha
        else:path.write_bytes(data)
        if suffix=='.ogg':meta.update(ogg_metadata(data))
        if 'derived_from_tiles' in meta:meta['encoding']='rgba_png_stored_v1'
        if assets.get(key,{}).get('legacy_hashes'):meta['legacy_hashes']=assets[key]['legacy_hashes']
        assets[key]=dict(name=name,kind=kind,roles=roles,tags=tags.split(),source=source,
                         sha256=sha,file=rel.as_posix(),bytes=len(data),**meta)
    for source,spec in sources.items():
        if spec.get('adapter')=='registered':continue
        file=CACHE/(source+spec['extension'])
        if not file.exists():
            if not args.download:raise SystemExit('Missing source cache: '+str(file)+'; use --download')
            req=urllib.request.Request(spec['download'],headers={'User-Agent':'Everweave-Asset-Importer/1.0'})
            with urllib.request.urlopen(req,timeout=45) as response:data=response.read(20_000_001)
            assert len(data)<=20_000_000,'package size limit'
            assert digest(data)==spec['sha256'],source+' source revision changed'
            file.write_bytes(data)
        data=file.read_bytes();assert digest(data)==spec['sha256'],source
        if spec['extension']=='.zip':
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names=archive.namelist()
                license_name=next(n for n in names if n.lower().endswith('license.txt'))
                (LIB/'licenses'/(source+'.txt')).write_bytes(archive.read(license_name))
                if source in ('tiny_town','tiny_dungeon'):
                    table=TOWN if source=='tiny_town' else DUNGEON
                    prefix='town_v1' if source=='tiny_town' else 'dungeon_v1'
                    theme='town village forest' if source=='tiny_town' else 'dungeon ruins cave'
                    for name in names:
                        if not re.fullmatch(r'Tiles/tile_\d{4}\.png',name):continue
                        number=int(Path(name).stem.split('_')[1])
                        title,role,tags=table.get(number,(f'tile_{number:04d}','part','construction tile'))
                        raw=archive.read(name);img=Image.open(io.BytesIO(raw))
                        common=' common' if role in ('hero','npc','item','enemy') or title in ('crate','chest','shelf','cauldron','switch') else ''
                        add(prefix+'_'+title,raw,'.png',source,title.replace('_',' '),'image',[role],theme+' '+tags+common,
                            size=list(img.size),perspective='top_down',family='kenney_tiny',anchor='bottom_center',footprint=[1,1],animation='static',source_member=name,curated=number in table,
                            description=tags,surface_use=('accent: contrasting clusters; use in small patches' if title in ('paving','rubble','stone_path','grass_detail') else 'wall' if title=='stone' else 'base') if role=='ground' else '',
                            **({'placement':'wall_front'} if source=='tiny_dungeon' and title=='torch' else {}))
                    if source=='tiny_town':
                        assemblies={'blue_house':[[48,49,50],[60,63,62],[72,85,75]],'red_house':[[52,53,54],[64,67,66],[76,89,79]],'large_tree':[[6,7,8],[18,19,20],[30,31,32]],'autumn_tree':[[9,10,11],[21,22,23],[33,34,35]]}
                        for title,tiles in assemblies.items():
                            image=Image.new('RGBA',(48,48))
                            for y,row in enumerate(tiles):
                                for x,n in enumerate(row):
                                    tile=Image.open(io.BytesIO(archive.read(f'Tiles/tile_{n:04d}.png'))).convert('RGBA')
                                    image.alpha_composite(tile,(x*16,y*16))
                            output=io.BytesIO(encode_rgba(image.width,image.height,image.tobytes()))
                            role='building' if 'house' in title else 'vegetation'
                            add(prefix+'_'+title,output.getvalue(),'.png',source,title.replace('_',' '),'image',[role],theme+' '+title.replace('_',' '),size=[48,48],perspective='top_down',family='kenney_tiny',anchor='bottom_center',footprint=[3,2] if role=='building' else [2,1],animation='static',derived_from_tiles=tiles,curated=True)
                        # Tall trees are a crown over its matching trunk tile. The
                        # 3x3 forest autotile fragments are not standalone trees.
                        for old in ('pine','round_tree','large_tree','autumn_tree'):
                            assets[prefix+'_'+old]['curated']=False
                        for title,tiles in {'pine':[4,16],'autumn_tree':[3,15]}.items():
                            image=Image.new('RGBA',(16,32))
                            for y,n in enumerate(tiles):image.alpha_composite(Image.open(io.BytesIO(archive.read(f'Tiles/tile_{n:04d}.png'))).convert('RGBA'),(0,y*16))
                            output=io.BytesIO(encode_rgba(image.width,image.height,image.tobytes()))
                            add('town_v2_'+title,output.getvalue(),'.png',source,title.replace('_',' '),'image',['vegetation'],theme+' tree '+title.replace('_',' '),size=[16,32],perspective='top_down',family='kenney_tiny',anchor='bottom_center',footprint=[1,1],animation='static',derived_from_tiles=[[n] for n in tiles],curated=True)
                else:
                    for name in names:
                        if not name.startswith('Audio/') or not name.endswith('.ogg'):continue
                        stem=Path(name).stem
                        slug=re.sub(r'(?<!^)([A-Z])',r'_\1',stem).lower()
                        prefix='rpg_v1_' if source=='rpg_audio' else 'ui_v1_'
                        tags=re.sub(r'\d+','',slug).replace('_',' ')
                        add(prefix+slug,archive.read(name),'.ogg',source,tags.strip(),'sfx',['effect'],'common '+tags,
                            loop=False,loop_start=0,gain_db=-10,source_member=name,curated=True)
        else:
            add('music_v1_'+source,data,'.ogg',source,spec['title'],'music',['music'],spec['tags'],
                loop=spec['loop'],loop_start=spec.get('loop_start',0),gain_db=-14,bpm=spec.get('bpm'),loop_evidence='author description',curated=True)
            (LIB/'licenses'/(source+'.txt')).write_text(spec['title']+'\nAuthor: '+spec['author']+'\nLicense selected: CC0 1.0\nSource: '+spec['page']+'\nRetrieved: 2026-09-12\n',encoding='utf-8')
    index=dict(version=1,assets=assets)
    (LIB/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    credits=['# Content library sources','', 'The following assets are distributed under CC0 1.0. Original authors are credited here; no claim of original authorship is made.','']
    for key,spec in sources.items():credits.append(f'- **{spec["title"]}** — {spec["author"]}. [Source]({spec["page"]}). Version: {spec["version"]}. Source SHA-256: `{spec["sha256"]}`.')
    credits += ['', 'House/tree assemblies join the listed original tile indices; original PNGs and OGGs remain unmodified. Generated runtime variants are separate data definitions.','', 'The full source-package digests, download URLs, member names and derivative tile arrangements are recorded in sources.json and index.json.']
    (LIB/'CREDITS.md').write_text('\n'.join(credits)+'\n',encoding='utf-8')
    print('LIBRARY_IMPORTED',len(assets),'entries',sum(e['bytes'] for e in assets.values()),'bytes')

if __name__=='__main__':main()
