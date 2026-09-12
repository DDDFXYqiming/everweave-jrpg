"""Versioned surface assemblies; placement variation costs no model tokens."""
import hashlib
import json
from pathlib import Path
from .diagnostics import InvalidPatch

FILE=Path(__file__).resolve().parents[1]/'assets/library/materials.json'

def definitions():
    return json.loads(FILE.read_text(encoding='utf-8'))

def menu(profile):
    return [dict(id=k,name=v['name'],tiles=v['tiles']) for k,v in definitions().items()
            if profile in v['tags'] or 'common' in v['tags']]

def validate(raw,palette):
    from .schema import obj
    from .visuals import validate_visuals
    obj(raw,'material reference',('material','material_hash'),('material',))
    key=raw['material'];defs=definitions()
    if not isinstance(key,str) or key not in defs:raise InvalidPatch('unknown surface material',value=key,category='reference')
    data=defs[key];digest=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if raw.get('material_hash',digest)!=digest:raise InvalidPatch('surface material version differs',value=key)
    def recipe(value):
        if 'size' not in value and 'asset' not in value:value=dict(value,size=[16,16])
        result=validate_visuals(dict(style='surface',terrain='grass',palette=palette,sprites={'tile':value}))['sprites']['tile']
        if result['size']!=[16,16]:raise InvalidPatch('material components must be 16x16')
        return result
    result=dict(material=key,material_hash=digest,size=[16,16],base=recipe(data['base']),
                variants=[recipe(v) for v in data.get('variants',[])],tiles=list(data['tiles']),
                detail_density=data.get('detail_density',.18),grain=data.get('grain',.025),dressing=data.get('dressing',True))
    if 'detail_key' in data:result['detail_key']=data['detail_key']
    return result
