export function initBriefs(context){
 const {S,api,post,esc,icon,safeMarkdown,toast,openPaper,showView}=context;
 const element=id=>document.getElementById(id);
 const state={current:null,history:[],busy:false,dirty:false,loading:0,searchDrafts:new Map()};
 element('view-briefs').innerHTML=`<div class="page-heading"><div><div class="eyebrow">FROM BRIEF TO DESIGN PRECEDENTS</div><h1>任务书解读<span class="heading-dot">.</span></h1><p>读清要求，提炼关键词，让案例与文献检索都有学习方向。</p></div><button id="bfNew" class="button outline">${icon('plus')}新建解读</button></div>
 <div class="bf-history"><label for="bfHistory">已保存的解读</label><select id="bfHistory"><option value="">选择历史记录</option></select></div>
 <details id="bfInputPanel" class="card bf-input" open><summary>任务书来源与解读范围</summary><form id="bfForm">
 <label class="field-label" for="bfTitle">任务书标题 <small>可选</small></label><input id="bfTitle" maxlength="200" placeholder="例如：社区图书馆设计任务书">
 <div class="bf-source-tabs"><label><input type="radio" name="bfMode" value="document" checked>从资料库选择</label><label><input type="radio" name="bfMode" value="paste">粘贴任务书原文</label></div>
 <div id="bfDocumentFields"><label class="field-label" for="bfDocument">任务书文件</label><div class="bf-document-row"><select id="bfDocument" aria-label="选择任务书文件"></select><button id="bfImport" class="button outline small" type="button">${icon('upload')}导入任务书</button></div>
 <div class="bf-range"><label>起始页 / 段<input id="bfStart" type="number" min="1" step="1" value="1"></label><label>结束页 / 段<input id="bfEnd" type="number" min="1" step="1" value="1"></label><button id="bfRead" class="button ghost small" type="button">打开原文 / 文字识别 ↗</button></div><small>支持 PDF、Word、EPUB、TXT、Markdown。扫描 PDF 请先完成文字识别；图纸与图片须结合原件核对。</small></div>
 <div id="bfPasteFields" hidden><label class="field-label" for="bfText">原文内容</label><textarea id="bfText" rows="9" maxlength="32000" placeholder="粘贴设计目标、场地条件、功能与规模、交付成果等原文…"></textarea></div>
 <div class="bf-form-foot"><small>选定原文发送到已配置的 AI 服务。单次最多 32,000 字、60 页 / 段；每次成功解读单独保存。</small><button id="bfInterpret" class="button primary" type="submit">${icon('sparkles')}解读并提取关键词</button></div></form></details>
 <p id="bfStatus" class="bf-status" role="status">解读后可编辑检索词与学习重点，再查找相关案例与文献。</p><div id="bfResult"></div><input id="bfFile" type="file" accept=".pdf,.docx,.epub,.txt,.md" hidden>`;

 function selectedMode(){return element('view-briefs').querySelector('input[name="bfMode"]:checked').value;}
 function busy(value){state.busy=value;for(const control of element('bfForm').elements)control.disabled=value;element('bfNew').disabled=value;element('bfHistory').disabled=value;}
 function paperOptions(){const selected=element('bfDocument').value;element('bfDocument').innerHTML='<option value="">选择已导入的任务书…</option>'+S.papers.map(paper=>`<option value="${paper.id}">${esc(paper.title)} · ${paper.page_count} ${paper.format==='pdf'?'页':'段'}</option>`).join('');if(S.papers.some(paper=>paper.id===selected))element('bfDocument').value=selected;}
 function historyOptions(){element('bfHistory').innerHTML='<option value="">选择历史记录</option>'+state.history.map(brief=>`<option value="${brief.id}">${esc(brief.title)} · ${new Date(brief.created_at).toLocaleString('zh-CN')}</option>`).join('');element('bfHistory').value=state.current?.id||'';}
 function modeFields(){const documentMode=selectedMode()==='document';element('bfDocumentFields').hidden=!documentMode;element('bfPasteFields').hidden=documentMode;element('bfText').required=!documentMode;element('bfDocument').required=documentMode;for(const id of ['bfStart','bfEnd'])element(id).required=documentMode;}
 function documentRange(){const paper=S.papers.find(entry=>entry.id===element('bfDocument').value);element('bfStart').value=1;element('bfEnd').value=paper?.page_count||1;for(const id of ['bfStart','bfEnd'])element(id).max=paper?.page_count||1;}
 function restoreInput(brief){if(state.dirty)return;const documentMode=brief.paper_id&&S.papers.some(paper=>paper.id===brief.paper_id);element('view-briefs').querySelector(`input[name="bfMode"][value="${documentMode?'document':'paste'}"]`).checked=true;element('bfTitle').value=brief.title;if(documentMode){element('bfDocument').value=brief.paper_id;documentRange();element('bfStart').value=brief.coverage.start;element('bfEnd').value=brief.coverage.end;}else element('bfText').value=brief.input_text||brief.sources.map(source=>source.quote).join('\n');modeFields();}
 function markdown(target,text){target.replaceChildren(safeMarkdown(text,state.current.sources));}
 function render(){
  const brief=state.current;
  if(!brief){element('bfResult').innerHTML='<div class="bf-empty"><i>'+icon('note')+'</i><h2>从一份任务书开始</h2><p>设计要求 → 任务关键词 → 案例与文献检索 → 分析与归档</p></div>';return;}
  const analysis=brief.analysis;
  element('bfResult').innerHTML=`<article class="card bf-overview"><div class="bf-result-heading"><div><span class="badge">AI 解读 · 待复核</span><h2>${esc(brief.title)}</h2><small>${esc(brief.coverage.label)} · ${brief.coverage.chars.toLocaleString()} 字</small></div><a class="button outline small" href="/api/briefs/${brief.id}/export" download>导出解读</a></div><div id="bfSummary" class="message-content"></div>${brief.coverage.warnings.length?`<div class="bf-warning">${brief.coverage.warnings.map(warning=>`<p>${esc(warning)}</p>`).join('')}</div>`:''}</article>
 <section class="card bf-section"><div class="bf-section-heading"><h2>01 <span>任务要求清单</span></h2><small>点击编号跳转原文依据</small></div><div class="bf-requirements">${analysis.requirements.map((requirement,index)=>`<div class="bf-requirement"><span class="bf-category">${esc(requirement.category)}</span><div><div class="message-content" data-bf-requirement="${index}"></div><blockquote>${esc(requirement.quote)}</blockquote></div></div>`).join('')}</div></section>
 <section class="card bf-section"><div class="bf-section-heading"><h2>02 <span>任务关键词</span></h2><small>点击关键词加入自定义检索</small></div><div class="bf-keywords">${analysis.keywords.map((keyword,index)=>`<div><button type="button" data-bf-keyword="${index}" class="bf-keyword">${esc(keyword.term)} ${icon('plus')}</button><span class="bf-keyword-basis">${esc(keyword.basis)}</span><div class="message-content" data-bf-reason="${index}"></div></div>`).join('')}</div></section>
 <section class="bf-section bf-search-section"><div class="bf-section-heading"><h2>03 <span>带着问题寻找案例与文献</span></h2><small>可修改检索词和学习重点，检索后保留记录</small></div><div class="bf-searches">${[...analysis.searches,{query:'',focus:'',custom:true}].map((search,index)=>`<form class="card bf-search" data-bf-search="${index}"><label for="bfQuery${index}">${search.custom?'自定义检索':'学习方向 '+String(index+1).padStart(2,'0')}</label><input id="bfQuery${index}" name="query" type="search" value="${esc(search.query)}" minlength="2" maxlength="200" required placeholder="组合建筑类型与空间特征"><label for="bfFocus${index}">希望学习与解决的问题</label><textarea id="bfFocus${index}" name="focus" rows="3" maxlength="800" required placeholder="例如：庭院如何组织公共活动与安静阅读区">${esc(search.focus)}</textarea><div class="bf-search-buttons"><button class="button primary small" type="submit">${icon('search')}检索学习案例 ↗</button><button class="button outline small" type="submit" data-bf-literature>检索相关文献 ↗</button></div></form>`).join('')}</div><p class="bf-public-note">只有此处的检索词发送给搜索网站。案例与文献分析结合任务书背景与学习重点，附原网址；请先确认检索词适合公开。</p></section>
 ${brief.history?.length?`<section class="card bf-section"><h2>已检索的学习方向</h2><div class="bf-search-history">${brief.history.map((search,index)=>`<button class="button outline small" data-bf-history="${index}">${esc(search.query)} · ${search.count} 个候选</button>`).join('')}</div></section>`:''}
 ${brief.literature_history?.length?`<section class="card bf-section"><h2>相关文献检索记录</h2><div class="bf-search-history">${brief.literature_history.map(search=>`<button class="button outline small" data-bf-lit-history="${search.id}">${esc(search.query)} ↗</button>`).join('')}</div></section>`:''}
 <section class="card bf-section"><h2>待澄清与补充</h2><div id="bfQuestions" class="message-content"></div></section><details id="bfSources" class="card bf-section"><summary>原文依据 · ${brief.sources.length} 段</summary><div class="bf-sources">${brief.sources.map(source=>`<section id="bfSource${source.number}"><button class="button ghost small" data-source="${source.number}">[${source.number}] ${esc(source.locator)} ${source.paper_id?'↗':''}</button><p>${esc(source.quote)}</p></section>`).join('')}</div></details>`;
  markdown(element('bfSummary'),analysis.summary);
  for(const [index,requirement] of analysis.requirements.entries())markdown(element('bfResult').querySelector(`[data-bf-requirement="${index}"]`),requirement.text+` [${requirement.source}]`);
  for(const [index,keyword] of analysis.keywords.entries())markdown(element('bfResult').querySelector(`[data-bf-reason="${index}"]`),keyword.reason+(keyword.source?` [${keyword.source}]`:''));
  markdown(element('bfQuestions'),analysis.questions.length?analysis.questions.map(question=>'- '+question).join('\n'):'当前解读未列出待澄清事项，请结合原任务书复核。');
  for(const [index,draft] of (state.searchDrafts.get(brief.id)||[]).entries()){if(!draft)continue;const query=element('bfQuery'+index),focus=element('bfFocus'+index);if(query)query.value=draft.query;if(focus)focus.value=draft.focus;}
 }
 async function load(briefId){
  if(state.busy)return;
  const token=++state.loading;
  try{const data=await api('/api/briefs/'+briefId);if(token!==state.loading||state.busy)return;state.current=data.brief;restoreInput(data.brief);element('bfHistory').value=briefId;element('bfInputPanel').open=false;render();element('bfStatus').textContent='已载入保存的解读与案例检索方向。';}
  catch(error){toast(error.message,true);}
 }
 element('bfDocument').onchange=()=>{documentRange();state.dirty=true;};
 element('bfForm').addEventListener('input',()=>{state.dirty=true;});
 for(const radio of element('view-briefs').querySelectorAll('input[name="bfMode"]'))radio.onchange=modeFields;
 element('bfRead').onclick=()=>{const paperId=element('bfDocument').value;if(paperId)openPaper(paperId,Number(element('bfStart').value)||1);else toast('请先选择或导入任务书。');};
 element('bfImport').onclick=()=>element('bfFile').click();
 element('bfFile').onchange=async()=>{
  const file=element('bfFile').files[0];if(!file||state.busy)return;
  busy(true);element('bfStatus').textContent='正在导入任务书…';
  try{const imported=await api('/api/papers?filename='+encodeURIComponent(file.name),{method:'POST',body:file});await context.refresh();paperOptions();element('bfDocument').value=imported.paper?.id||imported.id;documentRange();state.dirty=true;element('bfStatus').textContent='任务书已导入。扫描件请先打开原文进行文字识别。';}
  catch(error){element('bfStatus').textContent=error.message;toast(error.message,true);}
  finally{busy(false);element('bfFile').value='';}
 };
 element('bfForm').onsubmit=async event=>{
  event.preventDefault();if(state.busy)return;
  if(!S.config.has_key||!S.config.model){toast('请先配置 AI 密钥与模型，输入会保留。',true);showView('settings');return;}
  const documentMode=selectedMode()==='document';const body={title:element('bfTitle').value,...(documentMode?{paper_id:element('bfDocument').value,start_page:Number(element('bfStart').value),end_page:Number(element('bfEnd').value)}:{text:element('bfText').value})};
  ++state.loading;busy(true);element('bfStatus').textContent='正在读取选定原文、提取任务要求并核对引用，请稍候…';
  try{const data=await post('/api/briefs',body);state.current=data.brief;state.dirty=false;state.history=[data.brief,...state.history];historyOptions();element('bfInputPanel').open=false;render();element('bfStatus').textContent='解读已保存。选择下方学习方向，即可检索相关案例。';}
  catch(error){element('bfStatus').textContent=error.message;toast(error.message,true);}
  finally{busy(false);}
 };
 element('bfNew').onclick=()=>{if(state.busy)return;state.current=null;++state.loading;element('bfHistory').value='';element('bfInputPanel').open=true;render();element('bfStatus').textContent='可使用当前输入继续解读，或更换任务书；已有记录保留在历史中。';};
 element('bfHistory').onchange=()=>{if(element('bfHistory').value)load(element('bfHistory').value);};
 function rememberSearch(form){if(!form||!state.current)return;const drafts=state.searchDrafts.get(state.current.id)||[];drafts[Number(form.dataset.bfSearch)]={query:form.elements.query.value,focus:form.elements.focus.value};state.searchDrafts.set(state.current.id,drafts);}
 element('bfResult').addEventListener('input',event=>{rememberSearch(event.target.closest('[data-bf-search]'));});
 element('bfResult').addEventListener('submit',async event=>{
  const form=event.target.closest('[data-bf-search]');if(!form)return;event.preventDefault();if(state.busy)return;
  rememberSearch(form);const search=event.submitter?.hasAttribute('data-bf-literature')?context.searchLiterature:context.searchCases;await search(state.current,form.elements.query.value.trim(),form.elements.focus.value.trim());
 });
 element('bfResult').addEventListener('click',async event=>{
  const citation=event.target.closest('[data-source]');if(citation){const source=state.current.sources.find(entry=>entry.number===Number(citation.dataset.source));if(source?.paper_id){await openPaper(source.paper_id,source.page);}else if(source){element('bfSources').open=true;element('bfSource'+source.number).scrollIntoView({behavior:'smooth',block:'center'});}return;}
  const keywordButton=event.target.closest('[data-bf-keyword]');if(keywordButton){const keyword=state.current.analysis.keywords[Number(keywordButton.dataset.bfKeyword)];const index=state.current.analysis.searches.length;const input=element('bfQuery'+index);input.value=[input.value.trim(),keyword.term].filter(Boolean).join(' ').slice(0,200);input.focus();if(!element('bfFocus'+index).value)element('bfFocus'+index).value=keyword.reason;rememberSearch(input.closest('form'));return;}
  const literatureButton=event.target.closest('[data-bf-lit-history]');if(literatureButton){await context.openLiterature(literatureButton.dataset.bfLitHistory);return;}
  const historyButton=event.target.closest('[data-bf-history]');if(historyButton){const search=state.current.history[Number(historyButton.dataset.bfHistory)];await context.searchCases(state.current,search.query,search.learning_focus,true);}
 });
 modeFields();render();
 return {show:async()=>{const token=state.loading;paperOptions();try{const data=await api('/api/briefs');state.history=data.briefs;historyOptions();if(token===state.loading&&state.current&&!state.busy)await load(state.current.id);}catch(error){toast(error.message,true);}},open:async briefId=>{showView('briefs');await load(briefId);},hasUnsaved:()=>state.busy||state.dirty};
}
