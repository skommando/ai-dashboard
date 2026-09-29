# 180 天网页登录与独立项目上报认证

用户已确认：查看账号和随机生成的 20 位复杂密码用于网页登录；会话有效期 180 天。Basic Auth 从 Nginx 与应用中移除。登录接口的所有失败统一返回固定正文“功能未开发”，避免通过响应区分用户名、密码或请求格式。项目版本查询和快照上报只需原有的项目令牌，不依赖网页登录；SQLite 快照、revision 与幂等规则保持不变。

## 登录与会话

- `GET /login` 返回独立的手机适配登录页；`POST /api/v1/login` 接收 JSON `username`、`password`。账号与密码从仓库外私有环境读取，公共源码、示例、测试和 Git 历史不包含真实值。
- 任意登录失败返回同一 HTTP 状态、`text/plain` 正文 `功能未开发`，不加 Basic challenge。登录成功签发 180 天有效的 `__Host-` 前缀 Cookie：`Secure`、`HttpOnly`、`SameSite=Lax`、`Path=/`，不设置 `Domain`。签名密钥是独立随机私密值；验证和密码变更使旧 Cookie 失效。
- 未持会话访问首页重定向 `/login`；项目读取 API 返回 401。首次经登录页进入后，Safari 正常浏览会保存 Cookie；隐私浏览或主动清除网站数据后重新登录。Cookie 在有效期内不会按访问时间无限续期。
- `/healthz`、`/docs`、`/openapi.json` 不返回项目内容，可公开访问以支持监控与接入。网页读取仍需会话。登录页不展示真实账号。

## 上报

- `GET /api/v1/projects/{id}/revision` 和 `PUT /api/v1/projects/{id}/snapshot` 只校验 `X-Project-Token`，旧项目 ID、原令牌哈希、完整快照、版本冲突和幂等重放保持有效。
- 标准库客户端仅读取项目令牌文件或环境变量，仍要求 HTTPS、拒绝跳转和外部明文 HTTP，不再要求或发送 Basic 凭据。
- 上报接口不会因浏览器的查看 Cookie 获得写权限；Cookie 不代替项目令牌。OpenAPI 分别声明会话 Cookie 与项目令牌的安全边界。

## 部署和验收

- 宝塔站点仍提供 HTTPS；项目 Nginx locations 显式取消继承的 Basic，认证由回环应用处理。低权限 systemd 应用从 `/opt/ai-dashboard/shared/dashboard.env` 读取私有登录凭据与会话密钥。发布器验证新环境配置，健康探测不使用旧 Basic。
- 本地完成登录失败同响应、180 天边界、签名篡改/换密失效、无会话读取拒绝、只凭项目令牌可上报、仅 Cookie 不可上报，以及前端小屏登录流程验证。再按 `dev` CI → `main` CI → 固定 SHA 部署并在真实 HTTPS 域名复验。
