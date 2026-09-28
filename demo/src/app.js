(function () {
  'use strict';
  const live = DashboardConfig.mode === 'live';
  let projects = DashboardConfig.projects || [];
  const dateLabel = live ? new Date().toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric', weekday: 'long' }) : DashboardConfig.dateLabel;
  const { summarize, matches } = ProgressModel;
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
  const localTime = value => {
    if (!value || Number.isNaN(Date.parse(value))) return '时间未知';
    const at = new Date(value);
    return at.toLocaleString('zh-CN', { ...(at.getFullYear() === new Date().getFullYear() ? {} : { year: 'numeric' }), month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };
  const reported = project => live ? localTime(project.receivedAt) : project.updated;
  let connection = 'loading';
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
  const state = { filter: 'all', query: '', projectId: projects[0]?.id || null, view: 'home', taskId: null, scenario: 'online', homeScroll: 0, openWaves: new Map() };
  projects.forEach(project => state.openWaves.set(project.id, new Set([project.currentWave])));
  const visibleProjects = () => projects.filter(project => filters.find(f => f.id === state.filter).match(project) && matches(project, state.query))
    .sort((a, b) => Number(attention(b)) - Number(attention(a)));
  const activeProject = () => projects.find(p => p.id === state.projectId) || projects[0] || null;
  const projectLink = project => `#project/${encodeURIComponent(project.id)}`;
  const taskLink = (project, task) => `${projectLink(project)}/task/${encodeURIComponent(task.id)}`;
  const symbol = status => `<span class="task-symbol ${esc(status)}" aria-hidden="true">${status === 'done' ? icon('check') : ['blocked', 'waiting', 'failed'].includes(status) ? icon('pause') : ''}</span>`;
  const progress = (summary, label, className = '', status = '') => summary.total
    ? `<progress class="${esc(className)} ${esc(status)}" value="${summary.done}" max="${summary.total}" aria-label="${esc(label)}：${summary.done}/${summary.total} Task 已完成"></progress>`
    : '<span class="unplanned-track" aria-label="尚未登记任务"></span>';

  function renderNavigation() {
    $('#side-project-count').textContent = projects.length;
    $('#heading-count').textContent = projects.length;
    $('#primary-nav').innerHTML = filters.filter(f => f.id !== 'active').map(f => `<button type="button" class="nav-button ${state.filter === f.id ? 'active' : ''}" data-filter="${f.id}" aria-pressed="${state.filter === f.id}">${icon(f.icon)}<span>${f.nav}</span><span class="nav-count">${projects.filter(f.match).length}</span></button>`).join('');
    $('#side-projects').innerHTML = projects.map(project => `<a class="side-project ${state.projectId === project.id ? 'selected' : ''}" href="${projectLink(project)}"><span class="tiny-dot ${esc(project.status)}" aria-hidden="true"></span>${esc(project.shortName || project.name)}</a>`).join('');
    $('#filters').innerHTML = filters.map(f => `<button type="button" class="filter-button ${state.filter === f.id ? 'active' : ''}" data-filter="${f.id}" aria-pressed="${state.filter === f.id}">${f.name}<span>${projects.filter(f.match).length}</span></button>`).join('');
    $('#overview-summary').textContent = `${projects.filter(p => p.status === 'active').length} 个推进中，${projects.filter(attention).length} 个需关注`;
  }

  function renderList() {
    const scroll = $('#project-scroll').scrollTop;
    const visible = visibleProjects();
    $('#list-caption').textContent = state.query ? `找到 ${visible.length} 个项目` : `${visible.length} 个项目${state.filter === 'all' ? ' · 需关注优先' : ''}`;
    $('#project-list').innerHTML = visible.length ? visible.map(project => {
      const summary = summarize(project);
      const waveIndex = project.waves.findIndex(w => w.id === project.currentWave);
      const wave = project.waves[waveIndex];
      return `<a role="listitem" class="project-row ${state.projectId === project.id ? 'selected' : ''}" href="${projectLink(project)}" data-project="${esc(project.id)}" data-status="${esc(project.status)}" aria-label="查看${esc(project.name)}，${esc(statusLabels[project.status] || project.status)}，${summary.total ? `${summary.done}/${summary.total} Task` : '尚未登记任务'}">
        <div class="row-top"><span class="project-icon ${esc(project.color)}">${icon(project.glyph)}</span><div class="row-identity"><strong>${esc(project.name)}</strong><span class="row-wave">${wave ? `<span class="wave-code">WAVE ${String(waveIndex + 1).padStart(2, '0')}</span>${esc(wave.name)}` : '暂无当前阶段'}</span></div>${statusTag(project.status)}</div>
        <p class="row-summary">${esc(project.summary)}</p>
        <div class="row-bottom">${progress(summary, project.name, '', project.status)}<span class="row-count">${summary.total ? `<b>${summary.done}</b> / ${summary.total}` : '待拆分'}</span><span class="row-percent">${summary.percent === null ? '—' : `${summary.percent}%`}</span><span class="row-updated">${esc(reported(project))}</span></div>
      </a>`;
    }).join('') : `<div class="empty-state" role="listitem">${icon('search')}<h2>${live && !projects.length ? connection === 'loading' ? '正在读取项目' : connection === 'offline' ? '无法读取项目' : '尚无项目' : '没有找到项目'}</h2><p>${state.query ? `没有与“${esc(state.query)}”匹配的项目或任务。` : live && !projects.length ? connection === 'offline' ? '连接恢复后会自动重试。' : '项目完成首次上报后会显示在这里。' : '这个筛选条件下暂时没有项目。'}</p>${projects.length ? '<button class="text-button" type="button" data-action="clear-search">清除筛选</button>' : ''}</div>`;
    $('#project-scroll').scrollTop = scroll;
    renderNavigation();
  }

  function waveMarkup(project, wave, index) {
    const summary = summarize({ waves: [wave] });
    const current = project.currentWave === wave.id;
    const complete = summary.total > 0 && summary.done === summary.total;
    const expanded = state.openWaves.get(project.id)?.has(wave.id);
    const caption = wave.acceptance === 'pending' ? complete ? '实施完成 · 待验收' : '验收待确认' : current ? '当前阶段' : wave.defined === false ? '后续计划' : complete ? '已完成' : '尚未开始';
    return `<details class="wave ${current ? 'current' : ''}" data-wave="${esc(wave.id)}" data-owner="${esc(project.id)}" ${expanded ? 'open' : ''}>
      <summary aria-label="Wave ${index + 1} ${esc(wave.name)} ${summary.total ? `${summary.done}/${summary.total}` : '待细化'}"><span class="wave-number ${current ? 'current' : complete ? 'complete' : ''} ${wave.defined === false ? 'undefined' : ''}">${complete && !current ? icon('check') : String(index + 1).padStart(2, '0')}</span><span class="wave-title"><strong>${esc(wave.name)}</strong><small>${caption}</small></span><span class="wave-count ${summary.total ? '' : 'text'}">${summary.total ? `${summary.done} / ${summary.total}` : '待细化'}</span><span class="wave-chevron">${icon('chevronRight')}</span></summary>
      <div class="wave-body">${wave.tasks.length ? wave.tasks.map(task => `<a class="task-row" data-task="${esc(task.id)}" data-status="${esc(task.status)}" href="${taskLink(project, task)}" aria-label="查看任务：${esc(task.title)}，${esc(statusLabels[task.status] || task.status)}">${symbol(task.status)}<span class="task-name">${esc(task.title)}${task.status === 'active' ? '<small class="task-hint">正在推进</small>' : task.status === 'waiting' ? '<small class="task-hint">等待确认</small>' : ''}</span><span class="task-code">${esc(task.code)}</span>${icon('chevronRight', 'task-chevron')}</a>`).join('') : '<div class="wave-empty">这个阶段还没有拆分 Task，暂不计入已规划范围。</div>'}</div>
    </details>`;
  }

  function projectMarkup(project) {
    const summary = summarize(project);
    const ongoing = project.waves.flatMap(w => w.tasks).find(t => ['active', 'waiting', 'blocked'].includes(t.status));
    const completeScope = summary.total > 0 && summary.done === summary.total && summary.unplannedWaves === 0;
    const focus = ongoing ? `<a class="focus-note ${esc(project.status)}" href="${taskLink(project, ongoing)}"><span class="focus-label">${project.status === 'blocked' ? '需要你确认' : '当前在做'}${icon('arrowUpRight')}</span><strong>${esc(project.blocker || ongoing.title)}</strong></a>`
      : project.status === 'blocked' && project.blocker ? `<div class="focus-note blocked"><span class="focus-label">当前阻塞</span><strong>${esc(project.blocker)}</strong></div>`
      : summary.pendingAcceptance ? `<div class="focus-note review"><span class="focus-label">验收事项待确认</span><strong>${completeScope ? '实施工作已完成，可以查看本阶段的交付效果。' : '请查看待确认的验收事项与当前任务。'}</strong></div>` : '';
    return `<div class="detail-nav"><span class="desktop-detail-label">项目详情</span><a class="back-link mobile-back" href="#">${icon('arrowLeft')}全部项目</a><span class="detail-nav-end">${icon('eye')}只读</span></div>
      <div class="detail-content"><div class="detail-project-heading"><span class="project-icon ${esc(project.color)}">${icon(project.glyph)}</span><div class="detail-title-wrap"><h2 tabindex="-1">${esc(project.name)}</h2><span class="category-label">${esc(project.category)}</span></div>${statusTag(project.status)}</div>
      <p class="detail-description">${esc(project.description)}</p>
      <div class="metric-top"><span>已规划范围</span><div class="metric-ratio"><span>${summary.total ? `${summary.done} / ${summary.total} Task` : '尚未登记任务'}</span><strong>${summary.percent === null ? '—' : `${summary.percent}<small>%</small>`}</strong></div></div>
      ${progress(summary, project.name, 'detail-progress', project.status)}
      <div class="scope-note ${summary.pendingAcceptance ? 'pending' : ''}">${icon(summary.pendingAcceptance ? 'clock' : 'layers')}<span>${summary.pendingAcceptance ? `${summary.pendingAcceptance} 个验收事项待确认；Task 完成度按已验证任务计算。${summary.unplannedWaves ? `另有 ${summary.unplannedWaves} 个 Wave 待细化。` : ''}` : summary.unplannedWaves ? `另有 ${summary.unplannedWaves} 个 Wave 待细化，以上仅统计已规划 Task。` : project.status === 'complete' ? '全部任务已完成，交付检查已通过。' : '按 Task 等权计量，子项不增加任务总数。'}</span></div>
      ${focus}
      <div class="section-heading"><h3>阶段与任务</h3><span>${String(project.waves.length).padStart(2, '0')} WAVES</span></div>
      <div class="wave-list">${project.waves.length ? project.waves.map((wave, index) => waveMarkup(project, wave, index)).join('') : '<div class="wave-empty">尚未登记阶段，项目上报后会在这里显示。</div>'}</div>
      <div class="section-heading"><h3>最近进展</h3>${live ? '' : '<span>示例记录</span>'}</div><ol class="activity-list">${project.updates.map(update => `<li><time>${esc(live ? localTime(update.at) : update.time)}</time><div><strong>${esc(update.text)}</strong><small>${esc(update.detail)}</small></div></li>`).join('')}</ol>
      <div class="detail-end">最后上报 · ${esc(live ? localTime(project.receivedAt) : project.updatedAt)}</div></div>`;
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
      ${task.children.length ? `<div class="section-heading"><h3>子项</h3><span>${childrenDone} / ${task.children.length} 已完成</span></div><ul class="subtask-list">${task.children.map(child => `<li class="${esc(child.status)}">${symbol(child.status)}<span>${esc(child.title)}</span></li>`).join('')}</ul><p class="fine-note">子项展示执行细节，这个 Task 始终按 1 个任务计量。</p>` : ''}
      <div class="section-heading"><h3>${task.verified ? '完成依据' : '验证与记录'}</h3>${task.verified ? '<span>已通过检查</span>' : ''}</div>
      ${task.evidence.length ? `<dl class="evidence-list">${task.evidence.map(evidence => `<div><dt>${esc(evidence.label)}</dt><dd>${esc(evidence.text)}</dd></div>`).join('')}</dl>` : '<p class="task-copy">尚未提交验证结果，完成后由项目侧更新。</p>'}
      <div class="task-meta"><div><small>所属阶段</small><span>${esc(wave.name)}</span></div><div><small>${live ? '任务更新' : '最后上报'}</small><span>${esc(live ? localTime(task.updatedAt) : task.updated)}</span></div></div>
      <div class="detail-end" style="margin-top:28px">${live ? '项目上报 · ' : '示例任务 · '}只读查看</div></div>`;
  }

  function renderDetail() {
    const panel = $('#detail-panel');
    if (!activeProject() || (!visibleProjects().length && state.view === 'home')) {
      panel.innerHTML = `<div class="empty-state">${icon('layers')}<h2>选择一个项目</h2><p>项目的阶段、任务和最近进展会显示在这里。</p></div>`;
      return;
    }
    const project = activeProject();
    panel.innerHTML = state.view === 'task' ? taskMarkup(project, state.taskId) : projectMarkup(project);
  }

  function applyRoute(initial = false, dataRefresh = false) {
    let parts;
    try { parts = location.hash.replace(/^#/, '').split('/').map(decodeURIComponent); } catch { parts = []; }
    const oldView = state.view;
    const detailScroll = $('#detail-panel').scrollTop;
    const focused = dataRefresh ? document.activeElement : null;
    const focusScope = focused?.closest?.('#filters,#primary-nav,#side-projects,#project-list,#detail-panel');
    const focusKey = focusScope && focused !== focusScope ? focused.dataset.filter ? ['filter', focused.dataset.filter]
      : focused.dataset.project ? ['project', focused.dataset.project]
      : focused.dataset.task ? ['task', focused.dataset.task]
      : focused.closest('details[data-wave]') && focused.tagName === 'SUMMARY' ? ['wave', focused.closest('details[data-wave]').dataset.wave]
      : focused.getAttribute('href') ? ['href', focused.getAttribute('href')]
      : focused.tagName === 'H2' ? ['heading', ''] : null : null;
    const routeProject = parts[0] === 'project' ? projects.find(p => p.id === parts[1]) : null;
    if (routeProject) {
      state.projectId = routeProject.id;
      state.view = parts[2] === 'task' && routeProject.waves.some(w => w.tasks.some(t => t.id === parts[3])) ? 'task' : 'project';
      state.taskId = state.view === 'task' ? parts[3] : null;
    } else { state.view = 'home'; state.taskId = null; }
    if (live && connection === 'online' && location.hash.startsWith('#project/')) {
      const canonical = routeProject ? state.view === 'task' ? taskLink(routeProject, routeProject.waves.flatMap(w => w.tasks).find(t => t.id === state.taskId)) : projectLink(routeProject) : '';
      if (location.hash !== canonical) history.replaceState(null, '', `${location.pathname}${location.search}${canonical}`);
    }
    if (state.view === 'home' && !visibleProjects().some(p => p.id === state.projectId)) state.projectId = visibleProjects()[0]?.id || null;
    document.body.dataset.view = state.view;
    renderList(); renderDetail();
    $('#detail-panel').scrollTop = dataRefresh ? detailScroll : 0;
    if (focusKey) {
      const [key, value] = focusKey;
      const candidates = key === 'heading' ? focusScope.querySelectorAll('h2') : focusScope.querySelectorAll(key === 'wave' ? 'details[data-wave] > summary' : `[data-${key}], [href]`);
      const replacement = [...candidates].find(node => key === 'wave' ? node.parentElement.dataset.wave === value : key === 'href' ? node.getAttribute('href') === value : node.dataset[key] === value);
      (replacement || $('#project-search')).focus({ preventScroll: true });
    }
    document.title = state.view === 'home' ? '进度簿 · 项目总览' : `${activeProject()?.name || '项目'} · 进度簿`;
    if (!initial && !dataRefresh && matchMedia('(max-width: 1000px)').matches) {
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
    if (event.target === $('#rules-dialog')) {
      const bounds = $('#rules-dialog').getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) $('#rules-dialog').close();
    }
  });
  document.addEventListener('toggle', event => {
    if (event.target.matches?.('details[data-wave]') && event.target.isConnected) {
      const open = state.openWaves.get(event.target.dataset.owner);
      if (!open) return;
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
  });
  window.addEventListener('hashchange', () => applyRoute());
  $('#date-label').textContent = dateLabel;
  fillIcons(); applyRoute(true);
  if (live) LiveFeed.createLiveFeed({ onState: snapshot => {
    connection = snapshot.status;
    document.body.dataset.connection = connection;
    projects = snapshot.projects;
    projects.forEach(project => {
      if (!state.openWaves.has(project.id)) state.openWaves.set(project.id, new Set(project.currentWave ? [project.currentWave] : []));
      const open = state.openWaves.get(project.id);
      for (const id of open) if (!project.waves.some(wave => wave.id === id)) open.delete(id);
    });
    for (const id of state.openWaves.keys()) if (!projects.some(project => project.id === id)) state.openWaves.delete(id);
    const latest = projects.map(project => project.receivedAt).filter(Boolean).sort((a, b) => Date.parse(a) - Date.parse(b)).at(-1);
    $('#snapshot-label').textContent = connection === 'offline' ? latest ? `离线 · 最后上报 ${localTime(latest)}` : '离线 · 无可用项目数据' : latest ? `最后上报 ${localTime(latest)}` : '尚无项目上报';
    $('#offline-banner').hidden = connection !== 'offline';
    if (connection === 'offline') $('#offline-banner div > span').textContent = latest ? `保留最后一次读取的数据，最近上报于 ${localTime(latest)}。连接恢复后会自动重试。` : '无法读取当前数据，连接恢复后会自动重试。';
    applyRoute(false, true);
  } }).start();
})();
