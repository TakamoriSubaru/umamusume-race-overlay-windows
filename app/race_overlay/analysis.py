"""The analysis board (a little like Hakuraku): after a race it shows what really happened.
Pages: Table (numbers per uma), Speed, Stamina, Gap to the leader, Lane and a Skills timeline.
It is a normal window you can click (click an uma to follow it on every page) and, in OBS, its own
window ("Umamusume Analysis (Windows)"). It can also change pages by itself, for the stream."""

import bisect
import math
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QAbstractItemView, QButtonGroup, QHBoxLayout, QHeaderView, QLabel, QPushButton, QSplitter, QStackedWidget,
                             QStyledItemDelegate, QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

from .constants import ANALYSIS_NAME
from . import skillcheck
from .racedata import STYLE_NAMES, load_skills
from .replay import ReplayPage
from .theme import THEME, build_theme_qss

PALETTE = ("#ff6fae", "#5de6c2", "#6cb8ff", "#ffd24a", "#b56cff", "#ff9a6f", "#9be564", "#ff6b6b", "#4dd0e1",
           "#f0f0f0", "#c5e1a5", "#ffb74d", "#9fa8da", "#80cbc4", "#e6ee9c", "#ce93d8", "#90caf9", "#bcaaa4")
PHASES = ((0.0, 1 / 6.0, "Opening"), (1 / 6.0, 2 / 3.0, "Middle"), (2 / 3.0, 1.0, "Final"))
LEG_W = 224                 # width of the list of umas at the right of a chart
KINDS = {                   # page -> (title, x axis, y axis label, upside down?)
    "speed": ("Speed", "dist", "m/s", False),
    "hp": ("Stamina left", "dist", "% of the start", False),
    "gap": ("Gap to the leader", "time", "metres behind", True),
}

_skill_cache = {}


def skill_records(ov):
    paths = ov.umdb_paths()
    key = tuple(paths)
    if key not in _skill_cache:
        _skill_cache[key] = load_skills(paths)
    return _skill_cache[key]


def skill_names(ov):
    return {k: (v.get("name") or "") for k, v in skill_records(ov).items()}


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
    events = (sim or {}).get("events") if sim else getattr(ov, "sim_events", [])
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
             "brought": list(h.skills or []), "dist": [], "t": [], "speed": [], "hp": [], "lane": [], "lane_raw": [], "tempt": [], "block": []}
        for k in range(nk):
            if j >= len(frames[k]):
                continue
            d = float(frames[k][j][0])
            r["t"].append(float(times[k]))
            r["dist"].append(d)
            r["lane"].append(frames[k][j][1] / 1000.0)
            r["lane_raw"].append(float(frames[k][j][1]))
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
                     "Gut": rp.get("rawGuts"), "Wit": rp.get("rawWiz"), "WitBase": rp.get("baseWiz")}
        r["stats"] = stats
        r["popularity"] = rm.get("popularity")
        res = results[j] if j < len(results) else None
        r["raw_time"] = float(res["finishTimeRaw"]) if res and res.get("finishTimeRaw", 0) > 0 else 0.0
        r["start_delay"] = res.get("startDelay") if res else None
        r["last_spurt_at"] = res.get("lastSpurtStart") if res else None
        r["mood"] = rp.get("motivation") or ""
        r["duel_at"] = next((e[0] for e in (events or []) if e[1] == 5 and e[2] and e[2][0] == j), None)
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
    # every uma on the same distances (every 10 m), and how far above or below the field average she was
    grid = [float(g) for g in range(0, int(total) + 1, 10)]
    if grid[-1] < total:
        grid.append(total)
    for key in ("speed", "hp"):
        cols = []
        for r in runners:
            xs = r["dist"][:len(r[key])]
            ys = r[key] if key == "speed" else [100.0 * v / (r.get("hp0") or 1.0) for v in r[key]]
            cols.append([None if (not xs or g > xs[-1] + 1e-9) else skillcheck._lin(xs, ys, g) for g in grid])
        means = []
        for i in range(len(grid)):
            vals = [c[i] for c in cols if c[i] is not None]
            means.append(sum(vals) / len(vals) if len(vals) >= 2 else None)
        for r, c in zip(runners, cols):
            r[key + "_rel"] = [None if (v is None or means[i] is None) else v - means[i] for i, v in enumerate(c)]
    out = {"runners": runners, "total": total, "acts": acts, "has_speed": have_extra, "grid": grid,
           "times": [float(t) for t in times],
           "title": ov.course_lines(info)[0] if info else "Race", "info": info,
           "max_t": max((r["t"][-1] for r in runners if r["t"]), default=1.0)}
    try:
        skillcheck.analyse(out, skill_records(ov), info)
    except Exception as e:                                 # the reasons are a bonus: never break the board
        print("skill check:", e)
        for r in runners:
            r.setdefault("hit", []), r.setdefault("miss", [])
            r.setdefault("wit_chance", None)
    return out


def series(data, kind, r, compare=False):
    """(xs, ys) of one uma for one chart. compare: how far above (+) or below (-) the field average she was."""
    if compare and kind in ("speed", "hp"):
        pts = [(g, v) for g, v in zip(data["grid"], r[kind + "_rel"]) if v is not None]
        return [a for a, _b in pts], [b for _a, b in pts]
    if kind == "speed":
        return r["dist"][:len(r["speed"])], r["speed"]
    if kind == "hp":
        h0 = r.get("hp0") or 1.0
        return r["dist"][:len(r["hp"])], [100.0 * v / h0 for v in r["hp"]]
    if kind == "gap":
        return r["t"][:len(r["gapv"])], r["gapv"]
    return r["dist"], r["lane"]


def uma_face(ov, p, r, rect):
    """The round picture of the uma (her face), or her first letter while the picture is not there yet."""
    h = r["h"]
    try:
        ov.draw_circle_picture(p, rect, ov.uma_pixmap(h), (h.name[:1] or "?"), QColor("#ffffff"))
    except Exception:
        p.setPen(QColor(THEME["text"]))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, h.name[:1] or "?")


def fmt_value(kind, v, compare=False):
    if v is None:
        return ""
    if compare and kind in ("speed", "hp"):
        return {"speed": "%+.2f", "hp": "%+.0f%%"}[kind] % v
    return {"speed": "%.1f m/s", "hp": "%.0f%%", "gap": "%.1f m"}[kind] % v


class UmaList(QWidget):
    """The umas with their pictures, finish order, at the left. Click = follow her, right-click = hide her.
    While the mouse is over a chart the numbers show her value at that spot."""
    W = 280

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setFixedWidth(self.W)
        self.setMinimumHeight(300)

    def geo(self):
        n = max(1, len(self.win.data["runners"])) if self.win.data else 1
        return min(62.0, max(34.0, (self.height() - 4) / float(n)))

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        d, ov = self.win.data, self.win.ov
        if not d:
            return
        rh = self.geo()
        self.rows = []
        for n, r in enumerate(d["runners"]):
            rect = QRectF(0, n * rh, self.W, rh - 4)
            self.rows.append((rect, n))
            hidden, sel = n in self.win.hidden, n == self.win.hl
            path = QPainterPath()
            path.addRoundedRect(rect, 10, 10)
            p.fillPath(path, QColor(255, 111, 174, 46) if sel else QColor(THEME["card"]))
            if sel:
                p.setPen(QPen(QColor(THEME["pink"]), 1.5))
                p.drawPath(path)
            p.setOpacity(0.35 if hidden else 1.0)
            strip = QPainterPath()
            strip.addRoundedRect(QRectF(rect.left() + 5, rect.top() + 8, 4, rect.height() - 16), 2, 2)
            p.fillPath(strip, QColor(r["color"]))
            pic = rect.height() - 12
            uma_face(ov, p, r, QRectF(rect.left() + 16, rect.top() + 6, pic, pic))
            tx = rect.left() + 16 + pic + 10
            tw = rect.right() - tx - 78
            p.setFont(ov.fnt(13, True))
            p.setPen(QColor(THEME["text"]))
            fm = QFontMetrics(p.font())
            top = rect.top() + (6 if rh >= 44 else 2)
            p.drawText(QRectF(tx, top, tw, rect.height() / 2.0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText("%s. %s" % (r["place"], r["name"]), Qt.TextElideMode.ElideRight, int(tw)))
            if rh >= 44:
                p.setFont(ov.fnt(10))
                p.setPen(QColor(THEME["sub"]))
                p.drawText(QRectF(tx, rect.top() + rect.height() / 2.0 - 1, tw, rect.height() / 2.0 - 4),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           QFontMetrics(p.font()).elidedText(r["trainer"] or r["style"], Qt.TextElideMode.ElideRight, int(tw)))
            hv = self.win.hover
            p.setFont(ov.fnt(13, True, mono=True))
            p.setPen(QColor(THEME["yellow"] if hv is not None else THEME["text"]))
            text = fmt_value(self.win.page, hv.get(n), self.win.compare) if hv is not None else r["time"]
            p.drawText(QRectF(rect.right() - 80, rect.top() + 2, 72, rect.height() / 2.0 + 6),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)
            if hv is None and rh >= 44:
                p.setFont(ov.fnt(10, mono=True))
                p.setPen(QColor(THEME["sub"]))
                p.drawText(QRectF(rect.right() - 80, rect.top() + rect.height() / 2.0 + 2, 72, rect.height() / 2.0 - 6),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, r["gap"])
            p.setOpacity(1.0)

    def mousePressEvent(self, ev):
        self.win.stop_auto()
        for rect, n in getattr(self, "rows", []):
            if rect.contains(ev.position()):
                if ev.button() == Qt.MouseButton.RightButton or ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    self.win.toggle_hidden(n)
                else:
                    self.win.set_hl(None if self.win.hl == n else n)
                return


class ChartView(QWidget):
    """A line chart. Move the mouse over it: the list at the left shows every uma's number at that spot."""

    def __init__(self, win, kind):
        super().__init__()
        self.win, self.kind = win, kind
        self.setMouseTracking(True)
        self.hx = None
        self.setMinimumSize(420, 300)

    def plot_rect(self):
        return QRectF(56, 50, max(100, self.width() - 80), max(80, self.height() - 96))

    def ranges(self):
        d = self.win.data
        title, xk, ylab, inv = KINDS[self.kind]
        xmax = d["total"] if xk == "dist" else d["max_t"]
        lo, hi = None, None
        for n, r in enumerate(d["runners"]):
            if n in self.win.hidden:
                continue
            ys = series(d, self.kind, r, self.win.compare_on(self.kind))[1]
            if self.kind == "speed" and not self.win.compare_on(self.kind):
                ys = ys[3:]                                    # the standing start is left out of the scale
            if ys:
                lo = min(ys) if lo is None else min(lo, min(ys))
                hi = max(ys) if hi is None else max(hi, max(ys))
        if lo is None:
            lo, hi = 0.0, 1.0
        if self.win.compare_on(self.kind):                     # centred on the field average
            m = max(abs(lo), abs(hi)) or 1.0
            lo, hi = -m, m
        elif self.kind in ("hp", "gap"):
            lo = 0.0
        ticks = nice_ticks(lo, hi)
        return xmax, ticks[0], ticks[-1], ticks

    def value_at(self, r, x):
        xs, ys = series(self.win.data, self.kind, r, self.win.compare_on(self.kind))
        if not xs or x > xs[-1] + 1e-9 or x < xs[0] - 1e-9:
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
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 12, 12)
        p.fillPath(path, QColor(THEME["card"]))
        d = self.win.data
        if not d:
            return
        ov = self.win.ov
        title, xk, ylab, inv = KINDS[self.kind]
        sub, line = QColor(THEME["sub"]), QColor(THEME["line"])
        if self.kind in ("speed", "hp") and not d["has_speed"]:
            p.setPen(sub)
            p.setFont(ov.fnt(14))
            p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, "This race has no speed or stamina data.")
            return
        pr = self.plot_rect()
        xmax, ylo, yhi, ticks = self.ranges()
        span = (yhi - ylo) or 1.0

        def px(x):
            return pr.left() + pr.width() * (x / xmax if xmax else 0.0)

        def py(y):
            f = (y - ylo) / span
            return pr.top() + pr.height() * (f if inv else 1.0 - f)

        p.setPen(QColor(THEME["text"]))
        p.setFont(ov.fnt(15, True))
        cmp_on = self.win.compare_on(self.kind)
        if cmp_on:
            head = {"speed": "Speed compared to the field   (m/s: above 0 = faster than the others)",
                    "hp": "Stamina compared to the field   (%: above 0 = more stamina left than the others)"}[self.kind]
        else:
            head = "%s%s" % (title, ("   (%s)" % ylab) if ylab else "")
        p.drawText(QRectF(18, 8, pr.width() - 120, 24), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, head)
        if xk == "dist":                                     # race parts as soft bands
            for a, b, name in PHASES:
                if name == "Middle":
                    p.fillRect(QRectF(px(a * xmax), pr.top(), px(b * xmax) - px(a * xmax), pr.height()), QColor(255, 255, 255, 9))
                p.setFont(ov.fnt(10))
                p.setPen(sub)
                p.drawText(QRectF(px(a * xmax), pr.top() - 18, px(b * xmax) - px(a * xmax), 16), Qt.AlignmentFlag.AlignCenter, name)
        p.setFont(ov.fnt(10, mono=True))
        for t in ticks:
            y = py(t)
            p.setPen(QPen(line, 1))
            p.drawLine(QPointF(pr.left(), y), QPointF(pr.right(), y))
            p.setPen(sub)
            p.drawText(QRectF(0, y - 8, pr.left() - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "%g" % t)
        for t in nice_ticks(0, xmax, 8):
            if t > xmax + 1e-6:
                continue
            p.setPen(sub)
            p.drawText(QRectF(px(t) - 30, pr.bottom() + 6, 60, 16), Qt.AlignmentFlag.AlignCenter, "%g" % t)
        p.drawText(QRectF(pr.left(), pr.bottom() + 22, pr.width(), 16), Qt.AlignmentFlag.AlignCenter,
                   "Metres" if xk == "dist" else "Seconds")
        if cmp_on:
            p.setPen(QPen(QColor(255, 255, 255, 150), 1.5))
            p.drawLine(QPointF(pr.left(), py(0)), QPointF(pr.right(), py(0)))
        elif self.kind == "hp":
            p.setPen(QPen(QColor("#ff6b81"), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(pr.left(), py(0)), QPointF(pr.right(), py(0)))

        hl = self.win.hl
        p.save()
        p.setClipRect(pr.adjusted(-2, -3, 3, 3))
        order = [n for n in range(len(d["runners"])) if n not in self.win.hidden and n != hl]
        if hl is not None and hl not in self.win.hidden:
            order.append(hl)
        for n in order:
            r = d["runners"][n]
            xs, ys = series(d, self.kind, r, self.win.compare_on(self.kind))
            if len(xs) < 2:
                continue
            col, w = QColor(r["color"]), 2.0
            if hl is not None:
                w, col = (3.6, col) if n == hl else (1.3, QColor(col.red(), col.green(), col.blue(), 60))
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
            cur = (self.hx - pr.left()) / pr.width() * xmax
            p.setPen(QColor(THEME["yellow"]))
            p.setFont(ov.fnt(11, True))
            p.drawText(QRectF(pr.right() - 160, 8, 160, 24), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       ("%.0f m" % cur) if xk == "dist" else ("%.1f s" % cur))

    def mouseMoveEvent(self, ev):
        self.hx = ev.position().x()
        pr = self.plot_rect()
        d = self.win.data
        if d and pr.left() <= self.hx <= pr.right():
            xmax = self.ranges()[0]
            cur = (self.hx - pr.left()) / pr.width() * xmax
            self.win.set_hover({n: self.value_at(r, cur) for n, r in enumerate(d["runners"])})
        else:
            self.win.set_hover(None)
        self.update()

    def leaveEvent(self, _ev):
        self.hx = None
        self.win.set_hover(None)
        self.update()

    def mousePressEvent(self, _ev):
        self.win.stop_auto()

STYLE_COL = {"Front": "#4aa3ff", "Pace": "#59d98e", "Late": "#ffd24a", "End": "#ff9f43"}
MOODS = {"Max": ("↑", "#ff6fae"), "High": ("↗", "#ff9a6f"), "Normal": ("→", "#ffd24a"),
         "Low": ("↘", "#6cb8ff"), "Min": ("↓", "#b56cff")}
PLACE_COL = {1: "#ffd24a", 2: "#e6ebf5", 3: "#ff9a6f"}
COLUMNS = ("FINISH", "NO.", "UMA", "TIME", "STYLE / MOOD", "START DELAY", "LAST SPURT", "HP RESULT", "DUEL", "PACE", "STATS")


def fmt_clock(sec):
    if not sec or sec <= 0:
        return "-"
    return "%d:%07.4f" % (int(sec // 60), sec - 60 * int(sec // 60))


class CellDelegate(QStyledItemDelegate):
    """Draws the cells of the table like the Hakuraku results table: big numbers, two lines, round badges."""

    def __init__(self, win, table):
        super().__init__(table)
        self.win = win

    def paint(self, p, option, index):
        data = index.data(Qt.ItemDataRole.UserRole + 1)
        if not data:
            return super().paint(p, option, index)
        ov, rect = self.win.ov, QRectF(option.rect)
        p.save()
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        n = index.data(Qt.ItemDataRole.UserRole)
        if n == self.win.hl:
            p.fillRect(rect, QColor(255, 111, 174, 40))
        p.setPen(QPen(QColor(255, 255, 255, 14), 1))
        p.drawLine(rect.bottomLeft(), rect.bottomRight())
        k = data["k"]
        text, sub = QColor(THEME["text"]), QColor(THEME["sub"])
        mid = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        if k == "num":
            p.setFont(ov.fnt(17, True))
            p.setPen(QColor(data.get("color") or THEME["text"]))
            p.drawText(rect, mid, data["text"])
        elif k == "uma":
            r = self.win.data["runners"][data["n"]]
            pic = rect.height() - 12
            uma_face(ov, p, r, QRectF(rect.left() + 8, rect.top() + 6, pic, pic))
            p.setFont(ov.fnt(13, True))
            p.setPen(QColor(r["color"]))
            tx = rect.left() + pic + 18
            fm = QFontMetrics(p.font())
            p.drawText(QRectF(tx, rect.top() + 8, rect.right() - tx - 4, rect.height() / 2 - 6), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(r["name"], Qt.TextElideMode.ElideRight, int(rect.right() - tx - 6)))
            p.setFont(ov.fnt(11))
            p.setPen(sub)
            p.drawText(QRectF(tx, rect.top() + rect.height() / 2, rect.right() - tx - 4, rect.height() / 2 - 8), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                       "[%s]" % r["trainer"] if r["trainer"] else "")
        elif k == "two":
            p.setFont(ov.fnt(13, True))
            p.setPen(QColor(data.get("ac") or THEME["text"]))
            p.drawText(QRectF(rect.left(), rect.top() + 8, rect.width(), rect.height() / 2 - 4), mid, data["a"])
            if data.get("b"):
                bc = data.get("bc")
                p.setFont(ov.fnt(11, bool(bc)))
                sr = QRectF(rect.left(), rect.top() + rect.height() / 2 - 2, rect.width(), rect.height() / 2 - 6)
                if bc:                                             # a small coloured pill
                    w = QFontMetrics(p.font()).horizontalAdvance(data["b"]) + 14
                    pill = QRectF(rect.center().x() - w / 2, sr.top() + 2, w, 17)
                    pp = QPainterPath()
                    pp.addRoundedRect(pill, 4, 4)
                    p.fillPath(pp, QColor(bc).darker(300))
                    p.setPen(QColor(bc))
                    p.drawText(pill, Qt.AlignmentFlag.AlignCenter, data["b"])
                else:
                    p.setPen(sub)
                    p.drawText(sr, mid | Qt.AlignmentFlag.AlignTop, data["b"])
        elif k == "style":
            col = QColor(STYLE_COL.get(data["style"], "#aaaaaa"))
            d = min(rect.height() - 16, 44.0)
            cx = rect.center().x()
            badge = QRectF(cx - d - 3, rect.center().y() - d / 2, d, d)
            p.setBrush(QColor("#f4f6fa"))
            p.setPen(QPen(col, 3))
            p.drawEllipse(badge)
            p.setPen(QColor("#10161f"))
            p.setFont(ov.fnt(10, True))
            p.drawText(badge, Qt.AlignmentFlag.AlignCenter, data["style"].upper())
            arrow, mc = MOODS.get(data["mood"], ("?", "#aaaaaa"))
            mood = QRectF(cx + 3, rect.center().y() - d / 2, d, d)
            p.setBrush(QColor(mc))
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.drawEllipse(mood)
            p.setPen(QColor("#ffffff"))
            p.setFont(ov.fnt(20, True))
            p.drawText(mood, Qt.AlignmentFlag.AlignCenter, arrow)
        elif k == "stat":
            p.setFont(ov.fnt(12, mono=True))
            rows = data["vals"]
            colw = rect.width() / 3.0
            for i, (label, val, col) in enumerate(rows):
                cell = QRectF(rect.left() + (i % 3) * colw, rect.top() + (rect.height() / 2 - 20) + (i // 3) * 20, colw, 20)
                p.setPen(QColor(col))
                p.drawText(QRectF(cell.left() + 2, cell.top(), 22, 20), Qt.AlignmentFlag.AlignVCenter, label)
                p.setPen(text)
                p.drawText(QRectF(cell.left() + 22, cell.top(), colw - 24, 20), Qt.AlignmentFlag.AlignVCenter, str(val))
        p.restore()


class TableView(QTableWidget):
    """All umas, one row each, like the results table on Hakuraku. Click a row to see her skills below."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.tries = 0
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(66)
        self.setShowGrid(False)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setItemDelegate(CellDelegate(win, self))
        self.setStyleSheet("QTableWidget{background:%s;border:none;border-radius:12px;}"
                           "QHeaderView::section{background:#1b2336;color:#e6ebf5;font-weight:800;padding:10px 4px;border:none;"
                           "border-bottom:2px solid #3b4a72;}" % THEME["card"])
        self.cellClicked.connect(self.on_click)

    def fill(self, d):
        self.setColumnCount(len(COLUMNS))
        self.setHorizontalHeaderLabels(COLUMNS)
        rows = d["runners"] if d else []
        self.setRowCount(len(rows))
        win_speed = (rows[0]["speed"][-1] if rows and rows[0]["speed"] else None)
        for i, r in enumerate(rows):
            gap = ""
            if i and r["raw_time"] and rows[0]["raw_time"]:
                dt = r["raw_time"] - rows[0]["raw_time"]
                gap = ("+%.1fm" % (dt * win_speed)) if win_speed else ("+%.3fs" % dt)
            late = (r["start_delay"] or 0.0) > 0.08
            hp_txt = ""
            if r["hp"] and r["hp0"]:
                hp_txt = "%d HP (%.1f%%)" % (r["hp"][-1], 100.0 * r["hp"][-1] / r["hp0"])
            dry = r["empty_at"] is not None
            ls_speed = None
            if r["last_spurt_at"] and r["speed"]:
                after = [s for dd, s in zip(r["dist"], r["speed"]) if dd >= r["last_spurt_at"]]
                ls_speed = max(after) if after else None
            st = r["stats"] or {}
            stats = [("SPD", st.get("Spd"), "#4aa3ff"), ("STA", st.get("Sta"), "#ff7a7a"), ("POW", st.get("Pow"), "#ffb347"),
                     ("GUT", st.get("Gut"), "#ff8fb5"), ("WIT", st.get("Wit"), "#5de6c2")]
            cells = [
                {"k": "num", "text": str(r["place"]), "color": PLACE_COL.get(r["place"])},
                {"k": "num", "text": str(r["h"].id or "-")},
                {"k": "uma", "n": i},
                {"k": "two", "a": fmt_clock(r["raw_time"]), "b": gap},
                {"k": "style", "style": r["style"], "mood": r["mood"]},
                {"k": "two", "a": ("%.1fms" % (r["start_delay"] * 1000.0)) if r["start_delay"] is not None else "-",
                 "b": ("Late" if late else "Normal") if r["start_delay"] is not None else "", "bc": "#ff6b81" if late else "#5de6c2"},
                {"k": "two", "a": ("from %.0f m" % r["last_spurt_at"]) if r["last_spurt_at"] else "-",
                 "b": ("Speed: %.2f" % ls_speed) if ls_speed else ""},
                {"k": "two", "a": ("Ran dry at %.0f m" % r["empty_at"]) if dry else ("Survived" if r["hp"] else "-"),
                 "ac": "#ff8fa3" if dry else "#5de6c2", "b": hp_txt},
                {"k": "two", "a": ("from %.1f s" % r["duel_at"]) if r.get("duel_at") is not None else "-"},
                {"k": "two", "a": ("%.1fs rushed" % r["tempted"]) if r["tempted"] > 0.05 else "-"},
                {"k": "stat", "vals": [x for x in stats if x[1] is not None]},
            ]
            for c, data in enumerate(cells):
                it = QTableWidgetItem("")
                it.setData(Qt.ItemDataRole.UserRole, i)
                it.setData(Qt.ItemDataRole.UserRole + 1, data)
                self.setItem(i, c, it)
        hh = self.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for c, w in enumerate((58, 46, 180, 96, 112, 96, 104, 132, 84, 92, 190)):
            self.setColumnWidth(c, w)
        hh.setStretchLastSection(True)
        self.tries = 0

    def refresh_icons(self):
        """The pictures arrive a little after the race: draw again until they are there."""
        self.viewport().update()
        self.tries += 1

    def on_click(self, row, _col):
        self.win.stop_auto()
        it = self.item(row, 0)
        if it is not None:
            self.win.set_hl(it.data(Qt.ItemDataRole.UserRole))

    def mark(self, hl):
        self.viewport().update()


def skills_html(r):
    """Hit and missed skills of one uma, with the reason for every miss."""
    sub, ok, bad, mid = THEME["sub"], "#5de6c2", "#ff8fa3", "#ffd24a"
    kinds = {"cond": bad, "wit": mid, "unknown": sub}
    left = ["<b style='color:%s;font-size:14px'>Hit (%d)</b>" % (ok, len(r["hit"]))]
    for e in r["hit"]:
        extra = ("  x%d" % e["count"]) if e["count"] > 1 else ""
        where = (" - %.1f s, %.0f m" % (e["t"], e["dist"])) if e["dist"] is not None else (" - %.1f s" % e["t"])
        left.append("<span style='color:%s'>&#10004;</span> %s%s <span style='color:%s'>%s</span>" % (ok, e["name"], extra, sub, where))
    right = ["<b style='color:%s;font-size:14px'>Missed (%d)</b>" % (bad, len(r["miss"]))]
    for e in r["miss"]:
        col = kinds.get(e["kind"], sub)
        right.append("<span style='color:%s'>&#10008;</span> %s <span style='color:%s'> - %s</span>" % (col, e["name"], col, e["text"]))
    if not r["brought"]:
        right.append("<span style='color:%s'>The skills she brought are not known for this race.</span>" % sub)
    head = "<span style='font-size:15px;font-weight:700;color:%s'>%s</span>" % (r["color"], r["name"])
    if r.get("wit_chance"):
        head += "  <span style='color:%s'>wit check: about %.0f%% to pass</span>" % (sub, r["wit_chance"])
    note = ("<span style='color:%s;font-size:11px'>The game does not save why a skill missed. "
            "<span style='color:%s'>red</span> = its condition was never true in this race (sure). "
            "<span style='color:%s'>yellow</span> = it could have worked, so most likely the wit check (a guess). "
            "grey = needs course details I do not have.</span>" % (sub, bad, mid))
    return ("%s<table width='100%%' cellspacing='6'><tr><td valign='top' width='42%%'>%s</td><td valign='top'>%s</td></tr></table>%s"
            % (head, "<br>".join(left), "<br>".join(right), note))


class AnalysisWindow(QWidget):
    PAGES = (("table", "Table"), ("replay", "Replay"), ("speed", "Speed"), ("hp", "Stamina"), ("gap", "Gap"))
    AUTO = ("table", "speed", "hp", "gap")
    CHARTS = ("speed", "hp", "gap")

    def __init__(self, ov):
        super().__init__()
        self.ov = ov
        self.data = None
        self.hl = None                  # the uma that is followed
        self.hidden = set()
        self.hover = None               # {uma: value} while the mouse is over a chart
        self.compare = True             # speed / stamina compared to the field average
        self.auto = bool(ov.s.get("analysis_auto", True))
        self.pinned = False             # opened by hand: stays until you close it
        self.pending_at = None
        self.deadline = None
        self._count = 0
        self.setWindowTitle(ANALYSIS_NAME)
        self.setStyleSheet(build_theme_qss() + "AnalysisWindow{background:%s;} QLabel{color:%s;background:transparent;}"
                           "QTextBrowser{background:%s;border:none;border-radius:12px;padding:8px;color:%s;}"
                           % (THEME["bg"], THEME["text"], THEME["card"], THEME["text"]))
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.apply_flags()

        h = QHBoxLayout(self)
        h.setContentsMargins(12, 12, 12, 12)
        h.setSpacing(12)
        self.ulist = UmaList(self)
        h.addWidget(self.ulist)
        right = QVBoxLayout()
        right.setSpacing(8)
        self.lbl_title = QLabel("Analysis")
        self.lbl_title.setStyleSheet("font-size:17px;font-weight:800;")
        right.addWidget(self.lbl_title)
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
        self.btn_cmp = QPushButton("Compared to the field")
        self.btn_cmp.setCheckable(True)
        self.btn_cmp.setChecked(True)
        self.btn_cmp.setToolTip("On: each line shows how far above or below the average of all umas she was. Off: the real numbers.")
        self.btn_cmp.clicked.connect(self.on_compare)
        bar.addWidget(self.btn_cmp)
        right.addLayout(bar)
        self.stack = QStackedWidget()
        self.table = TableView(self)
        self.detail = QTextBrowser()
        self.detail.setOpenLinks(False)
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.table)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 2)
        self.replay = ReplayPage(self)
        self.views = {"table": split, "replay": self.replay}
        for k in ("speed", "hp", "gap"):
            self.views[k] = ChartView(self, k)
        for key, _l in self.PAGES:
            self.stack.addWidget(self.views[key])
        right.addWidget(self.stack, 1)
        self.lbl_sel = QLabel("")
        self.lbl_sel.setWordWrap(True)
        self.lbl_sel.setStyleSheet("font-size:13px;")
        right.addWidget(self.lbl_sel)
        h.addLayout(right, 1)
        self.page = ov.s.get("analysis_page", "table")
        if self.page not in self.views:
            self.page = "table"
        self.show_page(self.page)

        g = ov.cfg.get("analysis_geo")
        self.resize(1280, 720)
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
        self.replay.stop()
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
    def compare_on(self, kind):
        return self.compare and kind in ("speed", "hp")

    def on_compare(self):
        self.compare = self.btn_cmp.isChecked()
        self.stop_auto()
        self.refresh()

    def set_data(self, data):
        self.data = data
        self.hl = 0 if data and data["runners"] else None       # the winner is followed at the start
        self.hidden = set()
        self.hover = None
        self.lbl_title.setText(data["title"] if data else "No race yet")
        self.table.fill(data)
        self.replay.set_data(data)
        self.refresh()

    def refresh(self):
        d = self.data
        sel = d["runners"][self.hl] if d and self.hl is not None and self.hl < len(d["runners"]) else None
        self.table.mark(self.hl)
        if sel is not None:
            self.detail.setHtml(skills_html(sel))
            bits = [sel["name"]]
            if sel["top_speed"] is not None:
                bits.append("top speed %.1f m/s" % sel["top_speed"])
            if sel["hp_left"] is not None:
                bits.append("stamina left %.0f%%" % sel["hp_left"])
            if sel["tempted"] > 0.05:
                bits.append("tempted %.1f s" % sel["tempted"])
            if sel["blocked"] > 0.05:
                bits.append("blocked %.1f s" % sel["blocked"])
            self.lbl_sel.setText("  -  ".join(bits))
        else:
            self.detail.setHtml("<span style='color:%s'>Click an uma to see her skills.</span>" % THEME["sub"] if d else "")
            self.lbl_sel.setText("Click an uma on the left to follow her." if d else "")
        self.lbl_sel.setVisible(self.page in self.CHARTS)
        for v in list(self.views.values()) + [self.ulist]:
            v.update()
        self.replay.view.update()

    def set_hover(self, vals):
        self.hover = vals
        self.ulist.update()

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
        self.hover = None
        self.btns[key].setChecked(True)
        self.stack.setCurrentWidget(self.views[key])
        self.ulist.setVisible(key in self.CHARTS)
        if key != "replay":
            self.replay.stop()
        self.btn_cmp.setVisible(key in ("speed", "hp"))
        self.refresh()

    def on_page_click(self, key):
        self.stop_auto()
        self.show_page(key)
        self.ov.set_setting("analysis_page", key)

    def set_auto(self, on):
        self.auto = bool(on)
        self._count = 0

    def stop_auto(self):
        if self.auto:
            self.set_auto(False)
            self.ov.set_setting("analysis_auto", False)

    def on_second(self):
        if self.isVisible():
            self.ulist.update()
            if self.table.tries < 20:
                self.table.refresh_icons()          # the pictures arrive a little later
        if not self.isVisible() or not self.auto or not self.data:
            return
        self._count += 1
        if self._count >= max(2, int(float(self.ov.s.get("analysis_page_seconds", 8.0)))):
            self._count = 0
            pages = [k for k in self.AUTO if self.data["has_speed"] or k not in ("speed", "hp")]
            if self.page == "replay":
                return
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
                self.set_auto(bool(self.ov.s.get("analysis_auto", True)))
                if self.auto:
                    self.show_page(self.AUTO[0])
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
        self.set_data(data)
        self.set_auto(False)
        self.show()
        self.raise_()
        self.activateWindow()
        self.pinned = True
        self.ov.refresh_tray()
