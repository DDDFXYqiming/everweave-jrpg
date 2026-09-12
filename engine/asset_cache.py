"""Materialize ignored local assets from the committed manifests, without editing them."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MAX_PACKAGE = 20_000_000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def asset_path(root, entry):
    path = (root / entry['file']).resolve()
    if not path.is_relative_to((root / 'assets/library/blobs').resolve()):
        raise ValueError('Asset path escapes the local cache')
    return path


def valid_file(path, sha, size=None):
    return (path.is_file() and (size is None or path.stat().st_size == size)
            and digest(path.read_bytes()) == sha)


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique staging names also allow two different save launchers to prepare
    # the same immutable cache safely. Never expose partially downloaded files.
    fd, name = tempfile.mkstemp(prefix='.asset-', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def fetch(url, sha):
    if not isinstance(url, str) or not url.startswith('https://'):
        raise ValueError('Asset manifests require a public HTTPS download URL')
    request = urllib.request.Request(url, headers={'User-Agent': 'Everweave-Asset-Cache/1.0'})
    with urllib.request.urlopen(request, timeout=45) as response:
        if not response.url.startswith('https://'):
            raise ValueError('Asset download redirected away from HTTPS')
        data = response.read(MAX_PACKAGE + 1)
    if len(data) > MAX_PACKAGE or digest(data) != sha:
        raise ValueError('Asset download size/hash differs from its pinned manifest')
    return data


def pillow(root, install):
    target = root / 'userdata/library-tools/pillow-12.2.0'
    if target.is_dir():
        sys.path.insert(0, str(target))
    try:
        from PIL import Image
    except ImportError:
        if not install:
            raise ValueError('Rebuilding composed images needs Pillow; use --download to prepare it locally') from None
        print('Preparing local image assembly tool (Pillow 12.2.0)...', flush=True)
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check',
                            '--only-binary=:all:', '--no-deps', '--upgrade', '--target', str(target),
                            'Pillow==12.2.0'], check=True)
        except subprocess.CalledProcessError as error:
            raise ValueError('Local image tool preparation failed; check pip/network and retry startup') from error
        sys.path.insert(0, str(target))
        from PIL import Image
    return Image


def prepare(root=ROOT, *, download=False, cache=None, verify_only=False, progress=print):
    root = Path(root).resolve()
    library = root / 'assets/library'
    entries = json.loads((library / 'index.json').read_text(encoding='utf-8'))['assets']
    sources = json.loads((library / 'sources.json').read_text(encoding='utf-8'))
    missing = {key: entry for key, entry in entries.items()
               if not valid_file(asset_path(root, entry), entry['sha256'], entry['bytes'])}
    if verify_only:
        if missing:
            raise ValueError(f'{len(missing)} assets missing or damaged; run python -m engine.asset_cache --download')
        return dict(assets=len(entries),prepared=0)
    # The client decodes these raw files directly. Importing every cached PNG/
    # OGG again as Godot resources adds duplicate disk use and startup work.
    for folder in (library/'blobs',root/'userdata'):
        marker=folder/'.gdignore'
        if not marker.exists():atomic_write(marker,b'')
    cache = Path(cache) if cache else root / 'userdata/library-ingest'
    packages = {}
    for key, entry in missing.items():
        path = asset_path(root, entry)
        if valid_file(path, entry['sha256'], entry['bytes']):
            continue  # Another entry or launcher already materialized these bytes.
        source = sources[entry['source']]
        if source.get('adapter') == 'registered':
            if not download or not entry.get('download'):
                raise ValueError(f'{key}: missing cache; a registered asset needs its own download URL')
            progress(f'Downloading asset {key}...')
            data = fetch(entry['download'], entry['sha256'])
        else:
            sha = source['sha256']
            if sha not in packages:
                package_path = cache / (sha + source['extension'])
                # Reuse packages downloaded by the older development importer.
                old_path = cache / (entry['source'] + source['extension'])
                if valid_file(package_path, sha):
                    packages[sha] = package_path.read_bytes()
                elif valid_file(old_path, sha):
                    packages[sha] = old_path.read_bytes()
                else:
                    if not download:
                        raise ValueError(f'Missing source package: {entry["source"]}; use --download')
                    progress(f'Downloading asset pack: {source["title"]}...')
                    packages[sha] = fetch(source['download'], sha)
                    atomic_write(package_path, packages[sha])
            package = packages[sha]
            if source['extension'] == '.zip':
                with zipfile.ZipFile(io.BytesIO(package)) as archive:
                    def member(name):
                        info = archive.getinfo(name)
                        if info.file_size > MAX_PACKAGE:
                            raise ValueError('Asset archive member exceeds size limit')
                        return archive.read(info)
                    if 'source_member' in entry:
                        data = member(entry['source_member'])
                    elif 'derived_from_tiles' in entry:
                        Image = pillow(root, download)
                        canvas = Image.new('RGBA', tuple(entry['size']))
                        for y, row in enumerate(entry['derived_from_tiles']):
                            for x, tile in enumerate(row):
                                picture = Image.open(io.BytesIO(member(f'Tiles/tile_{tile:04d}.png'))).convert('RGBA')
                                canvas.alpha_composite(picture, (x*16, y*16))
                        output = io.BytesIO()
                        canvas.save(output, format='PNG')
                        data = output.getvalue()
                    else:
                        raise ValueError(f'{key}: no source member or assembly recipe')
            else:
                data = package
        if len(data) != entry['bytes'] or digest(data) != entry['sha256']:
            raise ValueError(f'{key}: reconstructed bytes differ from the pinned asset; cache not replaced')
        atomic_write(path, data)
    return dict(assets=len(entries),prepared=len(missing))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true', help='Download missing sources and locally bootstrap image assembly if needed')
    parser.add_argument('--verify', action='store_true', help='Verify the cache without network or writes')
    args = parser.parse_args()
    try:
        result = prepare(download=args.download, verify_only=args.verify)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Asset preparation failed: {error}\n')
    print('ASSET_CACHE_OK', json.dumps(result))


if __name__ == '__main__':
    main()
