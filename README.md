# BlogPilot（智博日更）

Windows 本地软件：每天自动生成一篇原创 AI 技术博文，质量检查后填充并发布到 51CTO。

在 VS Code 中调试时，可直接右键项目根目录的 `main.py`，选择“在终端中运行 Python 文件”。

## 当前能力

- 默认每天 10:00，可修改时间，也可点击“立即生成并发布”。
- 默认使用 DeepSeek OpenAI 格式接口（`https://api.deepseek.com`、`deepseek-v4-pro`），也支持手动改为 OpenAI、通义千问等兼容接口。
- 读取用户配置的历史文章目录作为风格和去重语料，绝不修改历史文章。
- 新安装默认把文章保存到“文档\\BlogPilot\\generated_posts”，也可通过本机配置指定其他目录。
- 检查字数、AI 主题、Markdown、密钥泄漏、标题和正文相似度。
- 提供动画进度条和实时运行日志；质量未通过时仍会保存“待检查”草稿。
- 使用 Windows DPAPI 加密 API Key。
- 使用电脑已有 Chrome 和独立应用 Profile 登录 51CTO，不接触普通 Chrome Profile。
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
python -m blogpost run-daily
python -m blogpost login
python -m blogpost schedule install
python -m blogpost schedule status
```

## 首次使用

1. 打开“设置”，填写 API Base URL、模型名称和 API Key。
2. 保持“安全试运行”开启。
3. 点击“打开 51CTO 登录窗口”，在独立 Chrome 窗口中登录。
4. 点击“立即生成并发布”，检查编辑器中的排版、原创标记和 AI 分类。
5. 校准确认无误后，在设置中关闭安全试运行。
6. 点击“安装/更新每日任务”，注册每天 10:00 的 Windows 任务。

真实发布前请阅读 [首次运行说明](docs/first-run.md) 和 [安全说明](docs/security.md)。

## 测试

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -p 'test_*.py' -v
```
