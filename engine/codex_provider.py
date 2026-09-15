"""Codex app-server transport using an existing ChatGPT subscription login.

No platform API keys, OAuth token extraction, model fallback or paid-provider
fallback. Each game request uses an ephemeral, tool-disabled conversation.
"""
from collections import deque
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import tomllib

MODEL = 'gpt-5.6-luna'
EFFORT = 'high'


class CodexError(RuntimeError):
    usage = None


def executable():
    explicit = os.environ.get('EVERWEAVE_CODEX_BIN')
    if explicit:
        path = Path(explicit)
        if path.is_file() and path.suffix.lower() not in ('.cmd', '.bat', '.ps1'):return str(path)
        raise CodexError('EVERWEAVE_CODEX_BIN must point to the Codex executable.')
    if os.name == 'nt':
        wrapper = shutil.which('codex.cmd')
        if wrapper:
            package = Path(wrapper).parent / 'node_modules' / '@openai' / 'codex' / 'node_modules' / '@openai'
            matches = list(package.glob('codex-win32-*/vendor/*/bin/codex.exe'))
            if matches:return str(matches[0])
        found = shutil.which('codex.exe')
    else:found = shutil.which('codex')
    if not found:raise CodexError('Codex CLI was not found. Install it and sign in with ChatGPT first.')
    return found


def process_config():
    # Read config structure only to disable inherited MCP servers in this child.
    # Never read auth.json or copy subscription credentials into the game.
    home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    config = {}
    path = home / 'config.toml'
    if path.exists():config = tomllib.loads(path.read_text(encoding='utf-8'))
    if config.get('forced_login_method')=='api':
        raise CodexError('Codex is configured for API-only login. Subscription generation stopped without changing login configuration.')
    disabled = ('shell_tool','unified_exec','apps','plugins','multi_agent','multi_agent_v2',
                'browser_use','computer_use','image_generation','view_image','memories',
                'skill_search','code_mode','code_mode_host','goals','hooks','workspace_dependencies')
    values = {'model_provider':'openai', 'web_search':'disabled', 'project_doc_max_bytes':0,
              'model_reasoning_effort':EFFORT, 'model':MODEL}
    values.update({'features.' + key:False for key in disabled})
    for name in config.get('mcp_servers', {}):
        if not re.fullmatch(r'[A-Za-z0-9_-]+',name):raise CodexError('An inherited MCP name cannot be safely disabled by this CLI version.')
        values['mcp_servers.'+name+'.enabled'] = False
    return values


class RPC:
    def __init__(self, cwd, timeout=300, cancel=None):
        args = [executable(), 'app-server', '--stdio']
        for key,value in process_config().items():args += ['-c', key+'='+json.dumps(value)]
        env = dict(os.environ)
        # An exported key must never silently switch billing away from ChatGPT.
        for key in ('OPENAI_API_KEY','CODEX_API_KEY','OPENAI_BASE_URL'):env.pop(key, None)
        env['RUST_LOG'] = 'error'
        self.process = subprocess.Popen(args,cwd=cwd,env=env,stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.queue = queue.Queue();self.saved=deque();self.sequence=0
        self.deadline=time.monotonic()+timeout
        self.cancel=cancel
        def read():
            try:
                for line in self.process.stdout:
                    try:self.queue.put(json.loads(line))
                    except ValueError:continue
            finally:self.queue.put(None)
        def drain():
            for _ in self.process.stderr:pass  # Never publish raw provider diagnostics/credentials.
        self.reader=threading.Thread(target=read,daemon=True);self.reader.start()
        self.errors=threading.Thread(target=drain,daemon=True);self.errors.start()

    def send(self, message):
        try:self.process.stdin.write(json.dumps(message,ensure_ascii=False)+'\n');self.process.stdin.flush()
        except (OSError,ValueError):raise CodexError('Codex app-server connection closed.') from None

    def receive(self):
        remaining=self.deadline-time.monotonic()
        if remaining<=0:raise CodexError('Codex subscription request timed out; it was not replayed.')
        while True:
            if self.cancel is not None and self.cancel.is_set():raise CodexError('Codex generation was stopped with the game.')
            remaining=self.deadline-time.monotonic()
            if remaining<=0:raise CodexError('Codex subscription request timed out; it was not replayed.')
            try:message=self.queue.get(timeout=min(remaining,.25));break
            except queue.Empty:continue
        if message is None:raise CodexError('Codex app-server exited before completing the request.')
        if 'method' in message and 'id' in message:
            self.send(dict(id=message['id'],error=dict(code=-32601,message='Game generation does not execute tools or approvals.')))
            raise CodexError('Codex requested a tool/approval; this game transport only accepts generated content.')
        return message

    def call(self, method, params):
        self.sequence+=1;key=self.sequence
        self.send(dict(id=key,method=method,params=params))
        while True:
            message=self.receive()
            if message.get('id')==key:
                if 'error' in message:
                    # Error text may include caller data: expose only the operation and code.
                    raise CodexError(f'Codex {method} failed (code {message["error"].get("code")}); check CLI login, model access and version.')
                return message.get('result',{})
            self.saved.append(message)

    def initialize(self):
        self.call('initialize',dict(clientInfo=dict(name='everweave_local',title='Everweave',version='0.1.0'),capabilities=dict(experimentalApi=True)))
        self.send(dict(method='initialized',params={}))

    def close(self):
        if self.process.poll() is None:
            try:self.process.stdin.close();self.process.wait(timeout=3)
            except (OSError,subprocess.TimeoutExpired):self.process.kill();self.process.wait(timeout=5)
        self.reader.join(timeout=1);self.errors.join(timeout=1)
        for stream in (self.process.stdout,self.process.stderr):stream.close()


def preflight(rpc, model=MODEL, effort=EFFORT):
    account=rpc.call('account/read',{'refreshToken':False}).get('account') or {}
    if account.get('type')!='chatgpt':
        raise CodexError('ChatGPT subscription login required. Run codex login; API-key login is not accepted.')
    cursor=None;found=None
    while True:
        page=rpc.call('model/list',dict(limit=100,includeHidden=True,cursor=cursor))
        found=next((m for m in page.get('data',[]) if m.get('model')==model),None)
        cursor=page.get('nextCursor')
        if found or not cursor:break
    if not found:raise CodexError('The requested gpt-5.6-luna model is unavailable for this Codex login; no model fallback was used.')
    if effort not in [e.get('reasoningEffort') for e in found.get('supportedReasoningEfforts',[])]:
        raise CodexError('The requested reasoning effort is unavailable for this Codex model.')
    limits=rpc.call('account/rateLimits/read',{})
    buckets=[limits.get('rateLimits',{})]+list((limits.get('rateLimitsByLimitId') or {}).values())
    for bucket in buckets:
        if not isinstance(bucket,dict):continue
        for key in ('primary','secondary'):
            if (bucket.get(key) or {}).get('usedPercent',0)>=100:
                raise CodexError('Codex subscription usage limit reached. Wait for reset; no paid fallback was attempted.')
    return dict(auth='chatgpt',plan=account.get('planType'),model=model,effort=effort)


def probe():
    with tempfile.TemporaryDirectory(prefix='everweave-codex-') as cwd:
        rpc=RPC(cwd,timeout=45)
        try:rpc.initialize();return preflight(rpc)
        finally:rpc.close()


def close_json_containers(text):
    """Close at most four omitted terminal containers; never invent JSON values.

    Only accept a completed value followed by missing braces/brackets. Partial
    strings, missing values and mismatched delimiters remain validation errors.
    """
    try:json.loads(text);return text,0
    except ValueError:pass
    stack=[];quoted=False;escape=False
    for char in text:
        if quoted:
            if escape:escape=False
            elif char=='\\':escape=True
            elif char=='"':quoted=False
        elif char=='"':quoted=True
        elif char in '{[':stack.append(char)
        elif char in '}]':
            if not stack or stack.pop()!=('{' if char=='}' else '['):return text,0
    if quoted or not 1<=len(stack)<=4 or not text.rstrip().endswith(('}',']')):return text,0
    candidate=text+''.join('}' if char=='{' else ']' for char in reversed(stack))
    try:
        if not isinstance(json.loads(candidate),dict):return text,0
    except ValueError:return text,0
    return candidate,len(stack)


def generate(system, user, cfg):
    if cfg.get('model',MODEL)!=MODEL:raise CodexError('Subscription mode is pinned to gpt-5.6-luna.')
    effort=cfg.get('reasoning_effort',EFFORT)
    with tempfile.TemporaryDirectory(prefix='everweave-codex-') as cwd:
        rpc=RPC(cwd,cancel=cfg.get('_cancel_event'));usage={}
        try:
            rpc.initialize();metadata=preflight(rpc,MODEL,effort)
            result=rpc.call('thread/start',dict(model=MODEL,modelProvider='openai',allowProviderModelFallback=False,
                cwd=cwd,sandbox='read-only',approvalPolicy='never',ephemeral=True,serviceName='everweave',
                serviceTier='default',environments=[],dynamicTools=[],
                baseInstructions='You generate declarative game content. Return only the requested JSON. Do not use tools, access files, browse, or execute commands.',
                developerInstructions=system,config={'model_reasoning_effort':effort}))
            if result.get('model',MODEL)!=MODEL:raise CodexError('Codex returned a different model; generation stopped.')
            if result.get('modelProvider','openai')!='openai' or result.get('reasoningEffort',effort)!=effort:
                raise CodexError('Codex returned a different provider or reasoning effort; generation stopped.')
            thread=result['thread']['id']
            turn=rpc.call('turn/start',dict(threadId=thread,model=MODEL,effort=effort,serviceTierForTurn='default',input=[dict(type='text',text=user)]))
            turn_id=turn['turn']['id'];messages={};usage={}
            while True:
                event=rpc.saved.popleft() if rpc.saved else rpc.receive()
                method=event.get('method');params=event.get('params') or {}
                if params.get('threadId') not in (None,thread):continue
                item=params.get('item') or {}
                if method=='item/started' and item.get('type') in ('commandExecution','fileChange','mcpToolCall','dynamicToolCall','webSearch','imageGeneration','collabAgentToolCall'):
                    raise CodexError('A tool was requested during content generation; the request was stopped.')
                if method=='item/completed' and item.get('type')=='agentMessage' and item.get('phase')!='commentary':messages[item['id']]=item.get('text','')
                if method=='thread/tokenUsage/updated':usage=params.get('tokenUsage',{}).get('last',{})
                if method=='turn/completed' and params.get('turn',{}).get('id')==turn_id:
                    finished=params['turn']
                    if finished.get('status')!='completed':
                        raise CodexError('Codex generation did not complete. Check subscription limits and CLI connectivity; no paid fallback was used.')
                    break
            text='\n'.join(messages.values())
            if not text.strip():raise CodexError('Codex returned no final game content.')
            if len(text.encode('utf-8'))>128000:raise CodexError('Codex content exceeds the game response size limit.')
            text,closed=close_json_containers(text)
            return text,dict(input_tokens=usage.get('inputTokens',0),output_tokens=usage.get('outputTokens',0),
                reasoning_tokens=usage.get('reasoningOutputTokens',0),reasoning_observed=usage.get('reasoningOutputTokens',0)>0,
                cached_input_tokens=usage.get('cachedInputTokens',0),provider='codex_subscription',model=MODEL,effort=effort,auth=metadata['auth'],closed_json_containers=closed)
        except CodexError as exc:
            exc.usage=dict(input_tokens=usage.get('inputTokens',0),output_tokens=usage.get('outputTokens',0),reasoning_tokens=usage.get('reasoningOutputTokens',0),reasoning_observed=bool(usage.get('reasoningOutputTokens',0)))
            raise
        finally:rpc.close()
