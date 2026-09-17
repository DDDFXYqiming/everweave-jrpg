"""Pinned, local content catalog. The model receives IDs, never filesystem paths."""
import copy
from collections import Counter
from functools import lru_cache
import hashlib
import json
import re
from pathlib import Path

from .diagnostics import InvalidPatch

ROOT=Path(__file__).resolve().parents[1]

@lru_cache(maxsize=1)
def catalog():
    return json.loads((ROOT/'assets/library/index.json').read_text(encoding='utf-8'))['assets']

@lru_cache(maxsize=1024)
def _verified(path,size,modified):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def resolve(key,kind=None,pinned=None):
    if not isinstance(key,str) or key not in catalog():
        raise InvalidPatch('unknown library asset',category='reference',value=key,expected='an asset ID from library_candidates')
    entry=catalog()[key]
    if kind and entry['kind'] not in ((kind,) if isinstance(kind,str) else kind):
        raise InvalidPatch('library asset has the wrong media type',category='reference',value=key,expected=str(kind))
    if pinned is not None and pinned!=entry['sha256'] and pinned not in entry.get('legacy_hashes',[]):
        raise InvalidPatch('library asset revision differs from saved content',category='reference',value=key,expected=entry['sha256'])
    file=(ROOT/entry['file']).resolve()
    if not file.is_relative_to((ROOT/'assets/library/blobs').resolve()):raise InvalidPatch('asset escapes the local library')
    try:
        stat=file.stat()
        if stat.st_size!=entry['bytes'] or _verified(str(file),stat.st_size,stat.st_mtime_ns)!=entry['sha256']:
            raise InvalidPatch('library file is damaged or changed; restore the pinned library',value=key)
    except OSError as exc:raise InvalidPatch('library file is missing; restore the pinned library',value=key) from exc
    return copy.deepcopy(entry)

def used_assets(value):
    result=set()
    def walk(v):
        if isinstance(v,list):
            for x in v:walk(x)
        elif isinstance(v,dict):
            if isinstance(v.get('asset'),str):result.add(v['asset'])
            for key,x in v.items():
                if key not in ('library_candidates','rejected_response'):walk(x)
    walk(value)
    return sorted(result)

def usage(plan):
    sprites=list(plan.get('visuals',{}).get('sprites',{}).values())
    composed=sum('parts' in s or ('asset' in s and ('layers' in s or 'frames' in s)) for s in sprites)
    referenced=sum('asset' in s and 'layers' not in s and 'frames' not in s for s in sprites)
    materials=sum('material' in s for s in sprites)
    return dict(referenced=referenced,composed=composed,materials=materials,drawn=len(sprites)-composed-referenced-materials,
                unique_assets=len(used_assets(plan)),modules=len(plan.get('module_sources',[])))

def _selection(context):
    destination=json.dumps(context.get('destination') or {},ensure_ascii=False).lower()
    setting=(str(context.get('setting',''))+' '+str((context.get('game_spec') or {}).get('visual_theme',''))).lower()
    underground=('dungeon','ruin','crypt','cave','地下','遗迹','地牢','洞穴','古墓')
    science=('sci-fi','space','火星','太空','宇宙','星际','赛博','机器人')
    profile='sci_fi' if any(x in destination or x in setting for x in science) else 'dungeon' if any(x in destination or x in setting for x in underground) else 'town'
    modern=('生化','感染','病毒','丧尸','医院','实验室','现代','resident evil','zombie','infection','hospital','laboratory','modern','survival horror')
    if any(x in setting for x in modern):profile='modern'
    elif any(x in setting for x in science):profile='sci_fi'
    query=setting+' '+destination
    synonyms={'村民':'villager','商人':'merchant villager','柜台':'crate shelf','士兵':'guard soldier','法师':'mage','幽灵':'ghost','蜘蛛':'spider','老鼠':'rat','恶魔':'demon boss','首领':'boss demon','治疗':'healer medicine','药':'potion medicine','斧':'axe','杖':'staff','门':'door','水井':'well','森林':'forest tree','机械':'machine switch','箱':'chest crate','书':'shelf book','花':'flowers'}
    words=set(re.findall('[a-z_]+',query+' '+' '.join(v for k,v in synonyms.items() if k in query)))
    matching=[e for e in catalog().values() if e['kind']=='image' and profile in e['tags'] and e.get('curated')]
    family=Counter(e.get('family','') for e in matching).most_common(1)[0][0] if matching else ''
    recent=Counter(asset for record in context.get('design_history',[])[-5:] for asset in record.get('assets',[]))
    return profile,family,recent,words

def candidate_pool(context):
    """Return the technically compatible visual recall pool before prompt truncation.

    The ordinary catalog path still owns file integrity, perspective/family and
    usage-history rules.  A semantic selector may rank this metadata, but it
    never gets to introduce an unknown asset ID or bypass those rules.
    """
    profile,family,recent,_=_selection(context)
    images=[]
    for key,entry in catalog().items():
        if entry['kind']!='image' or not entry.get('curated') or (family and entry.get('family')!=family):continue
        value=dict(id=key,name=entry['name'],roles=entry.get('roles',[]),tags=entry.get('tags',[]),
                   size=entry['size'],footprint=entry['footprint'],recent_uses=recent[key],
                   profile_match=profile in entry.get('tags',[]) or 'common' in entry.get('tags',[]))
        if entry.get('description'):value['description']=entry['description']
        if entry.get('surface_use'):value['surface_use']=entry['surface_use']
        images.append(value)
    images.sort(key=lambda e:(not e['profile_match'],e['recent_uses'],e['id']))
    return dict(profile=profile,family=family or 'no_matching_visual_family',perspective='top_down',images=images)

def candidates(context):
    profile,family,recent,words=_selection(context)
    pool=[]
    for key,entry in catalog().items():
        if entry['kind']!='image' or not entry.get('curated'):continue
        if not family or entry.get('family')!=family:continue
        tags=entry['tags']
        if profile not in tags and 'common' not in tags:continue
        score=10*(profile in tags)+4*len(words.intersection(tags))-recent[key]
        pool.append((score,key,entry))
    # Cover usable roles before adding decorative variety. All these families
    # have the same view/pixel scale; raw construction tiles stay out of prompts.
    chosen=[]
    for role,limit in (('ground',3),('hero',2),('npc',3),('building',2),('vegetation',3),('object',6),('item',5),('enemy',2),('decoration',3)):
        if role=='hero' and context.get('hero_visual'):continue
        matches=sorted((x for x in pool if role in x[2]['roles']),key=lambda x:(-x[0],x[1]))[:limit]
        for _,key,e in matches:
            candidate=dict(id=key,name=e['name'],role=role,size=e['size'],footprint=e['footprint'])
            if e.get('description'):candidate['description']=e['description']
            if role=='ground' and e.get('surface_use'):candidate['surface_use']=e['surface_use']
            chosen.append(candidate)
    audio=[]
    preferred=('rpg_v1_footstep00','rpg_v1_door_open_1','rpg_v1_creak1','rpg_v1_metal_latch','rpg_v1_knife_slice','rpg_v1_handle_coins','ui_v1_click_001','ui_v1_confirmation_001')
    for key,e in catalog().items():
        if e['kind']=='music' and (profile in e['tags'] or 'common' in e['tags']):
            audio.append(dict(id=key,name=e['name'],kind='music',tags=e['tags'],loop=e['loop']))
        elif key in preferred:audio.append(dict(id=key,name=e['name'],kind='sfx',loop=False))
    from .modules import menu
    from .materials import menu as material_menu
    modules=menu();spec=context.get('game_spec')
    if spec:
        keys={r['id'] for r in spec['resources']}
        modules=[m for m in modules if (m['id']!='duel_v1' or spec['systems']['combat'] and 'mp' in keys) and (m['id']!='trade_v1' or spec['systems']['inventory'] and 'gold' in keys)]
    return dict(profile=profile,family=family or 'no_matching_visual_family',perspective='top_down',images=chosen,audio=audio,modules=modules,materials=material_menu(profile),
     art_policy='Use only assets that fit this setting. Empty image candidates mean original drawing is required; do not force medieval substitutions.')
