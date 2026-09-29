# VPS 部署与发布

本部署使用单个 FastAPI 服务与 SQLite，默认目录 `/opt/ai-dashboard`。Nginx提供HTTPS；网页登录与180天会话由应用校验，项目版本查询和上报仅需项目令牌。无需frp。示例域名和服务器路径需部署者替换，生产秘密只能人工写入私有配置。

## 1. 前置条件

- Linux、systemd、Git、Nginx、Python3.12；现有HTTPS站点和证书。
- 系统账户 `ai-dashboard`，禁止交互登录。部署用管理员权限，应用进程用该低权限账户。
- 应用端口 `127.0.0.1:8810` 空闲；公网只开放HTTPS入口。
- 独立Python可安装在 `/opt/ai-dashboard/runtime/python`。若系统没有3.12，可使用校验过的固定版本运行时；本轮采用 Astral python-build-standalone CPython3.12.14。其为[uv使用的发行方式](https://docs.astral.sh/uv/guides/install-python/)，不替换系统Python。下载后核对发布者SHA-256，再解包到应用目录。

Nginx站点应有443 TLS监听和 `#REWRITE-END` 插入标记，移除旧的 `auth_basic`；发布器在标记之后加入项目include。已有根location若冲突，先按本模板整理。示意：

```nginx
server {
    listen 443 ssl;
    server_name dashboard.example.com;
    ssl_certificate /etc/ssl/dashboard/fullchain.pem;
    ssl_certificate_key /etc/ssl/dashboard/privkey.pem;
    #REWRITE-END
}
```

网页登录凭据不放在宝塔密码文件，而放在应用的仓库外私有环境文件。证书续期所需ACME challenge路径保持可访问，它不是应用API。

## 2. 私有数据准备

目录布局和恢复原则见[运行说明](operations.md)。`shared` 根由管理员持有、组为ai-dashboard，权限0750；`shared/data`由服务用户持有、权限0700，以便SQLite创建WAL/SHM。凭据与备份目录只允许管理员访问。

在 `shared/dashboard.env` 人工填入四个变量，使用简单的 `KEY="value"` 格式；文件root拥有，组ai-dashboard，权限0640。不使用shell命令替换或额外变量：

```dotenv
DASHBOARD_DB_PATH="/opt/ai-dashboard/shared/data/dashboard.sqlite3"
DASHBOARD_WEB_DIR="/opt/ai-dashboard/current/web"
DASHBOARD_LOGIN_USERNAME="<人工填写的查看账号>"
DASHBOARD_LOGIN_PASSWORD="<人工填写的复杂密码>"
DASHBOARD_SESSION_SECRET="<人工填写的独立随机密钥，至少32字符>"
```

初次空部署可在data下创建空SQLite文件，让应用初始化表；**不得覆盖已经存在的数据库**。从旧系统迁移时：冻结旧写入，用SQLite backup API生成副本并做integrity_check，通过SSH/SCP传入data目录，权限设为服务用户可读写。核对项目revision及projects/events/receipts记录，不能在写入期间只复制主文件而遗漏WAL。

## 3. 验证开发提交并发布main

按[贡献流程](../CONTRIBUTING.md)在dev测试、审查并推送，等待GitHub CI通过，再合入main。使用仓库外开发环境执行：

```sh
python scripts/release.py --sha <当前完整commit-SHA>
```

工具要求当前HEAD与SHA相同、工作区干净，构建并执行Python/Node检查；记录默认在仓库外的用户状态目录，也可用 `--record <仓库外记录文件>` 指定。只有所有者明确要求时才能加 `--skip-tests --reason "明确授权的原因"`。手动跳过不会自动免除备份、秘密检查及对发布目标的核对。

生产只拉取GitHub当前main对应的明确SHA，不跟踪dev。先将该版本的部署脚本放到VPS管理员私有暂存目录，然后执行（参数为通用示例）：

```sh
python3 /root/dashboard-bootstrap/deploy/vps/release.py deploy \
  --sha <main完整commit-SHA> \
  --repo-url https://github.com/skommando/ai-dashboard.git \
  --python /opt/ai-dashboard/runtime/python/bin/python3.12 \
  --site /etc/nginx/sites-available/dashboard.conf \
  --include /etc/nginx/dashboard.locations.conf \
  --site-root /var/www/dashboard \
  --nginx /usr/sbin/nginx
```

bootstrap解释器需Python3.10+，可直接用上面的外置Python3.12。路径必须为无空格/控制符的安全绝对路径。发布器会预检、拉取main并核对SHA、创建release及锁定依赖的venv、备份SQLite和配置、安装systemd单元、切换current、检查公开的健康端点，然后检查并重载Nginx。失败恢复先前代码、站点和服务启用状态；保留最新生产数据库，不盲目覆盖回旧副本。升级旧Basic版本时可短暂保留旧环境变量供回滚，成功验证后删除。

## 4. 验收和停用旧链路

用实际HTTPS域名检查：未登录首页跳转登录页，错误账号/密码统一返回“功能未开发”，登录后读取成功；项目令牌可独立读取本项目、查询版本和上报，错误令牌被拒绝，同请求重试返回原回执。核对迁移前后的记录及版本，验证服务重启后登录会话和进度仍存在。

随后停止并禁用旧的本项目Windows计划任务、frpc与专用frps。不要停止共享frps或修改其他站点。移除旧生产数据前在仓库外保留受限备份，接入方按[API迁移步骤](api.md#7-从旧本机服务迁移)切换。

## 5. 启停和回滚

```sh
bash /opt/ai-dashboard/current/tools/start.sh
bash /opt/ai-dashboard/current/tools/stop.sh
# 回滚到已存在的上一个release，只切换代码，不覆盖数据库
/opt/ai-dashboard/runtime/python/bin/python3.12 /root/dashboard-bootstrap/deploy/vps/release.py rollback --sha <上个release的完整SHA>
```

参见[tools说明](../tools/README.md)。每次发布保留固定版本、备份和验证记录；数据恢复与代码回滚是两件事。若切换后已有新上报，需要冻结写入并核对新增数据，才能决定是否恢复某个旧数据库副本。
