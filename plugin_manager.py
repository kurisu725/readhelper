"""Version 1 plugin API. Plugins are shipped, reviewed Python packages, never remote code."""
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'plugins'
_plugins = None


def installed():
    global _plugins
    if _plugins is None:
        _plugins = {}
        for path in sorted(ROOT.glob('*/manifest.json')):
            manifest = json.loads(path.read_text(encoding='utf-8'))
            pid = manifest['id']
            if not re.fullmatch(r'[a-z][a-z0-9-]{1,63}', pid) or manifest['api_version'] != 1:
                raise ValueError('Unsupported plugin manifest: ' + path.name)
            name = 'researchdesk_plugin_' + pid.replace('-', '_')
            spec = importlib.util.spec_from_file_location(name, path.parent / '__init__.py',
                                                       submodule_search_locations=[str(path.parent)])
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            _plugins[pid] = (manifest, module, path.parent)
    return _plugins


def enabled(conn, pid):
    row = conn.execute('SELECT value FROM settings WHERE key=?', ('plugin:' + pid,)).fetchone()
    return bool(row and row[0] == 'true')


def init_schema(conn):
    for pid, (_, module, _) in installed().items():
        # Preserve access to existing users' historical records on upgrade.
        if not conn.execute('SELECT 1 FROM settings WHERE key=?', ('plugin:' + pid,)).fetchone():
            migrate = getattr(module, 'has_data', lambda c: False)(conn)
            conn.execute('INSERT INTO settings VALUES (?,?)', ('plugin:' + pid, 'true' if migrate else 'false'))
        if enabled(conn, pid):
            module.init_schema(conn)


def descriptors(app):
    with app.connect() as conn:
        return [{**manifest, 'enabled': enabled(conn, pid)}
                for pid, (manifest, _, _) in installed().items()]


def set_enabled(app, pid, value):
    if pid not in installed() or type(value) is not bool:
        raise app.AppError('插件或开关值无效。')
    with app.WRITE_LOCK, app.connect() as conn:
        if value:
            installed()[pid][1].init_schema(conn)
        conn.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('plugin:' + pid, 'true' if value else 'false'))
        if not value:
            selected = conn.execute("SELECT value FROM settings WHERE key='research_mode'").fetchone()
            if selected and selected[0] in installed()[pid][0].get('modes', {}):
                conn.execute("INSERT OR REPLACE INTO settings VALUES ('research_mode','general')")
    if not value:
        getattr(installed()[pid][1], 'on_disable', lambda application: None)(app)
    return descriptors(app)


def shutdown(app):
    for _, module, _ in installed().values():
        getattr(module, 'shutdown', lambda application: None)(app)


def provider(mode):
    return next(((pid, mod) for pid, (m, mod, _) in installed().items()
                 if mode in m.get('modes', {})), (None, None))


def available_mode(conn, mode):
    pid, _ = provider(mode)
    return mode == 'general' or bool(pid and enabled(conn, pid))


def dispatch(handler, method, path, query, app):
    for pid, (manifest, module, folder) in installed().items():
        asset_prefix = '/plugins/' + pid + '/'
        is_asset = path.startswith(asset_prefix)
        is_route = any(path == route or path.startswith(route + '/') for route in manifest.get('routes', []))
        if not is_asset and not is_route:
            continue
        with app.connect() as conn:
            if not enabled(conn, pid):
                raise app.AppError('请先在“插件与更新”中启用此插件。', 404)
        if is_asset:
            if method != 'GET':
                raise app.AppError('不支持此操作。', 405)
            root = (folder / 'static').resolve()
            target = (root / app.urllib.parse.unquote(path[len(asset_prefix):])).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                raise app.AppError('插件资源不存在。', 404)
            kind = app.mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
            handler.reply(target.read_bytes(), kind=kind)
        else:
            module.handle(handler, method, path, query, app)
        return True
    return False


def export_markdown(conn):
    # Disabling a plugin never removes its data from a full export or backup.
    return '\n\n'.join(mod.markdown(conn) for _, mod, _ in installed().values()
                       if getattr(mod, 'has_data', lambda c: False)(conn))
