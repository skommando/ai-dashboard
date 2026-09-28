# ai-dashboard

一个面向个人的远程项目进度看板，初步目标是在 iPhone 上方便地查看 Windows 本机运行的多个项目。

## 需求起点

- 为不同项目设计统一、可解释的进度计量指标。
- 提供统一的更新入口，让项目或其中的 agent 主动上报进度；候选为 MCP、HTTP API（以 OpenAPI 描述）。
- 提供直观、友好的查看体验，适配手机与桌面。
- 调研现有开源 AI 工作台，明确可借鉴内容和本项目边界。

## 当前状态

2026-09-28：Python + SQLite 后端、稳定上报 OpenAPI、真实前端和本机/VPS 服务已上线，核心与公开页面验证通过。

正式页面沿用已认可的原生 HTML/CSS/JavaScript，读取真实上报数据。独立 demo 继续保留虚构样例。项目不调用大模型，也不提供网页写入或远程执行功能。

## 已部署入口

- 查看：[dashboard.example.com](https://dashboard.example.com)，使用既有 Basic Auth。
- 本机读取：`http://127.0.0.1:8810/`，同样要求查看凭据。
- 本机上报：`http://127.0.0.1:8811`，每项目使用独立 Bearer token。
- 本机 OpenAPI：[交互文档](http://127.0.0.1:8811/docs)、[JSON 契约](http://127.0.0.1:8811/openapi.json)。

首个真实项目为 `ai-dashboard`。其他项目按[接入说明](docs/api.md)登记、领取本机令牌并主动上报；不会扫描其他仓库伪造进度。

## 运行与维护

当前用户登录任务 `AI Dashboard - dashboard.example.com` 管理本机监督进程；它负责读取服务、写入服务与 frpc，组件异常退出会重试。VPS 使用独立 `ai-dashboard-frps.service`，8072 为控制端口，8083 仅监听回环，供 Nginx 转发。

```powershell
# 在仓库根目录检查、启动或停止本项目服务
.\.venv\Scripts\python.exe scripts/service.py status --config .runtime/service.json
Start-ScheduledTask -TaskName 'AI Dashboard - dashboard.example.com'
powershell -NoProfile -File scripts/stop-dashboard.ps1

# 构建与检查
node scripts/build-demo.cjs
node --test tests/*.cjs
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
```

运行配置、原始令牌、日志和 SQLite 位于忽略的 `.runtime/`；不要提交或转发这些文件。安装环境可按 `requirements-lock.txt` 复现。详见[运行说明](docs/operations.md)和[VPS 部署说明](docs/vps-deployment.md)。

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
- [正式服务契约](docs/superpowers/specs/2026-09-28-live-dashboard-contract.md)与[实施检查点](docs/superpowers/plans/2026-09-28-live-dashboard.md)。
- [上线验证记录](docs/verification/2026-09-28-live-dashboard.md)：真实上报、重启、鉴权、端口边界与公网浏览器证据。

## 下一步

在 iPhone 上体验正式页面，并为其他项目接入上报。浏览器移动视口与真实 iPhone 的验收分别记录。

当前阶段不包含 AI 编码执行器、聊天平台、多用户系统或原生 iOS 应用。远程控制本地 Codex 仅完成独立连接的最小验证，未纳入看板首版。
