(function (root) {
  'use strict';
  function summarize(project) {
    const waves = project.waves || [];
    const tasks = waves.flatMap(wave => wave.tasks || []).filter(task => task.status !== 'cancelled');
    const completed = tasks.filter(task => task.status === 'done' && task.verified === true);
    return {
      done: completed.length,
      total: tasks.length,
      percent: tasks.length ? Math.round(completed.length / tasks.length * 100) : null,
      unplannedWaves: waves.filter(wave => wave.defined === false).length,
      pendingAcceptance: (project.acceptance === 'pending' ? 1 : 0)
        + waves.filter(wave => wave.acceptance === 'pending').length
        + completed.filter(task => task.acceptance === 'pending').length,
    };
  }
  function matches(project, query) {
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) return true;
    const taskText = task => [task.title, task.summary, ...(task.children || []).map(taskText)].join(' ');
    const text = [project.name, project.description, project.summary,
      ...(project.waves || []).flatMap(wave => [wave.name, ...(wave.tasks || []).map(taskText)]),
    ].join(' ').toLocaleLowerCase();
    return text.includes(needle);
  }
  const api = Object.freeze({ summarize, matches });
  root.ProgressModel = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(globalThis);
