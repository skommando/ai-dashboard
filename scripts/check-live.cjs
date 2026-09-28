const assert = require('node:assert/strict');
const { readFileSync, mkdirSync, writeFileSync } = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { once } = require('node:events');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');

const root = path.resolve(__dirname, '..');
const previewDir = path.join(root, 'demo/previews/live');
mkdirSync(previewDir, { recursive: true });
const at = '2026-09-28T08:03:00Z';
const task = { id: 'item/one', code: 'API-01', title: '真实任务', status: 'done', verified: true, acceptance: 'not_required', goal: '检查接口', summary: '通过', updatedAt: at, evidence: [{ label: '记录', text: '通过' }], children: [] };
const base = { id: 'project/one', name: '真实项目 <script>alert(1)</script>', shortName: '真实', description: '描述', summary: '正在检查', status: 'review', acceptance: 'pending', category: '工具', glyph: 'book', color: 'sage', currentWave: 'phase/api', waves: [{ id: 'phase/api', name: '接口', defined: true, acceptance: 'not_required', tasks: [task] }], updates: [{ at, tone: 'done', text: '已通过', detail: 'API' }], revision: 1, receivedAt: at, observedAt: at, progress: { done: 1, total: 1, percent: 100, unplannedWaves: 0, pendingAcceptance: 1 } };
const empty = { ...base, id: 'empty', name: '没有阶段的长项目名称用于手机布局验证', shortName: '无阶段', status: 'blocked', currentWave: null, waves: [], progress: { done: 0, total: 0, percent: null, unplannedWaves: 0, pendingAcceptance: 1 } };
const blocked = { ...base, id: 'blocked', name: '阻塞项目', shortName: '阻塞', status: 'blocked', acceptance: 'not_required', progress: { done: 1, total: 1, percent: 100, unplannedWaves: 0, pendingAcceptance: 0 } };
const layout = { ...base, id: 'layout', name: '项目进度看板', shortName: '项目进度看板', summary: '本机与公网查看已上线，上报、鉴权、重启和浏览器检查通过。', status: 'complete', acceptance: 'not_required', receivedAt: '2026-09-28T09:57:00Z', waves: [{ ...base.waves[0], tasks: Array.from({ length: 4 }, (_, index) => ({ ...task, id: `layout-${index}`, acceptance: 'not_required' })) }], progress: { done: 4, total: 4, percent: 100, unplannedWaves: 0, pendingAcceptance: 0 } };
let projects = [base, empty, blocked];
let offline = false;
let apiRequests = 0;
let active = 0;
let peak = 0;
const html = readFileSync(path.join(root, 'web/index.html'));
const server = http.createServer((req, res) => {
  if (req.url === '/api/v1/projects') {
    apiRequests++; active++; peak = Math.max(peak, active);
    setTimeout(() => {
      active--;
      res.setHeader('Content-Type', 'application/json');
      if (offline) { res.writeHead(503); res.end('{"error":"offline"}'); }
      else res.end(JSON.stringify({ projects, server_time: new Date().toISOString() }));
    }, 20);
  } else if (req.url === '/' || req.url.startsWith('/#')) { res.setHeader('Content-Type', 'text/html; charset=utf-8'); res.end(html); }
  else { res.writeHead(404); res.end(); }
});

(async () => {
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const url = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch({ headless: true });
  const errors = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(url);
    await page.locator('.project-row').first().waitFor();
    assert.equal(await page.locator('.project-row').count(), 3);
    projects = [base];
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await page.waitForFunction(() => document.querySelectorAll('.project-row').length === 1);
    assert.equal(await page.locator('#heading-count').innerText(), '1');
    projects = [base, empty, blocked];
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await page.waitForFunction(() => document.querySelectorAll('.project-row').length === 3);
    await page.locator('#filters [data-filter="attention"]').focus();
    const refreshed = page.waitForResponse(response => response.url().endsWith('/api/v1/projects'));
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await refreshed;
    await page.waitForTimeout(30);
    assert.equal(await page.evaluate(() => document.activeElement?.dataset?.filter), 'attention');
    await page.goto(`${url}#project/%ZZ`);
    await page.waitForFunction(() => location.hash === '');
    assert.equal(await page.evaluate(() => document.body.dataset.view), 'home');
    assert.equal(await page.locator('#demo-menu').count(), 0);
    assert.equal(await page.locator('script[src]').count(), 0);
    assert.equal(await page.locator('img[src=x]').count(), 0);
    assert.match(await page.locator('.project-list').innerText(), /真实项目 <script>alert\(1\)<\/script>/);
    const reviewColor = await page.locator('.project-row[data-status="review"] .status-tag').evaluate(node => getComputedStyle(node).color);
    const reviewTrack = await page.locator('.project-row[data-status="review"] progress').evaluate(node => getComputedStyle(node).color);
    assert.equal(reviewTrack, reviewColor);
    const blockedColor = await page.locator('[data-project="blocked"] .status-tag').evaluate(node => getComputedStyle(node).color);
    const blockedTrack = await page.locator('[data-project="blocked"] progress').evaluate(node => getComputedStyle(node).color);
    assert.equal(blockedTrack, blockedColor);
    await page.screenshot({ path: path.join(previewDir, 'live-desktop.png') });
    await page.goto(`${url}#project/${encodeURIComponent(base.id)}/task/${encodeURIComponent(task.id)}`);
    await page.locator('.task-heading').waitFor();
    assert.equal(await page.locator('.task-heading').innerText(), '真实任务');
    assert.doesNotMatch(await page.locator('.detail-content').innerText(), /时间未知/);
    await page.locator('.back-link').first().click();
    const detailTrack = await page.locator('.detail-progress').evaluate(node => getComputedStyle(node).color);
    assert.equal(detailTrack, reviewColor);
    const incompleteTask = { ...task, status: 'todo', verified: false, evidence: [], acceptance: 'not_required' };
    const pendingWave = { ...base.waves[0], acceptance: 'pending', tasks: [incompleteTask] };
    const undefinedWave = { id: 'future', name: '未来阶段', defined: false, acceptance: 'not_required', tasks: [] };
    const cases = [
      { name: '阶段 0/1 待验收', project: { ...base, acceptance: 'not_required', waves: [pendingWave] }, ready: '0 / 1 Task|验收待确认', forbidden: /实施完成/ },
      { name: '项目 0/1 待验收', project: { ...base, waves: [{ ...pendingWave, acceptance: 'not_required' }] }, ready: '0 / 1 Task|当前阶段', forbidden: /实施工作已完成/ },
      { name: '阶段 1/1 待验收', project: { ...base, acceptance: 'not_required', waves: [{ ...base.waves[0], acceptance: 'pending' }] }, ready: '1 / 1 Task|实施完成 · 待验收', expected: /实施完成 · 待验收/ },
      { name: '项目已规划 100% 待验收', project: base, ready: '1 / 1 Task|当前阶段', expected: /实施工作已完成/ },
      { name: '已规划 100% 但未来待细化', project: { ...base, waves: [base.waves[0], undefinedWave] }, ready: '1 / 1 Task|未来阶段', forbidden: /实施工作已完成/ },
    ];
    for (const scenario of cases) {
      projects = [scenario.project];
      const reply = page.waitForResponse(response => response.url().endsWith('/api/v1/projects'));
      await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
      await reply;
      await page.waitForFunction(marker => {
        const [count, label] = marker.split('|');
        const detail = document.querySelector('.detail-content')?.textContent || '';
        return detail.includes(count) && detail.includes(label);
      }, scenario.ready);
      const detail = await page.locator('.detail-content').innerText();
      if (scenario.forbidden) assert.doesNotMatch(detail, scenario.forbidden, scenario.name);
      if (scenario.expected) assert.match(detail, scenario.expected, scenario.name);
      assert.match(detail, /待验收|验收事项待确认/, scenario.name);
    }
    projects = [base, empty, blocked];
    const resetReply = page.waitForResponse(response => response.url().endsWith('/api/v1/projects'));
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await resetReply;
    await page.getByRole('searchbox').fill('真实项目');
    offline = true;
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await page.locator('#offline-banner:visible').waitFor();
    assert.equal(await page.evaluate(() => document.body.dataset.connection), 'offline');
    assert.equal(await page.locator('.project-row').count(), 1);
    assert.match(await page.locator('#snapshot-label').innerText(), /离线/);
    offline = false;
    projects = [base, empty, blocked];
    await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, value: true }); document.dispatchEvent(new Event('visibilitychange')); Object.defineProperty(document, 'hidden', { configurable: true, value: false }); document.dispatchEvent(new Event('visibilitychange')); });
    await page.locator('#offline-banner').waitFor({ state: 'hidden' });
    assert.equal(await page.locator('.project-row').count(), 1);
    assert.equal(await page.evaluate(() => location.hash), `#project/${encodeURIComponent(base.id)}`);
    assert.match(await page.locator('#snapshot-label').innerText(), /最后上报/);
    assert.doesNotMatch(await page.locator('#snapshot-label').innerText(), /刚刚/);
    await page.goto(`${url}#project/${encodeURIComponent(base.id)}/task/${encodeURIComponent(task.id)}`);
    await page.locator('.task-heading').waitFor();
    projects = [{ ...base, waves: [{ ...base.waves[0], tasks: [] }], progress: { done: 0, total: 0, percent: null, unplannedWaves: 0, pendingAcceptance: 1 } }, empty, blocked];
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await page.waitForFunction(() => location.hash === '#project/project%2Fone');
    assert.equal(await page.locator('.detail-project-heading h2').innerText(), base.name);
    projects = [empty];
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await page.waitForFunction(() => document.body.dataset.view === 'home');
    assert.equal(await page.evaluate(() => location.hash), '');
    await page.getByRole('searchbox').fill('');
    assert.equal(await page.locator('.project-row').count(), 1);
    assert.equal(await page.locator('.project-row[data-status="blocked"] progress').count(), 0);
    projects = [];
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await page.locator('.project-row').waitFor({ state: 'detached' });
    assert.match(await page.locator('#project-list').innerText(), /尚无项目/);
    const mobile = await browser.newPage({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true, timezoneId: 'Asia/Shanghai' });
    mobile.on('pageerror', error => errors.push(error.message));
    projects = [base, empty, blocked];
    await mobile.goto(url);
    await mobile.locator('.project-row').first().waitFor();
    await mobile.setViewportSize({ width: 375, height: 600 });
    await mobile.evaluate(() => window.scrollTo(0, 120));
    const scrollBefore = await mobile.evaluate(() => window.scrollY);
    assert.ok(scrollBefore > 0);
    const mobileRefresh = mobile.waitForResponse(response => response.url().endsWith('/api/v1/projects'));
    await mobile.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await mobileRefresh;
    await mobile.waitForTimeout(30);
    assert.ok(Math.abs(await mobile.evaluate(() => window.scrollY) - scrollBefore) <= 1);
    await mobile.setViewportSize({ width: 375, height: 812 });
    await mobile.evaluate(() => window.scrollTo(0, 0));
    const width = await mobile.evaluate(() => ({ page: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth, visual: visualViewport.width, layout: innerWidth }));
    assert.ok(width.page <= 376 && width.viewport === 375 && Math.abs(width.visual - 375) <= 1, JSON.stringify(width));
    await mobile.screenshot({ path: path.join(previewDir, 'live-mobile.png') });
    await mobile.locator('[data-project="empty"]').click();
    await mobile.locator('.detail-project-heading h2').waitFor();
    assert.equal(await mobile.locator('details[data-wave]').count(), 0);
    assert.match(await mobile.locator('.wave-list').innerText(), /尚未登记阶段/);
    await mobile.screenshot({ path: path.join(previewDir, 'live-mobile-empty-wave.png') });
    const baselinePeak = peak;
    assert.equal(baselinePeak, 1);
    projects = [layout];
    for (const viewportWidth of [375, 390, 430]) {
      await mobile.setViewportSize({ width: viewportWidth, height: 812 });
      await mobile.goto(url);
      await mobile.locator('[data-project="layout"]').waitFor();
      assert.equal(await mobile.locator('.row-updated').innerText(), '9/28 17:57');
      const geometry = await mobile.evaluate(() => {
        const row = document.querySelector('.project-row');
        const list = document.querySelector('.project-list');
        const summary = row.querySelector('.row-summary');
        return { page: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth,
          visual: visualViewport.width, layout: innerWidth, rowRight: row.getBoundingClientRect().right,
          listRight: list.getBoundingClientRect().right, summaryWidth: summary.clientWidth,
          summaryScrollWidth: summary.scrollWidth, overflow: getComputedStyle(summary).textOverflow };
      });
      assert.equal(geometry.viewport, viewportWidth, JSON.stringify(geometry));
      assert.ok(Math.abs(geometry.visual - viewportWidth) <= 1, JSON.stringify(geometry));
      assert.ok(geometry.page <= viewportWidth + 1, JSON.stringify(geometry));
      assert.ok(geometry.rowRight <= geometry.listRight + 1, JSON.stringify(geometry));
      assert.equal(geometry.overflow, 'ellipsis');
      if (viewportWidth <= 390) assert.ok(geometry.summaryScrollWidth > geometry.summaryWidth, JSON.stringify(geometry));
      if (viewportWidth === 375) await mobile.screenshot({ path: path.join(previewDir, 'live-mobile-layout-375.png') });
    }
    await mobile.close();
    await page.goto(url);
    await page.locator('[data-project="layout"]').waitFor();
    const desktopGeometry = await page.evaluate(() => ({
      page: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth,
      rowRight: document.querySelector('.project-row').getBoundingClientRect().right,
      listRight: document.querySelector('.project-list').getBoundingClientRect().right,
    }));
    assert.ok(desktopGeometry.page <= desktopGeometry.viewport + 1, JSON.stringify(desktopGeometry));
    assert.ok(desktopGeometry.rowRight <= desktopGeometry.listRight + 1, JSON.stringify(desktopGeometry));
    assert.deepEqual(errors, []);
    writeFileSync(path.join(previewDir, 'verification.json'), JSON.stringify({ checkedAt: new Date().toISOString(), engine: 'Playwright Chromium', apiRequests, baselinePeakConcurrency: baselinePeak, totalPeakConcurrency: peak, mobileWidth: width, realIPhoneTested: false }, null, 2));
    console.log(`Live browser checks passed; ${apiRequests} API requests, baseline peak concurrency ${baselinePeak}, mobile width ${width.page}/${width.viewport}`);
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
