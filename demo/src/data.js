(function (root) {
  'use strict';
  function wave(id, name, titles, doneCount, options = {}) {
    return {
      id, name, defined: true, acceptance: 'not_required',
      tasks: titles.map((title, index) => ({
        id: `${id}-t${index + 1}`, code: `T${Number(id.slice(1))}.${index + 1}`, title,
        status: index < doneCount ? 'done' : 'todo', verified: index < doneCount,
        acceptance: 'not_required',
        goal: `完成${title}，并检查正常输入和异常输入下的表现。`,
        summary: index < doneCount ? '实现与约定检查已完成，结果已记录。' : '尚未开始，按阶段计划推进。',
        updated: index < doneCount ? '今天 11:20' : '今天 09:10',
        evidence: index < doneCount ? [{ label: '检查结果', text: '约定的功能检查通过' }, { label: '记录位置', text: `docs/tasks/${id}-${index + 1}.md` }] : [],
        children: [],
      })),
      ...options,
    };
  }
  const knowledge = {
    id: 'knowledge', name: '本地知识库', shortName: '知识库', glyph: 'book', color: 'sage',
    description: '把散落的笔记和资料放在一起，检索时保留原文出处。',
    summary: '正在处理检索结果去重，引用来源已接通。', status: 'active',
    updated: '2 分钟前', updatedAt: '今天 14:36', currentWave: 'w2', category: '个人工具',
    waves: [
      wave('w1', '资料接入', ['定义文档目录结构', '导入 Markdown 笔记', '解析 PDF 正文', '提取文档元数据', '文件变更检测', '重复文件识别', '增量导入记录', '接入流程验证'], 8),
      wave('w2', '检索与引用', ['建立全文索引', '中文分词与召回', '连接原文引用', '检索结果排序', '合并重复检索片段', '高亮命中段落', '分页与空结果处理', '检索体验回归'], 4),
      wave('w3', '阅读体验', ['资料阅读页', '标签与目录导航', '手机阅读布局', '阅读状态回归'], 0),
      { id: 'w4', name: '多端验证', defined: false, tasks: [] },
      { id: 'w5', name: '交付与整理', defined: false, tasks: [] },
    ],
    updates: [
      { time: '14:36', tone: 'active', text: '开始合并重复检索片段', detail: 'Wave 02 · T2.5' },
      { time: '14:08', tone: 'done', text: '检索结果排序检查通过', detail: '已规划任务 11 → 12 / 20' },
      { time: '11:20', tone: 'done', text: '原文引用已连接到检索结果', detail: 'Wave 02 · T2.3' },
    ],
  };
  Object.assign(knowledge.waves[1].tasks[4], {
    status: 'active', goal: '同一段内容被多个来源命中时，只保留一份清晰结果，同时保留所有原文引用。',
    summary: '文档标识归一化已完成，正在处理相邻片段的重叠区间。', updated: '今天 14:36',
    children: [
      { title: '归一化文档标识', status: 'done' },
      { title: '合并相邻片段的重叠区间', status: 'active' },
      { title: '验证跨来源引用仍可追溯', status: 'todo' },
    ],
    evidence: [{ label: '当前记录', text: 'docs/tasks/retrieval-dedup.md' }, { label: '验证要求', text: '无重复结果；来源引用完整；空结果可正常返回' }],
  });

  const billing = {
    id: 'billing', name: '账单归档', shortName: '账单归档', glyph: 'receipt', color: 'sand',
    description: '把不同来源的账单整理成统一、可核对的月度记录。',
    summary: '导入流程已完成，等待确认退款的归属月份。', status: 'blocked',
    updated: '18 分钟前', updatedAt: '今天 14:20', currentWave: 'w2', category: '生活管理',
    blocker: '退款按原消费月份归档，还是按实际退款月份归档？',
    waves: [
      wave('w1', '数据导入', ['识别账单格式', '清洗日期与金额', '建立统一记录', '检查重复账单'], 4),
      wave('w2', '分类与核对', ['设置分类规则', '核对总金额', '确认退款归属规则', '生成月度汇总', '补充导入异常提示', '整体验证'], 2),
    ],
    updates: [
      { time: '14:20', tone: 'blocked', text: '退款归属规则需要确认', detail: '当前进度保留在 6 / 10' },
      { time: '13:42', tone: 'done', text: '月度总金额核对通过', detail: 'Wave 02 · T2.2' },
    ],
  };
  Object.assign(billing.waves[1].tasks[2], {
    status: 'waiting', summary: '同一笔跨月退款会影响两个月的汇总，需要先确定记账口径。',
    goal: '统一退款记录的月份归属，避免统计规则前后不一致。',
    blocker: billing.blocker, updated: '今天 14:20',
    evidence: [{ label: '两种口径', text: '原消费月：便于追溯消费；实际退款月：贴近资金变化。' }],
  });

  const photos = {
    id: 'photos', name: '家庭相册整理', shortName: '相册整理', glyph: 'image', color: 'plum',
    description: '按拍摄日期整理家庭照片，保留原图并生成轻量预览。',
    summary: '已完成全部检查，等待查看分组与预览效果。', status: 'review',
    updated: '42 分钟前', updatedAt: '今天 13:56', currentWave: 'w2', category: '生活管理',
    waves: [
      wave('w1', '归档规则', ['读取拍摄日期', '识别重复照片', '建立年月目录', '保留原始文件'], 4),
      wave('w2', '预览与验证', ['生成照片缩略图', '提供相册预览', '检查日期缺失情况', '验证归档结果'], 4, { acceptance: 'pending' }),
    ],
    updates: [{ time: '13:56', tone: 'review', text: '实施完成，等待阶段验收', detail: '8 / 8 Task · Wave 02 待验收' }],
  };
  Object.assign(photos.waves[1].tasks[3], { summary: '抽查原图、日期分组与缩略图，约定检查均已通过。', evidence: [
    { label: '验证结果', text: '原图数量一致；重复项可追溯；缺失日期的照片单独归档。' },
    { label: '阶段验收', text: '待查看相册预览效果。实施进度已计入完成。' },
  ] });

  const reading = {
    id: 'reading', name: '阅读清单', shortName: '阅读清单', glyph: 'bookmark', color: 'blue',
    description: '统一收藏稍后阅读的文章，保留来源与阅读状态。',
    summary: '收藏入口可用，正在整理列表的筛选体验。', status: 'active',
    updated: '1 小时前', updatedAt: '今天 13:12', currentWave: 'w2', category: '个人工具',
    waves: [
      wave('w1', '收藏入口', ['保存文章链接', '提取标题与来源', '识别重复收藏'], 3),
      wave('w2', '列表与阅读', ['筛选未读文章', '按来源浏览', '搜索收藏内容', '文章详情页', '手机适配', '阅读流程验证'], 0),
    ],
    updates: [{ time: '13:12', tone: 'active', text: '开始实现未读筛选', detail: 'Wave 02 · T2.1' }],
  };
  Object.assign(reading.waves[1].tasks[0], { status: 'active', summary: '筛选条件已接通，正在检查空列表和切换后的滚动位置。' });

  const toolbox = {
    id: 'toolbox', name: '日常小工具', shortName: '小工具', glyph: 'grid', color: 'stone',
    description: '把常用的文本处理与格式转换工具放在一个页面。',
    summary: '全部任务完成，交付检查已通过。', status: 'complete',
    updated: '昨天', updatedAt: '昨天 18:05', currentWave: 'w3', category: '个人工具',
    waves: [
      wave('w1', '基础页面', ['工具入口', '通用输入区域', '结果展示'], 3),
      wave('w2', '常用工具', ['文本去重', '格式转换', '时间戳换算'], 3),
      wave('w3', '交付检查', ['手机布局', '键盘操作', '完整回归'], 3, { acceptance: 'accepted' }),
    ],
    updates: [{ time: '昨天', tone: 'done', text: '交付检查已通过', detail: '9 / 9 Task · 已验收' }],
  };
  const monitor = {
    id: 'monitor', name: '个人站点可用性与证书到期检查', shortName: '站点检查', glyph: 'globe', color: 'stone',
    description: '定期检查个人站点是否可访问，以及证书是否即将到期。',
    summary: '已明确检查范围，任务尚待拆分。', status: 'planning',
    updated: '昨天', updatedAt: '昨天 16:30', currentWave: 'w1', category: '基础设施',
    waves: [{ id: 'w1', name: '站点与规则', defined: false, tasks: [] }, { id: 'w2', name: '检查与展示', defined: false, tasks: [] }],
    updates: [{ time: '昨天', tone: 'todo', text: '记录站点检查范围', detail: '2 个 Wave 待细化' }],
  };
  const data = { dateLabel: '9 月 28 日，周一', snapshotLabel: '今天 14:38', projects: [knowledge, billing, photos, reading, toolbox, monitor] };
  root.DemoData = data;
  if (typeof module !== 'undefined' && module.exports) module.exports = data;
})(globalThis);
