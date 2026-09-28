# 本机进度服务与上线契约

状态：2026-09-28 用户明确授权实施后端、数据库、稳定上报接口、本机上线及 `dashboard.example.com` 的 VPS/frp 配置。首页待验收进度条与待验收标签前景色一致，阻塞进度条与阻塞标签前景色一致。其余已验收的页面和进度口径保持。

## 本轮决定

- Python 3.12 + FastAPI + SQLite，选择 HTTP API + OpenAPI，不另做 MCP。
- 沿用已认可的原生前端并接入真实查询，保留离线可转发 demo；不为接入 API 重写框架。
- 读取服务绑定 `127.0.0.1:8810`，写入服务绑定 `127.0.0.1:8811`。只有读取端口经 frp 转发；VPS 转发端口在现场确认。
- 读取服务启用 Basic Auth（与用户已配置的入口一致），Nginx 同样保留 Basic Auth；避免绕过 Nginx 直接访问转发端口取得数据。凭据仅保存在被忽略的本机运行配置中。
- 写入端口使用每项目独立随机 Bearer token。令牌只保存哈希到 SQLite，原始值通过本地 CLI 写入指定凭据文件，不在输出中打印。禁止使用网页 Basic Auth 作为写入授权。
- 首次公网打开不展示虚构项目。上线后只登记本项目的真实实施进度；其他项目通过文档中的接入流程自行上报。

## 上报协议

`PUT http://127.0.0.1:8811/api/v1/projects/{project_id}/snapshot`

请求头：`Authorization: Bearer <project-token>`、`Idempotency-Key: <stable-unique-request-id>`、`Content-Type: application/json`。

```json
{
  "schema_version": 1,
  "expected_revision": 0,
  "observed_at": "2026-09-28T08:00:00Z",
  "change_note": "完成接入验证",
  "project": {
    "name": "项目名称",
    "shortName": "短名称",
    "description": "项目目标",
    "summary": "当前进展",
    "status": "active",
    "acceptance": "not_required",
    "category": "个人工具",
    "glyph": "book",
    "color": "sage",
    "currentWave": "wave-implementation",
    "waves": [{
      "id": "wave-implementation", "name": "实现", "defined": true,
      "acceptance": "not_required",
      "tasks": [{
        "id": "task-api", "code": "API-01", "title": "实现上报接口",
        "status": "done", "verified": true, "acceptance": "not_required",
        "goal": "稳定接收项目快照", "summary": "检查通过",
        "updatedAt": "2026-09-28T08:00:00Z",
        "evidence": [{"label": "检查", "text": "接口回归通过"}],
        "children": [{"title": "输入校验", "status": "done"}]
      }]
    }],
    "updates": [{"at": "2026-09-28T08:00:00Z", "tone": "done", "text": "接口检查通过", "detail": "API-01"}]
  }
}
```

project ID、Wave ID、Task ID 是稳定标识；前端不能假定 ID 是 `w1` 之类可解析的编号。Wave 序号使用数组顺序。Task ID 在单个项目内唯一，Wave ID 在项目内唯一。最多项目/Wave/Task/子项四层，子项不计数。project.currentWave 可为 null，非空时必须引用存在的 Wave。waves 可为空。defined=false 的 Wave 必须没有 Task。

项目状态：`planning|active|blocked|review|complete`。Task/子项状态：`todo|active|waiting|blocked|done|failed|cancelled`。验收状态：`not_required|pending|accepted|rejected`。glyph 与 color 使用已有前端的有限枚举，禁止注入样式或任意 HTML。Task 可带可选 `blocker`，project 可带可选 `blocker`。所有文字按纯文本显示。除 name 外的说明文字允许空串；可选列表默认空，其他默认值由 OpenAPI 清楚表达。

完成 Task 必须 verified=true，并至少有一条 evidence；项目 complete 要求有效 Task 非零且全部完成、没有待细化 Wave 或待验收事项。取消 Task 退出分母；零分母 percent=null。验收 pending 不抵消已验证的实施完成。

项目规模上限：请求体 1 MiB，200 个 Wave、单项目合计 5000 个 Task、每 Task 100 个子项、updates 最多 100 条。文本长度及 ID 长度设置合理的明确上限，拒绝未知字段和非法日期；日期需包含时区。reported/observed 时间与服务收到时间分别保存，网页标示最后收到的上报。

### 稳定性与冲突

- 以 SQLite 事务写入完整快照；启用 WAL、busy_timeout 与可靠同步设置。保存项目当前 revision、快照、事件和幂等回执。
- 初始 revision=0（项目登记但尚无快照）；首次成功上报返回 revision=1。任何新写入要求 expected_revision 等于当前 revision，否则 409，不覆盖新状态。
- 同一项目相同 Idempotency-Key、相同规范化请求重试，返回原成功回执，即使当前 revision 已继续增加；不重复加版本或事件。
- 相同幂等键不同请求返回 409。身份验证先于回执读取，不能跨项目重放。
- 完整快照代表项目当前范围，变更原因保存到事件。保留最近状态、幂等回执和简短事件；本轮不实现全量版本回滚。
- 成功响应：`{"project_id":"...","revision":1,"received_at":"...","replayed":false}`；重放可将 replayed 标为 true。冲突响应提供 current_revision。错误为结构化 JSON，不暴露令牌、密码或文件路径。

## 查询和应用入口

读取服务：

- `GET /`：真实前端 `web/index.html`；禁止把 demo 样例注入正式构建。
- `GET /healthz`：健康状态，需与读服务鉴权策略一致。
- `GET /api/v1/projects`：`{"projects":[ProjectView],"server_time":"ISO8601"}`。
- `GET /api/v1/projects/{id}`：单个 ProjectView；未上报或不存在为 404。

ProjectView = 上述 project 的所有业务字段，加 `id`、`revision`、`receivedAt`、`observedAt`、`progress`。progress 为 `{done,total,percent,unplannedWaves,pendingAcceptance}`，与既有 JS 口径一致。不得携带报告令牌等私密配置。

写入服务：上述 PUT 快照接口；`GET /api/v1/projects/{id}/revision`（同一 Bearer token 权限）返回 `{"project_id":"...","revision":0}`；`GET /healthz` 仅通用健康结果；本机 `/docs` 和 `/openapi.json` 提供上报协议。写入路由绝不注册到读取服务。读取响应使用 no-store。

## 配置与接入 CLI

服务从环境读取 `DASHBOARD_DB_PATH`、`DASHBOARD_WEB_DIR`、`DASHBOARD_VIEW_USERNAME`、`DASHBOARD_VIEW_PASSWORD`。默认运行文件位于仓库 `.runtime/`，该目录整体忽略。读服务缺少口令时拒绝启动；不得提交或记录真实凭据。

命令入口约定：

- `python -m dashboard.server --role read --host 127.0.0.1 --port 8810`
- `python -m dashboard.server --role write --host 127.0.0.1 --port 8811`
- `python -m dashboard.manage init --db <path>`
- `python -m dashboard.manage register <project_id> --db <path> --token-file <path>`，登记项目并将令牌只写到指定文件；已有项目不意外轮换。
- 提供显式轮换命令，旧 token 立即失效。
- `clients/report_progress.py` 使用 Python 标准库发送请求；读取 token 文件或环境变量，不通过 URL 传令牌。支持固定幂等键重试、明确的 409 处理；网络/5xx 可退避重试，401/422/409 不盲重试覆盖。需记录足够复用同一请求的信息供重试，不在失败时丢弃或改写 expected_revision。

## 真实前端

- 用同一套源码构建 `web/index.html`，配置 mode=live，启动数据为空；demo 构建保留原虚构数据和场景菜单。
- 读取 `/api/v1/projects`，前台每 15 秒刷新，切回前台立即刷新；隐藏页面暂停轮询，串行请求，超时后明确离线，后续恢复不丢筛选或有效下钻路径。
- 不把上报时间改成页面刷新的时间；ISO 时间由浏览器本地化。API 无项目时显示真实空状态；请求失败时显示离线/无法读取，绝不回退到 demo 数据。
- 页面不使用 Basic Auth 密码变量或写入 token，不增加写入控件。移除正式页面上的 DEMO 标记、固定快照时间和演示场景菜单。
- 保持搜索/深层路由一致性；允许合法的任意项目与阶段 ID、无 Wave、无 Task、被后续快照移除的节点。

## 上线与验收

本机独立虚拟环境；持久运行的读服务、写服务和 frpc 由本项目启动脚本/监督进程管理，日志与 PID 存入 .runtime。进程只能停止本项目启动并验证过身份的进程。尽可能配置当前用户登录时自动恢复；不得改变其他项目的服务。

VPS 操作只修改 dashboard.example.com 的必要站点配置和本项目专用转发配置，修改前备份，Nginx 配置检查成功后 reload。保留既有 Basic Auth，提供 HTTPS，并准备本地后端不可达时的静态离线页。frp 使用现有授权连接，不输出认证信息。

验收：核心事务/幂等/鉴权/冲突/输入校验/持久化测试；前端真实 API 和手机尺寸联调；服务重启后数据保留；上报后网页可见；公网未认证 401、认证后 200；写入路由公网不可用；HTTPS 正常；旧站点不受影响。上线只登记本项目真实实施进展。
