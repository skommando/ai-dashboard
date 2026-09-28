# 运行、备份与恢复

## 开发和生产分离

开发使用本地 `dev` 源码和独立数据库；生产在VPS `/opt/ai-dashboard`，运行 `main` 固定提交。源码从GitHub同步，数据库、原始令牌与环境文件永不经Git同步。主机地址、真实域名、账号密码由部署者在仓库外配置，文档只保留通用示例。

启动停止入口见 [tools](../tools/README.md)，生产部署步骤见 [VPS部署](vps-deployment.md)。旧本机读取/写入/frpc三进程链路不再作为生产入口。

## 生产目录

| 目录 | 作用 |
| --- | --- |
| `/opt/ai-dashboard/repo` | GitHub源码缓存 |
| `/opt/ai-dashboard/releases/<commit>` | 固定版本代码和虚拟环境 |
| `/opt/ai-dashboard/current` | 当前release软链接 |
| `/opt/ai-dashboard/runtime/python` | 独立Python3.12解释器 |
| `/opt/ai-dashboard/shared` | 受限的SQLite、配置、凭据及备份 |

服务使用低权限 `ai-dashboard` 用户，代码由管理员拥有。`dashboard.env` 至少设置 `DASHBOARD_DB_PATH`、`DASHBOARD_WEB_DIR`、`DASHBOARD_VIEW_USERNAME`、`DASHBOARD_VIEW_PASSWORD`。配置文件及SQLite不可公开下载。Nginx的查看凭据与应用Basic一致；写入额外校验项目令牌。

## 备份与恢复

SQLite启用WAL。在线备份使用SQLite backup API，不在服务写入时只复制主数据库文件；副本执行 `PRAGMA integrity_check`。备份保持和原库同等访问限制。

发布工具在切换版本前备份数据库，保留上一release。应用启动或健康检查失败时恢复上一代码/服务；**代码回滚不自动恢复旧数据库**，否则会丢失切换后已经接收的上报。确需数据恢复时先停止写入、保存当前完整库，再核对所有新增版本与回执，明确选择恢复点。

迁移旧本机数据时先冻结旧写入，使用一致副本核对projects/events/receipts的行数、各项目revision和SQLite完整性，再切换Nginx。只停用本应用的旧计划任务与专用frps，不影响共享服务。

## 运行检查

```sh
systemctl status ai-dashboard.service --no-pager
journalctl -u ai-dashboard.service --since '10 minutes ago' --no-pager
ss -ltn '( sport = :8810 )'
```

应用仅监听 `127.0.0.1:8810`。进程存活不等于公网可用，发布后还需通过实际域名验证TLS、Basic认证、项目令牌、读取、上报与幂等重试。日志不得含认证头或请求正文。查看端15秒刷新，可在网络恢复后继续读取；项目上报时间与页面刷新时间分别显示。
