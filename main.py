"""推特视频下载器 —— 入口。

正常启动：推特视频下载器.app / 推特视频下载器.exe

自检模式（排查用，不开窗口）：
    推特视频下载器 --selftest [推文链接] [--out 日志路径]

为什么要有 --out：Windows 上打包成 windowed 的 exe 没有控制台，print 出来的东西
哪儿都看不到，所以自检结果要能落盘。macOS 直接跑通常能看见 stdout。
"""
from __future__ import annotations

import sys
from pathlib import Path

DEFAULT_SELFTEST_URL = "https://x.com/NASA/status/1816862466816496101"


def _parse_argv(argv: list) -> tuple:
    """从命令行里抠出 (链接, 日志路径)。"""
    url, out = None, None
    for i, a in enumerate(argv):
        if a == "--selftest" and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            url = argv[i + 1]
        elif a == "--out" and i + 1 < len(argv):
            out = argv[i + 1]
    return url, out


def selftest(url: str | None = None, out_path: str | None = None) -> int:
    """在打包环境里验证解析+下载链路，不上界面。返回 0=通过，1=失败。"""
    import tempfile

    from twdownloader import api

    url = url or DEFAULT_SELFTEST_URL
    lines = []
    ok = False
    try:
        handle, tid = api.parse_ref(url)
        lines.append(f"链接解析: handle={handle} id={tid}")
        tw = api.fetch_tweet(handle, tid)
        lines.append(f"推文解析: @{tw.handle} / {tw.author} / {len(tw.media)} 个媒体 / 来源={tw.source}")
        for m in tw.media:
            lines.append(f"  - {m.kind} {m.width}x{m.height} {m.duration:.1f}s 档位={m.quality_labels()}")
        vids = [m for m in tw.media if m.is_video]
        if vids:
            with tempfile.TemporaryDirectory() as d:
                dest = Path(d) / "selftest.mp4"
                n = api.download(vids[0].pick("最高"), dest, on_progress=lambda a, b: None)
                lines.append(f"下载成功: {n/1024/1024:.2f} MB")
        lines.append("自检通过")
        ok = True
    except Exception as e:
        lines.append(f"自检失败: {type(e).__name__}: {e}")

    text = f"自检目标: {url}\n" + "\n".join(lines)
    if sys.stdout is not None:
        try:
            print(text)
        except Exception:
            pass
    if out_path:
        try:
            Path(out_path).write_text(text + "\n", encoding="utf-8")
        except Exception as e:
            if sys.stderr is not None:
                print(f"写日志失败: {e}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    from twdownloader.compat import enable_utf8_stdout

    enable_utf8_stdout()

    if "--selftest" in sys.argv:
        _url, _out = _parse_argv(sys.argv)
        sys.exit(selftest(_url, _out))

    from twdownloader.main_window import run

    sys.exit(run())
