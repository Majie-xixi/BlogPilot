# 安全说明

- 不保存 51CTO 明文密码，只保存独立 Chrome Profile 的登录会话。
- API Key 经 Windows DPAPI 加密，不写入源码、配置 JSON、SQLite 或普通日志。
- 日志自动隐藏 Authorization、Cookie、Token、Password 和 API Key。
- 不绕过验证码、安全挑战或访问限制。
- 不进行刷阅读、点赞、评论或多账号操作。
- 最终发布点击只执行一次；结果不明确时状态为 `unknown`，禁止自动再次提交。
- 历史目录根部 Markdown 只读，程序只写 `generated_posts` 子目录。
