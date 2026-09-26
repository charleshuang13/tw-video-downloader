"""推特视频下载器 —— 入口。

正常启动：推特视频下载器.app
自检模式（排查用，不开窗口）：
    推特视频下载器 --selftest [推文链接]
"""
from __future__ import annotations

import sys


def selftest(url: str | None = None) -> int:
    """在打包环境里验证解析+下载链路，打印结果，不弹窗。"""
    import tempfile
    from pathlib import Path

    from twdownloader import api

    url = url or "https://x.com/NASA/status/1816862466816496101"
    print("自检开始:", url)
    try:
        handle, tid = api.parse_ref(url)
        print(f"  链接解析: handle={handle} id={tid}")
        tw = api.fetch_tweet(handle, tid)
        print(f"  推文解析: @{tw.handle} / {tw.author} / {len(tw.media)} 个媒体 / 来源={tw.source}")
        for m in tw.media:
            print(f"    - {m.kind} {m.width}x{m.height} {m.duration:.1f}s 档位={m.quality_labels()}")
        vids = [m for m in tw.media if m.is_video]
        if vids:
            with tempfile.TemporaryDirectory() as d:
                dest = Path(d) / "selftest.mp4"
                n = api.download(vids[0].pick("最高"), dest,
                                 on_progress=lambda a, b: None)
                print(f"  下载成功: {n/1024/1024:.2f} MB → {dest.name}")
        print("自检通过")
        return 0
    except Exception as e:
        print(f"自检失败: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        arg = sys.argv[i + 1] if len(sys.argv) > i + 1 else None
        sys.exit(selftest(arg))

    from twdownloader.main_window import run

    sys.exit(run())
