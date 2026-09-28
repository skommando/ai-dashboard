# 贡献与发布

请从 `dev` 开发并向 `dev` 提交 Pull Request。`main` 是通过验收的生产代码，不作为日常开发分支。不要提交数据库、真实快照、主机信息、凭据、个人环境配置或带真实数据的截图。

## 本地验证

需要 Python 3.12 和 Node.js 22。创建虚拟环境并安装 `requirements-lock.txt`。虚拟环境无需纳入Git。

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
node scripts/build-demo.cjs
node --test tests/*.cjs
node scripts/check-task-copy.cjs
git diff --check
```

浏览器检查需安装 Playwright 1.62.1 及 Chromium；也可用 `PLAYWRIGHT_MODULE_PATH` 指向已有安装。额外运行 `scripts/check-live.cjs` 和 `scripts/check-demo.cjs` 检查完整前端流。浏览器模拟与真实 iPhone 验证须分别报告。涉及关键鉴权、持久化、发布回滚的改动，需要独立审查。

## 发布顺序

1. 本地 `dev` 完成改动、测试与必要审查，提交并推送 `dev`。
2. 确认该提交的 GitHub CI 通过，才将通过验收的提交合入 `main`，推送 `main`。
3. 等待 `main` 对应提交的 CI，通过后以完整 commit SHA 发布到 VPS；不要部署未提交工作区或动态漂移的分支。
4. 验证公网鉴权、读取、上报及服务状态，保留部署记录与上一release。源码由Git同步，数据库/环境文件不由Git同步。

部署并非 `git push` 的隐含效果；服务器不自动拉取 `dev`。本项目所有者允许在完成约定验证后发布，无需重复请求确认。仅当所有者明确命令跳过测试时，才能使用发布工具的跳过选项，并记录原因；跳过测试不免除凭据保护和数据备份。

## 许可

提交贡献即表示你有权提交，并同意以本仓库 MIT 许可分发该贡献。第三方依赖仍遵循各自许可证，不因本项目采用 MIT 而改变。
