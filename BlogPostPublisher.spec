# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['src/blogpost/entrypoint.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src/blogpost/migrations/001_initial.sql', 'blogpost/migrations'),
        ('src/blogpost/migrations/002_multi_account.sql', 'blogpost/migrations'),
        ('src/blogpost/migrations/003_account_article_type.sql', 'blogpost/migrations'),
    ],
    hiddenimports=['tkinter', 'sqlite3'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['PySide6', 'playwright', 'httpx', 'keyring'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BlogPostPublisher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
