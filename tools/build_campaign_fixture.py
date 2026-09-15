"""Generate review fixtures from the real campaign engine, with no model calls."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from engine.storage import Store
from engine.world import World
from engine.read_views import atlas
from campaign_fixtures import chapter_patch,region_patch

folder=ROOT/'userdata/campaign-fixture';folder.mkdir(parents=True,exist_ok=True)
w=World(Store(':memory:'));w.start('跨区域信件调查',authored=True,planned=True)
w.apply_patch(chapter_patch(),w.context(kind='campaign'))
for rid in list(w.state['topology']):w.apply_patch(region_patch(w,rid),w.context(rid))
for rid,node in w.state['topology'].items():node['visited']=True
snap=w.snapshot()
(folder/'snapshot.json').write_text(json.dumps(snap,ensure_ascii=False),encoding='utf8')
(folder/'atlas.json').write_text(json.dumps(atlas(w),ensure_ascii=False),encoding='utf8')
w.state['campaign']['chapters']['c1']['flags']['power']=True
w.persist()
(folder/'atlas-unlocked.json').write_text(json.dumps(atlas(w),ensure_ascii=False),encoding='utf8')
w.state['campaign']['chapters']['c1']['links'][0]['one_way']=True
w.state['current']='c1_station'
(folder/'atlas-one-way.json').write_text(json.dumps(atlas(w),ensure_ascii=False),encoding='utf8')
w.store.close()
print('CAMPAIGN_FIXTURE_OK')
