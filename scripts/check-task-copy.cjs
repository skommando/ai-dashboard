// 验证上报的任务工作要点在窄屏详情中保留换行，并作为安全的纯文本显示。
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');

(async () => {
  const root = path.resolve(__dirname, '..');
  const snapshot = JSON.parse(readFileSync(path.join(root, 'examples/sample-snapshot.json'), 'utf8'));
  const task = snapshot.project.waves[0].tasks[0];
  task.goal = '让各项目稳定上报进度。\n让使用者能够了解具体完成了哪些工作。';
  task.summary = '• 已完成：支持按项目接收完整进度快照，集中展示阶段与任务。\n• 已完成：增加版本检查，旧上报不会覆盖新进展。\n• 待完成：验证异常恢复。<script>window.injected = true</script>';
  const at = new Date().toISOString();
  const project = { ...snapshot.project, id: 'copy-check', revision: 1, observedAt: at, receivedAt: at };
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 375, height: 812 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('http://dashboard.test/**', route => {
      if (route.request().url().includes('/api/v1/projects')) {
        return route.fulfill({ json: { projects: [project], server_time: at } });
      }
      return route.fulfill({ contentType: 'text/html', body: readFileSync(path.join(root, 'web/index.html'), 'utf8') });
    });
    await page.goto(`http://dashboard.test/#project/copy-check/task/${task.id}`);
    await page.locator('.task-heading').waitFor();
    for (const [selector, expected] of [['.task-copy', task.goal], ['.task-update p', task.summary]]) {
      const block = page.locator(selector);
      assert.equal(await block.textContent(), expected);
      assert.equal(await block.evaluate(node => getComputedStyle(node).whiteSpace), 'pre-line', `${selector} must retain reported line breaks`);
      assert.equal(await block.innerText(), expected);
      assert.ok(await block.evaluate(node => node.scrollWidth <= node.clientWidth + 1));
    }
    assert.equal(await page.evaluate(() => window.injected), undefined);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= 376));
    assert.deepEqual(errors, []);
    console.log('Task copy checks passed: multiline goal/work items, escaped text, 375px layout.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
