"""Register a reviewed CC0 asset batch without changing engine code.

Manifest: {source_id, source:{title,author,page,version,license:"CC0-1.0"},
 assets:[{id,file,name,kind,roles,tags,family?,perspective?,footprint?,loop?}]}.
Files must be PNG or Vorbis OGG beneath the manifest's folder. This tool does not
download or determine copyright ownership; verify the original license first.
Default is a dry-run; use --apply after reviewing the reported entries.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
from PIL import Image
from import_library import ogg_metadata

ROOT=Path(__file__).resolve().parents[1]
LIB=ROOT/'assets/library'

def register(path,apply=False):
    path=Path(path).resolve();raw=json.loads(path.read_text(encoding='utf-8'))
    source_id=raw['source_id'];source=raw['source']
    assert re.fullmatch('[a-z][a-z0-9_]{0,39}',source_id)
    assert source['license']=='CC0-1.0'
    assert all(isinstance(source.get(k),str) and source[k] for k in ('title','author','page','version'))
    assert source['page'].startswith('https://')
    index=json.loads((LIB/'index.json').read_text(encoding='utf-8'));sources=json.loads((LIB/'sources.json').read_text(encoding='utf-8'))
    pending=[];seen=set()
    for spec in raw['assets']:
        key=spec['id'];assert re.fullmatch('[a-z][a-z0-9_]{0,39}',key)
        assert key not in seen,'Duplicate asset ID in batch'
        seen.add(key)
        file=(path.parent/spec['file']).resolve()
        assert file.is_relative_to(path.parent) and not file.is_symlink()
        assert file.suffix.lower() in ('.png','.ogg') and file.stat().st_size<=15_000_000
        data=file.read_bytes();sha=hashlib.sha256(data).hexdigest()
        if key in index['assets']:assert index['assets'][key]['sha256']==sha,'Use a new versioned ID when bytes change'
        kind=spec['kind'];assert kind in ('image','sfx','music')
        entry={k:spec[k] for k in ('name','kind','roles','tags')}
        assert isinstance(entry['roles'],list) and isinstance(entry['tags'],list)
        entry.update(source=source_id,sha256=sha,file=f'assets/library/blobs/{sha}{file.suffix.lower()}',bytes=len(data),curated=True)
        if kind=='image':
            assert file.suffix.lower()=='.png'
            img=Image.open(io.BytesIO(data));assert 8<=img.width<=96 and 8<=img.height<=96
            assert spec.get('perspective')=='top_down' and spec.get('family')
            entry.update(size=list(img.size),family=spec['family'],perspective='top_down',anchor='bottom_center',footprint=spec.get('footprint',[1,1]),animation='static')
            assert len(entry['footprint'])==2 and all(type(n) is int and 1<=n<=8 for n in entry['footprint'])
        else:
            assert file.suffix.lower()=='.ogg'
            entry.update(ogg_metadata(data),loop=bool(spec.get('loop',False)),loop_start=spec.get('loop_start',0),gain_db=spec.get('gain_db',-14 if kind=='music' else -10))
            assert -40<=entry['gain_db']<=0
            assert 0<=entry['loop_start']<entry['duration_seconds']
        if key in index['assets']:assert entry==index['assets'][key],'Existing asset metadata is immutable; use a new versioned ID'
        pending.append((key,entry,data))
    if apply:
        for key,entry,data in pending:
            (ROOT/entry['file']).write_bytes(data);index['assets'][key]=entry
        source=dict(source,adapter='registered',sha256=hashlib.sha256(path.read_bytes()).hexdigest(),checksum_scope='registration manifest')
        sources[source_id]=source
        (LIB/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (LIB/'sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (LIB/'licenses'/(source_id+'.txt')).write_text(json.dumps(source,ensure_ascii=False,indent=2),encoding='utf-8')
        with (LIB/'CREDITS.md').open('a',encoding='utf-8') as credits:credits.write(f'\n- **{source["title"]}** — {source["author"]}; CC0 1.0; {source["page"]}; {source["version"]}.\n')
    return [dict(id=k,name=e['name'],sha256=e['sha256']) for k,e,_ in pending]

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('manifest',type=Path);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    print(json.dumps(register(args.manifest,args.apply),ensure_ascii=False,indent=2))
