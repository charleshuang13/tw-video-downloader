"""离屏截界面图（README 截图用）。

跑法：QT_QPA_PLATFORM=offscreen .venv/bin/python screenshot.py [推文链接]
不加参数默认用一条公开的示例推文。
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from twdownloader import api  # noqa: E402
from twdownloader.compat import enable_utf8_stdout  # noqa: E402
from twdownloader.main_window import MainWindow  # noqa: E402

enable_utf8_stdout()

DEMO_URL = "https://x.com/NASA/status/1816862466816496101"


def main(url: str = DEMO_URL):
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(1180, 760)
    win.show()

    handle, tid = api.parse_ref(url)
    win.input.setPlainText(f"https://x.com/{handle}/status/{tid}")
    win.log_line("开始解析 1 条推文")
    win.log_line(f"解析 {tid} …")

    tw = api.fetch_tweet(handle, tid)
    win.on_tweet(tw)

    # 拉封面（等 worker 抓完再截图）
    w = win.thumb_worker
    if w:
        w.wait(8000)
        app.processEvents()
    win.log_line(f"  @{tw.handle} 抓到 {len(tw.media)} 个媒体（{tw.created}）")
    win.table.selectRow(0)
    app.processEvents()

    m = tw.media[0]
    win.log_line(f"输出目录：{win.outdir()}")
    win.log_line(f"↓ {tw.handle}_{tw.id}_01.mp4  ({m.kind} {m.width}x{m.height} {m.duration:.1f}s)")
    win.log_line(f"  完成 8.42 MB → {win.outdir()}/{tw.handle}_{tw.id}_01.mp4")
    win.on_progress(1, 1, f"{tw.handle}_{tw.id}_01.mp4  100%  (8.4/8.4 MB)")
    win.on_item_state(tw.id, "ok", f"已存 {tw.handle}_{tw.id}_01.mp4")
    win.set_stat("全部完成：1 个文件", "#4cc38a")
    app.processEvents()

    win.grab().save("docs/screenshot.png")
    print("已保存 docs/screenshot.png")
    win.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEMO_URL)
