CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    profile_url TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    schedule_time TEXT NOT NULL DEFAULT '10:00',
    monthly_target INTEGER NOT NULL DEFAULT 21,
    category TEXT NOT NULL DEFAULT 'AI 智能体',
    secondary_category TEXT NOT NULL DEFAULT '编程 Agent',
    personal_category TEXT NOT NULL DEFAULT 'AI',
    article_type TEXT NOT NULL DEFAULT '技术解析',
    content_directions TEXT NOT NULL DEFAULT 'AI Agent、AI 编程、Prompt、AIOps、边缘 AI、大模型工程',
    keywords TEXT NOT NULL DEFAULT '',
    article_subdir TEXT NOT NULL DEFAULT 'default',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO accounts(
    id, display_name, created_at, updated_at
) VALUES(
    'default', '账号一', datetime('now', 'localtime'), datetime('now', 'localtime')
);
