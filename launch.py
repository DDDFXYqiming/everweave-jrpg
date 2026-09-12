#!/usr/bin/env python3
"""Launch Godot and its local state helper, preparing missing local asset caches.
The paid API credential is entered in the game (or supplied by DEEPSEEK_API_KEY).
The only command-line token is a per-launch local loopback session credential.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from engine.server import GameServer, data_dir


def find_godot(explicit: str | None) -> str | None:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    elif os.environ.get('GODOT_BIN'):
        candidates.append(os.environ['GODOT_BIN'])
    else:
        for executable in ('godot', 'godot4', 'Godot'):
            found = shutil.which(executable)
            if found:
                candidates.append(found)
        # User can simply put the official Windows executable beside this script or in tools/.
        for folder in (ROOT, ROOT / 'tools'):
            candidates.extend(str(p) for p in sorted(folder.glob('Godot*_console.exe'), reverse=True))
            candidates.extend(str(p) for p in sorted(folder.glob('Godot*.exe'), reverse=True) if '_console' not in p.name)
            candidates.extend(str(p) for p in sorted(folder.glob('Godot*_linux.x86_64'), reverse=True))
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path.resolve())
        found = shutil.which(candidate)
        if found:
            return found
    return None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description='Everweave / 未写之境')
    p.add_argument('--godot', help='Path to the Godot 4 Standard executable')
    p.add_argument('--data-dir', type=Path, default=data_dir(), help='Save folder (outside the repository)')
    p.add_argument('--server-only', action='store_true', help='Run the local helper for editor F6; no Godot process')
    p.add_argument('--headless-smoke', action='store_true', help='Run the real Godot client headlessly for 120 frames')
    p.add_argument('--demo', action='store_true', help='Create an offline demo if no save exists; no network calls')
    args = p.parse_args(argv)
    if sys.version_info < (3, 11):
        print('Python 3.11 or newer is required.', file=sys.stderr)
        return 2
    executable = find_godot(args.godot)
    if not executable and not args.server_only:
        print('Godot 4 Standard was not found. Download it from the official Godot site.', file=sys.stderr)
        print('Then: python launch.py --godot "Godot.exe"', file=sys.stderr)
        print('Or set GODOT_BIN / place the official executable in this project folder.', file=sys.stderr)
        return 2
    args.data_dir = args.data_dir.expanduser().resolve()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    # Exclusive slot lock prevents two local helpers from editing the same SQLite world.
    lock_path = args.data_dir / 'instance.lock'
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        print(f'Another instance may be using this save folder: {args.data_dir}', file=sys.stderr)
        print('Close it first. After an abnormal shutdown, remove instance.lock only after confirming no instance is running.', file=sys.stderr)
        return 3
    os.write(lock_fd, str(os.getpid()).encode())
    os.close(lock_fd)
    server = None
    worker = None
    child = None
    runtime_file = args.data_dir / 'runtime.json'
    code = 0
    try:
        # Resolve the versioned manifests before opening a world. Existing
        # verified assets take an offline fast path; no repository metadata changes.
        from engine.asset_cache import prepare
        result = prepare(download=True, progress=lambda message: print(message, flush=True))
        print(f'Local asset cache ready: {result["assets"]} entries.', flush=True)
        token = secrets.token_urlsafe(32)
        server = GameServer(('127.0.0.1', 0), args.data_dir / 'world.sqlite3', token)
        url = f'http://127.0.0.1:{server.server_port}'
        runtime_file.write_text(json.dumps({'url': url, 'token': token}), encoding='utf-8')
        if os.name != 'nt':
            runtime_file.chmod(0o600)
        if args.demo:
            with server.world.lock:
                if server.world.state is None:
                    server.world.start('一个永远下雨的蒸汽朋克岛国，我是失忆的帝国逃兵。')
                server.director.configure({'offline': True})
        server.director.start_worker()
        worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .15}, daemon=True)
        worker.start()
        print(f'Everweave local helper ready. Saves: {args.data_dir}', flush=True)
        print('No cloud requests until live mode is explicitly configured in the game.', flush=True)
        if args.server_only:
            print('Open project.godot and press F6. Ctrl+C stops the helper.', flush=True)
            while True:
                time.sleep(1)
        else:
            # Import PNG/WAV resources before opening the game, including first launch from source.
            import_result = subprocess.run([executable, '--headless', '--editor', '--path', str(ROOT), '--import', '--quit'], cwd=ROOT, check=False)
            if import_result.returncode:
                print('Godot resource import failed. Check the messages above.', file=sys.stderr)
                return import_result.returncode
            command = [executable, '--path', str(ROOT)]
            if args.headless_smoke:
                command += ['--headless', '--quit-after', '120']
            command += ['--', '--backend-url=' + url, '--session-token=' + token]
            child = subprocess.Popen(command, cwd=ROOT)
            code = child.wait()
    except KeyboardInterrupt:
        code = 0
    except (OSError, ValueError) as exc:
        print(f'Cannot start Everweave: {exc}', file=sys.stderr)
        code = 1
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=4)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        if server:
            server.director.stop()
            if worker and worker.is_alive():
                server.shutdown()
                worker.join(timeout=2)
            server.server_close()
            # A daemon network call may still be unwinding. Process exit safely releases SQLite.
            if not any(worker.is_alive() for worker in server.director.threads):
                server.world.store.close()
        runtime_file.unlink(missing_ok=True)
        lock_path.unlink(missing_ok=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
