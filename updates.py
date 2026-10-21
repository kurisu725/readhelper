"""Explicit GitHub Release checks and verified installer downloads. No remote code execution."""
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RELEASE = json.loads((Path(__file__).resolve().parent / 'release.json').read_text(encoding='utf-8'))
VERSION = RELEASE['version']
LOCK = threading.RLock()
STATE = {'status': 'idle', 'message': ''}
MAX_INSTALLER = 500 * 1024 * 1024


def repository(value):
    value = str(value).strip().removeprefix('https://github.com/').removesuffix('/').removesuffix('.git')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}', value):
        raise ValueError('请填写 GitHub 仓库，格式为 用户名/仓库名。')
    if value.split('/')[1] in ('.', '..'):
        raise ValueError('GitHub 仓库名无效。')
    return value


def version_tuple(value):
    if not re.fullmatch(r'v?\d+\.\d+\.\d+', value):
        raise ValueError('正式版本号必须采用 v1.7.0 格式。')
    return tuple(map(int, value.removeprefix('v').split('.')))


def target():
    if sys.platform == 'win32':
        return 'windows-x64.exe'
    if sys.platform == 'darwin':
        return 'macos-' + ('arm64' if platform.machine() == 'arm64' else 'x64') + '.dmg'
    return None


def settings(app):
    with app.connect() as conn:
        rows = dict(conn.execute('SELECT key,value FROM settings'))
    return {'version': VERSION, 'repository': rows.get('update_repository', RELEASE.get('repository', '')),
            'target': target(), 'authenticated': bool(app.env('PAPER_GITHUB_TOKEN').strip())}


def github_request(url, app, accept='application/vnd.github+json'):
    headers = {'Accept': accept, 'User-Agent': 'ResearchDesk/' + VERSION,
               'X-GitHub-Api-Version': '2022-11-28'}
    token = app.env('PAPER_GITHUB_TOKEN').strip()
    if token:
        if any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise ValueError('GitHub 访问令牌格式有误，请检查本机配置。')
        # Only constructed API URLs may receive a local credential.
        if urllib.parse.urlsplit(url).netloc != 'api.github.com' or not url.startswith('https://'):
            raise ValueError('GitHub 授权地址无效。')
        headers['Authorization'] = 'Bearer ' + token
    return urllib.request.Request(url, headers=headers)


class NoAPIRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def select_release(payload, repo, current=VERSION, platform_target=None):
    tag = payload.get('tag_name', '')
    latest = version_tuple(tag)
    result = {'version': tag.removeprefix('v'), 'current_version': current,
              'available': latest > version_tuple(current),
              'url': 'https://github.com/' + repo + '/releases/tag/' + urllib.parse.quote(tag, safe=''),
              'notes': str(payload.get('body') or '')[:20000], 'asset': None}
    if payload.get('draft') or payload.get('prerelease'):
        raise ValueError('该版本不是正式发布版本。')
    if not result['available']:
        return result
    expected = 'ResearchDesk-' + result['version'] + '-' + (platform_target or target() or 'unsupported')
    prefix = 'https://github.com/' + repo + '/releases/download/' + urllib.parse.quote(tag, safe='') + '/'
    for asset in payload.get('assets', []):
        if asset.get('name') != expected:
            continue
        digest = asset.get('digest') or ''
        if not re.fullmatch('sha256:[a-fA-F0-9]{64}', digest):
            raise ValueError('发布附件缺少 GitHub SHA-256 校验值，请在 GitHub 重新上传安装包。')
        size = asset.get('size')
        url = asset.get('browser_download_url')
        if url != prefix + expected or type(size) is not int or not 0 < size <= MAX_INSTALLER:
            raise ValueError('发布附件地址或大小不符合要求。')
        asset_id = asset.get('id')
        api_url = 'https://api.github.com/repos/' + repo + '/releases/assets/' + str(asset_id)
        if type(asset_id) is not int or asset_id <= 0 or asset.get('url') != api_url:
            raise ValueError('发布附件的 GitHub API 地址无效。')
        result['asset'] = {'name': expected, 'url': url, 'api_url': api_url,
                           'sha256': digest[7:].lower(), 'size': size}
        break
    return result


def check(app):
    repo = repository(settings(app)['repository'])
    request = github_request('https://api.github.com/repos/' + repo + '/releases/latest', app)
    try:
        with urllib.request.build_opener(NoAPIRedirects).open(request, timeout=20) as response:
            data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError('发布信息过大。')
        return select_release(json.loads(data), repo)
    except urllib.error.HTTPError as error:
        messages = {401: 'GitHub 访问令牌无效或已过期，请检查本机配置。',
                    404: '未找到可访问的正式 Release。请确认已发布版本；私有仓库还需在本机配置有该仓库读取权限的 GitHub 令牌。',
                    403: 'GitHub 拒绝访问或请求受到限制，请检查令牌的仓库读取权限后重试。',
                    429: 'GitHub 请求过于频繁，请稍后再试。'}
        raise ValueError(messages.get(error.code, 'GitHub 暂时无法访问，请稍后重试。')) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ValueError('无法连接 GitHub，请检查网络后重试。') from None


class ReleaseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != 'https' or parsed.netloc not in ('github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'):
            raise ValueError('下载被重定向到非 GitHub 地址，已停止。')
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected:
            redirected.remove_header('Authorization')
        return redirected


def download_worker(app):
    partial = None
    try:
        release = check(app)  # Re-fetch; never accept an installer URL supplied by the browser.
        asset = release['asset']
        if not release['available'] or not asset:
            raise ValueError('没有适用于此系统的新版安装包。')
        folder = app.DATA.parent / 'updates'
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = folder / asset['name']
        partial = destination.with_suffix(destination.suffix + '.partial')
        digest = hashlib.sha256()
        received = 0
        if app.env('PAPER_GITHUB_TOKEN').strip():
            request = github_request(asset['api_url'], app, 'application/octet-stream')
        else:
            request = urllib.request.Request(asset['url'], headers={'User-Agent': 'ResearchDesk/' + VERSION})
        with urllib.request.build_opener(ReleaseRedirects).open(request, timeout=30) as response, partial.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                received += len(chunk)
                if received > asset['size']:
                    raise ValueError('安装包大小与发布信息不符。')
                digest.update(chunk)
                output.write(chunk)
                with LOCK:
                    STATE.update(received=received, total=asset['size'])
        if received != asset['size'] or digest.hexdigest() != asset['sha256']:
            raise ValueError('安装包 SHA-256 校验失败，文件已丢弃。')
        partial.replace(destination)
        with LOCK:
            STATE.update(status='ready', message='下载完成，SHA-256 校验通过。',
                         path=str(destination), sha256=asset['sha256'], name=asset['name'])
    except Exception as error:
        if partial:
            partial.unlink(missing_ok=True)
        with LOCK:
            STATE.clear()
            STATE.update(status='error', message=str(error) if isinstance(error, ValueError) else '下载失败，请检查网络后重试。')


def start_download(app):
    with LOCK:
        if STATE['status'] == 'downloading':
            return snapshot()
        STATE.clear()
        STATE.update(status='downloading', message='正在获取并校验安装包…', received=0, total=0)
        threading.Thread(target=download_worker, args=(app,), daemon=True).start()
        return snapshot()


def snapshot():
    with LOCK:
        return {k: v for k, v in STATE.items() if k not in ('path', 'sha256')}


def open_installer(app):
    with LOCK:
        if STATE['status'] != 'ready':
            raise ValueError('请先下载并校验安装包。')
        path = Path(STATE['path'])
        if path.parent.resolve() != (app.DATA.parent / 'updates').resolve():
            raise ValueError('安装包路径无效。')
        if hashlib.sha256(path.read_bytes()).hexdigest() != STATE['sha256']:
            raise ValueError('安装包已被修改，请重新下载。')
        if sys.platform == 'darwin':
            subprocess.Popen(['open', str(path)])
        elif sys.platform == 'win32':
            os.startfile(str(path))
        else:
            raise ValueError('此系统不支持自动打开安装包。')
    return {'ok': True}


def handle(handler, method, path, app):
    try:
        if method == 'GET' and path == '/api/updates':
            return handler.reply({**settings(app), 'download': snapshot()})
        if method == 'POST' and path == '/api/updates/settings':
            repo = repository(handler.body().get('repository', ''))
            with LOCK:
                if STATE['status'] == 'downloading':
                    raise ValueError('请等待当前下载结束后再更改仓库。')
                STATE.clear(); STATE.update(status='idle', message='')
                with app.WRITE_LOCK, app.connect() as conn:
                    conn.execute("INSERT OR REPLACE INTO settings VALUES ('update_repository',?)", (repo,))
            return handler.reply(settings(app))
        if method == 'POST' and path == '/api/updates/check':
            handler.body()
            return handler.reply(check(app))
        if method == 'POST' and path == '/api/updates/download':
            handler.body()
            return handler.reply(start_download(app))
        if method == 'POST' and path == '/api/updates/open':
            handler.body()
            return handler.reply(open_installer(app))
        raise app.AppError('更新接口不存在。', 404)
    except ValueError as error:
        raise app.AppError(str(error)) from None
