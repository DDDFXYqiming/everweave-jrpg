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
hybrid_test='--hybrid' in sys.argv
adventure_test='--adventure' in sys.argv
if content_test:(ROOT/'userdata/content-e2e').mkdir(parents=True,exist_ok=True)
if hybrid_test:(ROOT/'userdata/hybrid-e2e').mkdir(parents=True,exist_ok=True)
if adventure_test:(ROOT/'userdata/adventure-e2e').mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as td:
    server=GameServer(('127.0.0.1',0),Path(td)/'world.sqlite3',secrets.token_urlsafe(32))
    if adventure_test:
        sys.path.insert(0,str(ROOT/'tests'))
        from adventure_fixtures import adventure_plan,authored_adventure_region
        server.world.start('Adventure native acceptance',authored=True,planned=True)
        server.world.apply_patch(adventure_plan(),server.world.context(kind='campaign'))
        for rid in list(server.world.state['topology']):server.world.apply_patch(authored_adventure_region(server.world,rid),server.world.context(rid))
    if hybrid_test:
        sys.path.insert(0,str(ROOT/'tests'))
        from hybrid_fixtures import hybrid_patch
        server.world.start('Hybrid native acceptance',authored=True)
        server.world.apply_patch(hybrid_patch(),server.world.context())
    if content_test:
        sys.path.insert(0,str(ROOT/'tests'))
        from content_fixtures import authored_patch
        server.world.start('Native executable content acceptance')
        server.world.apply_patch(authored_patch(),server.world.context())
        from engine.schema import InvalidPatch
        from engine.director import ProviderError
        target=server.world.state['topology']['r0']['children'][0]
        server.director._failure(InvalidPatch('ambiguous item identity',path='region.items[2].id',category='reference'),server.world.context(target))
        server.director._failure(ProviderError('test-only unavailable provider'),server.world.context(kind='reaction'))
    fixture_stop=threading.Event()
    fixture_worker=None
    if content_test:
        def ready_waiting_exit():
            # Simulate a model response arriving while the native wait panel is
            # open. No test-only HTTP endpoint and no cloud/provider request.
            while not fixture_stop.wait(.02):
                with server.world.lock:
                    waiting=server.world.state['ui'].get('kind')=='pending_exit'
                if waiting:
                    if fixture_stop.wait(.6):return
                    with server.world.lock:
                        server.world.apply_patch(authored_patch(),server.world.context(target),'test_fixture')
                    return
        fixture_worker=threading.Thread(target=ready_waiting_exit,daemon=True)
        fixture_worker.start()
    server.director.start_worker()
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        script='native_adventure_e2e' if adventure_test else 'native_hybrid_e2e' if hybrid_test else 'native_content_e2e' if content_test else 'native_e2e'
        command=[find_godot(None),'--path',str(ROOT),'--script',f'res://tests/{script}.gd']
        if '--headless' in sys.argv: command+=['--headless']
        command+=['--','--backend-url=http://127.0.0.1:'+str(server.server_port),'--session-token='+server.token]
        try:
            result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=150)
        except subprocess.TimeoutExpired as exc:
            for output in (exc.stdout,exc.stderr):
                if output:print(output.decode('utf-8',errors='replace') if isinstance(output,bytes) else output)
            raise RuntimeError('Native test exceeded its deadline; see captured output') from None
        print(result.stdout);print(result.stderr)
        marker='NATIVE_ADVENTURE_E2E_OK' if adventure_test else 'NATIVE_HYBRID_E2E_OK' if hybrid_test else 'NATIVE_CONTENT_E2E_OK' if content_test else 'NATIVE_E2E_OK'
        assert result.returncode==0 and marker in result.stdout and 'SCRIPT ERROR' not in result.stderr
        assert server.director.calls==0
    finally:
        fixture_stop.set()
        if fixture_worker:fixture_worker.join(timeout=2)
        server.director.stop();server.shutdown();worker.join();server.server_close();server.world.store.close()
