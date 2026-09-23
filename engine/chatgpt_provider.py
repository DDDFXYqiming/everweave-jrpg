"""Direct ChatGPT subscription Responses SSE transport for game JSON."""
import json
from collections import Counter
import hashlib
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
import random
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
import uuid
from .subscription_auth import Store,SubscriptionError,refresh

MODEL='gpt-6-luna';MODELS=('gpt-5.6-luna',MODEL)
RESPONSES_URL='https://chatgpt.com/backend-api/codex/responses'
EFFORTS=('none','low','medium','high','xhigh','max')
_AUTH_LOCK=threading.Lock()


class DirectError(RuntimeError):
    def __init__(self,message,usage=None,category='provider',diagnostics=None,retry_after=None):
        super().__init__(message);self.usage=usage or {};self.category=category
        self.diagnostics=diagnostics or {};self.retry_after=retry_after


def usage(response,effort='high',model=MODEL):
    value=response.get('usage') or {};input_detail=value.get('input_tokens_details') or {};output_detail=value.get('output_tokens_details') or {}
    return dict(input_tokens=int(value.get('input_tokens',0) or 0),output_tokens=int(value.get('output_tokens',0) or 0),
        reasoning_tokens=int(output_detail.get('reasoning_tokens',0) or 0),cached_input_tokens=int(input_detail.get('cached_tokens',0) or 0),
        reasoning_observed=bool(output_detail.get('reasoning_tokens',0)),provider='chatgpt_subscription',model=model,effort=effort,
        reported_effort=(response.get('reasoning') or {}).get('effort'))


def content(response):
    parts=[]
    for item in response.get('output') or []:
        if not isinstance(item,dict) or item.get('type')!='message':continue
        for block in item.get('content') or []:
            if isinstance(block,dict) and block.get('type') in ('output_text','text') and block.get('text'):parts.append(str(block['text']))
    return ''.join(parts)


def classify(payload,status=None):
    text=json.dumps(payload,ensure_ascii=False).lower()
    if status==401 or any(v in text for v in ('invalid_token','access_token_expired','token_expired')):return 'auth'
    if status==402 or any(v in text for v in ('usage_limit','insufficient_quota','quota','credit balance')):return 'quota'
    if status==429 or 'rate_limit' in text:return 'rate_limit'
    if status and status>=500:return 'transient'
    return 'provider'


def retry_after(headers):
    try:value=headers.get('Retry-After')
    except AttributeError:return None
    try:return max(0.0,float(value))
    except (TypeError,ValueError):
        try:return max(0.0,(parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds())
        except (TypeError,ValueError,OverflowError):return None


def connection_category(error):
    reason=getattr(error,'reason',error)
    return 'provider' if isinstance(reason,(ssl.SSLCertVerificationError,ssl.CertificateError)) else 'transient'


def wait_retry(cancel,delay):
    if cancel is not None:return cancel.wait(delay)
    time.sleep(delay);return False


def set_read_timeout(response,seconds):
    """尽力让阻塞读取服从顶层任务的剩余时限。"""
    try:response.fp.raw._sock.settimeout(max(.1,min(180.0,seconds)))
    except (AttributeError,OSError):pass


def stream_request(token,system,user,cfg):
    audit=cfg.get('_audit');meta=cfg.get('_request_meta',{});progress=cfg.get('_codex_progress');cancel=cfg.get('_cancel_event')
    started=time.monotonic();last_event=started;last_log=started;first_delta=None;first_reasoning=None;chars=0;reasoning_chars=0;events=0;completed=None;deltas=[];kinds=Counter()
    deadline=float(cfg.get('_task_deadline',started+900));response=None
    effort=cfg.get('reasoning_effort','high');model=cfg.get('model',MODEL)
    body=dict(model=model,instructions=system,input=[dict(role='user',content=[dict(type='input_text',text=user+'\nReturn the complete result as one JSON object.')])],
        reasoning={'effort':effort},text={'format':{'type':'json_object'}},store=False,stream=True,
        prompt_cache_key='everweave-'+hashlib.sha256(system.encode()).hexdigest()[:32])
    headers={'Content-Type':'application/json','Accept':'text/event-stream','Authorization':'Bearer '+token.access_token,
        'ChatGPT-Account-Id':token.account_id,'originator':'Codex Everweave','User-Agent':'Codex Everweave','session_id':str(uuid.uuid4())}
    if not token.account_id:headers.pop('ChatGPT-Account-Id')
    if audit:audit.emit('chatgpt.request.started',**meta,model=model,effort=effort,system_chars=len(system),input_chars=len(user),client_context_limit_tokens=None,deadline_remaining=round(max(0,deadline-started),3))
    try:
        if started>=deadline:raise DirectError('ChatGPT generation exceeded the shared task deadline.',category='deadline')
        try:
            response=urllib.request.urlopen(urllib.request.Request(RESPONSES_URL,json.dumps(body,ensure_ascii=False).encode(),headers,method='POST'),timeout=max(1,min(180,deadline-started)))
        except urllib.error.HTTPError as exc:
            try:payload=json.loads(exc.read(65536))
            except Exception:payload={}
            raise DirectError('ChatGPT subscription HTTP '+str(exc.code)+'.',category=classify(payload,exc.code),diagnostics={'http_status':exc.code},retry_after=retry_after(exc.headers)) from None
        except (urllib.error.URLError,OSError,TimeoutError) as exc:
            raise DirectError('ChatGPT subscription connection failed.',category=connection_category(exc),diagnostics={'connection_error':type(getattr(exc,'reason',exc)).__name__}) from exc
        buffer=[]
        while True:
            if cancel is not None and cancel.is_set():raise DirectError('ChatGPT generation stopped with the game.',category='cancelled')
            if time.monotonic()>=deadline:raise DirectError('ChatGPT generation exceeded the shared task deadline.',category='deadline')
            set_read_timeout(response,deadline-time.monotonic())
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
            elif kind=='response.completed':
                completed=event.get('response')
                break
            elif kind in ('error','response.error','response.cancelled','response.failed','response.incomplete'):
                raise DirectError('ChatGPT subscription response did not complete.',category=classify(event))
            if last_event-last_log>=15:
                last_log=last_event;state=dict(stage='output' if chars else 'reasoning',elapsed_seconds=round(last_event-started,3),last_event_age=0,output_chars=chars,reasoning_chars=reasoning_chars,errors=0,retries=max(0,int(meta.get('transport_attempt',1))-1),deadline_remaining=round(max(0,deadline-last_event),1))
                if progress:progress(state)
                if audit:audit.emit('chatgpt.progress',**meta,**state)
        if not isinstance(completed,dict):raise DirectError('ChatGPT response.completed was missing.')
        if completed.get('status') not in (None,'completed') or completed.get('error'):raise DirectError('ChatGPT subscription response failed.',usage(completed,effort,model),classify(completed))
        if completed.get('model') and completed['model']!=model:raise DirectError('ChatGPT returned a different model; no fallback is allowed.')
        text=content(completed) or ''.join(deltas);stats=usage(completed,effort,model)
        if stats['reported_effort'] and stats['reported_effort']!=effort:
            raise DirectError('ChatGPT 返回了不同的思考等级，停止本次生成。',stats,category='configuration')
        if not text.strip():raise DirectError('ChatGPT returned no final game content.',stats)
        if len(text.encode())>128000:raise DirectError('ChatGPT game content exceeds 128 KB.',stats)
        from .codex_provider import close_json_containers
        text,closed=close_json_containers(text);stats['closed_json_containers']=closed
        if audit and closed:audit.emit('chatgpt.output.containers_closed',**meta,closed_containers=closed,response_chars=len(text))
        if audit:audit.emit('chatgpt.request.finished',**meta,status='completed',seconds=round(time.monotonic()-started,3),first_reasoning_seconds=first_reasoning,first_output_seconds=first_delta,events=events,event_counts=dict(kinds),response_chars=len(text),usage=stats,usage_unknown=False)
        return text,stats
    except DirectError as exc:
        usage_unknown=not bool(exc.usage) and (response is not None or exc.category=='transient')
        observed=dict(elapsed_seconds=round(time.monotonic()-started,3),events=events,event_counts=dict(kinds),output_chars=chars,reasoning_chars=reasoning_chars,first_reasoning_seconds=first_reasoning,first_output_seconds=first_delta,last_event_age=round(time.monotonic()-last_event,3),response_completed=completed is not None,usage_unknown=usage_unknown)
        exc.diagnostics={**observed,**exc.diagnostics}
        if audit:audit.emit('chatgpt.request.finished',**meta,status='failed',seconds=observed['elapsed_seconds'],first_reasoning_seconds=first_reasoning,first_output_seconds=first_delta,events=events,event_counts=dict(kinds),response_chars=chars,reasoning_chars=reasoning_chars,category=exc.category,error=str(exc),retry_after=exc.retry_after,usage=exc.usage,usage_unknown=observed['usage_unknown'],deadline_remaining=round(max(0,deadline-time.monotonic()),3))
        raise
    finally:
        if response is not None:response.close()


def generate(system,user,cfg):
    if cfg.get('model',MODEL) not in MODELS or cfg.get('reasoning_effort') not in EFFORTS:raise DirectError('订阅直连需要 Luna，思考等级可选 none/low/medium/high/xhigh/max。')
    injected=cfg.get('_subscription_token');store=Store(cfg.get('_subscription_store'))
    with _AUTH_LOCK:
        token=injected or store.load()
        if not token:raise DirectError('Everweave needs its own ChatGPT subscription authorization.',category='auth')
        if token.expired():
            if not token.refresh_token:raise DirectError('Temporary shared access expired; authorize Everweave.',category='auth')
            token=refresh(token);store.save(token)
    maximum=max(0,min(2,int(cfg.get('max_transport_retries',1))));transport_retries=0;unknown_usage_attempts=0;auth_refreshed=False
    local=dict(cfg);local['_request_meta']=dict(cfg.get('_request_meta',{}),transport_attempt=1,transport_max_attempts=maximum+1)
    while True:
        try:
            raw,stats=stream_request(token,system,user,local)
            stats.update(transport_retries=transport_retries,unknown_usage_attempts=unknown_usage_attempts,model_requests=1+transport_retries+int(auth_refreshed))
            return raw,stats
        except DirectError as exc:
            attempt_usage_unknown=bool(exc.diagnostics.get('usage_unknown',False))
            if attempt_usage_unknown:unknown_usage_attempts+=1
            reserve=local.get('_reserve_transport_retry')
            auth_retry=exc.category=='auth' and not auth_refreshed and not injected and bool(token.refresh_token) and callable(reserve)
            transport_retry=exc.category in ('transient','rate_limit') and transport_retries<maximum and callable(reserve)
            if not auth_retry and not transport_retry:
                exc.diagnostics.update(transport_retries=transport_retries,unknown_usage_attempts=unknown_usage_attempts,retries_exhausted=exc.category in ('transient','rate_limit'),last_call=local.get('_request_meta',{}).get('call'))
                raise
            delay=0.0 if auth_retry else exc.retry_after if exc.retry_after is not None else 2.0*(2**transport_retries)+random.uniform(0,.6)
            now=time.monotonic();deadline=float(local.get('_task_deadline',now+900));cancel=local.get('_cancel_event');audit=local.get('_audit');meta=local.get('_request_meta',{})
            if now+delay>=deadline:
                exc.diagnostics.update(transport_retries=transport_retries,unknown_usage_attempts=unknown_usage_attempts,retries_exhausted=True,deadline_remaining=max(0,deadline-now),last_call=meta.get('call'))
                raise
            if audit:audit.emit('chatgpt.retry.scheduled',**meta,next_attempt=int(meta.get('transport_attempt',1))+1,retry_kind='auth_refresh' if auth_retry else exc.category,delay_seconds=round(delay,3),error=str(exc),partial_output_chars=exc.diagnostics.get('output_chars',0),usage_unknown=attempt_usage_unknown,deadline_remaining=round(deadline-now,3))
            if wait_retry(cancel,delay):raise DirectError('ChatGPT generation stopped during retry wait.',category='cancelled',diagnostics={'last_call':meta.get('call')}) from None
            next_call=reserve(dict(category=exc.category,error=str(exc),usage_unknown=attempt_usage_unknown,component=meta.get('component'),previous_call=meta.get('call'),partial_output_chars=exc.diagnostics.get('output_chars',0),retry_kind='auth_refresh' if auth_retry else exc.category)) if reserve else None
            if next_call is None:
                exc.diagnostics.update(transport_retries=transport_retries,unknown_usage_attempts=unknown_usage_attempts,retries_exhausted=True,retry_blocked='budget_or_state',last_call=meta.get('call'))
                if audit:audit.emit('chatgpt.retry.exhausted',**meta,reason='budget_or_state',error=str(exc),usage_unknown=attempt_usage_unknown)
                raise
            if auth_retry:
                with _AUTH_LOCK:
                    latest=store.load()
                    if latest and latest.access_token!=token.access_token:token=latest
                    else:token=refresh(token);store.save(token)
                auth_refreshed=True
            else:transport_retries+=1
            local=dict(local);local['_request_meta']=dict(meta,call=next_call,transport_attempt=int(meta.get('transport_attempt',1))+1,transport_max_attempts=maximum+1)
            if audit:audit.emit('chatgpt.retry.started',**local['_request_meta'],retry_kind='auth_refresh' if auth_retry else exc.category,deadline_remaining=round(max(0,deadline-time.monotonic()),3))
