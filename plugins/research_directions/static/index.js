export function activate(ctx) {
  const {S, api, post, esc, icon, toast, registerView, showView} = ctx;
  const prefix = '/api/research-directions';
  const style = document.createElement('link');
  style.rel = 'stylesheet';
  style.href = '/plugins/research-directions/style.css';
  document.head.append(style);
  const section = document.createElement('section');
  section.id = 'view-directions';
  section.className = 'view';
  document.querySelector('#view-library').parentElement.append(section);
  const nav = document.createElement('button');
  nav.className = 'nav-item';
  nav.dataset.view = 'directions';
  nav.setAttribute('aria-label', '研究方向');
  nav.title = '研究方向';
  nav.innerHTML = icon('layers') + '<span>研究方向</span>';
  document.querySelector('.main-nav').append(nav);
  section.innerHTML = `
    <div class="page-heading"><div><div class="eyebrow">EXPLORE WITH EVIDENCE</div><h1>研究方向<span class="heading-dot">.</span></h1><p>从一个问题出发，找到相关论文，展开有出处的研究脉络。</p></div></div>
    <div class="direction-layout">
      <aside class="direction-sidebar">
        <form id="directionForm" class="card direction-form">
          <h2>开始一次梳理</h2>
          <label for="directionTopic">研究主题</label><textarea id="directionTopic" rows="3" maxlength="200" minlength="2" required placeholder="例如：工业遗产再利用中的公共空间评价"></textarea>
          <label for="directionEnglish">补充英文检索词（可选）</label><input id="directionEnglish" maxlength="200" placeholder="adaptive reuse public space evaluation">
          <div class="direction-row"><div><label for="directionFrom">起始年份</label><input id="directionFrom" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" placeholder="不限"></div><div><label for="directionTo">结束年份</label><input id="directionTo" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" placeholder="不限"></div></div>
          <label for="directionLimit">最多纳入论文</label><select id="directionLimit"><option value="8">8 篇 · 快速了解</option><option value="16" selected>16 篇 · 标准梳理</option><option value="24">24 篇 · 扩大范围</option></select>
          <fieldset><legend>论文来源</legend><div class="direction-checks"><label><input type="checkbox" name="provider" value="openalex" checked>OpenAlex</label><label><input type="checkbox" name="provider" value="semantic" checked>Semantic Scholar</label><label><input type="checkbox" name="provider" value="crossref" checked>Crossref</label><label><input type="checkbox" name="provider" value="arxiv">arXiv 预印本</label></div></fieldset>
          <label class="direction-toggle"><input type="checkbox" id="directionExpand" checked>自动补充英文检索词</label>
          <p class="muted">使用 AI 设置中的模型分析检索到的摘要。开启自动扩展会增加一次模型调用。</p>
          <button id="directionStart" class="button primary" type="submit">${icon('sparkles')}检索并生成导图</button>
        </form>
        <div class="card direction-history"><h2>历史梳理</h2><div id="directionHistory"></div></div>
      </aside>
      <main class="direction-results">
        <div class="card direction-progress"><div><strong id="directionStatus" role="status" aria-live="polite">输入主题，开始探索</strong><p id="directionMeta" class="muted">仅依据题录与摘要，导图中的方向需要进一步验证。</p></div><div class="direction-actions"><button id="directionCancel" class="button outline small" hidden>取消任务</button><button id="directionRetry" class="button outline small" hidden>复用结果重试分析</button><a id="directionMarkdown" class="button outline small" hidden>导出 Markdown</a><a id="directionJSON" class="button outline small" hidden>导出 JSON</a></div><div id="directionWarnings"></div></div>
        <div id="directionResult"><div class="card direction-placeholder">${icon('layers')}<h2>把论文串成研究脉络</h2><p>研究分支 → 代表论文 → 相关问题 → 候选方向</p><p class="muted">每个分析节点都可展开查看原文证据。</p></div></div>
        <div id="directionSources" class="card direction-sources" hidden></div>
      </main>
    </div>`;
  const element = id => section.querySelector('#' + id);
  let selected = null, current = null, timer = null, submitting = false, viewMode = 'map', rendered = '';
  const statusLabels = {searching: '检索中', analyzing: '分析中', done: '已完成', error: '未完成', cancelled: '已取消', interrupted: '已中断'};
  const running = run => run && ['searching', 'analyzing'].includes(run.status);
  const dirty = () => Boolean(element('directionTopic').value.trim());

  async function history() {
    const {runs} = await api(prefix);
    element('directionHistory').innerHTML = runs.length ? runs.map(run => `<button type="button" class="direction-history-item ${run.id === selected ? 'active' : ''}" data-run="${esc(run.id)}"><strong>${esc(run.topic)}</strong><small>${esc(statusLabels[run.status] || run.status)} · ${esc(new Date(run.created_at).toLocaleDateString('zh-CN'))}</small></button>`).join('') : '<p class="muted">还没有历史记录。</p>';
    return runs;
  }

  function evidence(entries) {
    return `<details class="direction-evidence"><summary>核对证据 · ${entries.length} 条</summary>${entries.map(entry => `<blockquote><p>${esc(entry.quote)}</p><button type="button" class="direction-source-link" data-source="${entry.source}">[${entry.source}] 查看论文摘要 ↗</button></blockquote>`).join('')}</details>`;
  }

  function leaf(node, direction) {
    const label = direction ? '研究建议 · 待验证' : node.kind === 'reported' ? '摘要明确报告' : '分析推断 · 待验证';
    return `<article class="direction-node ${direction ? 'suggestion' : 'problem'}"><span class="direction-kind">${label}</span><h4>${esc(node.title)}</h4><p>${esc(node.detail)}</p>${evidence(node.evidence)}</article>`;
  }

  function branch(node) {
    const numbers = [...new Set([...node.evidence, ...node.problems.flatMap(item => item.evidence), ...node.directions.flatMap(item => item.evidence)].map(entry => entry.source))];
    return `<details class="direction-branch" open><summary>${esc(node.name)}<small>${numbers.length} 篇支撑文献</small></summary><div class="direction-branch-body"><article class="direction-node direction-branch-summary"><span class="direction-kind">研究分支</span><p>${esc(node.summary)}</p><div class="direction-paper-links">${numbers.map(number => `<button type="button" data-source="${number}" class="direction-source-link">论文 [${number}]</button>`).join('')}</div>${evidence(node.evidence)}</article><div class="direction-node-group"><h3>相关问题</h3>${node.problems.map(node => leaf(node, false)).join('')}</div><div class="direction-node-group"><h3>候选研究方向</h3>${node.directions.map(node => leaf(node, true)).join('')}</div></div></details>`;
  }

  function render(run) {
    current = run;
    const active = running(run);
    element('directionStatus').textContent = run.error || run.stage;
    element('directionStatus').classList.toggle('direction-error', run.status === 'error');
    const usable = run.sources.filter(source => source.basis === 'abstract').length;
    element('directionMeta').textContent = `${run.topic} · ${run.sources.length} 篇题录 / ${usable} 篇可用摘要 · ${new Date(run.created_at).toLocaleString('zh-CN')} · ${run.model}`;
    element('directionWarnings').innerHTML = run.warnings.map(warning => `<p class="direction-warning">${esc(warning)}</p>`).join('');
    element('directionCancel').hidden = !active;
    element('directionRetry').hidden = active || run.status === 'done';
    element('directionStart').disabled = submitting || active;
    element('directionMarkdown').hidden = !run.sources.length;
    element('directionJSON').hidden = !run.sources.length;
    element('directionMarkdown').href = `${prefix}/${run.id}/export`;
    element('directionJSON').href = `${prefix}/${run.id}/export?format=json`;
    const signature = run.id + run.status + run.sources.length;
    if (signature === rendered) return;
    rendered = signature;
    if (run.report.branches) {
      element('directionResult').innerHTML = `<div class="card direction-overview"><span class="eyebrow">${esc(run.queries.join(' / '))}</span><h2>${esc(run.topic)}</h2><p>${esc(run.report.overview.text)}</p>${evidence(run.report.overview.evidence)}<div class="direction-actions"><button type="button" class="button outline small" data-mode="map" aria-pressed="${viewMode === 'map'}">导图</button><button type="button" class="button outline small" data-mode="outline" aria-pressed="${viewMode === 'outline'}">大纲</button><button type="button" class="button outline small" data-expand>展开全部</button><button type="button" class="button outline small" data-collapse>折叠分支</button></div></div><div class="direction-map ${viewMode === 'outline' ? 'outline-view' : ''}" aria-label="研究方向导图"><div class="direction-root">${esc(run.topic)}</div><div class="direction-branches">${run.report.branches.map(branch).join('')}</div></div>`;
    } else {
      element('directionResult').innerHTML = `<div class="card direction-placeholder">${icon(active ? 'search' : 'layers')}<h2>${active ? '正在建立研究脉络' : '检索记录已保留'}</h2><p>${esc(run.stage)}</p><p class="muted">${active ? '可切换到阅读页面，任务会继续。' : '可以复用已有摘要重试分析，或修改主题重新检索。'}</p></div>`;
    }
    const sources = element('directionSources');
    sources.hidden = !run.sources.length;
    sources.innerHTML = `<h2>参考论文 <span class="badge">${run.sources.length}</span></h2><p class="muted">仅基于索引提供的摘要，未自动下载或阅读全文。题录缺少摘要时不用于生成分析。</p>${run.sources.map(source => `<details id="direction-source-${source.number}" class="direction-paper"><summary><span>[${source.number}] ${esc(source.title)}</span><small>${esc(source.year)} · ${esc(source.providers.join(' / '))}</small></summary><p>${esc(source.authors.join(', '))} · ${esc(source.venue)}</p><p class="direction-abstract">${esc(source.abstract || '索引未提供摘要。')}</p><a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">打开论文来源 ↗</a>${source.fulltext_url ? ` <a href="${esc(source.fulltext_url)}" target="_blank" rel="noopener noreferrer">全文链接 ↗</a>` : ''}</details>`).join('')}`;
  }

  async function load(runId) {
    selected = runId;
    clearTimeout(timer);
    try {
      const {run} = await api(`${prefix}/${runId}`);
      if (selected !== runId) return;
      render(run);
      if (running(run)) timer = setTimeout(() => load(runId), 1800);
      else await history();
    } catch (error) {
      if (selected !== runId) return;
      element('directionStatus').textContent = '进度读取失败：' + error.message;
      if (running(current)) timer = setTimeout(() => load(runId), 4000);
    }
  }

  element('directionForm').addEventListener('submit', async event => {
    event.preventDefault();
    if (submitting) return;
    if (!S.config.has_key || !S.config.model) {
      toast('请先配置 AI 密钥和模型。', true);
      showView('settings');
      return;
    }
    submitting = true;
    element('directionStart').disabled = true;
    try {
      const body = {topic: element('directionTopic').value.trim(), english_query: element('directionEnglish').value.trim(),
        year_from: element('directionFrom').value.trim(), year_to: element('directionTo').value.trim(),
        limit: Number(element('directionLimit').value), expand_query: element('directionExpand').checked,
        providers: [...section.querySelectorAll('[name="provider"]:checked')].map(input => input.value)};
      const {run} = await post(prefix, body);
      element('directionTopic').value = '';
      rendered = '';
      await load(run.id);
      await history();
    } catch (error) { toast(error.message, true); }
    finally { submitting = false; element('directionStart').disabled = running(current); }
  });
  element('directionCancel').onclick = async () => {
    if (!selected) return;
    try { await post(`${prefix}/${selected}/cancel`); await load(selected); }
    catch (error) { toast(error.message, true); }
  };
  element('directionRetry').onclick = async () => {
    if (!selected) return;
    element('directionRetry').disabled = true;
    try { const {run} = await post(`${prefix}/${selected}/retry`); rendered = ''; await load(run.id); await history(); }
    catch (error) { toast(error.message, true); }
    finally { element('directionRetry').disabled = false; }
  };
  section.addEventListener('click', event => {
    const target = event.target.closest('button');
    if (!target) return;
    if (target.dataset.run) { rendered = ''; load(target.dataset.run); }
    if (target.dataset.source) {
      const source = element('direction-source-' + target.dataset.source);
      if (source) { source.open = true; source.scrollIntoView({behavior: 'smooth', block: 'center'}); }
    }
    if (target.dataset.mode) {
      viewMode = target.dataset.mode;
      section.querySelector('.direction-map')?.classList.toggle('outline-view', viewMode === 'outline');
      section.querySelectorAll('[data-mode]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.mode === viewMode)));
    }
    if (target.hasAttribute('data-expand') || target.hasAttribute('data-collapse')) {
      section.querySelectorAll('.direction-branch').forEach(branch => { branch.open = target.hasAttribute('data-expand'); });
    }
  });
  const readerButton = document.createElement('button');
  readerButton.className = 'button outline small';
  readerButton.textContent = '探索研究方向';
  readerButton.onclick = () => {
    const paper = S.papers.find(paper => paper.id === S.reader);
    element('directionTopic').value = (S.selection || paper?.title || '').slice(0, 200);
    showView('directions');
    element('directionTopic').focus();
  };
  document.querySelector('#readerKnowledge').after(readerButton);
  registerView('directions', '研究方向', {
    hasUnsaved: dirty,
    async show() {
      try {
        const runs = await history();
        if (!selected && runs.length) selected = (runs.find(running) || runs[0]).id;
        if (selected) await load(selected);
      } catch (error) { toast(error.message, true); }
    }
  });
}
