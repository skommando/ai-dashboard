# VPS 生产迁移与公开发布设计

## 已确认范围

用户要求统一读写服务，将应用及 SQLite 迁往 VPS 的 `/opt/ai-dashboard`，取消本应用的 frp 依赖。源码通过 GitHub `skommando/ai-dashboard` public 仓库同步，MIT 许可；本地 `dev` 开发，验收后发布 `main`。用户确认：通过约定测试和独立审查即可发布，不必再等待确认；只有用户明确要求时允许跳过测试。其他项目按新版客户端和文档自行切换，不在本轮跨仓库改写。

公开前检查当前文件、全部 Git 对象、refs/reflogs/不可达对象及元数据，保留并清洗历史。真实凭据、数据库、私人部署记录不得进入 public Git；运行所需秘密继续保留于受限的私有目录，任何报告只含脱敏结果。

## 应用与鉴权

- Python 3.12、FastAPI、SQLite；单个 ASGI 应用默认监听 `127.0.0.1:8810`，由 Nginx 提供 HTTPS。
- 查看页面、读取 API、OpenAPI、健康检查均需 `Authorization: Basic ...`。项目版本查询和快照 PUT 另需 `X-Project-Token`；两种鉴权是 AND 关系，不能用查看凭据写入，也不能仅凭项目令牌绕过查看凭据。
- 保留 `/api/v1/projects`、`/api/v1/projects/{project_id}`、`/api/v1/projects/{project_id}/revision`、`/api/v1/projects/{project_id}/snapshot` 的现有语义。快照结构、revision、幂等回执及任务计量不变。没有公开注册项目/轮换令牌接口，管理员仍通过管理 CLI 操作。
- OpenAPI 声明 Basic 与头部 apiKey 的联合鉴权，并提供完整请求和响应模型、状态码。API 接入文档按端点、方法、认证、参数、约束、请求/响应例子、错误处理和重试流程组织，包含 AI 接入清单与人工填入凭据的位置。
- 标准库客户端支持公网 HTTPS（证书和主机名验证）、本机回环 HTTP；禁止 URL 内嵌凭据、跳转、外部明文 HTTP。秘密仅从文件或环境变量读取，不出现在命令参数、请求封存文件或错误输出。提供 revision 查询便于 AI 操作，冲突不得自动重基。

## 部署、数据及发布

- `/opt/ai-dashboard/repo` 拉取 GitHub 源码；`releases/<commit>` 保存固定版本；`current` 指向已验收 release；`shared` 保存 SQLite、私有环境文件、凭据与一致性备份；独立 Python runtime 也在应用目录下。
- systemd 使用现有低权限 `ai-dashboard` 用户，环境文件仅授权管理与服务账户读取；代码不可由服务账户改写。主机重启后自动启动。
- 开发数据库独立于生产；不从 Git 同步数据库或配置。生产从经验证的 `main` 固定 SHA 发布，保留上一 release；发布前 SQLite backup，切换失败恢复代码与服务。回滚不得无提示丢弃已经接收的生产写入。
- 首次迁移在短暂冻结本机写入后使用 SQLite backup API 建立一致性副本，保存项目、令牌哈希、版本、事件与幂等回执。先传输至私有目录并验证完整性/计数，再启动 VPS 服务和切换 Nginx。成功后停止并禁用本项目 Windows 自启与专用 frps；共享 frps 和其他站点不变。
- 当前项目令牌如未发现泄露则保留，来源项目更换 base URL 并增加 Basic 凭据即可。若发现真实泄露，清历史之外还须轮换并记录接入影响。
- 发布脚本不后台自动拉取最新代码；dev 测试与 GitHub CI 通过后推进 main，再部署该提交。跳过测试需显式开关与原因并留记录，不能以工具默认值默许跳过。

## 验收

1. 单服务 Basic + 项目 token 鉴权矩阵、Unicode 凭据、无效输入、错误响应、版本冲突、幂等重放、存储恢复及 OpenAPI 引用通过。
2. HTTPS 客户端正确发送双凭据，不跟随跳转、不泄露秘密、失败后原请求重试。
3. Linux 部署/回滚脚本通过验证；私有数据在源码外；生产由 systemd 托管并仅本地监听应用端口。
4. 全部 Git 历史与最终公开 refs 的敏感信息检查通过；开源许可、贡献/安全说明、CI 与 dev/main 发布规则齐备。
5. 公网实际验证鉴权、读写、版本冲突与重试；数据库迁移前后记录对应，原幂等回执仍可重放；页面在手机尺寸保持可用。
6. 本系统在看板登记本轮迁移任务并持续上报，只有实际验证完成才标记完成。
