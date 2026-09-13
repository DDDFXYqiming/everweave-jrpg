"""Loopback-only authenticated bridge. This is a local helper, not a hosted service."""
import argparse
import hmac
import json
import os
import secrets
import threading
import logging
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from .world import World,GameError
from .storage import Store,dumps
from .director import Director,ProviderError,official_deepseek
from .audit import AuditLog,NullAudit

def data_dir():
 if os.name=='nt': return Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'EverweaveJRPG'
 return Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'everweave-jrpg'

class GameServer(ThreadingHTTPServer):
 daemon_threads=True
 def __init__(self,address,save_path,token):
  if address[0]!='127.0.0.1': raise ValueError('Only IPv4 loopback binding is supported')
  self.token=token; self.world=World(Store(save_path)); self.director=Director(self.world); self.seen=OrderedDict()
  self.snapshot_sequence=0
  self.preference_keys=('offline','base_url','model','deepseek_options','reasoning_effort','max_calls','hybrid_content','language')
  self.preferences=dict(offline=False,base_url='https://api.deepseek.com',model='deepseek-flash',deepseek_options=True,reasoning_effort='low',max_calls=60,hybrid_content=True,language='zh')
  self.preference_path=None if str(save_path)==':memory:' else Path(save_path).with_name('settings.json')
  if self.preference_path and self.preference_path.exists():
   try:
    saved=json.loads(self.preference_path.read_text(encoding='utf-8'))
    if isinstance(saved,dict): self.preferences.update({k:saved[k] for k in self.preference_keys if k in saved})
   except (OSError,ValueError): pass
  super().__init__(address,Handler)
  self.audit=NullAudit() if str(save_path)==':memory:' else AuditLog(Path(save_path).parent/'logs')
  self.audit.add_secret(token);self.director.audit=self.audit
  self.audit.emit('server.started',port=self.server_port,world_loaded=bool(self.world.state))
 def server_close(self):
  super().server_close()
  if hasattr(self,'audit'):
   self.audit.emit('server.stopped');self.audit.close()
 def remember_configuration(self):
  self.preferences={k:self.director.cfg[k] for k in self.preference_keys}
  self.save_preferences()
 def save_preferences(self):
  if self.preference_path:
   temporary=self.preference_path.with_suffix('.tmp')
   temporary.write_text(dumps(self.preferences),encoding='utf-8'); temporary.replace(self.preference_path)
 def snapshot(self):
  s=self.world.snapshot(); s['director']=self.director.status()
  self.snapshot_sequence+=1; s['snapshot_sequence']=self.snapshot_sequence
  s['configuration']={k:(self.director.cfg or self.preferences)[k] for k in self.preference_keys}
  base=s['configuration']['base_url']
  s['configuration']['credential_available']=bool((self.director.cfg or {}).get('api_key') or (official_deepseek(base) and os.environ.get('DEEPSEEK_API_KEY')))
  return s

class Handler(BaseHTTPRequestHandler):
 server_version='EverweaveLocal/0.1'
 def log_message(self,*args): pass  # Never log secrets, prompts, URLs, request bodies or auth headers.
 def reply(self,status,value):
  body=dumps(value).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers()
  try: self.wfile.write(body)
  except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError): pass
 def authorized(self):
  expected='Bearer '+self.server.token; supplied=self.headers.get('Authorization','')
  # Web pages cannot use this API: no CORS; reject browser origins and foreign Host headers.
  host=self.headers.get('Host','').split(':')[0]
  return not self.headers.get('Origin') and host in ('127.0.0.1','localhost') and hmac.compare_digest(supplied.encode("utf-8"),expected.encode("utf-8"))
 def do_OPTIONS(self): self.reply(403,dict(error='Browser access is disabled.'))
 def do_GET(self):
  if not self.authorized(): self.reply(401,dict(error='Local session token required.')); return
  path=urlsplit(self.path)
  with self.server.world.lock:
   if path.path=='/state':self.reply(200,self.server.snapshot())
   elif path.path=='/atlas':
    from .read_views import atlas
    self.reply(200,atlas(self.server.world))
   elif path.path=='/journal':
    from .read_views import journal
    query=parse_qs(path.query)
    try:
     before=int(query['before'][0]) if 'before' in query else None
     self.reply(200,journal(self.server.world,query.get('tab',['history'])[0],before,int(query.get('limit',['30'])[0])))
    except ValueError as exc:self.reply(400,dict(error=str(exc)))
   else:self.reply(404,dict(error='Not found'))
 def do_POST(self):
  if not self.authorized(): self.reply(401,dict(error='Local session token required.')); return
  try:
   length=int(self.headers.get('Content-Length','0'))
   if not 0<length<=16000:
    # Drain only a bounded small rejected upload so Windows can deliver the 413
    # instead of resetting the socket while the local client is still sending.
    self.connection.settimeout(.5)
    if length>0:
     try: self.rfile.read(min(length,65536))
     except (TimeoutError,OSError): pass
    self.reply(413,dict(error='Request body limit exceeded')); return
   if self.headers.get('Content-Type','').split(';')[0]!='application/json': self.reply(415,dict(error='JSON required')); return
   self.connection.settimeout(5)
   raw=self.rfile.read(length)
   if len(raw)!=length: raise ValueError('incomplete request')
   data=json.loads(raw)
   if not isinstance(data,dict): raise ValueError('expected object')
  except (ValueError,UnicodeError,TimeoutError,OSError): self.reply(400,dict(error='Invalid request')); return
  server=self.server; w=server.world; d=server.director
  started=time.monotonic()
  action={key:data[key] for key in ('op','id','dx','dy','move','target','kind') if key in data}
  before={}
  try:
   with w.lock:
    before={key:(w.state or {}).get(key) for key in ('current','steps','story_revision')}
    before['player']={key:(w.state or {}).get('player',{}).get(key) for key in ('x','y','hp','mp','gold')}
    request_id=self.headers.get('X-Request-ID','')
    if request_id and request_id in server.seen:
     server.audit.emit('request.duplicate',route=self.path,request_id=request_id[:96])
     self.reply(200,server.snapshot()); return
    if self.path=='/start':
     if w.state and not data.get('replace_save',False): raise GameError('新世界会覆盖当前存档，请明确确认。')
     # Validate all inputs before replacing an existing save.
     setting=data.get('setting','')
     if not isinstance(setting,str) or not 3<=len(setting.strip())<=600: raise GameError('世界设定需要 3～600 个字符。')
     d.configure(data); w.start(setting,authored=not d.cfg['offline'],language=d.cfg['language'],planned=not d.cfg['offline']); server.seen.clear(); server.remember_configuration()
    elif self.path=='/configure': d.configure(data); server.remember_configuration()
    elif self.path=='/language':
     language=data.get('language')
     if language not in ('zh','en'):raise ValueError('Unsupported language')
     server.preferences['language']=language
     if d.cfg is not None:d.cfg['language']=language
     server.save_preferences()
    elif self.path=='/action': w.action(data)
    elif self.path=='/retry': d.retry(data.get('target'),data.get('kind'),data.get('mode','repair'))
    elif self.path=='/pause': d.paused=bool(data.get('paused',True))
    else: self.reply(404,dict(error='Not found')); return
    if request_id:
     server.seen[request_id]=True
     while len(server.seen)>512: server.seen.popitem(last=False)
    self.reply(200,server.snapshot())
    if self.path!='/state':
     after={key:(w.state or {}).get(key) for key in ('current','steps','story_revision')}
     after['player']={key:(w.state or {}).get('player',{}).get(key) for key in ('x','y','hp','mp','gold')}
     server.audit.emit('action.completed' if self.path=='/action' else 'request.completed',
       route=self.path,request_id=request_id[:96],action=action,before=before,after=after,
       ui_kind=(w.state or {}).get('ui',{}).get('kind'),milliseconds=round((time.monotonic()-started)*1000,2))
   d.wake.set()
  except (GameError,ProviderError,ValueError,TypeError,KeyError) as exc:
   server.audit.emit('action.rejected',level=logging.WARNING,exception=exc,route=self.path,action=action,error=str(exc),before=before)
   self.reply(400,dict(error=str(exc)[:260]))
  except Exception as exc:
   server.audit.emit('action.error',level=logging.ERROR,exception=exc,route=self.path,action=action,before=before)
   self.reply(500,dict(error='Local engine error. Save remains on this computer.'))

def main():
 p=argparse.ArgumentParser(); p.add_argument('--port',type=int,default=8765); p.add_argument('--data-dir',type=Path,default=data_dir()); args=p.parse_args()
 args.data_dir.mkdir(parents=True,exist_ok=True); token=secrets.token_urlsafe(32)
 server=GameServer(('127.0.0.1',args.port),args.data_dir/'world.sqlite3',token)
 runtime=args.data_dir/'runtime.json'; runtime.write_text(dumps(dict(url=f'http://127.0.0.1:{server.server_port}',token=token)),encoding='utf-8')
 if os.name!='nt': runtime.chmod(0o600)
 server.director.start_worker()
 print('Everweave local bridge is ready. Start Godot through launch.py. No network LLM calls until configured.',flush=True)
 try: server.serve_forever(poll_interval=.2)
 except KeyboardInterrupt: pass
 finally: server.director.stop(); server.server_close(); runtime.unlink(missing_ok=True)

if __name__=='__main__': main()
