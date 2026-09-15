import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from engine.server import GameServer
from adventure_fixtures import adventure_plan, authored_adventure_region
from tools.play_session import LocalAPI, Session, observe, route


class PlaySessionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.server = GameServer(('127.0.0.1', 0), ':memory:', 'test-local-only')
        self.world = self.server.world
        self.world.start('调查与同行', authored=True, planned=True)
        self.world.apply_patch(adventure_plan(), self.world.context(kind='campaign'))
        self.world.apply_patch(authored_adventure_region(self.world, 'r0'), self.world.context('r0'))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.runtime = Path(self.folder.name) / 'runtime.json'
        self.runtime.write_text(json.dumps(dict(url=f'http://127.0.0.1:{self.server.server_port}', token='test-local-only')))
        self.session = Session(LocalAPI(self.folder.name))

    def tearDown(self):
        self.server.shutdown(); self.thread.join(); self.server.server_close()
        self.world.store.close(); self.folder.cleanup()

    def test_player_projection_excludes_solutions_and_unrevealed_content(self):
        snap = self.world.snapshot()
        snap['region']['program']['secret_answer'] = 'UNSEEN_RULE'
        snap['region']['entities'].append(dict(id='UNSEEN_EXIT', spent=True, hidden=True))
        snap['region']['scenes'] = [dict(text='UNSEEN_SCENE')]
        snap['player']['resources']['private_test'] = 'UNSEEN_RESOURCE'
        text = json.dumps(observe(snap))
        self.assertNotIn('UNSEEN', text)
        self.assertNotIn('effects', text)
        self.assertNotIn('flag_sources', text)

    def test_go_uses_real_http_moves_then_stops_at_authored_menu(self):
        self.world.state['ui'] = {}; self.world.state['player'].update(x=12, y=5)
        self.world.persist(self.world.region())
        entity = next(e for e in self.world.region()['entities'] if e.get('local_id') == 'console')
        before = self.world.state['steps']
        result = self.session.go(entity['id'], interact=True)
        self.assertEqual(result['reason'], 'interacted')
        self.assertGreater(result['moves'], 1)
        self.assertEqual(self.world.state['steps'] - before, result['moves'])
        self.assertEqual(result['observation']['ui']['kind'], 'actions')
        self.session.act('choose', 'meet_mira')
        result = self.session.act('choose', 'scene:meeting:help')
        self.assertIn('listen', self.world.state['player']['abilities'])
        self.assertEqual(self.world.state['adventure']['cast']['mira']['state']['trust'], 5)

    def test_walk_stops_at_resource_change_and_never_finishes_route(self):
        self.world.state['ui'] = {}; self.world.state['player'].update(x=12, y=5)
        r = self.world.region()
        r['program']['hooks'].append(dict(id='toll', on='move', target='player', when=True, once=True,
                                         effects=[dict(op='resource', id='focus', delta=-1)]))
        self.world.persist(r)
        target = next(e for e in r['entities'] if e.get('local_id') == 'console')
        result = self.session.go(target['id'], interact=True)
        self.assertEqual(result['reason'], 'resources_changed'); self.assertEqual(result['moves'], 1)
        self.assertFalse(self.world.state['ui'])

    def test_path_respects_solid_footprints_and_rejects_unoffered_choice(self):
        s = self.world.snapshot(); s['player'].update(x=10, y=5)
        target = dict(x=4, y=5, footprint=[1, 1])
        s['region']['props'].append(dict(x=8, y=6, footprint=[1, 3], solid=True))
        path = route(s, target)
        self.assertTrue(path); self.assertFalse({(8, 4), (8, 5), (8, 6)} & set(path))
        before = copy.deepcopy(self.world.state)
        with self.assertRaises(ValueError): self.session.act('choose', 'not_visible')
        self.assertEqual(self.world.state, before)

    def test_runtime_token_cannot_be_sent_to_remote_url(self):
        self.runtime.write_text(json.dumps(dict(url='https://example.com', token='test-local-only')))
        with self.assertRaises(ValueError): LocalAPI(self.folder.name)

    def test_authored_combat_controls_use_client_protocol_and_real_turn(self):
        s=self.world.state;r=self.world.region()
        s['game_spec']['systems']['combat']=True
        s['game_spec']['resources'].append(dict(id='hp',label='体力',initial=24,max=24,display='bar'))
        s['player'].update(hp=24,max_hp=24)
        r['entities'].append(dict(id='r0:foe',local_id='foe',kind='enemy',x=20,y=8,spent=False,solid=True))
        r['program']['actions'].append(dict(id='strike',label='打击',description='打击',scope='combat',target='player',when=True,once=False,effects=[dict(op='stat',target='enemy',name='hp',delta=-2)]))
        s['ui']={};s['battle']=dict(id='r0:foe',name='对手',hp=6,max_hp=6,attack=2,turn=0,log=[],authored=True)
        self.world.persist(r)
        result=self.session.act('combat','strike')['observation']
        self.assertEqual(result['battle']['hp'],4);self.assertEqual(result['battle']['turn'],1)
        self.assertEqual(s['player']['hp'],22)


if __name__ == '__main__': unittest.main()
