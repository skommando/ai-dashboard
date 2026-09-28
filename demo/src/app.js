(function () {
  'use strict';
  const { projects, dateLabel } = DemoData;
  const { summarize, matches } = ProgressModel;
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
  const shapes = {
    grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    book: '<path d="M4 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-2H4z"/><path d="M13 7a3 3 0 0 1 3-3h4v15h-4a4 4 0 0 0-3 2"/><path d="M7 8h3M7 11h3"/>',
    receipt: '<path d="M5 3l3 2 4-2 4 2 3-2v18l-3-2-4 2-4-2-3 2z"/><path d="M9 9h6M9 13h6"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="8" cy="9" r="1.5"/><path d="m21 16-5-5-7 8M3 16l4-4 4 3"/>',
    bookmark: '<path d="M6 3h12v18l-6-4-6 4z"/><path d="M9 7h6M9 10h4"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c-5 5-5 13 0 18 5-5 5-13 0-18z"/>',
    monitor: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
    eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.3 8.7a2.8 2.8 0 0 1 5.4.9c0 2-2.7 2-2.7 4M12 17h.01"/>',
    chevronDown: '<path d="m6 9 6 6 6-6"/>',
    chevronRight: '<path d="m9 5 7 7-7 7"/>',
    arrowLeft: '<path d="m10 5-7 7 7 7M3 12h18"/>',
    arrowUpRight: '<path d="M6 18 18 6M6 6h12v12"/>',
    arrowRight: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
    close: '<path d="m6 6 12 12M6 18 18 6"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    attention: '<path d="M12 3 2.5 20h19z"/><path d="M12 9v4M12 16h.01"/>',
    checkCircle: '<circle cx="12" cy="12" r="9"/><path d="m7 12 3 3 7-7"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5"/>',
    wifiOff: '<path d="m3 3 18 18M8.5 8.5A13 13 0 0 0 2 12m20 0a13 13 0 0 0-10-4M5 16a9 9 0 0 1 7-3m6.5 3a9 9 0 0 0-2-1.5M8 19a5 5 0 0 1 7-1M12 21h.01"/>',
    layers: '<path d="m12 3 10 5-10 5L2 8zM2 12l10 5 10-5M2 16l10 5 10-5"/>',
    empty: '<path d="M5 5h14l3 11v4H2v-4z"/><path d="M2 16h6l2 3h4l2-3h6M9 9h6"/>',
    pause: '<path d="M9 7v10M15 7v10"/>',
  };
  const icon = (name, cls = '') => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${shapes[name] || shapes.grid}</svg>`;
  function fillIcons(container = document) { container.querySelectorAll('[data-icon]').forEach(node => { node.innerHTML = icon(node.dataset.icon); }); }
  const statusLabels = { active: '进行中', blocked: '已阻塞', review: '待验收', complete: '已完成', planning: '规划中', done: '已完成', todo: '未开始', waiting: '待确认', failed: '失败', cancelled: '已取消' };
  const statusTag = status => `<span class="status-tag ${esc(status)}">${esc(statusLabels[status] || status)}</span>`;
  const attention = project => ['blocked', 'review'].includes(project.status) || summarize(project).pendingAcceptance > 0;
  const filters = [
    { id: 'all', name: '全部', nav: '项目总览', icon: 'grid', match: () => true },
    { id: 'active', name: '进行中', nav: '进行中', icon: 'clock', match: p => p.status === 'active' },
    { id: 'attention', name: '需关注', nav: '需要关注', icon: 'attention', match: attention },
    { id: 'complete', name: '已完成', nav: '已完成', icon: 'checkCircle', match: p => p.status === 'complete' },
  ];
  const state = { filter: 'all', query: '', projectId: projects[0].id, view: 'home', taskId: null, scenario: 'online', homeScroll: 0, openWaves: new Map() };
  projects.forEach(project => state.openWaves.set(project.id, new Set([project.currentWave])));
  const visibleProjects = () => projects.filter(project => filters.find(f => f.id === state.filter).match(project) && matches(project, state.query))
    .sort((a, b) => Number(attention(b)) - Number(attention(a)));
  const activeProject = () => projects.find(p => p.id === state.projectId) || projects[0];
  const projectLink = project => `#project/${encodeURIComponent(project.id)}`;
  const taskLink = (project, task) => `${projectLink(project)}/task/${encodeURIComponent(task.id)}`;
  const symbol = status => `<span class="task-symbol ${esc(status)}" aria-hidden="true">${status === 'done' ? icon('check') : ['blocked', 'waiting', 'failed'].includes(status) ? icon('pause') : ''}</span>`;
  const progress = (summary, label, className = '') => summary.total
    ? `<progress class="${className}" value="${summary.done}" max="${summary.total}" aria-label="${esc(label)}：${summary.done}/${summary.total} Task 已完成"></progress>`
    : '<span class="unplanned-track" aria-label="尚未登记任务"></span>';

  function renderNavigation() {
    $('#primary-nav').innerHTML = filters.filter(f => f.id !== 'active').map(f => `<button type="button" class="nav-button ${state.filter === f.id ? 'active' : ''}" data-filter="${f.id}" aria-pressed="${state.filter === f.id}">${icon(f.icon)}<span>${f.nav}</span><span class="nav-count">${projects.filter(f.match).length}</span></button>`).join('');
    $('#side-projects').innerHTML = projects.map(project => `<a class="side-project ${state.projectId === project.id ? 'selected' : ''}" href="${projectLink(project)}"><span class="tiny-dot ${project.status}" aria-hidden="true"></span>${esc(project.shortName)}</a>`).join('');
    $('#filters').innerHTML = filters.map(f => `<button type="button" class="filter-button ${state.filter === f.id ? 'active' : ''}" data-filter="${f.id}" aria-pressed="${state.filter === f.id}">${f.name}<span>${projects.filter(f.match).length}</span></button>`).join('');
    $('#overview-summary').textContent = `${projects.filter(p => p.status === 'active').length} 个推进中，${projects.filter(attention).length} 个需关注`;
  }

  function renderList() {
    const scroll = $('#project-scroll').scrollTop;
    const visible = visibleProjects();
    $('#list-caption').textContent = state.query ? `找到 ${visible.length} 个项目` : `${visible.length} 个项目${state.filter === 'all' ? ' · 需关注优先' : ''}`;
    $('#project-list').innerHTML = visible.length ? visible.map(project => {
      const summary = summarize(project);
      const wave = project.waves.find(w => w.id === project.currentWave);
      const waveNumber = String(Number(project.currentWave.slice(1))).padStart(2, '0');
      return `<a role="listitem" class="project-row ${state.projectId === project.id ? 'selected' : ''}" href="${projectLink(project)}" data-project="${project.id}" data-status="${project.status}" aria-label="查看${esc(project.name)}，${statusLabels[project.status]}，${summary.total ? `${summary.done}/${summary.total} Task` : '尚未登记任务'}">
        <div class="row-top"><span class="project-icon ${project.color}">${icon(project.glyph)}</span><div class="row-identity"><strong>${esc(project.name)}</strong><span class="row-wave"><span class="wave-code">WAVE ${waveNumber}</span>${esc(wave.name)}</span></div>${statusTag(project.status)}</div>
        <p class="row-summary">${esc(project.summary)}</p>
        <div class="row-bottom">${progress(summary, project.name)}<span class="row-count">${summary.total ? `<b>${summary.done}</b> / ${summary.total}` : '待拆分'}</span><span class="row-percent">${summary.percent === null ? '—' : `${summary.percent}%`}</span><span class="row-updated">${esc(project.updated)}</span></div>
      </a>`;
    }).join('') : `<div class="empty-state" role="listitem">${icon('search')}<h2>没有找到项目</h2><p>${state.query ? `没有与“${esc(state.query)}”匹配的项目或任务。` : '这个筛选条件下暂时没有项目。'}</p><button class="text-button" type="button" data-action="clear-search">清除筛选</button></div>`;
    $('#project-scroll').scrollTop = scroll;
    renderNavigation();
  }

  function waveMarkup(project, wave, index) {
    const summary = summarize({ waves: [wave] });
    const current = project.currentWave === wave.id;
    const complete = summary.total > 0 && summary.done === summary.total;
    const expanded = state.openWaves.get(project.id).has(wave.id);
    const caption = wave.acceptance === 'pending' ? '实施完成 · 待验收' : current ? '当前阶段' : wave.defined === false ? '后续计划' : complete ? '已完成' : '尚未开始';
    return `<details class="wave ${current ? 'current' : ''}" data-wave="${wave.id}" data-owner="${project.id}" ${expanded ? 'open' : ''}>
      <summary aria-label="Wave ${index + 1} ${esc(wave.name)} ${summary.total ? `${summary.done}/${summary.total}` : '待细化'}"><span class="wave-number ${current ? 'current' : complete ? 'complete' : ''} ${wave.defined === false ? 'undefined' : ''}">${complete && !current ? icon('check') : String(index + 1).padStart(2, '0')}</span><span class="wave-title"><strong>${esc(wave.name)}</strong><small>${caption}</small></span><span class="wave-count ${summary.total ? '' : 'text'}">${summary.total ? `${summary.done} / ${summary.total}` : '待细化'}</span><span class="wave-chevron">${icon('chevronRight')}</span></summary>
      <div class="wave-body">${wave.tasks.length ? wave.tasks.map(task => `<a class="task-row" data-task="${task.id}" data-status="${task.status}" href="${taskLink(project, task)}" aria-label="查看任务：${esc(task.title)}，${statusLabels[task.status]}">${symbol(task.status)}<span class="task-name">${esc(task.title)}${task.status === 'active' ? '<small class="task-hint">正在推进</small>' : task.status === 'waiting' ? '<small class="task-hint">等待确认</small>' : ''}</span><span class="task-code">${esc(task.code)}</span>${icon('chevronRight', 'task-chevron')}</a>`).join('') : '<div class="wave-empty">这个阶段还没有拆分 Task，暂不计入已规划范围。</div>'}</div>
    </details>`;
  }

  function projectMarkup(project) {
    const summary = summarize(project);
    const ongoing = project.waves.flatMap(w => w.tasks).find(t => ['active', 'waiting', 'blocked'].includes(t.status));
    const focus = ongoing ? `<a class="focus-note ${project.status}" href="${taskLink(project, ongoing)}"><span class="focus-label">${project.status === 'blocked' ? '需要你确认' : '当前在做'}${icon('arrowUpRight')}</span><strong>${esc(project.blocker || ongoing.title)}</strong></a>`
      : summary.pendingAcceptance ? '<div class="focus-note review"><span class="focus-label">等待阶段验收</span><strong>实施工作已完成，可以查看本阶段的交付效果。</strong></div>' : '';
    return `<div class="detail-nav"><span class="desktop-detail-label">项目详情</span><a class="back-link mobile-back" href="#">${icon('arrowLeft')}全部项目</a><span class="detail-nav-end">${icon('eye')}只读</span></div>
      <div class="detail-content"><div class="detail-project-heading"><span class="project-icon ${project.color}">${icon(project.glyph)}</span><div class="detail-title-wrap"><h2 tabindex="-1">${esc(project.name)}</h2><span class="category-label">${esc(project.category)}</span></div>${statusTag(project.status)}</div>
      <p class="detail-description">${esc(project.description)}</p>
      <div class="metric-top"><span>已规划范围</span><div class="metric-ratio"><span>${summary.total ? `${summary.done} / ${summary.total} Task` : '尚未登记任务'}</span><strong>${summary.percent === null ? '—' : `${summary.percent}<small>%</small>`}</strong></div></div>
      ${progress(summary, project.name, 'detail-progress')}
      <div class="scope-note ${summary.pendingAcceptance ? 'pending' : ''}">${icon(summary.pendingAcceptance ? 'clock' : 'layers')}<span>${summary.pendingAcceptance ? `${summary.pendingAcceptance} 个验收事项待确认，实施完成度已计入。` : summary.unplannedWaves ? `另有 ${summary.unplannedWaves} 个 Wave 待细化，以上仅统计已规划 Task。` : project.status === 'complete' ? '全部任务已完成，交付检查已通过。' : '按 Task 等权计量，子项不增加任务总数。'}</span></div>
      ${focus}
      <div class="section-heading"><h3>阶段与任务</h3><span>${String(project.waves.length).padStart(2, '0')} WAVES</span></div>
      <div class="wave-list">${project.waves.map((wave, index) => waveMarkup(project, wave, index)).join('')}</div>
      <div class="section-heading"><h3>最近进展</h3><span>示例记录</span></div><ol class="activity-list">${project.updates.map(update => `<li><time>${esc(update.time)}</time><div><strong>${esc(update.text)}</strong><small>${esc(update.detail)}</small></div></li>`).join('')}</ol>
      <div class="detail-end">最后上报 · ${esc(project.updatedAt)}</div></div>`;
  }

  function taskMarkup(project, taskId) {
    const wave = project.waves.find(w => w.tasks.some(t => t.id === taskId));
    if (!wave) return projectMarkup(project);
    const task = wave.tasks.find(t => t.id === taskId);
    const childrenDone = task.children.filter(child => child.status === 'done').length;
    return `<div class="detail-nav"><a class="back-link" href="${projectLink(project)}">${icon('arrowLeft')}返回项目</a><span class="detail-nav-end">${icon('eye')}任务详情</span></div>
      <div class="detail-content"><div class="task-breadcrumb">${esc(project.name)}<span class="sub-dot"> / </span>${esc(wave.name)}</div><h2 class="task-heading" tabindex="-1">${esc(task.title)}</h2><div class="task-tags"><span class="task-id">${esc(task.code)}</span>${statusTag(task.status)}${task.acceptance === 'pending' ? statusTag('review') : ''}</div>
      <div class="section-heading"><h3>任务目标</h3></div><p class="task-copy">${esc(task.goal)}</p>
      <div class="task-update"><div class="eyebrow">最近进展</div><p>${esc(task.summary)}</p></div>
      ${task.blocker ? `<div class="blocking-callout"><strong>等待确认</strong><br>${esc(task.blocker)}</div>` : ''}
      ${task.children.length ? `<div class="section-heading"><h3>子项</h3><span>${childrenDone} / ${task.children.length} 已完成</span></div><ul class="subtask-list">${task.children.map(child => `<li class="${child.status}">${symbol(child.status)}<span>${esc(child.title)}</span></li>`).join('')}</ul><p class="fine-note">子项展示执行细节，这个 Task 始终按 1 个任务计量。</p>` : ''}
      <div class="section-heading"><h3>${task.verified ? '完成依据' : '验证与记录'}</h3>${task.verified ? '<span>已通过检查</span>' : ''}</div>
      ${task.evidence.length ? `<dl class="evidence-list">${task.evidence.map(evidence => `<div><dt>${esc(evidence.label)}</dt><dd>${esc(evidence.text)}</dd></div>`).join('')}</dl>` : '<p class="task-copy">尚未提交验证结果，完成后由项目侧更新。</p>'}
      <div class="task-meta"><div><small>所属阶段</small><span>${esc(wave.name)}</span></div><div><small>最后上报</small><span>${esc(task.updated)}</span></div></div>
      <div class="detail-end" style="margin-top:28px">示例任务 · 只读查看</div></div>`;
  }

  function renderDetail() {
    const panel = $('#detail-panel');
    if (!visibleProjects().length && state.view === 'home') {
      panel.innerHTML = `<div class="empty-state">${icon('layers')}<h2>选择一个项目</h2><p>项目的阶段、任务和最近进展会显示在这里。</p></div>`;
      return;
    }
    const project = activeProject();
    panel.innerHTML = state.view === 'task' ? taskMarkup(project, state.taskId) : projectMarkup(project);
  }

  function applyRoute(initial = false) {
    let parts;
    try { parts = location.hash.replace(/^#/, '').split('/').map(decodeURIComponent); } catch { parts = []; }
    const oldView = state.view;
    const routeProject = parts[0] === 'project' ? projects.find(p => p.id === parts[1]) : null;
    if (routeProject) {
      state.projectId = routeProject.id;
      state.view = parts[2] === 'task' && routeProject.waves.some(w => w.tasks.some(t => t.id === parts[3])) ? 'task' : 'project';
      state.taskId = state.view === 'task' ? parts[3] : null;
    } else { state.view = 'home'; state.taskId = null; }
    document.body.dataset.view = state.view;
    renderList(); renderDetail();
    $('#detail-panel').scrollTop = 0;
    document.title = state.view === 'home' ? '进度簿 · 项目总览' : `${activeProject().name} · 进度簿`;
    if (!initial && matchMedia('(max-width: 1000px)').matches) {
      requestAnimationFrame(() => {
        window.scrollTo(0, state.view === 'home' ? state.homeScroll : 0);
        if (state.view !== 'home' && oldView !== state.view) $('#detail-panel h2')?.focus({ preventScroll: true });
      });
    }
  }

  function updateFilter(id) {
    state.filter = id;
    const visible = visibleProjects();
    if (visible.length && !visible.some(p => p.id === state.projectId)) state.projectId = visible[0].id;
    if (location.hash) location.hash = '';
    state.view = 'home'; state.taskId = null; document.body.dataset.view = 'home';
    renderList(); renderDetail();
  }

  document.addEventListener('click', event => {
    const link = event.target.closest('a[href^="#"]');
    if (link && state.view === 'home' && link.getAttribute('href').startsWith('#project/')) state.homeScroll = window.scrollY;
    if (link && link.dataset.action !== 'skip') {
      // srcdoc inherits its parent's base URL; set the fragment on this document.
      event.preventDefault();
      const next = link.getAttribute('href');
      if (location.hash === next || (next === '#' && !location.hash)) applyRoute();
      else location.hash = next;
    }
    const filter = event.target.closest('[data-filter]');
    if (filter) {
      const fromSidebar = Boolean(filter.closest('#primary-nav'));
      updateFilter(filter.dataset.filter);
      (fromSidebar ? $('#primary-nav') : $('#filters')).querySelector(`[data-filter="${state.filter}"]`)?.focus({ preventScroll: true });
    }
    const action = event.target.closest('[data-action]')?.dataset.action;
    if (action === 'rules') $('#rules-dialog').showModal();
    if (action === 'close-rules') $('#rules-dialog').close();
    if (action === 'skip') { event.preventDefault(); $('#main-content').focus(); }
    if (action === 'clear-search') { state.query = ''; $('#project-search').value = ''; updateFilter('all'); $('#project-search').focus(); }
    const scenario = event.target.closest('[data-scenario]')?.dataset.scenario;
    if (scenario) {
      state.scenario = scenario;
      $('#offline-banner').hidden = scenario !== 'offline';
      $('#snapshot-label').textContent = scenario === 'offline' ? '离线 · 保留示例快照' : '示例快照 · 今天 14:38';
      document.querySelectorAll('[data-check]').forEach(node => { node.textContent = node.dataset.check === scenario ? '✓' : ''; });
      $('#demo-menu').open = false;
    } else if (!event.target.closest('#demo-menu')) $('#demo-menu').open = false;
    if (event.target === $('#rules-dialog')) {
      const bounds = $('#rules-dialog').getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) $('#rules-dialog').close();
    }
  });
  document.addEventListener('toggle', event => {
    if (event.target.matches?.('details[data-wave]') && event.target.isConnected) {
      const open = state.openWaves.get(event.target.dataset.owner);
      if (event.target.open) open.add(event.target.dataset.wave); else open.delete(event.target.dataset.wave);
    }
  }, true);
  $('#project-search').addEventListener('input', event => {
    state.query = event.target.value;
    const visible = visibleProjects();
    if (visible.length && !visible.some(p => p.id === state.projectId)) state.projectId = visible[0].id;
    if (state.view !== 'home') {
      const next = visible.length ? projectLink(activeProject()) : '#';
      if (location.hash !== next) { location.hash = next; return; }
    }
    applyRoute();
  });
  document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      if (matchMedia('(max-width: 1000px)').matches && state.view !== 'home') { location.hash = ''; setTimeout(() => $('#project-search').focus(), 0); }
      else $('#project-search').focus();
    }
    if (event.key === 'Escape') $('#demo-menu').open = false;
  });
  window.addEventListener('hashchange', () => applyRoute());
  $('#date-label').textContent = dateLabel;
  $('#heading-count').textContent = projects.length;
  fillIcons(); applyRoute(true);
})();
