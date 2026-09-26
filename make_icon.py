"""生成 app 图标（icon.png 1024x1024）。QPainter 必须在 QApplication 之后用。"""
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication

S = 1024
OUT = Path(__file__).with_name("icon.png")


def draw() -> QPixmap:
    pm = QPixmap(S, S)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)

    # 圆角底：深蓝到黑的渐变，模仿 macOS 图标圆角
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
    shaft = QRectF(cx - 62, 250, 124, 250)
    p.drawRoundedRect(shaft, 20, 20)
    head = QPainterPath()
    head.moveTo(cx - 175, 470)
    head.lineTo(cx + 175, 470)
    head.lineTo(cx, 690)
    head.closeSubpath()
    p.fillPath(head, QBrush(white))

    # 承接盘（两条横线）
    p.setBrush(white)
    p.drawRoundedRect(QRectF(255, 745, 514, 46), 23, 23)
    p.drawRoundedRect(QRectF(340, 830, 344, 38), 19, 19)

    # 右下角 X 标记
    p.setPen(QPen(white, 34, Qt.SolidLine, Qt.RoundCap))
    ox, oy, L = S - 250, S - 250, 110
    p.drawLine(QPointF(ox - L, oy - L), QPointF(ox + L, oy + L))
    p.drawLine(QPointF(ox + L, oy - L), QPointF(ox - L, oy + L))

    p.end()
    return pm


def main():
    app = QApplication(sys.argv)          # noqa: F841  QPixmap 之前必须先有 QApplication
    pm = draw()
    pm.save(str(OUT), "PNG")
    print(f"图标已生成：{OUT}  {pm.width()}x{pm.height()}")


if __name__ == "__main__":
    main()
