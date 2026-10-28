"""The match board: the score of a team match (draft), race by race, and the umas each team drafted.
It comes in after the results board and stays until the next race. In OBS it is its own window
("Umamusume Match (Windows)")."""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QPainterPath, QPen

from .constants import MATCH_NAME
from .frameless import fit_window
from .results_board import COL_W, FOOT_H, GUTTER, PAD, SUB_H, TOP_H, ResultsBoard

HEAD_H = 104         # a team card: name, big score, progress bar
RACE_H = 28          # one race row
PICK_H = 18          # one drafted uma
MAX_RACES = 8        # rows shown (the newest ones)
MAX_PICKS = 8


class MatchBoard(ResultsBoard):
    NAME = MATCH_NAME
    TITLE = "TEAM MATCH"
    TITLE_KEY = "match_title"
    STAY_KEY = "match_seconds"
    POS_KEY, SCALE_KEY = "match_pos", "match_scale"

    def __init__(self, ov):
        super().__init__(ov)
        self.match = None
        self.cols = 2
        self.col_w = COL_W

    # ----- data -------------------------------------------------------------------------
    def show_picks(self):
        return bool(self.ov.s.get("match_show_picks", True)) and any(t["picks"] for t in self.match.teams)

    def show_races(self):
        return bool(self.ov.s.get("match_show_races", True))

    def rows_shown(self):
        return self.match.race_rows()[-MAX_RACES:]

    def set_data(self, entries, footer):
        """entries = [{"match": the Match to draw}]. The Match is read again at every repaint, so a score
        changed by hand shows at once; call this again when the number of rows changes."""
        self.entries = list(entries)
        self.match = self.entries[0]["match"] if self.entries else None
        self.footer = footer or ""
        if self.match is None:
            return
        n_races = max(1, len(self.rows_shown())) if self.show_races() else 0
        n_picks = min(MAX_PICKS, max(len(t["picks"]) for t in self.match.teams)) if self.show_picks() else 0
        self.lw = 2 * PAD + 2 * COL_W + GUTTER
        self.lh = TOP_H + 8 + HEAD_H + (SUB_H + n_races * RACE_H if self.show_races() else 0) + 4
        if n_picks:
            self.lh += SUB_H + n_picks * PICK_H + 4
        self.lh += FOOT_H + PAD
        fit_window(self, self.lw, self.lh, self.pref_scale)
        if not self._placed:
            scr = self.screen()
            if scr is not None:
                av = scr.availableGeometry()
                self.move(av.center().x() - self.width() // 2, av.center().y() - self.height() // 2)
            self._placed = True

    def refresh(self):
        """The teams, rules or score changed: size and redraw (and keep a board that is on screen)."""
        if self.entries:
            self.set_data(self.entries, self.footer_text())
            self.update()

    def footer_text(self):
        m = self.match
        if m is None:
            return ""
        w = m.winner()
        if w is not None:
            return "%s wins!" % m.teams[w]["name"]
        return "First to %d points" % m.target

    # ----- drawing ----------------------------------------------------------------------
    def draw_columns(self, p, tc, sc, ac):
        m = self.match
        if m is None:
            return
        self.footer = self.footer_text()
        totals, win = m.totals(), m.winner()
        for c in range(2):
            x = PAD + c * (COL_W + GUTTER)
            self.draw_team(p, m.teams[c], totals[c], x, TOP_H + 8, tc, sc, ac, win == c)

        y = TOP_H + 8 + HEAD_H
        if self.show_races():
            p.setFont(self.spaced(10, True, 1.8))
            p.setPen(sc)
            p.drawText(QRectF(PAD + 8, y, 2 * COL_W + GUTTER - 16, SUB_H),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, "RACE BY RACE")
            y += SUB_H
            rows = self.rows_shown()
            if not rows:
                p.setFont(self.ov.fnt(11))
                p.setPen(sc)
                p.drawText(QRectF(PAD, y, 2 * COL_W + GUTTER, RACE_H), Qt.AlignmentFlag.AlignCenter,
                           "No race scored yet")
            for label, da, db in rows:
                self.draw_race_row(p, label, da, db, y, tc, sc, m)
                y += RACE_H
        y += 4
        if self.show_picks():
            p.setFont(self.spaced(10, True, 1.8))
            p.setPen(sc)
            p.drawText(QRectF(PAD + 8, y, 2 * COL_W + GUTTER - 16, SUB_H),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, "DRAFTED UMAS")
            y += SUB_H
            f = self.ov.fnt(12)
            p.setFont(f)
            for c in range(2):
                x = PAD + c * (COL_W + GUTTER)
                col = QColor(m.teams[c]["color"])
                for i, name in enumerate(m.teams[c]["picks"][:MAX_PICKS]):
                    p.setPen(tc)
                    p.fillRect(QRectF(x + 8, y + i * PICK_H + 5, 4, 9), col)
                    p.drawText(QRectF(x + 18, y + i * PICK_H, COL_W - 26, PICK_H),
                               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                               QFontMetrics(f).elidedText(name, Qt.TextElideMode.ElideRight, int(COL_W - 26)))

    def draw_team(self, p, team, score, x, y, tc, sc, ac, winner):
        col = QColor(team["color"])
        card = QPainterPath()
        card.addRoundedRect(QRectF(x, y, COL_W, HEAD_H - 8), 8, 8)
        bg = QColor(tc)
        bg.setAlpha(20)
        p.fillPath(card, bg)
        tint = QColor(col)
        tint.setAlpha(34)
        p.fillPath(card, tint)
        p.fillRect(QRectF(x + 10, y, COL_W - 20, 4), col)
        if winner:
            p.setPen(QPen(QColor(ac), 2))
            p.drawPath(card)

        nf = self.spaced(14, True, 1.0)
        p.setFont(nf)
        p.setPen(tc)
        name = team["name"].upper()
        p.drawText(QRectF(x + 8, y + 8, COL_W - 16, 22), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(nf).elidedText(name, Qt.TextElideMode.ElideRight, int(COL_W - 16)))
        p.setFont(self.ov.fnt(40, True, mono=True))
        p.setPen(col if not winner else QColor(ac))
        p.drawText(QRectF(x, y + 28, COL_W, 46), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   str(score))
        target = max(1, self.match.target)
        bar_w = COL_W - 32
        track = QColor(tc)
        track.setAlpha(36)
        p.fillRect(QRectF(x + 16, y + HEAD_H - 24, bar_w, 6), track)
        p.fillRect(QRectF(x + 16, y + HEAD_H - 24, bar_w * min(1.0, max(0, score) / float(target)), 6), col)

    def draw_race_row(self, p, label, da, db, y, tc, sc, m):
        rh = RACE_H - 4
        row = QPainterPath()
        row.addRoundedRect(QRectF(PAD, y, 2 * COL_W + GUTTER, rh), 6, 6)
        bg = QColor(tc)
        bg.setAlpha(18)
        p.fillPath(row, bg)
        p.setFont(self.ov.fnt(11, True))
        p.setPen(sc)
        p.drawText(QRectF(PAD, y, 2 * COL_W + GUTTER, rh), Qt.AlignmentFlag.AlignCenter, label)
        for c, d in enumerate((da, db)):
            x = PAD + c * (COL_W + GUTTER)
            col = QColor(m.teams[c]["color"])
            p.setFont(self.ov.fnt(15, True, mono=True))
            p.setPen(col if d else sc)
            text = ("+%d" % d) if d > 0 else (str(d) if d < 0 else "0")
            p.drawText(QRectF(x + 14, y, COL_W - 28, rh),
                       (Qt.AlignmentFlag.AlignLeft if c == 0 else Qt.AlignmentFlag.AlignRight)
                       | Qt.AlignmentFlag.AlignVCenter, text)

    def contextMenuEvent(self, ev):
        from PyQt6.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction("Settings...", self.ov.open_settings)
        m.addAction("Hide the match board", lambda: self.hide_now())
        m.exec(ev.globalPos())
