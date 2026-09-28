document.addEventListener('click', event => {
  const menu = document.querySelector('#demo-menu');
  const scenario = event.target.closest('[data-scenario]')?.dataset.scenario;
  if (scenario) {
    document.querySelector('#offline-banner').hidden = scenario !== 'offline';
    document.querySelector('#snapshot-label').textContent = scenario === 'offline' ? '离线 · 保留示例快照' : '示例快照 · 今天 14:38';
    document.querySelectorAll('[data-check]').forEach(node => { node.textContent = node.dataset.check === scenario ? '✓' : ''; });
    menu.open = false;
  } else if (!event.target.closest('#demo-menu')) menu.open = false;
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') document.querySelector('#demo-menu').open = false;
});
