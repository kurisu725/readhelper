import {initExtensions} from '/extensions.js';
import { initKnowledge } from '/knowledge.js';
import { initOnlineCases } from '/online_cases.js';
import { initBriefs } from '/briefs.js';
import { initLiterature } from '/literature.js';
import * as pdfjs from '/vendor/pdf.min.mjs';
import { marked, Renderer } from '/vendor/marked.mjs';
pdfjs.GlobalWorkerOptions.workerSrc = '/vendor/pdf.worker.min.mjs';
const $ = (id) => document.getElementById(id);
const paths = {
  book:'M12 7C8 4 5 4 2 5v15c3-1 6-1 10 2 4-3 7-3 10-2V5c-3-1-6-1-10 2Zm0 0v15',
  library:'M4 3v18M8 3v18M12 4v17M16 3l5 17M3 21h19',
  layers:'m12 3 10 5-10 5L2 8Zm-10 9 10 5 10-5M2 16l10 5 10-5',
  note:'M14 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-9M16 3l5 5-10 10H6v-5Z',
  shield:'M12 3 3 7v5c0 5 5 8 9 10 4-2 9-5 9-10V7Zm-4 9 3 3 5-6',
  settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm-2-6h4l1 3 3 1 3-1 2 4-2 2v3l2 2-2 4-3-1-3 1-1 3h-4l-1-3-3-1-3 1-2-4 2-2v-3L1 9l2-4 3 1 3-1Z',
  download:'M12 3v12m-5-5 5 5 5-5M4 15v5h16v-5',
  upload:'M12 16V4m-5 5 5-5 5 5M4 15v5h16v-5',
  search:'M21 21l-5-5M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14',
  plus:'M12 5v14M5 12h14', minus:'M5 12h14',
  sparkles:'m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3Zm7 0v4m-2-2h4',
  chevronLeft:'m15 5-7 7 7 7',chevronRight:'m9 5 7 7-7 7',arrowLeft:'M20 12H4m7-7-7 7 7 7',
  edit:'m15 3 6 6-12 12H3v-6Zm-3 3 6 6', x:'m6 6 12 12M6 18 18 6',
  check:'m4 12 5 5L20 6', send:'m3 3 19 9-19 9 4-9Zm4 9h15', stop:'M6 6h12v12H6Z',
  key:'M15 3a6 6 0 1 0 0 12 6 6 0 0 0 0-12ZM10 13 3 20v2h4v-3h3v-3m7-9h.01',
  info:'M12 8h.01M12 11v6m0-15a10 10 0 1 0 0 20 10 10 0 0 0 0-20',
  sliders:'M4 5h16M4 12h16M4 19h16M8 2v6m8 1v6M9 16v6',
  copy:'M9 8h12v14H9ZM5 17H2V2h13v3', archive:'M3 3h18v5H3Zm2 5v13h14V8m-10 4h6',
  trash:'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7',
  globe:'M2 12h20M12 2c6 5 6 15 0 20-6-5-6-15 0-20Zm0 0a10 10 0 1 0 0 20 10 10 0 0 0 0-20'
};
function icon(name) { return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] || paths.note}"/></svg>`; }
function icons(root=document) { root.querySelectorAll('[data-icon]').forEach(el => { el.innerHTML=icon(el.dataset.icon); }); }
const esc=(s)=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statusLabels={unread:'待读',reading:'阅读中',done:'已读',archived:'已归档'};
const S={papers:[],notes:[],config:{},selected:new Set(),drafts:new Map(),filter:'all',category:'all',view:'library',reader:null,page:1,selection:'',pdf:null,loadingTask:null,zoom:1,textMode:false,renderVersion:0,busy:false,controller:null};
const chatInstances=new Map();
const extensionViews=new Map();
const registerView=(id,title,ui)=>extensionViews.set(id,{title,ui});
let toastTimer,searchTimer,resizeTimer,ocrPollTimer;
S.ocrJob=null;
function toast(message,error=false) { $('toast').textContent=message;$('toast').classList.toggle('error',error);$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,error?7000:3800); }
async function api(path, options={}) {
 const response=await fetch(path,{...options,headers:{'X-Requested-With':'ResearchDesk',...(options.body && !(options.body instanceof File)?{'Content-Type':'application/json'}:{}),...options.headers}});
 const value=await response.json();if(!response.ok)throw new Error(value.error||'操作未完成，请重试。');return value;
}
const post=(path,body={})=>api(path,{method:'POST',body:JSON.stringify(body)});
const patch=(path,body)=>api(path,{method:'PATCH',body:JSON.stringify(body)});
function units(p){return p.page_count+(p.format==='pdf'?' 页':' 段');}
function location(p,page,label=''){return label||(p?.format==='pdf'?'PDF第'+page+'页':'文本第'+page+'段');}
function paperById(id){return S.papers.find(p=>p.id===id);}
function empty(title,text,button=''){return `<div class="empty-state"><i>${icon('book')}</i><h3>${esc(title)}</h3><p>${esc(text)}</p>${button}</div>`;}
async function refresh(){const data=await api('/api/state');Object.assign(S,data);renderCounts();renderLibrary();renderAllNotes();renderSettings();}
function renderCounts(){$('knowledgeCount').textContent=S.knowledge_count||0;const active=S.papers.filter(p=>p.status!=='archived');$('paperCount').textContent=active.length;$('totalLabel').textContent=active.length;$('noteCount').textContent=S.notes.length;for(const status of ['unread','reading','done','archived'])$(status+'Count').textContent=S.papers.filter(p=>p.status===status).length;$('configDot').className='dot '+(S.config.has_key&&S.config.model?'green':'amber');}
function showView(view){
 if(extensionViews.has(view)){extensionViews.get(view).ui.show();}

 S.view=view;document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id==='view-'+view));
 document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
 $('breadcrumb').textContent={library:'资料库',reader:'资料阅读',compare:'跨文献分析',notes:'阅读笔记',settings:'AI 设置',knowledge:'知识与案例',webcases:'网络案例',briefs:'任务书解读',literature:'网络文献',search:'搜索结果',extensions:'插件与更新'}[view]||extensionViews.get(view)?.title||view;
 if(view==='extensions')extensionsUI.show();
 if(view==='briefs')briefUI.show();
 if(view==='literature')literatureUI.show();
 if(view==='webcases')onlineUI.show();if(view==='knowledge')knowledgeUI.show();if(view==='library')renderLibrary();if(view==='compare'){renderComparePicker();mountChat($('compareChat'),[...S.selected]);}if(view==='notes')renderAllNotes();if(view==='settings')renderSettings();
 if(view!=='reader')window.scrollTo(0,0);
}
function renderLibrary(){
 const active=S.papers.filter(p=>p.status!=='archived');$('welcomePanel').hidden=active.length>0;$('workflowGrid').hidden=active.length>0;
 let papers=S.papers.filter(p=>S.filter==='all'?p.status!=='archived':p.status===S.filter);
 if(S.category!=='all')papers=papers.filter(p=>p.category===S.category);
 const sort=$('sortSelect').value;if(sort==='title')papers.sort((a,b)=>a.title.localeCompare(b.title,'zh'));else if(sort==='year')papers.sort((a,b)=>b.year.localeCompare(a.year));
 $('libraryTabs').querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.filter===S.filter));
 $('libraryList').innerHTML=papers.map(p=>`<article class="paper-row"><input type="checkbox" data-select="${p.id}" aria-label="选择 ${esc(p.title)}" ${S.selected.has(p.id)?'checked':''}><div class="pdf-icon" aria-hidden="true">${esc(p.format.toUpperCase())}</div><div class="paper-info" role="button" tabindex="0" data-open="${p.id}"><h3>${esc(p.title)}</h3><p>${esc(p.authors||'作者待核对')} · ${p.year?esc(p.year)+' · ':''}${units(p)} · ${esc(p.category)}${p.format==='pdf'&&p.text_pages<p.page_count?' · 文字 '+(p.text_pages||0)+'/'+p.page_count+' 页':''}</p>${p.tags?'<div class="paper-tags">'+p.tags.split(/[,，]/).filter(Boolean).slice(0,5).map(t=>`<span class="tag">${esc(t)}</span>`).join('')+'</div>':''}</div><span class="badge ${p.status}">${statusLabels[p.status]}</span><button class="button ghost small row-open" data-open="${p.id}">阅读 ${icon('chevronRight')}</button></article>`).join('')|| (S.filter!=='all'?'<div class="empty-list">这里还没有文献。导入 PDF，或在阅读页面更新状态。</div>':'');
 $('dropTitle').textContent=active.length?'继续添加文献、图书或规范':'拖入文献、图书或规范，开启阅读';updateSelectedButton();
}
function updateSelectedButton(){const count=S.selected.size;$('compareSelected').disabled=count===0;$('compareSelected').querySelector('span').textContent=count?`分析所选 (${count})`:'分析所选';}
function selectPaper(id,checked){if(S.busy){toast('请先等待当前回答完成，或停止生成。');return false;}if(checked&&S.selected.size>=6){toast('一次最多选择 6 份资料。',true);return false;}if(checked)S.selected.add(id);else S.selected.delete(id);updateSelectedButton();return true;}
async function uploadFiles(files){
 if(S.importing)return;const items=[...files];if(!items.length)return;S.importing=true;document.body.classList.add('importing');let added=0,duplicates=0,failed=[];
 try{for(let i=0;i<items.length;i++){const file=items[i];$('dropTitle').textContent=`正在导入 ${i+1}/${items.length}：${file.name}`;if(file.size>100*1024*1024){failed.push(file.name+' 超过 100MB');continue;}try{const result=await api('/api/papers?filename='+encodeURIComponent(file.name),{method:'POST',body:file,headers:{'Content-Type':'application/pdf'}});if(result.duplicate)duplicates++;else added++;}catch(e){failed.push(file.name+'：'+e.message);}}await refresh();toast(`已导入 ${added} 篇${duplicates?'，跳过 '+duplicates+' 篇重复文件':''}${failed.length?'；'+failed.join('；'):''}`,failed.length>0);}finally{S.importing=false;document.body.classList.remove('importing');$('fileInput').value='';renderLibrary();}}
function renderComparePicker(){
 const papers=S.papers.filter(p=>p.status!=='archived');$('comparePapers').innerHTML=papers.length?papers.map(p=>`<label class="compare-option"><input type="checkbox" data-compare-select="${p.id}" ${S.selected.has(p.id)?'checked':''}><span><strong>${esc(p.title)}</strong><small>${units(p)} · ${esc(p.year||'年份待核对')}${p.format==='pdf'&&p.text_pages<p.page_count?' · 部分页待识别':''}</small></span></label>`).join(''):empty('先添加资料','导入两份或更多资料，开始连接它们的发现。');
}
function safeMarkdown(text,refs=[]){
 const renderer=new Renderer();renderer.html=({text})=>esc(text);
 const template=document.createElement('template');template.innerHTML=marked.parse(text,{gfm:true,breaks:true,renderer});
 const allowed=new Set('P BR H1 H2 H3 H4 H5 H6 UL OL LI STRONG EM DEL CODE PRE BLOCKQUOTE TABLE THEAD TBODY TR TH TD HR A'.split(' '));
 for(const el of [...template.content.querySelectorAll('*')]){if(!allowed.has(el.tagName)){el.replaceWith(document.createTextNode(el.textContent));continue;}const href=el.tagName==='A'?el.getAttribute('href'):null;for(const a of [...el.attributes])el.removeAttribute(a.name);if(href&&/^https?:\/\//i.test(href)){el.setAttribute('href',href);el.setAttribute('target','_blank');el.setAttribute('rel','noopener noreferrer');}}
 const walker=document.createTreeWalker(template.content,NodeFilter.SHOW_TEXT);const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
 for(const node of nodes){if(node.parentElement?.closest('pre,code,a')||!(/\[\d+\]/.test(node.textContent)))continue;const fragment=document.createDocumentFragment();let last=0;for(const match of node.textContent.matchAll(/\[(\d+)\]/g)){fragment.append(document.createTextNode(node.textContent.slice(last,match.index)));const ref=refs.find(r=>r.number===Number(match[1]));if(ref){const b=document.createElement(ref.url?'a':'button');if(ref.url&&/^https?:\/\//i.test(ref.url)){b.href=ref.url;b.target='_blank';b.rel='noopener noreferrer';}b.className='citation';b.dataset.source=ref.number;b.textContent=match[0];b.title=`${ref.title} · ${ref.locator||location(paperById(ref.paper_id),ref.page)}`;fragment.append(b);}else fragment.append(document.createTextNode(match[0]));last=match.index+match[0].length;}fragment.append(document.createTextNode(node.textContent.slice(last)));node.replaceWith(fragment);}
 return template.content;
}
const singlePrompts=[['快速精读','请基于摘录，从研究问题、主要贡献、方法、结果、局限五个方面梳理这篇论文，并标注依据。'],['研究方法','详细解释这篇研究的方法、数据来源、实验设计和评价指标，区分摘录已提供和未提供的信息。'],['批判性分析','请批判性分析当前摘录中的研究：主要假设、证据强度、潜在偏差、局限，以及我需要继续核对的关键问题。'],['翻译选段','请将我选中的原文准确翻译成中文，保留关键英文术语，并解释其中难理解的概念。若未选择文字，请提示我先选段。']];
const bookPrompts=[['章节梳理','基于摘录梳理本书的主题、核心观点和论证结构，标明章节或文本位置，说明哪些部分尚未覆盖。'],['概念解释','解释当前资料中的核心概念、概念之间的联系，并给出摘录中的依据。'],['论证分析','分析作者的主要论点、论据和隐含前提，区分原文主张与自己的推断，并提出值得继续思考的问题。'],singlePrompts[3]];
const standardPrompts=[['条款解读','基于摘录逐项解释规范要求、适用范围、术语与例外。区分强制性要求、推荐做法和你的解释，引用条款原文位置，不推断规范目前是否有效。'],['要求清单','把摘录中的要求整理为检查清单，包括要求、适用条件、验证材料和原文依据。没有提供的信息请明确标记。'],['适用与边界','分析当前摘录中规范的适用条件、边界、引用关系和需要进一步核对的版本信息，不补造未提供的条款。'],singlePrompts[3]];
function readingPrompts(ids){const category=paperById(ids[0])?.category;return [...(category==='图书'?bookPrompts:category==='规范'?standardPrompts:singlePrompts),valuePrompt];}
const valuePrompt=['创新与借鉴','请基于当前原文摘录分别提取：1. 创新点，区分原文明确提出与分析归纳，不断言首创；2. 可改进方向，区分原文局限与建议，说明依据、适用条件和待验证点；3. 可学习参考之处，说明可迁移的方法、场景与边界。各项引用原文，缺失信息明确指出。'];
const comparePrompts=[['对比研究','对比这些论文的研究问题、方法、数据和主要结果，用表格呈现，逐项引用来源。'],['共识与分歧','这些论文在哪些发现上有共识、在哪些方面存在分歧？请区分实验条件差异与实质结论分歧，并引用依据。'],['研究空白','根据这些摘录，提出值得进一步验证的研究空白和后续问题。将论文明确指出的局限与你的推断分开。'],['写综述提纲','基于这些文献，拟定一份中文文献综述提纲，按主题组织，并在各主题下标明支持的文献依据。']];
async function mountChat(container,ids){
 const key=ids.slice().sort().join(',');const instance={container,ids:[...ids],key,messages:[],generation:Symbol()};chatInstances.set(container.id,instance);
 const multi=container.id==='compareChat';const prompts=multi?[...comparePrompts,valuePrompt]:readingPrompts(ids);
 container.innerHTML=(multi?`<div class="chat-header">${icon('sparkles')} 跨文献研究助手<span class="dot green"></span><span class="muted">${ids.length} 篇已选</span></div>`:'')+`<div class="chat-body"><div class="chat-intro"><div class="chat-welcome"><div class="ai-symbol">${icon('sparkles')}</div><h3>${multi?'让不同的发现，彼此对话':'读懂资料，从一个问题开始'}</h3><p>${multi?'选择左侧文献，比较研究方法、梳理结论，探索它们之间的联系。':'围绕文献观点、图书章节、规范条款或一段难懂的原文提问。回答附带摘录出处，方便随时核对。'}</p></div><div class="prompt-grid">${prompts.map(([label,q],i)=>`<button class="prompt-button" data-prompt="${i}">${icon(i===0?'book':i===1?'sliders':i===2?'search':'note')}${label}</button>`).join('')}</div></div><div class="chat-messages"></div></div><div class="selection-banner quote-preview" hidden></div><form class="chat-compose">${!S.config.has_key||!S.config.model?'<div class="no-key-inline">先连接你的 AI 服务，开始阅读问答。<button type="button" data-goto-settings>前往设置 →</button></div>':''}<div class="compose-box"><textarea aria-label="向文献提问" rows="2" placeholder="${multi?'向所选文献提问…':'这份资料的核心观点或要求是什么？'}"></textarea><div class="compose-toolbar"><small>${multi?'依据所选文献的相关摘录':'依据当前资料的相关摘录'} · ⌘ Enter 发送</small><button class="send-button" type="submit" aria-label="发送问题">${icon('send')}</button></div></div><p class="compose-caption">AI 分析供阅读参考，请点击引用核对原文。PDF 使用页序，其他文件使用章节或文本位置。</p></form>`;
 container.querySelector('[data-goto-settings]')?.addEventListener('click',()=>showView('settings'));
 container.querySelectorAll('[data-prompt]').forEach(b=>b.addEventListener('click',()=>{container.querySelector('textarea').value=prompts[Number(b.dataset.prompt)][1];container.querySelector('textarea').focus();}));
 container.querySelector('form').addEventListener('submit',e=>{e.preventDefault();if(S.busy){S.controller?.abort();return;}ask(instance);});
 container.querySelector('textarea').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)){e.preventDefault();if(!S.busy)ask(instance);}});
 updateSelection();
 if(ids.length){try{const result=await api('/api/messages?ids='+encodeURIComponent(key));if(chatInstances.get(container.id)!==instance)return;instance.messages=result.messages;renderChatMessages(instance);}catch(e){toast(e.message,true);}}
}
function renderChatMessages(instance){const area=instance.container.querySelector('.chat-messages');area.replaceChildren();instance.container.querySelector('.chat-intro').hidden=instance.messages.length>0;for(const m of instance.messages)appendMessage(instance,m);scrollChat(instance);}
function appendMessage(instance,message){
 const el=document.createElement('article');el.className='message '+message.role;const assistant=message.role==='assistant';el.innerHTML=`<div class="message-label"><span>${icon(assistant?'sparkles':'note')}${assistant?'研读助手':'你'}</span>${assistant?'<span>基于文献摘录</span>':''}</div><div class="message-content"></div>`;el.querySelector('.message-content').append(safeMarkdown(message.content,message.refs||[]));
 if(assistant&&message.refs?.length){const details=document.createElement('details');details.className='sources-panel';details.innerHTML=`<summary>本次参考摘录 · ${message.refs.length} 条 · 点击核对</summary>`+message.refs.map(r=>`<button class="source-button" data-source="${r.number}"><strong>[${r.number}] ${esc(r.title)} · ${esc(r.locator||location(paperById(r.paper_id),r.page))}</strong><small>${esc(r.text.slice(0,150))}</small></button>`).join('');el.append(details);}
 if(assistant){const actions=document.createElement('div');actions.className='message-actions';actions.innerHTML=`<button type="button" data-copy>${icon('copy')}复制</button><button type="button" data-save>${icon('note')}存为笔记</button><button type="button" data-save-card>${icon('book')}存为卡片</button>`;actions.querySelector('[data-copy]').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(message.content);toast('已复制回答。');}catch{toast('复制失败，请手动选择回答文本。',true);}});actions.querySelector('[data-save]').addEventListener('click',()=>saveAnswerNote(instance,message));actions.querySelector('[data-save-card]').addEventListener('click',()=>knowledgeUI.fromAnswer(message,instance.ids));el.append(actions);}
 el.addEventListener('click',e=>{const b=e.target.closest('[data-source]');if(!b)return;const ref=(message.refs||[]).find(r=>r.number===Number(b.dataset.source));if(ref)openPaper(ref.paper_id,ref.page);});instance.container.querySelector('.chat-messages').append(el);return el;
}
function scrollChat(instance){const area=instance.container.querySelector('.chat-body');area.scrollTop=area.scrollHeight;}
async function ask(instance){
 const textarea=instance.container.querySelector('textarea'),question=textarea.value.trim();if(!question)return;
 if(!instance.ids.length){toast('先选择至少一篇文献。',true);return;}if(!S.config.has_key||!S.config.model){toast('请先配置密钥和模型名称。',true);showView('settings');return;}if(S.busy)return;
 S.busy=true;S.controller=new AbortController();textarea.value='';instance.container.querySelector('.chat-intro').hidden=true;
 const send=instance.container.querySelector('.send-button');send.innerHTML=icon('stop');send.setAttribute('aria-label','停止生成');
 const user={role:'user',content:question,refs:[]},answer={role:'assistant',content:'',refs:[]};const userEl=appendMessage(instance,user),answerEl=appendMessage(instance,answer);answerEl.classList.add('streaming');answerEl.querySelector('.message-actions')?.remove();const status=document.createElement('div');status.className='stream-status';status.innerHTML='<span class="spinner"></span>正在检索原文并等待模型响应…';answerEl.prepend(status);scrollChat(instance);
 let completed=false,lastPaint=0;
 try{
  const response=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'ResearchDesk'},signal:S.controller.signal,body:JSON.stringify({paper_ids:instance.ids,question,selection:instance.container.id==='readerChat'?S.selection:''})});
  if(!response.ok){const value=await response.json();throw new Error(value.error||'请求未完成。');}
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
  const receive=(event)=>{if(event.type==='sources'){answer.refs=event.refs;status.innerHTML='<span class="spinner"></span>已找到 '+answer.refs.length+' 条原文摘录，正在生成…';}else if(event.type==='delta'){answer.content+=event.text;if(Date.now()-lastPaint>90){answerEl.querySelector('.message-content').replaceChildren(safeMarkdown(answer.content,answer.refs));lastPaint=Date.now();scrollChat(instance);}}else if(event.type==='error')throw new Error(event.error);else if(event.type==='done'){completed=true;answer.invalid=event.invalid_citations;answer.truncated=event.truncated;}};
  while(true){const {value,done}=await reader.read();if(done){buffer+=decoder.decode();break;}buffer+=decoder.decode(value,{stream:true});const lines=buffer.split('\n');buffer=lines.pop();for(const line of lines)if(line.trim())receive(JSON.parse(line));}if(buffer.trim())receive(JSON.parse(buffer));if(!completed)throw new Error('连接提前结束，回答未保存。');
  instance.messages.push(user,answer);answerEl.remove();const final=appendMessage(instance,answer);if(answer.invalid?.length||!(/\[\d+\]/.test(answer.content))||answer.truncated){const warn=document.createElement('div');warn.className='chat-warning';warn.textContent=answer.truncated?'回答达到服务输出上限，可能不完整。可继续追问具体部分。':answer.invalid?.length?'模型使用了无法对应的引用编号，请核对下方原文。':'此回答没有有效的行内引用，请对照下方摘录核对。';final.append(warn);}scrollChat(instance);
 }catch(e){answerEl.classList.remove('streaming');status.remove();const error=document.createElement('div');error.className='error-message';error.textContent=e.name==='AbortError'?'已停止。本次显示的内容不计入已保存记录，请重试或缩小问题范围。':e.message;answerEl.append(error);answerEl.querySelector('.message-content').replaceChildren(safeMarkdown(answer.content,answer.refs));if(!answer.content)answerEl.querySelector('.message-content').remove();textarea.value=question;scrollChat(instance);
 }finally{S.busy=false;S.controller=null;send.innerHTML=icon('send');send.setAttribute('aria-label','发送问题');}
}
async function saveAnswerNote(instance,message){try{
 // A running pre-update service may still serve this newly installed frontend until restart.
 let content=message.content;const refs=message.refs||[];
 if(!S.note_refs_enabled&&refs.length)content+='\n\n参考出处：\n'+refs.map(r=>`[${r.number}] ${r.title} · ${r.locator||location(paperById(r.paper_id),r.page)}`).join('\n');
 await post('/api/notes',{paper_id:instance.ids.length===1?instance.ids[0]:null,page:refs[0]?.page||1,content,refs});await refresh();if(S.reader)renderReaderNotes();toast(S.note_refs_enabled?'回答与可跳转出处已保存到阅读笔记。':'回答与出处已保存，重新打开更新后的程序即可点击出处。');
 }catch(e){toast(e.message,true);}}
async function openPaper(id,page=null){
 const paper=paperById(id);if(!paper){toast('找不到文献。',true);return;}
 if(S.busy&&S.reader!==id){toast('请先等待回答完成，或停止生成后切换文献。');return;}
 const changed=S.reader!==id;if(changed){if(S.reader)S.drafts.set(S.reader,$('noteContent').value);$('noteContent').value=S.drafts.get(id)||'';}S.reader=id;S.page=Math.max(1,Math.min(paper.page_count,page||paper.current_page||1));S.selection='';S.zoom=1;S.textMode=paper.format!=='pdf';$('pdfMode').hidden=paper.format!=='pdf';$('pdfMode').classList.toggle('active',!S.textMode);$('textMode').classList.toggle('active',S.textMode);showView('reader');
 $('readerSource').hidden=!paper.origin_url;$('readerSource').href=paper.origin_url||'#';
 $('readerTitle').textContent=paper.title;$('readerMeta').textContent=`${paper.authors||'作者待核对'}${paper.year?' · '+paper.year:''} · ${units(paper)}`;$('readerStatus').value=paper.status;$('pageTotal').textContent='/ '+paper.page_count;$('pageInput').max=paper.page_count;$('pageInput').setAttribute('aria-label',paper.format==='pdf'?'页码':'文本位置');$('openOriginal').href='/api/papers/'+id+'/pdf#page='+S.page;$('extractHint').textContent=paper.text_chars<40?'未检测到文字层：可阅读原文，AI 问答需先 OCR':'选中原文后，可引用到提问或笔记';
 clearTimeout(ocrPollTimer);S.ocrJob=null;renderOCR();if(paper.format==='pdf')pollOCR(id);
 if(changed||!chatInstances.get('readerChat'))await mountChat($('readerChat'),[id]);renderReaderNotes();showReaderTab('chat');updateSelection();
 try{const outline=await api('/api/papers/'+id+'/outline');$('outlineSelect').innerHTML=outline.units.map(u=>`<option value="${u.page}">${esc(location(paper,u.page,u.label))}</option>`).join('');}catch{}
 if(paper.format==='pdf'&&(changed||!S.pdf)){if(S.loadingTask){try{await S.loadingTask.destroy();}catch{}}S.pdf=null;$('pdfPage').hidden=true;$('pdfLoading').hidden=false;try{S.loadingTask=pdfjs.getDocument({url:'/api/papers/'+id+'/pdf',cMapUrl:'/vendor/cmaps/',cMapPacked:true,standardFontDataUrl:'/vendor/standard_fonts/',wasmUrl:'/vendor/wasm/',isEvalSupported:false});const pdf=await S.loadingTask.promise;if(S.reader!==id)return;S.pdf=pdf;}catch(e){$('pdfLoading').textContent='原文渲染失败，可切换「文字」或打开 PDF。';toast('无法渲染此 PDF，可使用文字视图。',true);}}
 if(paper.format!=='pdf'){$('openOriginal').href='/api/papers/'+id+'/original';$('openOriginal').textContent='下载原文件 ↗';}else $('openOriginal').textContent='打开 PDF ↗';
 await renderPage();
 if(paper.status==='unread'){try{Object.assign(paper,await patch('/api/papers/'+id,{status:'reading'}));$('readerStatus').value='reading';renderCounts();}catch(e){toast(e.message,true);}}
}
async function renderPage(){
 const version=++S.renderVersion,id=S.reader,pageNo=S.page;if(!id)return;const paper=paperById(id);$('pageInput').value=pageNo;$('prevPage').disabled=pageNo<=1;$('nextPage').disabled=pageNo>=paper.page_count;$('notePageLabel').textContent='关联'+location(paper,pageNo);$('openOriginal').href='/api/papers/'+id+(paper.format==='pdf'?'/pdf#page='+pageNo:'/original');$('outlineSelect').value=String(pageNo);$('pdfLoading').hidden=false;$('pdfLoading').textContent='正在载入原文…';
 $('pdfPage').hidden=S.textMode;$('plainText').hidden=!S.textMode;$('pdfViewport').scrollTop=0;
 try{const data=await api('/api/papers/'+id+'/page?page='+pageNo);if(version!==S.renderVersion)return;$('notePageLabel').textContent='关联'+location(paper,pageNo,data.label);$('plainText').style.fontSize=(paper.format==='pdf'?12:15)*S.zoom+'px';$('plainText').textContent=data.text||'本页没有可提取的文字。扫描页请点击上方「识别本页」或「识别全书」，再在此选择文字。';$('extractHint').textContent=data.ocr_done?'本页文字来自 OCR，请对照原图核对；在「文字」视图可选段提问':'选中原文后，可引用到提问或笔记';
 if(!S.textMode&&S.pdf){const page=await S.pdf.getPage(pageNo);if(version!==S.renderVersion)return;const base=page.getViewport({scale:1}),width=Math.max(180,$('pdfViewport').clientWidth-46),scale=(width/base.width)*S.zoom,viewport=page.getViewport({scale});const canvas=document.createElement('canvas');canvas.id='pdfCanvas';const ratio=Math.min(window.devicePixelRatio||1,2);canvas.width=Math.floor(viewport.width*ratio);canvas.height=Math.floor(viewport.height*ratio);canvas.style.width=viewport.width+'px';canvas.style.height=viewport.height+'px';const layer=document.createElement('div');layer.id='textLayer';layer.className='textLayer';const holder=$('pdfPage');holder.style.width=viewport.width+'px';holder.style.height=viewport.height+'px';holder.style.setProperty('--scale-factor',scale);holder.style.setProperty('--user-unit',viewport.userUnit||1);holder.replaceChildren(canvas,layer);holder.hidden=false;const task=page.render({canvasContext:canvas.getContext('2d'),canvas,viewport,transform:ratio!==1?[ratio,0,0,ratio,0,0]:null});await task.promise;if(version!==S.renderVersion)return;const textLayer=new pdfjs.TextLayer({textContentSource:page.streamTextContent(),container:layer,viewport});await textLayer.render();}
 if(version===S.renderVersion){$('pdfLoading').hidden=true;$('zoomLabel').textContent=S.zoom===1?(paper.format==='pdf'?'自适应':'100%'):Math.round(S.zoom*100)+'%';}
 await patch('/api/papers/'+id,{current_page:pageNo});paper.current_page=pageNo;
 }catch(e){if(version===S.renderVersion){$('pdfLoading').textContent='页面加载失败，可切换文字或打开原始 PDF。';console.warn('PDF page could not render:',e.name);}}
}
function renderOCR(){
 const p=paperById(S.reader),j=S.ocrJob,running=j?.status==='running';$('ocrPanel').hidden=!p||p.format!=='pdf';if(!p||p.format!=='pdf')return;
 $('ocrDescription').textContent=`${p.text_pages||0}/${p.page_count} 页有可用文字 · 中文 / 英文 · ${S.config.ocr_engine||'本机处理'}`;
 $('ocrPage').disabled=running||!S.config.ocr_available;$('ocrAll').disabled=running||!S.config.ocr_available;$('ocrStop').hidden=!running;$('ocrProgress').hidden=!running;
 $('ocrProgress').max=Math.max(1,j?.total||1);$('ocrProgress').value=j?.completed||0;
 let text=S.config.ocr_available?'全书识别会跳过有文字和已处理的页；识别结果自动保存。':'本机 OCR 组件不可用。Windows 源码版请安装 requirements.txt 的依赖；安装版请更新完整安装包。';
 if(running)text=`正在识别 PDF 第 ${j.current_page} 页 · 已处理 ${j.completed}/${j.total} 页。可继续阅读。`;
 else if(j?.status==='done')text=j.total?`已完成 ${j.completed} 页，${j.recognized} 页识别到文字${j.failed?'，'+j.failed+' 页失败，可用「识别本页」重试':''}。在「文字」视图可选段提问。`:'没有待识别页。若某页文字不正确，可切到该页点击「识别本页」重新识别。';
 else if(j?.status==='cancelled')text=`已停止，已处理 ${j.completed}/${j.total} 页。再次识别全书可继续。`;
 else if(j?.status==='error')text=j.error;
 $('ocrStatus').textContent=text;$('ocrStatus').classList.toggle('ocr-error',j?.status==='error');
}
async function pollOCR(id){
 clearTimeout(ocrPollTimer);if(S.reader!==id)return;
 try{const {job,paper}=await api('/api/papers/'+id+'/ocr');if(S.reader!==id)return;const previous=S.ocrJob;S.ocrJob=job;Object.assign(paperById(id),paper);renderOCR();
 if(job&&(!previous||job.revision!==previous.revision)&&job.completed){const current=S.page,data=await api('/api/papers/'+id+'/page?page='+current);if(S.reader===id&&S.page===current){$('plainText').textContent=data.text||'此页暂未识别到文字，请核对原图。';if(data.ocr_done)$('extractHint').textContent='本页文字来自 OCR，请对照原图核对；在「文字」视图可选段提问';}}
 if(job?.status==='running')ocrPollTimer=setTimeout(()=>pollOCR(id),1200);
 }catch(e){if(S.reader===id){$('ocrStatus').textContent='进度获取失败，正在重试…';ocrPollTimer=setTimeout(()=>pollOCR(id),3000);}}
}
async function startOCR(scope){const id=S.reader;if(!id)return;try{$('ocrPage').disabled=true;$('ocrAll').disabled=true;const result=await post('/api/papers/'+id+'/ocr',{scope,page:S.page});if(S.reader===id){S.ocrJob=result.job;renderOCR();await pollOCR(id);}}catch(e){toast(e.message,true);renderOCR();}}
$('ocrPage').onclick=()=>startOCR('page');$('ocrAll').onclick=()=>startOCR('missing');$('ocrStop').onclick=async()=>{try{await api('/api/papers/'+S.reader+'/ocr',{method:'DELETE'});await pollOCR(S.reader);}catch(e){toast(e.message,true);}};
function changePage(page){const paper=paperById(S.reader);if(!paper)return;S.page=Math.max(1,Math.min(paper.page_count,Math.round(Number(page)||1)));S.selection='';updateSelection();renderPage();}
function showReaderTab(tab){$('readerChat').hidden=tab!=='chat';$('readerNotes').hidden=tab!=='notes';$('chatTab').classList.toggle('active',tab==='chat');$('notesTab').classList.toggle('active',tab==='notes');}
function updateSelection(){const preview=$('readerChat').querySelector('.selection-banner');if(preview){preview.hidden=!S.selection;preview.innerHTML='<button class="icon-button" type="button" aria-label="取消引用">'+icon('x')+'</button>'+esc(S.selection.slice(0,450))+(S.selection.length>450?'…':'');preview.querySelector('button').onclick=()=>{S.selection='';updateSelection();};}$('noteQuote').hidden=!S.selection;$('noteQuote').textContent=S.selection;}
function noteMarkup(note){const date=new Date(note.created_at).toLocaleDateString('zh-CN');const refs=note.refs||[];return `<article class="note-card"><div class="note-heading"><button ${note.paper_id?`data-open="${note.paper_id}" data-page="${note.page||1}"`:''}>${esc(note.title||'综合分析笔记')}${note.page?' · '+esc(location(paperById(note.paper_id),note.page,note.source_label)):''}</button><button class="icon-button" data-delete-note="${note.id}" title="删除笔记" aria-label="删除笔记">${icon('trash')}</button></div><div class="note-date">${date}</div>${note.quote?`<blockquote>${esc(note.quote)}</blockquote>`:''}<div class="note-content"></div>${refs.length?`<div class="note-sources"><p>参考出处 <span>点击回到原文</span></p>${refs.map(r=>`<button type="button" class="note-source" data-source="${r.number}" title="跳转到 ${esc(r.title)} · ${esc(r.locator)}"><span class="note-source-number">[${r.number}]</span><span><strong>${esc(r.title)}</strong><small>${esc(r.locator)}</small></span><span aria-hidden="true">↗</span></button>`).join('')}</div>`:''}</article>`;}
function formatNotes(root,notes){root.querySelectorAll('.note-card').forEach((card,i)=>{const note=notes[i],refs=note.refs||[],el=card.querySelector('.note-content');el.classList.add('message-content');el.replaceChildren(safeMarkdown(note.display_content??note.content,refs));card.addEventListener('click',async e=>{const source=e.target.closest('[data-source]');if(!source)return;const ref=refs.find(r=>r.number===Number(source.dataset.source));if(!ref)return;await openPaper(ref.paper_id,ref.page);if(S.reader===ref.paper_id&&S.page===ref.page)showReaderTab('notes');});});}
function renderAllNotes(){$('allNotes').innerHTML=S.notes.length?S.notes.map(noteMarkup).join(''):empty('把思考留下来','在阅读页面记录笔记，或将有价值的 AI 回答连同出处一起保存。');formatNotes($('allNotes'),S.notes);}
function renderReaderNotes(){const notes=S.notes.filter(n=>n.paper_id===S.reader||n.refs?.some(r=>r.paper_id===S.reader));$('readerNoteCount').textContent=notes.length;$('paperNoteList').innerHTML=notes.length?notes.map(noteMarkup).join(''):empty('留下一点自己的想法','选中原文可加入引文，再记录你的理解或疑问。');formatNotes($('paperNoteList'),notes);$('notePageLabel').textContent='关联'+location(paperById(S.reader),S.page);}
function renderSettings(){const c=S.config;$('configFilePath').textContent=c.config_file||'';$('baseUrl').value=c.base_url||'';$('modelName').value=c.model||'';$('baseUrl').readOnly=c.base_locked;$('modelName').readOnly=c.model_locked;$('baseHint').textContent=c.base_locked?'地址由环境变量或 .env 指定；修改该配置文件即可生效。':'使用兼容 OpenAI Chat Completions 的接口。';$('modelHint').textContent=c.model_locked?'模型由环境变量或 .env 指定。':'配置密钥后可获取模型列表，也可以直接填写。';$('keyBadge').textContent=c.has_key?'密钥已配置':'待配置密钥';$('keyBadge').className='badge '+(c.has_key?'green':'amber');$('keyStatus').className='config-status '+(c.has_key?'configured':'');$('keyStatus').textContent=c.has_key?'✓ 已从'+c.key_source+'读取密钥，内容不会返回到页面。':'尚未读取到密钥。请在右侧任选一种方式配置，再获取模型。';}
async function saveSettings(){const config=await post('/api/settings',{base_url:$('baseUrl').value.trim(),model:$('modelName').value.trim()});S.config=config;renderCounts();renderSettings();return config;}
async function search(term){term=term.trim();if(!term){showView('library');return;}showView('search');$('searchSummary').textContent='正在搜索…';try{const result=await api('/api/search?q='+encodeURIComponent(term));if($('globalSearch').value.trim()!==term)return;const meta=S.papers.filter(p=>p.status!=='archived'&&(p.title+' '+p.authors+' '+p.tags).toLowerCase().includes(term.toLowerCase()));$('searchSummary').textContent=`“${term}” · ${meta.length} 篇标题/作者匹配，${result.results.length} 条全文匹配（最多显示 60 条）`;
 const highlight=(text)=>{const lower=text.toLowerCase(),needle=term.toLowerCase();let pos=0,out='',index;while((index=lower.indexOf(needle,pos))!==-1){out+=esc(text.slice(pos,index))+'<mark>'+esc(text.slice(index,index+term.length))+'</mark>';pos=index+term.length;}return out+esc(text.slice(pos));};
 $('searchResults').innerHTML=(meta.length?'<div class="search-group"><h3>文献信息</h3>'+meta.map(p=>`<button class="search-hit" data-open="${p.id}"><strong>${highlight(p.title)}</strong><span>${esc(p.authors||'作者待核对')} · ${units(p)}</span></button>`).join('')+'</div>':'')+(result.results.length?'<div class="search-group"><h3>全文摘录</h3>'+result.results.map(r=>`<button class="search-hit" data-open="${r.paper_id}" data-page="${r.page}"><strong>${esc(r.title)}</strong><span>${esc(r.locator||location(paperById(r.paper_id),r.page))}</span><p>…${highlight(r.snippet)}…</p></button>`).join('')+'</div>':'')||empty('没有找到相关内容','试试英文术语、作者姓名或更短的关键词。扫描件需先 OCR 才能全文搜索。');}catch(e){toast(e.message,true);}}

const knowledgeUI=initKnowledge({S,api,post,patch,esc,icon,icons,safeMarkdown,toast,openPaper,showView});
const onlineUI=initOnlineCases({S,api,post,esc,icon,safeMarkdown,toast,refresh,showView,openCard:id=>knowledgeUI.openCard(id),openBrief:id=>briefUI.open(id)});
const literatureUI=initLiterature({S,api,post,esc,icon,safeMarkdown,toast,refresh,showView,openPaper,openCard:id=>knowledgeUI.openCard(id)});
const briefUI=initBriefs({S,api,post,esc,icon,safeMarkdown,toast,refresh,openPaper,showView,searchCases:(...args)=>onlineUI.fromBrief(...args),searchLiterature:(...args)=>literatureUI.fromBrief(...args),openLiterature:id=>literatureUI.open(id)});
const extensionsUI=initExtensions({S,api,post,patch,esc,icon,safeMarkdown,toast,refresh,showView,openPaper,registerView});
$('readerKnowledge').onclick=()=>knowledgeUI.fromReader();
$('readerLiterature').onclick=()=>literatureUI.fromReader(paperById(S.reader));
icons();
document.addEventListener('click',async e=>{
 const nav=e.target.closest('[data-view]');if(nav){showView(nav.dataset.view);return;}
 const open=e.target.closest('[data-open]');if(open){openPaper(open.dataset.open,Number(open.dataset.page)||null);return;}
 const status=e.target.closest('[data-status]');if(status){S.filter=status.dataset.status;showView('library');return;}
 const del=e.target.closest('[data-delete-note]');if(del&&confirm('删除这条笔记？此操作无法撤销。')){try{await api('/api/notes/'+del.dataset.deleteNote,{method:'DELETE'});await refresh();if(S.reader)renderReaderNotes();toast('笔记已删除。');}catch(error){toast(error.message,true);}}
});
document.addEventListener('keydown',e=>{if(e.key==='k'&&(e.metaKey||e.ctrlKey)){e.preventDefault();$('globalSearch').focus();}const el=e.target.closest('[data-open]');if(el&&e.key==='Enter')openPaper(el.dataset.open,Number(el.dataset.page)||null);});
$('libraryList').addEventListener('change',e=>{if(e.target.dataset.select){const ok=selectPaper(e.target.dataset.select,e.target.checked);if(!ok)e.target.checked=S.selected.has(e.target.dataset.select);}});
$('comparePapers').addEventListener('change',e=>{const id=e.target.dataset.compareSelect;if(!id)return;if(!selectPaper(id,e.target.checked))e.target.checked=S.selected.has(id);else mountChat($('compareChat'),[...S.selected]);});
$('libraryTabs').addEventListener('click',e=>{const b=e.target.closest('[data-filter]');if(b){S.filter=b.dataset.filter;renderLibrary();}});
$('categoryFilter').onchange=e=>{S.category=e.target.value;renderLibrary();};$('outlineSelect').onchange=e=>changePage(e.target.value);$('sortSelect').addEventListener('change',renderLibrary);$('compareSelected').onclick=()=>showView('compare');
for(const id of ['topImport','heroImport','dropImport'])$(id).onclick=()=>$('fileInput').click();$('fileInput').onchange=e=>uploadFiles(e.target.files);
for(const event of ['dragenter','dragover'])$('dropzone').addEventListener(event,e=>{e.preventDefault();$('dropzone').classList.add('dragover');});for(const event of ['dragleave','drop'])$('dropzone').addEventListener(event,e=>{e.preventDefault();$('dropzone').classList.remove('dragover');});$('dropzone').addEventListener('drop',e=>uploadFiles(e.dataTransfer.files));
$('globalSearch').addEventListener('input',e=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>search(e.target.value),350);});
$('backLibrary').onclick=()=>showView('library');$('prevPage').onclick=()=>changePage(S.page-1);$('nextPage').onclick=()=>changePage(S.page+1);$('pageInput').onchange=e=>changePage(e.target.value);
$('zoomIn').onclick=()=>{S.zoom=Math.min(2.5,S.zoom+.2);renderPage();};$('zoomOut').onclick=()=>{S.zoom=Math.max(.6,S.zoom-.2);renderPage();};
function setTextMode(value){S.textMode=value;$('pdfMode').classList.toggle('active',!value);$('textMode').classList.toggle('active',value);renderPage();}$('pdfMode').onclick=()=>setTextMode(false);$('textMode').onclick=()=>setTextMode(true);
$('pdfViewport').addEventListener('mouseup',()=>{const selection=window.getSelection();if(selection?.toString().trim()&&$('pdfViewport').contains(selection.anchorNode)&&$('pdfViewport').contains(selection.focusNode)){S.selection=selection.toString().trim().slice(0,6000);updateSelection();}});
$('chatTab').onclick=()=>showReaderTab('chat');$('notesTab').onclick=()=>showReaderTab('notes');
$('readerStatus').onchange=async e=>{try{Object.assign(paperById(S.reader),await patch('/api/papers/'+S.reader,{status:e.target.value}));renderCounts();toast('阅读状态已更新。');}catch(error){toast(error.message,true);}};
$('noteForm').onsubmit=async e=>{e.preventDefault();try{await post('/api/notes',{paper_id:S.reader,page:S.page,content:$('noteContent').value,quote:S.selection});$('noteContent').value='';S.drafts.delete(S.reader);S.selection='';await refresh();renderReaderNotes();updateSelection();toast('笔记已保存。');}catch(error){toast(error.message,true);}};
$('editPaper').onclick=()=>{const p=paperById(S.reader);$('editCategory').value=p.category;$('editTitle').value=p.title;$('editAuthors').value=p.authors;$('editYear').value=p.year;$('editTags').value=p.tags;$('editDialog').showModal();};$('closeEdit').onclick=()=>$('editDialog').close();
$('editForm').onsubmit=async e=>{e.preventDefault();try{const p=await patch('/api/papers/'+S.reader,{category:$('editCategory').value,title:$('editTitle').value,authors:$('editAuthors').value,year:$('editYear').value,tags:$('editTags').value});Object.assign(paperById(S.reader),p);$('readerTitle').textContent=p.title;$('readerMeta').textContent=`${p.authors||'作者待核对'}${p.year?' · '+p.year:''} · ${units(p)}`;$('editDialog').close();await mountChat($('readerChat'),[S.reader]);toast('资料信息已保存。');}catch(error){toast(error.message,true);}};
$('settingsForm').onsubmit=async e=>{e.preventDefault();try{await saveSettings();$('settingsFeedback').textContent='已保存';toast('AI 设置已保存。');}catch(error){toast(error.message,true);}};
$('openConfigFile').onclick=async()=>{try{const result=await post('/api/open-config');toast('已打开配置文件。填写 PAPER_API_KEY 并保存后，点击获取模型。');}catch(e){toast(e.message,true);}};
$('fetchModels').onclick=async()=>{const b=$('fetchModels');b.disabled=true;b.textContent='获取中…';try{await saveSettings();const result=await post('/api/models');$('modelOptions').innerHTML=result.models.map(m=>`<option value="${esc(m)}">`).join('');if(!result.models.length)throw new Error('服务没有返回模型列表，请手动填写模型名称。');$('modelHint').textContent=`已获取 ${result.models.length} 个模型。点击模型输入框选择，随后保存。`;$('modelName').focus();toast('模型列表已获取，请选择要使用的模型。');}catch(error){toast(error.message,true);}finally{b.disabled=false;b.textContent='获取模型';}};
window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(S.view==='reader'&&S.reader)renderPage();},250);});
window.addEventListener('beforeunload',e=>{if([...extensionViews.values()].some(v=>v.ui.hasUnsaved?.())||knowledgeUI.hasUnsaved()||onlineUI.hasUnsaved()||literatureUI.hasUnsaved()||briefUI.hasUnsaved()||S.busy||$('noteContent').value.trim()||[...S.drafts.values()].some(d=>d.trim())){e.preventDefault();e.returnValue='';}});
try{await refresh();await extensionsUI.load();showView('library');}catch(e){toast('本地服务连接失败，请重新启动程序。',true);}

window.addEventListener('focus',async()=>{try{S.config=await api('/api/settings');renderCounts();if(S.view==='settings')renderSettings();if(S.view==='reader')renderOCR();}catch{}});
