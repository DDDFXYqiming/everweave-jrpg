"""用同一个 Godot 客户端的 Web 导出文件提供本机浏览器游戏。"""
import base64
import hashlib
import hmac
from http.cookies import SimpleCookie
from pathlib import Path
import re
from urllib.parse import urlsplit, unquote

from .server import GameServer, Handler


MIME = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
        '.wasm': 'application/wasm', '.pck': 'application/octet-stream',
        '.png': 'image/png', '.ico': 'image/x-icon'}


def _content_policy(html: str) -> str:
    # Godot 的官方导出页有内联启动脚本和样式；只批准当前导出文件的确切哈希。
    hashes = {'script': [], 'style': []}
    for kind in hashes:
        for match in re.finditer(rf'<{kind}\b([^>]*)>(.*?)</{kind}>', html, re.I | re.S):
            if kind == 'script' and re.search(r'\bsrc\s*=', match.group(1), re.I):
                continue
            digest = base64.b64encode(hashlib.sha256(match.group(2).encode('utf-8')).digest()).decode('ascii')
            hashes[kind].append("'sha256-" + digest + "'")
    return '; '.join((
        "default-src 'none'",
        "script-src 'self' 'wasm-unsafe-eval' " + ' '.join(hashes['script']),
        "style-src 'self' " + ' '.join(hashes['style']),
        "connect-src 'self'",
        "img-src 'self' data: blob:",
        "media-src 'self' blob:",
        "font-src 'self' data:",
        "worker-src 'self' blob:",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
    ))


class WebGameServer(GameServer):
    def __init__(self, address, save_path, token, export_root, credential_path=None):
        self.export_root = Path(export_root).resolve()
        index = self.export_root / 'index.html'
        if not index.is_file():
            raise ValueError('缺少 Godot Web 导出；请用 launch.py --web 构建。')
        self.web_files = {file.name: file for file in self.export_root.iterdir()
                          if file.is_file() and (file.name == 'index.html' or file.name.startswith('index.'))
                          and file.suffix.lower() in MIME}
        self.web_csp = _content_policy(index.read_text(encoding='utf-8'))
        super().__init__(address, save_path, token, WebHandler, credential_path)
        self.cookie_name = 'everweave_' + self.instance_id[:12]


class WebHandler(Handler):
    def origin(self): return 'http://127.0.0.1:' + str(self.server.server_port)
    def same_host(self): return self.headers.get('Host', '') == '127.0.0.1:' + str(self.server.server_port)

    def cookie_valid(self):
        try:
            cookie = SimpleCookie(self.headers.get('Cookie', ''))
            entry = cookie.get(self.server.cookie_name)
            return bool(entry and hmac.compare_digest(entry.value, self.server.token))
        except Exception:
            return False

    def web_origin(self):
        origin = self.headers.get('Origin')
        return self.same_host() and (origin == self.origin() if origin else self.headers.get('Sec-Fetch-Site') == 'same-origin')

    def authorized(self):
        # 原生客户端继续使用 Bearer；浏览器内的同一 Godot 客户端只发送同源 cookie。
        return super().authorized() or (self.web_origin() and self.cookie_valid()
                                        and self.headers.get('X-Everweave-Web') == '1')

    def send_file(self, path, mime, cookie=False):
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(path.stat().st_size))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', self.server.web_csp)
        if cookie:
            self.send_header('Set-Cookie', f'{self.server.cookie_name}={self.server.token}; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers()
        try:
            with path.open('rb') as stream:
                while chunk := stream.read(128 * 1024):
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_GET(self):
        path = urlsplit(self.path).path
        name = 'index.html' if path == '/' else unquote(path.removeprefix('/'))
        file = self.server.web_files.get(name)
        if file and path in ('/', '/' + name):
            if not self.same_host() or self.headers.get('Sec-Fetch-Site', 'none') not in ('none', 'same-origin'):
                self.reply(403, {'error': '请直接打开本机游戏地址。'})
                return
            if name != 'index.html' and not self.cookie_valid():
                self.reply(401, {'error': 'Local session required'})
                return
            self.send_file(file, MIME[file.suffix.lower()], cookie=name == 'index.html')
            return
        super().do_GET()
