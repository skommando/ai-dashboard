const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { once } = require('node:events');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');

const loginHtml = readFileSync(path.join(__dirname, '../web/login.html'), 'utf8');
const server = http.createServer(async (request, response) => {
  const pathname = new URL(request.url, 'http://127.0.0.1').pathname;
  if (pathname === '/login') {
    response.setHeader('Content-Type', 'text/html; charset=utf-8');
    response.end(loginHtml);
  } else if (pathname === '/api/v1/login' && request.method === 'POST') {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    const payload = JSON.parse(Buffer.concat(chunks).toString());
    if (payload.username === 'test-viewer' && payload.password === 'LongTestPassphrase5!') {
      // Backend tests check Secure; the local HTTP fixture checks browser persistence.
      response.setHeader('Set-Cookie', '__Host-ai_dashboard_session=test-session; Max-Age=15552000; Path=/; Secure; HttpOnly; SameSite=Lax');
      response.setHeader('Content-Type', 'application/json');
      response.end('{"status":"ok"}');
    } else {
      response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('功能未开发');
    }
  } else if (pathname === '/') {
    if (request.headers.cookie?.includes('__Host-ai_dashboard_session=test-session')) {
      response.setHeader('Content-Type', 'text/html; charset=utf-8');
      response.end('<h1>项目总览</h1>');
    } else {
      response.writeHead(303, { Location: '/login' });
      response.end();
    }
  } else { response.writeHead(404); response.end(); }
});

(async () => {
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 375, height: 812 } });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`${base}/#project/demo/task/one`);
    await page.locator('h1').waitFor();
    assert.equal(await page.locator('h1').innerText(), '查看项目进度');
    const geometry = await page.evaluate(() => ({ page: document.documentElement.scrollWidth,
      viewport: document.documentElement.clientWidth, button: document.querySelector('button').getBoundingClientRect().height }));
    assert.equal(geometry.viewport, 375);
    assert.ok(geometry.page <= 375 && geometry.button >= 44, JSON.stringify(geometry));
    await page.locator('#username').fill('wrong');
    await page.locator('#password').fill('LongTestPassphrase5!');
    await page.locator('button').click();
    await page.waitForFunction(() => document.querySelector('#error')?.textContent === '功能未开发');
    assert.equal(await page.locator('#error').innerText(), '功能未开发');
    if (process.env.LOGIN_CHECK_IMAGE_PATH) await page.screenshot({ path: process.env.LOGIN_CHECK_IMAGE_PATH });
    await page.locator('#username').fill('test-viewer');
    await page.locator('button').click();
    await page.locator('h1').filter({ hasText: '项目总览' }).waitFor();
    assert.ok(page.url().endsWith('/#project/demo/task/one'), page.url());
    const state = await context.storageState();
    const reopened = await browser.newContext({ storageState: state, viewport: { width: 375, height: 812 } });
    const later = await reopened.newPage();
    await later.goto(base);
    assert.equal(await later.locator('h1').innerText(), '项目总览');
    assert.deepEqual(errors, []);
    console.log('Login browser checks passed: 375px, uniform failure, return link and stored session.');
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
