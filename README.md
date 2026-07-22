# BlogPilot（智博日更）

Windows 本地软件：为一个或多个 51CTO 账号分别生成原创 AI 技术博文，质量检查后按顺序自动发布。

在 VS Code 中调试时，可直接右键项目根目录的 `main.py`，选择“在终端中运行 Python 文件”。

## 当前能力

- 最多管理 5 个本地账号；切换账号会立即刷新该账号的今日状态、月度进度、文章与运行历史。
- 每个账号可独立设置主页、发布时间、月目标、文章分类、博文类型、内容方向和主题关键词；关键词会作为选题硬约束。
- 支持当前账号单独执行，也支持勾选多个账号后串行生成、串行发布；一个账号失败不会阻止后续账号。
- 不同账号当天的标题、主题和正文统一参与查重，避免生成相似文章。
- 发布失败后可直接重发当前账号已经保存的文章，不会再次调用大模型生成。
- 默认使用 DeepSeek OpenAI 格式接口（`https://api.deepseek.com`、`deepseek-v4-pro`），也支持其他兼容接口。
- 首次启动由用户选择专用数据目录；文章按账号保存在 `articles\generated_posts\<account_id>`，程序升级和卸载不会删除该目录。
- 检查字数、AI 主题、Markdown、密钥泄漏、标题和正文相似度。
- 使用 Windows DPAPI 加密 API Key。
- 使用电脑已有 Chrome，并为每个账号建立独立应用 Profile 和调试端口，不接触普通 Chrome Profile，也不会串用其他账号的登录窗口。
- Chrome 自动化禁用组件更新、后台同步和本地生成式 AI 功能；按流量计费网络会暂停自动生成和发布。
- 遇到验证码、登录失效、页面结构变化或发布结果不明确时停止。

## 运行

无需安装 Qt 或独立浏览器。开发模式：

```powershell
$env:PYTHONPATH='src'
python -m blogpost gui
```

命令行：

```powershell
python -m blogpost run-now
python -m blogpost run-now --account default --account account-xxxx
python -m blogpost run-daily
python -m blogpost login
python -m blogpost schedule install
python -m blogpost schedule status
```

## 标准安装

双击 `dist\BlogPilot-Setup-0.1.0.msi` 即可安装。程序安装在当前 Windows 用户的本地程序目录，并创建开始菜单和桌面快捷方式，不需要管理员权限。

第一次启动会弹出 Windows 原生目录选择窗口，请选择专门保存 BlogPilot 数据的位置，例如 `E:\BlogPilotData`。配置、数据库、加密 API Key、日志、诊断文件、各账号 Chrome 登录会话和文章都保存在所选目录中；安装目录只包含程序文件。

升级或卸载只处理程序和快捷方式，不会删除数据目录。如需换电脑，可复制数据目录，但 API Key 受 Windows DPAPI 保护，需要在新电脑重新填写；每个 51CTO 账号也应重新登录一次。

## 首次使用

1. 首次启动先选择专用数据目录；如需继续使用旧数据，请直接选择原来的 BlogPilot 数据目录。
2. 打开“全局设置”，填写 API Base URL、模型名称和 API Key，并保持“安全试运行”开启。
3. 打开“账号管理”，填写 51CTO 主页后会自动读取公开博主名称；再设置发布时间、分类、博文类型和主题关键词，需要时新增第二个账号。
4. 切换到每个账号，分别点击显示账号名称的“登录 · 账号名称”按钮，在对应独立 Chrome 窗口中各登录一次；以后发布不需要在网页中手动切换账号。
5. 运行日志默认只显示本次启动和本次任务；旧运行结果在“查看历史记录”中查询，也可随时点击“清空日志”。
6. 使用“立即生成并发布”校准当前账号，或使用“批量依次发布”勾选多个账号。
7. 人工确认排版、原创标记和分类无误后，在全局设置中关闭安全试运行。
8. 点击“安装 / 更新每日任务”，按所有启用账号的发布时间注册统一 Windows 任务。

账号配置、Cookie、数据库、日志、API Key 和文章都只保存在本机，Git 不会上传这些数据。

真实发布前请阅读 [首次运行说明](docs/first-run.md) 和 [安全说明](docs/security.md)。

## 测试

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -p 'test_*.py' -v
```
