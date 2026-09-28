const test = require('node:test');
const assert = require('node:assert/strict');
const { existsSync } = require('node:fs');
const modelPath = require('node:path').join(__dirname, '../demo/src/model.js');
const model = existsSync(modelPath) ? require(modelPath) : {};
const done = (id, extra = {}) => ({ id, title: id, status: 'done', verified: true, ...extra });
const todo = id => ({ id, title: id, status: 'todo', verified: false });
const project = waves => ({ id: 'p', name: '测试项目', waves });
function summarize(input) {
  assert.equal(typeof model.summarize, 'function', '计量函数尚未实现');
  return model.summarize(input);
}

test('不同大小的 Wave 直接汇总 Task：2/10 = 20%，不平均为 50%', () => {
  const value = summarize(project([
    { tasks: [done('a'), done('b')] },
    { tasks: ['c', 'd', 'e', 'f', 'g', 'h', 'i', 'j'].map(todo) },
  ]));
  assert.equal(value.done, 2);
  assert.equal(value.total, 10);
  assert.equal(value.percent, 20);
});

test('子项完成不替代父 Task 验证，也不增加分母', () => {
  const value = summarize(project([{ tasks: [
    done('a'), { ...todo('b'), children: [done('b1'), done('b2'), done('b3')] },
  ] }]));
  assert.equal(value.done, 1);
  assert.equal(value.total, 2);
  assert.equal(value.percent, 50);
});

test('实施完成但待验收的 Task 计入进度，验收另计', () => {
  const value = summarize(project([{ tasks: [done('a', { acceptance: 'pending' })] }]));
  assert.equal(value.percent, 100);
  assert.equal(value.pendingAcceptance, 1);
});

test('标记 done 但没有验证依据的 Task 不计为完成', () => {
  const value = summarize(project([{ tasks: [done('a', { verified: false })] }]));
  assert.equal(value.done, 0);
  assert.equal(value.percent, 0);
});

test('取消项退出计量，但待细化 Wave 仍被报告', () => {
  const value = summarize(project([
    { tasks: [done('a'), { ...todo('b'), status: 'cancelled' }] },
    { defined: false, tasks: [] },
  ]));
  assert.equal(value.total, 1);
  assert.equal(value.percent, 100);
  assert.equal(value.unplannedWaves, 1);
});

test('零 Task 和全部取消的计划都显示未知百分比', () => {
  assert.equal(summarize(project([])).percent, null);
  assert.equal(summarize(project([{ tasks: [{ ...todo('a'), status: 'cancelled' }] }])).percent, null);
});

test('搜索能找到下钻任务和子项，并忽略大小写及首尾空格', () => {
  assert.equal(typeof model.matches, 'function', '搜索函数尚未实现');
  const input = project([{ name: '检索', tasks: [{ ...todo('a'), title: 'Search 索引', children: [{ title: '中文分词' }] }] }]);
  assert.equal(model.matches(input, '  SEARCH '), true);
  assert.equal(model.matches(input, '中文分词'), true);
  assert.equal(model.matches(input, '不存在'), false);
});
