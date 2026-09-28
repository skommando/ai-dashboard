# ai-dashboard

一个面向个人的远程项目进度看板，初步目标是在 iPhone 上方便地查看 Windows 本机运行的多个项目。

## 需求起点

- 为不同项目设计统一、可解释的进度计量指标。
- 提供统一的更新入口，让项目或其中的 agent 主动上报进度；候选为 MCP、HTTP API（以 OpenAPI 描述）。
- 提供直观、友好的查看体验，适配手机与桌面。
- 调研现有开源 AI 工作台，明确可借鉴内容和本项目边界。

## 当前状态

2026-09-28：已确认只读查看、项目主动上报、按 Task 等权计量和本地离线展示边界，并完成第一版前端 demo。

当前 demo 使用原生 HTML/CSS/JavaScript 与静态样例数据。后续后端采用 Python + SQLite，正式前端建议 Vue 3 + TypeScript；远程访问计划沿用 VPS + frp + HTTPS/Basic Auth。后端、真实数据接入与部署尚未实现。

## 前端 demo

- [完整 demo](demo/index.html)：可独立打开，自动适配桌面与手机。
- [手机预览](demo/mobile.html)：可独立转发，桌面可切换手机宽度。
- [体验说明与命令](demo/README.md)。

```powershell
node scripts/build-demo.cjs
node --test tests/progress-model.test.cjs
python -m http.server 8765 --bind 127.0.0.1 --directory demo
```

浏览器打开 `http://127.0.0.1:8765/`。也可直接打开 HTML，无需运行服务。

## 文档入口

- [项目协作约定](AGENTS.md)：工作范围、授权、验证、Git 与协作规则。
- [AI 工作台简要调研](docs/research/2026-09-28-ai-workbenches.md)：六个代表项目、与本项目的差异、iPhone 访问可行性与后续设计建议。
- [进度看板设计](docs/superpowers/specs/2026-09-28-progress-dashboard-design.md)：已确认的计量口径、只读架构与桌面/手机 demo 方案。
- [demo 执行计划](docs/superpowers/plans/2026-09-28-frontend-demo.md)与[验证记录](docs/verification/2026-09-28-frontend-demo.md)。
- [本地 Codex 最小验证](docs/research/2026-09-28-codex-local-probe.md)：不使用 SDK 的实际调用结果与尚未验证的边界。

## 下一步

体验 HTML demo 并反馈视觉和使用体验；后端协议和真实项目接入在后续实施阶段完成。

当前阶段不包含 AI 编码执行器、聊天平台、多用户系统或原生 iOS 应用。远程控制本地 Codex 仅完成独立连接的最小验证，未纳入看板首版。
