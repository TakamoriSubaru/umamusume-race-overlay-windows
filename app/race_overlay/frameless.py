"""Behaviour shared by the tower window and the results board:
drag to move, pull the edges to resize, which side to slide in from, and fitting the window to its content."""

from PyQt6.QtCore import Qt


def fit_window(win, logical_w, logical_h, scale):
    """Resize `win` so its content (logical_w x logical_h units) fits exactly at `scale`.
    The scale is lowered when the content would not fit on the screen, and the window is
    pulled back onto the screen when growing pushed it off the edge."""
    scr = win.screen()
    av = scr.availableGeometry() if scr is not None else None
    if av is not None:
        scale = min(scale, av.height() * 0.95 / logical_h, av.width() * 0.95 / logical_w)
    scale = max(scale, 0.3)
    w = max(win.minimumWidth(), int(round(logical_w * scale)))
    h = max(win.minimumHeight(), int(round(logical_h * w / logical_w)))
    win._fitting = True
    try:
        win.resize(w, h)
    finally:
        win._fitting = False
    if av is not None and win.isVisible():
        x = min(win.x(), av.right() - w + 1)
        y = min(win.y(), av.bottom() - h + 1)
        x, y = max(av.left(), x), max(av.top(), y)
        if (x, y) != (win.x(), win.y()):
            win.move(x, y)


class FramelessMixin:
    """Put this before QWidget in the class list. The class provides `logical_w()`."""

    _fitting = False        # True while the program itself resizes the window
    pref_scale = 1.0        # the size the user chose, as a scale (1.0 = the design size)

    def logical_w(self):
        raise NotImplementedError

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if not self._fitting and self.width() > 0:
            self.pref_scale = self.width() / float(self.logical_w())   # the user (or a saved size) chose this

    # ---- which side the window slides in from
    def side_for(self, mode):
        """-1 = from the left, +1 = from the right, 0 = no sliding (fade only)."""
        if mode == "left":
            return -1
        if mode == "right":
            return 1
        if mode == "off":
            return 0
        scr = self.screen()
        if scr is None:
            return 1
        return 1 if self.geometry().center().x() > scr.geometry().center().x() else -1

    # ---- no title bar: drag to move, pull an edge to resize
    def _edges_at(self, pos):
        m = 7
        e = Qt.Edge(0)
        if pos.x() <= m:
            e |= Qt.Edge.LeftEdge
        if pos.x() >= self.width() - m:
            e |= Qt.Edge.RightEdge
        if pos.y() <= m:
            e |= Qt.Edge.TopEdge
        if pos.y() >= self.height() - m:
            e |= Qt.Edge.BottomEdge
        return e

    def mouseMoveEvent(self, ev):
        if not (self.windowFlags() & Qt.WindowType.FramelessWindowHint):
            return
        e = self._edges_at(ev.position().toPoint())
        L, R, T, B = Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.TopEdge, Qt.Edge.BottomEdge
        if (e & L and e & T) or (e & R and e & B):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif (e & R and e & T) or (e & L and e & B):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif e & L or e & R:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif e & T or e & B:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.unsetCursor()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.windowFlags() & Qt.WindowType.FramelessWindowHint:
            wh = self.windowHandle()
            if wh is None:
                return
            e = self._edges_at(ev.position().toPoint())
            if e and hasattr(wh, "startSystemResize"):
                wh.startSystemResize(e)
            elif hasattr(wh, "startSystemMove"):
                wh.startSystemMove()
