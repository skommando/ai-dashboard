const { readFileSync, writeFileSync, mkdirSync } = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const read = name => readFileSync(path.join(root, 'demo/src', name), 'utf8');
const { summarize } = require('../demo/src/model.js');
const { projects } = require('../demo/src/data.js');
const escapeHtml = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const labels = { active: '进行中', blocked: '已阻塞', review: '待验收', complete: '已完成', planning: '规划中' };
let html = read('shell.html');
for (const [marker, file] of [['STYLES', 'styles.css'], ['MODEL', 'model.js'], ['DATA', 'data.js']]) {
  const token = `/* INLINE_${marker} */`;
  if (!html.includes(token)) throw new Error(`Missing inline marker: ${marker}`);
  html = html.replace(token, () => read(file));
}
html = html.replace('/* INLINE_APP */', () => `const DashboardConfig = { mode: 'demo', projects: DemoData.projects, dateLabel: DemoData.dateLabel };\n${read('app.js')}\n${read('scenario.js')}`);
const staticRows = projects.map(project => {
  const value = summarize(project);
  return `<div class="project-row" data-status="${project.status}"><div class="row-top"><span class="project-icon ${project.color}">${escapeHtml(project.shortName[0])}</span><div class="row-identity"><strong>${escapeHtml(project.name)}</strong><span class="row-wave">已规划范围</span></div><span class="status-tag ${project.status}">${labels[project.status]}</span></div><p class="row-summary">${escapeHtml(project.summary)}</p><div class="row-bottom">${value.total ? `<progress value="${value.done}" max="${value.total}"></progress><span class="row-count">${value.done} / ${value.total}</span><span class="row-percent">${value.percent}%</span>` : '<span class="unplanned-track"></span><span class="row-count">尚未登记任务</span>'}<span class="row-updated">${escapeHtml(project.updated)}</span></div></div>`;
}).join('');
let liveHtml = read('shell.html');
liveHtml = liveHtml.replace(/^[ \t]*<details class="demo-menu" id="demo-menu">[\s\S]*?<\/details>\r?\n/m, '');
liveHtml = liveHtml.replace('<span class="foot-version">DEMO / 01</span>', '');
liveHtml = liveHtml.replace('<span id="side-project-count">06</span>', '<span id="side-project-count">0</span>');
liveHtml = liveHtml.replace('<span class="heading-count" id="heading-count">6</span>', '<span class="heading-count" id="heading-count">0</span>');
liveHtml = liveHtml.replace('个人项目进度看板，只读交互演示。', '个人项目进度看板，只读查看真实上报。');
liveHtml = liveHtml.replace('以下保留最后一次记录 · 今天 14:38。请确认电脑在线后再查看。', '无法读取当前数据，连接恢复后会自动重试。');
liveHtml = liveHtml.replace('暂时无法连接本机', '暂时无法读取进度');
liveHtml = liveHtml.replace('<span class="offline-tag">离线示例</span>', '<span class="offline-tag">离线</span>');
liveHtml = liveHtml.replace('示例快照 · 今天 14:38', '正在读取项目…');
liveHtml = liveHtml.replace('本页为虚构演示数据，不代表本机实时状态。', '数据由项目主动上报；最后上报时间与页面刷新时间分别计算。');
liveHtml = liveHtml.replace(/<noscript>[\s\S]*?<\/noscript>/, '<noscript><main class="static-preview">请启用 JavaScript 查看实时项目进度。</main></noscript>');
for (const [marker, source] of [['STYLES', read('styles.css')], ['MODEL', read('model.js')], ['DATA', "const DashboardConfig = { mode: 'live', projects: [] };"], ['APP', `${read('live.js')}\n${read('app.js')}`]]) {
  liveHtml = liveHtml.replace(`/* INLINE_${marker} */`, () => source);
}
mkdirSync(path.join(root, 'web'), { recursive: true });
writeFileSync(path.join(root, 'web/index.html'), liveHtml);
html = html.replace('/* INLINE_STATIC */', () => `<style>.app-shell{display:none}.static-preview{max-width:680px;margin:auto;padding:24px 20px}.static-preview h1{font-size:27px;font-weight:600;margin:12px 0}.static-preview>p{font-size:12px;line-height:1.9;color:#69756f;margin-bottom:24px}.static-preview .project-list{gap:12px}</style><main class="static-preview"><div class="eyebrow">进度簿 · 演示数据</div><h1>项目总览</h1><p>当前显示静态概览。在支持页面交互的浏览器中打开，可进一步查看 Wave 和 Task 详情。</p><div class="project-list">${staticRows}</div></main>`);
writeFileSync(path.join(root, 'demo/index.html'), html);
const encoded = html.replace(/&/g, '&amp;').replace(/"/g, '&quot;');
const mobile = `<!doctype html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>进度簿 · 手机预览</title>
<style>*{box-sizing:border-box}body{margin:0;background:#e9ede7;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;color:#60735b}.preview{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:32px 20px;gap:48px}.note{max-width:180px}.note h1{font-size:22px;font-weight:550;color:#304b2d;letter-spacing:-.02em}.note p{font-size:12px;line-height:1.9}.note label{display:block;font-size:11px;margin:20px 0 8px}select{padding:9px 12px;border:1px solid #c6d1bf;background:#f7faf2;color:#526d47;border-radius:5px;font:12px inherit}iframe{display:block;width:390px;height:844px;max-height:calc(100vh - 64px);border:1px solid #c9d3c0;border-radius:20px;background:#f5f6f3;box-shadow:0 15px 45px #334a2520}.caption{font-size:10px;color:#8d9e7f;margin-top:21px}@media(max-width:600px){.preview{padding:0;display:block}.note{display:none}iframe{width:100%!important;height:100vh;height:100dvh;max-height:none;border:0;border-radius:0;box-shadow:none}}</style></head><body><main class="preview"><div class="note"><h1>进度簿</h1><p>手机端交互预览。<br>项目、阶段和任务，<br>按阅读顺序逐层展开。</p><label for="preview-width">预览宽度</label><select id="preview-width"><option value="375">375 px · 窄屏</option><option value="390" selected>390 px · 标准</option><option value="430">430 px · 大屏</option></select><p class="caption">同一套页面 · 演示数据<br>在手机上打开时自动铺满屏幕。</p></div><iframe id="phone" title="手机端进度看板" srcdoc="${encoded}"></iframe></main><script>document.querySelector('#preview-width').addEventListener('change',function(){document.querySelector('#phone').style.width=this.value+'px'});</script></body></html>`;
writeFileSync(path.join(root, 'demo/mobile.html'), mobile);
mkdirSync(path.join(root, 'demo/previews'), { recursive: true });
console.log(`Exported demo/index.html (${Buffer.byteLength(html)} bytes), demo/mobile.html (${Buffer.byteLength(mobile)} bytes), and web/index.html (${Buffer.byteLength(liveHtml)} bytes).`);
