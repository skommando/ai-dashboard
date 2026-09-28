(function (root) {
  'use strict';
  function createLiveFeed({ url = '/api/v1/projects', visibility = document, intervalMs = 15000, timeoutMs = 8000, onState }) {
    let projects = [];
    let timer = null;
    let controller = null;
    let pending = false;
    let running = false;
    let stopped = true;

    function schedule() {
      clearTimeout(timer);
      if (!stopped && !visibility.hidden) timer = setTimeout(refresh, intervalMs);
    }
    async function refresh() {
      if (stopped || visibility.hidden) return;
      if (running) { pending = true; return; }
      clearTimeout(timer);
      running = true;
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetch(url, { signal: controller.signal, cache: 'no-store', credentials: 'same-origin' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        projects = ProgressModel.adaptResponse(await response.json());
        if (!stopped) onState({ status: 'online', projects });
      } catch (error) {
        if (!stopped) onState({ status: 'offline', projects, error });
      } finally {
        clearTimeout(timeout);
        controller = null;
        running = false;
        if (pending && !visibility.hidden) { pending = false; refresh(); }
        else schedule();
      }
    }
    function onVisibility() {
      if (visibility.hidden) { clearTimeout(timer); pending = false; }
      else refresh();
    }
    function start() {
      if (!stopped) return;
      stopped = false;
      visibility.addEventListener('visibilitychange', onVisibility);
      refresh();
    }
    function stop() {
      stopped = true;
      pending = false;
      clearTimeout(timer);
      controller?.abort();
      visibility.removeEventListener('visibilitychange', onVisibility);
    }
    const api = { start, stop, refresh };
    return api;
  }
  root.LiveFeed = { createLiveFeed };
  if (typeof module !== 'undefined' && module.exports) module.exports = { createLiveFeed };
})(globalThis);
