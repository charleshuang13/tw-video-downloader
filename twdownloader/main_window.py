"""推特视频下载器 —— PySide6 界面。"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from . import api
from .workers import DownloadWorker, FetchThumbWorker, ParseWorker

C_BG = "#1e1f26"
C_PANEL = "#282a35"
C_TEXT = "#e6e8ef"
C_DIM = "#8b90a0"
C_OK = "#4cc38a"
C_WARN = "#e0a63c"
C_ERR = "#e5534b"
C_ACCENT = "#4c8dff"

STYLE = f"""
QWidget {{ background: {C_BG}; color: {C_TEXT}; font-size: 13px; }}
QLabel#hint {{ color: {C_DIM}; }}
QLabel#title {{ font-size: 15px; font-weight: 600; }}
QTextEdit, QLineEdit, QTableWidget, QComboBox {{
    background: {C_PANEL}; border: 1px solid #3a3d4a; border-radius: 6px;
    padding: 4px; selection-background-color: {C_ACCENT};
}}
QTableWidget {{ gridline-color: #33364a; }}
QHeaderView::section {{
    background: #22242e; color: {C_DIM}; border: none; padding: 6px; border-bottom: 1px solid #3a3d4a;
}}
QPushButton {{
    background: #33364a; border: 1px solid #454a63; border-radius: 6px;
    padding: 7px 16px; color: {C_TEXT};
}}
QPushButton:hover {{ background: #3d4159; }}
QPushButton:disabled {{ color: #6a6e80; background: #2a2c36; }}
QPushButton#primary {{ background: {C_ACCENT}; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: #5e9bff; }}
QPushButton#primary:disabled {{ background: #33364a; color: #6a6e80; }}
QProgressBar {{
    background: {C_PANEL}; border: 1px solid #3a3d4a; border-radius: 6px;
    height: 10px; text-align: center; color: {C_TEXT};
}}
QProgressBar::chunk {{ background: {C_ACCENT}; border-radius: 5px; }}
QCheckBox {{ color: {C_TEXT}; }}
QFrame#card {{ background: {C_PANEL}; border: 1px solid #3a3d4a; border-radius: 8px; }}
"""

COLS = ["作者", "内容", "媒体", "清晰度", "状态"]


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("推特视频下载器")
        self.resize(1180, 760)
        self.setStyleSheet(STYLE)

        self.tweets = []                 # 解析成功的 Tweet 列表
        self._row_of = {}                # tweet_id -> 行号
        self.parse_worker = None
        self.dl_worker = None
        self.thumb_worker = None
        self._thumbs = {}

        self._build()

    # ------------------------------------------------------------------ UI --
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("推特视频下载器")
        title.setObjectName("title")
        head.addWidget(title)
        head.addStretch(1)
        self.lbl_source = QLabel("解析接口：fxtwitter")
        self.lbl_source.setObjectName("hint")
        head.addWidget(self.lbl_source)
        root.addLayout(head)

        # 输入区
        hint = QLabel("把推文链接粘进来（一行一个，也支持一次贴一串或只贴推文ID）")
        hint.setObjectName("hint")
        root.addWidget(hint)

        self.input = QTextEdit()
        self.input.setPlaceholderText("https://x.com/xiaoyuanovo00/status/2103456485179261344")
        self.input.setFixedHeight(66)
        root.addWidget(self.input)

        row = QHBoxLayout()
        self.btn_parse = QPushButton("解析")
        self.btn_parse.setObjectName("primary")
        self.btn_parse.clicked.connect(self.on_parse)
        row.addWidget(self.btn_parse)

        self.btn_clear = QPushButton("清空列表")
        self.btn_clear.clicked.connect(self.on_clear)
        row.addWidget(self.btn_clear)

        self.btn_paste = QPushButton("从剪贴板粘贴")
        self.btn_paste.clicked.connect(self.on_paste)
        row.addWidget(self.btn_paste)

        row.addStretch(1)
        self.lbl_stat = QLabel("等待解析")
        self.lbl_stat.setStyleSheet(f"color: {C_DIM};")
        row.addWidget(self.lbl_stat)
        root.addLayout(row)

        # 中部：表格 + 预览
        split = QSplitter(Qt.Horizontal)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 190)
        self.table.itemSelectionChanged.connect(self.on_select)
        split.addWidget(self.table)

        side = QFrame()
        side.setObjectName("card")
        sv = QVBoxLayout(side)
        sv.setContentsMargins(10, 10, 10, 10)
        self.preview = QLabel("选中一条看封面")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(230, 300)
        self.preview.setStyleSheet(f"color:{C_DIM}; background:#20222c; border-radius:6px;")
        sv.addWidget(self.preview, 1)
        self.lbl_meta = QLabel("")
        self.lbl_meta.setWordWrap(True)
        self.lbl_meta.setStyleSheet(f"color:{C_DIM};")
        sv.addWidget(self.lbl_meta)
        split.addWidget(side)
        split.setSizes([860, 300])
        root.addWidget(split, 3)

        # 选项区
        opt = QHBoxLayout()
        opt.setSpacing(12)
        opt.addWidget(QLabel("清晰度"))
        self.cmb_q = QComboBox()
        self.cmb_q.addItems(["最高", "720p", "480p", "360p"])
        self.cmb_q.setFixedWidth(110)
        opt.addWidget(self.cmb_q)

        self.chk_v = QCheckBox("下视频")
        self.chk_v.setChecked(True)
        self.chk_p = QCheckBox("下图片")
        self.chk_p.setChecked(True)
        opt.addWidget(self.chk_v)
        opt.addWidget(self.chk_p)

        opt.addSpacing(8)
        self.btn_dir = QPushButton("选择保存目录")
        self.btn_dir.clicked.connect(self.on_pick_dir)
        opt.addWidget(self.btn_dir)
        self.edit_dir = QLineEdit(str(Path.home() / "Downloads" / "TwitterDL"))
        opt.addWidget(self.edit_dir, 1)
        self.btn_open = QPushButton("打开目录")
        self.btn_open.clicked.connect(self.on_open_dir)
        opt.addWidget(self.btn_open)
        root.addLayout(opt)

        # 下载控制
        act = QHBoxLayout()
        self.btn_dl = QPushButton("开始下载")
        self.btn_dl.setObjectName("primary")
        self.btn_dl.setEnabled(False)
        self.btn_dl.clicked.connect(self.on_download)
        act.addWidget(self.btn_dl)

        self.btn_stop = QPushButton("停止")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.on_stop)
        act.addWidget(self.btn_stop)

        self.bar = self._mk_bar()
        act.addWidget(self.bar, 1)
        root.addLayout(act)

        self.lbl_prog = QLabel("")
        self.lbl_prog.setStyleSheet(f"color:{C_DIM};")
        root.addWidget(self.lbl_prog)

        log_head = QLabel("日志")
        log_head.setObjectName("hint")
        root.addWidget(log_head)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(140)
        self.log.setStyleSheet(
            f"background:#171820; border:1px solid #3a3d4a; border-radius:6px; "
            f"font-family:'JetBrains Mono','Menlo',monospace; font-size:12px; color:#c9cddb;"
        )
        root.addWidget(self.log)

    def _mk_bar(self):
        from PySide6.QtWidgets import QProgressBar

        b = QProgressBar()
        b.setRange(0, 100)
        b.setValue(0)
        b.setTextVisible(False)
        return b

    # -------------------------------------------------------------- 小工具 --
    def log_line(self, msg: str, color: str = ""):
        self.log.setTextColor(QColor(color or "#c9cddb"))
        self.log.append(msg)
        self.log.moveCursor(QTextCursor.End)
        self._tick()

    @staticmethod
    def _tick():
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

    def set_stat(self, msg: str, color: str = C_DIM):
        self.lbl_stat.setText(msg)
        self.lbl_stat.setStyleSheet(f"color: {color};")

    def outdir(self) -> Path:
        return Path(os.path.expanduser(self.edit_dir.text().strip() or "~/Downloads/TwitterDL"))

    # ------------------------------------------------------------- 解析动作 --
    def on_paste(self):
        from PySide6.QtWidgets import QApplication

        txt = QApplication.clipboard().text().strip()
        if txt:
            cur = self.input.toPlainText().strip()
            self.input.setPlainText((cur + "\n" + txt).strip() if cur else txt)
            self.set_stat("已从剪贴板粘贴", C_ACCENT)

    def on_clear(self):
        self.table.setRowCount(0)
        self.tweets.clear()
        self._row_of.clear()
        self._thumbs.clear()
        self.preview.setText("选中一条看封面")
        self.preview.setPixmap(QPixmap())
        self.btn_dl.setEnabled(False)
        self.bar.setValue(0)
        self.lbl_prog.setText("")
        self.set_stat("列表已清空")

    def on_parse(self):
        refs = api.split_inputs(self.input.toPlainText())
        if not refs:
            QMessageBox.warning(self, "没识别到链接", "贴一个 x.com 或 twitter.com 的推文链接试试。")
            return
        self.on_clear()
        self.btn_parse.setEnabled(False)
        self.btn_dl.setEnabled(False)
        self.set_stat(f"正在解析 {len(refs)} 条…", C_WARN)
        self.log_line(f"开始解析 {len(refs)} 条推文")

        self.parse_worker = ParseWorker(refs, self)
        self.parse_worker.one.connect(self.on_tweet)
        self.parse_worker.failed.connect(self.on_parse_fail)
        self.parse_worker.log.connect(self.log_line)
        self.parse_worker.done.connect(self.on_parse_done)
        self.parse_worker.start()

    def on_tweet(self, tw):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.tweets.append(tw)
        self._row_of[tw.id] = row

        vid = sum(1 for m in tw.media if m.is_video)
        pic = sum(1 for m in tw.media if m.kind == "photo")
        parts = []
        if vid:
            parts.append(f"{vid} 视频")
        if pic:
            parts.append(f"{pic} 图")
        dur = next((m.duration for m in tw.media if m.is_video and m.duration), 0)

        cells = [
            tw.handle,
            tw.summary(36),
            " + ".join(parts) or "无媒体",
            (f"{dur:.1f} 秒" if dur else "—"),
            "已解析",
        ]
        for c, txt in enumerate(cells):
            it = QTableWidgetItem(txt)
            if c == 4:
                it.setForeground(QColor(C_OK))
            self.table.setItem(row, c, it)

        self.lbl_source.setText(f"解析接口：{tw.source}")
        self.btn_dl.setEnabled(True)
        self._refresh_quality_options()

        # 异步抓封面
        self.thumb_worker = FetchThumbWorker(tw, self)
        self.thumb_worker.got.connect(self._on_thumb)
        self.thumb_worker.start()
        self._tick()

    def _refresh_quality_options(self):
        """按已解析到的实际档位刷新清晰度下拉（有的推文有 1080p，有的只有 360p）。"""
        labels = set()
        for t in self.tweets:
            for m in t.media:
                if m.is_video:
                    labels.update(m.quality_labels())
        if not labels:
            return

        def num(lb):
            got = re.search(r"\d+", lb)
            return int(got.group()) if got else 0

        items = ["最高"] + sorted(labels, key=num, reverse=True)
        cur = self.cmb_q.currentText()
        self.cmb_q.clear()
        self.cmb_q.addItems(items)
        if cur in items:
            self.cmb_q.setCurrentText(cur)

    def _on_thumb(self, tid, data):
        pm = QPixmap()
        if pm.loadFromData(data):
            self._thumbs[tid] = pm
            row = self._row_of.get(tid)
            if row is not None and self.table.currentRow() == row:
                self._show_preview(tid)

    def on_parse_fail(self, ref, err):
        row = self.table.rowCount()
        self.table.insertRow(row)
        for c, txt in enumerate(["—", ref, "—", "—", "解析失败"]):
            it = QTableWidgetItem(txt)
            if c == 4:
                it.setForeground(QColor(C_ERR))
            it.setToolTip(err)
            self.table.setItem(row, c, it)
        self.log_line(f"  {ref} → {err}", C_ERR)

    def on_parse_done(self, ok, total):
        self.btn_parse.setEnabled(True)
        self.btn_dl.setEnabled(bool(self.tweets))
        if ok:
            self.set_stat(f"解析完成：成功 {ok} / {total} 条", C_OK)
        else:
            self.set_stat(f"解析失败：0 / {total} 条", C_ERR)

    # ------------------------------------------------------------- 预览 --
    def on_select(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.tweets):
            self._show_preview(self.tweets[row].id)
        else:
            self.lbl_meta.setText("")

    def _show_preview(self, tid):
        pm = self._thumbs.get(tid)
        if pm:
            self.preview.setPixmap(pm.scaled(self.preview.width(), self.preview.height(),
                                             Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.preview.setText("封面加载中…")
        tw = next((t for t in self.tweets if t.id == tid), None)
        if tw:
            self.lbl_meta.setText(f"@{tw.handle}\n{tw.author}\n{tw.created}\n{tw.text[:80]}")

    # ------------------------------------------------------------- 下载 --
    def on_pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择保存目录", str(self.outdir().parent))
        if d:
            self.edit_dir.setText(d)

    def on_open_dir(self):
        d = self.outdir()
        d.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["open", str(d)])

    def on_download(self):
        if not self.tweets:
            return
        if not self.chk_v.isChecked() and not self.chk_p.isChecked():
            QMessageBox.warning(self, "没勾选类型", "至少勾一个：下视频 或 下图片。")
            return
        jobs = [(t, t.media) for t in self.tweets]
        for t in self.tweets:
            row = self._row_of.get(t.id)
            if row is not None:
                it = self.table.item(row, 4)
                if it:
                    it.setText("排队中")
                    it.setForeground(QColor(C_WARN))
        self.btn_dl.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.bar.setValue(0)
        self.set_stat("开始下载…", C_WARN)
        self.log_line(f"输出目录：{self.outdir()}")

        self.dl_worker = DownloadWorker(
            jobs, self.outdir(),
            want_video=self.chk_v.isChecked(),
            want_photo=self.chk_p.isChecked(),
            quality=self.cmb_q.currentText(),
            parent=self,
        )
        self.dl_worker.log.connect(self.log_line)
        self.dl_worker.item_state.connect(self.on_item_state)
        self.dl_worker.progress.connect(self.on_progress)
        self.dl_worker.finished_all.connect(self.on_download_done)
        self.dl_worker.start()

    def on_stop(self):
        if self.dl_worker and self.dl_worker.isRunning():
            self.dl_worker.stop()
            self.set_stat("正在停止…", C_WARN)
            self.log_line("已请求停止，等当前文件收尾")

    def on_item_state(self, tid, state, note):
        row = self._row_of.get(tid)
        if row is None:
            return
        it = self.table.item(row, 4)
        if not it:
            return
        txt = {"pending": "排队中", "active": "下载中", "ok": "完成", "fail": "失败", "skip": "跳过"}.get(state, state)
        it.setText(f"{txt}  {note}" if note else txt)
        it.setForeground(QColor({"ok": C_OK, "fail": C_ERR, "active": C_WARN}.get(state, C_DIM)))
        it.setToolTip(note)
        self._tick()

    def on_progress(self, done, total, text):
        if total:
            self.bar.setValue(int(done / total * 100))
        self.lbl_prog.setText(text or f"{done} / {total}")
        self._tick()

    def on_download_done(self, ok, bad, outdir):
        self.btn_stop.setEnabled(False)
        self.btn_dl.setEnabled(True)
        if bad == 0:
            self.bar.setValue(100)
            self.set_stat(f"全部完成：{ok} 个文件", C_OK)
        else:
            self.set_stat(f"完成：{ok} 个成功，{bad} 个失败", C_WARN if ok else C_ERR)
        self.log_line(f"下载结束 → {outdir}")

    # ------------------------------------------------------------- 收尾 --
    def closeEvent(self, e):
        for w in (self.parse_worker, self.dl_worker, self.thumb_worker):
            if w and w.isRunning():
                if hasattr(w, "stop"):
                    w.stop()
                w.wait(1500)
        super().closeEvent(e)


def run():
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("推特视频下载器")
    win = MainWindow()
    win.show()
    return app.exec()
