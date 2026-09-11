"""Native integration test with an isolated standard-library server, no cloud calls."""
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine.server import GameServer
from launch import find_godot

(ROOT/'userdata/e2e').mkdir(parents=True,exist_ok=True)
content_test='--content' in sys.argv
if content_test:(ROOT/'userdata/content-e2e').mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as td:
    server=GameServer(('127.0.0.1',0),Path(td)/'world.sqlite3',secrets.token_urlsafe(32))
    if content_test:
        sys.path.insert(0,str(ROOT/'tests'))
        from content_fixtures import authored_patch
        server.world.start('Native executable content acceptance')
        server.world.apply_patch(authored_patch(),server.world.context())
    server.director.start_worker()
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        script='native_content_e2e' if content_test else 'native_e2e'
        command=[find_godot(None),'--path',str(ROOT),'--script',f'res://tests/{script}.gd']
        if '--headless' in sys.argv: command+=['--headless']
        command+=['--','--backend-url=http://127.0.0.1:'+str(server.server_port),'--session-token='+server.token]
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=150)
        print(result.stdout);print(result.stderr)
        marker='NATIVE_CONTENT_E2E_OK' if content_test else 'NATIVE_E2E_OK'
        assert result.returncode==0 and marker in result.stdout and 'SCRIPT ERROR' not in result.stderr
        assert server.director.calls==0
    finally:
        server.director.stop();server.shutdown();worker.join();server.server_close();server.world.store.close()
