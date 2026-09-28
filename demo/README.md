# 进度簿：只读前端 demo

- [打开完整 demo](index.html)：独立 HTML，自动适配桌面与手机。
- [打开手机预览](mobile.html)：独立 HTML，桌面可切换 375 / 390 / 430px；手机打开时铺满页面。
- [桌面截图](previews/desktop.png)、[手机首页](previews/mobile.png)、[手机项目详情](previews/mobile-project.png)、[手机任务详情](previews/mobile-task.png)。

两个 HTML 都内嵌了样式、脚本和样例数据，可单独复制、转发。运行时不需要安装依赖或连接网络，也没有模型、后端或进度写入功能。

## 可以体验的内容

1. 筛选“需关注”，查看账单规则待确认与相册待验收两种状态。
2. 打开“本地知识库”，查看 `12/20 = 60%`，以及两个尚待细化的 Wave。
3. 在“检索与引用”下进入“合并重复检索片段”，查看目标、进展、子项和验证要求。
4. 从任务返回项目、再返回总览，已选筛选条件会保留。
5. 搜索项目、Task 或子项文字；搜索不到时可清除筛选。
6. 点击问号查看计算口径；通过“演示数据”菜单切换本机离线示例。
7. 打开“个人站点可用性与证书到期检查”，检查长名称和无 Task 时的展示。

所有项目、时间、检查结果和进度均为虚构样例，没有读取当前电脑的真实项目状态。

## 在手机上体验

可把任一 HTML 文件传到手机。文件查看器若禁用了脚本，会显示静态项目概览；完整交互应在支持脚本的浏览器页面中体验。也可以把 `index.html` 放到已有静态站点，通过 Safari 打开该地址。

真实 iPhone 尚待用户体验；当前已用 Chromium 模拟手机尺寸检查布局和交互，没有把浏览器模拟结果称为 Safari 真机验证。

## 本地预览、构建和检查

在仓库根目录执行：

```powershell
# 可选：提供本机预览地址，随后访问 http://127.0.0.1:8765/
python -m http.server 8765 --bind 127.0.0.1 --directory demo

# 修改 demo/src 后，重新生成独立 HTML
node scripts/build-demo.cjs

# 检查计量与搜索规则
node --test tests/progress-model.test.cjs

# 浏览器检查（开发环境需有 Playwright 和 Chromium）
node scripts/check-demo.cjs
```

浏览器检查脚本可通过 `PLAYWRIGHT_MODULE_PATH` 指向已有 Playwright 安装；Codex 本次使用 bundled runtime，没有给 demo 增加外部依赖。检查脚本会更新 `previews/` 中的截图和 `verification.json`。

## 文件组织

- `src/model.js`：进度与搜索规则，浏览器和测试使用同一份代码。
- `src/data.js`：六个演示项目。
- `src/app.js`：只读渲染、筛选和导航。
- `src/styles.css`：桌面、手机与可读性样式。
- `src/shell.html`：页面结构；构建时内联其他文件。

后续接入真实数据时，需要独立完成上报接口、查询接口和部署配置；本次不包含这些实现。
