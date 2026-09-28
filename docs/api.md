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

## 任务详情怎么写

任务详情中的“任务目标”读取 `task.goal`，“最近进展”读取 `task.summary`。看板原样展示上报内容，不会从验收日期或证据路径自动生成工作说明。两者最多各2000字符，支持换行，作为纯文本显示；使用 `•` 或数字分点即可，无需 Markdown 或 HTML。

- **goal：要达成什么。** 写清解决的问题、影响的功能或使用场景、预期结果，不只重复标题。
- **summary：截至目前具体做了什么。** 按主要工作事项列出，通常2–5项，简单任务可1项。每项写“做了什么 + 带来的结果或影响”，粒度为功能、流程、体验或交付物，不逐文件、函数或代码修改罗列。
- **状态要准确。** 用“已完成 / 进行中 / 待完成”区分事实；新快照保留已完成的主要工作，再更新新增结果及剩余事项。不要用最后一次验收结论覆盖整个任务的工作概述。
- **依据另记。** 日期、测试范围及结果、验收结论、证据路径放在 `evidence`；阻塞原因放在 `blocker`。关键验收结论也可在 summary 末尾简述，但不能替代主要工作说明。
- **以项目事实为准。** 同一 Wave 的各 Task 应分别说明自己的工作，不批量套用同一句验收文案。证据不足时明确写“工作明细待补充”，不能为了凑条数编造内容。该口径不改变进度计量，也不强制拒绝已有的简短报告。

例如，“2026-09-21联合验收通过；R4主观体验并入GRW6。”只说明验收与后续安排，不能说明这个 Task 具体做了什么。应由来源项目查阅对应任务记录，补齐主要工作后重新上报。格式示例见 [sample-snapshot.json](../examples/sample-snapshot.json)；其中内容仅作格式演示，不应直接套用到其他项目。

可将以下要求交给负责上报的项目 agent：

> 上报前逐项核对 Task：goal 说明目标与预期结果；summary 根据本项目的任务记录、实现和验证事实，按主要事项列出具体工作与结果，通常2–5项，简单任务可1项，用换行分隔，不逐文件或函数罗列。保留已完成的主要工作，明确区分已完成、进行中和待完成；不得仅写“验收通过”、日期、阶段代号，也不得给同阶段所有任务套用相同总结。将检查和验收依据放进 evidence，缺少事实时明确说明。先更新项目自身的上报数据源，再读取最新 revision，用新请求文件和幂等键重新上报，避免后续脚本覆盖回旧文案。

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

## 为另一个本机项目接入

在本仓库根目录、使用本项目虚拟环境，先登记一个稳定项目 ID。以下 `my-project` 只是占位，需替换为真实项目。

```powershell
.\.venv\Scripts\python.exe -m dashboard.manage register my-project --db .runtime/dashboard.sqlite3 --token-file .runtime/credentials/my-project.token
```

将 `examples/sample-snapshot.json` 复制到该项目自己的工作目录，填写真实计划和状态；第一次上报 `expected_revision` 为 0。后续可这样查询版本（不会输出令牌）：

```powershell
$projectToken = (Get-Content -Raw .runtime/credentials/my-project.token).Trim()
Invoke-RestMethod -Uri 'http://127.0.0.1:8811/api/v1/projects/my-project/revision' -Headers @{ Authorization = "Bearer $projectToken" }
```

用 `prepare` 把本次快照封存成一个新请求文件，再调用 `send`；网络重试继续发送原文件。客户端是独立的标准库 Python 脚本，其他项目可用其绝对路径调用，无需引入本看板的 Python 包。远程手机只访问查看域名，不持有项目上报 token，也不能用查看账号写入进度。
