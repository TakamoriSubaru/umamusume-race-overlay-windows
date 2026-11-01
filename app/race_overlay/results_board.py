"""The results board: a second window that shows the final placings after a race,
laid out in two columns like a TV "stage points" graphic. In OBS it is its own window
("Umamusume Race Results (Windows)"), so you can put it anywhere on the stream."""

import math
import os
import time
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QMenu, QWidget

from .constants import PODIUM, RESULTS_NAME, SCRIPT_DIR, SLIDE_SECONDS
from .frameless import FramelessMixin, fit_window

# design size, in "logical units" (everything is drawn at this size and scaled to the window width)
PAD = 12            # space at the left / right / bottom edge
COL_W = 300         # one column of placings
GUTTER = 12         # space between the two columns
TOP_H = 54          # title band
SUB_H = 24          # the "TIME" label row
ROW_H = 46          # one placing
FOOT_H = 40         # track name band
ONE_COLUMN_MAX = 6  # up to this many umas: one column, more: two columns


PTS_W = 56          # extra width of the points column (only when the race is scored)


class ResultsBoard(FramelessMixin, QWidget):
    NAME = RESULTS_NAME         # <- the window name you pick in OBS
    TITLE = "RACE RESULTS"
    TITLE_KEY = "results_title"      # setting with your own title
    STAY_KEY = "results_seconds"     # setting: how long the board stays
    POS_KEY, SCALE_KEY = "results_pos", "results_scale"

    def __init__(self, ov):
        super().__init__()
        self.ov = ov
        self.setWindowTitle(self.NAME)
        self.setMinimumSize(220, 100)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        if ov.args.transparent:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.entries = []        # [{"h": Horse, "place": int, "time": str, "gap": str}]
        self.footer = ""
        self.cols = 2
        self.per_col = 0
        self.col_w = COL_W
        self.lw, self.lh = 2 * PAD + 2 * COL_W + GUTTER, 300
        self.slide = 0.0         # 0 = out, 1 = fully in
        self.want = 0.0
        self.pending_at = None   # when the board should start to slide in
        self.deadline = None     # when it should leave again
        self.pinned = False      # "Show results board": stays visible so you can place it

        icon = os.path.join(SCRIPT_DIR, "icon.png")
        self.icon = None
        if os.path.isfile(icon):
            pm = QPixmap(icon)
            if not pm.isNull():
                self.icon = pm.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)

        self.pref_scale = float(ov.cfg.get(self.SCALE_KEY) or 1.0)
        pos = ov.cfg.get(self.POS_KEY)
        self._placed = bool(pos and not ov.args.reset_window)
        if self._placed:
            self.move(int(pos[0]), int(pos[1]))
        self.apply_flags(initial=True)

    def logical_w(self):
        return self.lw

    # ----- window flags ---------------------------------------------------------------
    def apply_flags(self, initial=False):
        a, s = self.ov.args, self.ov.s
        flags = Qt.WindowType.Window
        if a.frameless or a.transparent or not s.get("title_bar", False):
            flags |= Qt.WindowType.FramelessWindowHint
        if s.get("on_top", True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        if initial:
            self.setWindowFlags(flags)
            return
        was_visible = self.isVisible()
        geo = self.geometry()
        self.setWindowFlags(flags)
        if was_visible:
            self.show()
        self.setGeometry(geo)

    # ----- data -----------------------------------------------------------------------
    def set_data(self, entries, footer):
        self.entries = list(entries)
        self.footer = footer or ""
        n = len(self.entries)
        self.cols = 1 if n <= ONE_COLUMN_MAX else 2
        self.per_col = int(math.ceil(n / float(self.cols))) if n else 0
        self.col_w = COL_W + (PTS_W if any("pts" in e for e in self.entries) else 0)
        self.lw = 2 * PAD + self.cols * self.col_w + (self.cols - 1) * GUTTER
        self.lh = TOP_H + SUB_H + max(1, self.per_col) * ROW_H + FOOT_H + PAD
        fit_window(self, self.lw, self.lh, self.pref_scale)
        if not self._placed:
            scr = self.screen()
            if scr is not None:
                av = scr.availableGeometry()
                self.move(av.center().x() - self.width() // 2, av.center().y() - self.height() // 2)
            self._placed = True

    def refit(self):
        if self.entries:
            fit_window(self, self.lw, self.lh, self.pref_scale)

    # ----- showing and hiding -----------------------------------------------------------
    def stay(self):
        return float(self.ov.s.get(self.STAY_KEY, 10.0))

    def title_now(self):
        return (self.ov.s.get(self.TITLE_KEY, "") or "").strip().upper() or self.TITLE

    def hold_forever(self):
        return bool(self.ov.args.hold) or self.stay() <= 0

    def present(self, entries, footer, delay):
        """Show the board `delay` seconds from now (and for results_seconds after that)."""
        self.set_data(entries, footer)
        self.pending_at = time.monotonic() + max(0.0, delay)
        self.deadline = None

    def dismiss(self):
        """A new race starts: the board goes away (unless you are placing it)."""
        self.pending_at = None
        self.deadline = None
        if not self.pinned:
            self.want = 0.0

    def set_pinned(self, on, sample=None):
        """Keep the board on screen so it can be placed. `sample` = (entries, footer) when there is nothing to show."""
        self.pinned = bool(on)
        if on:
            if not self.entries and sample:
                self.set_data(*sample)
            self.pending_at = None
            self.deadline = None
            self.want = 1.0
            self._reveal()
        else:
            self.want = 0.0

    def _reveal(self):
        self.slide = 0.0
        self.show()
        self.raise_()

    def tick(self, now, dt):
        if self.pending_at is not None and now >= self.pending_at:
            self.pending_at = None
            self.want = 1.0
            self._reveal()
            self.deadline = None if self.hold_forever() else now + self.stay()
        if self.deadline is not None and now >= self.deadline and not self.pinned:
            self.deadline = None
            self.want = 0.0
        step = dt / SLIDE_SECONDS
        if self.slide < self.want:
            self.slide = min(self.want, self.slide + step)
        elif self.slide > self.want:
            self.slide = max(self.want, self.slide - step)
        if self.isVisible():
            if self.want == 0.0 and self.slide <= 0.0 and not self.pinned:
                self.hide()
            else:
                self.update()

    def remember(self):
        """Keep the position and size for the next start."""
        self.ov.cfg[self.POS_KEY] = [self.x(), self.y()]
        self.ov.cfg[self.SCALE_KEY] = round(self.pref_scale, 4)

    # ----- drawing ----------------------------------------------------------------------
    def paintEvent(self, _ev):
        ov = self.ov
        a, s = ov.args, ov.s
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                         | QPainter.RenderHint.SmoothPixmapTransform)
        panel = QColor(s["bg"])
        panel.setAlphaF(float(s["bg_opacity"]))
        if a.chroma:
            p.fillRect(self.rect(), QColor(a.chroma_color))
        elif not a.transparent:
            p.fillRect(self.rect(), QColor(s["bg"]))
        if not self.entries or self.slide <= 0.01:
            p.end()
            return

        scale = self.width() / float(self.lw)
        p.scale(scale, scale)
        lw, lh = self.lw, self.height() / scale
        e = 1.0 - (1.0 - max(0.0, min(1.0, self.slide))) ** 3      # ease out
        d = self.side_for(s.get("slide", "auto"))
        if d:
            p.translate(d * (1.0 - e) * lw, 0)
        p.setOpacity(e)
        if a.chroma or a.transparent:
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, lw, lh), 10, 10)
            p.fillPath(path, panel)

        tc, sc, ac = QColor(s["text_color"]), QColor(s["sub_color"]), QColor(s.get("accent") or "#f5c518")
        self.draw_title(p, lw, tc, ac)
        self.draw_columns(p, tc, sc, ac)
        self.draw_footer(p, lw, lh, ac)
        p.end()

    def spaced(self, px, bold, spacing):
        f = self.ov.fnt(px, bold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
        return f

    def band(self):
        """The darker strip behind the title and the track name; lighter on a light background."""
        return QColor(0, 0, 0, 70 if QColor(self.ov.s["bg"]).lightness() < 128 else 22)

    def draw_title(self, p, lw, tc, ac):
        p.fillRect(QRectF(0, 0, lw, TOP_H), self.band())
        p.fillRect(QRectF(0, TOP_H - 3, lw, 3), ac)
        if self.icon is not None:
            p.drawPixmap(QRectF(PAD, 8, 38, 38), self.icon, QRectF(self.icon.rect()))
        p.setFont(self.spaced(24, True, 2.5))
        p.setPen(tc)
        p.drawText(QRectF(0, 0, lw, TOP_H - 3), Qt.AlignmentFlag.AlignCenter, getattr(self, "TITLE_TEXT", None) or self.title_now())

    def has_pts(self):
        return any("pts" in e for e in self.entries)

    def draw_columns(self, p, tc, sc, ac):
        for c in range(self.cols):
            x = PAD + c * (self.col_w + GUTTER)
            p.setFont(self.spaced(10, True, 1.5))
            p.setPen(sc)
            pw = PTS_W if self.has_pts() else 0
            p.drawText(QRectF(x, TOP_H, self.col_w - 10 - pw, SUB_H),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "TIME")
            if pw:
                p.drawText(QRectF(x, TOP_H, self.col_w - 10, SUB_H),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "PTS")
        for i, ent in enumerate(self.entries):
            c, r = divmod(i, self.per_col)
            x = PAD + c * (self.col_w + GUTTER)
            y = TOP_H + SUB_H + r * ROW_H
            self.draw_entry(p, ent, x, y, tc, sc, ac)

    def draw_entry(self, p, ent, x, y, tc, sc, ac):
        ov, h = self.ov, ent["h"]
        place = ent["place"]
        podium = ov.podium(place - 1) if place <= 3 else None
        rh = ROW_H - 4

        row = QPainterPath()
        row.addRoundedRect(QRectF(x, y, self.col_w, rh), 6, 6)
        bg = QColor(tc)
        bg.setAlpha(20)
        p.fillPath(row, bg)
        if place == 1:
            win = QColor(ac)
            win.setAlpha(40)
            p.fillPath(row, win)
        team_col = QColor(ent["team_color"]) if ent.get("team_color") else None
        if team_col is not None:                      # team match: the row is tinted in the team colour
            tint = QColor(team_col)
            tint.setAlpha(56)
            p.fillPath(row, tint)
        if podium is not None:
            strip = QPainterPath()
            strip.addRoundedRect(QRectF(x, y + 5, 3.5, rh - 10), 1.75, 1.75)
            p.fillPath(strip, podium)

        # placing number
        p.setFont(ov.fnt(17, True))
        p.setPen(podium if podium is not None else tc)
        p.drawText(QRectF(x + 8, y, 30, rh), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "%d." % place)

        # picture(s): same choice as the tower (uma / player / both)
        asz = 34
        ov.draw_pictures(p, h, QRectF(x + 40, y + (rh - asz) / 2.0, asz, asz), tc)

        # names
        name_x = x + 82
        time_w = 92
        pw = PTS_W if "pts" in ent else 0
        name_w = self.col_w - 82 - time_w - 4 - pw
        head, label = ov.name_parts(h)
        tf = ov.fnt(13, True)
        p.setFont(tf)
        p.setPen(tc)
        if label:
            p.drawText(QRectF(name_x, y + 5, name_w, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(tf).elidedText(head, Qt.TextElideMode.ElideRight, int(name_w)))
            nf = ov.fnt(10)
            for px in (9.0, 8.0):
                if QFontMetrics(nf).horizontalAdvance(label) <= name_w:
                    break
                nf = ov.fnt(px)
            p.setFont(nf)
            p.setPen(sc)
            p.drawText(QRectF(name_x, y + 23, name_w, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(nf).elidedText(label, Qt.TextElideMode.ElideRight, int(name_w)))
        else:                                     # one name only: it is the headline
            p.drawText(QRectF(name_x, y, name_w, rh), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(tf).elidedText(head, Qt.TextElideMode.ElideRight, int(name_w)))

        # time + gap to the winner
        tx = x + self.col_w - time_w - 8 - pw
        if pw:
            p.setFont(ov.fnt(17, True, mono=True))
            p.setPen(team_col if team_col is not None else (ac if place == 1 else tc))
            p.drawText(QRectF(x + self.col_w - pw - 6, y, pw, rh),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(ent["pts"]))
        details = ov.s.get("results_details", "both")
        if details != "none":
            p.setFont(ov.fnt(14, True, mono=True))
            p.setPen(tc)
            p.drawText(QRectF(tx, y + 5, time_w, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       ent["time"])
        if details == "both":
            p.setFont(ov.fnt(10, place == 1))
            p.setPen(ac if place == 1 else sc)
            p.drawText(QRectF(tx, y + 23, time_w, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       ent["gap"])

    def draw_footer(self, p, lw, lh, ac):
        p.fillRect(QRectF(0, lh - FOOT_H, lw, FOOT_H), self.band())
        f = self.spaced(15, True, 1.2)
        text = QFontMetrics(f).elidedText((self.footer or "RACE").upper(), Qt.TextElideMode.ElideRight, int(lw - 24))
        p.setFont(f)
        p.setPen(ac)
        p.drawText(QRectF(0, lh - FOOT_H, lw, FOOT_H), Qt.AlignmentFlag.AlignCenter, text)

    # ----- mouse / keyboard / menu --------------------------------------------------------
    def contextMenuEvent(self, ev):
        m = QMenu(self)
        m.addAction("Settings...", self.ov.open_settings)
        m.addAction("Hide the results board", lambda: self.hide_now())
        m.exec(ev.globalPos())

    def hide_now(self):
        self.pinned = False
        self.pending_at = None
        self.deadline = None
        self.want = 0.0
        self.slide = 0.0
        self.hide()
        self.ov.refresh_tray()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.hide_now()

    def hideEvent(self, ev):
        super().hideEvent(ev)
        if self.entries:
            self.remember()

    def closeEvent(self, ev):
        if not self.ov.quitting:
            self.hide_now()
            ev.ignore()
            return
        ev.accept()
