const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { once } = require('node:events');
const { adaptResponse, summarize } = require('../demo/src/model.js');
const { existsSync } = require('node:fs');
const livePath = require('node:path').join(__dirname, '../demo/src/live.js');
const { createLiveFeed } = existsSync(livePath) ? require(livePath) : {};

const task = { id: 'task/arbitrary', code: 'API-01', title: '<b>真实任务</b>', status: 'done', verified: true, acceptance: 'pending', goal: '', summary: '', updatedAt: '2026-09-28T08:01:00Z', evidence: [{ label: '检查', text: '通过' }], children: [] };
const project = { id: 'project/one', name: '<img src=x>', shortName: '一', description: '', summary: '真实进展', status: 'review', acceptance: 'pending', category: '', glyph: 'book', color: 'sage', currentWave: 'phase/api', waves: [{ id: 'phase/api', name: 'API', defined: true, acceptance: 'not_required', tasks: [task] }], updates: [{ at: '2026-09-28T08:02:00Z', tone: 'done', text: '已检查', detail: 'API-01' }], revision: 4, receivedAt: '2026-09-28T08:03:00Z', observedAt: '2026-09-28T08:00:00Z', progress: { done: 1, total: 1, percent: 100, unplannedWaves: 0, pendingAcceptance: 2 } };

test('adaptResponse uses receivedAt and preserves opaque IDs, task evidence, and zero-wave projects', () => {
  assert.equal(typeof adaptResponse, 'function', 'API 数据适配尚未实现');
  const [actual, empty] = adaptResponse({ projects: [project, { ...project, id: 'empty', currentWave: null, waves: [], progress: { done: 0, total: 0, percent: null, unplannedWaves: 0, pendingAcceptance: 1 } }], server_time: '2026-09-28T09:00:00Z' });
  assert.equal(actual.receivedAt, '2026-09-28T08:03:00Z');
  assert.equal(actual.waves[0].id, 'phase/api');
  assert.equal(actual.waves[0].tasks[0].updatedAt, '2026-09-28T08:01:00Z');
  assert.equal(actual.updates[0].at, '2026-09-28T08:02:00Z');
  assert.deepEqual(summarize(actual), project.progress);
  assert.equal(empty.currentWave, null);
  assert.equal(empty.waves.length, 0);
  assert.equal(summarize(empty).percent, null);
});

test('adaptResponse rejects malformed API payload rather than treating it as an empty workspace', () => {
  assert.equal(typeof adaptResponse, 'function', 'API 数据适配尚未实现');
  assert.throws(() => adaptResponse({ projects: null }), /projects/);
  assert.throws(() => adaptResponse({ projects: [], server_time: 'bad' }), /server_time/);
});

test('live feed reads real HTTP snapshots, marks errors offline, and resumes on visibility without concurrent requests', async () => {
  assert.equal(typeof createLiveFeed, 'function', '真实请求生命周期尚未实现');
  let response = { projects: [project], server_time: '2026-09-28T09:00:00Z' };
  let fail = false;
  let requests = 0;
  let concurrent = 0;
  let peak = 0;
  const server = http.createServer((req, res) => {
    requests++; concurrent++; peak = Math.max(peak, concurrent);
    setTimeout(() => {
      concurrent--;
      res.setHeader('Content-Type', 'application/json');
      res.setHeader('Cache-Control', 'no-store');
      if (fail) { res.writeHead(503); res.end('{"error":"unavailable"}'); }
      else res.end(JSON.stringify(response));
    }, 20);
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const events = [];
  const listeners = new Map();
  const visibility = { hidden: false, addEventListener: (name, callback) => listeners.set(name, callback), removeEventListener: name => listeners.delete(name) };
  const feed = createLiveFeed({ url: `http://127.0.0.1:${server.address().port}/api/v1/projects`, visibility, intervalMs: 40, timeoutMs: 200, onState: state => events.push(state) });
  try {
    feed.start();
    await waitFor(() => events.some(e => e.status === 'online'));
    assert.equal(events.at(-1).projects[0].id, 'project/one');
    assert.equal(events.at(-1).projects[0].receivedAt, '2026-09-28T08:03:00Z');
    fail = true;
    await waitFor(() => events.some(e => e.status === 'offline'));
    assert.equal(events.at(-1).projects[0].id, 'project/one');
    visibility.hidden = true;
    listeners.get('visibilitychange')();
    await new Promise(resolve => setTimeout(resolve, 90));
    const whileHidden = requests;
    await new Promise(resolve => setTimeout(resolve, 90));
    assert.equal(requests, whileHidden);
    fail = false;
    response = { projects: [], server_time: '2026-09-28T09:01:00Z' };
    visibility.hidden = false;
    listeners.get('visibilitychange')();
    await waitFor(() => events.at(-1)?.status === 'online' && events.at(-1).projects.length === 0);
    assert.equal(peak, 1);
  } finally { feed.stop(); await new Promise(resolve => server.close(resolve)); }
});

test('an unanswered API request times out, reports offline, and later retries successfully', async () => {
  let stalled = true;
  const server = http.createServer((req, res) => {
    if (stalled) return;
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ projects: [], server_time: '2026-09-28T09:00:00Z' }));
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const events = [];
  const visibility = { hidden: false, addEventListener() {}, removeEventListener() {} };
  const feed = createLiveFeed({ url: `http://127.0.0.1:${server.address().port}/api/v1/projects`, visibility, intervalMs: 30, timeoutMs: 25, onState: state => events.push(state.status) });
  try {
    feed.start();
    await waitFor(() => events.includes('offline'));
    stalled = false;
    await waitFor(() => events.includes('online'));
  } finally { feed.stop(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
});

async function waitFor(predicate) {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 10));
  }
  assert.fail('timed out waiting for live state');
}
