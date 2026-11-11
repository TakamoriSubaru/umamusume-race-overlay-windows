"""The analysis board (a little like Hakuraku): after a race it shows what really happened.
Pages: Table (numbers per uma), Speed, Stamina, Gap to the leader, Lane and a Skills timeline.
It is a normal window you can click (click an uma to follow it on every page) and, in OBS, its own
window ("Umamusume Analysis (Windows)"). It can also change pages by itself, for the stream."""

import bisect
import math
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                             QStackedWidget, QTableWidget, QTableWidgetItem, QToolTip, QVBoxLayout, QWidget)

from .constants import ANALYSIS_NAME
from .racedata import STYLE_NAMES, load_skills
from .theme import THEME, build_theme_qss

PALETTE = ("#ff6fae", "#5de6c2", "#6cb8ff", "#ffd24a", "#b56cff", "#ff9a6f", "#9be564", "#ff6b6b", "#4dd0e1",
           "#f0f0f0", "#c5e1a5", "#ffb74d", "#9fa8da", "#80cbc4", "#e6ee9c", "#ce93d8", "#90caf9", "#bcaaa4")
PHASES = ((0.0, 1 / 6.0, "Opening"), (1 / 6.0, 2 / 3.0, "Middle"), (2 / 3.0, 1.0, "Final"))
LEG_W = 224                 # width of the list of umas at the right of a chart
KINDS = {                   # page -> (title, x axis, y axis label, upside down?)
    "speed": ("Speed", "dist", "m/s", False),
    "hp": ("Stamina left", "dist", "% of the start", False),
    "gap": ("Gap to the leader", "time", "metres behind", True),
    "lane": ("Lane (relative, 0 = inside rail)", "dist", "", False),
}

_skill_cache = {}


def skill_names(ov):
    paths = ov.umdb_paths()
    key = tuple(paths)
    if key not in _skill_cache:
        _skill_cache[key] = {k: (v.get("name") or "") for k, v in load_skills(paths).items()}
    return _skill_cache[key]


def nice_ticks(lo, hi, n=5):
    if hi <= lo:
        hi = lo + 1.0
    step = (hi - lo) / float(n)
    mag = 10 ** math.floor(math.log10(step))
    for m in (1, 2, 2.5, 5, 10):
        if step <= m * mag + 1e-12:
            step = m * mag
            break
    v = math.floor(lo / step) * step
    out = []
    while v <= hi + step * 0.001:
        out.append(round(v, 6))
        v += step
    return out


def build_analysis(ov, horses=None, sim=None, entries=None, rmap=None, info=None):
    """Everything the board needs, from the race that is loaded (or from a given made-up race). None when nothing is loaded."""
    horses = ov.horses if horses is None else horses
    times = (sim or {}).get("times") if sim else ov.times
    frames = (sim or {}).get("frames") if sim else ov.frames
    extra = (sim or {}).get("extra") if sim else getattr(ov, "sim_extra", [])
    results = (sim or {}).get("results") if sim else ov.results
    log = (sim or {}).get("skill_log") if sim else ov.skill_log
    rmap = ov.result_map if rmap is None else rmap
    info = (ov.course_info if info is None else info) or {}
    if not horses or not times or not frames:
        return None
    entries = entries if entries is not None else ov.results_entries()
    names = skill_names(ov)
    total = float(info.get("distance") or 0.0)
    if total <= 0:
        total = max((row[0] for fr in frames for row in fr[:1]), default=1600.0)
    nk = len(times)
    have_extra = bool(extra) and len(extra) >= nk
    dts = [(times[k + 1] - times[k]) if k + 1 < nk else (times[k] - times[k - 1] if k else 0.0) for k in range(nk)]

    runners = []
    for ci, e in enumerate(entries):
        h = e["h"]
        j = h.frame_idx
        r = {"h": h, "j": j, "place": e["place"], "time": e["time"], "gap": e["gap"], "color": PALETTE[ci % len(PALETTE)],
             "name": h.label or h.name, "trainer": h.trainer, "style": STYLE_NAMES.get(h.style, "?"),
             "brought": list(h.skills or []), "dist": [], "t": [], "speed": [], "hp": [], "lane": [], "tempt": [], "block": []}
        for k in range(nk):
            if j >= len(frames[k]):
                continue
            d = float(frames[k][j][0])
            r["t"].append(float(times[k]))
            r["dist"].append(d)
            r["lane"].append(frames[k][j][1] / 1000.0)
            if have_extra and j < len(extra[k]):
                sp, hp, tm, bl = extra[k][j]
                r["speed"].append(sp / 100.0)
                r["hp"].append(float(hp))
                r["tempt"].append(tm)
                r["block"].append(bl)
            if d >= total:                      # this uma has finished: nothing after the line matters
                break
        stats = None
        rm = (rmap or {}).get(h.id) or {}
        rp = rm.get("raceParam") or {}
        if rp.get("rawSpeed") is not None:
            stats = {"Spd": rp.get("rawSpeed"), "Sta": rp.get("rawStamina"), "Pow": rp.get("rawPow"),
                     "Gut": rp.get("rawGuts"), "Wit": rp.get("rawWiz")}
        r["stats"] = stats
        res = results[j] if j < len(results) else None
        r["raw_time"] = float(res["finishTimeRaw"]) if res and res.get("finishTimeRaw", 0) > 0 else 0.0
        runners.append(r)

    # numbers per uma
    for r in runners:
        sp, hp = r["speed"], r["hp"]
        r["top_speed"] = max(sp) if sp else None
        r["avg_speed"] = (total / r["raw_time"]) if r["raw_time"] > 0 else None
        hp0 = hp[0] if hp and hp[0] > 0 else None
        r["hp0"] = hp0
        r["hp_left"] = (100.0 * hp[-1] / hp0) if hp0 else None
        r["empty_at"] = None
        r["tempted"] = r["blocked"] = 0.0
        if hp:
            for i, v in enumerate(hp):
                if v <= 0 and r["dist"][i] > 0:
                    r["empty_at"] = r["dist"][i]
                    break
        for i, k in enumerate(range(len(r["t"]))):
            kk = bisect.bisect_left(times, r["t"][i])
            dt = dts[min(kk, nk - 1)]
            if r["tempt"] and r["tempt"][i]:
                r["tempted"] += dt
            if r["block"] and r["block"][i] >= 0:
                r["blocked"] += dt

    # gap to the leader at every moment (the x axis is time)
    lead = [max((r["dist"][i] for r in runners if i < len(r["dist"])), default=0.0) for i in range(nk)]
    for r in runners:
        r["gapv"] = [max(0.0, lead[i] - r["dist"][i]) for i in range(len(r["dist"]))]

    # skills that really activated
    by_j = {r["j"]: n for n, r in enumerate(runners)}
    acts = []
    for horse, skill, t in log or []:
        n = by_j.get(horse)
        if n is None or t is None:
            continue
        r = runners[n]
        d = None
        if r["t"]:
            k = min(max(bisect.bisect_left(r["t"], t), 0), len(r["t"]) - 1)
            d = r["dist"][k]
        acts.append({"n": n, "id": int(skill), "name": names.get(int(skill)) or ("Skill %d" % int(skill)), "t": float(t), "dist": d})
    for n, r in enumerate(runners):
        r["acts"] = sorted((a for a in acts if a["n"] == n), key=lambda a: a["t"])
    return {"runners": runners, "total": total, "acts": acts, "has_speed": have_extra,
            "title": ov.course_lines(info)[0] if info else "Race", "info": info,
            "max_t": max((r["t"][-1] for r in runners if r["t"]), default=1.0)}


def series(data, kind, r):
    """(xs, ys) of one uma for one chart."""
    if kind == "speed":
        return r["dist"][:len(r["speed"])], r["speed"]
    if kind == "hp":
        h0 = r.get("hp0") or 1.0
        return r["dist"][:len(r["hp"])], [100.0 * v / h0 for v in r["hp"]]
    if kind == "gap":
        return r["t"][:len(r["gapv"])], r["gapv"]
    return r["dist"], r["lane"]


class ChartView(QWidget):
    """A line chart with the umas listed at the right (click = follow, Ctrl+click = hide)."""

    def __init__(self, win, kind):
        super().__init__()
        self.win, self.kind = win, kind
        self.setMouseTracking(True)
        self.hx = None
        self.setMinimumSize(520, 300)

    def plot_rect(self):
        return QRectF(64, 46, max(100, self.width() - LEG_W - 86), max(80, self.height() - 92))

    def ranges(self):
        d = self.win.data
        title, xk, ylab, inv = KINDS[self.kind]
        xmax = d["total"] if xk == "dist" else d["max_t"]
        lo, hi = None, None
        for n, r in enumerate(d["runners"]):
            if n in self.win.hidden:
                continue
            ys = series(d, self.kind, r)[1]
            if self.kind == "speed":
                ys = ys[3:]                                    # the first moments (standing start) are left out of the scale
            if ys:
                lo = min(ys) if lo is None else min(lo, min(ys))
                hi = max(ys) if hi is None else max(hi, max(ys))
        if lo is None:
            lo, hi = 0.0, 1.0
        if self.kind in ("hp", "gap"):
            lo = 0.0
        ticks = nice_ticks(lo, hi)
        return xmax, ticks[0], ticks[-1], ticks

    def value_at(self, r, x):
        xs, ys = series(self.win.data, self.kind, r)
        if not xs:
            return None
        if x > xs[-1] + 1e-9 or x < xs[0] - 1e-9:
            return None
        i = bisect.bisect_left(xs, x)
        if i == 0:
            return ys[0]
        if i >= len(xs):
            return ys[-1]
        x0, x1 = xs[i - 1], xs[i]
        return ys[i] if x1 == x0 else ys[i - 1] + (ys[i] - ys[i - 1]) * (x - x0) / (x1 - x0)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        p.fillRect(self.rect(), QColor(THEME["card"]))
        d = self.win.data
        if not d:
            return
        ov = self.win.ov
        title, xk, ylab, inv = KINDS[self.kind]
        sub, line = QColor(THEME["sub"]), QColor(THEME["line"])
        if self.kind in ("speed", "hp") and not d["has_speed"]:
            p.setPen(sub)
            p.setFont(ov.fnt(14))
            p.drawText(QRectF(0, 0, self.width(), self.height()), Qt.AlignmentFlag.AlignCenter,
                       "This race has no speed or stamina data.")
            return
        pr = self.plot_rect()
        xmax, ylo, yhi, ticks = self.ranges()
        span = (yhi - ylo) or 1.0

        def px(x):
            return pr.left() + pr.width() * (x / xmax if xmax else 0.0)

        def py(y):
            f = (y - ylo) / span
            return pr.top() + pr.height() * (f if inv else 1.0 - f)

        if xk == "dist":                                     # race phases as soft bands
            for a, b, name in PHASES:
                if name == "Middle":
                    p.fillRect(QRectF(px(a * xmax), pr.top(), px(b * xmax) - px(a * xmax), pr.height()), QColor(255, 255, 255, 9))
                p.setFont(ov.fnt(10))
                p.setPen(sub)
                p.drawText(QRectF(px(a * xmax), pr.top() - 18, px(b * xmax) - px(a * xmax), 16), Qt.AlignmentFlag.AlignCenter, name)
        p.setFont(ov.fnt(10, mono=True))
        for t in ticks:                                       # y grid
            y = py(t)
            p.setPen(QPen(line, 1))
            p.drawLine(QPointF(pr.left(), y), QPointF(pr.right(), y))
            p.setPen(sub)
            p.drawText(QRectF(0, y - 8, pr.left() - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "%g" % t)
        for t in nice_ticks(0, xmax, 8):                      # x labels
            if t > xmax + 1e-6:
                continue
            x = px(t)
            p.setPen(QPen(line, 1))
            p.drawLine(QPointF(x, pr.bottom()), QPointF(x, pr.bottom() + 4))
            p.setPen(sub)
            p.drawText(QRectF(x - 30, pr.bottom() + 5, 60, 16), Qt.AlignmentFlag.AlignCenter, "%g" % t)
        p.setPen(sub)
        p.setFont(ov.fnt(11, True))
        p.drawText(QRectF(pr.left(), 4, pr.width(), 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   "%s%s" % (title, ("  (%s)" % ylab) if ylab else ""))
        p.setFont(ov.fnt(10))
        p.drawText(QRectF(pr.left(), pr.bottom() + 20, pr.width(), 16), Qt.AlignmentFlag.AlignCenter,
                   "Distance (m)" if xk == "dist" else "Race time (s)")
        if self.kind == "hp":                                 # empty tank
            p.setPen(QPen(QColor("#ff6b81"), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(pr.left(), py(0)), QPointF(pr.right(), py(0)))

        hl = self.win.hl
        p.save()
        p.setClipRect(pr.adjusted(-2, -3, 3, 3))
        order = [n for n in range(len(d["runners"])) if n not in self.win.hidden and n != hl]
        if hl is not None and hl not in self.win.hidden:
            order.append(hl)                                  # the followed uma is drawn last (on top)
        for n in order:
            r = d["runners"][n]
            xs, ys = series(d, self.kind, r)
            if len(xs) < 2:
                continue
            col = QColor(r["color"])
            w = 1.5
            if hl is not None:
                w, col = (3.0, col) if n == hl else (1.2, QColor(col.red(), col.green(), col.blue(), 70))
            path = QPainterPath(QPointF(px(xs[0]), py(ys[0])))
            for x, y in zip(xs[1:], ys[1:]):
                path.lineTo(px(x), py(y))
            p.strokePath(path, QPen(col, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.restore()
        if hl is not None and hl < len(d["runners"]):         # little marks where the followed uma used a skill
            col = QColor(d["runners"][hl]["color"])
            for a in d["runners"][hl]["acts"]:
                x = a["dist"] if xk == "dist" else a["t"]
                if x is None or x > xmax:
                    continue
                tri = QPainterPath(QPointF(px(x), pr.bottom() - 1))
                tri.lineTo(px(x) - 4, pr.bottom() + 6)
                tri.lineTo(px(x) + 4, pr.bottom() + 6)
                tri.closeSubpath()
                p.fillPath(tri, col)

        if self.hx is not None and pr.left() <= self.hx <= pr.right():
            p.setPen(QPen(QColor(255, 255, 255, 110), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(self.hx, pr.top()), QPointF(self.hx, pr.bottom()))
        self.draw_legend(p, pr, xmax, xk)

    def draw_legend(self, p, pr, xmax, xk):
        d, ov = self.win.data, self.win.ov
        x0 = self.width() - LEG_W + 6
        cur = None
        if self.hx is not None and pr.left() <= self.hx <= pr.right():
            cur = (self.hx - pr.left()) / pr.width() * xmax
        p.setFont(ov.fnt(10, True))
        p.setPen(QColor(THEME["sub"]))
        head = ("at %.0f m" % cur if xk == "dist" else "at %.1f s" % cur) if cur is not None else "end of the race"
        p.drawText(QRectF(x0, 6, LEG_W - 10, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, head)
        rows = d["runners"]
        rh = min(24.0, max(16.0, (self.height() - 40) / float(max(1, len(rows)))))
        self.leg_rows = []
        for n, r in enumerate(rows):
            y = 30 + n * rh
            rect = QRectF(x0, y, LEG_W - 10, rh - 2)
            self.leg_rows.append((rect, n))
            hidden = n in self.win.hidden
            if n == self.win.hl:
                p.fillRect(rect, QColor(255, 255, 255, 28))
            col = QColor(r["color"])
            col.setAlphaF(0.25 if hidden else 1.0)
            p.fillRect(QRectF(x0 + 4, y + rh / 2.0 - 4, 14, 5), col)
            p.setFont(ov.fnt(11, n == self.win.hl))
            p.setPen(QColor(THEME["sub"] if hidden else THEME["text"]))
            fm = QFontMetrics(p.font())
            p.drawText(QRectF(x0 + 24, y, LEG_W - 100, rh - 2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText("%s. %s" % (r["place"], r["name"]), Qt.TextElideMode.ElideRight, LEG_W - 100))
            if not hidden:
                if cur is not None:
                    v = self.value_at(r, cur)
                else:
                    xs, ys = series(d, self.kind, r)
                    v = ys[-1] if ys else None
                p.setFont(ov.fnt(11, mono=True))
                p.drawText(QRectF(x0, y, LEG_W - 12, rh - 2), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           "" if v is None else ("%.1f" % v))

    def mouseMoveEvent(self, ev):
        self.hx = ev.position().x()
        self.update()

    def leaveEvent(self, _ev):
        self.hx = None
        self.update()

    def mousePressEvent(self, ev):
        self.win.stop_auto()
        for rect, n in getattr(self, "leg_rows", []):
            if rect.contains(ev.position()):
                if ev.button() == Qt.MouseButton.RightButton or ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    self.win.toggle_hidden(n)
                else:
                    self.win.set_hl(None if self.win.hl == n else n)
                return


class SkillsView(QWidget):
    """One row per uma, one mark for every skill that really activated, placed on the track."""
    LEFT = 200
    RIGHT = 70

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setMouseTracking(True)
        self.setMinimumSize(520, 300)

    def geo(self):
        d = self.win.data
        n = max(1, len(d["runners"])) if d else 1
        top = 34.0
        rh = min(34.0, (self.height() - top - 28) / float(n))
        return top, rh, self.LEFT, self.width() - self.RIGHT

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        p.fillRect(self.rect(), QColor(THEME["card"]))
        d = self.win.data
        if not d:
            return
        ov = self.win.ov
        top, rh, x0, x1 = self.geo()
        sub = QColor(THEME["sub"])
        total = d["total"]

        def px(x):
            return x0 + (x1 - x0) * x / total

        for a, b, name in PHASES:
            if name == "Middle":
                p.fillRect(QRectF(px(a * total), top, px(b * total) - px(a * total), rh * len(d["runners"])), QColor(255, 255, 255, 9))
            p.setFont(ov.fnt(10))
            p.setPen(sub)
            p.drawText(QRectF(px(a * total), 6, px(b * total) - px(a * total), 18), Qt.AlignmentFlag.AlignCenter, name)
        for n, r in enumerate(d["runners"]):
            y = top + n * rh
            if n == self.win.hl:
                p.fillRect(QRectF(0, y, self.width(), rh), QColor(255, 255, 255, 24))
            col = QColor(r["color"])
            p.setFont(ov.fnt(11, n == self.win.hl))
            p.setPen(QColor(THEME["text"]))
            p.drawText(QRectF(10, y, self.LEFT - 16, rh), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(p.font()).elidedText("%s. %s" % (r["place"], r["name"]), Qt.TextElideMode.ElideRight, self.LEFT - 16))
            p.setPen(QPen(QColor(THEME["line"]), 1))
            p.drawLine(QPointF(x0, y + rh / 2), QPointF(x1, y + rh / 2))
            for a in r["acts"]:
                if a["dist"] is None:
                    continue
                x = px(min(total, a["dist"]))
                m = QPainterPath()
                m.addRoundedRect(QRectF(x - 3, y + rh * 0.18, 6, rh * 0.64), 2, 2)
                p.fillPath(m, col)
            p.setPen(sub)
            p.setFont(ov.fnt(10, mono=True))
            p.drawText(QRectF(x1 + 8, y, self.RIGHT - 10, rh), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       "%d / %d" % (len(r["acts"]), len(r["brought"])) if r["brought"] else "%d" % len(r["acts"]))
        p.setPen(sub)
        p.setFont(ov.fnt(10))
        base = top + rh * len(d["runners"])
        for t in nice_ticks(0, total, 8):
            if t <= total + 1e-6:
                p.drawText(QRectF(px(t) - 30, base + 4, 60, 16), Qt.AlignmentFlag.AlignCenter, "%g" % t)
        p.drawText(QRectF(x0, base + 18, x1 - x0, 14), Qt.AlignmentFlag.AlignCenter, "Distance (m)    -    activated / brought")

    def row_at(self, pos):
        top, rh, x0, x1 = self.geo()
        n = int((pos.y() - top) // rh) if rh else -1
        d = self.win.data
        return n if d and 0 <= n < len(d["runners"]) else None

    def mouseMoveEvent(self, ev):
        d = self.win.data
        n = self.row_at(ev.position())
        if not d or n is None:
            QToolTip.hideText()
            return
        top, rh, x0, x1 = self.geo()
        best = None
        for a in d["runners"][n]["acts"]:
            if a["dist"] is None:
                continue
            dx = abs(x0 + (x1 - x0) * min(d["total"], a["dist"]) / d["total"] - ev.position().x())
            if dx <= 6 and (best is None or dx < best[0]):
                best = (dx, a)
        if best:
            a = best[1]
            QToolTip.showText(ev.globalPosition().toPoint(), "%s\n%.1f s  -  %.0f m" % (a["name"], a["t"], a["dist"]), self)
        else:
            QToolTip.hideText()

    def mousePressEvent(self, ev):
        self.win.stop_auto()
        n = self.row_at(ev.position())
        if n is not None:
            self.win.set_hl(None if self.win.hl == n else n)


class NumItem(QTableWidgetItem):
    def __init__(self, text, key):
        super().__init__(text)
        self.key = key
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other):
        a, b = self.key, getattr(other, "key", None)
        if a is None or b is None:
            return (a is not None) and (b is None)
        return a < b


class TableView(QTableWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(False)
        self.verticalHeader().hide()
        self.setShowGrid(False)
        self.cellClicked.connect(self.on_click)

    def fill(self, d):
        self.setSortingEnabled(False)
        stats = d and any(r["stats"] for r in d["runners"])
        cols = ["#", "Uma", "Player", "Style", "Time", "Gap", "Top m/s", "Avg m/s", "Stamina", "Dry at",
                "Tempted", "Blocked", "Skills"] + (["Spd", "Sta", "Pow", "Gut", "Wit"] if stats else [])
        self.setColumnCount(len(cols))
        self.setHorizontalHeaderLabels(cols)
        rows = d["runners"] if d else []
        self.setRowCount(len(rows))
        for i, r in enumerate(rows):
            def num(v, fmt, nd=None):
                return NumItem("–" if v is None else fmt % v, v)
            cells = [NumItem(str(r["place"]), r["place"]), QTableWidgetItem(r["name"]), QTableWidgetItem(r["trainer"]),
                     QTableWidgetItem(r["style"]), NumItem(r["time"], r["raw_time"] or None), NumItem(r["gap"], r["raw_time"] or None),
                     num(r["top_speed"], "%.2f"), num(r["avg_speed"], "%.2f"),
                     num(r["hp_left"], "%.0f%%"), NumItem("no" if r["empty_at"] is None and r["hp0"] else ("–" if r["hp0"] is None else "%.0f m" % r["empty_at"]),
                                                          (1e9 if r["empty_at"] is None else r["empty_at"]) if r["hp0"] else None),
                     NumItem("%.1f s" % r["tempted"] if d["has_speed"] else "–", r["tempted"] if d["has_speed"] else None),
                     NumItem("%.1f s" % r["blocked"] if d["has_speed"] else "–", r["blocked"] if d["has_speed"] else None),
                     NumItem("%d / %d" % (len(r["acts"]), len(r["brought"])) if r["brought"] else str(len(r["acts"])), len(r["acts"]))]
            if stats:
                st = r["stats"] or {}
                cells += [NumItem("–" if st.get(k) is None else str(st.get(k)), st.get(k)) for k in ("Spd", "Sta", "Pow", "Gut", "Wit")]
            for c, it in enumerate(cells):
                if c in (1, 2, 3):
                    it.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                it.setData(Qt.ItemDataRole.UserRole, i)
                self.setItem(i, c, it)
            self.item(i, 1).setForeground(QColor(r["color"]))
            self.item(i, 1).setFont(QFont(self.font().family(), self.font().pointSize(), QFont.Weight.Bold))
        self.setSortingEnabled(True)
        self.sortItems(0, Qt.SortOrder.AscendingOrder)
        hh = self.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setStretchLastSection(False)

    def on_click(self, row, _col):
        self.win.stop_auto()
        it = self.item(row, 0)
        if it is not None:
            n = it.data(Qt.ItemDataRole.UserRole)
            self.win.set_hl(None if self.win.hl == n else n)

    def mark(self, hl):
        for row in range(self.rowCount()):
            it = self.item(row, 0)
            if it is not None and hl is not None and it.data(Qt.ItemDataRole.UserRole) == hl:
                self.selectRow(row)
                return
        self.clearSelection()


class AnalysisWindow(QWidget):
    PAGES = (("table", "Table"), ("speed", "Speed"), ("hp", "Stamina"), ("gap", "Gap"), ("lane", "Lane"), ("skills", "Skills"))
    AUTO = ("table", "speed", "hp", "gap", "skills")

    def __init__(self, ov):
        super().__init__()
        self.ov = ov
        self.data = None
        self.hl = None                  # the uma that is followed on every page
        self.hidden = set()
        self.pinned = False             # opened by hand: stays until you close it
        self.pending_at = None
        self.deadline = None
        self._count = 0
        self.setWindowTitle(ANALYSIS_NAME)
        self.setStyleSheet(build_theme_qss() + "AnalysisWindow{background:%s;} QLabel{color:%s;background:transparent;}"
                           % (THEME["bg"], THEME["text"]))
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.apply_flags()

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)
        top = QHBoxLayout()
        self.lbl_title = QLabel("Analysis")
        self.lbl_title.setStyleSheet("font-size:16px;font-weight:800;")
        top.addWidget(self.lbl_title, 1)
        self.cb_auto = QCheckBox("Change page by itself")
        self.cb_auto.setChecked(bool(ov.s.get("analysis_auto", True)))
        self.cb_auto.toggled.connect(self.on_auto)
        top.addWidget(self.cb_auto)
        v.addLayout(top)
        bar = QHBoxLayout()
        self.group = QButtonGroup(self)
        self.btns = {}
        for key, label in self.PAGES:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setMinimumWidth(10)
            b.clicked.connect(lambda _c=False, k=key: self.on_page_click(k))
            self.group.addButton(b)
            bar.addWidget(b)
            self.btns[key] = b
        bar.addStretch(1)
        v.addLayout(bar)
        self.stack = QStackedWidget()
        self.views = {"table": TableView(self), "skills": SkillsView(self)}
        for k in KINDS:
            self.views[k] = ChartView(self, k)
        for key, _l in self.PAGES:
            self.stack.addWidget(self.views[key])
        v.addWidget(self.stack, 1)
        self.lbl_hint = QLabel("Click an uma to follow her on every page. Ctrl+click or right-click on a chart: hide her.")
        self.lbl_hint.setStyleSheet("color:%s;" % THEME["sub"])
        v.addWidget(self.lbl_hint)
        self.page = ov.s.get("analysis_page", "table")
        if self.page not in self.views:
            self.page = "table"
        self.show_page(self.page)

        g = ov.cfg.get("analysis_geo")
        self.resize(1200, 660)
        if g and len(g) == 4 and not ov.args.reset_window:
            self.setGeometry(int(g[0]), int(g[1]), int(g[2]), int(g[3]))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_second)
        self.timer.start(1000)

    # ----- window ---------------------------------------------------------------------
    def apply_flags(self):
        flags = Qt.WindowType.Window
        if self.ov.s.get("on_top", True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        was = self.isVisible()
        self.setWindowFlags(flags)
        if was:
            self.show()

    def remember(self):
        self.ov.cfg["analysis_geo"] = [self.x(), self.y(), self.width(), self.height()]

    def hideEvent(self, ev):
        super().hideEvent(ev)
        self.pinned = False
        self.remember()
        self.ov.refresh_tray()

    def closeEvent(self, ev):
        if not self.ov.quitting:
            self.hide()
            ev.ignore()
            return
        ev.accept()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.hide()

    # ----- data and pages ---------------------------------------------------------------
    def set_data(self, data):
        self.data = data
        self.hl = None
        self.hidden = set()
        self.lbl_title.setText(("Analysis  -  %s" % data["title"]) if data else "Analysis  -  no race yet")
        self.views["table"].fill(data)
        self.refresh()

    def refresh(self):
        self.views["table"].mark(self.hl)
        for v in self.views.values():
            v.update()

    def set_hl(self, n):
        self.hl = n
        self.refresh()

    def toggle_hidden(self, n):
        if n in self.hidden:
            self.hidden.discard(n)
        else:
            self.hidden.add(n)
        self.refresh()

    def show_page(self, key):
        self.page = key
        self.btns[key].setChecked(True)
        self.stack.setCurrentWidget(self.views[key])
        self.views[key].update()

    def on_page_click(self, key):
        self.stop_auto()
        self.show_page(key)
        self.ov.set_setting("analysis_page", key)

    def stop_auto(self):
        if self.cb_auto.isChecked():
            self.cb_auto.setChecked(False)

    def on_auto(self, on):
        self.ov.set_setting("analysis_auto", bool(on))
        self._count = 0

    def on_second(self):
        if not self.isVisible() or not self.cb_auto.isChecked() or not self.data:
            return
        self._count += 1
        if self._count >= max(2, int(float(self.ov.s.get("analysis_page_seconds", 8.0)))):
            self._count = 0
            pages = [k for k in self.AUTO if self.data["has_speed"] or k not in ("speed", "hp")]
            i = pages.index(self.page) if self.page in pages else -1
            self.show_page(pages[(i + 1) % len(pages)])

    # ----- when the window comes and goes (same rules as the other boards) ---------------------
    def stay(self):
        return float(self.ov.s.get("analysis_seconds", 30.0))

    def hold_forever(self):
        return bool(self.ov.args.hold) or self.stay() <= 0

    def present(self, delay):
        self.pending_at = time.monotonic() + max(0.0, delay)
        self.deadline = None

    def dismiss(self):
        """A new race starts."""
        self.pending_at = None
        self.deadline = None
        if not self.pinned and self.isVisible():
            self.hide()

    def tick(self, now, _dt):
        if self.pending_at is not None and now >= self.pending_at:
            self.pending_at = None
            data = build_analysis(self.ov)
            if data:
                self.set_data(data)
                if self.ov.s.get("analysis_auto", True):
                    self.show_page(self.AUTO[0])
                self._count = 0
                if not self.isVisible():
                    self.show()
                self.deadline = None if self.hold_forever() else now + self.stay()
        if self.deadline is not None and now >= self.deadline and not self.pinned:
            self.deadline = None
            self.hide()

    def open_now(self):
        """'Open the analysis board': the race that was run last (or a made-up one, to see what it looks like)."""
        data = build_analysis(self.ov)
        if data is None:
            data = self.ov.sample_analysis()
        self.pinned = True
        self.pending_at = None
        self.deadline = None
        self.set_data(data)
        self.show()
        self.raise_()
        self.activateWindow()
        self.pinned = True
        self.ov.refresh_tray()
