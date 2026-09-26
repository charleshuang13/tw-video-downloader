"""后台线程：解析推文 / 下载媒体。全部走 Qt 信号回主线程，UI 不卡。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from . import api


class ParseWorker(QThread):
    """批量解析推文元信息。"""

    one = Signal(object)        # api.Tweet
    failed = Signal(str, str)   # 原始输入, 错误
    log = Signal(str)
    done = Signal(int, int)     # 成功数, 总数

    def __init__(self, refs, parent=None):
        super().__init__(parent)
        self._refs = list(refs)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        ok = 0
        for handle, tid in self._refs:
            if self._stop:
                break
            self.log.emit(f"解析 {tid} …")
            try:
                tw = api.fetch_tweet(handle, tid)
                ok += 1
                self.one.emit(tw)
                self.log.emit(
                    f"  @{tw.handle} 抓到 {len(tw.media)} 个媒体"
                    + (f"（{tw.created}）" if tw.created else "")
                )
            except api.ParseError as e:
                self.failed.emit(f"{handle or ''}/{tid}", str(e))
                self.log.emit(f"  失败：{e}")
            except Exception as e:
                self.failed.emit(f"{handle or ''}/{tid}", f"{type(e).__name__}: {e}")
                self.log.emit(f"  异常：{type(e).__name__}: {e}")
        self.done.emit(ok, len(self._refs))


class FetchThumbWorker(QThread):
    """抓封面图（纯 bytes，主线程再转 QPixmap）。"""

    got = Signal(str, bytes)     # tweet_id, 图片数据

    def __init__(self, tweet, parent=None):
        super().__init__(parent)
        self._tweet = tweet

    def run(self):
        for m in self._tweet.media:
            url = m.thumbnail or m.url
            if not url:
                continue
            try:
                self.got.emit(self._tweet.id, api._get(url, timeout=15))
                return
            except Exception:
                continue


class DownloadWorker(QThread):
    """串行下载队列，逐条上报进度。"""

    log = Signal(str)
    item_state = Signal(str, str, str)    # tweet_id, 状态(pending/active/ok/fail), 说明
    progress = Signal(int, int, str)      # 已完成媒体数, 总媒体数, 当前百分比说明
    finished_all = Signal(int, int, str)  # 成功, 失败, 输出目录

    def __init__(self, jobs, outdir: Path, want_video=True, want_photo=True,
                 quality="最高", parent=None):
        super().__init__(parent)
        self._jobs = list(jobs)          # [(Tweet, [MediaItem, ...]), ...]
        self._outdir = Path(outdir)
        self._want_video = want_video
        self._want_photo = want_photo
        self._quality = quality
        self._stop = False
        self._cur_bytes = 0
        self._cur_total = 0

    def stop(self):
        self._stop = True

    def _plan(self, tw):
        out = []
        for m in tw.media:
            if m.is_video and self._want_video:
                out.append(m)
            elif m.kind == "photo" and self._want_photo:
                out.append(m)
        return out

    def run(self):
        total_items, done_items = 0, 0
        ok, bad = 0, 0
        for tw, _ in self._jobs:
            total_items += len(self._plan(tw))
        self._outdir.mkdir(parents=True, exist_ok=True)

        for tw, _ in self._jobs:
            if self._stop:
                break
            items = self._plan(tw)
            if not items:
                self.item_state.emit(tw.id, "skip", "没有符合筛选条件的媒体")
                continue
            self.item_state.emit(tw.id, "active", "下载中")
            seq, fails = 0, 0
            for m in items:
                if self._stop:
                    break
                seq += 1
                self._cur_bytes = self._cur_total = 0
                ext = "mp4" if m.is_video else "jpg"
                url = m.pick(self._quality) if m.is_video else (m.url + "?name=orig")
                dest = self._outdir / f"{tw.handle}_{tw.id}_{seq:02d}.{ext}"
                self.log.emit(f"↓ {dest.name}  ({m.kind} {m.width}x{m.height}"
                              + (f" {m.duration:.1f}s" if m.duration else "") + ")")
                try:
                    n = api.download(
                        url, dest,
                        on_progress=lambda a, b, t=total_items, d=done_items: self.progress.emit(
                            d, t, self._pct_text(a, b, dest.name)),
                        should_stop=lambda: self._stop,
                    )
                    self.log.emit(f"  完成 {n/1024/1024:.2f} MB → {dest}")
                    ok += 1
                    self.item_state.emit(tw.id, "ok", f"已存 {dest.name}")
                except InterruptedError:
                    self.log.emit("  已取消")
                    self.item_state.emit(tw.id, "fail", "已取消")
                    bad += 1
                    break
                except Exception as e:
                    fails += 1
                    self.log.emit(f"  失败：{type(e).__name__}: {e}")
                    # 直链失败 → 试 yt-dlp 兜底
                    if m.is_video:
                        try:
                            made = api.download_by_ytdlp(tw.page_url, self._outdir, self.log.emit)
                            self.log.emit(f"  yt-dlp 兜底成功：{', '.join(p.name for p in made)}")
                            ok += 1
                            fails -= 1
                            self.item_state.emit(tw.id, "ok", "yt-dlp 兜底成功")
                            continue
                        except Exception as e2:
                            self.log.emit(f"  yt-dlp 兜底也失败：{e2}")
                    self.item_state.emit(tw.id, "fail", f"{type(e).__name__}: {e}")
                    if fails >= len(items):
                        bad += 1
                finally:
                    done_items += 1
                    self.progress.emit(done_items, total_items, "")

        self.finished_all.emit(ok, bad, str(self._outdir))

    @staticmethod
    def _pct_text(got: int, total: int, name: str) -> str:
        if total:
            return f"{name}  {got/total*100:.0f}%  ({got/1048576:.1f}/{total/1048576:.1f} MB)"
        return f"{name}  {got/1048576:.1f} MB"
