"""Isolated integration tests, using a local mock AI provider only."""
import http.client
import io
import json
import os
import sqlite3
import sys
import tempfile
import time
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import online_cases as web
import literature
import plugin_manager
history = plugin_manager.installed()["architecture-history"][1].history


def fixture_pdf(title='A test study'):
    writer=PdfWriter()
    for line in ('Methods: randomized experiment with 120 participants.',
                 'Results: improvement was 12 percent. Limitations: a small sample.'):
        page=writer.add_blank_page(width=612,height=792)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(f'BT /F1 16 Tf 50 700 Td ({line}) Tj ET'.encode())
        page[NameObject('/Contents')]=writer._add_object(stream)
    writer.add_metadata({'/Title':title,'/Author':'Test Researcher','/CreationDate':'D:20241010120000'})
    result=io.BytesIO();writer.write(result);return result.getvalue()


def web_analysis():
    return dict(is_project=True,match_level='同类',project_name='庭院图书馆（功能测试）',typology='公共图书馆 [1]',
                location='当前来源未提供',architect='当前来源未提供',year='当前来源未提供',scale='当前来源未提供',
                summary='阅读空间围绕庭院组织。[1]',similarity='同为图书馆，关注庭院与动线。[1]',
                space='回游动线连接庭院。[1]',strategy='当前来源未提供',innovations='分析归纳：庭院与阅读空间联系。[1]',
                improvements='分析建议：进一步核对采光与使用评价。',takeaways='可参考动线组织，需结合场地验证。[1]',
                limits='仅依据当前网页摘录，图纸与性能数据未提供。')

WEB_HTML='<html><title>庭院图书馆（功能测试）</title><nav>不得作为正文的导航</nav><article><h1>庭院图书馆</h1><p>'+('本网页仅为程序功能测试，非真实项目。共享庭院组织阅读空间，回游动线连接庭院、阅览室与公共入口；设计关注安静区域与交往空间的关系。性能、设计者、年代和面积尚未提供。'*4)+'</p></article><footer>不得作为正文的页脚</footer></html>'

LITERATURE_FIXTURE={'title':'工业遗产再利用与公共空间（功能测试）','authors':['测试研究者'],'year':'2024',
    'venue':'功能测试期刊','doi':'10.1234/test.architecture','url':'https://doi.org/10.1234/test.architecture',
    'abstract':'本摘要仅为功能测试，不代表真实研究。研究关注工业遗产再利用后的公共空间，通过使用者访谈与空间观察讨论公共性评价。摘要没有提供量化性能、样本量或图纸细节，需要进一步阅读全文验证。'*2,
    'kind':'journal-article','provider':'Crossref'}

BRIEF_TEXT='''社区图书馆设计任务书（功能测试示例）
设计一座面向社区居民与儿童的公共图书馆，组织阅读、交流与共享活动。
总建筑面积不超过 3000 平方米，场地现有树木应予保留。
阅览室需与活动空间分区，形成清晰、连续的无障碍流线。
提交总平面图、各层平面图、剖面图与设计说明，表达场地及空间组织。'''


def brief_analysis(sources):
    requirements=[]
    for source in sources:
        for line in source['quote'].splitlines():
            if len(line.strip())>20:
                requirements.append({'category':('设计目标','规模与指标','限制条件','交付成果')[len(requirements)%4],
                                     'text':line.strip(),'source':source['number'],'quote':line.strip()})
    if not requirements:
        source=sources[0]
        requirements=[{'category':'设计目标','text':source['quote'][:100],'source':source['number'],'quote':source['quote'][:100]}]
    return {'summary':'社区图书馆以阅读、交流与共享活动为核心，关注场地与公共空间的联系。[1]',
            'requirements':requirements[:8],
            'keywords':[{'term':'社区图书馆','basis':'原文明确','source':1,'reason':'以社区公共阅读为主要任务。'},
                        {'term':'儿童阅读','basis':'原文明确','source':1,'reason':'任务使用者包含儿童。'},
                        {'term':'庭院组织','basis':'分析建议','source':None,'reason':'可研究庭院分隔动静区域，但不是任务书硬性要求。'}],
            'searches':[{'query':'社区图书馆 公共空间','focus':'学习阅读与共享活动的关系，核对功能规模和社区使用方式。'},
                        {'query':'图书馆 庭院 保留树木','focus':'学习场地树木与院落布局，核对采光、动静分区及无障碍流线。'},
                        {'query':'儿童图书馆 阅读空间','focus':'学习儿童区空间尺度与看护视线，结合本任务的使用者需求调整。'}],
            'questions':['任务书未给出基地尺寸、朝向及周边道路条件，需要补充场地资料。','未明确提交日期和成果比例，应进一步核对。']}


class Provider(BaseHTTPRequestHandler):
    mode='stream';captured=None
    def log_message(self,*args): pass
    def do_GET(self):
        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
        self.wfile.write(b'{"data":[{"id":"test-model"},{"id":"test-model"},{"id":"other"}]}')
    def do_POST(self):
        Provider.captured=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if Provider.mode=='unauthorized':
            self.send_response(401);self.end_headers();self.wfile.write(b'test-only-secret');return
        if Provider.captured.get('stream') is False:
            if 'history_draft' in Provider.captured['messages'][0]['content'] or 'history_comparison' in Provider.captured['messages'][0]['content']:
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                payload=json.loads(Provider.captured['messages'][1]['content'])
                if 'history_comparison' in Provider.captured['messages'][0]['content']:
                    result={'summary':'测试研究者甲、乙对始建时间的解释不同。[1]',
                            'agreements':'两种说法都提到建馆活动。[1]',
                            'differences':'甲关注筹建，乙关注开放时间，需区分事件定义。[1]',
                            'dependencies':'两份材料标注了共同史源，应核对版本与转引关系，不能当作独立互证。[1]',
                            'questions':'待查原始营建档案与开放记录，尚不能裁决年代。[1]'}
                elif payload['kind']=='event':
                    result={'title':'示例阅览馆筹建（功能测试）','date_text':'民国二十年前后','event_kind':'筹建','description':'材料记述筹建活动，具体年份待考。[1]'}
                else:
                    result={'title':'筹建与开放年代之辨（功能测试）','author':'测试研究者甲','publication_date':'2008（测试）','question':'如何界定始建年代？',
                            'claim':'作者认为应区分筹建与开放。[1]','method':'对读年报与后出研究。[1]','limitations':'尚缺原始工事档案。[1]','source_chain':'标有共同史源，转引关系待核。[1]'}
                if Provider.mode=='history-bad-ref':result['description' if payload.get('kind')=='event' else 'summary']='不存在的依据 [99]'
                if Provider.mode=='history-no-ref':result={k:v.replace('[1]','') for k,v in result.items()}
                self.wfile.write(json.dumps({'choices':[{'message':{'content':'not json' if Provider.mode=='history-bad' else json.dumps(result,ensure_ascii=False)},'finish_reason':'length' if Provider.mode=='history-truncated' else 'stop'}]}).encode());return
            if 'literature_analysis' in Provider.captured['messages'][0]['content']:
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                result={key:'依据功能测试摘要：研究公共空间使用情况，具体条件需阅读全文核对。[1]' for key in literature.FIELDS}
                if Provider.mode=='literature-bad':result['method']='不存在的来源 [99]'
                self.wfile.write(json.dumps({'choices':[{'message':{'content':json.dumps(result,ensure_ascii=False)},'finish_reason':'stop'}]}).encode());return
            if 'brief_interpretation' in Provider.captured['messages'][0]['content']:
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                data=brief_analysis(json.loads(Provider.captured['messages'][1]['content'])['sources'])
                if Provider.mode=='brief-quote':data['requirements'][0]['quote']='原文不存在的指标：建筑高度不得超过 99 米。'
                if Provider.mode=='brief-source':data['requirements'][0]['source']=99
                if Provider.mode=='brief-keyword':data['keywords'][0]['source']=True
                if Provider.mode=='brief-private-query':data['searches'][0]['query']='图书馆 someone@example.org'
                content='not JSON' if Provider.mode=='brief-bad' else json.dumps(data,ensure_ascii=False)
                self.wfile.write(json.dumps({'choices':[{'message':{'content':content},'finish_reason':'stop'}]}).encode());return
            if 'is_project' in Provider.captured['messages'][0]['content']:
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                data=web_analysis()
                if Provider.mode=='web-not-project':data['is_project']=False
                if Provider.mode=='web-bad':data['is_project']='true'
                if Provider.mode=='web-invalid-ref':data['summary']='无效引用 [99]。'
                self.wfile.write(json.dumps({'choices':[{'message':{'content':json.dumps(data,ensure_ascii=False)},'finish_reason':'stop'}]}).encode());return
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
            draft={'title':'示例庭院图书馆（测试资料）','kind':'案例','aliases':'Courtyard Library',
                   'tags':'公共建筑，庭院','content':'回游动线连接阅读空间与庭院。[1]',
                   'details':{'location':'当前摘录未提供','architect':'当前摘录未提供','space':'回游动线连接庭院。[1]'},
                   'analysis':{'innovations':'分析归纳：庭院与阅读空间形成联系。[1]',
                               'improvements':'分析建议：进一步核对采光与使用评价，当前摘录未提供。',
                               'takeaways':'可参考回游动线的组织方式，需结合具体场地验证。[1]'}}
            if Provider.mode=='draft-invalid-ref':draft['content']='待核对的主张。[99]'
            content='not json' if Provider.mode=='draft-bad' else json.dumps(draft,ensure_ascii=False)
            self.wfile.write(json.dumps({'choices':[{'message':{'content':content},'finish_reason':'stop'}]},ensure_ascii=False).encode());return
        self.send_response(200);self.send_header('Content-Type','application/json' if Provider.mode=='json' else 'text/event-stream');self.end_headers()
        if Provider.mode=='json':
            self.wfile.write(json.dumps({'choices':[{'message':{'content':'研究有局限 [1]。'},'finish_reason':'stop'}]},ensure_ascii=False).encode());return
        if Provider.mode=='broken':
            self.wfile.write(b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n');return
        for delta in ('## 结果\n','样本规模有限 [1]。','\n\n|方法|评价|\n|---|---|\n|实验|有局限|'):
            self.wfile.write(('data: '+json.dumps({'choices':[{'delta':{'content':delta}}]},ensure_ascii=False)+'\n\n').encode())
        self.wfile.write(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider=ThreadingHTTPServer(('127.0.0.1',0),Provider)
        threading.Thread(target=cls.provider.serve_forever,daemon=True).start()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        cls.server.daemon_threads=False
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.provider.shutdown();cls.provider.server_close()
    def setUp(self):
        config_env=patch.dict(os.environ,{'PAPER_CONFIG_FILE':'/nonexistent/researchdesk-test-config'})
        config_env.start();self.addCleanup(config_env.stop)
        self.tmp=tempfile.TemporaryDirectory()
        self.paths=patch.multiple(app,DATA=Path(self.tmp.name),DB=Path(self.tmp.name)/'library.sqlite3');self.paths.start()
        self.environment=patch.dict(os.environ,{'PAPER_API_KEY':'test-only-secret','PAPER_BASE_URL':f'http://127.0.0.1:{self.provider.server_port}/v1','PAPER_MODEL':'test-model'});self.environment.start()
        app.init_db();Provider.mode='stream';Provider.captured=None
        if self._testMethodName.startswith('test_history'):
            plugin_manager.set_enabled(app,'architecture-history',True)
        with app.connect() as conn:conn.execute("INSERT OR REPLACE INTO settings VALUES ('research_mode','general')")
    def tearDown(self):
        self.server._threads.join()
        app.stop_ocr()
        deadline=time.monotonic()+5
        while any(j['status']=='running' for j in app.OCR_JOBS.values()) and time.monotonic()<deadline:
            time.sleep(.02)
        app.OCR_JOBS.clear()
        self.environment.stop();self.paths.stop();self.tmp.cleanup()
    def request(self,path,method='GET',body=None,headers=None):
        raw=body if isinstance(body,bytes) else json.dumps(body).encode() if body is not None else None
        req=urllib.request.Request(self.url+path,data=raw,method=method,headers={'X-Requested-With':'ResearchDesk',**(headers or {})})
        try:
            with urllib.request.urlopen(req,timeout=10) as r:return r.status,r.read()
        except urllib.error.HTTPError as e:return e.code,e.read()
    def paper(self,title='A test study'):
        status,raw=self.request('/api/papers?filename=example.pdf','POST',fixture_pdf(title));self.assertEqual(status,201,raw)
        return json.loads(raw)['paper']
    def wait_ocr(self,pid):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            job=app.ocr_snapshot(pid)
            if job['status']!='running':return job
            time.sleep(.04)
        self.fail('OCR job timed out')
    @unittest.skipUnless(sys.platform=='darwin' and (app.ROOT/'ocr_macos').is_file(),'macOS OCR helper required')
    def test_ocr_updates_search_sources_and_resumes(self):
        p=self.paper();pid=p['id']
        with app.connect() as c:
            c.execute("UPDATE pages SET text='' WHERE paper_id=?",(pid,))
            c.execute('DELETE FROM chunks WHERE paper_id=?',(pid,))
            c.execute('UPDATE papers SET text_chars=0 WHERE id=?',(pid,))
        self.assertEqual(self.request('/api/ask','POST',{'paper_ids':[pid],'question':'研究方法'})[0],409)
        status,raw=self.request('/api/papers/'+pid+'/ocr','POST',{'scope':'missing'})
        self.assertEqual(status,202,raw);self.assertNotIn('_cancel',json.loads(raw)['job'])
        job=self.wait_ocr(pid);self.assertEqual(job['status'],'done',job);self.assertEqual(job['completed'],2)
        _,raw=self.request('/api/search?q=participants');self.assertEqual(json.loads(raw)['results'][0]['page'],1)
        refs,papers=app.retrieve([pid],'participants');self.assertIn('participants',refs[0]['text'])
        self.assertEqual(papers[0]['ocr_pages'],2);self.assertEqual(papers[0]['text_pages'],2)
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT SUM(length(text)) FROM pages WHERE paper_id=?',(pid,)).fetchone()[0],app.paper_row(pid,c)['text_chars'])
        _,raw=self.request('/api/papers/'+pid+'/ocr','POST',{'scope':'missing'});self.assertEqual(json.loads(raw)['job']['total'],0)
        self.assertEqual(self.request('/api/papers/'+pid+'/ocr','POST',{'scope':'page','page':99})[0],400)
    @unittest.skipIf(sys.platform=='win32','POSIX executable helper mock')
    def test_ocr_cancel_exclusive_and_preserve_progress(self):
        p=self.paper();pid=p['id'];helper=Path(self.tmp.name)/'ocr_macos'
        helper.write_text('#!'+sys.executable+'\nimport json,time\nprint(json.dumps({"page":1,"text":"已识别的内容应保存并用于后续搜索与问答。"}),flush=True)\ntime.sleep(20)\n')
        helper.chmod(0o700)
        with patch.object(app,'ROOT',Path(self.tmp.name)),patch.object(app.sys,'platform','darwin'):
            status,_=self.request('/api/papers/'+pid+'/ocr','POST',{'scope':'page','page':1});self.assertEqual(status,202)
            deadline=time.monotonic()+5
            while app.ocr_snapshot(pid)['completed']==0 and time.monotonic()<deadline:time.sleep(.02)
            self.assertEqual(self.request('/api/papers/'+pid+'/ocr','POST',{'scope':'page','page':2})[0],409)
            self.request('/api/papers/'+pid+'/ocr','DELETE');self.assertEqual(self.wait_ocr(pid)['status'],'cancelled')
        with app.connect() as c:
            row=c.execute('SELECT text,ocr_done FROM pages WHERE paper_id=? AND page=1',(pid,)).fetchone()
            self.assertIn('已识别',row['text']);self.assertEqual(row['ocr_done'],1)
    def test_knowledge_sources_links_archive_and_backup(self):
        a=self.paper('Architecture Book');b=self.paper('Case Research')
        status,raw=self.request('/api/knowledge','POST',{'kind':'术语','title':'庭院','aliases':'Courtyard','content':'围合的室外空间。[1]','tags':'空间，建筑设计','sources':[{'paper_id':a['id'],'page':1,'quote':'原文选段'}]})
        self.assertEqual(status,201,raw);term=json.loads(raw)['card']
        status,raw=self.request('/api/knowledge','POST',{'kind':'案例','title':'测试图书馆','content':'案例总结 [1] [2]','details':{'space':'回游动线'},'analysis':{'innovations':'分析归纳 [1]','improvements':'待验证','takeaways':'可借鉴 [2]'},'related_ids':[term['id']],'sources':[{'paper_id':a['id'],'page':1},{'paper_id':b['id'],'page':2}]})
        self.assertEqual(status,201,raw);case=json.loads(raw)['card'];self.assertEqual(case['sources'][1]['locator'],'PDF第2页')
        _,raw=self.request('/api/knowledge');cards={c['id']:c for c in json.loads(raw)['cards']}
        self.assertEqual(cards[term['id']]['related_ids'],[case['id']]);self.assertEqual(cards[case['id']]['related_ids'],[term['id']])
        self.request('/api/knowledge/'+case['id'],'PATCH',{'status':'archived'})
        _,raw=self.request('/api/knowledge');saved=next(c for c in json.loads(raw)['cards'] if c['id']==case['id'])
        self.assertEqual(saved['status'],'archived');self.assertEqual(saved['details']['space'],'回游动线');self.assertEqual(len(saved['sources']),2)
        self.request('/api/knowledge/'+case['id'],'PATCH',{'status':'organized','related_ids':[]})
        _,raw=self.request('/api/knowledge');term=next(c for c in json.loads(raw)['cards'] if c['id']==term['id']);self.assertEqual(term['related_ids'],[])
        _,raw=self.request('/api/knowledge/export?id='+case['id']);self.assertIn('可学习与参考之处',raw.decode());self.assertIn('Case Research',raw.decode());self.assertNotIn('## 庭院',raw.decode())
        _,raw=self.request('/api/export');self.assertIn('测试图书馆',raw.decode())
        _,raw=self.request('/api/backup')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            restored=Path(self.tmp.name)/'knowledge-backup.sqlite3';restored.write_bytes(z.read('data/library.sqlite3'))
        with closing(sqlite3.connect(restored)) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM knowledge').fetchone()[0],2)
            self.assertEqual(c.execute('SELECT count(*) FROM knowledge_sources').fetchone()[0],3)
    def test_knowledge_validation_is_atomic(self):
        p=self.paper();_,raw=self.request('/api/knowledge','POST',{'title':'保留原卡片','sources':[{'paper_id':p['id'],'page':1}]});card=json.loads(raw)['card']
        self.assertEqual(self.request('/api/knowledge/'+card['id'],'PATCH',{'title':'不应被保存','sources':[{'paper_id':p['id'],'page':999}]})[0],400)
        self.assertEqual(self.request('/api/knowledge/'+card['id'],'PATCH',{'related_ids':[card['id']]})[0],400)
        self.assertEqual(self.request('/api/knowledge','POST',{'title':'','kind':'不存在'})[0],400)
        self.assertEqual(self.request('/api/knowledge','POST',{'title':'x','analysis':[]})[0],400)
        _,raw=self.request('/api/knowledge');saved=json.loads(raw)['cards'][0];self.assertEqual(saved['title'],'保留原卡片');self.assertEqual(len(saved['sources']),1)
        self.assertEqual(self.request('/api/knowledge/'+('f'*16),'PATCH',{'status':'archived'})[0],404)
        app.init_db()
        with app.connect() as c:self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
    def test_knowledge_ai_draft_is_grounded_and_not_persisted(self):
        p=self.paper();other=self.paper('Excluded Book')
        status,raw=self.request('/api/knowledge/draft','POST',{'kind':'案例','focus':'庭院与空间组织','sources':[{'paper_id':p['id'],'page':2}]})
        self.assertEqual(status,200,raw);result=json.loads(raw);self.assertTrue(result['draft']['ai_generated']);self.assertEqual(result['draft']['status'],'inbox')
        self.assertIn('创新',Provider.captured['messages'][0]['content']);self.assertIn('Results:',Provider.captured['messages'][-1]['content']);self.assertNotIn('Excluded Book',Provider.captured['messages'][-1]['content'])
        self.assertEqual(result['refs'][0]['page'],2);self.assertEqual(result['draft']['sources'][0]['paper_id'],p['id']);self.assertFalse(Provider.captured['stream'])
        with app.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM knowledge').fetchone()[0],0)
        status,raw=self.request('/api/knowledge','POST',result['draft']);self.assertEqual(status,201,raw)
        self.assertNotIn(b'test-only-secret',raw);self.assertFalse(app.AI_LOCK.locked())
    def test_knowledge_ai_search_balanced_errors_and_citations(self):
        a=self.paper('Selected A');b=self.paper('Selected B')
        body={'kind':'知识','focus':'研究方法和实验结果','scope':'search','sources':[{'paper_id':a['id'],'page':1},{'paper_id':b['id'],'page':1}]}
        status,raw=self.request('/api/knowledge/draft','POST',body);self.assertEqual(status,200,raw)
        self.assertEqual({r['paper_id'] for r in json.loads(raw)['refs']},{a['id'],b['id']})
        Provider.mode='draft-invalid-ref';_,raw=self.request('/api/knowledge/draft','POST',body);self.assertTrue(json.loads(raw)['warnings'])
        Provider.mode='draft-bad';self.assertEqual(self.request('/api/knowledge/draft','POST',body)[0],502);self.assertFalse(app.AI_LOCK.locked())
        Provider.mode='unauthorized';status,raw=self.request('/api/knowledge/draft','POST',body);self.assertEqual(status,502);self.assertNotIn(b'test-only-secret',raw)
        Provider.mode='stream';app.AI_LOCK.acquire()
        try:self.assertEqual(self.request('/api/knowledge/draft','POST',body)[0],409)
        finally:app.AI_LOCK.release()
        body['sources'][0]['page']=999;self.assertEqual(self.request('/api/knowledge/draft','POST',body)[0],400)
        with app.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM knowledge').fetchone()[0],0)
    def test_pdf_import_duplicate_progress(self):
        p=self.paper();self.assertEqual(p['page_count'],2);self.assertGreater(p['text_chars'],50);self.assertEqual(p['year'],'2024')
        _,raw=self.request('/api/papers?filename=renamed.pdf','POST',fixture_pdf());self.assertTrue(json.loads(raw)['duplicate'])
        _,raw=self.request('/api/papers/'+p['id'],'PATCH',{'status':'done','current_page':999});self.assertEqual(json.loads(raw)['current_page'],2)
        with app.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM papers').fetchone()[0],1)
    def test_invalid_encrypted_pdf(self):
        self.assertEqual(self.request('/api/papers','POST',b'not a pdf')[0],400)
        w=PdfWriter();w.add_blank_page(width=20,height=20);w.encrypt('private');b=io.BytesIO();w.write(b)
        self.assertEqual(self.request('/api/papers','POST',b.getvalue())[0],400)
    def test_search_chinese_page_literal_wildcards(self):
        p=self.paper();_,raw=self.request('/api/search?q=participants');self.assertEqual(json.loads(raw)['results'][0]['page'],1)
        _,raw=self.request('/api/papers/'+p['id']+'/page?page=2');self.assertIn('12 percent',json.loads(raw)['text'])
        with app.connect() as c:c.execute('UPDATE pages SET text=? WHERE paper_id=? AND page=1',('样本量120；随机实验。',p['id']))
        _,raw=self.request('/api/search?q='+urllib.parse.quote('样本'));self.assertEqual(len(json.loads(raw)['results']),1)
        _,raw=self.request('/api/search?q=%25');self.assertEqual(json.loads(raw)['results'],[])
    def test_balanced_sources(self):
        a=self.paper('First');b=self.paper('Second');refs,_=app.retrieve([a['id'],b['id']],'研究方法和实验结果')
        self.assertEqual({r['paper_id'] for r in refs},{a['id'],b['id']});self.assertEqual([r['number'] for r in refs],list(range(1,len(refs)+1)))
        self.assertTrue(any('Methods' in r['text'] for r in refs));self.assertIn('样本',app.tokens('检查样本量'))
    def test_stream_and_persistence(self):
        p=self.paper();status,raw=self.request('/api/ask','POST',{'paper_ids':[p['id']],'question':'研究结果是什么？'})
        self.assertEqual(status,200,raw);events=[json.loads(line) for line in raw.splitlines()]
        self.assertEqual(events[0]['type'],'sources');self.assertEqual(events[-1]['type'],'done');self.assertTrue(any('样本' in e.get('text','') for e in events))
        self.assertEqual(Provider.captured['model'],'test-model');self.assertIn('PDF第',Provider.captured['messages'][-1]['content']);self.assertNotIn(b'test-only-secret',raw)
        _,history=self.request('/api/messages?ids='+p['id']);messages=json.loads(history)['messages'];self.assertEqual(len(messages),2);self.assertEqual(messages[1]['refs'][0]['paper_id'],p['id'])
    def test_json_and_broken_stream(self):
        p=self.paper();payload={'paper_ids':[p['id']],'question':'分析局限'};Provider.mode='json';_,raw=self.request('/api/ask','POST',payload)
        self.assertEqual(json.loads(raw.splitlines()[-1])['type'],'done');Provider.mode='broken';_,raw=self.request('/api/ask','POST',payload)
        self.assertEqual(json.loads(raw.splitlines()[-1])['type'],'error')
        with app.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM messages').fetchone()[0],2)
    def test_auth_error_redacted(self):
        p=self.paper();Provider.mode='unauthorized';status,raw=self.request('/api/ask','POST',{'paper_ids':[p['id']],'question':'分析'})
        self.assertEqual(status,502);self.assertNotIn(b'test-only-secret',raw);self.assertFalse(app.AI_LOCK.locked())
        with app.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM messages').fetchone()[0],0)
    def test_settings_notes_backup_export(self):
        p=self.paper();_,state=self.request('/api/state');self.assertNotIn(b'test-only-secret',state);self.assertTrue(json.loads(state)['config']['has_key'])
        status,raw=self.request('/api/models','POST',{});self.assertEqual(status,200);self.assertEqual(json.loads(raw)['models'],['other','test-model'])
        self.request('/api/notes','POST',{'paper_id':p['id'],'page':2,'quote':'12 percent','content':'检查证据强度'})
        _,raw=self.request('/api/export');self.assertIn('检查证据强度',raw.decode());_,raw=self.request('/api/backup')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertIn('data/library.sqlite3',z.namelist());self.assertTrue(any(n.endswith('.pdf') for n in z.namelist()));self.assertFalse(any('.env' in n for n in z.namelist()))
            restored=Path(self.tmp.name)/'restore.sqlite3';restored.write_bytes(z.read('data/library.sqlite3'))
        with closing(sqlite3.connect(restored)) as c:self.assertEqual(c.execute('SELECT content FROM notes').fetchone()[0],'检查证据强度')
    def test_note_refs_persist_across_books_rename_restart_and_backup(self):
        a=self.paper('Book A');b=self.paper('Book B')
        refs=[{'number':2,'paper_id':a['id'],'page':2,'title':'Forged','locator':'wrong'},
              {'number':4,'paper_id':b['id'],'page':1}]
        body={'content':'跨书比较 [2] 与 [4]，待核对 [99]。','refs':refs}
        status,raw=self.request('/api/notes','POST',body);self.assertEqual(status,201,raw);nid=json.loads(raw)['id']
        self.request('/api/papers/'+a['id'],'PATCH',{'title':'Renamed Book A','status':'archived'})
        app.init_db()
        _,raw=self.request('/api/state');state=json.loads(raw);self.assertTrue(state['note_refs_enabled'])
        n=next(n for n in state['notes'] if n['id']==nid)
        self.assertIsNone(n['paper_id']);self.assertEqual(n['content'],body['content'])
        self.assertEqual([(r['number'],r['paper_id'],r['page']) for r in n['refs']],[(2,a['id'],2),(4,b['id'],1)])
        self.assertEqual(n['refs'][0]['title'],'Renamed Book A');self.assertEqual(n['refs'][0]['locator'],'PDF第2页')
        for r in n['refs']:self.assertEqual(self.request('/api/papers/'+r['paper_id']+'/page?page='+str(r['page']))[0],200)
        _,raw=self.request('/api/export');self.assertIn('[2] Renamed Book A · PDF第2页',raw.decode())
        _,raw=self.request('/api/backup')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            restored=Path(self.tmp.name)/'notes-backup.sqlite3';restored.write_bytes(z.read('data/library.sqlite3'))
        with closing(sqlite3.connect(restored)) as c:
            self.assertEqual(len(json.loads(c.execute('SELECT refs FROM notes WHERE id=?',(nid,)).fetchone()[0])),2)
    def test_note_refs_validation_and_manual_text_source(self):
        _,raw=self.request('/api/papers?filename=guide.txt','POST','文本规范。应记录具体条件与适用范围。'.encode());p=json.loads(raw)['paper']
        good={'number':1,'paper_id':p['id'],'page':1}
        for refs in (None,{},[good,good],[{**good,'page':999}],[{**good,'number':True}],
                     [{**good,'paper_id':'f'*16}],[{**good,'number':0}]):
            status,raw=self.request('/api/notes','POST',{'content':'不应保存','refs':refs});self.assertEqual(status,400,raw)
        with app.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM notes').fetchone()[0],0)
        self.request('/api/notes','POST',{'paper_id':p['id'],'page':1,'content':'条件记录 [1]','quote':'应记录具体条件'})
        _,raw=self.request('/api/state');n=json.loads(raw)['notes'][0]
        self.assertEqual(n['refs'][0]['paper_id'],p['id']);self.assertIn('文本第1段',n['refs'][0]['locator'])
        self.assertEqual(n['refs'][0]['text'],'应记录具体条件')
    def test_legacy_note_migration_is_unambiguous_and_preserves_original(self):
        a=self.paper('Original Book');b=self.paper('Second Book');duplicate=self.paper('Duplicate Content')
        _,raw=self.request('/api/papers?filename=legacy.txt','POST','老笔记中的章节来源。条款与文字。'.encode());text=json.loads(raw)['paper']
        refs=[{'number':1,'paper_id':a['id'],'page':2,'title':a['title'],'locator':'PDF第2页'},
              {'number':2,'paper_id':b['id'],'page':1,'title':b['title'],'locator':'PDF第1页'}]
        content='保留历史分析 [1] 与 [2]。';old=content+'\n\n参考出处：\n'+'\n'.join(app.reference_line(r) for r in refs)
        with app.connect() as c:
            label=c.execute('SELECT label FROM pages WHERE paper_id=?',(text['id'],)).fetchone()[0]
            fallback='旧文字笔记 [1]。\n\n参考出处：\n[1] '+text['title']+' · '+label
            ambiguous='不可猜测 [1]。\n\n参考出处：\n[1] Second Book · PDF第1页'
            c.execute('UPDATE papers SET title=? WHERE id=?',('Second Book',duplicate['id']))
            c.execute('UPDATE papers SET title=? WHERE id=?',('Renamed Original',a['id']))
            c.execute('INSERT INTO messages (scope,role,content,refs,created_at) VALUES (?,?,?,?,?)',
                      ('test','assistant',content,json.dumps(refs),app.now()))
            c.execute('DROP TABLE notes')
            c.execute("CREATE TABLE notes (id TEXT PRIMARY KEY,paper_id TEXT REFERENCES papers(id),page INTEGER,content TEXT NOT NULL,quote TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL)")
            c.executemany('INSERT INTO notes VALUES (?,?,?,?,?,?)',[
                ('1'*16,None,None,old,'',app.now()),('2'*16,None,None,fallback,'',app.now()),
                ('3'*16,None,None,ambiguous,'',app.now())])
        app.init_db();app.init_db()
        _,raw=self.request('/api/state');notes={n['id']:n for n in json.loads(raw)['notes']}
        self.assertEqual(notes['1'*16]['content'],old);self.assertEqual(notes['1'*16]['display_content'],content)
        self.assertEqual(notes['1'*16]['refs'][0]['paper_id'],a['id']);self.assertEqual(notes['1'*16]['refs'][0]['title'],'Renamed Original')
        self.assertEqual(notes['2'*16]['refs'][0]['paper_id'],text['id'])
        self.assertEqual(notes['3'*16]['refs'],[]);self.assertEqual(notes['3'*16]['display_content'],ambiguous)
        _,raw=self.request('/api/export');export=raw.decode().split('## AI 问答记录')[0]
        self.assertEqual(export.count('参考出处：'),3);self.assertIn('[1] Renamed Original · PDF第2页',export)
    def web_result(self):
        r={'title':'庭院图书馆（功能测试）','url':'https://example.org/courtyard-library','snippet':'共享庭院组织图书馆空间、公共入口与回游动线；本段仅为功能测试材料，不代表真实项目。'*3}
        with patch.object(web,'bing_search',return_value=[r,r,{'title':'不可用地址','url':'http://127.0.0.1/private'}]),patch.object(web,'gooood_search',return_value=[]),patch.object(web,'brave_search',return_value=[r]):
            status,raw=self.request('/api/web-cases/search','POST',{'query':'庭院图书馆'})
        self.assertEqual(status,200,raw);items=json.loads(raw)['results'];self.assertEqual(len(items),1)
        return items[0]
    def test_web_search_history_dedup_and_safe_urls(self):
        a=self.web_result();b=self.web_result();self.assertEqual(a['id'],b['id'])
        _,raw=self.request('/api/web-cases');self.assertEqual(len(json.loads(raw)['results']),1)
        self.assertNotIn(b'test-only-secret',raw)
        self.assertEqual(self.request('/api/web-cases/search','POST',{'query':'x'})[0],400)
        self.assertEqual(self.request('/api/web-cases/search','POST',{'query':[]})[0],400)
        with patch.object(web,'bing_search',side_effect=OSError()),patch.object(web,'gooood_search',side_effect=OSError()),patch.object(web,'brave_search',side_effect=OSError()):
            _,raw=self.request('/api/web-cases/search','POST',{'query':'无结果关键词'})
        self.assertEqual(json.loads(raw)['results'],[]);self.assertTrue(json.loads(raw)['warnings'])
    def test_web_analysis_save_edit_export_and_backup(self):
        item=self.web_result();rid=item['id']
        with patch.object(web,'read_url',return_value=(item['url'],WEB_HTML,'text/html')):
            status,raw=self.request('/api/web-cases/'+rid+'/analyze','POST',{})
        self.assertEqual(status,200,raw);case=json.loads(raw)['case'];self.assertEqual(case['basis'],'page')
        self.assertIn('共享庭院',Provider.captured['messages'][-1]['content']);self.assertIn('数据',Provider.captured['messages'][0]['content'])
        self.assertNotIn('不得作为正文的页脚',case['source_excerpt']);self.assertNotIn(b'test-only-secret',raw)
        with patch.object(web,'read_url',side_effect=AssertionError('Cached analysis must not re-fetch')):
            self.assertEqual(self.request('/api/web-cases/'+rid+'/analyze','POST',{})[0],200)
        _,raw=self.request('/api/web-cases/'+rid+'/save','POST',{});cid=json.loads(raw)['card_id']
        _,raw=self.request('/api/web-cases/'+rid+'/save','POST',{});self.assertEqual(json.loads(raw)['card_id'],cid)
        self.assertTrue(json.loads(raw)['already_saved'])
        self.request('/api/knowledge/'+cid,'PATCH',{'content':'我的核对与修改 [1]。'})
        app.init_db()
        _,raw=self.request('/api/knowledge');card=next(c for c in json.loads(raw)['cards'] if c['id']==cid)
        self.assertEqual(card['kind'],'案例');self.assertEqual(card['status'],'inbox')
        self.assertEqual(card['web_sources'][0]['url'],item['url']);self.assertEqual(card['content'],'我的核对与修改 [1]。')
        _,raw=self.request('/api/knowledge/export?id='+cid);self.assertIn(item['url'],raw.decode());self.assertIn('创新点',raw.decode())
        _,raw=self.request('/api/backup')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            db=Path(self.tmp.name)/'web-backup.sqlite3';db.write_bytes(z.read('data/library.sqlite3'))
        with closing(sqlite3.connect(db)) as c:
            self.assertEqual(c.execute('SELECT saved_card_id FROM web_cases').fetchone()[0],cid)
            self.assertEqual(json.loads(c.execute('SELECT web_sources FROM knowledge WHERE id=?',(cid,)).fetchone()[0])[0]['url'],item['url'])
    def test_web_snippet_scope_and_analysis_failures(self):
        item=self.web_result();path='/api/web-cases/'+item['id']
        self.assertEqual(self.request(path+'/save','POST',{})[0],409)
        with patch.object(web,'read_url',side_effect=OSError('Source unavailable')):
            status,raw=self.request(path+'/analyze','POST',{})
        self.assertEqual(status,200,raw);case=json.loads(raw)['case'];self.assertEqual(case['basis'],'snippet');self.assertTrue(case['fetch_note'])
        with patch.object(web,'read_url',return_value=(item['url'],WEB_HTML,'text/html')):
            Provider.mode='web-bad';self.assertEqual(self.request(path+'/analyze','POST',{'force':True})[0],502)
            self.assertFalse(app.AI_LOCK.locked())
            Provider.mode='web-invalid-ref';_,raw=self.request(path+'/analyze','POST',{'force':True});self.assertIn('编号',json.loads(raw)['case']['fetch_note'])
            Provider.mode='web-not-project';self.assertEqual(self.request(path+'/analyze','POST',{'force':True})[0],200)
        self.assertEqual(self.request(path+'/save','POST',{})[0],409)
        self.assertEqual(self.request('/api/web-cases/'+('f'*16)+'/analyze','POST',{})[0],404)
    def test_web_private_addresses_redirects_and_html_extraction(self):
        for url in ('file:///etc/passwd','javascript:alert(1)','http://127.0.0.1/a','http://[::1]/',
                    'https://localhost/','https://user:password@example.org/','https://example.org:8080/'):
            with self.assertRaises(ValueError,msg=url):web.clean_url(url)
        with patch.object(web.socket,'getaddrinfo',return_value=[(0,0,0,'',('127.0.0.1',443))]):
            with self.assertRaises(ValueError):web.public_addresses('example.org',443)
        class Redirect:
            status=302
            def getheader(self,k,default=''):return 'http://127.0.0.1/private' if k=='Location' else default
        from unittest.mock import MagicMock
        connection=MagicMock();connection.getresponse.return_value=Redirect()
        with patch.object(web,'public_addresses',return_value=['8.8.8.8']),patch.object(web.socket,'create_connection'),patch.object(web.http.client,'HTTPConnection',return_value=connection):
            with self.assertRaises(ValueError):web.read_url('http://example.org/')
        parser=web.PageText();parser.feed(WEB_HTML);text=parser.text()
        self.assertIn('共享庭院',text);self.assertNotIn('不得作为正文',text)

    def test_proxy_dns_uses_independent_public_resolution_and_still_blocks_private(self):
        with patch.object(web.socket,'getaddrinfo',return_value=[(0,0,0,'',('198.18.3.10',443))]),patch.object(web,'encrypted_public_addresses',return_value=['47.93.61.213']) as fallback:
            self.assertEqual(web.public_addresses('www.gooood.cn',443),['47.93.61.213']);fallback.assert_called_once_with('www.gooood.cn')
        for address in ('127.0.0.1','192.168.1.1','169.254.169.254','::1'):
            with patch.object(web.socket,'getaddrinfo',return_value=[(0,0,0,'',(address,443)),(0,0,0,'',('198.18.3.10',443))]),patch.object(web,'encrypted_public_addresses') as fallback:
                with self.assertRaises(ValueError):web.public_addresses('example.org',443)
                fallback.assert_not_called()
        with self.assertRaises(ValueError):web.clean_url('http://198.18.3.10/private')

    def test_encrypted_dns_checks_addresses_and_tls_hostname(self):
        from unittest.mock import MagicMock
        connection=MagicMock();response=connection.getresponse.return_value;response.status=200
        with patch.object(web.http.client,'HTTPConnection',return_value=connection),patch.object(web.socket,'create_connection') as connect,patch.object(web.ssl,'create_default_context') as tls:
            response.read.return_value=json.dumps({'Status':0,'Answer':[{'type':1,'data':'47.93.61.213'}]}).encode()
            self.assertEqual(web.encrypted_public_addresses('www.gooood.cn'),['47.93.61.213'])
            connect.assert_called_with(('1.1.1.1',443),timeout=4)
            self.assertEqual(tls.return_value.wrap_socket.call_args.kwargs['server_hostname'],'cloudflare-dns.com')
            for address in ('198.18.3.10','127.0.0.1','169.254.169.254'):
                response.read.return_value=json.dumps({'Status':0,'Answer':[{'type':1,'data':address}]}).encode()
                with self.assertRaises(OSError):web.encrypted_public_addresses('example.org')

    def test_case_fetch_failure_explains_cause_without_calling_ai(self):
        item=self.web_result()
        with app.connect() as conn:conn.execute("UPDATE web_cases SET snippet='' WHERE id=?",(item['id'],))
        with patch.object(web,'read_url',side_effect=ValueError('网页地址指向非公开网络。')),patch.object(app,'provider_request') as provider:
            status,raw=self.request('/api/web-cases/'+item['id']+'/analyze','POST',{})
            self.assertEqual(status,422);self.assertIn('非公开网络',raw.decode());provider.assert_not_called()
        self.assertFalse(app.AI_LOCK.locked())

    def literature_result(self,body=None):
        with patch.object(literature,'crossref_search',return_value=[LITERATURE_FIXTURE]),patch.object(literature,'semantic_search',return_value=[{**LITERATURE_FIXTURE,'doi':'10.1234/TEST.ARCHITECTURE','provider':'Semantic Scholar'}]):
            status,raw=self.request('/api/literature/search','POST',body or {'query':'工业遗产 公共空间'})
        self.assertEqual(status,200,raw);data=json.loads(raw);self.assertEqual(len(data['results']),1);return data

    def test_literature_search_history_dedup_years_and_degraded_channel(self):
        first=self.literature_result();second=self.literature_result()
        self.assertNotEqual(first['search']['id'],second['search']['id'])
        self.assertEqual(set(first['results'][0]['providers']),{'Crossref','Semantic Scholar'})
        self.assertEqual(self.request('/api/literature/search','POST',{'query':'aa','year_from':'2026','year_to':'2020'})[0],400)
        with patch.object(literature,'crossref_search',return_value=[LITERATURE_FIXTURE]),patch.object(literature,'semantic_search',side_effect=OSError()):
            status,raw=self.request('/api/literature/search','POST',{'query':'adaptive reuse','year_from':'2025'})
            self.assertEqual(status,200,raw);data=json.loads(raw);self.assertEqual(data['results'],[]);self.assertTrue(data['search']['warnings'])
        with patch.object(literature,'crossref_search',side_effect=OSError()),patch.object(literature,'semantic_search',side_effect=OSError()):
            self.assertEqual(self.request('/api/literature/search','POST',{'query':'architecture'})[0],502)
        _,raw=self.request('/api/literature/searches/'+first['search']['id']);self.assertEqual(json.loads(raw)['results'],first['results'])
        self.assertEqual(literature.normalize([{**LITERATURE_FIXTURE,'doi':'','url':'http://127.0.0.1/'}]),[])

    def test_literature_analysis_sources_save_import_export_and_backup(self):
        data=self.literature_result();item=data['results'][0];path='/api/literature/'+item['id']
        status,raw=self.request(path+'/analyze','POST',{});self.assertEqual(status,200,raw)
        evidence=json.loads(Provider.captured['messages'][1]['content']);self.assertEqual(evidence['source']['abstract'],item['abstract']);self.assertIn('未阅读全文',evidence['scope'])
        _,raw=self.request(path+'/save','POST',{});cid=json.loads(raw)['card_id']
        self.assertEqual(json.loads(self.request(path+'/save','POST',{})[1])['card_id'],cid)
        _,raw=self.request('/api/knowledge');card=next(c for c in json.loads(raw)['cards'] if c['id']==cid);self.assertEqual(card['web_sources'][0]['basis'],'abstract');self.assertEqual(card['web_sources'][0]['url'],item['url'])
        self.request('/api/knowledge/'+cid,'PATCH',{'content':'我核对后的内容 [1]。'})
        self.request(path+'/analyze','POST',{'force':True})
        self.assertEqual(next(c for c in json.loads(self.request('/api/knowledge')[1])['cards'] if c['id']==cid)['content'],'我核对后的内容 [1]。')
        status,raw=self.request(path+'/import','POST',{});self.assertEqual(status,200,raw);pid=json.loads(raw)['paper_id']
        self.assertEqual(json.loads(self.request(path+'/import','POST',{})[1])['paper_id'],pid)
        with app.connect() as conn:
            paper=app.paper_row(pid,conn);self.assertEqual(paper['origin_url'],item['url']);self.assertTrue(paper['title'].startswith('【摘要】'))
        _,raw=self.request('/api/literature/searches/'+data['search']['id']+'/ris');self.assertIn(b'DO  - 10.1234/',raw)
        _,raw=self.request('/api/export');self.assertIn('网络文献',raw.decode());self.assertIn(item['url'],raw.decode())
        _,raw=self.request('/api/backup')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            db=Path(self.tmp.name)/'restored.sqlite3';db.write_bytes(archive.read('data/library.sqlite3'))
        with closing(sqlite3.connect(db)) as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM web_literature').fetchone()[0],1)

    def test_literature_missing_abstract_and_invalid_analysis_are_not_saved(self):
        item=self.literature_result()['results'][0];path='/api/literature/'+item['id']
        Provider.mode='literature-bad'
        self.assertEqual(self.request(path+'/analyze','POST',{})[0],502);self.assertFalse(app.AI_LOCK.locked())
        self.assertEqual(self.request(path+'/save','POST',{})[0],409)
        with app.connect() as conn:conn.execute("UPDATE web_literature SET abstract='' WHERE id=?",(item['id'],))
        with patch.object(app,'provider_request') as provider:
            self.assertEqual(self.request(path+'/analyze','POST',{})[0],422);provider.assert_not_called()

    def test_literature_brief_and_reader_context_remains_separate(self):
        status,raw=self.request('/api/briefs','POST',{'text':BRIEF_TEXT});self.assertEqual(status,200,raw);brief=json.loads(raw)['brief']
        data=self.literature_result({'query':'图书馆 公共空间','brief_id':brief['id'],'focus':'空间使用评价'})
        self.assertEqual(data['search']['context_title'],brief['title'])
        status,raw=self.request('/api/literature/'+data['results'][0]['id']+'/analyze','POST',{});self.assertEqual(status,200,raw)
        context=json.loads(Provider.captured['messages'][1]['content'])['context'];self.assertIn('brief_summary',context)
        _,raw=self.request('/api/briefs/'+brief['id']);self.assertEqual(json.loads(raw)['brief']['literature_history'][0]['id'],data['search']['id'])
        _,raw=self.request('/api/briefs/'+brief['id']+'/export');self.assertIn(data['results'][0]['url'],raw.decode())
        paper=self.paper();other=self.literature_result({'query':'空间使用评价','paper_id':paper['id']})
        self.assertEqual(other['search']['context_title'],paper['title']);self.assertIsNone(other['search']['brief_id'])
    def test_architecture_search_parser_uses_project_results_only(self):
        html='<a href="/advertising.htm"><img alt="Unrelated navigation project"></a><article><a href="/library.htm" data-zh="庭院图书馆 / 测试团队"><img alt="thumbnail"></a></article>'
        parser=web.SearchLinks('https://www.gooood.cn/search?q=图书馆');parser.feed(html)
        self.assertEqual(len(parser.results),1);self.assertEqual(parser.results[0]['title'],'庭院图书馆 / 测试团队')
        with patch.object(web,'read_url',return_value=('https://www.gooood.cn/search?q=x',html,'text/html')) as read:
            self.assertEqual(len(web.gooood_search('图书馆')),1)
        self.assertIn('/search?q=',read.call_args[0][0])
    def test_mixed_web_local_sources_keep_numbering_and_draft(self):
        p=self.paper();body={'title':'跨来源案例','kind':'案例','content':'网页 [1] 与本书 [2]。',
            'sources':[{'paper_id':p['id'],'page':2}],
            'web_sources':[{'url':'https://example.org/library','title':'网页来源','quote':'共享庭院与回游动线的功能测试摘录。'}]}
        status,raw=self.request('/api/knowledge','POST',body);self.assertEqual(status,201,raw)
        card=json.loads(raw)['card'];self.assertEqual(card['web_sources'][0]['number'],1);self.assertEqual(card['sources'][0]['number'],2)
        self.assertEqual(self.request('/api/knowledge/'+card['id'],'PATCH',{'web_sources':[{'url':'javascript:alert(1)'}]})[0],400)
        status,raw=self.request('/api/knowledge/draft','POST',{'kind':'案例','focus':'跨来源比较','sources':body['sources'],'web_sources':body['web_sources']})
        self.assertEqual(status,200,raw);draft=json.loads(raw)['draft'];self.assertEqual(len(draft['web_sources']),1);self.assertEqual(len(draft['sources']),1)
        self.assertIn('网页来源',Provider.captured['messages'][-1]['content']);self.assertIn('Results:',Provider.captured['messages'][-1]['content'])
        status,raw=self.request('/api/knowledge/draft','POST',{'kind':'案例','focus':'庭院空间','scope':'search','sources':[],'web_sources':body['web_sources']})
        self.assertEqual(status,200,raw);self.assertEqual(len(json.loads(raw)['draft']['web_sources']),1)
    def create_brief(self,**body):
        status,raw=self.request('/api/briefs','POST',body or {'title':'社区图书馆任务（测试）','text':BRIEF_TEXT})
        self.assertEqual(status,200,raw)
        return json.loads(raw)['brief']

    def test_brief_paste_history_export_and_backup(self):
        brief=self.create_brief()
        self.assertEqual(brief['input_text'],BRIEF_TEXT)
        self.assertIsNone(brief['paper_id'])
        self.assertEqual(brief['sources'][0]['number'],1)
        status,raw=self.request('/api/briefs');self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)['briefs'][0]['id'],brief['id'])
        status,raw=self.request('/api/briefs/'+brief['id']);self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)['brief']['analysis'],brief['analysis'])
        status,raw=self.request('/api/briefs/'+brief['id']+'/export');self.assertEqual(status,200,raw)
        self.assertIn('3000 平方米',raw.decode());self.assertIn('分析建议',raw.decode())
        self.assertIn('任务书解读',app.export_markdown().decode())
        status,raw=self.request('/api/backup');self.assertEqual(status,200)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            database=Path(self.tmp.name)/'brief-backup.sqlite3'
            database.write_bytes(archive.read('data/library.sqlite3'))
        with closing(sqlite3.connect(database)) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM design_briefs').fetchone()[0],1)

    def test_brief_document_coverage_and_ocr_boundary(self):
        paper=self.paper()
        with app.connect() as conn:
            conn.execute('UPDATE pages SET text=? WHERE paper_id=? AND page=1',(BRIEF_TEXT,paper['id']))
            conn.execute('UPDATE pages SET text=? WHERE paper_id=? AND page=2',('',paper['id']))
        brief=self.create_brief(paper_id=paper['id'],start_page=1,end_page=2)
        self.assertEqual(brief['sources'][0]['paper_id'],paper['id'])
        self.assertEqual(brief['sources'][0]['page'],1)
        self.assertEqual(brief['coverage']['missing'],[2])
        partial=self.create_brief(paper_id=paper['id'],start_page=1,end_page=1)
        self.assertIn('范围外',' '.join(partial['coverage']['warnings']))
        Provider.captured=None
        status,raw=self.request('/api/briefs','POST',{'paper_id':paper['id'],'start_page':2,'end_page':2})
        self.assertEqual(status,422);self.assertIn('文字识别',json.loads(raw)['error']);self.assertIsNone(Provider.captured)
        with app.connect() as conn:
            conn.execute('UPDATE pages SET text=? WHERE paper_id=? AND page=1',('很长的原文'*7000,paper['id']))
        status,raw=self.request('/api/briefs','POST',{'paper_id':paper['id']})
        self.assertEqual(status,422);self.assertIsNone(Provider.captured)
        self.assertEqual(self.request('/api/briefs','POST',{'paper_id':paper['id'],'start_page':True})[0],400)

    def test_brief_rejects_unverifiable_ai_without_partial_save(self):
        for mode in ('brief-bad','brief-source','brief-quote','brief-keyword','brief-private-query'):
            Provider.mode=mode
            status,raw=self.request('/api/briefs','POST',{'text':BRIEF_TEXT})
            self.assertEqual(status,502,(mode,raw));self.assertNotIn('test-only-secret',raw.decode())
            self.assertFalse(app.AI_LOCK.locked())
        with app.connect() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM design_briefs').fetchone()[0],0)
        with patch.dict(os.environ,{'PAPER_API_KEY':'','OPENAI_API_KEY':''}):
            self.assertEqual(self.request('/api/briefs','POST',{'text':BRIEF_TEXT})[0],409)
        self.assertEqual(self.request('/api/briefs/'+'0'*16)[0],404)

    def test_brief_search_context_isolated_and_grounded(self):
        brief=self.create_brief()
        candidate={'title':'庭院图书馆（测试）','url':'https://example.org/library','snippet':'共享庭院组织公共阅读空间。'*10}
        body={'query':'社区图书馆','learning_focus':'研究动静分区与儿童看护视线'}
        with patch.object(web,'bing_search',return_value=[candidate]) as search,patch.object(web,'gooood_search',return_value=[]),patch.object(web,'brave_search',return_value=[candidate]):
            status,raw=self.request('/api/briefs/'+brief['id']+'/search','POST',body);self.assertEqual(status,200,raw)
            scoped=json.loads(raw)['results'][0]
            status,raw=self.request('/api/web-cases/search','POST',body);ordinary=json.loads(raw)['results'][0]
            self.assertNotEqual(scoped['id'],ordinary['id'])
            self.assertEqual(scoped['learning_focus'],body['learning_focus'])
            status,raw=self.request('/api/briefs/'+brief['id']+'/search','POST',body)
            self.assertEqual(json.loads(raw)['results'][0]['id'],scoped['id'])
            for call in search.call_args_list:
                self.assertEqual(call.args[0],'社区图书馆 建筑 案例')
                self.assertNotIn('3000',call.args[0]);self.assertNotIn('儿童看护',call.args[0])
        with patch.object(web,'read_url',return_value=(candidate['url'],WEB_HTML,'text/html')):
            status,raw=self.request('/api/web-cases/'+scoped['id']+'/analyze','POST',{})
        self.assertEqual(status,200,raw)
        payload=Provider.captured['messages'][1]['content']
        self.assertIn('研究动静分区与儿童看护视线',payload);self.assertIn('3000 平方米',payload)
        with app.connect() as conn:
            self.assertEqual(json.loads(conn.execute('SELECT analysis FROM web_cases WHERE id=?',(ordinary['id'],)).fetchone()[0]),{})
        status,raw=self.request('/api/web-cases/'+scoped['id']+'/save','POST',{});self.assertEqual(status,200,raw)
        card_id=json.loads(raw)['card_id']
        with app.connect() as conn:
            card=conn.execute('SELECT * FROM knowledge WHERE id=?',(card_id,)).fetchone()
            self.assertIn(brief['title'],card['content']);self.assertIn(candidate['url'],card['web_sources'])
        status,raw=self.request('/api/briefs/'+brief['id']);history=json.loads(raw)['brief']['history']
        self.assertEqual(len(history),1);self.assertEqual(history[0]['count'],1)
        status,raw=self.request('/api/web-cases?brief_id='+brief['id'])
        self.assertEqual([entry['id'] for entry in json.loads(raw)['results']],[scoped['id']])
        status,raw=self.request('/api/briefs/'+brief['id']+'/export');self.assertEqual(status,200)
        self.assertIn(candidate['url'],raw.decode());self.assertIn(body['learning_focus'],raw.decode())
        second=self.create_brief(title='第二份任务（测试）',text=BRIEF_TEXT)
        with patch.object(web,'bing_search',return_value=[candidate]),patch.object(web,'gooood_search',return_value=[]),patch.object(web,'brave_search',return_value=[candidate]):
            _,raw=self.request('/api/briefs/'+brief['id']+'/search','POST',{**body,'learning_focus':'学习结构设计'})
            other_focus=json.loads(raw)['results'][0]
            _,raw=self.request('/api/briefs/'+second['id']+'/search','POST',body)
            other_brief=json.loads(raw)['results'][0]
        self.assertEqual(len({scoped['id'],ordinary['id'],other_focus['id'],other_brief['id']}),4)

    def test_brief_literal_document_reference_is_preserved(self):
        sources=[{'number':1,'quote':'参考文献[2024]仅为任务书自带编号，方案需说明公共空间组织。'}]
        result=brief_analysis(sources)
        result['requirements'][0]['text']='方案需说明公共空间组织。'
        valid=app.briefs.validate_analysis(result,sources)
        self.assertIn('[2024]',valid['requirements'][0]['quote'])
        result['summary']='未经核对的结论[99]'
        with self.assertRaises(ValueError):app.briefs.validate_analysis(result,sources)

    def test_web_scope_migration_preserves_saved_old_cases(self):
        conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('CREATE TABLE knowledge (id TEXT PRIMARY KEY)');conn.execute("INSERT INTO knowledge VALUES ('saved-card')")
        conn.execute('''CREATE TABLE web_cases (id TEXT PRIMARY KEY,query TEXT,title TEXT,url TEXT,snippet TEXT,engine TEXT,
            discovered_at TEXT,page_text TEXT,basis TEXT,fetch_note TEXT,analysis TEXT,analyzed_at TEXT,
            saved_card_id TEXT REFERENCES knowledge(id),UNIQUE(query,url))''')
        conn.execute('INSERT INTO web_cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                     ('0123456789abcdef','图书馆','旧案例','https://example.org/old','','test','today','原文','page','',json.dumps(web_analysis()),'today','saved-card'))
        web.init_schema(conn);web.init_schema(conn)
        row=conn.execute('SELECT * FROM web_cases').fetchone()
        self.assertEqual(row['saved_card_id'],'saved-card');self.assertEqual(row['brief_id'],'')
        self.assertEqual(json.loads(row['analysis']),web_analysis());self.assertEqual(row['page_text'],'原文')
        self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[]);conn.close()

    def hs_create(self,body):
        status,raw=self.request('/api/history','POST',body);self.assertEqual(status,201,raw);return json.loads(raw)['record']
    def hs_evidence(self,pid=None,original='民国二十年前后筹建。（功能测试，非真实史料）',**fields):
        data={'source_title':'示例馆年报（功能测试）','creator':'测试编纂者','edition':'测试版本','source_date':'1934（测试）',
              'volume':'卷一','printed_page':'十二','origin_key':'示例馆年报-测试版本','original':original,**fields}
        if pid:data.update(paper_id=pid,page=2)
        return self.hs_create({'kind':'evidence','subject':'示例阅览馆（功能测试）','title':'筹建记载','data':data})
    def hs_event(self,ids,**fields):
        return self.hs_create({'kind':'event','subject':'示例阅览馆（功能测试）','title':'筹建年代异说','source_ids':ids,
            'data':{'date_text':'民国二十年前后','event_kind':'筹建','description':'原文记载筹建，尚待核对。[1]','precision':'约年','year_start':1931,**fields}})
    def hs_view(self,ids,**fields):
        return self.hs_create({'kind':'view','subject':'示例阅览馆（功能测试）','title':'筹建年代解释','source_ids':ids,
            'data':{'author':'测试研究者甲','publication_date':'2008','question':'如何界定始建？','claim':'将筹建作为起点。[1]',
                    'method':'文本互证','source_chain':'引年报，转引关系待查','limitations':'需核原始档案',**fields}})
    def hs_snapshot(self):return json.loads(self.request('/api/history')[1])

    def test_history_evidence_corrections_revisions_links_and_atomic_edit(self):
        p=self.paper();e=self.hs_evidence(p['id']);data={**e['data'],'corrected':'民国二十一年前后筹建。','correction_note':'对照图像校正十一字（测试）','interpretation':'目前只能判断筹建时间。'}
        status,raw=self.request('/api/history/'+e['id'],'PATCH',{'revision':1,'data':data});self.assertEqual(status,200,raw)
        updated=json.loads(raw)['record'];self.assertEqual(updated['revision'],2);self.assertEqual(updated['data']['original'],e['data']['original'])
        self.assertEqual(self.request('/api/history/'+e['id'],'PATCH',{'revision':1,'title':'不应覆盖'})[0],409)
        self.assertEqual(self.request('/api/history/'+e['id'],'PATCH',{'revision':2,'data':{**data,'page':999}})[0],400)
        refs=self.hs_snapshot()['records'][0]['refs'];self.assertEqual((refs[0]['paper_id'],refs[0]['page']),(p['id'],2));self.assertIn('十二',refs[0]['locator'])
        versions=json.loads(self.request('/api/history/'+e['id']+'/revisions')[1])['revisions']
        self.assertEqual([v['revision'] for v in versions],[2,1]);self.assertEqual(versions[1]['data']['corrected'],'')
        _,raw=self.request('/api/history/source?paper_id='+p['id']+'&page=2');self.assertIn('Results:',json.loads(raw)['text'])
        self.assertEqual(self.request('/api/history/source?paper_id='+p['id']+'&page=99')[0],404)
        with app.connect() as conn:conn.execute('UPDATE pages SET text=? WHERE paper_id=? AND page=2',('字'*25000,p['id']))
        source=json.loads(self.request('/api/history/source?paper_id='+p['id']+'&page=2')[1]);self.assertTrue(source['truncated']);self.assertEqual(len(source['text']),24000)
        app.init_db();self.assertEqual(self.hs_snapshot()['records'][0]['revision'],2)

    def test_history_sources_and_timeline_uncertainty_validation(self):
        e=self.hs_evidence(url='https://example.org/archive/1')
        for changed in ({'url':'http://127.0.0.1/'},{'original':''},{'original':3},{'url':'javascript:alert(1)'},{'paper_id':[],'printed_page':'','url':''}):
            status,_=self.request('/api/history','POST',{'kind':'evidence','subject':'测试','title':'不可保存','data':{**e['data'],**changed}});self.assertEqual(status,400)
        a=self.hs_event([e['id']]);b=self.hs_event([e['id']],date_text='另一说：民国二十一年',precision='明确',year_start=1932)
        self.assertNotEqual(a['id'],b['id']);self.assertEqual(a['data']['year_end'],1931)
        interval=self.hs_event([e['id']],precision='区间',year_start=-200,year_end=-150,date_text='公元前二世纪');self.assertEqual(interval['data']['year_start'],-200)
        unknown=self.hs_event([e['id']],precision='不详',year_start=None,year_end=None,date_text='年代不详');self.assertIsNone(unknown['data']['year_start'])
        base={'kind':'event','subject':a['subject'],'title':'不保存','source_ids':[e['id']],'data':a['data']}
        for d in ({'precision':'不详'},{'year_start':0},{'year_start':True},{'year_start':1933,'year_end':1932},{'precision':'区间','year_end':None},{'description':'无此来源 [99]'}):
            self.assertEqual(self.request('/api/history','POST',{**base,'data':{**a['data'],**d}})[0],400)
        self.assertEqual(self.request('/api/history','POST',{**base,'source_ids':[e['id'],e['id']]})[0],400)
        self.assertEqual(self.request('/api/history','POST',{**base,'source_ids':[a['id']]})[0],400)

    def test_history_draft_is_selected_grounded_unstored_and_rejects_stale(self):
        p=self.paper();e=self.hs_evidence(p['id'],corrected='民国二十一年前后筹建。',interpretation='测试推断，不是原文');self.hs_evidence(original='不应发往模型的未选材料')
        body={'kind':'event','subject':e['subject'],'focus':'筹建年代','source_ids':[e['id']]}
        status,raw=self.request('/api/history/draft','POST',body);self.assertEqual(status,200,raw);draft=json.loads(raw)['draft']
        self.assertEqual(draft['status'],'待核对');self.assertIsNone(draft['data']['year_start']);self.assertEqual(draft['data']['precision'],'不详')
        payload=json.loads(Provider.captured['messages'][1]['content']);self.assertEqual(len(payload['sources']),1);ref=payload['sources'][0]
        self.assertEqual(ref['original'],e['data']['original']);self.assertEqual(ref['corrected'],e['data']['corrected']);self.assertEqual(ref['interpretation'],e['data']['interpretation'])
        self.assertNotIn('不应发往模型',json.dumps(payload,ensure_ascii=False));self.assertIn('architecture_history',Provider.captured['messages'][0]['content'])
        self.assertEqual(len(self.hs_snapshot()['records']),2)
        status,raw=self.request('/api/history/draft','POST',{**body,'kind':'view'});self.assertEqual(status,200,raw);view=json.loads(raw)['draft'];self.hs_create(view)
        self.request('/api/history/'+e['id'],'PATCH',{'revision':1,'title':'已核新版本'})
        self.assertEqual(self.request('/api/history','POST',draft)[0],409);self.assertFalse(app.AI_LOCK.locked())

    def test_history_ai_failures_never_save_partial_results_or_hold_lock(self):
        e=self.hs_evidence();body={'kind':'event','subject':e['subject'],'focus':'筹建年代','source_ids':[e['id']]}
        for mode in ('history-bad','history-bad-ref','history-no-ref','history-truncated','unauthorized'):
            Provider.mode=mode;status,raw=self.request('/api/history/draft','POST',body);self.assertEqual(status,502,raw);self.assertNotIn(b'test-only-secret',raw);self.assertFalse(app.AI_LOCK.locked())
        Provider.mode='stream';app.AI_LOCK.acquire()
        try:self.assertEqual(self.request('/api/history/draft','POST',body)[0],409)
        finally:app.AI_LOCK.release()
        self.assertEqual(len(self.hs_snapshot()['records']),1)
        large=self.hs_evidence(original='字'*23000,corrected='字'*23000)
        self.assertEqual(self.request('/api/history/draft','POST',{**body,'source_ids':[large['id']]})[0],400)

    def test_history_comparison_rebases_citations_preserves_snapshots_and_flags_updates(self):
        e1=self.hs_evidence();e2=self.hs_evidence(original='另一份材料记载次年开放（测试）')
        v1=self.hs_view([e1['id'],e2['id']],claim='筹建 [1] 与开放 [2] 分别对待。');v2=self.hs_view([e2['id'],e1['id']],author='测试研究者乙',claim='重视开放 [1]，筹建为辅 [2]。')
        status,raw=self.request('/api/history/compare','POST',{'view_ids':[v1['id'],v2['id']]});self.assertEqual(status,200,raw)
        result=json.loads(raw)['comparison'];self.assertEqual(len(result['refs']),2)
        payload=json.loads(Provider.captured['messages'][1]['content']);self.assertEqual(payload['views'][1]['source_numbers'],[2,1]);self.assertIn('开放 [2]',payload['views'][1]['data']['claim'])
        self.assertEqual(payload['sources'][0]['origin_key'],payload['sources'][1]['origin_key']);self.assertIn('不能按观点数量',Provider.captured['messages'][0]['content'])
        self.request('/api/history/'+e1['id'],'PATCH',{'revision':1,'data':{**e1['data'],'corrected':'新校订'}})
        snapshot=self.hs_snapshot();comparison=snapshot['comparisons'][0];self.assertTrue(comparison['stale']);self.assertEqual(comparison['refs'][0]['revision'],1)
        for v in (v1,v2):self.assertTrue(next(r for r in snapshot['records'] if r['id']==v['id'])['stale_sources'])
        self.assertEqual(self.request('/api/history/compare','POST',{'view_ids':[v1['id'],v2['id']]})[0],409)
        for v in (v1,v2):
            status,raw=self.request('/api/history/'+v['id'],'PATCH',{'revision':1,'source_ids':[s['evidence_id'] for s in v['sources']]});self.assertEqual(status,200,raw)
        self.assertEqual(self.request('/api/history/compare','POST',{'view_ids':[v1['id'],v2['id']]})[0],200)
        self.assertTrue(next(c for c in self.hs_snapshot()['comparisons'] if c['id']==comparison['id'])['stale'])
        self.assertEqual(self.request('/api/history/compare','POST',{'view_ids':[v1['id'],v1['id']]})[0],400)
        self.request('/api/history/'+v2['id'],'PATCH',{'revision':2,'subject':'另一个研究对象'})
        self.assertEqual(self.request('/api/history/compare','POST',{'view_ids':[v1['id'],v2['id']]})[0],400)

    def test_history_comparison_concurrent_evidence_edit_does_not_persist(self):
        e=self.hs_evidence();v1=self.hs_view([e['id']]);v2=self.hs_view([e['id']],author='测试研究者乙')
        original=history.ai_json
        def change_during_analysis(*args,**kwargs):
            result=original(*args,**kwargs);history.save({'revision':1,'title':'分析中更新'},app,e['id']);return result
        with patch.object(history,'ai_json',side_effect=change_during_analysis):
            self.assertEqual(self.request('/api/history/compare','POST',{'view_ids':[v1['id'],v2['id']]})[0],409)
        self.assertEqual(self.hs_snapshot()['comparisons'],[])

    def test_history_export_and_backup_include_evidence_versions(self):
        e=self.hs_evidence(url='https://example.org/archive/1');self.hs_event([e['id']]);v1=self.hs_view([e['id']]);v2=self.hs_view([e['id']],author='测试研究者乙')
        self.request('/api/history/compare','POST',{'view_ids':[v1['id'],v2['id']]})
        self.request('/api/history/'+e['id'],'PATCH',{'revision':1,'data':{**e['data'],'corrected':'校订文本','interpretation':'个人解释'}})
        for path in ('/api/history/export','/api/export'):
            status,raw=self.request(path);self.assertEqual(status,200,raw);output=raw.decode();self.assertIn(e['data']['original'],output);self.assertIn('校订文本',output);self.assertIn('个人解释',output);self.assertIn('https://example.org/archive/1',output);self.assertIn('共同史源',output)
        _,raw=self.request('/api/history/export?subject=missing');self.assertNotIn(e['title'],raw.decode())
        _,raw=self.request('/api/backup')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            db=Path(self.tmp.name)/'history-backup.sqlite3';db.write_bytes(archive.read('data/library.sqlite3'))
        with closing(sqlite3.connect(db)) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM history_revisions WHERE record_id=?',(e['id'],)).fetchone()[0],2)
            self.assertEqual(conn.execute('SELECT count(*) FROM history_comparisons').fetchone()[0],1)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_history_mode_default_toggle_and_selected_ai_workflows(self):
        with app.connect() as conn:conn.execute("DELETE FROM settings WHERE key='research_mode'")
        cfg=json.loads(self.request('/api/settings')[1]);self.assertEqual(cfg['research_mode'],'general');self.assertNotIn('key',cfg)
        self.request('/api/research-mode','POST',{'mode':'history'})
        self.assertEqual(self.request('/api/research-mode','POST',{'mode':'bad'})[0],400)
        p=self.paper();self.request('/api/ask','POST',{'paper_ids':[p['id']],'question':'研究方法'})
        self.assertIn('architecture_history',Provider.captured['messages'][0]['content'])
        status,raw=self.request('/api/knowledge/draft','POST',{'kind':'知识','focus':'历史贡献','sources':[{'paper_id':p['id'],'page':1}]});self.assertEqual(status,200,raw)
        draft=json.loads(raw)['draft'];self.assertEqual(draft['analysis_mode'],'history');self.assertIn('architecture_history',Provider.captured['messages'][0]['content'])
        _,raw=self.request('/api/knowledge','POST',draft);card=json.loads(raw)['card']
        item=self.web_result();path='/api/web-cases/'+item['id']
        with patch.object(web,'read_url',return_value=(item['url'],WEB_HTML,'text/html')):status,raw=self.request(path+'/analyze','POST',{})
        self.assertEqual(status,200,raw);self.assertEqual(json.loads(raw)['case']['analysis_mode'],'history');self.assertIn('architecture_history',Provider.captured['messages'][0]['content'])
        data=self.literature_result();lit='/api/literature/'+data['results'][0]['id'];status,raw=self.request(lit+'/analyze','POST',{});self.assertEqual(status,200,raw)
        self.assertEqual(json.loads(raw)['item']['analysis_mode'],'history');self.assertIn('architecture_history',Provider.captured['messages'][0]['content'])
        self.request('/api/research-mode','POST',{'mode':'general'})
        self.request('/api/ask','POST',{'paper_ids':[p['id']],'question':'研究方法'});self.assertNotIn('architecture_history',Provider.captured['messages'][0]['content'])
        # Changing mode must invalidate a cached analysis, and retain earlier archived card labels.
        self.request(lit+'/analyze','POST',{});self.assertNotIn('architecture_history',Provider.captured['messages'][0]['content'])
        _,raw=self.request('/api/knowledge/export?id='+card['id']);self.assertIn('历史贡献',raw.decode())
        self.request('/api/knowledge/'+card['id'],'PATCH',{'title':'保留历史研究模式'})
        self.assertEqual(next(c for c in json.loads(self.request('/api/knowledge')[1])['cards'] if c['id']==card['id'])['analysis_mode'],'history')
        with patch.object(web,'read_url',return_value=(item['url'],WEB_HTML,'text/html')):status,raw=self.request(path+'/analyze','POST',{})
        self.assertEqual(json.loads(raw)['case']['analysis_mode'],'general');self.assertNotIn('architecture_history',Provider.captured['messages'][0]['content'])

    def test_history_schema_migration_preserves_previous_analysis_labels(self):
        p=self.paper();_,raw=self.request('/api/knowledge','POST',{'title':'旧卡片','content':'旧文本','sources':[{'paper_id':p['id'],'page':1}]});cid=json.loads(raw)['card']['id']
        item=self.web_result();lit=self.literature_result()['results'][0]
        with app.connect() as conn:
            for table in ('knowledge','web_cases','web_literature'):conn.execute('ALTER TABLE '+table+' DROP COLUMN analysis_mode')
        app.init_db();app.init_db()
        with app.connect() as conn:
            for table in ('knowledge','web_cases','web_literature'):self.assertEqual(conn.execute('SELECT analysis_mode FROM '+table).fetchone()[0],'general')
            self.assertEqual(conn.execute('SELECT content FROM knowledge WHERE id=?',(cid,)).fetchone()[0],'旧文本')
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_validation_and_origin(self):
        self.assertEqual(self.request('/api/settings','POST',{'base_url':'https://bad.example/#token'})[0],400)
        self.assertEqual(self.request('/api/settings','POST',{'base_url':'http://bad.example/v1'})[0],400)
        self.assertEqual(self.request('/api/settings','POST',{},headers={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/api/ask','POST',{'paper_ids':[],'question':'hi'})[0],400)
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port);c.request('GET','/api/state',headers={'Host':'evil.example'});self.assertEqual(c.getresponse().status,403);c.close()
    def test_text_markdown_and_standard_category(self):
        raw=('技术规范说明\n\n1 范围\n仅适用于本试验。\n\n2 要求\n应记录试验条件。').encode('utf-8')
        status,result=self.request('/api/papers?filename=guide.txt','POST',raw)
        self.assertEqual(status,201,result);p=json.loads(result)['paper'];self.assertEqual(p['format'],'txt')
        self.assertEqual(p['category'],'其他');self.assertGreater(p['text_chars'],20)
        self.request('/api/papers/'+p['id'],'PATCH',{'category':'规范'})
        _,unit=self.request('/api/papers/'+p['id']+'/page?page=1')
        self.assertIn('文本第1段',json.loads(unit)['label'])
        refs,_=app.retrieve([p['id']],'要求');self.assertIn('文本',refs[0]['locator'])
        status,download=self.request('/api/papers/'+p['id']+'/original');self.assertEqual(download,raw)
        status,result=self.request('/api/papers?filename=notes.md','POST',b'# Notes\n\nA reading note.')
        self.assertEqual(status,201,result);self.assertEqual(json.loads(result)['paper']['format'],'md')

    def test_docx_sections(self):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            z.writestr('word/document.xml',"""<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>1 Scope</w:t></w:r></w:p><w:p><w:r><w:t>This standard applies to tests.</w:t></w:r></w:p><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>2 Requirements</w:t></w:r></w:p><w:p><w:r><w:t>Record all conditions.</w:t></w:r></w:p></w:body></w:document>""")
        status,raw=self.request('/api/papers?filename=standard.docx','POST',buf.getvalue())
        self.assertEqual(status,201,raw);p=json.loads(raw)['paper'];self.assertEqual(p['page_count'],2)
        _,raw=self.request('/api/papers/'+p['id']+'/outline');self.assertIn('Requirements',json.loads(raw)['units'][1]['label'])

    def test_epub_spine_order_and_metadata(self):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            z.writestr('mimetype','application/epub+zip')
            z.writestr('META-INF/container.xml','<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/book.opf"/></rootfiles></container>')
            z.writestr('OEBPS/book.opf',"""<package xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Test Book</dc:title><dc:creator>A Writer</dc:creator></metadata><manifest><item id="two" href="2.xhtml"/><item id="one" href="1.xhtml"/></manifest><spine><itemref idref="one"/><itemref idref="two"/></spine></package>""")
            z.writestr('OEBPS/2.xhtml','<html><body><h1>Chapter Two</h1><p>Second chapter.</p></body></html>')
            z.writestr('OEBPS/1.xhtml','<html><body><h1>Chapter One</h1><p>First chapter.</p><script>IGNORE_ME</script></body></html>')
        status,raw=self.request('/api/papers?filename=book.epub','POST',buf.getvalue())
        self.assertEqual(status,201,raw);p=json.loads(raw)['paper'];self.assertEqual(p['title'],'Test Book');self.assertEqual(p['category'],'图书')
        _,raw=self.request('/api/papers/'+p['id']+'/page?page=1');unit=json.loads(raw)
        self.assertIn('Chapter One',unit['label']);self.assertNotIn('IGNORE_ME',unit['text'])
        self.assertEqual(p['page_count'],2)

    def test_dotenv_precedence_not_code(self):
        root=Path(self.tmp.name)/'config';root.mkdir();(root/'.env').write_text('PAPER_API_KEY="file-secret"\nPAPER_MODEL=$(never-execute)\n')
        with patch.object(app,'USER_ROOT',root),patch.dict(os.environ,{'PAPER_CONFIG_FILE':str(root/'.env')}):
            self.assertEqual(app.dotenv()['PAPER_MODEL'],'$(never-execute)');self.assertEqual(app.config()['key'],'test-only-secret')
            with patch.dict(os.environ,{'PAPER_API_KEY':'','OPENAI_API_KEY':''}):self.assertEqual(app.config()['key'],'file-secret')
        with self.assertRaises(app.AppError):app.validated_base('https://user:secret@host/v1')

if __name__=='__main__':unittest.main()
