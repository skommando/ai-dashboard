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
- [ ] Task 1 实现并审查
- [ ] Task 2 实现并审查
- [ ] Task 3 本机与 VPS 部署
- [ ] Task 4 端到端验证、最终审查与交付

## 已裁决事项

- 保留现有原生前端：用户已认可交互和视觉，接入真实数据不需要重写 Vue。
- 使用完整快照＋revision＋幂等键：接入方可以可靠重试，结构化计划不会出现部分更新。
