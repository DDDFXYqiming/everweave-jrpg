"""Static resource consistency checks, not a substitute for Godot's native parser."""
from pathlib import Path
import json
import struct
import tempfile
import unittest
import wave

from engine.world import World
from engine.storage import Store
from engine.director import Director

ROOT=Path(__file__).resolve().parents[1]

class ArtifactTests(unittest.TestCase):
    def test_atlas_coordinates_fit_actual_png(self):
        data=(ROOT/'assets/atlas.png').read_bytes()
        self.assertEqual(data[:8],b'\x89PNG\r\n\x1a\n')
        width,height=struct.unpack('>II',data[16:24])
        index=json.loads((ROOT/'assets/atlas.json').read_text(encoding='utf-8'))
        for sprite in index.values():
            x,y,w,h=sprite['rect']
            self.assertTrue(0<=x<x+w<=width and 0<=y<y+h<=height)
        for name in ['hero_0','sentinel','slime','wolf','wisp','mimic','portal','portal_pending','house','tower','chest','chest_open','shrine']:
            self.assertIn(name,index)

    def test_music_is_valid_pcm(self):
        with wave.open(str(ROOT/'assets/wander.wav'),'rb') as source:
            self.assertEqual(source.getnchannels(),1)
            self.assertEqual(source.getsampwidth(),2)
            self.assertEqual(source.getframerate(),22050)
            self.assertEqual(source.getnframes(),22050*24)

    def test_declared_resources_exist(self):
        import re
        for script in list((ROOT/'client').glob('*.gd'))+[ROOT/'client/main.tscn']:
            for reference in re.findall(r'res://[^"\s]+',script.read_text(encoding='utf-8')):
                self.assertTrue((ROOT/reference.removeprefix('res://')).is_file(),f'{script}: {reference}')

    def test_no_font_or_runtime_credentials_shipped(self):
        for folder in (ROOT/'assets',ROOT/'client'):
            for f in folder.rglob('*'):
                self.assertNotIn(f.suffix.lower(),('.ttf','.otf','.woff','.woff2','.pem','.key'))
                self.assertNotEqual(f.name,'runtime.json')

    def test_pending_world_reaction_survives_restart(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'save.sqlite3';w=World(Store(path));w.start('在漫长的雨夜中寻找记忆。');d=Director(w);d.configure({'offline':True});d.cfg['cooldown']=0;d.step()
            event,deleted=w.story('choice','帮助陌生人',{'tag':'mercy'});w.persist(event=event,delete=deleted);w.store.close()
            restored=World(Store(path));self.assertTrue(restored.reaction_needed)
            again=Director(restored);again.configure({'offline':True});again.cfg['cooldown']=0
            for _ in range(3):again.step()
            self.assertEqual(restored.region()['revision'],1)
            self.assertFalse(restored.state['director_reaction_pending'])
            restored.store.close()

if __name__=='__main__':unittest.main()
