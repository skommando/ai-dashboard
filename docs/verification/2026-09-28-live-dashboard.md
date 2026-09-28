# 本机进度服务与公网看板交付验证

日期：2026-09-28。代码实现截至 `fceb33f`；公网入口为 [dashboard.example.com](https://dashboard.example.com)。本轮已完成后端、SQLite、OpenAPI、真实前端、Windows 常驻与 VPS 只读部署，没有接入模型交互。

## 当前结果

- 本机读服务 `127.0.0.1:8810`、上报服务 `127.0.0.1:8811` 与 frpc 由本项目监督器运行；当前用户登录任务 `AI Dashboard - dashboard.example.com` 已注册并处于运行状态。
- VPS 独立 `ai-dashboard-frps.service` 为 active/enabled；8072 为控制端口，8083 仅监听 `127.0.0.1`。Nginx 保留既有 HTTPS 和 Basic Auth。
- 生产库仅登记并上报本项目 `ai-dashboard`，最终快照 revision=7，实施任务 4/4 完成。未把演示项目注入生产，也未擅自接管其他仓库。
- 已确认待验收与阻塞进度条分别使用对应标签的前景色，列表与详情保持一致。

## 验证证据

| 检查 | 结果 |
| --- | --- |
| Python 全套 | 36/36 通过：后端、CLI、Windows 进程生命周期、VPS 配置与监听验证 |
| Node 规则 | 12/12 通过：进度、搜索、真实数据适配、串行轮询和超时恢复 |
| 独立审查 | 前后端、运行部署分别审查；最终 Astra 整体审查发现的问题已集中修复并通过限定复核 |
| 实际上报 | 用标准库 CLI 封存并发送真实快照；相同请求重试不加版本，旧 revision/错误 token/同键不同内容均被拒绝 |
| 重启持久化 | 停止完整本机服务并经任务计划重启；SQLite integrity_check=ok，原 revision 和幂等回执保留，原请求返回 replayed=true |
| 公开鉴权 | 根页面与查询 API 未认证均401，认证后均200；页面内容 SHA 与本机正式构建一致 |
| 写入隔离 | 公网 PUT 返回403，公网 OpenAPI 返回404；写入文档仅在本机8811可访问 |
| 隧道边界 | VPS `ss` 确认8083仅回环；回环未认证HTTP401，公网IP:8083的HTTP请求无可读响应 |
| 隧道认证 | 一次错误 frp token 探针被拒绝，没有影响正在运行的合法代理 |
| TLS | 默认信任链与主机名校验通过，实际协商TLS1.3 |
| 离线页 | 停服后，已认证访问域名返回503及明确离线说明；重启后恢复200 |
| 真实浏览器 | 公开HTTPS页面的桌面、375/390/430px、下钻、深层URL刷新、返回与实时上报自动更新均通过；无JavaScript错误 |
| 秘密检查 | 已跟踪源码/构建产物与本机组件日志均未发现实际查看密码、frp token 或上报 token；私有运行文件被Git忽略 |

真实浏览器记录：[public-browser.json](live/public-browser.json)。截图：[桌面](live/desktop.png)、[375px](live/mobile-375.png)、[手机](live/mobile.png)、[任务详情](live/mobile-task.png)。

## 复核中修复的问题

- 修正 OpenAPI 模型引用及机器可见的 Bearer/幂等头声明，避免仅有文档页面却不能正确调用。
- Basic Auth 改为 UTF-8 bytes 恒时比较，避免非 ASCII 输入导致500。
- 前后端采用一致整数舍入，23/40统一显示58%；验收提示不再把pending直接当成实施完成。
- 紧凑 ISO 时间在读取视图中规范化，存储和幂等哈希保持原语义。
- Windows 组件在受控放行和 Job Object 归属后启动；降低心跳文件写入频率，启动失败会报告非零状态。
- 启动确认按实例ID，不依赖 venv 的 pythonw 重定向器PID；失败清理仅作用于匹配实例。
- VPS 使用专用回环代理实例，避免修改共享 frps 或依赖可被单独停止的防火墙保护。
- VPS 第一次现场安装因 `ss` 的 `*:8072` 表示被误判而退出；回滚实际恢复了原站点 SHA、新单元被移除且无残留监听。后续兼容控制端口的合法表示，代理端仍严格要求回环。
- 最后截图发现真实长摘要在375px下挤出13px，且旧检查比较膨胀后的innerWidth导致假阳性。已重新打开QA任务记录原因，修复Grid最小宽度，并改为固定视口/clientWidth/visualViewport及卡片容器边界验证；真实公网复测后再次完成Task。

## 部署与恢复记录

- 成功的 VPS 配置备份：`/root/ai-dashboard-backups/20260928T092743Z-2359772`。
- 第一次回滚的备份：`/root/ai-dashboard-backups/20260928T091812Z-2358912`；站点与备份的SHA相同。
- 原共享 `/root/frp/frps.toml`、`ws.example-user.com` 配置 SHA 未改变；原共享 frps PID 在部署检查时保持不变，没有重启该服务。
- 本机 `.runtime/` ACL 限当前用户和 SYSTEM。SQLite 一致备份保存在 `.runtime/backups/`，未纳入Git。
- 登录自启属于当前用户会话，不表示登录前的系统级Windows服务。

## 验收边界与非阻断事项

- 已执行 Chromium 的真实公开网址与移动视口验证；真实 iPhone/Safari 的实际观感尚待用户体验，不把模拟测试记为真机验收。
- 生命周期中的进程就绪与HTTP/frp功能健康分别验证；启动包装的PID/实例检查不能替代网络检查。极慢启动超过包装超时后，仍应通过status查询实际状态。
- Starlette 对测试使用的 httpx 发出一条弃用提示；测试通过，生产服务不使用该测试客户端，依赖已锁定。
- 一次已停止测试的临时目录清理被自动审批以“策略阻止”拒绝，目录保留；未绕过限制，不影响生产服务或数据。
- 请求的子agent配置按项目约定使用 Sol/high 和最终 Astra/medium；派发工具未返回实际模型/推理信息，实际配置不可验证。

当前本地代码留在 `feat/local-dashboard`，不涉及远端Git推送。后续接入和运维入口见 [API说明](../api.md)、[运行说明](../operations.md)、[VPS说明](../vps-deployment.md)。
