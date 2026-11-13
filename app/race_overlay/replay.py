"""The race replay of the analysis board: the umas (their pictures) move along the track, 30 frames per second.
Left to right = distance, up = lane position. Click an uma to look only at her; the buttons above show or hide umas."""

import bisect
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
                             QVBoxLayout, QWidget)

from .theme import THEME

FPS = 30
LABEL_SECONDS = 2.5          # how long a skill name stays above an uma
PHASE_LINES = ((200.0, "Mid race"), (800.0, "Final leg"), (1000.0, "Last spurt"))


def nice_step(span, n=6):
    step = span / float(n)
    import math
    mag = 10 ** math.floor(math.log10(max(step, 1e-9)))
    for m in (1, 2, 2.5, 5, 10):
        if step <= m * mag:
            return m * mag
    return 10 * mag


class ReplayView(QWidget):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setMinimumSize(560, 300)
        self.setMouseTracking(True)
        self.cam = None
        self.faces = []                          # (rect, runner index) of the pictures drawn last

    # ----- where is everybody at time t ------------------------------------------------------------
    def state(self, r, t):
        ts = r["t"]
        if not ts:
            return None
        i = bisect.bisect_right(ts, t)
        if i <= 0:
            k0 = k1 = 0
            f = 0.0
        elif i >= len(ts):
            k0 = k1 = len(ts) - 1
            f = 0.0
        else:
            k0, k1 = i - 1, i
            f = (t - ts[k0]) / ((ts[k1] - ts[k0]) or 1.0)

        def lerp(arr):
            return arr[k0] + (arr[k1] - arr[k0]) * f if arr else None
        sp = lerp(r["speed"])
        hp = lerp(r["hp"])
        return {"dist": lerp(r["dist"]), "lane": lerp(r["lane_raw"]), "speed": sp,
                "hp": (100.0 * hp / r["hp0"]) if (hp is not None and r.get("hp0")) else None,
                "block": (r["block"][k0] if r["block"] else -1), "tempt": (r["tempt"][k0] if r["tempt"] else 0)}

    def target_x0(self, sts):
        W = self.page.window_m
        f = self.page.focus
        if f is not None and sts.get(f):
            return sts[f]["dist"] - W * 0.5
        ds = [s["dist"] for n, s in sts.items() if s and n not in self.page.hidden]
        return (max(ds) if ds else 0.0) - W * 0.8

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        ov, d = self.page.win.ov, self.page.win.data
        bg = QPainterPath()
        bg.addRoundedRect(QRectF(self.rect()), 12, 12)
        p.fillPath(bg, QColor("#05101c"))
        self.faces = []
        if not d:
            return
        from .analysis import uma_face
        t = self.page.t
        runners = d["runners"]
        sts = {n: self.state(r, t) for n, r in enumerate(runners)}
        W = self.page.window_m
        x0t = self.target_x0(sts)
        self.cam = x0t if self.cam is None else self.cam + (x0t - self.cam) * 0.35
        x0, x1 = self.cam, self.cam + W
        L, R, T, B = 64.0, 16.0, 16.0, 40.0
        pr = QRectF(L, T, self.width() - L - R, self.height() - T - B)
        lane_max = max(6000.0, max((r["lane_raw"] and max(r["lane_raw"]) or 0) for r in runners) * 1.08)

        def px(x):
            return pr.left() + pr.width() * (x - x0) / W

        def py(y):
            return pr.bottom() - pr.height() * (y / lane_max)

        p.fillRect(pr, QColor("#12232f"))
        p.fillRect(QRectF(pr.left(), py(1100), pr.width(), pr.bottom() - py(1100)), QColor(120, 130, 150, 70))
        sub = QColor(THEME["sub"])
        p.setFont(ov.fnt(10))
        for v in range(0, int(lane_max) + 1, 1000):           # lane position (left)
            p.setPen(QPen(QColor(255, 255, 255, 18), 1))
            p.drawLine(QPointF(pr.left(), py(v)), QPointF(pr.right(), py(v)))
            p.setPen(sub)
            p.drawText(QRectF(0, py(v) - 8, L - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "{:,}".format(v))
        step = nice_step(W, 6)                                # distance (bottom)
        x = int(x0 // step) * step
        while x <= x1:
            if x >= x0:
                p.setPen(sub)
                p.drawLine(QPointF(px(x), pr.bottom()), QPointF(px(x), pr.bottom() + 4))
                p.drawText(QRectF(px(x) - 30, pr.bottom() + 5, 60, 16), Qt.AlignmentFlag.AlignCenter, "%g" % x)
            x += step
        for dist, name in PHASE_LINES + ((d["total"], "Goal"),):
            if x0 <= dist <= x1:
                p.setPen(QPen(QColor(255, 255, 255, 110), 1, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(px(dist), pr.top() + 18), QPointF(px(dist), pr.bottom()))
                p.setPen(QColor("#10161f"))
                chip = QRectF(px(dist) - 34, pr.top() + 2, 68, 16)
                cp = QPainterPath()
                cp.addRoundedRect(chip, 4, 4)
                p.fillPath(cp, QColor("#c9ced8"))
                p.setFont(ov.fnt(10))
                p.drawText(chip, Qt.AlignmentFlag.AlignCenter, name)
        p.setPen(sub)
        p.setFont(ov.fnt(10))
        p.save()
        p.translate(14, pr.center().y())
        p.rotate(-90)
        p.drawText(QRectF(-80, -10, 160, 14), Qt.AlignmentFlag.AlignCenter, "Lane position")
        p.restore()
        shown = [n for n in range(len(runners)) if n not in self.page.hidden]
        foc = self.page.focus
        rad = max(16.0, min(28.0, pr.height() / 13.0))
        order = sorted(shown, key=lambda n: (n == foc, -sts[n]["dist"] if sts[n] else 0))
        p.setClipRect(pr.adjusted(-30, -40, 30, 30))
        for n in order:
            s = sts[n]
            if not s or s["dist"] is None:
                continue
            r = runners[n]
            cx, cy = px(s["dist"]), py(s["lane"] or 0.0)
            dim = foc is not None and n != foc
            p.setOpacity(0.22 if dim else 1.0)
            ring = QPainterPath()
            ring.addEllipse(QPointF(cx, cy), rad + 2.5, rad + 2.5)
            p.fillPath(ring, QColor(r["color"]))
            rect = QRectF(cx - rad, cy - rad, rad * 2, rad * 2)
            uma_face(ov, p, r, rect)
            self.faces.append((rect, n))
            if self.page.cb_block.isChecked() and s["block"] is not None and s["block"] >= 0 and not dim:
                p.setPen(QPen(QColor("#ff4d4d"), 3))
                p.drawArc(rect.adjusted(-4, -4, 4, 4), 100 * 16, 160 * 16)
            if not dim:
                labels = []
                if self.page.cb_skills.isChecked():
                    labels += [a["name"] for a in r["acts"] if 0.0 <= t - a["t"] <= LABEL_SECONDS]
                if self.page.cb_modes.isChecked():
                    if s["tempt"]:
                        labels.append("Rushed")
                    if r.get("duel_at") is not None and r["duel_at"] <= t <= (r["raw_time"] or 1e9):
                        labels.append("Dueling")
                y = rect.top() - 6
                p.setFont(ov.fnt(10))
                fm = QFontMetrics(p.font())
                for text in labels[:4]:
                    w = fm.horizontalAdvance(text) + 12
                    chip = QRectF(cx - w / 2, y - 17, w, 17)
                    cp = QPainterPath()
                    cp.addRoundedRect(chip, 5, 5)
                    p.fillPath(cp, QColor("#f4f6fa"))
                    p.setPen(QColor("#10161f"))
                    p.drawText(chip, Qt.AlignmentFlag.AlignCenter, text)
                    y -= 19
            p.setOpacity(1.0)
        p.setClipping(False)
        lead = max((s["dist"] for n, s in sts.items() if s and n in shown), default=0.0)
        shown_d = sts[foc]["dist"] if foc is not None and sts.get(foc) else lead
        box = QRectF(self.width() - 86, self.height() - 26, 76, 22)
        bp = QPainterPath()
        bp.addRoundedRect(box, 5, 5)
        p.fillPath(bp, QColor("#f4f6fa"))
        p.setPen(QColor("#10161f"))
        p.setFont(ov.fnt(12, True))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, "%.0f m" % shown_d)
        if foc is not None and sts.get(foc):                   # a small card with the numbers of the followed uma
            r, s = runners[foc], sts[foc]
            card = QRectF(pr.left() + 10, pr.top() + 24, 230, 64)
            cp = QPainterPath()
            cp.addRoundedRect(card, 8, 8)
            p.fillPath(cp, QColor(10, 16, 28, 210))
            p.setPen(QColor(r["color"]))
            p.setFont(ov.fnt(12, True))
            p.drawText(card.adjusted(10, 6, -8, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, r["name"])
            p.setPen(QColor(THEME["text"]))
            p.setFont(ov.fnt(11, mono=True))
            p.drawText(card.adjusted(10, 26, -8, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                       "Speed  %s" % ("%.1f m/s" % s["speed"] if s["speed"] is not None else "-"))
            p.drawText(card.adjusted(10, 43, -8, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                       "Stamina %s" % ("%.0f%%" % s["hp"] if s["hp"] is not None else "-"))

    def mousePressEvent(self, ev):
        for rect, n in reversed(self.faces):
            if rect.adjusted(-4, -4, 4, 4).contains(ev.position()):
                self.page.set_focus(None if self.page.focus == n else n)
                return
        self.page.set_focus(None)


class ReplayPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.t = 0.0
        self.t_end = 1.0
        self.playing = False
        self.focus = None
        self.hidden = set()
        self.window_m = 80.0
        self.last = None
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        self.chips = QGridLayout()
        self.chips.setSpacing(6)
        v.addLayout(self.chips)
        self.view = ReplayView(self)
        v.addWidget(self.view, 1)
        row = QHBoxLayout()
        self.btn_play = QPushButton("Play")
        self.btn_play.setObjectName("primary")
        self.btn_play.setMinimumWidth(80)
        self.btn_play.clicked.connect(self.toggle_play)
        row.addWidget(self.btn_play)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1)
        self.slider.sliderMoved.connect(self.on_slider)
        self.slider.sliderPressed.connect(lambda: self.set_playing(False))
        row.addWidget(self.slider, 1)
        self.lbl_time = QLabel("0.00 s / 0.00 s")
        self.lbl_time.setMinimumWidth(110)
        row.addWidget(self.lbl_time)
        v.addLayout(row)
        opts = QHBoxLayout()
        opts.addWidget(QLabel("Speed"))
        self.cmb_speed = QComboBox()
        for label, val in (("0.25x", 0.25), ("0.5x", 0.5), ("1x", 1.0), ("2x", 2.0), ("4x", 4.0)):
            self.cmb_speed.addItem(label, val)
        self.cmb_speed.setCurrentIndex(2)
        opts.addWidget(self.cmb_speed)
        opts.addWidget(QLabel("View window"))
        self.sp_win = QDoubleSpinBox()
        self.sp_win.setRange(30, 600)
        self.sp_win.setDecimals(0)
        self.sp_win.setSuffix(" m")
        self.sp_win.setValue(self.window_m)
        self.sp_win.valueChanged.connect(self.on_window)
        opts.addWidget(self.sp_win)
        self.cb_skills = QCheckBox("Skill labels")
        self.cb_modes = QCheckBox("Race modes")
        self.cb_block = QCheckBox("Block indicator")
        for cb in (self.cb_skills, self.cb_modes, self.cb_block):
            cb.setChecked(True)
            cb.toggled.connect(lambda _c: self.view.update())
            opts.addWidget(cb)
        opts.addStretch(1)
        opts.addWidget(QLabel("%d FPS" % FPS))
        v.addLayout(opts)
        self.timer = QTimer(self)
        self.timer.setInterval(int(1000 / FPS))
        self.timer.timeout.connect(self.tick)
        self.btns = []

    # ----- data -----------------------------------------------------------------------------------
    def set_data(self, d):
        self.set_playing(False)
        self.focus = None
        self.hidden = set()
        self.view.cam = None
        self.t = 0.0
        self.t_end = max(0.5, d["max_t"]) if d else 0.5
        self.slider.setRange(0, int(self.t_end * FPS))
        for b in self.btns:
            b.setParent(None)
        self.btns = []
        if d:
            all_b = QPushButton("Toggle all")
            all_b.clicked.connect(self.toggle_all)
            self.chips.addWidget(all_b, 0, 0)
            self.btns.append(all_b)
            for n, r in enumerate(d["runners"]):
                b = QPushButton("#%s %s [%s]" % (r["h"].id or r["place"], r["name"], r["trainer"]))
                b.setCheckable(True)
                b.setChecked(True)
                b.setStyleSheet("QPushButton{border-left:5px solid %s;text-align:left;padding:3px 8px;}" % r["color"])
                b.setMinimumWidth(10)
                b.clicked.connect(lambda _c=False, k=n: self.toggle_hidden(k))
                self.chips.addWidget(b, (n + 1) // 5, (n + 1) % 5)
                self.btns.append(b)
        self.update_time()
        self.view.update()

    def toggle_hidden(self, n):
        if n in self.hidden:
            self.hidden.discard(n)
        else:
            self.hidden.add(n)
        if self.focus in self.hidden:
            self.focus = None
        self.sync_chips()
        self.view.update()

    def toggle_all(self):
        d = self.win.data
        if not d:
            return
        self.hidden = set() if self.hidden else set(range(len(d["runners"])))
        self.focus = None
        self.sync_chips()
        self.view.update()

    def sync_chips(self):
        for n, b in enumerate(self.btns[1:]):
            b.setChecked(n not in self.hidden)

    def set_focus(self, n):
        self.focus = n
        if n is not None:
            self.hidden.discard(n)
            self.sync_chips()
        self.view.cam = None
        self.view.update()

    def on_window(self, v):
        self.window_m = float(v)
        self.view.update()

    # ----- playing ---------------------------------------------------------------------------------
    def set_playing(self, on):
        self.playing = bool(on)
        self.btn_play.setText("Pause" if on else "Play")
        self.last = time.monotonic()
        if on:
            self.timer.start()
        else:
            self.timer.stop()

    def toggle_play(self):
        if not self.playing and self.t >= self.t_end - 0.01:
            self.t = 0.0
            self.view.cam = None
        self.set_playing(not self.playing)

    def on_slider(self, v):
        self.t = v / float(FPS)
        self.update_time()
        self.view.update()

    def tick(self):
        now = time.monotonic()
        dt = min(0.2, now - (self.last or now))
        self.last = now
        self.t += dt * float(self.cmb_speed.currentData() or 1.0)
        if self.t >= self.t_end:
            self.t = self.t_end
            self.set_playing(False)
        self.update_time()
        self.view.update()

    def update_time(self):
        self.slider.blockSignals(True)
        self.slider.setValue(int(self.t * FPS))
        self.slider.blockSignals(False)
        self.lbl_time.setText("%.2f s / %.2f s" % (self.t, self.t_end))

    def stop(self):
        self.set_playing(False)
