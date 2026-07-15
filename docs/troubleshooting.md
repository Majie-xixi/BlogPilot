# 故障排查

## 提示需要登录

点击“打开 51CTO 登录窗口”，在独立 Chrome 窗口重新登录。不要关闭普通 Chrome，也不要复制 Cookie。

## 出现验证码或访问受限

程序会停止。请在独立 Chrome 窗口人工完成验证，然后重新执行。程序不会绕过验证。

## 页面结构未识别

诊断文件位于 `%LOCALAPPDATA%\BlogPostPublisher\diagnostics`。文件已做基础脱敏，用于更新页面选择器。不要直接公开发送未检查的诊断文件。

## API 鉴权失败

检查 Base URL、模型名称和 API Key。国内服务商的模型名和接口地址以其控制台为准。

## 文章未发布但已生成

Markdown 会保留在设置的文章输出目录中。修复登录或分类后，可人工复制发布；不要盲目反复点击以免重复。

## 定时任务没有执行

运行 `python -m blogpost schedule status` 检查状态，并确认电脑在 10:00 后开机。任务启用了 StartWhenAvailable，错过时间后会尽快执行。
