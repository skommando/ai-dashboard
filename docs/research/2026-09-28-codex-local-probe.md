# 本地 Codex 最小连接验证

日期：2026-09-28。用户授权范围：用最小功能验证调用本地 Codex 的可行性，不扩建控制台；主项目仍是只读进度看板。

## 结论与边界

独立 WebSocket 客户端调用本机 Codex 并获得一次真实模型回复已经跑通，未使用 SDK。此结果证明了本地运行时的程序化连接能力，不代表已打通 iPhone 经 VPS 的远程链路，也不证明能接管正在运行的桌面会话或完整复现桌面客户端功能。

| 检查 | 实际结果 |
| --- | --- |
| 本机版本 | `codex-cli 0.153.4`，Windows |
| 共享 daemon 管理 | `codex app-server daemon version` 返回生命周期管理仅支持 Unix；该命令在本机不可用 |
| 独立服务 | 直接启动当前安装的 `codex.exe app-server --listen ws://127.0.0.1:<临时端口>`，成功 |
| 协议 | 采用本机 CLI 生成的 JSON Schema，完成 `initialize` / `initialized` 握手 |
| 已有会话元数据 | 成功 `thread/read` 读取本看板会话的元数据，返回 `historyMode=paginated`、`status=notLoaded`；未恢复或修改该会话 |
| 最小调用 | `thread/start` 创建 `ephemeral=true`、只读沙箱的测试会话，随后 `turn/start` 发送固定应答提示 |
| 真实返回 | 收到 5 次文本增量，最终内容为 `CODEX_PROBE_OK`，完成状态为 `completed` |
| 模型 | 服务返回 `gpt-6-astra`、provider `openai`；未覆盖用户模型配置 |
| 清理 | 测试专用 app-server 已停止，客户端正常退出，退出码 0；未启动或重启现有桌面后台服务 |
| 外部访问 | 未新增 VPS 配置或公开端口，未验证 iPhone / VPS / frp 的端到端访问 |

执行时间为 2026-09-28 06:44:33–06:44:40 UTC。一次性脚本和结果位于本机临时目录：`C:\Users\example-user\AppData\Local\Temp\ai-dashboard-codex-probe-f6e6aa006f374b4680537550a2ecfa32`，其中 `result.json` 保存结构化结果，`probe.mjs` 保存测试方法。该临时目录不作为产品代码或持久运行服务。

## 对产品范围的影响

- 本地 Codex 连接具有可行性，可以成为后续单独验证的扩展方向。
- 当前 HTML demo 保持只读，不加入对话输入框、发消息、审批、启动/暂停任务或模型设置。
- 若后续确需远程控制，应另测真实桌面会话的历史与订阅、运行中会话连接、审批，以及 iPhone 外网访问；不能用本次临时会话的成功代替这些证据。
- “SDK 不如客户端优化”没有在本次得到证实。官方 Codex SDK 也用于控制本地 Codex，SDK、app-server 与桌面产品的实际差异应按具体能力和配置检验。

官方参考：[手机 Remote](https://developers.openai.com/blog/mastering-codex-remote-for-engineering)、[Codex app-server](https://learn.chatgpt.com/docs/app-server)、[Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)。本机验证以安装版本的实际行为为准。
