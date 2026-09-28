# 本机服务运行

本项目的读服务、写服务和 frpc 由 `scripts/service.py` 一个监督进程启动。实际凭据与 frp 配置放在被 Git 忽略的 `.runtime/`，不要提交或粘贴真实配置。示例结构见 `deploy/service.example.json`；把其中路径改为本机绝对路径，并将 `DASHBOARD_VIEW_USERNAME`、`DASHBOARD_VIEW_PASSWORD` 换成实际读取凭据后，保存为 `.runtime/service.json`。frpc 的可执行文件和配置路径也要实际存在。启动前先建立独立 `.venv`、安装后端依赖并初始化数据库。

```powershell
py -3.12 scripts/service.py status --config .runtime/service.json
powershell -NoProfile -File scripts/start-dashboard.ps1
py -3.12 scripts/service.py status --config .runtime/service.json
powershell -NoProfile -File scripts/stop-dashboard.ps1
```

也可前台运行 `py -3.12 scripts/service.py run --config .runtime/service.json`，用于首次检查。脚本只启动配置中的绝对路径命令，不经 shell 展开。监督进程拥有三个受控组件代理，异常退出会按 0.5 秒起、最多 30 秒的退避重启。Windows 上代理必须先加入监督进程的 Job Object 并得到放行，才会启动实际组件；代理自身加入嵌套 Job Object，组件及其子进程在代理意外结束时一并清理。监督进程意外结束时，外层 Job Object 清理全部代理和组件，避免登录恢复后旧端口仍被占用。稳定运行时状态文件约每秒更新一次，组件变化时立即更新；`status` 结合活跃文件锁与心跳判断是否运行，不依据旧 PID 杀进程。`stop` 写入匹配本次实例的停止请求，由监督进程关闭自己持有的子进程句柄并等待退出；无活跃实例时返回错误。`start-dashboard.ps1` 会等待所有配置的组件持续运行，启动失败时返回非零退出码。脚本使用本次启动的随机实例标识判断状态；需条件停止时可使用 `service.py stop --config .runtime/service.json --instance-id <状态中的instance_id>`，只会停止匹配的实例。

`.runtime/service-state.json` 仅含实例标识、PID、心跳、组件退出码和重启信息；环境变量和命令参数不会写入其中。各组件输出写入 `.runtime/<name>.log`，每份日志最多约 1 MiB，另保留一份轮换备份。应用或 frpc 自身若向标准输出写出秘密，日志也会记录该内容，因此接入时应检查其日志行为并限制 `.runtime` 的访问权限。

登录自启任务由部署人员在当前用户权限下配置，目标为 `scripts/start-dashboard.ps1`；此仓库脚本不会自行注册计划任务。配置任务前应先确认手动启动、状态查询、停止都成功。不要用旧状态文件中的 PID 手动结束进程。
