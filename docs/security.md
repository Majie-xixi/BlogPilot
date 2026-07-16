# 安全说明

- 不保存 51CTO 明文密码；每个账号只在本机保存独立 Chrome Profile 登录会话。
- API Key 经 Windows DPAPI 加密，不写入源码、配置 JSON、SQLite 或普通日志。
- 日志自动隐藏 Authorization、Cookie、Token、Password 和 API Key。
- 不绕过验证码、安全挑战或访问限制。
- 多账号能力只用于管理用户本人合法账号，不进行刷阅读、点赞、评论、账号农场或活动规则规避。
- 最终发布点击只执行一次；结果不明确时状态为 `unknown`，禁止自动再次提交。
- 历史文章目录只读，程序只在 `E:\Projects\BlogPilotWorkspace` 的约定目录写入数据。
- Chrome 启动参数禁用组件更新、后台联网、同步、预测加载和本地生成式 AI 功能。
- 按流量计费网络下，自动任务暂停生成和发布，只允许有大小与超时限制的状态检查。
- 账号配置、Cookie、数据库、日志、文章、本地需求和可执行文件均被 Git 忽略。
