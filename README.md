# ai-dashboard · 进度簿

一个轻量的项目进度看板。项目或 agent 主动上报工作快照，在手机和桌面统一查看 Project → Wave → Task 的进度、具体工作、阻塞和验收依据。

- Python 3.12 + FastAPI + SQLite，单个服务同时提供页面、读取与上报 API。
- 查看使用 Basic Auth；上报额外需要项目独立令牌。公网部署在 VPS，经 Nginx 提供 HTTPS，无需隧道或保持开发电脑在线。
- Task 等权计量；子项不增加分母。未规划范围、实际完成、验收及上报时间分别显示。
- HTML/CSS/JavaScript 前端，无模型调用、远程执行或手机写入界面。

## 使用

1. 部署管理员按 [VPS 部署](docs/vps-deployment.md) 启动服务，设置查看账号并登记项目令牌。
2. 接入方按 [API 与 AI 接入文档](docs/api.md) 准备凭据、查询版本、封存快照并上报。
3. 在浏览器打开自己的部署域名，用查看账号登录；可在 iPhone Safari 中访问。

本文的域名、路径与凭据均为示例，仓库不包含可用的生产凭据或真实项目数据库。

## 本地开发

需要 Python 3.12、Node.js 22。开发数据库与生产数据库独立。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
node scripts/build-demo.cjs
.\tools\start.ps1
# 访问 http://127.0.0.1:8810，使用自己设置的开发凭据
.\tools\stop.ps1
```

启动参数与凭据设置见 [tools](tools/README.md)。启动/停止脚本放在 `tools/`；Linux 入口用于管理 VPS 上的 systemd 服务。运行数据默认在仓库外，不能放进 Git。

## 开发与发布

`dev` 用于迭代；通过测试与审查后合入 `main`，生产只部署 `main` 的固定提交。GitHub CI 不持有部署凭据，也不会自动部署。只有所有者明确要求时才可跳过测试，并记录原因。

- [贡献与验收流程](CONTRIBUTING.md)
- [运行、备份与恢复](docs/operations.md)
- [安全与凭据](SECURITY.md)
- [协作约定](AGENTS.md)

## 离线演示

[完整 demo](demo/index.html) 和 [手机预览](demo/mobile.html) 可独立打开，仅含虚构样例。修改 `demo/src/` 后运行 `node scripts/build-demo.cjs`，同时生成正式前端 `web/index.html`。浏览器移动视口检查与真实 iPhone 验收分别记录。

## 许可

[MIT](LICENSE)，Copyright © 2026 skommando。第三方依赖保持各自的许可证。
