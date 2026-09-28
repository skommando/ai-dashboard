# 项目进度 API 接入规范

版本：API v1 / `schema_version=1`。适用对象：项目服务、脚本及负责更新进度的 AI agent。源码中的 OpenAPI 是字段约束的机器可读契约；本文说明接入顺序、语义与错误处理。

## 1. 服务地址与凭据

生产基址由管理员提供，例如 `https://dashboard.example.com`；不要直接照抄示例域名。开发可用 `http://127.0.0.1:8810`。生产禁止明文 HTTP，不忽略 TLS 证书校验，不跟随携带凭据请求的重定向。

| 配置 | 由谁提供 | 用途与存放 |
| --- | --- | --- |
| `base_url` | 管理员 | 已部署服务的 HTTPS 基址，无额外路径 |
| `project_id` | 管理员与接入方约定 | 稳定项目标识，不能以每次运行的临时名称替代 |
| Basic 用户名、密码 | 管理员私下提供；人工写入 | 所有端点均需要；放仓库外的凭据JSON或环境变量 |
| 项目令牌 | 管理员登记项目后私下提供；人工写入 | 仅对应项目的上报与版本查询；独立令牌文件或环境变量 |

Basic 文件格式为 `{"username":"<人工填写>","password":"<人工填写>"}`；项目令牌文件只含令牌。占位符不能直接使用。禁止把真实值写入源码、快照、请求封存文件、Git、日志、Issue或命令参数。文件路径可以出现在命令中，文件内容不能打印。

请求头：

| Header | 必需范围 | 说明 |
| --- | --- | --- |
| `Authorization: Basic <base64(username:password)>` | 全部 | Base64不是加密，安全性依赖HTTPS；用户名/密码为UTF-8 |
| `X-Project-Token: <项目令牌>` | revision GET、snapshot PUT | 与Basic同时校验，不能用Bearer替代 |
| `Idempotency-Key` | snapshot PUT | 1–128字符；字母/数字开头，其后可含字母、数字、点、下划线、横线和冒号 |
| `Content-Type: application/json` | snapshot PUT | UTF-8 JSON，最大1 MiB |

项目注册与令牌轮换没有公网端点。管理员在VPS应用环境执行 `python -m dashboard.manage register <project_id> --db <私有数据库路径> --token-file <私有新令牌文件>`；显式轮换用 `rotate`。登记不会覆盖已有项目；令牌文件必须为新文件，命令不会输出令牌。数据库只保存令牌哈希，轮换立即使旧令牌失效。

## 2. 端点总览

路径均相对于 `base_url`。

| 方法与路径 | 认证 | 作用 | 成功响应 |
| --- | --- | --- | --- |
| `GET /` | Basic | 手机/桌面只读页面 | HTML |
| `GET /healthz` | Basic | 服务探测 | `{"status":"ok"}` |
| `GET /api/v1/projects` | Basic | 全部已上报项目及服务时间 | `{projects:[ProjectView],server_time:"..."}` |
| `GET /api/v1/projects/{project_id}` | Basic | 单个项目最近快照视图 | `ProjectView` |
| `GET /api/v1/projects/{project_id}/revision` | Basic + 项目令牌 | 查询当前版本，首次未上报为0 | `{project_id:"...",revision:0}` |
| `PUT /api/v1/projects/{project_id}/snapshot` | Basic + 项目令牌 | 原子替换该项目完整快照 | `{project_id,revision,received_at,replayed}` |
| `GET /openapi.json`、`GET /docs` | Basic | JSON契约、交互文档 | OpenAPI JSON / HTML |

路径参数 `project_id` 为1–80字符，首位字母或数字，其后可含字母、数字、点、横线和下划线。必须匹配管理员登记的ID与令牌。未知项目的读取返回404，未登记/错误令牌不能上报。

## 3. 快照请求体

PUT 是**全量替换**，不是增量合并；遗漏旧Wave/Task会使其不再出现在最新快照，更新前必须以本项目完整且真实的计划为依据。

| 顶层参数 | 类型 | 必需 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | integer | 是 | 固定为1 |
| `expected_revision` | integer | 是 | 当前已知版本，≥0；CAS校验防止旧数据覆盖 |
| `observed_at` | string | 是 | 本次观察时间，含时区ISO 8601 |
| `change_note` | string | 是 | 本次变化摘要，最多2000字符；不含凭据 |
| `project` | object | 是 | 完整Project，见下表 |

### Project

| 参数 | 类型 / 默认 | 说明 |
| --- | --- | --- |
| `name` | string，必需 | 非空，最多160字符 |
| `shortName`, `category` | string / 空 | 最多240字符 |
| `description`, `summary` | string / 空 | 目标、项目概述，各最多2000字符 |
| `status` | enum / `planning` | `planning`、`active`、`blocked`、`review`、`complete` |
| `acceptance` | enum / `not_required` | `not_required`、`pending`、`accepted`、`rejected` |
| `glyph` | enum / `grid` | `grid`、`book`、`receipt`、`image`、`bookmark`、`globe`、`monitor` |
| `color` | enum / `stone` | `sage`、`sand`、`plum`、`blue`、`stone` |
| `currentWave` | string或null / null | 当前Wave ID，非null时必须已存在 |
| `blocker` | string或null / null | 阻塞说明，最多2000字符 |
| `waves` | array / [] | 最多200个Wave |
| `updates` | array / [] | 最近进展记录，最多100条；只保留要展示的窗口 |

### Wave、Task、子项与依据

| 对象 | 参数 | 类型 / 默认 | 说明 |
| --- | --- | --- | --- |
| Wave | `id`, `name` | string，必需 | ID规则同project_id；name非空且≤160字符 |
| Wave | `defined` | boolean / true | false表示尚未细化，此时tasks必须为空 |
| Wave | `acceptance` | enum / not_required | 同Project验收枚举 |
| Wave | `tasks` | array / [] | 全项目合计最多5000个Task |
| Task | `id`, `title` | string，必需 | ID全项目唯一；title非空且≤160字符 |
| Task | `code` | string / 空 | 展示编号，≤240字符 |
| Task | `status` | enum / todo | todo、active、waiting、blocked、done、failed、cancelled |
| Task | `verified` | boolean / false | 验证是否通过；done必须true且有evidence |
| Task | `acceptance` | enum / not_required | 同Project验收枚举 |
| Task | `goal`, `summary` | string / 空 | 任务目标与具体工作概述，各≤2000字符 |
| Task | `updatedAt` | string或null / null | 含时区ISO时间 |
| Task | `blocker` | string或null / null | 阻塞说明，≤2000字符 |
| Task | `evidence` | array / [] | 最多100条，每条label非空≤240，text非空≤2000 |
| Task | `children` | array / [] | 最多100个子项；每项title必需、非空≤160；status同Task，默认todo |
| Update | `at`, `tone`, `text` | string，必需 | at为含时区ISO时间；tone为todo/active/waiting/blocked/done/failed/review/complete；text≤2000 |
| Update | `detail` | string / 空 | ≤2000字符 |

所有对象拒绝未知字段、重复JSON键及类型错误。Wave ID项目内唯一；Task ID整个项目内唯一。不要传主观计算的percent，服务根据任务事实计算。

### 任务文字标准

- `goal`：要解决的问题、影响的使用场景和预期结果，不只重复标题。
- `summary`：截至目前具体做了什么，按主要事项列出工作及结果，通常2–5项，简单任务可1项。用 `•` 或编号和换行分隔，页面保留分行；这是纯文本，不解释HTML/Markdown。
- 明确“已完成 / 进行中 / 待完成”。每次更新保留已完成的主要工作，不能用最新验收句子覆盖全部概述；同一Wave的各Task分别说明，不套用同一句结论。
- 说明功能、流程、体验或交付物，不逐文件、函数或代码修改列清单。测试与验收依据写入evidence，阻塞写入blocker。证据不足时明确“工作明细待补充”，不能编造。

完整可验证样例见 [sample-snapshot.json](../examples/sample-snapshot.json)。示例只解释格式，不代表你的项目已经完成这些工作。

## 4. 响应与计量

首次成功PUT例子：

```json
{"project_id":"my-project","revision":1,"received_at":"2026-09-28T08:00:00Z","replayed":false}
```

同一幂等键和相同内容重试会返回原revision/received_at，`replayed=true`，不会新增版本。整个快照、版本、事件和回执在同一个SQLite事务提交，重启不丢失已成功回执。

ProjectView含原Project字段，以及 `id`、`revision`、`receivedAt`（服务接收时间）、`observedAt`（上报观察时间）、`progress`。读取时间被规范化为浏览器可解析的ISO表示，存储与幂等内容哈希不受影响。

```json
{"done":3,"total":4,"percent":75,"unplannedWaves":1,"pendingAcceptance":0}
```

Task等权：`cancelled`退出分母，子项不计数；done且verified的Task计完成。percent四舍五入，零分母为null；未细化Wave单列。验收与实施分开。Project标complete要求存在Task且全部完成、无未细化Wave、无pending/rejected验收。

## 5. 错误和重试

应用错误格式：

```json
{"error":{"code":"revision_conflict","message":"expected_revision differs from current revision"},"current_revision":2}
```

| HTTP | 常见含义 | 接入方动作 |
| --- | --- | --- |
| 401 | Basic缺失/错误，或项目令牌缺失/错误/不匹配 | 停止重试，核对两种凭据；Basic错误可能由Nginx返回HTML |
| 404 | 项目尚无快照或路径不存在 | 核对ID；首次上报前用revision端点，不靠404推断版本 |
| 409 | `revision_conflict`或`idempotency_conflict` | 读取最新版本/快照，核对其他写者与真实范围，再创建新快照和新键；不能只把版本号改大重发 |
| 413 | 超过1 MiB | 缩减内容，不能删除必要计划来假造进度 |
| 415 | Content-Type不支持 | 使用application/json |
| 422 | 参数/快照/幂等键校验失败 | 按OpenAPI修正类型、字段、标识、完成依据等 |
| 5xx、网络超时 | 服务/代理/网络暂时不可用 | 有限退避，原请求体与原幂等键重试；不能假设失败就没有入库 |

所有响应不可缓存。不要记录带认证头的完整请求；错误处理不能输出凭据。反向代理可能返回HTML错误，客户端应首先识别HTTP状态，不假设每个错误都是JSON。

## 6. 标准库客户端与AI执行步骤

`clients/report_progress.py` 可通过绝对路径从其他项目调用，无需安装看板依赖。以下从仓库根执行；路径为示例，将它们换成仓库外的真实私有路径：

```powershell
# 1. 查询当前revision（登记后未上报为0）
python clients/report_progress.py revision my-project --base-url https://dashboard.example.com --basic-auth-file <私有Basic文件> --token-file <私有项目令牌文件>

# 2. 更新项目自身的数据源，填写完整快照及刚确认的expected_revision
# 3. 封存为新的请求文件，不把凭据放进该文件
python clients/report_progress.py prepare my-project --snapshot <快照文件> --request-file <新的请求文件>

# 4. 发送；超时后重复这条命令，继续用原请求文件
python clients/report_progress.py send --base-url https://dashboard.example.com --basic-auth-file <私有Basic文件> --token-file <私有项目令牌文件> --request-file <请求文件>
```

也可使用 `--basic-user-env <变量名> --basic-password-env <变量名> --token-env <变量名>`，只在命令参数中传变量名。不要把文件和环境凭据方式混用。`--retries`为0–10，默认4；只对网络问题和5xx重试，4xx立即停止。请求不经环境代理、不跟随重定向。

AI接入检查单：领取配置 → 查询版本 → 从源项目记录整理事实 → 核对goal/summary → 检查全量范围和done依据 → prepare新文件 → send → 读取服务快照确认revision/任务内容。遇到缺少凭据或工作证据应明确说明，不能猜测或编造。

## 7. 从旧本机服务迁移

生产应用与SQLite现位于VPS，开发电脑关闭不影响查看。现有项目ID、令牌哈希、快照、revision和幂等回执通过数据库迁移保留；未被要求轮换的项目令牌可继续使用。

接入方需要：更新客户端；将旧 `http://127.0.0.1:8811` 改为管理员提供的HTTPS基址；补充Basic凭据；项目令牌改发 `X-Project-Token`。不要再发送 `Authorization: Bearer`。本轮不自动修改其他项目仓库。迁移后先查询revision，不能从0重建已有项目。
