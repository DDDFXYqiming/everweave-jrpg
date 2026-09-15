"""Direct ChatGPT subscription Responses SSE transport for game JSON."""
import json
from collections import Counter
import hashlib
import socket
import threading
import time
import urllib.error
import urllib.request
import uuid
from .subscription_auth import Store,SubscriptionError,refresh

MODEL='gpt-5.6-luna';RESPONSES_URL='https://chatgpt.com/backend-api/codex/responses'
_AUTH_LOCK=threading.Lock()


class DirectError(RuntimeError):
    def __init__(self,message,usage=None,category='provider'):super().__init__(message);self.usage=usage or {};self.category=category


def usage(response):
    value=response.get('usage') or {};input_detail=value.get('input_tokens_details') or {};output_detail=value.get('output_tokens_details') or {}
    return dict(input_tokens=int(value.get('input_tokens',0) or 0),output_tokens=int(value.get('output_tokens',0) or 0),
        reasoning_tokens=int(output_detail.get('reasoning_tokens',0) or 0),cached_input_tokens=int(input_detail.get('cached_tokens',0) or 0),
        reasoning_observed=bool(output_detail.get('reasoning_tokens',0)),provider='chatgpt_subscription',model=MODEL,effort='high')


def content(response):
    parts=[]
    for item in response.get('output') or []:
        if not isinstance(item,dict) or item.get('type')!='message':continue
        for block in item.get('content') or []:
            if isinstance(block,dict) and block.get('type') in ('output_text','text') and block.get('text'):parts.append(str(block['text']))
    return ''.join(parts)


def classify(payload,status=None):
    text=json.dumps(payload,ensure_ascii=False).lower()
    if status in (401,403) or any(v in text for v in ('invalid_token','access_token_expired','unauthorized')):return 'auth'
    if status in (402,429) or any(v in text for v in ('usage_limit','quota','rate_limit')):return 'quota'
    if status and status>=500:return 'transient'
    return 'provider'


def stream_request(token,system,user,cfg):
    audit=cfg.get('_audit');meta=cfg.get('_request_meta',{});progress=cfg.get('_codex_progress');cancel=cfg.get('_cancel_event')
    started=time.monotonic();last_event=started;last_log=started;first_delta=None;first_reasoning=None;chars=0;reasoning_chars=0;events=0;completed=None;deltas=[];kinds=Counter()
    body=dict(model=MODEL,instructions=system,input=[dict(role='user',content=[dict(type='input_text',text=user+'\nReturn the complete result as one JSON object.')])],
        reasoning={'effort':'high'},text={'format':{'type':'json_object'}},store=False,stream=True,
        prompt_cache_key='everweave-'+hashlib.sha256(system.encode()).hexdigest()[:32])
    headers={'Content-Type':'application/json','Accept':'text/event-stream','Authorization':'Bearer '+token.access_token,
        'ChatGPT-Account-Id':token.account_id,'originator':'Codex Everweave','User-Agent':'Codex Everweave','session_id':str(uuid.uuid4())}
    if not token.account_id:headers.pop('ChatGPT-Account-Id')
    if audit:audit.emit('chatgpt.request.started',**meta,model=MODEL,effort='high',system_chars=len(system),input_chars=len(user))
    try:
        response=urllib.request.urlopen(urllib.request.Request(RESPONSES_URL,json.dumps(body,ensure_ascii=False).encode(),headers,method='POST'),timeout=180)
    except urllib.error.HTTPError as exc:
        try:payload=json.loads(exc.read(65536))
        except Exception:payload={}
        raise DirectError('ChatGPT subscription HTTP '+str(exc.code)+'.',category=classify(payload,exc.code)) from None
    except (urllib.error.URLError,OSError,TimeoutError) as exc:raise DirectError('ChatGPT subscription connection failed.',category='transient') from exc
    try:
        buffer=[]
        while True:
            if cancel is not None and cancel.is_set():raise DirectError('ChatGPT generation stopped with the game.')
            if time.monotonic()-started>900:raise DirectError('ChatGPT generation exceeded the 15-minute hard limit.')
            try:raw=response.readline()
            except (OSError,socket.timeout) as exc:raise DirectError('ChatGPT stream produced no event for 3 minutes.',category='transient') from exc
            if not raw:
                if completed is None:raise DirectError('ChatGPT stream ended before response.completed.',category='transient')
                break
            line=raw.decode('utf8',errors='replace').rstrip('\r\n')
            if line.startswith('data:'):buffer.append(line[5:].lstrip())
            if line and not line.startswith('data:'):continue
            if not buffer:continue
            joined='\n'.join(buffer);buffer=[]
            if joined=='[DONE]':
                if completed is not None:break
                continue
            try:event=json.loads(joined)
            except ValueError:raise DirectError('ChatGPT returned an invalid SSE event.') from None
            last_event=time.monotonic();events+=1;kind=str(event.get('type',''));kinds[kind]+=1
            if kind=='response.output_text.delta':
                delta=str(event.get('delta') or '');deltas.append(delta);chars+=len(delta)
                if first_delta is None:
                    first_delta=round(last_event-started,3)
                    if audit:audit.emit('chatgpt.output.started',**meta,seconds=first_delta)
            elif 'reasoning' in kind and isinstance(event.get('delta'),str):
                reasoning_chars+=len(event['delta'])
                if first_reasoning is None:
                    first_reasoning=round(last_event-started,3)
                    if audit:audit.emit('chatgpt.reasoning.started',**meta,seconds=first_reasoning)
            elif kind=='response.completed':completed=event.get('response')
            elif kind in ('error','response.error','response.cancelled','response.failed','response.incomplete'):
                raise DirectError('ChatGPT subscription response did not complete.',category=classify(event))
            if last_event-last_log>=15:
                last_log=last_event;state=dict(stage='output' if chars else 'reasoning',elapsed_seconds=round(last_event-started,3),last_event_age=0,output_chars=chars,reasoning_chars=reasoning_chars,errors=0,retries=0)
                if progress:progress(state)
                if audit:audit.emit('chatgpt.progress',**meta,**state)
        if not isinstance(completed,dict):raise DirectError('ChatGPT response.completed was missing.')
        if completed.get('status') not in (None,'completed') or completed.get('error'):raise DirectError('ChatGPT subscription response failed.',usage(completed),classify(completed))
        if completed.get('model') and completed['model']!=MODEL:raise DirectError('ChatGPT returned a different model; no fallback is allowed.')
        text=content(completed) or ''.join(deltas);stats=usage(completed)
        if not text.strip():raise DirectError('ChatGPT returned no final game content.',stats)
        if len(text.encode())>128000:raise DirectError('ChatGPT game content exceeds 128 KB.',stats)
        from .codex_provider import close_json_containers
        text,closed=close_json_containers(text);stats['closed_json_containers']=closed
        if audit:audit.emit('chatgpt.request.finished',**meta,status='completed',seconds=round(time.monotonic()-started,3),first_reasoning_seconds=first_reasoning,first_output_seconds=first_delta,events=events,event_counts=dict(kinds),response_chars=len(text),usage=stats)
        return text,stats
    except DirectError as exc:
        if audit:audit.emit('chatgpt.request.finished',**meta,status='failed',seconds=round(time.monotonic()-started,3),first_reasoning_seconds=first_reasoning,first_output_seconds=first_delta,events=events,event_counts=dict(kinds),response_chars=chars,category=exc.category,usage=exc.usage)
        raise
    finally:response.close()


def generate(system,user,cfg):
    if cfg.get('model',MODEL)!=MODEL or cfg.get('reasoning_effort')!='high':raise DirectError('Direct subscription mode is fixed to GPT-5.6 Luna / high.')
    injected=cfg.get('_subscription_token');store=Store(cfg.get('_subscription_store'))
    with _AUTH_LOCK:
        token=injected or store.load()
        if not token:raise DirectError('Everweave needs its own ChatGPT subscription authorization.',category='auth')
        if token.expired():
            if not token.refresh_token:raise DirectError('Temporary shared access expired; authorize Everweave.',category='auth')
            token=refresh(token);store.save(token)
    try:return stream_request(token,system,user,cfg)
    except DirectError as exc:
        if exc.category!='auth' or injected or not token.refresh_token:raise
        with _AUTH_LOCK:
            latest=store.load()
            if latest and latest.access_token!=token.access_token:token=latest
            else:token=refresh(token);store.save(token)
        return stream_request(token,system,user,cfg)
