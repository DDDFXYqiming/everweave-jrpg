"""可选的同源本机 Web 客户端；复用原来的权威动作接口。"""
import copy
import hmac
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit,unquote
from .server import GameServer,Handler

ROOT=Path(__file__).resolve().parents[1]


class WebGameServer(GameServer):
    def __init__(self,address,save_path,token):
        super().__init__(address,save_path,token,WebHandler)
        self.cookie_name='everweave_'+self.instance_id[:12]

    def snapshot(self):
        value=super().snapshot()
        item_fields=('id','name','description','kind','quantity','equipped','price','icon_visual','usable')
        value['inventory']=[{k:v for k,v in item.items() if k in item_fields} for item in value.get('inventory',[])]
        if value.get('ui',{}).get('goods'):
            value['ui']['goods']=[{k:v for k,v in item.items() if k in item_fields} for item in value['ui']['goods']]
        if value.get('ui',{}).get('choices'):
            value['ui']['choices']=[{k:v for k,v in choice.items() if k in ('id','text')} for choice in value['ui']['choices']]
        region=value.get('region')
        if region:
            # 只传玩家画面和操作需要的字段；规则和未展示剧情留在服务端。
            allowed=('id','name','description','biome','weather','width','height','tiles','surfaces','props','entities','visuals','audio','seed','revision')
            value['region']={key:region[key] for key in allowed if key in region}
            fields=('id','local_id','name','description','kind','x','y','sprite','solid','footprint','spent','target','direction','locked','blocked_reason','alerted','intent','actor_id')
            value['region']['entities']=[{k:v for k,v in entity.items() if k in fields} for entity in region['entities']]
            value['region']['music_override']=region.get('runtime',{}).get('audio_music','')
        return value


class WebHandler(Handler):
    def origin(self):return 'http://127.0.0.1:'+str(self.server.server_port)
    def same_host(self):return self.headers.get('Host','')=='127.0.0.1:'+str(self.server.server_port)
    def cookie_valid(self):
        try:
            cookie=SimpleCookie(self.headers.get('Cookie',''));entry=cookie.get(self.server.cookie_name)
            return bool(entry and hmac.compare_digest(entry.value,self.server.token))
        except Exception:return False
    def web_origin(self):
        origin=self.headers.get('Origin')
        return self.same_host() and (origin==self.origin() if origin else self.headers.get('Sec-Fetch-Site')=='same-origin')
    def authorized(self):
        # 原生客户端继续使用 Bearer；Web 写入必须来自本页并携带非简单请求头。
        return super().authorized() or (self.web_origin() and self.cookie_valid() and self.headers.get('X-Everweave-Web')=='1')
    def send_file(self,path,mime,cookie=False):
        data=path.read_bytes()
        self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if cookie:self.send_header('Set-Cookie',f'{self.server.cookie_name}={self.server.token}; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers()
        try:self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
    def do_GET(self):
        path=urlsplit(self.path).path
        if path in ('/','/app.js','/style.css'):
            if not self.same_host() or self.headers.get('Sec-Fetch-Site','none') not in ('none','same-origin'):
                self.reply(403,{'error':'请直接打开本机游戏地址。'});return
            name,mime={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}[path]
            self.send_file(ROOT/'web'/name,mime,cookie=path=='/');return
        if path.startswith('/media/'):
            if not ((self.web_origin() and self.cookie_valid()) or super().authorized()):
                self.reply(401,{'error':'Local session required'});return
            from .library import resolve
            try:
                entry=resolve(unquote(path[len('/media/'):]))
                file=ROOT/entry['file'];mime={'.png':'image/png','.ogg':'audio/ogg','.wav':'audio/wav'}.get(file.suffix.lower())
                if not mime:raise ValueError('不支持的媒体')
                self.send_file(file,mime)
            except (OSError,ValueError):self.reply(404,{'error':'素材不可用'})
            return
        super().do_GET()

