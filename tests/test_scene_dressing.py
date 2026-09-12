import copy
import unittest
from engine.scene import paint,dress,cells_for
from engine.materials import validate,definitions
from engine.schema import InvalidPatch
from engine.storage import Store
from engine.world import World
from engine.pcg import reachable
from hybrid_fixtures import hybrid_patch

class SceneDressingTests(unittest.TestCase):
    def setUp(self):
        self.w=World(Store(':memory:'));self.w.start('林间驿站与石室',authored=True)
    def tearDown(self):self.w.store.close()
    def decorated(self):
        raw=hybrid_patch();v=raw['region']['visuals']
        v['sprites'].update(floor={'material':'meadow_v1'},wall={'material':'masonry_v1'},flowers={'asset':'town_v1_flowers'})
        v.update(scenery=['flowers','tree'],density=.12)
        self.w.apply_patch(raw,self.w.context());return self.w.region()
    def test_materials_expand_and_pin_all_component_assets(self):
        palette=hybrid_patch()['region']['visuals']['palette']
        for key in definitions():
            m=validate({'material':key},palette)
            self.assertEqual(m['size'],[16,16]);self.assertEqual(len(m['material_hash']),64)
            for part in [m['base']]+m['variants']:
                if 'asset' in part:self.assertEqual(len(part['asset_hash']),64)
        for value in ({'material':'missing'},{'material':'meadow_v1','material_hash':'0'*64}):
            with self.assertRaises(InvalidPatch):validate(value,palette)
    def test_room_floor_wall_and_threshold_are_distinct_and_repaintable(self):
        self.decorated();r=self.w.region()
        paint(r,[dict(room=[1,1,8,6],tile='ground',surface='floor',doors=[[4,6]])])
        self.assertEqual((r['tiles'][2][2],r['surfaces'][2][2]),(0,'floor'))
        self.assertEqual((r['tiles'][1][2],r['surfaces'][1][2]),(3,''))
        self.assertEqual((r['tiles'][6][4],r['surfaces'][6][4]),(1,''))
        paint(r,[dict(room=[1,1,8,6],tile='ground',surface='floor',wall_surface='wall',door_surface='floor',doors=[[4,6]])])
        self.assertEqual(r['surfaces'][1][2],'wall');self.assertEqual(r['surfaces'][6][4],'floor')
        paint(r,[dict(rect=[4,1,1,1],tile='path')])
        self.assertEqual((r['tiles'][1][4],r['surfaces'][1][4]),(1,''))
    def test_direct_library_ids_for_room_edges_are_normalized(self):
        raw=hybrid_patch();raw['region']['scene']['paint'].append(dict(room=[1,1,8,6],tile='ground',surface='floor',wall_surface='dungeon_v1_stone',door_surface='town_v1_stone_path',doors=[[4,6]]))
        self.w.apply_patch(raw,self.w.context())
        self.assertEqual(self.w.region()['surfaces'][1][2],'dungeon_v1_stone')
    def test_dressing_is_deterministic_non_blocking_and_keeps_interactions_clear(self):
        r=self.decorated();before=copy.deepcopy(r)
        props=[p for p in r['props'] if p.get('scenery_auto')]
        self.assertGreater(len(props),5);self.assertLessEqual(len(props),192)
        area=reachable(r['tiles'],r['spawn']);dress(r)
        self.assertEqual(r,before);self.assertEqual(reachable(r['tiles'],r['spawn']),area)
        for p in props:
            self.assertFalse(p['solid']);self.assertEqual(r['tiles'][p['y']][p['x']],0)
            for e in r['entities']:
                self.assertGreater(min(max(abs(p['x']-x),abs(p['y']-y)) for x,y in cells_for(e)),1)
        clone=copy.deepcopy(r);clone.pop('dressing_signature');dress(clone)
        self.assertEqual(clone['props'],r['props'])
    def test_density_zero_and_live_repaint_remove_only_automatic_dressing(self):
        r=self.decorated();explicit=[p for p in r['props'] if not p.get('scenery_auto')]
        p=next(p for p in r['props'] if p.get('scenery_auto'))
        paint(r,[dict(rect=[p['x'],p['y'],1,1],tile='path')]);dress(r)
        self.assertFalse(any(q.get('scenery_auto') and (q['x'],q['y'])==(p['x'],p['y']) for q in r['props']))
        r['visuals']['density']=0;dress(r);self.assertEqual(r['props'],explicit)
    def test_material_role_keeps_old_ground_roads_clear_and_dresses_indoor_path_floors(self):
        r=self.decorated();r['visuals']['sprites']['road']={'material':'earth_path_v1','tiles':[1,4],'size':[16,16]}
        paint(r,[dict(rect=[0,0,10,20],tile='ground',surface='road'),dict(rect=[14,0,14,20],tile='path',surface='floor')]);dress(r)
        props=[p for p in r['props'] if p.get('scenery_auto')]
        self.assertFalse(any(p['x']<10 for p in props))
        self.assertTrue(any(p['x']>=14 for p in props))
        r['visuals']['sprites']['floor']['dressing']=False
        dress(r)
        self.assertFalse(any(p.get('scenery_auto') and p['x']>=14 for p in r['props']))
    def test_wall_mounted_assets_stay_on_wall_faces(self):
        r=self.decorated();r['visuals']['sprites']['torch']={'asset':'dungeon_v1_torch','size':[16,16]}
        r['visuals']['scenery']=['torch']
        paint(r,[dict(rect=[0,2,28,1],tile='wall')]);dress(r)
        props=[p for p in r['props'] if p.get('scenery_auto')]
        self.assertTrue(props)
        for p in props:
            self.assertEqual(r['tiles'][p['y']][p['x']],3)
            self.assertEqual(r['tiles'][p['y']+1][p['x']],0)
    def test_even_width_art_reserves_both_half_cells(self):
        r=self.decorated();r['visuals']['sprites']['wide']={'size':[32,16],'layers':[['rect',0,0,32,16,'ground']]}
        r['visuals']['scenery']=['wide'];dress(r)
        props=[p for p in r['props'] if p.get('scenery_auto')]
        self.assertTrue(props)
        for p in props:
            self.assertGreater(p['x'],0);self.assertLess(p['x'],r['width']-1)
            for x in range(p['x']-1,p['x']+2):self.assertEqual(r['tiles'][p['y']][x],0)

if __name__=='__main__':unittest.main()
