"""Look of the settings window."""

import os
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QWidget



THEME = {"bg": "#17141f", "card": "#221e2e", "card2": "#2b2640", "line": "#3a3354", "input": "#13101a",
         "text": "#f4eefc", "sub": "#a9a0c4", "pink": "#ff6fae", "pink2": "#ff9a6f", "yellow": "#ffd24a",
         "mint": "#5de6c2", "violet": "#b56cff", "sky": "#6cb8ff"}


def make_check_icon():
    """Draws the little white tick for the check boxes and returns its file path ('' if it fails)."""
    try:
        import tempfile
        path = os.path.join(tempfile.gettempdir(), "race-overlay-native-check.png")
        pm = QPixmap(20, 20)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#2a1020"), 2.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPolyline([QPointF(5, 10.5), QPointF(8.5, 14), QPointF(15, 6.5)])
        p.end()
        return path if pm.save(path, "PNG") else ""
    except Exception:
        return ""


def build_theme_qss():
    t = THEME
    check = make_check_icon()
    check_rule = ("image: url(%s);" % check.replace("\\", "/")) if check else ""
    grad = "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %s, stop:1 %s)" % (t["pink"], t["pink2"])
    return """
QDialog, QMessageBox, QInputDialog, QFileDialog, QColorDialog { background: %(bg)s; }
QWidget { color: %(text)s; font-size: 13px; }
QToolTip { background: %(card2)s; color: %(text)s; border: 1px solid %(pink)s; padding: 4px; }
QLabel { background: transparent; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QTabWidget::pane { border: 1px solid %(line)s; border-radius: 14px; background: #1c1826; top: -2px; }
QTabBar { background: transparent; }
QTabBar::tab { background: %(card2)s; color: #c9c0e6; padding: 9px 13px; margin: 0 4px 8px 0;
               border-radius: 17px; font-weight: 700; }
QTabBar::tab:hover:!selected { background: #3a3258; color: #ffffff; }
QTabBar::tab:selected { background: %(grad)s; color: #2a1020; }
QGroupBox { background: %(card)s; border: 1px solid %(line)s; border-radius: 14px; margin-top: 20px;
            padding: 16px 12px 12px 12px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 14px; padding: 3px 14px;
                   background: %(yellow)s; color: #3a2a00; border-radius: 11px; font-weight: 800; }
QPushButton { background: %(card2)s; border: 1px solid #4a4068; border-radius: 12px; padding: 8px 16px;
              font-weight: 700; }
QPushButton:hover { background: #3b3259; border-color: %(pink)s; }
QPushButton:pressed { background: %(pink)s; color: #2a1020; }
QPushButton:disabled { color: #7a7296; background: %(card)s; border-color: %(line)s; }
QPushButton#primary { background: %(grad)s; color: #2a1020; border: none; }
QPushButton#primary:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #ff86bd, stop:1 #ffb085); }
QPushButton#fold { text-align: left; background: transparent; border: none; color: %(yellow)s;
                   font-weight: 800; padding: 8px 4px; }
QPushButton#fold:hover { color: #ffffff; }
QPushButton#danger { background: #3a1f33; border-color: #7a3a63; color: #ffc2dc; }
QPushButton#danger:hover { background: #5a2850; border-color: %(pink)s; }
QLineEdit, QComboBox, QFontComboBox, QSpinBox, QDoubleSpinBox { background: %(input)s; border: 1px solid #4a4068; border-radius: 10px;
                                      padding: 6px 10px; selection-background-color: %(pink)s;
                                      selection-color: #2a1020; }
QLineEdit:focus, QComboBox:focus { border-color: %(pink)s; }
QLineEdit:read-only { color: %(sub)s; }
QComboBox::drop-down { border: none; width: 28px; }
QComboBox::down-arrow { width: 10px; height: 10px; }
QComboBox QAbstractItemView { background: %(card)s; border: 1px solid #4a4068; outline: 0;
                              selection-background-color: %(pink)s; selection-color: #2a1020; }
QCheckBox { spacing: 10px; background: transparent; }
QCheckBox::indicator { width: 20px; height: 20px; border-radius: 7px; border: 2px solid #5a4f80;
                       background: %(input)s; }
QCheckBox::indicator:hover { border-color: %(pink)s; }
QCheckBox::indicator:checked { background: %(mint)s; border-color: %(mint)s; %(check)s }
QSlider::groove:horizontal { height: 8px; background: %(input)s; border: 1px solid %(line)s; border-radius: 5px; }
QSlider::sub-page:horizontal { background: %(grad)s; border-radius: 5px; }
QSlider::handle:horizontal { background: #ffffff; border: 3px solid %(pink)s; width: 14px; height: 14px;
                             margin: -8px 0; border-radius: 10px; }
QPlainTextEdit { background: %(input)s; border: 1px solid %(line)s; border-radius: 12px; padding: 6px;
                 font-family: monospace; font-size: 11px; selection-background-color: rgba(255,111,174,95); }
QTableWidget { background: %(input)s; alternate-background-color: #191521; border: 1px solid %(line)s;
               border-radius: 12px; gridline-color: transparent;
               selection-background-color: rgba(255,111,174,95); selection-color: #ffffff; outline: 0; }
QTableWidget::item { padding: 5px; }
QHeaderView::section { background: %(card2)s; color: %(yellow)s; border: none; padding: 8px; font-weight: 800; }
QTableCornerButton::section { background: %(card2)s; border: none; }
QTreeView, QListView { background: %(input)s; border: 1px solid %(line)s; border-radius: 8px; outline: 0;
                       selection-background-color: rgba(255,111,174,95); }
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: #4d4470; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: %(pink)s; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: #4d4470; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: %(pink)s; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
""" % dict(t, grad=grad, check=check_rule)


class Banner(QWidget):
    """The coloured title strip at the top of the Settings window. Drawn with code only
    (gradient, sparkles, a chequered finish line): no game artwork is used."""

    def __init__(self, title, subtitle):
        super().__init__()
        self.title, self.subtitle = title, subtitle
        self.setFixedHeight(92)

    def paintEvent(self, _ev):
        t = THEME
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        rect = QRectF(0, 0, w, h)
        path = QPainterPath()
        path.addRoundedRect(rect, 20, 20)
        g = QLinearGradient(0, 0, w, h)
        g.setColorAt(0.0, QColor(t["pink"]))
        g.setColorAt(0.55, QColor(t["violet"]))
        g.setColorAt(1.0, QColor(t["sky"]))
        p.fillPath(path, QBrush(g))
        p.setClipPath(path)
        # speed lines
        p.setPen(QPen(QColor(255, 255, 255, 40), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i, (y, x0, ln) in enumerate(((18, 0.50, 0.22), (34, 0.58, 0.16), (50, 0.46, 0.26), (66, 0.62, 0.14))):
            p.drawLine(QPointF(w * x0, y), QPointF(w * (x0 + ln), y))
        # chequered finish line on the right
        cell = 11
        cols = 4
        x_start = w - cols * cell - 18
        for r in range(0, int(h // cell) + 1):
            for c in range(cols):
                if (r + c) % 2 == 0:
                    p.fillRect(QRectF(x_start + c * cell, r * cell + 4, cell, cell), QColor(255, 255, 255, 210))
                else:
                    p.fillRect(QRectF(x_start + c * cell, r * cell + 4, cell, cell), QColor(30, 20, 50, 170))
        # sparkles
        p.setPen(Qt.PenStyle.NoPen)
        for (sx, sy, sr, col) in ((0.40, 0.30, 7, t["yellow"]), (0.47, 0.72, 5, "#ffffff"),
                                  (0.66, 0.26, 4, "#ffffff"), (0.72, 0.68, 6, t["yellow"])):
            self._star(p, w * sx - 20, h * sy, sr, QColor(col))
        # text
        p.setClipping(False)
        f = QFont(self.font())
        f.setPointSize(19)
        f.setWeight(QFont.Weight.ExtraBold)
        p.setFont(f)
        p.setPen(QColor(0, 0, 0, 70))
        p.drawText(QRectF(23, 13, w - 120, 42), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.title)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(22, 11, w - 120, 42), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.title)
        f2 = QFont(self.font())
        f2.setPointSize(10)
        f2.setWeight(QFont.Weight.DemiBold)
        p.setFont(f2)
        p.setPen(QColor(255, 255, 255, 225))
        p.drawText(QRectF(22, 54, w - 120, 26), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.subtitle)
        p.end()

    @staticmethod
    def _star(p, cx, cy, r, color):
        path = QPainterPath()
        path.moveTo(cx, cy - r)
        path.quadTo(cx, cy, cx + r, cy)
        path.quadTo(cx, cy, cx, cy + r)
        path.quadTo(cx, cy, cx - r, cy)
        path.quadTo(cx, cy, cx, cy - r)
        p.fillPath(path, QBrush(color))
