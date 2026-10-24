"""Tray icon drawing."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap



def make_tray_icon(base, color):
    """The program icon with a small status dot (green = working, yellow = waiting, red = problem)."""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    pt = QPainter(pm)
    pt.setRenderHint(QPainter.RenderHint.Antialiasing)
    pt.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if base is not None and not base.isNull():
        pt.drawPixmap(0, 0, base.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))
    else:
        pt.setBrush(QColor("#6a3fc0"))
        pt.setPen(Qt.PenStyle.NoPen)
        pt.drawRoundedRect(4, 4, 56, 56, 14, 14)
    pt.setBrush(QColor(color))
    pt.setPen(QPen(QColor("#ffffff"), 4))
    pt.drawEllipse(34, 34, 26, 26)
    pt.end()
    return QIcon(pm)
