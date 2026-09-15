"""Independent ChatGPT device OAuth and protected local credential storage."""
from dataclasses import asdict,dataclass
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

AUTH_BASE='https://auth.openai.com'
DEVICE_CODE_URL=AUTH_BASE+'/api/accounts/deviceauth/usercode'
DEVICE_TOKEN_URL=AUTH_BASE+'/api/accounts/deviceauth/token'
TOKEN_URL=AUTH_BASE+'/oauth/token'
VERIFY_URL=AUTH_BASE+'/codex/device'
CLIENT_ID='app_EMoamEEZ73f0CkXaXp7hrann'


class SubscriptionError(ValueError):pass


@dataclass
class Token:
    access_token:str
    refresh_token:str
    expires_at:float
    account_id:str=''
    def expired(self):return time.time()>=self.expires_at-60


@dataclass
class Login:
    verification_url:str
    user_code:str
    device_auth_id:str
    interval:float
    expires_at:float


def claims(token):
    try:
        part=token.split('.')[1];return json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4)))
    except Exception:return {}


def account_id(*tokens):
    for token in tokens:
        data=claims(token)
        if isinstance(data.get('chatgpt_account_id'),str):return data['chatgpt_account_id']
        auth=data.get('https://api.openai.com/auth')
        if isinstance(auth,dict) and isinstance(auth.get('chatgpt_account_id'),str):return auth['chatgpt_account_id']
        orgs=data.get('organizations')
        if isinstance(orgs,list) and orgs and isinstance(orgs[0],dict) and orgs[0].get('id'):return str(orgs[0]['id'])
    return ''


def expiry(access,expires_in=None):
    value=claims(access).get('exp')
    if isinstance(value,(int,float)) and value>0:return float(value)
    try:return time.time()+float(expires_in)
    except (TypeError,ValueError):return time.time()+3600


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise SubscriptionError('Subscription authentication redirect was refused.')


def request(url,data,form=False,timeout=30):
    body=(urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode())
    headers={'Accept':'application/json','Content-Type':'application/x-www-form-urlencoded' if form else 'application/json','User-Agent':'Everweave/0.1'}
    try:
        with urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url,body,headers,method='POST'),timeout=timeout) as response:
            return response.status,json.load(response)
    except urllib.error.HTTPError as exc:
        try:payload=json.loads(exc.read(65536))
        except Exception:payload={}
        return exc.code,payload
    except (OSError,urllib.error.URLError,TimeoutError) as exc:raise SubscriptionError('Subscription authentication connection failed.') from exc


def start_login():
    status,data=request(DEVICE_CODE_URL,{'client_id':CLIENT_ID})
    device=data.get('device_auth_id');code=data.get('user_code') or data.get('usercode')
    if status!=200 or not device or not code:raise SubscriptionError('Could not start ChatGPT device authorization.')
    return Login(VERIFY_URL,str(code),str(device),max(3,float(data.get('interval') or 5)),time.time()+float(data.get('expires_in') or 600))


def poll_login(login):
    if time.time()>login.expires_at:raise SubscriptionError('ChatGPT device authorization expired.')
    status,data=request(DEVICE_TOKEN_URL,{'device_auth_id':login.device_auth_id,'user_code':login.user_code})
    if status in (403,404):return None
    if status!=200:raise SubscriptionError('ChatGPT device authorization polling failed.')
    code=data.get('authorization_code');verifier=data.get('code_verifier')
    if not code or not verifier:return None
    status,data=request(TOKEN_URL,{'grant_type':'authorization_code','code':code,'redirect_uri':AUTH_BASE+'/deviceauth/callback','client_id':CLIENT_ID,'code_verifier':verifier},form=True)
    access=str(data.get('access_token') or '');refresh=str(data.get('refresh_token') or '');identity=str(data.get('id_token') or '')
    if status!=200 or not access or not refresh:raise SubscriptionError('ChatGPT authorization token exchange failed.')
    return Token(access,refresh,expiry(access,data.get('expires_in')),account_id(identity,access))


def refresh(token):
    status,data=request(TOKEN_URL,{'client_id':CLIENT_ID,'grant_type':'refresh_token','refresh_token':token.refresh_token,'scope':'openid profile email'},form=True)
    access=str(data.get('access_token') or '')
    if status!=200 or not access:raise SubscriptionError('ChatGPT subscription refresh failed; sign in again.')
    refresh_token=str(data.get('refresh_token') or token.refresh_token);identity=str(data.get('id_token') or '')
    return Token(access,refresh_token,expiry(access,data.get('expires_in')),account_id(identity,access) or token.account_id)


class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]


def protect(data):
    if os.name!='nt':return data
    buffer=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source),'Everweave ChatGPT subscription',None,None,None,1,ctypes.byref(target)):
        raise SubscriptionError('Windows could not protect the subscription credential.')
    try:return ctypes.string_at(target.data,target.size)
    finally:ctypes.windll.kernel32.LocalFree(target.data)


def unprotect(data):
    if os.name!='nt':return data
    buffer=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):
        raise SubscriptionError('The saved subscription credential cannot be opened by this Windows user.')
    try:return ctypes.string_at(target.data,target.size)
    finally:ctypes.windll.kernel32.LocalFree(target.data)


def default_path():
    root=Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) if os.name=='nt' else Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))
    return root/'EverweaveJRPG'/'chatgpt-subscription.bin'


class Store:
    def __init__(self,path=None):self.path=Path(path or default_path())
    def load(self):
        if not self.path.is_file():return None
        try:
            data=json.loads(unprotect(self.path.read_bytes()))
            token=Token(**data)
            return token if token.access_token and token.refresh_token else None
        except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc:raise SubscriptionError('Saved ChatGPT subscription credential is invalid.') from exc
    def save(self,token):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        data=protect(json.dumps(asdict(token),separators=(',',':')).encode())
        fd,name=tempfile.mkstemp(prefix='.subscription-',suffix='.tmp',dir=self.path.parent);temporary=Path(name)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(data)
            if os.name!='nt':temporary.chmod(0o600)
            try:temporary.replace(self.path)
            except OSError as exc:
                if os.name!='nt' or getattr(exc,'winerror',None)!=17:raise
                # Some redirected Windows profile folders report cross-volume
                # replacement even when both printed paths share a drive.
                # The payload is already user-DPAPI encrypted; replace it with a
                # flushed bounded write and let load() reject any interrupted file.
                with self.path.open('wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        finally:temporary.unlink(missing_ok=True)
    def forget(self):self.path.unlink(missing_ok=True)


class LoginManager:
    """One background device flow; public state never contains OAuth tokens."""
    def __init__(self,store=None):
        self.store=store or Store();self.lock=threading.Lock();self.login=None;self.error='';self.thread=None
        try:self.phase='ready' if self.store.load() else 'required'
        except SubscriptionError:self.phase='failed';self.error='Saved ChatGPT authorization needs to be replaced.'
    def public(self):
        with self.lock:
            value=dict(phase=self.phase,ready=self.phase=='ready',error=self.error)
            if self.phase=='pending' and self.login:
                value.update(verification_url=self.login.verification_url,user_code=self.login.user_code,expires_at=self.login.expires_at)
            return value
    def start(self):
        with self.lock:
            if self.phase in ('ready','pending'):return self.public_unlocked()
            self.login=start_login();self.phase='pending';self.error='';self.thread=threading.Thread(target=self._run,name='chatgpt-device-login',daemon=True);self.thread.start()
            return self.public_unlocked()
    def public_unlocked(self):
        value=dict(phase=self.phase,ready=self.phase=='ready',error=self.error)
        if self.phase=='pending' and self.login:value.update(verification_url=self.login.verification_url,user_code=self.login.user_code,expires_at=self.login.expires_at)
        return value
    def _run(self):
        try:
            while True:
                with self.lock:login=self.login
                token=poll_login(login)
                if token:
                    self.store.save(token)
                    with self.lock:self.phase='ready';self.login=None
                    return
                time.sleep(login.interval)
        except Exception as exc:
            with self.lock:self.phase='failed';self.error=str(exc);self.login=None
