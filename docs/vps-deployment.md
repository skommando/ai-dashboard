# VPS 只读看板部署

本部署仅操作 `dashboard.example.com` 的项目 include、离线页，以及专用 `ai-dashboard-frps.service`。现有站点的 TLS 和 Basic Auth 留在原站点配置内；共享 `frps.service`、`/root/frp/frps.toml` 和防火墙规则均不改动。主 agent 负责实际上传、安装与公网验收。

## 准备

VPS 需要 `bash`、Python 3.9+、`systemctl`、`runuser`、`ss`、`flock` 和现有 `/root/frp/frps` 0.62.1；站点文件为 `/www/server/panel/vhost/nginx/dashboard.example.com.conf`，Nginx 为 `/www/server/nginx/sbin/nginx`。安装程序必须由 root 运行。首次安装前检查控制端口 TCP 8072 和代理端口 TCP 8083 没有被其他进程占用；重复安装时应由本项目服务占用。

根据 [`deploy/vps/frps.toml.template`](../deploy/vps/frps.toml.template) 在本机创建私有配置，将占位符替换成独立生成的至少 32 字符随机 base64url/十六进制 token。不要把填入 token 的文件放进 Git、命令参数或日志。通过加密 SSH 传至 VPS 的 root 私有目录，例如 `/root/ai-dashboard-private/frps.toml`，并设置 `chmod 600`。安装脚本仅接受模板中的六个字段，不接受额外端口或监听设置；会调用 frps 自身的 `verify` 再校验语法。frpc 需使用同一 token，连接 VPS TCP 8072，设置 `remotePort = 8083`，从本机只读入口转发；frpc 的私有配置也不得提交。

模板字段已与 [frp v0.62.1 官方示例](https://github.com/fatedier/frp/blob/v0.62.1/conf/frps_full_example.toml) 对照；该版本支持 `proxyBindAddr`、`allowPorts` 和 `auth.token`。不使用 v0.64 才加入的 token 文件加载功能。

## 安装

将 `deploy/vps/` 上传到 VPS 的 root 私有暂存目录，然后执行：

```bash
bash /root/ai-dashboard-deploy/vps/install.sh /root/ai-dashboard-private/frps.toml
```

脚本先验证依赖、私有配置和现有 Nginx 配置，再备份项目相关文件；备份目录只允许 root 访问。它创建低权限 `ai-dashboard` 系统用户，安装独立 frps 二进制和服务，确认服务及 TCP 8072 已监听，并确认 TCP 8083 没有非回环监听。此时才将站点 include 加入 `#REWRITE-END` 后方并执行 `nginx -t`、reload。重复安装只保留一条 include。8083 只有 frpc 接入后才会出现，安装时不要求它已监听。

安装出错时脚本恢复站点、include、离线页、frps 配置、单元和二进制的旧文件（没有旧文件则移除），恢复服务先前的 enabled/active 状态，并重新加载 Nginx；失败始终返回非零。若回滚本身失败，终端会给出备份路径和错误，必须人工处理后再重试。成功后备份仍保留，供现场审计。

## 现场核验

```bash
systemctl is-active ai-dashboard-frps.service
systemctl is-enabled ai-dashboard-frps.service
ss -ltn '( sport = :8072 or sport = :8083 )'
/www/server/nginx/sbin/nginx -t
```

预期 8072 为公开监听；`ss` 可能显示 `*:8072`、`0.0.0.0:8072` 或 `[::]:8072`。frpc 接入后的 8083 **仅**为 `127.0.0.1:8083`。随后验证站点证书、Basic Auth、只读 `/api/`、断线离线页及写入请求被拒绝。安装脚本不能代替这些端到端验收。若预检前目标目录已有特殊权限或服务文件，先审阅现场状态；脚本会拒绝覆盖符号链接。
