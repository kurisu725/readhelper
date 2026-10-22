import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import plugin_manager
from pypdf import PdfReader, PdfWriter

directions = plugin_manager.installed()['research-directions'][1].service
ABSTRACT = ('We evaluate adaptive reuse using interviews and observations of public spaces. '
            'The study is limited by a small sample and a single study location. '
            'Future work should compare different sites over a longer period.')
QUOTE = 'The study is limited by a small sample and a single study location.'


def source(title='Public space evaluation', doi='10.1234/reuse'):
    return {'title': title, 'authors': ['Test Author'], 'year': '2025', 'doi': doi,
            'url': 'https://example.org/paper', 'abstract': ABSTRACT, 'provider': 'OpenAlex'}


def report():
    evidence = [{'source': 1, 'quote': QUOTE}]
    return {'overview': {'text': '本次摘要讨论公共空间评价，覆盖范围有限。', 'evidence': evidence},
            'branches': [{'name': '使用后评价', 'summary': '结合访谈和空间观察进行评价。', 'evidence': evidence,
                          'problems': [{'title': '样本与场地范围', 'detail': '摘要明确报告样本和场地有限。',
                                        'kind': 'reported', 'evidence': evidence}],
                          'directions': [{'title': '开展跨场地验证', 'detail': '可对照多个场地，检验结果能否迁移。',
                                          'evidence': evidence}]}]}


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = patch.multiple(app, DATA=self.root / 'data', DB=self.root / 'data/library.sqlite3')
        self.paths.start()
        self.environment = patch.dict(os.environ, {'PAPER_CONFIG_FILE': str(self.root / '.env'),
            'PAPER_API_KEY': 'test-key', 'PAPER_BASE_URL': 'https://example.invalid/v1', 'PAPER_MODEL': 'test-model'})
        self.environment.start()
        app.init_db()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        app.stop_ocr()
        directions.shutdown(app)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and (directions.JOBS or any(
                job['status'] == 'running' for job in app.OCR_JOBS.values())):
            time.sleep(.02)
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        app.OCR_JOBS.clear()
        self.environment.stop()
        self.paths.stop()
        self.temp.cleanup()

    def request(self, path, body=None, method=None):
        request = urllib.request.Request(self.url + path, data=json.dumps(body).encode() if body is not None else None,
            method=method, headers={'X-Requested-With': 'ResearchDesk', 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read()
                return response.status, json.loads(raw) if 'application/json' in response.headers.get('Content-Type', '') else raw
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def enable(self):
        self.assertEqual(self.request('/api/plugins/research-directions', {'enabled': True})[0], 200)

    def blank_paper(self):
        writer = PdfWriter()
        for _ in range(2):
            writer.add_blank_page(width=612, height=792)
        buffer = io.BytesIO()
        writer.write(buffer)
        return app.import_pdf(buffer.getvalue(), '扫描件.pdf')['paper']

    def wait_ocr(self, paper_id):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            job = app.ocr_snapshot(paper_id)
            if job['status'] != 'running':
                return job
            time.sleep(.03)
        self.fail('OCR did not finish')

    def wait_run(self, run_id):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            run = directions.get(run_id, app)
            if run['status'] not in directions.ACTIVE and run_id not in directions.JOBS:
                return run
            time.sleep(.02)
        self.fail('Research did not finish')

    def fake_provider(self, path, payload, **kwargs):
        self.assertEqual(path, '/chat/completions')
        self.assertFalse(payload['stream'])
        value = report() if 'research_direction_map' in payload['messages'][0]['content'] else {'query': 'adaptive reuse'}
        return io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps(value)}, 'finish_reason': 'stop'}]}).encode())

    def test_plugin_off_by_default_and_preserves_other_mode(self):
        self.assertEqual(self.request(directions.PREFIX)[0], 404)
        self.assertEqual(self.request('/plugins/research-directions/index.js')[0], 404)
        self.enable()
        self.assertEqual(self.request('/plugins/research-directions/index.js')[0], 200)
        plugin_manager.set_enabled(app, 'architecture-history', True)
        self.request('/api/research-mode', {'mode': 'history'})
        plugin_manager.set_enabled(app, 'research-directions', False)
        self.assertEqual(app.config()['research_mode'], 'history')

    def test_full_research_flow_persists_exports_and_reuses_evidence(self):
        self.enable()
        calls = []
        def search(query, start, end):
            calls.append(query)
            return [source(), source(doi='')]
        with patch.dict(directions.PROVIDERS, {'openalex': ('OpenAlex', search)}), patch.object(app, 'provider_request', side_effect=self.fake_provider):
            status, body = self.request(directions.PREFIX, {'topic': '公共空间评价', 'providers': ['openalex']})
            self.assertEqual(status, 202, body)
            run = self.wait_run(body['run']['id'])
            self.assertEqual(run['status'], 'done', run)
            self.assertEqual(len(run['sources']), 1)
            self.assertEqual(run['queries'], ['公共空间评价', 'adaptive reuse'])
            self.assertEqual(run['report']['branches'][0]['directions'][0]['kind'], 'inferred')
            self.assertEqual(len(calls), 2)
            status, body = self.request(directions.PREFIX + '/' + run['id'] + '/retry', {})
            self.assertEqual(status, 202)
            self.assertEqual(self.wait_run(body['run']['id'])['status'], 'done')
            self.assertEqual(len(calls), 2)
        status, exported = self.request(directions.PREFIX + '/' + run['id'] + '/export')
        self.assertEqual(status, 200)
        self.assertIn(QUOTE.encode(), exported)
        self.assertEqual(self.request(directions.PREFIX + '/' + run['id'] + '/export?format=json')[1]['id'], run['id'])
        plugin_manager.set_enabled(app, 'research-directions', False)
        self.assertEqual(self.request(directions.PREFIX)[0], 404)
        self.assertIn('公共空间评价'.encode(), self.request('/api/export')[1])
        self.enable()
        self.assertEqual(len(self.request(directions.PREFIX)[1]['runs']), 2)

    def test_invalid_quotes_and_sources_are_rejected(self):
        options = {'year_from': '', 'year_to': '', 'limit': 8}
        sources = directions.merge_sources([source()], options)
        for replacement in ({'source': 99, 'quote': QUOTE}, {'source': True, 'quote': QUOTE},
                            {'source': 1, 'quote': 'This sentence never appeared in the evidence.'}):
            value = report()
            value['overview']['evidence'] = [replacement]
            with self.assertRaises(ValueError):
                directions.validate_report(value, sources)
        value = report()
        value['branches'][0]['problems'][0]['kind'] = 'fact'
        with self.assertRaises(ValueError):
            directions.validate_report(value, sources)

    def test_unvalidated_report_is_not_saved(self):
        self.enable()
        def invalid_provider(*args, **kwargs):
            value = report()
            value['overview']['evidence'] = [{'source': 1, 'quote': 'A fabricated supporting quotation.'}]
            return io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps(value)}}]}).encode())
        with patch.dict(directions.PROVIDERS, {'openalex': ('OpenAlex', lambda *args: [source()])}), patch.object(app, 'provider_request', side_effect=invalid_provider):
            run = directions.start({'topic': 'public space', 'providers': ['openalex'], 'expand_query': False}, app)
            result = self.wait_run(run['id'])
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['report'], {})
        self.assertEqual(len(result['sources']), 1)

    def test_cancel_and_disable_prevent_late_result(self):
        self.enable()
        entered, release = threading.Event(), threading.Event()
        def delayed(*args):
            entered.set()
            release.wait(4)
            return [source()]
        with patch.dict(directions.PROVIDERS, {'openalex': ('OpenAlex', delayed)}), patch.object(app, 'provider_request') as provider:
            run = directions.start({'topic': 'public space', 'providers': ['openalex'], 'expand_query': False}, app)
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.request(directions.PREFIX, {'topic': 'another topic'})[0], 409)
            self.assertEqual(self.request(directions.PREFIX + '/' + run['id'] + '/cancel', {})[0], 200)
            plugin_manager.set_enabled(app, 'research-directions', False)
            release.set()
            result = self.wait_run(run['id'])
            provider.assert_not_called()
        self.assertEqual(result['status'], 'cancelled')
        self.assertFalse(result['report'])

    def test_partial_provider_failure_and_metadata_only(self):
        self.enable()
        def broken(*args):
            raise OSError('unavailable')
        candidate = source()
        candidate['abstract'] = ''
        with patch.dict(directions.PROVIDERS, {'openalex': ('OpenAlex', broken),
                      'crossref': ('Crossref', lambda *args: [candidate])}), patch.object(app, 'provider_request') as provider:
            run = directions.start({'topic': 'public space', 'providers': ['openalex', 'crossref'], 'expand_query': False}, app)
            result = self.wait_run(run['id'])
            provider.assert_not_called()
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['sources'][0]['basis'], 'metadata')
        self.assertTrue(any('OpenAlex' in warning for warning in result['warnings']))

    def test_option_validation_and_interrupted_recovery(self):
        self.enable()
        for extra in ({'limit': True}, {'providers': ['unknown']}, {'providers': []}, {'year_from': '2026', 'year_to': '2020'}, {'expand_query': 'yes'}):
            self.assertEqual(self.request(directions.PREFIX, {'topic': 'test topic', **extra})[0], 400)
        with app.connect() as conn:
            conn.execute('''INSERT INTO direction_runs(id,topic,options,status,stage,model,created_at,updated_at)
                            VALUES ('deadbeefdeadbeef','test','{}','analyzing','test','test','test','test')''')
            directions.init_schema(conn)
        self.assertEqual(directions.get('deadbeefdeadbeef', app)['status'], 'interrupted')

    def test_provider_parsing_and_deduplication(self):
        payload = {'results': [{'title': 'Public space evaluation', 'publication_year': 2025,
                    'doi': 'https://doi.org/10.1234/reuse', 'abstract_inverted_index': {'second': [1], 'first': [0]},
                    'primary_location': None, 'authorships': []}]}
        with patch.object(directions, 'read_index', return_value=('', json.dumps(payload), {})):
            records = directions.openalex_search('reuse', '2020', '2026')
        self.assertEqual(records[0]['abstract'], 'first second')
        self.assertEqual(records[0]['doi'], '10.1234/reuse')
        normalized = directions.merge_sources([source(), source(doi=''), {**source(), 'year': '2010'}],
                                             {'year_from': '2020', 'year_to': '', 'limit': 8})
        self.assertEqual(len(normalized), 1)

    def test_index_transport_rejects_untrusted_hosts_and_redirects(self):
        for url in ('http://api.openalex.org/works', 'https://127.0.0.1/works',
                    'https://api.openalex.org.evil.invalid/works', 'https://user@api.openalex.org/works',
                    'https://api.openalex.org/private', 'https://api.openalex.org:444/works'):
            with self.assertRaises(ValueError):
                directions.read_index(url)
        self.assertIsNone(directions.IndexRedirects().redirect_request(None, None, 302, '', {}, 'https://example.org'))

    def test_ocr_cancel_preserves_progress_and_validates_pages(self):
        paper = self.blank_paper()
        helper = self.root / 'fake_ocr.py'
        helper.write_text('import json,time\nprint(json.dumps({"page":1,"text":"searchable OCR result"}),flush=True)\ntime.sleep(20)\n')
        with patch.object(app, 'ocr_command', return_value=[sys.executable, '-u', str(helper)]):
            for page in (True, 'x', 0, 3):
                self.assertEqual(self.request('/api/papers/' + paper['id'] + '/ocr', {'scope': 'page', 'page': page})[0], 400)
            app.start_ocr(paper['id'], {'scope': 'missing'})
            deadline = time.monotonic() + 5
            while app.ocr_snapshot(paper['id'])['completed'] < 1 and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertEqual(app.ocr_snapshot(paper['id'])['completed'], 1)
            app.stop_ocr(paper['id'])
            self.assertEqual(self.wait_ocr(paper['id'])['status'], 'cancelled')
        self.assertEqual(self.request('/api/papers/' + paper['id'] + '/page?page=1')[1]['text'], 'searchable OCR result')
        with app.connect() as conn:
            self.assertEqual(app.paper_row(paper['id'], conn)['ocr_pages'], 1)

    @unittest.skipUnless(sys.platform == 'win32' and app.ocr_command(), 'Windows OCR dependencies required')
    def test_windows_ocr_real_scanned_pdf_and_resume(self):
        from PIL import Image, ImageDraw, ImageFont
        image = Image.new('RGB', (1400, 1800), 'white')
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(str(Path(os.environ['WINDIR']) / 'Fonts/arial.ttf'), 38)
        draw.text((85, 150), 'Research methods and public space', font=font, fill='black')
        draw.text((85, 230), 'A study with 120 participants.', font=font, fill='black')
        chinese = Path(os.environ['WINDIR']) / 'Fonts/msyh.ttc'
        if chinese.exists():
            draw.text((85, 330), '扫描文献文字识别与研究方向', font=ImageFont.truetype(str(chinese), 42), fill='black')
        buffer = io.BytesIO()
        blank = Image.new('RGB', image.size, 'white')
        image.save(buffer, format='PDF', save_all=True, append_images=[blank], resolution=150)
        image.close()
        blank.close()
        self.assertFalse(PdfReader(io.BytesIO(buffer.getvalue())).pages[0].extract_text())
        paper = app.import_pdf(buffer.getvalue(), '扫描中文 English.pdf')['paper']
        app.start_ocr(paper['id'], {'scope': 'missing'})
        job = self.wait_ocr(paper['id'])
        self.assertEqual(job['status'], 'done', job)
        self.assertEqual(job['failed'], 0, job)
        self.assertEqual(job['completed'], 2)
        _, page = self.request('/api/papers/' + paper['id'] + '/page?page=1')
        self.assertIn('participants', page['text'].lower())
        if chinese.exists():
            self.assertIn('文字识别', page['text'])
        self.assertEqual(page['ocr_data']['engine'], 'RapidOCR')
        self.assertTrue(page['ocr_data']['blocks'])
        self.assertEqual(self.request('/api/search?q=participants')[1]['results'][0]['page'], 1)
        with app.connect() as conn:
            total = conn.execute('SELECT SUM(length(text)) FROM pages WHERE paper_id=?', (paper['id'],)).fetchone()[0]
            self.assertEqual(app.paper_row(paper['id'], conn)['text_chars'], total)
        self.assertEqual(app.start_ocr(paper['id'], {'scope': 'missing'})['total'], 0)


if __name__ == '__main__':
    unittest.main()
