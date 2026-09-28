# 只读进度看板 HTML Demo Implementation Plan

> **For agentic workers:** 使用 `superpowers:executing-plans` 在当前会话执行。用户已确认先制作纯展示 demo，本轮不增加审批步骤或后端实现。

**Goal:** 交付独立 HTML，支持桌面与 iPhone 阅读项目进度和任务详情。

**Architecture:** 源文件按计量、样例数据、页面逻辑、样式划分；构建脚本内联为无依赖 HTML。浏览器只对样例数据进行查询、筛选和导航，不修改任务。

**Tech Stack:** 原生 HTML/CSS/JavaScript；Node 内置测试；Playwright 用于浏览器验证。

**Spec:** [已确认的设计](../specs/2026-09-28-progress-dashboard-design.md)

## Global Constraints

- 纯展示，使用清楚标注的演示数据，无模型调用、后端服务或公网部署。
- Task 等权；子项不改变分母；待验收与实施完成分开；未知分母不显示百分比。
- 项目 → Wave → Task → 可选子项；未来未拆 Wave 不虚构成任务。
- 1440px 桌面、375/390/430px 手机可读；键盘焦点、返回、长名称和空状态可用。
- 导出文件不依赖 CDN、外部字体、网络图片或构建环境。

## Review Focus

- Wave 大小不同、子项较多时，项目比例仍按 Task 计数。
- 100% 的已规划范围不能掩盖待细化 Wave 或待验收状态。
- 手机在筛选后进入和返回详情，筛选上下文不得丢失。
- 空查询结果、零 Task、离线示例均有清楚反馈。
- 长名称与任务详情不得造成手机横向溢出或不可触控。

## 视觉决定

- 主色：`#F5F6F3` 工作区底、`#FFFFFF` 内容面、`#202B27` 文字、`#537565` 强调、`#B4772E` 待处理、`#B45D50` 阻塞。
- 中文使用本地系统无衬线字体，页面标题用中等字重；进度数字和 Wave 编号用本地等宽字体。
- 特征：用真实 Wave 顺序构成阶段轨道，任务数和完成状态紧贴轨道；其余区域使用安静的列表与细分隔线。
- 自检：去掉大数字统计卡、装饰性图表和欢迎标语，第一屏直接呈现项目与进展。

### Task 1: 可解释的计量与样例数据

**Files:** `demo/src/model.js`、`demo/src/data.js`、`tests/progress-model.test.cjs`

**Interfaces:** `ProgressModel.summarize(project)` 返回 `{ done, total, percent, unplannedWaves, pendingAcceptance }`；`ProgressModel.matches(project, query)` 搜索项目和任务文字。

- [x] 编写并观察失败测试：2/10 为 20%、子项不增加分母、待验收已完成 Task 计入、未通过检查不计入、取消项排除、零分母为未知、深层任务可搜索。
- [x] 实现计量函数，运行 `node --test tests/progress-model.test.cjs`，7/7 通过。
- [x] 创建六个一致的示例项目，覆盖正常、阻塞、待验收、完成、待细化和空计划。

### Task 2: 页面、移动端与独立导出

**Files:** `demo/src/shell.html`、`demo/src/styles.css`、`demo/src/app.js`、`scripts/build-demo.cjs`、生成的 `demo/index.html` 和 `demo/mobile.html`

**Interfaces:** 页面消费 `ProgressModel` 和 `DemoData.projects`。导航使用 hash；项目和 Task ID 保持稳定。

- [x] 实现项目列表、状态筛选、搜索、Wave 展开、Task 详情、返回和计算口径说明。
- [x] 桌面列表/详情并排，手机逐层进入；提供仅影响预览的离线场景选择。
- [x] 内联源码构建独立 HTML，并生成内嵌同一页面的手机预览文件。
- [x] 运行 `node scripts/build-demo.cjs`，成功导出两个可直接打开的 HTML。

### Task 3: 浏览器验证与交付

**Files:** `scripts/check-demo.cjs`、`demo/previews/*.png`、`demo/README.md`、根 `README.md`、验证记录。

- [x] 在实际浏览器验证桌面/手机布局、筛选/搜索、Wave/Task 下钻、返回、计算说明、离线和空状态。
- [x] 检查 375/390/430/1440px 无横向溢出、控制台错误和外部资源请求；检查本地 HTML 打开。
- [x] 保存桌面、手机首页和手机详情截图，并目视检查和修正布局。
- [x] 最终只读审查；记录验证、真实 iPhone 尚待用户体验的边界；提交交付文件并请求打开预览。

## 执行记录

- 基线：`c1c8a31`，工作区干净；创建 `demo/progress-dashboard` 分支。
- 方法裁决：这是已获授权的可逆展示原型，使用当前独占干净目录，不另建 worktree。计量规则做行为测试，视觉和交互做浏览器验证，不为文案和 CSS 逐条制造测试。
- 方法裁决：本机提供 bundled Playwright；只用于本地页面验证，不为 demo 增加运行依赖。
- Task 1 完成：先失败后实现，7/7 计量与搜索测试通过。
- Task 2 完成：两个独立 HTML 导出成功；手机 iframe 内链接通过当前文档 hash 更新，修复继承父文档 URL 导致的嵌套预览问题。
- Task 3 完成：22 项浏览器检查通过；补充禁用脚本时的静态概览，便于手机附件查看器阅读；4 张截图已检查。
- 最终审查：独立 reviewer 发现的深层搜索路由 P2 已通过失败回归定位并修复，完整测试转绿。审查范围与非阻断裁决见验证记录。
- 交付：保留 `demo/progress-dashboard` 分支和当前工作目录；本次交付本地文件，未安排合并、推送或部署。
