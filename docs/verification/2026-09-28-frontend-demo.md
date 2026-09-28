# 前端 demo 验证记录

日期：2026-09-28。范围：独立 HTML 展示原型，非后端或远程部署验收。

## 自动化证据

- `node --test tests/progress-model.test.cjs`：7/7 通过。首次运行因计量/搜索功能不存在而失败，实现后转绿。
- `node scripts/build-demo.cjs`：导出独立的 `demo/index.html`、`demo/mobile.html`。
- `node scripts/check-demo.cjs`：21 项浏览器检查通过，执行环境为 Playwright Chromium。完整结果见 [verification.json](../../demo/previews/verification.json)。
- 实际验证通过 `file://` 打开独立导出文件，没有外部 HTTP 资源请求或 JavaScript 错误。
- 1440px 桌面、375/390/430px 手机及 1001px 布局断点没有横向溢出；长项目名、Task 详情、待验收、空计划、空搜索、离线示例均有覆盖。
- 筛选后进入详情再返回可保留筛选；内嵌手机预览的 hash 导航保持在同一文档中。
- 禁用 JavaScript 时仍能看到六个项目的静态概览。该用例先观察到 0 个项目的失败，再添加构建时静态回退后通过。

## 视觉检查

已检查桌面、手机首页、手机项目详情和手机 Task 详情截图。根据截图增大关键中文字号并加深次要文本；移动端提供整行 Task 点击区域、独立返回路径和可换行长标题。

[桌面](../../demo/previews/desktop.png) · [手机首页](../../demo/previews/mobile.png) · [项目详情](../../demo/previews/mobile-project.png) · [Task 详情](../../demo/previews/mobile-task.png)

## 边界

- 使用虚构演示数据，未读取本机真实项目或连接模型。
- 没有实现上报 MCP/API、SQLite 后端或 VPS 部署。
- 已完成 Chromium 浏览器模拟；真实 iPhone/Safari 和手机附件查看器尚待用户体验。
- 独立只读审查结果将在交付前补充。
