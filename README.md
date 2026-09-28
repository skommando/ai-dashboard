# ai-dashboard

一个面向个人的远程项目进度看板，初步目标是在 iPhone 上方便地查看 Windows 本机运行的多个项目。

## 需求起点

- 为不同项目设计统一、可解释的进度计量指标。
- 提供统一的更新入口，让项目或其中的 agent 主动上报进度；候选为 MCP、HTTP API（以 OpenAPI 描述）。
- 提供直观、友好的查看体验，适配手机与桌面。
- 调研现有开源 AI 工作台，明确可借鉴内容和本项目边界。

## 当前状态

2026-09-28：完成仓库初始化、同类项目调研及第一轮需求对齐。已确认只读查看、项目主动上报、按 Task 等权计量和本地离线展示边界；设计草案待整体审阅。

后端采用 Python + SQLite；设计草案建议 FastAPI、Vue 3 + TypeScript，以及用于评审的独立 HTML demo。计划沿用现有 VPS + frp + HTTPS/Basic Auth 访问方式。当前尚无产品实现或可执行的启动、测试、构建命令，后续实现时补充真实入口。

## 文档入口

- [项目协作约定](AGENTS.md)：工作范围、授权、验证、Git 与协作规则。
- [AI 工作台简要调研](docs/research/2026-09-28-ai-workbenches.md)：六个代表项目、与本项目的差异、iPhone 访问可行性与后续设计建议。
- [进度看板设计草案](docs/superpowers/specs/2026-09-28-progress-dashboard-design.md)：已确认的计量口径、只读架构与桌面/手机 demo 方案。
- [本地 Codex 最小验证](docs/research/2026-09-28-codex-local-probe.md)：不使用 SDK 的实际调用结果与尚未验证的边界。

## 下一步

整体核对设计草案后，制作可在桌面和 iPhone 体验的只读 HTML demo。后端协议和真实项目接入在后续实施阶段完成。

当前阶段不包含 AI 编码执行器、聊天平台、多用户系统或原生 iOS 应用。远程控制本地 Codex 仅完成独立连接的最小验证，未纳入看板首版。
