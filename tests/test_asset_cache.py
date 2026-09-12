import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from engine import asset_cache as cache


class AssetCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.library = self.root/'assets/library'
        self.library.mkdir(parents=True)
        self.data = b'original asset bytes'
        stream = io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            archive.writestr('Tiles/tile.png',self.data)
        self.package = stream.getvalue()
        sha = cache.digest(self.data)
        self.entry = dict(file=f'assets/library/blobs/{sha}.png',sha256=sha,bytes=len(self.data),source='pack',source_member='Tiles/tile.png')
        self.sources = dict(pack=dict(download='https://example.com/pack.zip',sha256=cache.digest(self.package),extension='.zip',title='Test pack'))
        self.write_manifests()

    def tearDown(self):
        self.temp.cleanup()

    def write_manifests(self):
        (self.library/'index.json').write_text(json.dumps(dict(assets={'picture':self.entry})))
        (self.library/'sources.json').write_text(json.dumps(self.sources))

    def test_cold_prepare_then_offline_cache_hit_does_not_edit_manifests(self):
        original={p.name:p.read_bytes() for p in self.library.glob('*.json')}
        with patch.object(cache,'fetch',return_value=self.package) as fetch:
            self.assertEqual(cache.prepare(self.root,download=True,progress=lambda _:None)['prepared'],1)
            self.assertEqual(fetch.call_count,1)
        self.assertEqual(cache.asset_path(self.root,self.entry).read_bytes(),self.data)
        with patch.object(cache,'fetch',side_effect=AssertionError('must stay offline')):
            self.assertEqual(cache.prepare(self.root,download=True)['prepared'],0)
        self.assertEqual(original,{p.name:p.read_bytes() for p in self.library.glob('*.json')})

    def test_damaged_asset_is_repaired_from_package_without_network(self):
        with patch.object(cache,'fetch',return_value=self.package):
            cache.prepare(self.root,download=True,progress=lambda _:None)
        cache.asset_path(self.root,self.entry).write_bytes(b'damaged')
        with self.assertRaises(ValueError):cache.prepare(self.root,verify_only=True)
        with patch.object(cache,'fetch',side_effect=AssertionError('must use cached pack')):
            cache.prepare(self.root)
        self.assertEqual(cache.asset_path(self.root,self.entry).read_bytes(),self.data)

    def test_bad_asset_hash_never_replaces_a_file_with_bad_bytes(self):
        self.entry['sha256']='0'*64
        self.write_manifests()
        with patch.object(cache,'fetch',return_value=self.package):
            with self.assertRaisesRegex(ValueError,'pinned asset'):
                cache.prepare(self.root,download=True,progress=lambda _:None)
        self.assertFalse(cache.asset_path(self.root,self.entry).exists())

    def test_failed_download_and_path_escape_do_not_leave_partial_assets(self):
        with patch.object(cache,'fetch',side_effect=OSError('offline')):
            with self.assertRaises(OSError):cache.prepare(self.root,download=True,progress=lambda _:None)
        self.assertEqual([p.name for p in (self.library/'blobs').iterdir()],['.gdignore'])
        self.entry['file']='../outside.png';self.write_manifests()
        with self.assertRaises(ValueError):cache.prepare(self.root,download=True)

    def test_registered_assets_use_their_own_download_and_content_hash(self):
        self.sources['pack']=dict(adapter='registered')
        self.entry['download']='https://example.com/picture.png'
        self.write_manifests()
        with patch.object(cache,'fetch',return_value=self.data) as fetch:
            cache.prepare(self.root,download=True,progress=lambda _:None)
            fetch.assert_called_once_with(self.entry['download'],self.entry['sha256'])

    def test_non_https_and_mismatched_downloads_are_rejected(self):
        with self.assertRaises(ValueError):cache.fetch('http://example.com/a','0'*64)
        class Response(io.BytesIO):url='https://example.com/a'
        with patch('urllib.request.urlopen',return_value=Response(b'wrong')):
            with self.assertRaisesRegex(ValueError,'hash'):cache.fetch('https://example.com/a','0'*64)


if __name__=='__main__':unittest.main()
