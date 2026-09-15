"""Native integration test with an isolated standard-library server, no cloud calls."""
from pathlib import Path
import secrets
import sqlite3
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
threat_test='--threat' in sys.argv
generated_test='--generated' in sys.argv
generated_source=None
if generated_test:
    try:generated_source=Path(sys.argv[sys.argv.index('--generated')+1]).resolve()
    except (IndexError,ValueError):raise SystemExit('--generated requires an existing world.sqlite3 path')
    if not generated_source.is_file():raise SystemExit('generated world database does not exist')
if content_test:(ROOT/'userdata/content-e2e').mkdir(parents=True,exist_ok=True)
if hybrid_test:(ROOT/'userdata/hybrid-e2e').mkdir(parents=True,exist_ok=True)
if adventure_test:(ROOT/'userdata/adventure-e2e').mkdir(parents=True,exist_ok=True)
if threat_test:(ROOT/'userdata/threat-e2e').mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as td:
    save_path=Path(td)/'world.sqlite3'
    if generated_source:
        source=sqlite3.connect(generated_source.as_uri()+'?mode=ro',uri=True);destination=sqlite3.connect(save_path)
        try:source.backup(destination)
        finally:source.close();destination.close()
    server=GameServer(('127.0.0.1',0),save_path,secrets.token_urlsafe(32))
    if adventure_test or threat_test:
        sys.path.insert(0,str(ROOT/'tests'))
        from adventure_fixtures import adventure_plan,authored_adventure_region
        server.world.start('Adventure native acceptance',authored=True,planned=True)
        plan=adventure_plan()
        if threat_test:
            plan['campaign']['game_spec']['systems']['combat']=True
            plan['campaign']['game_spec']['resources'].append(dict(id='hp',label='体力',initial=24,max=24,display='bar'))
        server.world.apply_patch(plan,server.world.context(kind='campaign'))
        for rid in list(server.world.state['topology']):
            raw=authored_adventure_region(server.world,rid)
            if threat_test and rid=='r0':
                raw['region']['entities'].append(dict(id='guard',kind='enemy',name='巡逻守卫',at=[12,7],sprite='enemy',footprint=[2,2],stats=dict(hp=12,attack=2),behavior=dict(mode='hunt',radius=8,pace=1)))
                raw['region']['program']['actions'].append(dict(id='strike',label='反击',scope='combat',target='player',effects=[dict(op='stat',target='enemy',name='hp',delta=-4)]))
            server.world.apply_patch(raw,server.world.context(rid))
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
        script='native_generated_region' if generated_test else 'native_threat_e2e' if threat_test else 'native_adventure_e2e' if adventure_test else 'native_hybrid_e2e' if hybrid_test else 'native_content_e2e' if content_test else 'native_e2e'
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
        marker='NATIVE_GENERATED_REGION_OK' if generated_test else 'NATIVE_THREAT_E2E_OK' if threat_test else 'NATIVE_ADVENTURE_E2E_OK' if adventure_test else 'NATIVE_HYBRID_E2E_OK' if hybrid_test else 'NATIVE_CONTENT_E2E_OK' if content_test else 'NATIVE_E2E_OK'
        assert result.returncode==0 and marker in result.stdout and 'SCRIPT ERROR' not in result.stderr
        assert server.director.calls==0
    finally:
        fixture_stop.set()
        if fixture_worker:fixture_worker.join(timeout=2)
        server.director.stop();server.shutdown();worker.join();server.server_close();server.world.store.close()
