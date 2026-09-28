# VPS 生产迁移实施计划

> **For agentic workers:** 使用 superpowers:subagent-driven-development 按责任工作树实施，主 agent 集成与发布；独立审查不得由实现者替代。

**Goal:** 完成统一服务、VPS 数据迁移及安全公开仓库，建立 dev 验证后发布 main 的流程。

**Architecture:** 单个 Basic Auth 保护的 FastAPI 应用，对上报另校验 X-Project-Token。VPS systemd + Nginx；源码 release 与私有 SQLite/环境文件分离。

**Tech Stack:** Python 3.12、FastAPI、SQLite、原生前端、GitHub Actions、systemd、Nginx。

**Spec:** [设计](../specs/2026-09-28-vps-production.md)。用户已确认双凭据、通过验证可发布、MIT、清洗并保留历史、接入方自行按文档迁移；本轮发布授权有效。

## 全局约束与审查重点

- 私密值不输出、不提交；历史审计覆盖 refs/reflogs/不可达对象，公开前重扫。
- Basic 与项目 token 同时验证；写入不存在隐式的旧 Bearer 绕过；不改变快照版本语义。
- 开发不写生产；迁移冻结旧写入并作一致备份，不能用普通文件复制破坏 WAL 一致性。
- 发布绑定明确 SHA，失败恢复上一代码；不能覆盖或删除切换后新增生产数据。
- 不影响共享 frps、其他站点；停用的本项目隧道确认不再监听。

## Task 1：统一服务与接入客户端

负责 `dashboard/api.py`、`dashboard/server.py`、`clients/report_progress.py` 及后端/客户端测试。接口为 `create_app(db_path, web_dir, username, password)`；默认8810。客户端提供 prepare/send/revision，Basic 文件格式为用户名/密码JSON或环境变量，项目token继续独立文件/环境变量。

- [ ] 为双鉴权、统一读写与 HTTPS/redirect/error 写失败测试。
- [ ] 实现最小改动并通过相关后端与 CLI 回归；OpenAPI 声明 AND 鉴权。
- [ ] 独立审查、修复、集成。

## Task 2：VPS 发布和本地开发流程

负责 `deploy/vps/`、`scripts/` 发布/验证工具与相关测试；主 agent 实际执行迁移。以 `/opt/ai-dashboard` 为目标，配置和DB放shared，release不可由服务用户改写；提供可重复部署、状态检查、备份和回滚。

- [ ] 实现固定SHA发布和健康失败回滚测试及脚本；不默认跳过验证。
- [ ] 配置独立Python3.12、systemd、Nginx统一入口与受限文件权限。
- [ ] 停旧写入、备份/迁移/核对、切换；验证后停用旧专用frp与Windows自启。

## Task 3：开源、历史清洗与接入文档

主 agent 负责文档、GitHub和Git清洗；安全子 agent 只读审计。更新README、API参数/返回/错误文档、MIT LICENSE、CONTRIBUTING、SECURITY、忽略规则、CI。现有设计记录涉及私人机器的内容先清理；不公开真实记录截图。

- [ ] 全Git对象与工作目录审计，私有备份后按证据清洗历史及元数据。
- [ ] 完成标准接入文档及新版客户端示例，凭据全部占位。
- [ ] 通过最终脱敏扫描后创建 public `skommando/ai-dashboard`，推送清洁dev/main。

## Task 4：发布与最终验收

- [ ] 本地全套必要测试、Linux检查、独立整体审查及修复。
- [ ] GitHub CI通过，main固定SHA部署；验证实际公网上报、读取、拒绝越权与幂等重放。
- [ ] 验证所有迁移项目/事件/回执保留，手机布局与服务重启。
- [ ] 更新看板本系统任务、交付运行及接入说明，报告证据与真实限制。
