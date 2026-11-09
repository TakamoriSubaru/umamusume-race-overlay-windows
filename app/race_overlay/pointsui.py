"""Small pictures (drawn with code, no image files) and cards for the Points tab."""

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF, QTextOption
from PyQt6.QtWidgets import QAbstractButton, QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from .theme import THEME


def _pen(color, width):
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def paint_icon(p, kind, rect, color=None, accent=None):
    """Draws a simple picture in a square: flag, count, screen, sheet, share, link, paste, arrow."""
    color = QColor(color or THEME["pink"])
    accent = QColor(accent or THEME["yellow"])
    dark = QColor(THEME["card2"])
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    side = min(rect.width(), rect.height())
    p.translate(rect.center().x() - side / 2.0, rect.center().y() - side / 2.0)
    p.scale(side / 48.0, side / 48.0)
    p.setBrush(Qt.BrushStyle.NoBrush)
    P = QPointF
    if kind == "flag":
        p.setPen(_pen(color, 3))
        p.drawLine(P(11, 6), P(11, 43))
        p.setPen(Qt.PenStyle.NoPen)
        for j in range(3):
            for i in range(4):
                p.setBrush(QBrush(accent if (i + j) % 2 == 0 else color))
                p.drawRect(QRectF(14 + i * 7, 7 + j * 7, 7, 7))
    elif kind == "count":
        p.setPen(_pen(color, 3))
        p.drawRoundedRect(QRectF(5, 11, 38, 26), 7, 7)
        f = QFont()
        f.setBold(True)
        f.setPixelSize(17)
        p.setFont(f)
        p.setPen(accent)
        p.drawText(QRectF(5, 11, 38, 26), "+1", QTextOption(Qt.AlignmentFlag.AlignCenter))
    elif kind == "screen":
        p.setPen(_pen(color, 3))
        p.drawRoundedRect(QRectF(5, 7, 38, 26), 5, 5)
        p.drawLine(P(24, 33), P(24, 40))
        p.drawLine(P(15, 41), P(33, 41))
        p.setPen(_pen(accent, 3))
        for y, w in ((14, 26), (20, 20), (26, 14)):
            p.drawLine(P(11, y), P(11 + w, y))
    elif kind == "sheet":
        p.setPen(_pen(color, 3))
        p.drawRoundedRect(QRectF(8, 5, 32, 38), 5, 5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(accent))
        p.drawRect(QRectF(10, 7, 28, 7))
        p.setPen(_pen(color, 2))
        p.drawLine(P(24, 14), P(24, 41))
        for y in (22, 30, 38):
            p.drawLine(P(10, y), P(38, y))
    elif kind == "share":
        a, b, c = P(13, 24), P(35, 12), P(35, 36)
        p.setPen(_pen(color, 3))
        p.drawLine(a, b)
        p.drawLine(a, c)
        p.setBrush(QBrush(dark))
        for pt in (a, b, c):
            p.drawEllipse(pt, 6, 6)
    elif kind == "link":
        p.setPen(_pen(color, 3.5))
        p.drawRoundedRect(QRectF(5, 17, 22, 14), 7, 7)
        p.setPen(_pen(accent, 3.5))
        p.drawRoundedRect(QRectF(21, 17, 22, 14), 7, 7)
    elif kind == "paste":
        p.setPen(_pen(color, 3))
        p.drawRoundedRect(QRectF(10, 9, 28, 34), 5, 5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(accent))
        p.drawRoundedRect(QRectF(17, 5, 14, 8), 3, 3)
        p.setPen(_pen(accent, 2.5))
        for y, x2 in ((22, 32), (29, 32), (36, 25)):
            p.drawLine(P(16, y), P(x2, y))
    elif kind == "arrow":
        p.setPen(_pen(color, 3))
        p.drawLine(P(8, 24), P(38, 24))
        p.drawPolyline(QPolygonF([P(29, 15), P(39, 24), P(29, 33)]))
    p.restore()


class IconWidget(QWidget):
    def __init__(self, kind, size=44, color=None, accent=None):
        super().__init__()
        self.kind, self.color, self.accent = kind, color, accent
        self.setFixedSize(size, size)

    def paintEvent(self, _e):
        p = QPainter(self)
        paint_icon(p, self.kind, QRectF(self.rect()).adjusted(1, 1, -1, -1), self.color, self.accent)


class Flow(QWidget):
    """A row of pictures with arrows: what happens, from left to right."""

    def __init__(self, items):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(14)
        lay.addStretch(1)
        for i, (kind, label) in enumerate(items):
            if i:
                lay.addWidget(IconWidget("arrow", 30, THEME["sub"]), 0, Qt.AlignmentFlag.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(2)
            col.addWidget(IconWidget(kind, 52), 0, Qt.AlignmentFlag.AlignHCenter)
            lb = QLabel(label)
            lb.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lb.setStyleSheet("font-weight:700;")
            col.addWidget(lb)
            lay.addLayout(col)
        lay.addStretch(1)


class ModeCard(QAbstractButton):
    """A big picture button with a title and one short line. Checked = the chosen one."""

    def __init__(self, kind, title, sub):
        super().__init__()
        self.kind, self.title, self.sub = kind, title, sub
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(76)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self):
        return QSize(190, 76)

    def minimumSizeHint(self):
        return QSize(120, 76)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        p.setPen(QPen(QColor(THEME["pink"] if on else THEME["line"]), 2.5 if on else 1.5))
        p.setBrush(QColor("#3a2650" if on else THEME["card2"]))
        p.drawRoundedRect(r, 12, 12)
        paint_icon(p, self.kind, QRectF(10, (self.height() - 42) / 2.0, 42, 42), THEME["pink"] if on else THEME["sub"])
        f = QFont(self.font())
        f.setBold(True)
        f.setPixelSize(14)
        p.setFont(f)
        p.setPen(QColor(THEME["text"]))
        w, h = self.width() - 66, self.height() / 2.0
        opt = QTextOption(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        opt.setWrapMode(QTextOption.WrapMode.WordWrap)
        p.drawText(QRectF(60, 6, w, h - 4), self.title, opt)
        f.setBold(False)
        f.setPixelSize(12)
        p.setFont(f)
        p.setPen(QColor(THEME["sub"]))
        opt = QTextOption(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        opt.setWrapMode(QTextOption.WrapMode.WordWrap)
        p.drawText(QRectF(60, h + 2, w, h - 8), self.sub, opt)


class StepCard(QFrame):
    """One numbered step with a picture, a short title and one small line."""

    def __init__(self, n, kind, title, sub):
        super().__init__()
        self.setObjectName("stepcard")
        self.setStyleSheet("QFrame#stepcard{background:%s;border:1px solid %s;border-radius:12px;}" % (THEME["card2"], THEME["line"]))
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(4)
        top = QHBoxLayout()
        badge = QLabel(str(n))
        badge.setFixedSize(22, 22)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet("background:%s;color:#2a1020;border-radius:11px;font-weight:800;" % THEME["pink"])
        top.addWidget(badge)
        top.addStretch(1)
        top.addWidget(IconWidget(kind, 38))
        v.addLayout(top)
        t = QLabel(title)
        t.setWordWrap(True)
        t.setStyleSheet("font-weight:700;font-size:13px;")
        v.addWidget(t)
        s = QLabel(sub)
        s.setWordWrap(True)
        s.setStyleSheet("color:%s;font-size:11px;" % THEME["sub"])
        v.addWidget(s)
        v.addStretch(1)
