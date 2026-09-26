"""从 Godot 官方发布包按需安装当前版本的单线程 Web 导出模板。"""
from __future__ import annotations

import io
import os
from pathlib import Path
import re
import struct
import subprocess
import urllib.request
import zipfile
import zlib


FILES = ('version.txt', 'web_nothreads_debug.zip', 'web_nothreads_release.zip')


def _range(url: str, start: int, end: int) -> tuple[bytes, int]:
    request = urllib.request.Request(url, headers={
        'Range': f'bytes={start}-{end}',
        'User-Agent': 'Everweave Godot Web export setup',
    })
    with urllib.request.urlopen(request, timeout=90) as response:
        if response.status != 206:
            raise OSError('Godot 发布服务器未返回分段下载内容。')
        total = int(response.headers['Content-Range'].rsplit('/', 1)[1])
        data = response.read()
        if len(data) != end - start + 1:
            raise OSError('Godot 模板下载不完整。')
        return data, total


class _RemoteZip(io.RawIOBase):
    def __init__(self, url: str, length: int):
        self.url = url
        self.length = length
        self.position = 0

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.position

    def seek(self, offset, whence=0):
        self.position = offset if whence == 0 else self.position + offset if whence == 1 else self.length + offset
        return self.position

    def read(self, size=-1):
        if size < 0: size = self.length - self.position
        if size <= 0 or self.position >= self.length: return b''
        end = min(self.length - 1, self.position + size - 1)
        data, _ = _range(self.url, self.position, end)
        self.position += len(data)
        return data


def _entry(url: str, info: zipfile.ZipInfo) -> bytes:
    header, _ = _range(url, info.header_offset, info.header_offset + 29)
    signature, _, _, method, _, _, _, _, _, name_length, extra_length = struct.unpack('<IHHHHHIIIHH', header)
    if signature != 0x04034B50 or method != info.compress_type:
        raise OSError('Godot 模板包结构无效。')
    start = info.header_offset + 30 + name_length + extra_length
    packed, _ = _range(url, start, start + info.compress_size - 1)
    if method == zipfile.ZIP_STORED: data = packed
    elif method == zipfile.ZIP_DEFLATED: data = zlib.decompress(packed, -15)
    else: raise OSError('Godot 模板使用了不支持的压缩方式。')
    if len(data) != info.file_size or zlib.crc32(data) != info.CRC:
        raise OSError('Godot 模板校验失败。')
    return data


def ensure_web_templates(editor: str) -> Path:
    result = subprocess.run([editor, '--version'], capture_output=True, text=True, check=True)
    match = re.match(r'^(\d+\.\d+(?:\.\d+)?)\.stable\b', result.stdout.strip())
    if not match: raise OSError('当前 Godot 版本不是可自动安装模板的稳定版。')
    version = match.group(1)
    folder = Path(os.environ['APPDATA']) / 'Godot' / 'export_templates' / f'{version}.stable' if os.name == 'nt' else Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'godot' / 'export_templates' / f'{version}.stable'
    if all((folder / name).is_file() for name in FILES): return folder

    tag = f'{version}-stable'
    url = f'https://github.com/godotengine/godot-builds/releases/download/{tag}/Godot_v{tag}_export_templates.tpz'
    _, length = _range(url, 0, 0)
    with zipfile.ZipFile(_RemoteZip(url, length)) as archive:
        entries = {name: archive.getinfo('templates/' + name) for name in FILES}
        folder.mkdir(parents=True, exist_ok=True)
        for name, info in entries.items():
            target = folder / name
            if target.is_file() and target.stat().st_size == info.file_size:
                continue
            data = _entry(url, info)
            temporary = target.with_name(target.name + '.tmp')
            temporary.write_bytes(data)
            temporary.replace(target)
    if (folder / 'version.txt').read_text(encoding='utf-8').strip() != f'{version}.stable':
        raise OSError('Godot Web 模板与编辑器版本不匹配。')
    return folder
