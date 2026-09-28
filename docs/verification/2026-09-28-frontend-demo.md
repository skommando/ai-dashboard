# 前端 demo 验证记录

日期：2026-09-28。范围：独立 HTML 展示原型，非后端或远程部署验收。

## 自动化证据

- `node --test tests/progress-model.test.cjs`：7/7 通过。首次运行因计量/搜索功能不存在而失败，实现后转绿。
- `node scripts/build-demo.cjs`：导出独立的 `demo/index.html`、`demo/mobile.html`。
- `node scripts/check-demo.cjs`：22 项浏览器检查通过，执行环境为 Playwright Chromium。完整结果见 [verification.json](../../demo/previews/verification.json)。
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

## 独立审查与修复

独立 reviewer 对 `c1c8a31..613b857` 的源文件、设计、测试和样例做只读审查，并独立重跑 7/7 单元测试。派发配置为 `gpt-6-astra / medium`；工具没有返回实际模型配置，因此实际配置不可验证。

发现一项 P2：从 Task 深层地址搜索另一个项目时，详情已切换但 hash 与标题仍保留旧 Task。已先增加失败回归，复现旧地址未变化，再改用统一路由更新流程；重新构建后，地址、标题和刷新后的项目均正确，完整测试通过。未发起重复审查。

审查中还考虑了以下事项：

- 手机返回总览后焦点落在 body：保留浏览器默认路径，仍可从跳转链接继续键盘操作；未将其列为当前阻断。
- 待验收与待细化同时存在时，顶部提示先显示待验收：保留此优先级，Wave 列表继续明确呈现待细化状态。
- 真实 iPhone、后端和部署：维持上述明确的交付边界。

## 本机预览

交付时仅在回环地址启动静态预览：`http://127.0.0.1:8765/` 和 `/mobile.html`，两个入口均返回 HTTP 200。该地址供当前电脑使用，不是已部署的外网地址。
