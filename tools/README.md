# 启停入口

Windows 开发：先安装 Python 3.12，然后运行 `powershell -NoProfile -File tools/start.ps1`。首次运行会在 `%LOCALAPPDATA%\ai-dashboard\dev\venv` 建立虚拟环境并安装锁定依赖；可用 `-Python <仓库外解释器路径>` 指定已有环境。首次输入 Basic Auth 用户名和密码，或通过 `DASHBOARD_VIEW_USERNAME`、`DASHBOARD_VIEW_PASSWORD` 环境变量提供；脚本不会打印凭据。服务配置、SQLite、状态和日志也位于 `%LOCALAPPDATA%\ai-dashboard\dev`，可通过 `-Runtime <仓库外绝对路径>` 改写。运行 `powershell -NoProfile -File tools/stop.ps1` 停止。两个脚本跟随当前源码位置，默认仅启动一个回环应用进程，不启动 frp。

VPS：部署完成后以有 systemd 管理权限的账户运行 `bash tools/start.sh` 或 `bash tools/stop.sh`。两脚本只操作 `ai-dashboard.service`；发布与回滚使用 `deploy/vps/release.py`。

`scripts/service.py` 依赖 Windows Job Objects，仅用于 Windows 开发监督。Linux 的进程归属、停止与自动重启由 systemd 管理，不运行该 Windows 监督器。
