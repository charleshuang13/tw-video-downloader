"""离屏冒烟测试：解析 + 下载 + GUI 逻辑，不需要真屏幕。

跑法：QT_QPA_PLATFORM=offscreen .venv/bin/python test_smoke.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from twdownloader import api  # noqa: E402
from twdownloader.compat import enable_utf8_stdout  # noqa: E402
from twdownloader.main_window import MainWindow  # noqa: E402

enable_utf8_stdout()

TWEET = "https://x.com/NASA/status/1816862466816496101"
FAILS = []


def check(name, cond, extra=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        FAILS.append(name)


def test_link_parse():
    print("\n== 链接解析 ==")
    for raw, want in [
        (TWEET, "1816862466816496101"),
        (TWEET + "?s=20&t=abc", "1816862466816496101"),
        ("https://twitter.com/NASA/status/1816862466816496101/video/1", "1816862466816496101"),
        ("https://x.com/i/status/1816862466816496101", "1816862466816496101"),
        ("1816862466816496101", "1816862466816496101"),
    ]:
        h, t = api.parse_ref(raw)
        check(f"parse_ref({raw[:48]})", t == want, f"-> {t}")
    check("乱码输入应报错", _raises(api.parse_ref, "你好啊"))
    check("多行抽取", len(api.split_inputs(f"{TWEET}\n{TWEET}\n垃圾\n1816862466816496101")) == 1)


def _raises(fn, *a):
    try:
        fn(*a)
        return False
    except api.ParseError:
        return True
    except Exception:
        return False


def test_real_tweet():
    print("\n== 真实推文解析（联网）==")
    tw = api.fetch_tweet("NASA", "1816862466816496101")
    check("拿到作者", tw.handle == "NASA", f"@{tw.handle}")
    check("拿到媒体", len(tw.media) == 1, f"{len(tw.media)} 个")
    m = tw.media[0]
    check("是视频", m.is_video and m.kind == "video")
    labels = m.quality_labels()
    check("有清晰度档位", len(labels) >= 2, str(labels))
    check("时长>0", m.duration > 0, f"{m.duration:.2f}s")

    # 档位名要和 URL 里的短边对得上；pick() 选出来的必须是该档位的 URL
    by_label = {v.label: v.url for v in m.variants}
    check("最高档 = 码率最高", m.pick("最高") == m.variants[
        max(range(len(m.variants)), key=lambda i: m.variants[i].bitrate)].url)
    for lb in labels:
        check(f"选 {lb} 命中同一档", m.pick(lb) == by_label[lb], by_label[lb].split("/")[-2:])

    print("\n== 真实下载到临时目录（挑最低档，快一点）==")
    with tempfile.TemporaryDirectory() as d:
        dest = Path(d) / "smoke.mp4"
        seen = []
        n = api.download(m.pick(labels[-1]), dest, on_progress=lambda a, b: seen.append(b))
        check("文件落地", dest.exists() and n > 100_000, f"{n/1024/1024:.2f} MB")
        check("进度有回调", len(seen) >= 1, f"{len(seen)} 次")
        check("内容非空", dest.stat().st_size == n)
        head = dest.read_bytes()[:12]
        check("是 mp4 容器", b"ftyp" in head, str(head[4:12]))
    return tw


def test_gui():
    print("\n== GUI 离屏冒烟 ==")
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    check("窗口标题", win.windowTitle() == "推特视频下载器")

    # 注入假 tweet（绕过网络）
    fake = api.Tweet(
        id="999", handle="tester", author="测试", text="这是一条测试推文",
        created="2026-09-26", source="fxtwitter",
        media=[api.MediaItem(kind="video", url="http://x/a.mp4", duration=3.0, width=720, height=1280,
                             variants=[api.Variant(url="http://x/720.mp4", label="720p", bitrate=2000, height=720),
                                       api.Variant(url="http://x/480.mp4", label="480p", bitrate=900, height=480)]),
               api.MediaItem(kind="photo", url="http://x/p.jpg")],
    )
    win.on_tweet(fake)
    app.processEvents()
    check("表格插了一行", win.table.rowCount() == 1)
    check("作者列正确", win.table.item(0, 0).text() == "tester")
    check("媒体列统计", win.table.item(0, 2).text() == "1 视频 + 1 图", win.table.item(0, 2).text())
    check("勾选后按钮可用", win.btn_dl.isEnabled())
    opts = [win.cmb_q.itemText(i) for i in range(win.cmb_q.count())]
    check("清晰度按推文动态生成", opts == ["最高", "720p", "480p"], str(opts))

    win.on_item_state("999", "ok", "已存 x.mp4")
    app.processEvents()
    check("状态列变完成", "完成" in win.table.item(0, 4).text())
    win.on_progress(1, 2, "测试 50%")
    check("进度条 50%", win.bar.value() == 50, str(win.bar.value()))
    win.on_download_done(2, 0, "/tmp")
    check("结束状态文案", "全部完成" in win.lbl_stat.text(), win.lbl_stat.text())

    win.on_parse_fail("bad/123", "接口挂了")
    check("失败行也进表", win.table.rowCount() == 2)
    app.processEvents()

    win.on_clear()
    check("清空生效", win.table.rowCount() == 0 and not win.btn_dl.isEnabled())

    pm = _icon_check()
    check("图标可绘制", pm is not None and pm.width() == 1024)

    win.grab().save("/tmp/twdl_shot.png")
    print("  界面截图：/tmp/twdl_shot.png")
    win.close()


def _icon_check():
    try:
        import make_icon

        return make_icon.draw()
    except Exception as e:
        print("  图标异常:", e)
        return None


if __name__ == "__main__":
    test_link_parse()
    test_real_tweet()
    test_gui()
    print("\n==========================")
    if FAILS:
        print(f"失败 {len(FAILS)} 项：{FAILS}")
        sys.exit(1)
    print("全部通过")
