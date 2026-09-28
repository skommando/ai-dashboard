(function (root) {
  'use strict';
  function summarize(project) {
    const waves = project.waves || [];
    const tasks = waves.flatMap(wave => wave.tasks || []).filter(task => task.status !== 'cancelled');
    const completed = tasks.filter(task => task.status === 'done' && task.verified === true);
    return {
      done: completed.length,
      total: tasks.length,
      percent: tasks.length ? Math.floor((2 * completed.length * 100 + tasks.length) / (2 * tasks.length)) : null,
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
  function adaptResponse(response) {
    if (!response || !Array.isArray(response.projects)) throw new Error('Invalid projects response');
    if (typeof response.server_time !== 'string' || Number.isNaN(Date.parse(response.server_time))) throw new Error('Invalid server_time');
    return response.projects.map(project => {
      if (!project || typeof project.id !== 'string' || typeof project.name !== 'string' || !Array.isArray(project.waves) || !Array.isArray(project.updates) || typeof project.receivedAt !== 'string' || Number.isNaN(Date.parse(project.receivedAt))) throw new Error('Invalid project');
      return {
        ...project,
        waves: project.waves.map(wave => ({ ...wave, tasks: (wave.tasks || []).map(task => ({
          ...task, children: task.children || [], evidence: task.evidence || [],
        })) })),
        updates: project.updates.map(update => ({ ...update })),
      };
    });
  }
  const api = Object.freeze({ summarize, matches, adaptResponse });
  root.ProgressModel = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(globalThis);
