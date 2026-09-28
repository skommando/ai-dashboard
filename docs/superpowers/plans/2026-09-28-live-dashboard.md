# 本机后端与公网只读看板实施计划

> 使用 subagent-driven-development；用户已授权本机服务、frp、dashboard.example.com VPS 配置及子 agent 协同，直接执行到上线验证。主 agent 负责集成和部署。

**Spec:** [运行契约](../specs/2026-09-28-live-dashboard-contract.md)

## Global Constraints

- 保持已认可页面；待验收/阻塞进度条与对应标签同色。
- Python + SQLite，HTTP API + OpenAPI；公网只读，本机独立写入入口按项目鉴权。
- Task 等权且子项不计数；不混淆验收、实施完成与数据新鲜度。
- 原子快照、版本冲突和幂等重试；秘密不进 Git、不输出日志。
- 同一工作目录只有一个写入者；前后端采用独立工作树，主目录由主 agent 集成。
- 用户已授权部署；不修改无关服务，不向他人发消息，不创建远端 Git 仓库。

## 任务与接口

| Task | 所有权 | 输出与验收 |
| --- | --- | --- |
| 1 后端/数据库/上报客户端 | 后端工作树：dashboard/、clients/、examples/、requirements*.txt、pyproject.toml、tests/test_*.py、docs/api.md | 严格按契约实现；测试覆盖重启、并发、重试、乱序、跨项目鉴权和写端隔离；可用 OpenAPI |
| 2 前端接入与颜色 | 前端工作树：demo/src/、demo/index.html、demo/mobile.html、scripts/build-demo.cjs、scripts/check-*.cjs、web/、tests/*.cjs | 保留 demo，构建真实 web；无样例回退、可恢复轮询、颜色一致、真实时间和空状态 |
| 3 本机/VPS 部署 | 主 agent 协调独立部署任务：scripts/*部署脚本、deploy/、运行配置、VPS view 站点 | 备份、校验、服务管理、frp、TLS、Basic Auth、静态离线页 |
| 4 集成/审查/上线验证 | 主 agent＋独立 reviewer | 前后端契约一致、真实项目上报、公开读取和写入隔离、重启持久化、文档与检查点 |

## 预检

| 对接 | 约束/结论 |
| --- | --- |
| 1→2 | GET /api/v1/projects 的 ProjectView 使用约定字段；任意合法 Wave ID，不解析 w1 序号 |
| 1→3 | 环境变量与 python -m dashboard.server / manage 是固定进程入口；读写分端口 |
| 2→3 | 正式资源固定为 web/index.html；demo 另行保留 |
| 1 内部 | 幂等回执先查后比 revision，但必须先按项目鉴权；同一事务完成快照和回执 |
| 2 内部 | mode=live 无样例/假时间；所有显示内容仍只读 |
| 3 内部 | 使用现有 Basic Auth，与应用端鉴权一致；仅变更本项目专用配置 |

## Review Focus

- 提交成功而响应丢失后重试，不能重复加版本或退回旧快照。
- 两个不同写入者携带同一 revision，不得静默覆盖。
- 公开读取入口或转发端口不能提供写 API 或泄露鉴权信息。
- 服务离线、恢复和节点被移除后，前端保留合理浏览上下文而不显示假数据。
- 新旧进程、端口与配置的生命周期不得影响 cc_remote_workspace 或其他站点。

## 进展

- 2026-09-28 基线 ac0a14b；主分支 feat/local-dashboard；部署勘察正在只读执行。
- [x] Task 1 实现并审查
- [x] Task 2 实现并审查
- [x] Task 3 本机与 VPS 部署
- [x] Task 4 端到端验证、最终审查与交付

## 已裁决事项

- 保留现有原生前端：用户已认可交互和视觉，接入真实数据不需要重写 Vue。
- 使用完整快照＋revision＋幂等键：接入方可以可靠重试，结构化计划不会出现部分更新。
- VPS 改为专用 frps，控制端口8072、代理端口仅回环8083：消除防火墙服务停止/失败时的公开监听边界问题，且不影响原共享 frps；代价是增加一个轻量独立服务。

## 检查点

- 后端：主树 `27e3e1f`，OpenAPI/Unicode Basic 修复 `7e9022e`；后端15/15，独立审查发现的两项已修复并通过限定复核。
- 前端：主树 `641d331`；Node11/11、浏览器模拟HTTP回归通过；独立审查通过。正式端到端将使用合法描述性ID补足模拟数据中含斜线ID的代表性限制。
- 运行工具：主树 `366576c`；初轮7/7，正在修复启动确认、心跳频率和子进程创建归属窗口。
- VPS 初稿 `f8e5454` 尚未应用，正在按专用frps方案替换并完善回滚；既有view认证与TLS已验证，匿名401、提供的账号认证200。
- 本机 `.venv` Python3.12.10 已就绪；固定依赖记录到 requirements-lock.txt。22项合并Python测试通过，有Starlette针对httpx测试客户端的弃用提示，无运行测试失败。
- 本机 `AI Dashboard - dashboard.example.com` 当前用户登录任务已注册但尚未启动。私有配置、独立frp凭据和本项目token保存在忽略的 `.runtime/`，目录ACL仅当前用户及SYSTEM。
- 首个真实快照已准备，沿实施计划4个Task计数：后端、前端已完成，上线与联调仍进行中。尚未向生产库写入展示快照。

## 最终检查点

- Task1/2/3 的独立审查问题均已修复；最终Astra整体验证提出的计量、验收文案和日期问题在 `0859478` 修复并通过限定复核。
- 实际venv的pythonw身份差异在 `b75b759` 修复；合并后Python36/36、Node12/12通过。
- VPS专用frps已安装且active/enabled，控制8072、回环代理8083；查看域名已上线。原共享frps和其他站点配置未变。
- 本机当前用户登录任务已启动，reader/writer/frpc持续运行；完整停启和回执持久化、503离线页与恢复均已验证。
- 真实公网截图揭示长摘要375px挤出及旧检测基准缺陷，`fceb33f` 修复Grid收缩与视口检测，真实375/390/430px重测通过。
- 真实上报经网页自动刷新展示；QA发现后曾按原因重新打开，修复后最终revision7、4/4 Task完成。没有通过修改分母制造完成率。
- 详细证据与边界见 `docs/verification/2026-09-28-live-dashboard.md`。部署使用主目录，隔离工作树的实现均已集成；不需要新建主会话接力。
