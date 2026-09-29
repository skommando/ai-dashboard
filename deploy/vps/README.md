# VPS 发布入口

`release.py` 只部署显式指定、且当时等于 GitHub `main` 的完整 SHA。应用目录固定建议为 `/opt/ai-dashboard`：`repo` 是仅 root 可读的 Git 仓库，`releases/<SHA>` 是 root 拥有的发布目录，`current` 是原子切换的符号链接，`shared` 保存 SQLite、环境文件、凭据与备份，`runtime/python` 保存独立安装的 Python 3.12。脚本不安装系统包或 Python，不读取或更改共享 frps。

先由部署人员准备一个可执行的 Python 3.12，例如 `/opt/ai-dashboard/runtime/python/bin/python3.12`；准备已有TLS站点并移除旧Basic Auth。站点配置路径、include 路径、站点静态根目录和 Nginx 可执行文件都必须在命令中显式传入。include 使用当前站点已包含的项目 include 路径；脚本也可在站点的 `#REWRITE-END` 后插入该 include。`/.well-known/acme-challenge/` 保留供证书续期，网页登录与会话由应用处理。

首次迁移先停止旧本机写入和上报服务，用 Python `sqlite3.Connection.backup()` 创建一致副本，做 `PRAGMA integrity_check` 并核对项目、事件、回执数量和各项目 revision。通过加密传输把副本放入 `/opt/ai-dashboard/shared/data/dashboard.sqlite3`；`shared/data` 应为 `ai-dashboard:ai-dashboard`、`0700`，数据库为 `ai-dashboard:ai-dashboard`、`0660`，使 SQLite 可建立 WAL/SHM 文件。不要只复制仍在使用中的 WAL 主文件。然后由 root 创建 `/opt/ai-dashboard/shared/dashboard.env`，设置 `root:ai-dashboard` 和 `0640`。格式为每行一个 `KEY=value`，有空格或特殊字符时用单引号包住值：

```ini
DASHBOARD_DB_PATH=/opt/ai-dashboard/shared/data/dashboard.sqlite3
DASHBOARD_WEB_DIR=/opt/ai-dashboard/current/web
DASHBOARD_LOGIN_USERNAME='填写网页登录用户名'
DASHBOARD_LOGIN_PASSWORD='填写网页登录复杂密码'
DASHBOARD_SESSION_SECRET='填写至少32字符的独立随机密钥'
```

首次准备目录可用以下命令；`<已传输的一致性备份>` 和 `<root私有环境文件>` 均是部署人员事先准备的私有文件：

```bash
install -d -o root -g root -m 755 /opt/ai-dashboard
install -d -o root -g ai-dashboard -m 750 /opt/ai-dashboard/shared
install -d -o ai-dashboard -g ai-dashboard -m 700 /opt/ai-dashboard/shared/data
install -d -o root -g root -m 700 /opt/ai-dashboard/shared/credentials /opt/ai-dashboard/shared/backups
install -o ai-dashboard -g ai-dashboard -m 660 <已传输的一致性备份> /opt/ai-dashboard/shared/data/dashboard.sqlite3
install -o root -g ai-dashboard -m 640 <root私有环境文件> /opt/ai-dashboard/shared/dashboard.env
```

用来自已审查 `main` 提交的 `deploy/vps/` 工具，在 VPS 以 root 发布：

```bash
python3 deploy/vps/release.py deploy \
  --repo-url https://github.com/OWNER/REPOSITORY.git \
  --sha <经审查的完整main-SHA> \
  --python /opt/ai-dashboard/runtime/python/bin/python3.12 \
  --site /path/to/site.example.invalid.conf \
  --include /path/to/view-dashboard.locations.inc \
  --site-root /path/to/site.example.invalid \
  --nginx /path/to/nginx
```

脚本先校验环境、GitHub main SHA、源码和锁定依赖，再备份数据库，安装 systemd 单服务，切换 `current`，探测公开健康接口，最后检查并重载 Nginx。服务只监听 `127.0.0.1:8810`。发布中断会恢复上一代码和站点配置，不会用旧数据库覆盖已接收的新上报。备份位于 `shared/backups`，仅 root 可读。

代码回滚使用已有 release，保留当时的生产数据库：

跨认证协议切换成功后，该命令只接受已包含会话认证的 release。旧 Basic 版本的配置与上报客户端都不兼容本版，脚本会提前拒绝。首次发布失败仍按现场备份自动恢复原站点和原服务；若今后确需恢复旧协议，须先冻结写入，由管理员从 root 私有备份同时恢复旧站点 include、旧登录环境和旧客户端调用方式，并核对 HTTPS 鉴权。不能只换代码或用旧数据库覆盖新上报。

```bash
python3 deploy/vps/release.py rollback --sha <先前发布的完整SHA>
```

迁移切流并完成公网鉴权、上报、回执重放和重启持久化验证后，再单独停用本项目专用 frps 和旧 Windows 自启任务；共享 frps 及其他站点不属于本脚本。若回滚后数据库格式与旧代码不兼容，先冻结写入并评估备份及已接收记录，不能直接覆盖生产数据库。
