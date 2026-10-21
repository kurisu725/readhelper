import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import urllib.error
import urllib.request
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import plugin_manager
import updates


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = patch.multiple(app, DATA=self.root / 'data', DB=self.root / 'data/library.sqlite3')
        self.paths.start()
        self.environment = patch.dict(os.environ, {'PAPER_CONFIG_FILE': str(self.root / '.env'),
                                                   'PAPER_API_KEY': '', 'OPENAI_API_KEY': ''})
        self.environment.start()
        with updates.LOCK:
            updates.STATE.clear(); updates.STATE.update(status='idle', message='')
        app.init_db()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown(); self.thread.join(); self.server.server_close()
        self.environment.stop(); self.paths.stop(); self.temp.cleanup()

    def request(self, path, data=None, method=None, headers=None):
        request = urllib.request.Request(self.url + path, data=json.dumps(data).encode() if data is not None else None,
             method=method, headers=headers or {'X-Requested-With': 'ResearchDesk', 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request) as result:
                raw = result.read()
                return result.status, json.loads(raw) if 'application/json' in result.headers.get('Content-Type', '') else raw
        except urllib.error.HTTPError as result:
            return result.code, json.load(result)

    def enable(self, enabled=True):
        return self.request('/api/plugins/architecture-history', {'enabled': enabled})

    def fixture_release(self, content=b'installer', version='1.8.0'):
        name = f'ResearchDesk-{version}-windows-x64.exe'
        return {'tag_name': 'v' + version, 'draft': False, 'prerelease': False, 'body': '<script>not HTML</script>',
                'assets': [{'name': name, 'size': len(content), 'digest': 'sha256:' + hashlib.sha256(content).hexdigest(),
                            'browser_download_url': 'https://github.com/owner/desk/releases/download/v' + version + '/' + name}]}

    def test_fresh_install_general_optional_plugin(self):
        self.assertEqual(app.config()['research_mode'], 'general')
        self.assertFalse(self.request('/api/plugins')[1]['plugins'][0]['enabled'])
        self.assertEqual(self.request('/api/history')[0], 404)
        self.assertEqual(self.request('/api/research-mode', {'mode': 'history'})[0], 400)
        with app.connect() as conn:
            self.assertFalse(conn.execute("SELECT 1 FROM sqlite_master WHERE name='history_records'").fetchone())

    def test_toggle_preserves_records_and_exports(self):
        self.assertEqual(self.enable()[0], 200)
        self.assertEqual(self.request('/api/research-mode', {'mode': 'history'})[0], 200)
        code, body = self.request('/api/history', {'kind': 'evidence', 'subject': '测试建筑', 'title': '测试史料',
            'status': '待核对', 'data': {'source_title': '测试地方志', 'printed_page': '第12页', 'original': '始建年代待核。'}})
        self.assertEqual(code, 201, body)
        self.enable(False)
        self.assertEqual(app.config()['research_mode'], 'general')
        self.assertEqual(self.request('/api/history')[0], 404)
        self.assertIn('测试史料', self.request('/api/export')[1].decode())
        self.enable()
        self.assertEqual(len(self.request('/api/history')[1]['records']), 1)

    def test_migrate_previous_history_install(self):
        with app.connect() as conn:
            plugin_manager.installed()['architecture-history'][1].init_schema(conn)
            conn.execute("DELETE FROM settings WHERE key='plugin:architecture-history'")
            conn.execute("INSERT OR REPLACE INTO settings VALUES ('research_mode','history')")
        app.init_db()
        self.assertTrue(self.request('/api/plugins')[1]['plugins'][0]['enabled'])
        self.assertEqual(app.config()['research_mode'], 'history')

    def test_general_app_without_any_plugin_files(self):
        with patch.object(plugin_manager, 'ROOT', self.root / 'no-plugins'), patch.object(plugin_manager, '_plugins', None):
            app.init_db()
            self.assertEqual(self.request('/api/plugins')[1]['plugins'], [])
            self.assertEqual(self.request('/api/state')[0], 200)
            self.assertEqual(self.request('/api/export')[0], 200)

    def test_disabled_mode_can_edit_existing_knowledge(self):
        self.enable()
        code, data = self.request('/api/knowledge', {'kind': '知识', 'title': '历史分析', 'content': '待核对', 'analysis_mode': 'history'})
        self.assertEqual(code, 201, data)
        self.enable(False)
        code, data = self.request('/api/knowledge/' + data['card']['id'], {'title': '保留原模式'}, method='PATCH')
        self.assertEqual(code, 200, data)
        self.assertEqual(data['card']['analysis_mode'], 'history')

    def test_plugin_assets_require_enable_and_reject_traversal(self):
        self.assertEqual(self.request('/plugins/architecture-history/index.js')[0], 404)
        self.enable()
        self.assertEqual(self.request('/plugins/architecture-history/index.js')[0], 200)
        self.assertEqual(self.request('/plugins/architecture-history/%2e%2e/manifest.json')[0], 404)

    def test_write_requires_same_origin_marker(self):
        self.assertEqual(self.request('/api/plugins/architecture-history', {'enabled': True}, headers={'Origin': 'https://evil.invalid'})[0], 403)
        self.assertEqual(self.request('/api/updates/open', {}, headers={'Origin': 'https://evil.invalid', 'X-Requested-With': 'ResearchDesk'})[0], 403)

    def test_repository_validation_and_no_credentials(self):
        self.assertEqual(updates.repository('https://github.com/owner/desk.git'), 'owner/desk')
        for value in ['owner/..', 'https://evil.invalid/owner/repo', 'owner/repo?token=secret', 'a/b/c', 'a/b$(cmd)']:
            with self.assertRaises(ValueError): updates.repository(value)
        self.assertEqual(self.request('/api/updates/settings', {'repository': 'owner/desk'})[0], 200)
        self.assertEqual(self.request('/api/updates')[1]['repository'], 'owner/desk')

    def test_version_comparison_and_asset_matching(self):
        result = updates.select_release(self.fixture_release(version='1.10.0'), 'owner/desk', current='1.9.0', platform_target='windows-x64.exe')
        self.assertTrue(result['available']); self.assertIsNotNone(result['asset'])
        self.assertIsNone(updates.select_release(self.fixture_release(), 'owner/desk', platform_target='macos-arm64.dmg')['asset'])
        self.assertFalse(updates.select_release(self.fixture_release(version='1.7.0'), 'owner/desk')['available'])
        with self.assertRaises(ValueError): updates.version_tuple('v1.8.0-beta.1')

    def test_asset_integrity_and_origin_required(self):
        for field, value in [('digest', None), ('browser_download_url', 'https://evil.invalid/file.exe'), ('size', updates.MAX_INSTALLER + 1)]:
            data = self.fixture_release(); data['assets'][0][field] = value
            with self.assertRaises(ValueError): updates.select_release(data, 'owner/desk', platform_target='windows-x64.exe')
        with self.assertRaises(ValueError):
            updates.ReleaseRedirects().redirect_request(None, None, 302, '', {}, 'http://github.com/unsafe')

    def test_download_hash_success_then_tamper_prevents_open(self):
        release = updates.select_release(self.fixture_release(), 'owner/desk', platform_target='windows-x64.exe')
        with patch.object(updates, 'check', return_value=release), patch.object(updates.urllib.request, 'build_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(b'installer')
            updates.download_worker(app)
        self.assertEqual(updates.snapshot()['status'], 'ready')
        self.assertNotIn('path', updates.snapshot())
        Path(updates.STATE['path']).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, '修改'): updates.open_installer(app)

    def test_corrupt_download_removed(self):
        release = updates.select_release(self.fixture_release(), 'owner/desk', platform_target='windows-x64.exe')
        with patch.object(updates, 'check', return_value=release), patch.object(updates.urllib.request, 'build_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(b'corrupted')
            updates.download_worker(app)
        self.assertEqual(updates.snapshot()['status'], 'error')
        self.assertFalse(list((self.root / 'updates').glob('*')))

    def test_github_errors_are_actionable(self):
        self.request('/api/updates/settings', {'repository': 'owner/desk'})
        for status in (403, 404, 429):
            with patch.object(updates.urllib.request, 'urlopen', side_effect=urllib.error.HTTPError('url', status, '', {}, None)):
                with self.assertRaises(ValueError): updates.check(app)


if __name__ == '__main__': unittest.main()
