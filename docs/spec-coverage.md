# 规格覆盖

| 能力 | 自动验证 | 人工验证 |
|---|---|---|
| 历史目录只读、排除 generated_posts | `test_corpus.py` | 首次运行前后比较历史文件 |
| 原子保存与防覆盖 | `test_article_store.py` | 打开生成目录 |
| OpenAI 兼容调用与鉴权错误 | `test_llm.py` | 配置实际 API dry-run |
| 字数、Markdown、密钥、去重 | `test_quality.py` | 检查生成文章 |
| 每日幂等与手动流水线 | `test_pipeline.py` | 同日再次点击确认提示 |
| Chrome 独立 Profile 与填充脚本 | `test_chrome.py` | 真实 51CTO dry-run |
| 10:00 和 StartWhenAvailable | `test_scheduler.py` | Windows 任务计划程序 |
| 验证码/登录/unknown 安全停止 | 发布器代码路径 | 真实站点按需验证 |
