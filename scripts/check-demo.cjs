const assert = require('node:assert/strict');
const { mkdirSync, writeFileSync } = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const root = path.resolve(__dirname, '..');
const demoUrl = pathToFileURL(path.join(root, 'demo/index.html')).href;
const previewDir = path.join(root, 'demo/previews');
mkdirSync(previewDir, { recursive: true });
const checks = [];
const errors = [];
const externalRequests = [];
function watch(page) {
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (/^https?:/i.test(request.url())) externalRequests.push(request.url()); });
}
async function noOverflow(page, label) {
  const configuredWidth = page.viewportSize().width;
  const result = await page.evaluate(() => {
    const row = [...document.querySelectorAll('.project-row')].find(element => element.getBoundingClientRect().width > 0);
    return {
      layout: innerWidth, viewport: document.documentElement.clientWidth,
      visual: visualViewport?.width, width: document.documentElement.scrollWidth,
      listRight: row?.closest('.project-list')?.getBoundingClientRect().right,
      rowRight: row?.getBoundingClientRect().right,
      offenders: [...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > document.documentElement.clientWidth + 1 && e.getBoundingClientRect().width > 0).map(e => `${e.tagName}.${e.className}`).slice(0, 8),
    };
  });
  assert.ok(Math.abs(result.viewport - configuredWidth) <= 1, `${label}: ${JSON.stringify(result)}`);
  assert.ok(Math.abs(result.visual - configuredWidth) <= 1, `${label}: ${JSON.stringify(result)}`);
  assert.ok(result.width <= configuredWidth + 1, `${label}: ${JSON.stringify(result)}`);
  if (result.rowRight !== undefined) assert.ok(result.rowRight <= result.listRight + 1, `${label}: ${JSON.stringify(result)}`);
  checks.push(`${label}: no horizontal overflow`);
}
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 }, deviceScaleFactor: 1 });
    watch(page);
    await page.goto(demoUrl);
    assert.equal(await page.locator('.project-row').count(), 6);
    assert.match(await page.locator('.metric-ratio').innerText(), /12 \/ 20 Task/);
    await noOverflow(page, 'desktop 1440');
    await page.screenshot({ path: path.join(previewDir, 'desktop.png') });
    checks.push('Desktop overview renders six projects and 12/20 progress');

    await page.getByRole('searchbox').fill('重叠区间');
    assert.equal(await page.locator('.project-row').count(), 1);
    assert.match(await page.locator('.project-row').innerText(), /本地知识库/);
    await page.getByRole('searchbox').fill('<svg onload=alert(1)>');
    assert.equal(await page.locator('.project-row').count(), 0);
    assert.equal(await page.locator('.empty-state h2').first().innerText(), '没有找到项目');
    await page.getByRole('button', { name: '清除筛选', exact: true }).click();
    assert.equal(await page.locator('.project-row').count(), 6);
    checks.push('Search reaches child text, safely handles markup, and clears empty state');

    await page.goto(`${demoUrl}#project/knowledge/task/w2-t5`);
    await page.getByRole('searchbox').fill('账单');
    await page.waitForFunction(() => document.querySelector('.detail-project-heading h2')?.textContent === '账单归档');
    assert.equal(await page.evaluate(() => location.hash), '#project/billing');
    assert.equal(await page.title(), '账单归档 · 进度簿');
    await page.reload();
    assert.equal(await page.locator('.detail-project-heading h2').innerText(), '账单归档');
    checks.push('Search from a deep Task route updates URL and title; reload keeps the displayed project');

    const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
    watch(mobile);
    await mobile.goto(demoUrl);
    await noOverflow(mobile, 'mobile 390 home');
    await mobile.screenshot({ path: path.join(previewDir, 'mobile.png') });
    await mobile.locator('[data-project="knowledge"]').click();
    await mobile.waitForFunction(() => document.body.dataset.view === 'project');
    assert.equal(await mobile.locator('#detail-panel h2').innerText(), '本地知识库');
    assert.equal(await mobile.locator('details[data-wave="w2"]').getAttribute('open'), '');
    await noOverflow(mobile, 'mobile 390 project');
    await mobile.screenshot({ path: path.join(previewDir, 'mobile-project.png') });
    await mobile.locator('[data-task="w2-t5"]').click();
    await mobile.waitForFunction(() => document.body.dataset.view === 'task');
    assert.equal(await mobile.locator('.subtask-list li').count(), 3);
    assert.match(await mobile.locator('.task-copy').innerText(), /原文引用/);
    await noOverflow(mobile, 'mobile 390 task');
    await mobile.screenshot({ path: path.join(previewDir, 'mobile-task.png') });
    await mobile.getByRole('link', { name: '返回项目', exact: true }).click();
    await mobile.waitForFunction(() => document.body.dataset.view === 'project');
    await mobile.getByRole('link', { name: '全部项目', exact: true }).click();
    await mobile.waitForFunction(() => document.body.dataset.view === 'home');
    checks.push('Mobile project → Wave → Task → project → home navigation works');

    await mobile.locator('#filters [data-filter="attention"]').click();
    assert.equal(await mobile.locator('.project-row').count(), 2);
    await mobile.locator('[data-project="photos"]').click();
    await mobile.waitForFunction(() => document.body.dataset.view === 'project');
    assert.match(await mobile.locator('.metric-ratio').innerText(), /100/);
    assert.match(await mobile.locator('.scope-note').innerText(), /验收事项待确认/);
    await mobile.getByRole('link', { name: '全部项目', exact: true }).click();
    await mobile.waitForFunction(() => document.body.dataset.view === 'home');
    assert.equal(await mobile.locator('#filters [data-filter="attention"]').getAttribute('aria-pressed'), 'true');
    assert.equal(await mobile.locator('.project-row').count(), 2);
    checks.push('Acceptance is separate from 100% implementation; filter survives return');

    await mobile.locator('#filters [data-filter="all"]').click();
    await mobile.locator('[data-project="monitor"]').click();
    await mobile.waitForFunction(() => document.body.dataset.view === 'project');
    assert.match(await mobile.locator('.metric-ratio').innerText(), /尚未登记任务/);
    assert.equal(await mobile.locator('.detail-progress').count(), 0);
    assert.match(await mobile.locator('.wave-empty').first().innerText(), /还没有拆分/);
    checks.push('Zero-task project shows unknown progress and outlined Waves');

    await mobile.getByRole('button', { name: '查看进度计算方式', exact: true }).click();
    assert.equal(await mobile.locator('#rules-dialog').isVisible(), true);
    await mobile.getByRole('button', { name: '关闭计算说明', exact: true }).click();
    await mobile.locator('#demo-menu > summary').click();
    await mobile.locator('[data-scenario="offline"]').click();
    assert.equal(await mobile.locator('#offline-banner').isVisible(), true);
    assert.match(await mobile.locator('#snapshot-label').innerText(), /离线/);
    await noOverflow(mobile, 'mobile 390 offline');
    checks.push('Progress explanation and offline scenario work');

    for (const width of [375, 430, 1001]) {
      await mobile.setViewportSize({ width, height: 900 });
      await mobile.goto(demoUrl);
      await noOverflow(mobile, `width ${width} home`);
      await mobile.locator('[data-project="monitor"]').click();
      await mobile.waitForFunction(() => document.body.dataset.view === 'project');
      await noOverflow(mobile, `width ${width} long project name`);
    }

    const preview = await browser.newPage({ viewport: { width: 1100, height: 980 } });
    watch(preview);
    await preview.goto(pathToFileURL(path.join(root, 'demo/mobile.html')).href);
    const embedded = preview.frameLocator('#phone');
    assert.equal(await embedded.locator('.project-row').count(), 6);
    await embedded.locator('[data-project="knowledge"]').click();
    await embedded.locator('.detail-project-heading h2').waitFor({ state: 'visible' });
    assert.equal(await embedded.locator('.detail-project-heading h2').innerText(), '本地知识库');
    await preview.locator('#preview-width').selectOption('375');
    assert.equal(await preview.locator('#phone').evaluate(e => e.clientWidth), 373);
    checks.push('Standalone mobile preview embeds the full interactive page');
    const staticPreview = await browser.newPage({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
    await staticPreview.goto(demoUrl);
    assert.equal(await staticPreview.locator('.static-preview .project-row').count(), 6);
    assert.match(await staticPreview.locator('.static-preview').innerText(), /12 \/ 20/);
    await noOverflow(staticPreview, 'JavaScript-disabled mobile preview');
    checks.push('File viewers without JavaScript can still read the project overview');
    assert.deepEqual(errors, []);
    assert.deepEqual(externalRequests, []);
    checks.push('No JavaScript errors or external HTTP resources');
    const result = { checkedAt: new Date().toISOString(), engine: 'Playwright Chromium', checks, errors, externalRequests, realIPhoneTested: false };
    writeFileSync(path.join(previewDir, 'verification.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
