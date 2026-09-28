# 本机进度上报 API

本轮服务使用 Python 3.12、FastAPI 和 SQLite。读取与写入是两个独立应用：读取端 `127.0.0.1:8810` 使用 Basic Auth；写入端 `127.0.0.1:8811` 按项目使用 Bearer token。只有读取端适合被本项目的 frp/Nginx 配置转发。运行数据库、凭据和请求文件应放在不提交到 Git 的 `.runtime/`，正式前端由独立构建输出到 `web/index.html`。空数据库返回 `{"projects":[],"server_time":"..."}`，不会加载示例项目。

## 安装与启动

在 Python 3.12 虚拟环境中运行 `python -m pip install -r requirements.txt`；测试还需 `python -m pip install -r requirements-dev.txt`。先初始化数据库，再为每个项目单独登记：

```powershell
python -m dashboard.manage init --db .runtime/dashboard.sqlite3
python -m dashboard.manage register my-project --db .runtime/dashboard.sqlite3 --token-file .runtime/my-project.token
```

`register` 只在新项目上成功，不会静默替换已登记 token，也不会向终端输出 token。令牌原文只写入指定的全新文件；SQLite 保存 SHA-256 哈希。需要轮换时显式执行：

```powershell
python -m dashboard.manage rotate my-project --db .runtime/dashboard.sqlite3 --token-file .runtime/my-project-new.token
```

轮换成功后旧 token 立即失效。请保护令牌文件的本机访问权限，更新项目侧凭据后再处理旧文件。CLI 不会删除旧文件。

读写进程使用相同的 `DASHBOARD_DB_PATH`。读取进程还使用 `DASHBOARD_WEB_DIR`、`DASHBOARD_VIEW_USERNAME`、`DASHBOARD_VIEW_PASSWORD`。读取口令缺失时拒绝启动。环境变量由本机忽略的运行配置提供，不要把真实值写进 Git 或命令记录。默认数据库路径为 `.runtime/dashboard.sqlite3`，默认前端目录为 `web`。

```powershell
python -m dashboard.server --role read --host 127.0.0.1 --port 8810
python -m dashboard.server --role write --host 127.0.0.1 --port 8811
```

服务只允许绑定 `127.0.0.1`。读取服务的 `/`、`/healthz`、`/api/v1/projects`、`/api/v1/projects/{id}` 均要求 Basic Auth，所有响应标记 `Cache-Control: no-store`。未上报项目的单项查询返回 404。读取应用不注册写入路由、`/docs` 或 `/openapi.json`。写入应用提供无鉴权的通用 `/healthz`，以及本机 `/docs`、`/openapi.json`。

写入端 OpenAPI 的 `components/schemas` 包含完整快照模型，所有本地 `$ref` 都可从文档根解析。快照 PUT 与 revision GET 均声明 Bearer 认证；快照 PUT 另声明必填 `Idempotency-Key` 请求头，因此可在本机 `/docs` 直接填写认证与幂等键后调用。

读取端 Basic Auth 按 UTF-8 处理用户名和密码，401 挑战头也声明 UTF-8；Unicode 凭据与 ASCII 凭据均可使用。

## 快照格式与计量

示例文件为 [sample-snapshot.json](../examples/sample-snapshot.json)。`PUT /api/v1/projects/{project_id}/snapshot` 请求头必须有 `Authorization: Bearer <该项目token>`、`Idempotency-Key: <稳定且唯一的请求ID>` 与 `Content-Type: application/json`。请求体最大 1 MiB，`schema_version` 固定为 1。JSON 拒绝未知字段、重复键和错误类型；日期必须为含时区的 ISO 8601 时间。项目 ID、Wave ID、Task ID 为 1–80 位稳定标识，首位字母或数字，其余可含点、横线、下划线。`Idempotency-Key` 为 1–128 位同类可打印标识，额外允许冒号。

`project.name`、Wave 名、Task 标题和子项标题必填非空。其他说明文字允许空串：短文字最多 240 字符，说明/正文最多 2000 字符，名称最多 160 字符。`waves` 最多 200 个，项目内 Task 合计最多 5000 个，每 Task 子项最多 100 个，`updates` 最多 100 条；每 Task evidence 最多 100 条。`waves`、`tasks`、`children`、`evidence`、`updates` 默认空数组。`status` 默认 `planning`（Task/子项为 `todo`）；`acceptance` 默认 `not_required`；`defined` 默认 `true`；`verified` 默认 `false`；`glyph` 默认 `grid`；`color` 默认 `stone`；一般说明文字默认空串，证据 label 和 text 则必须非空。其他字段和枚举以本机 OpenAPI 为准。

Wave ID 在项目内唯一，Task ID 在整个项目内唯一；`currentWave` 为 `null` 或现有 Wave ID。`defined=false` 的 Wave 没有 Task。`done` Task 必须 `verified=true` 且至少有一条 evidence。项目标为 `complete` 时，必须有非零个有效 Task 且全部完成，没有待细化 Wave 或待处理的验收（`pending`/`rejected`）。`cancelled` Task 退出分母；子项不计数。`progress.done` 为已验证的 `done` Task 数，`progress.total` 为未取消 Task 数，`percent` 对 `done/total*100` 四舍五入，零分母时为 `null`。`unplannedWaves` 单独计算，`pendingAcceptance` 统计项目、Wave 和已完成 Task 的待验收项。实施进度、验收与上报新鲜度是独立信息。

成功响应是 `{"project_id":"my-project","revision":1,"received_at":"...","replayed":false}`。`GET /api/v1/projects/{id}/revision` 使用同一项目 token，登记后未上报时返回 revision 0。读取端的 ProjectView 使用原始 `project` 业务字段及 `id`、`revision`、`receivedAt`、`observedAt`、`progress`；`receivedAt` 是服务接收时间，`observedAt` 是上报方观察时间。读取视图会将已验证的 `observedAt`、Task `updatedAt` 和更新记录 `at` 转为浏览器可解析的扩展 ISO 格式；存储快照与幂等请求哈希不受此显示转换影响。

## 稳定上报与冲突处理

上报前复制示例并填写真实项目状态及当前 `expected_revision`，然后用标准库客户端封存请求。`prepare` 会将项目 ID、快照和幂等键写入新的请求文件；这份文件是网络故障后的重试依据，不能在重试期间改写。

```powershell
python clients/report_progress.py prepare my-project --snapshot .runtime/snapshot.json --request-file .runtime/request-001.json
python clients/report_progress.py send --request-file .runtime/request-001.json --token-file .runtime/my-project.token
```

也可使用 `--token-env 环境变量名` 读取令牌。客户端只允许 `http://127.0.0.1:<端口>` 写入地址，不跟随 HTTP 重定向，也不经代理发送令牌。`send` 对网络故障与 HTTP 5xx 采用有限退避重试，每次使用同一请求体和幂等键。超时或响应丢失后，重复运行同一 `send --request-file`；成功回执会从 SQLite 持久化重放，`replayed=true`，不会重复增加 revision 或事件。令牌错误 401、无效快照 422 和冲突 409 立即停止。

每次**新快照**读取当前 revision，创建新的请求文件和幂等键。若 409 携带 `current_revision`，先查询最新 revision/读取页面并人工核对其他写者的内容，再基于实际最新范围编辑快照及新 `expected_revision`。客户端不会把过期快照自动改成最新 revision。相同键配不同内容也返回 409。项目 token 必须与 URL 中的项目 ID 对应，不能跨项目重放。

服务把完整快照、revision、事件和回执放在同一个 SQLite 事务里，启用 WAL、busy timeout 与 `synchronous=FULL`。成功后保留最近快照、所有简短事件和幂等回执；当前版本不提供全量历史版本回滚。错误采用结构化 JSON，例如 `{"error":{"code":"revision_conflict","message":"..."},"current_revision":2}`，不包含凭据或本机路径。

后端测试：`python -m unittest tests.test_backend tests.test_cli -v`。
