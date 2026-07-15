# 首次运行

1. 启动软件后先进入设置。
2. DeepSeek 默认使用 OpenAI 格式地址 `https://api.deepseek.com`；其他服务商请填写其官方 OpenAI 兼容地址。
3. API Key 使用 Windows 当前账户的 DPAPI 加密，无法复制到另一台电脑或另一个 Windows 账户解密。
4. 默认开启 dry-run。dry-run 会生成文章、保存 Markdown，并尝试填充 51CTO 编辑器，但不会点击最终发布。
5. “打开 51CTO 登录窗口”使用独立 Chrome Profile。请在该窗口完成登录和验证码。
6. 首次 dry-run 必须人工确认：标题、正文、Markdown 排版、原创标记、AI 活动分类。
7. 确认无误后才能关闭 dry-run。关闭后的一键操作和每日任务会真实发布。
8. 安装计划任务后，在主界面或 `schedule status` 检查状态。

如果当天已经成功发布，自动任务会跳过；手动按钮会要求二次确认。
