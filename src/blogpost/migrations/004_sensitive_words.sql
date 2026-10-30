-- Local sensitive words captured from 51CTO review prompts or added by hand.
-- The baseline ships with the program (blogpost/data/sensitive_words.txt);
-- this table only stores per-installation additions and hit statistics.
CREATE TABLE IF NOT EXISTS local_sensitive_words (
    term TEXT PRIMARY KEY,
    replacement TEXT,
    source TEXT NOT NULL DEFAULT 'auto',
    hit_count INTEGER NOT NULL DEFAULT 1,
    last_hit_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
