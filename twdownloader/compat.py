"""跨平台兼容小工具。"""
from __future__ import annotations

import sys


def enable_utf8_stdout() -> None:
    """把 stdout/stderr 切成 UTF-8，避免 Windows 控制台（默认 cp1252）打印中文时
    UnicodeEncodeError 崩掉 —— 实测 GitHub Actions 的 Windows runner 上就挂在这。

    打包成 windowed 应用时 sys.stdout 是 None，直接跳过。
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
