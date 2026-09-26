"""生成图标：icon.png（1024x1024，给 macOS 转 icns）+ icon.ico（多尺寸，给 Windows）。

QPainter 必须在 QApplication 之后才能用。
跑法：QT_QPA_PLATFORM=offscreen python make_icon.py
"""
import struct
import sys
from io import BytesIO
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication

S = 1024
HERE = Path(__file__).parent
OUT_PNG = HERE / "icon.png"
OUT_ICO = HERE / "icon.ico"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def draw() -> QPixmap:
    pm = QPixmap(S, S)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)

    # 圆角底：深蓝到黑的渐变
    g = QLinearGradient(0, 0, 0, S)
    g.setColorAt(0.0, QColor("#3b6df0"))
    g.setColorAt(1.0, QColor("#111a33"))
    path = QPainterPath()
    path.addRoundedRect(QRectF(62, 62, S - 124, S - 124), 200, 200)
    p.fillPath(path, QBrush(g))

    # 细边
    p.setPen(QPen(QColor(255, 255, 255, 40), 6))
    p.drawPath(path)

    white = QColor("#ffffff")

    # 下载箭头
    cx = S / 2
    p.setPen(Qt.NoPen)
    p.setBrush(white)
    p.drawRoundedRect(QRectF(cx - 62, 250, 124, 250), 20, 20)
    head = QPainterPath()
    head.moveTo(cx - 175, 470)
    head.lineTo(cx + 175, 470)
    head.lineTo(cx, 690)
    head.closeSubpath()
    p.fillPath(head, QBrush(white))

    # 承接盘（两条横线）
    p.drawRoundedRect(QRectF(255, 745, 514, 46), 23, 23)
    p.drawRoundedRect(QRectF(340, 830, 344, 38), 19, 19)

    # 右下角 X 标记
    p.setPen(QPen(white, 34, Qt.SolidLine, Qt.RoundCap))
    ox, oy, L = S - 250, S - 250, 110
    p.drawLine(QPointF(ox - L, oy - L), QPointF(ox + L, oy + L))
    p.drawLine(QPointF(ox + L, oy - L), QPointF(ox - L, oy + L))

    p.end()
    return pm


def png_bytes(pm: QPixmap) -> bytes:
    # 注意：QByteArray 必须留一个 Python 引用，否则临时对象被回收会让 QBuffer 崩掉（实测 segfault）
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    pm.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def write_ico(pm: QPixmap, path: Path, sizes=ICO_SIZES) -> list:
    """手写 ICO —— Vista 以后 ICO 里可以直接塞 PNG，不需要 BMP/调色板。

    结构：ICONDIR(6 字节) + N × ICONDIRENTRY(16 字节) + N 段 PNG 数据。
    """
    blobs = []
    for s in sizes:
        scaled = pm.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        blobs.append((s, png_bytes(scaled)))

    header = struct.pack("<HHH", 0, 1, len(blobs))          # reserved, type=1(icon), count
    offset = len(header) + 16 * len(blobs)
    entries, data = b"", b""
    for size, blob in blobs:
        entries += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,   # 宽（256 要写 0）
            0 if size >= 256 else size,   # 高
            0,                            # 调色板色数（PNG 用不到）
            0,                            # reserved
            1,                            # color planes
            32,                           # bits per pixel
            len(blob),
            offset,
        )
        data += blob
        offset += len(blob)
    path.write_bytes(header + entries + data)
    return [s for s, _ in blobs]


def main():
    from twdownloader.compat import enable_utf8_stdout

    enable_utf8_stdout()
    app = QApplication(sys.argv)          # noqa: F841  QPixmap 之前必须先有 QApplication
    pm = draw()
    pm.save(str(OUT_PNG), "PNG")
    print(f"图标已生成：{OUT_PNG}  {pm.width()}x{pm.height()}")
    sizes = write_ico(pm, OUT_ICO)
    print(f"图标已生成：{OUT_ICO}  尺寸 {sizes}  {OUT_ICO.stat().st_size} 字节")


if __name__ == "__main__":
    main()
