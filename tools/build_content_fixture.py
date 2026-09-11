"""Build native-client fixtures from actual Python actions; no cloud calls or saves."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from content_fixtures import authored_patch
from engine.world import World
from engine.storage import Store

w=World(Store(':memory:'))
try:
    w.start('原生客户端执行内容验收')
    w.apply_patch(authored_patch(),w.context())
    snapshots=[w.snapshot()]
    w.action({'op':'interact','id':'r0:lever'})
    snapshots.append(w.snapshot())
    w.action({'op':'content_action','id':'tune'})
    w.action({'op':'invoke','id':'tune'})
    for _ in range(9):w.action({'op':'move','dx':1,'dy':0})
    snapshots.append(w.snapshot())
    w.state['player'].update(x=19,y=8)
    w.action({'op':'interact','id':'r0:foe'})
    snapshots.append(w.snapshot())
    path=ROOT/'tests/fixtures/generated_content.json'
    path.write_text(json.dumps(snapshots,ensure_ascii=False),encoding='utf-8')
    print('CONTENT_FIXTURE_OK: real actions -> door geometry/state -> objective -> custom combat')
finally:w.store.close()
