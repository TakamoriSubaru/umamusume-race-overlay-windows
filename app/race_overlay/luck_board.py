"""The skill luck board: the luckiest and the unluckiest players of the race (how many of their skills
activated). It comes in after the results board. In OBS it is its own window ("Umamusume Skill Luck (Windows)")."""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QPainterPath

from .constants import LUCK_NAME
from .frameless import fit_window
from .results_board import COL_W, FOOT_H, GUTTER, PAD, ROW_H, SUB_H, TOP_H, ResultsBoard

GOOD, BAD = "#4cd9a0", "#ff6b81"


class LuckBoard(ResultsBoard):
    NAME = LUCK_NAME
    TITLE = "SKILL LUCK"
    TITLE_KEY = "luck_title"
    STAY_KEY = "luck_seconds"
    POS_KEY, SCALE_KEY = "luck_pos", "luck_scale"

    def set_data(self, entries, footer):
        self.entries = list(entries)
        self.footer = footer or ""
        self.cols = 2
        self.col_w = COL_W
        self.per_col = max(1, max((sum(1 for e in self.entries if e["side"] == s) for s in ("lucky", "unlucky")),
                                  default=1))
        self.lw = 2 * PAD + 2 * COL_W + GUTTER
        self.lh = TOP_H + SUB_H + self.per_col * ROW_H + FOOT_H + PAD
        fit_window(self, self.lw, self.lh, self.pref_scale)
        if not self._placed:
            scr = self.screen()
            if scr is not None:
                av = scr.availableGeometry()
                self.move(av.center().x() - self.width() // 2, av.center().y() - self.height() // 2)
            self._placed = True

    def draw_columns(self, p, tc, sc, ac):
        for c, (side, label, col) in enumerate((("lucky", "LUCKIEST", GOOD), ("unlucky", "UNLUCKIEST", BAD))):
            x = PAD + c * (COL_W + GUTTER)
            p.setFont(self.spaced(11, True, 1.8))
            p.setPen(QColor(col))
            p.drawText(QRectF(x + 8, TOP_H, COL_W - 16, SUB_H),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
            for r, ent in enumerate([e for e in self.entries if e["side"] == side]):
                self.draw_entry(p, ent, x, TOP_H + SUB_H + r * ROW_H, tc, sc, ac, QColor(col))

    def draw_entry(self, p, ent, x, y, tc, sc, ac, col=None):
        ov, h = self.ov, ent["h"]
        rh = ROW_H - 4
        row = QPainterPath()
        row.addRoundedRect(QRectF(x, y, COL_W, rh), 6, 6)
        bg = QColor(tc)
        bg.setAlpha(20)
        p.fillPath(row, bg)
        strip = QPainterPath()
        strip.addRoundedRect(QRectF(x, y + 5, 3.5, rh - 10), 1.75, 1.75)
        p.fillPath(strip, col)
        asz = 34
        ov.draw_pictures(p, h, QRectF(x + 10, y + (rh - asz) / 2.0, asz, asz), tc)

        name_x, right_w = x + 52, 78
        name_w = COL_W - 52 - right_w - 6
        tf = ov.fnt(13, True)
        p.setFont(tf)
        p.setPen(tc)
        head, sub = ov.name_parts(h)
        p.drawText(QRectF(name_x, y + (5 if sub else 11), name_w, 18),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(tf).elidedText(head, Qt.TextElideMode.ElideRight, int(name_w)))
        if sub:
            nf = ov.fnt(10)
            p.setFont(nf)
            p.setPen(sc)
            p.drawText(QRectF(name_x, y + 23, name_w, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(nf).elidedText(sub, Qt.TextElideMode.ElideRight, int(name_w)))

        total = ent["total"]
        p.setFont(ov.fnt(17, True, mono=True))
        p.setPen(col)
        p.drawText(QRectF(x + COL_W - right_w - 6, y + 2, right_w, 20),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   ("%d/%d" % (ent["hit"], total)) if total else str(ent["hit"]))
        p.setFont(ov.fnt(10, False))
        p.setPen(sc)
        if total:
            small = "all hit!" if ent["hit"] == total else "%d missed" % (total - ent["hit"])
        else:
            small = "skills"
        p.drawText(QRectF(x + COL_W - right_w - 6, y + 23, right_w, 14),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, small)

    def contextMenuEvent(self, ev):
        from PyQt6.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction("Settings...", self.ov.open_settings)
        m.addAction("Hide the skill luck board", lambda: self.hide_now())
        m.exec(ev.globalPos())
