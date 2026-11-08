"""The overlay window: the race tower, tray icon, menus."""

import bisect
import os
import time
from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from . import logbuf
from .config import save_config
from .constants import (
    APP_NAME,
    ARROW_AFTER,
    CLOCK_HEADER_H,
    ARROW_SECONDS,
    BASE_W,
    COMPACT_HEADER_H,
    COMPACT_ROW_H,
    COMPACT_W,
    DEFAULT_SETTINGS,
    FOOT_PAD,
    HEADER_H,
    IMG_EXTS,
    KEEP_ON_RESET,
    PODIUM,
    ROW_H,
    IMAGES_DIR,
    SCRIPT_DIR,
    SLIDE_SECONDS,
    STATE_COLORS,
    STYLE_COLOR,
    STYLE_LABEL,
    THEME_PRESETS,
    WAKU_COLORS,
    WAKU_DARK,
)
from .databases import CardTitles, UmasDB, OutfitsDB, PlayersDB
from .frameless import FramelessMixin, fit_window
from .images import ImageStore, find_file_ci, find_wine_thumb_dirs
from .results_board import ResultsBoard
from .setups import get_setup
from .scoring import ScoreBook, norm_name, points_for, strip_club_tag
from .settings_dialog import SettingsDialog
from .simdata import parse_sim
from .sources import TestReplayThread, WatchThread, choose_source
from .luck import luck_table, pick, skill_ids
from .luck_board import LuckBoard
from .match import Match
from .match_board import MatchBoard
from .standings_board import StandingsBoard
from .tray import make_tray_icon
from .autoupdate import AutoUpdate
from .updater import Job, restart_program
from . import sheetwrite
from .racedata import RaceLog, build_record
from .constants import CONFIG_DIR as _CFG_DIR
from .util import fmt_time, install_exit_hooks, open_folder, stop_started_server


class Horse:
    def __init__(self, r, idx):
        self.id = r.get("frameOrder") or idx + 1
        self.frame_idx = self.id - 1
        self.name = r.get("name") or "?"
        self.trainer = r.get("trainer") or ""
        self.style = r.get("style") or 0
        self.gate = r.get("gate") or 0
        self.chara_id = r.get("charaId") or (r.get("dressId", 0) // 100 if r.get("dressId") else 0)
        self.dress_id = int(r.get("dressId") or 0)
        self.skills = skill_ids(r.get("skills") or r.get("skill_array"))     # equipped skills, when known
        self.label = self.name          # what is shown: "Name" or "Name (Outfit)"
        self.card_id = 0
        self.pkey = None
        self.ukey = None
        self.bkey = None
        self.y = None
        self.target = 0.0
        self.rank = 0
        self.gap_lines = ("", "")
        self.gap_kind = "none"
        self.hidden = False         # not shown in the tower ('Players only')
        self.prev_rank = None       # place on the previous frame (for the up / down arrow)
        self.move_dir = 0           # +1 gained a place, -1 lost one
        self.move_at = 0.0


class OverlayWidget(FramelessMixin, QWidget):
    def __init__(self, args, cfg):
        super().__init__()
        self.args = args
        self.cfg = cfg
        self.base = args.server
        self.setWindowTitle(APP_NAME)  # <- this is the window name you pick in OBS
        self.setMinimumSize(200, 120)

        self.s = dict(DEFAULT_SETTINGS)
        self.s.update({k: v for k, v in (cfg.get("settings") or {}).items() if k in DEFAULT_SETTINGS})
        if (cfg.get("settings") or {}).get("avatar_mode") == "uma" and "pictures" not in (cfg.get("settings") or {}):
            self.s["pictures"] = "uma"      # older versions: "uma faces only" stays "uma faces only"
        if args.bg:
            self.s["bg"] = args.bg
        if args.bg_opacity is not None:
            self.s["bg_opacity"] = args.bg_opacity
        if args.on_top:
            self.s["on_top"] = True
        self.dialog = None
        self.source_kind = "live"      # set by main(): "live", "watch" or "demo"
        self.tray = None
        self.tray_active = False
        self.slide = 0.0               # 0 = tower is out of the window, 1 = fully slid in
        self.pinned = False            # "Show overlay window": keep it visible to place it
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)   # never steal focus from the game
        self.quitting = False
        self.state = "yellow"
        self.preview = False
        self.preview_start = 0.0
        self.preview_len = 40.0
        self.board_done = False        # the results board was already queued for this race

        flags = Qt.WindowType.Window
        if args.frameless or args.transparent or not self.s.get("title_bar", False):
            flags |= Qt.WindowType.FramelessWindowHint
        self.setMouseTracking(True)
        if self.s.get("on_top", True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        if args.transparent:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # state
        self.horses = []
        self.times = []
        self.frames = []
        self.results = []
        self.course_info = None
        self.course_shape = None
        self.course_data = None
        self.result_map = {}
        self.racing = False
        self.hide_deadline = None
        self.clock_active = False
        self.clock_paused = False
        self.prev_clock = -1.0
        self.last_clock_time = 0.0
        self.last_clock_at = time.monotonic()
        self.panel_alpha = 0.0
        self.status_text = "Starting..."
        self.final_clock_text = None
        self.terrain_text = ""
        self.clock_text = "0.00"
        self.pix = {}          # card_id -> QPixmap
        self.pix_pending = set()
        self._drag = None
        self._last_tick = time.monotonic()

        images_dir = os.path.expanduser(args.images_dir) if args.images_dir else IMAGES_DIR
        extra = [os.path.expanduser(args.thumbs_dir)] if args.thumbs_dir else []
        extra += find_wine_thumb_dirs(self.s.get("race_overlay_dir", ""))
        self.thumbs = ImageStore(self.base, images_dir, extra)
        self.autoupdate = AutoUpdate(self)
        self.images_dir = images_dir
        self.players = PlayersDB(os.path.join(images_dir, "players.json"))
        self.outfits = OutfitsDB(os.path.join(images_dir, "outfits.json"))
        self.outfits.titles = CardTitles(self.umdb_paths)
        self.umas = UmasDB(os.path.join(images_dir, "umas.json"))
        self.thumbs.use_default = bool(self.s.get("default_faces", True))
        self.thumbs.loaded.connect(self.on_thumb)
        self.thumbs.start()

        g = cfg.get("geometry")
        if g and not args.reset_window:
            self.setGeometry(*g)
        else:
            self.resize(BASE_W, 420)

        self.board = ResultsBoard(self)
        self.test_thread = None                 # "Replay a saved race (test)"
        self.book = ScoreBook()                 # points of every race (scores.json)
        self.standings = StandingsBoard(self)
        self.luck = LuckBoard(self)
        self.match_note = ""
        self.match = Match()                    # team match (draft): teams, players, races (match.json)
        self.mboard = MatchBoard(self)
        self.skill_acts = {}                    # {horse index: [skill ids that activated]}

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    # ----- tower style: the full tower or the small corner tower ---------------------------
    def compact(self):
        return self.s.get("tower_style") == "compact"

    @property
    def bw(self):
        return COMPACT_W if self.compact() else BASE_W

    @property
    def hh_base(self):
        """The header height at normal size."""
        mode = self.s.get("tower_header", "both")
        if mode == "none":
            return 0
        if mode == "clock":
            return CLOCK_HEADER_H
        return COMPACT_HEADER_H if self.compact() else HEADER_H

    def header_k(self):
        try:
            return min(2.0, max(0.6, float(self.s.get("header_scale", 1.0))))
        except (TypeError, ValueError):
            return 1.0

    @property
    def hh(self):
        return int(round(self.hh_base * self.header_k()))

    @property
    def rh(self):
        return COMPACT_ROW_H if self.compact() else ROW_H

    def logical_w(self):
        return self.bw

    def snap_to_corner(self, corner):
        """Move the window to a corner of its screen (top-left, top-right, bottom-left, bottom-right)."""
        scr = self.screen()
        if scr is None or corner not in ("top-left", "top-right", "bottom-left", "bottom-right"):
            return
        av, m = scr.availableGeometry(), 24
        x = av.left() + m if corner.endswith("left") else av.right() - self.width() - m + 1
        y = av.top() + m if corner.startswith("top") else av.bottom() - self.height() - m + 1
        self.move(x, y)

    # ----- source wiring ------------------------------------------------------
    def attach(self, source):
        self.source = source
        source.race.connect(self.on_race)
        source.clock.connect(self.on_clock)
        source.status.connect(self.on_status)
        source.quit_request.connect(self.quit_app)
        install_exit_hooks(lambda: QTimer.singleShot(0, self.quit_app),
                           lambda: stop_started_server() if self.s.get("stop_server", True) else None)
        self._signal_tick = QTimer(self)             # lets Python see Ctrl+C while Qt is running
        self._signal_tick.start(500)
        self._signal_tick.timeout.connect(lambda: None)
        self.autoupdate.start()                      # a few seconds later: is there a new version?
        source.offset = float(self.cfg.get("sync_offset", 0.0))
        source.delay = float(self.s.get("start_delay", 12.0))
        source.start()

    def on_status(self, text):
        if text != self.status_text:
            logbuf.add("status: " + text.replace("\n", " | "))
        self.status_text = text
        t = text.lower()
        if "not reachable" in t or "not found" in t:
            self.state = "red"
        elif "waiting for uma" in t or "connecting" in t:
            self.state = "yellow"
        else:
            self.state = "green"
        self.refresh_tray()
        self.update()

    # ----- images --------------------------------------------------------------
    def want_img(self, key, spec):
        if key and key not in self.pix and key not in self.pix_pending:
            self.pix_pending.add(key)
            self.thumbs.request(key, spec)

    def on_thumb(self, key, data):
        pm = QPixmap()
        self.pix[key] = pm if (data and pm.loadFromData(data)) else None
        self.update()

    def uma_pixmap(self, h):
        """The picture of the UMA (always the same for the same uma / outfit)."""
        for k in (h.ukey, h.bkey):
            if k and self.pix.get(k):
                return self.pix[k]
        return None

    def player_pixmap(self, h):
        """The picture of the PLAYER (follows the trainer, whatever uma they run)."""
        return self.pix.get(h.pkey) if h.pkey else None

    def picture_mode(self):
        m = self.s.get("pictures", "both")
        return m if m in ("both", "uma", "player") else "both"

    # ----- race events ---------------------------------------------------------
    def on_race(self, payload, rmap):
        self.preview = False
        self.hide_deadline = None
        self.racing = False
        try:
            sim = parse_sim(payload["replay"])
        except Exception as e:
            print("SimData parse error:", e)
            return
        self.setup_race(sim, payload, rmap, collect=True)
        logbuf.add("race loaded: %d umas" % len(self.horses))

    def setup_race(self, sim, payload, rmap, collect=False):
        self.times, self.frames, self.results = sim["times"], sim["frames"], sim["results"]
        self.result_map = rmap

        self.board_done = False
        self.board.dismiss()                 # the results of the last race go away
        self.standings.dismiss()
        self.luck.dismiss()
        self.mboard.dismiss()
        self.skill_acts = sim.get("skills") or {}
        self.skill_log = sim.get("skill_log") or []
        self.horses = self.build_horses(payload, rmap)

        if collect:   # remember every trainer we see, so you can give them a picture
            for h in self.horses:
                if h.trainer:
                    self.players.touch(h.trainer, h.name)
            self.players.save()
            new_outfit = False
            for h in self.horses:         # ... and every alternative outfit, so you can name it
                new_outfit |= self.outfits.touch(h.chara_id, h.dress_id, h.name, h.card_id)
            if new_outfit:
                self.outfits.save()
            new_uma = False
            for h in self.horses:         # ... and every uma, so you can give her your own picture
                new_uma |= self.umas.touch(h.card_id, h.chara_id, h.name)
            self.umas.save()
            if self.dialog is not None:
                self.dialog.refresh_players()
                self.dialog.refresh_umas()

        self.course_shape = payload.get("courseShape")
        self.course_data = payload.get("courseData")
        self.course_info = payload.get("courseInfo")
        self.final_clock_text = None
        self.compute(0.0)
        self.fit_to_rows()
        self.update()

    def pick_card(self, chara, dress_id, trained_card=0):
        """The card whose picture and name show for a runner. The outfit worn in the race (the dress id) decides:
        the card in the race data is only the one she was trained with (a Summer Special Week can be trained
        with the Ruler of Japan card)."""
        base = chara * 100 + 1 if chara else 0
        if chara and dress_id and int(dress_id) // 100 == int(chara):         # a real outfit id of this uma
            if int(dress_id) == base:
                return base
            return self.outfits.card_for(chara, dress_id, self.thumbs.cards_of(chara)) or base
        return trained_card or base

    def uma_full_name(self, card, chara, name):
        """"Inari One" for her normal outfit, "Inari One Festival" for another one (so two cards never look the same)."""
        if not card or not chara or int(card) == int(chara) * 100 + 1:
            return name
        return "%s %s" % (name, self.outfits.auto_label(0, card) or "Alt")

    def umdb_paths(self):
        """Where Race Overlay's umdb.json (official outfit names) may be: your images folder, then the server folder."""
        paths = [os.path.join(self.images_dir, "umdb.json")]
        try:
            from .diagnostics import find_race_overlay
            folder = find_race_overlay(self.s.get("race_overlay_dir", ""))
            if folder:
                paths.append(os.path.join(folder, "resources", "umdb.json"))
        except Exception:
            pass
        return paths

    def build_horses(self, payload, rmap):
        """One Horse per runner, with the picture keys set and the pictures requested."""
        by_chara = {h.get("chara_id"): h for h in rmap.values() if h.get("chara_id")}
        horses = []
        for i, r in enumerate(payload.get("runners") or []):
            h = Horse(r, i)
            rm = rmap.get(h.id) or by_chara.get(h.chara_id) or {}
            if not h.skills:
                h.skills = skill_ids(rm.get("skills") or rm.get("skill_array"))
            chara = rm.get("chara_id") or h.chara_id
            h.chara_id = chara
            base_card = chara * 100 + 1 if chara else 0
            h.card_id = self.pick_card(chara, h.dress_id, rm.get("card_id") or 0)
            h.label = self.outfits.display(h.name, h.chara_id, h.dress_id, h.card_id)
            base = h.chara_id * 100 + 1 if h.chara_id else 0
            if h.trainer:
                h.pkey = "p:" + h.trainer.strip().lower()
                self.want_img(h.pkey, {"kind": "player", "trainer": h.trainer})
            if h.card_id:
                h.ukey = "c:%d" % h.card_id
                self.want_img(h.ukey, {"kind": "uma", "card_id": h.card_id, "chara_id": h.chara_id, "name": h.name})
            if base and base != h.card_id:
                h.bkey = "c:%d" % base
                self.want_img(h.bkey, {"kind": "uma", "card_id": base, "chara_id": h.chara_id, "name": h.name})
            horses.append(h)
        return horses

    # ----- auto size: the window follows the number of umas ----------------------------
    def update_hidden(self):
        """'Players only': umas without a trainer name are left out of the tower (when anybody has a name)."""
        only = bool(self.s.get("players_only", False)) and any(h.trainer.strip() for h in self.horses)
        for h in self.horses:
            h.hidden = only and not h.trainer.strip()

    def visible_rows(self):
        self.update_hidden()
        n = sum(1 for h in self.horses if not h.hidden)
        if self.compact():
            return min(n, max(2, int(self.s.get("compact_rows", 5) or 5)))
        m = int(self.s.get("max_rows", 0) or 0)
        return min(n, m) if m > 0 else n

    def refit_rows_now(self):
        """The tower style changed: put every row at its new place at once."""
        for h in self.horses:
            h.target = h.rank * self.rh
            h.y = h.target
        self.update()

    def fit_to_rows(self):
        """Make the window exactly as tall as the umas that are shown. When that is taller than the
        screen, the whole tower is scaled down to fit (and goes back to your size for a smaller field)."""
        if self.args.no_autosize or not self.horses:
            return
        fit_window(self, self.bw, self.hh + self.visible_rows() * self.rh + FOOT_PAD, self.pref_scale)

    def on_clock(self, p):
        now = time.monotonic()
        if p.get("active") and self.frames:
            if not self.racing:
                self.racing = True
                logbuf.add("race started (%d umas)" % len(self.horses))
            t = float(p.get("time", 0))
            self.clock_paused = self.prev_clock >= 0 and abs(t - self.prev_clock) < 0.02
            self.prev_clock = t
            self.clock_active = True
            self.last_clock_time = t
            self.last_clock_at = now
            self.hide_deadline = None
        elif not p.get("active"):
            self.clock_active = False
            self.prev_clock = -1.0
            if self.racing and self.hide_deadline is None:
                logbuf.add("race finished")
                if self.frames:
                    max_t = max([r["finishTimeRaw"] for r in self.results] + [self.last_clock_time])
                    self.compute(max_t + 0.001)
                    self.on_race_finished()
                if not self.args.hold:
                    self.hide_deadline = now + self.args.hide_after

    # ----- the per-frame tick --------------------------------------------------
    def tick(self):
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now

        if self.clock_active and self.frames:
            el = 0.0 if self.clock_paused else (now - self.last_clock_at)
            self.compute(self.last_clock_time + el)

        if self.preview and self.frames:
            self.racing = True
            self.compute((now - self.preview_start) % self.preview_len)

        if self.hide_deadline is not None and now >= self.hide_deadline:
            self.racing = False
            self.hide_deadline = None

        want = 1.0 if (self.racing and self.horses) else 0.0
        self.panel_alpha += (want - self.panel_alpha) * min(1.0, dt * 8)
        if abs(want - self.panel_alpha) < 0.01:
            self.panel_alpha = want

        # slide in while a race runs, slide out afterwards; the window itself only shows during a race
        if want and self.auto_hide_active() and not self.isVisible():
            self.reveal()
        step = dt / SLIDE_SECONDS
        if self.slide < want:
            self.slide = min(want, self.slide + step)
        elif self.slide > want:
            self.slide = max(want, self.slide - step)
        if (not want and self.slide <= 0.0 and self.isVisible() and self.auto_hide_active()
                and not self.pinned):
            self.hide()

        k = min(1.0, dt * 14)
        for h in self.horses:
            if h.y is None:
                h.y = h.target
            else:
                h.y += (h.target - h.y) * k
        self.board.tick(now, dt)
        self.standings.tick(now, dt)
        self.luck.tick(now, dt)
        self.mboard.tick(now, dt)
        self.update()

    # ----- tower maths (port of renderTime) ------------------------------------
    def interpolate(self, t):
        if not self.frames:
            return None
        times = self.times
        hi = bisect.bisect_right(times, t)
        lo = max(0, hi - 1)
        hi = min(len(times) - 1, max(hi, lo))
        a, b = self.frames[lo], self.frames[hi]
        ta, tb = times[lo], times[hi]
        f = 1.0 if tb <= ta else max(0.0, min(1.0, (t - ta) / (tb - ta)))
        out = []
        for i, (d, ln) in enumerate(a):
            if i < len(b):
                d2, l2 = b[i]
            else:
                d2, l2 = d, ln
            out.append((d + (d2 - d) * f, ln + (l2 - ln) * f))
        return out

    def compute(self, t):
        frame = self.interpolate(t)
        if frame is None:
            return
        total = (self.course_shape or {}).get("distance") or (self.course_data or {}).get("distance") or 0
        entries = []
        self.update_hidden()
        for h in self.horses:
            if h.hidden:
                continue
            d, ln = frame[h.frame_idx] if h.frame_idx < len(frame) else (0.0, 0)
            res = self.results[h.frame_idx] if h.frame_idx < len(self.results) else None
            fin = bool(res and res["finishTimeRaw"] > 0 and res["finishTimeRaw"] <= t)
            entries.append({"h": h, "dist": (total or d) if fin else d, "res": res, "fin": fin})

        def key(e):
            if e["fin"]:
                return (0, e["res"]["finishTimeRaw"])
            return (1, -e["dist"])
        entries.sort(key=key)

        all_fin = bool(entries) and all(e["fin"] for e in entries)
        if all_fin:
            self.terrain_text = "Race Finished"
        else:
            self.terrain_text = self.terrain_for(entries[0]["dist"] if entries else 0)

        for rank, e in enumerate(entries):
            h, res, fin = e["h"], e["res"], e["fin"]
            if h.prev_rank is not None and rank != h.prev_rank and t > ARROW_AFTER:
                h.move_dir = 1 if rank < h.prev_rank else -1
                h.move_at = time.monotonic()
            h.prev_rank = rank
            h.rank = rank
            h.target = rank * self.rh
            if rank == 0:
                if fin and res:
                    h.gap_kind, h.gap_lines = "done", (fmt_time(res["finishTimeRaw"]), "")
                else:
                    h.gap_kind, h.gap_lines = "lead", ("Leader", "")
            elif fin and res:
                prev = entries[rank - 1]
                prev_t = prev["res"]["finishTimeRaw"] if prev["res"] else 0
                tdiff = (res["finishTimeRaw"] - prev_t) if prev_t > 0 else res["finishDiffTime"]
                pos_at_prev = 0.0
                if prev_t > 0:
                    fr = self.interpolate(prev_t)
                    if fr and h.frame_idx < len(fr):
                        pos_at_prev = fr[h.frame_idx][0]
                dgap = (total - pos_at_prev) if (pos_at_prev > 0 and total) else 0.0
                h.gap_kind = "box"
                h.gap_lines = (fmt_time(res["finishTimeRaw"]), "+%.3f  %.1fm" % (tdiff, dgap))
            else:
                prev_d = entries[rank - 1]["dist"]
                gm = prev_d - e["dist"]
                gs = gm * t / prev_d if (t > 0 and prev_d > 0) else 0.0
                h.gap_kind = "box"
                h.gap_lines = ("+%.2f" % gs, "%.1fm" % gm)

        if all_fin:
            last = max([e["res"]["finishTimeRaw"] for e in entries if e["res"]] + [0])
            self.clock_text = fmt_time(last or t)
            self.clock_active = False
        else:
            self.clock_text = fmt_time(t)

    def terrain_for(self, d):
        cd = self.course_data
        if not cd or d <= 0:
            return ""
        total = cd.get("distance") or 0
        if total <= 0:
            return ""
        phase = ("Early" if d < total / 6 else "Mid" if d < total * 2 / 3
                 else "Late" if d < total * 5 / 6 else "Last Spurt")
        section = ""
        for c in cd.get("corners", []) or []:
            if c["start"] <= d <= c["start"] + c["length"]:
                section = "Corner"
                break
        if not section:
            for s in cd.get("straights", []) or []:
                if s["start"] <= d <= s["end"]:
                    final = s.get("frontType") == 1 and s["end"] >= total - 100
                    section = "Final Straight" if final else "Straight"
                    break
        grade = ""
        for sl in cd.get("slopes", []) or []:
            if sl["start"] <= d <= sl["start"] + sl["length"]:
                grade = "Uphill" if sl["slope"] > 0 else "Downhill"
                break
        parts = ["  ·  ".join([x for x in (phase, section) if x])]
        if grade:
            parts.append(grade)
        return "  ·  ".join(parts)

    # ----- painting ------------------------------------------------------------
    _role = ""                                  # "header" or "row" while one of those is being drawn

    def pick_color(self, role):
        """The text colour of the header or of the tower rows: their own colour, or the main text colour."""
        c = QColor(self.s.get(role + "_color") or "")
        return c if c.isValid() else QColor(self.s["text_color"])

    def fnt(self, px, bold=False, mono=False):
        """A font that follows the Settings window (family + size %), or the header / racer font of the part being drawn."""
        role = {"header": "header", "row": "racer"}.get(self._role, "")
        fam = (self.s.get(role + "_font") if role and not mono else "") or self.s.get("font") or ("Monospace" if mono else "")
        f = QFont(fam) if fam else QFont()
        if self._role == "row":
            try:
                px = px * min(1.6, max(0.6, float(self.s.get("racer_scale", 1.0))))
            except (TypeError, ValueError):
                pass
        f.setPixelSize(max(6, int(round(px * float(self.s.get("text_scale", 1.0))))))
        f.setBold(bold)
        return f

    # ----- when the window shows, and the slide ------------------------------------
    def auto_hide_active(self):
        """True when the window should only be visible while a race runs.
        Not possible without a tray icon (you could not get it back), and --show keeps it always visible."""
        return bool(self.s.get("auto_hide", True) and self.tray_active and not self.args.show
                    and not self.args.no_tray)

    def window_wanted(self):
        """What the 'Show / Hide overlay window' button means right now."""
        if self.auto_hide_active():
            return self.pinned
        return self.isVisible()

    def reveal(self):
        """Show the window for a race without taking the keyboard focus away from the game."""
        self.slide = 0.0
        self.show()
        self.raise_()

    def sync_window_visibility(self):
        """Called when 'hide the window when no race runs' is switched on or off."""
        if self.auto_hide_active():
            if self.isVisible() and not self.pinned and not self.racing:
                self.hide()
        elif not self.isVisible() and not self.quitting:
            self.show()
        self.refresh_tray()

    def slide_dir(self):
        """-1 = the tower comes in from the left, +1 = from the right, 0 = no sliding (fade only)."""
        return self.side_for(self.s.get("slide", "auto"))

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                         | QPainter.RenderHint.SmoothPixmapTransform)
        a, s = self.args, self.s
        panel = QColor(s["bg"])
        panel.setAlphaF(float(s["bg_opacity"]))

        if a.chroma:
            p.fillRect(self.rect(), QColor(a.chroma_color))
        elif not a.transparent:
            p.fillRect(self.rect(), QColor(s["bg"]))

        scale = self.width() / self.bw
        p.scale(scale, scale)
        lw = self.bw
        lh = self.height() / scale

        if self.panel_alpha <= 0.01 or not self.horses:
            if not a.chroma and not a.transparent:
                p.setPen(QColor(s["sub_color"]))
                p.setFont(self.fnt(11))
                text = self.status_text
                if self.pinned and self.auto_hide_active():
                    text = ("Placing the overlay: drag to move, pull an edge to resize.\n"
                            "It is hidden when no race runs and slides in when a race starts.\n\n" + text)
                p.drawText(QRectF(8, 8, lw - 16, lh - 16),
                           Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, text)
            p.end()
            return

        d = self.slide_dir()
        if d:
            e = 1.0 - (1.0 - max(0.0, min(1.0, self.slide))) ** 3      # ease out
            p.translate(d * (1.0 - e) * lw, 0)
        p.setOpacity(self.panel_alpha)
        rows = self.visible_rows()
        if a.chroma or a.transparent:
            need_h = self.hh + rows * self.rh + FOOT_PAD
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, lw, min(lh, need_h)), 10, 10)
            p.fillPath(path, panel)

        self.draw_header(p, lw)
        p.save()
        # only the rows that are shown: a uma that drops out of the top N slides out under the clip edge
        p.setClipRect(QRectF(0, self.hh, lw, max(0.0, min(lh - self.hh, rows * self.rh))))
        for h in self.horses:
            self.draw_row(p, h, lw, rows)
        p.restore()
        p.end()

    @staticmethod
    def course_lines(info):
        """('Tokyo · Turf · Mile 1600m', 'Left · Good · Sunny · Spring') from the race's courseInfo."""
        info = info or {}
        dist = " ".join([x for x in (info.get("distType"), ("%sm" % info["distance"]) if info.get("distance") else "") if x])
        line1 = " · ".join([x for x in (info.get("trackName"), info.get("surface"), dist) if x]) or "Race"
        line2 = " · ".join([x for x in (info.get("direction"), info.get("ground"), info.get("weather"), info.get("season")) if x])
        return line1, line2

    def draw_header_compact(self, p, lw):
        """One short header: the place on the left, the race clock on the right."""
        hh = self.hh_base
        tc, sc = self.pick_color("header"), QColor(self.s["sub_color"])
        line1, _line2 = self.course_lines(self.course_info)
        cw = int(lw - 76)
        f1 = self.fnt(11, True)
        p.setFont(f1); p.setPen(tc)
        p.drawText(QRectF(8, 3, cw, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(f1).elidedText(line1, Qt.TextElideMode.ElideRight, cw))
        p.setFont(self.fnt(9, True)); p.setPen(sc)
        p.drawText(QRectF(8, 19, cw, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.terrain_text)
        p.setFont(self.fnt(15, True, mono=True)); p.setPen(tc)
        p.drawText(QRectF(lw - 70, 4, 62, 26), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.clock_text)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawLine(QPointF(0, hh - 1), QPointF(lw, hh - 1))

    def draw_header_clock(self, p, lw):
        """The header with only the race clock (Tower tab, Header)."""
        hh = self.hh_base
        tc = self.pick_color("header")
        p.setFont(self.fnt(15 if self.compact() else 20, True, mono=True)); p.setPen(tc)
        p.drawText(QRectF(8, 0, lw - 16, hh), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   self.clock_text)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawLine(QPointF(0, hh - 1), QPointF(lw, hh - 1))

    def draw_header(self, p, lw):
        mode = self.s.get("tower_header", "both")
        if mode == "none":
            return
        k = self.header_k()                 # "Header size": the header is drawn bigger or smaller as one piece
        p.save()
        p.scale(k, k)
        self._role = "header"
        try:
            self.draw_header_scaled(p, lw / k, mode)
        finally:
            self._role = ""
            p.restore()

    def fit_font(self, font, text, width, lowest=0.6):
        """The same font, made smaller (down to `lowest`) until the text fits the width."""
        f = QFont(font)
        px = f.pixelSize()
        if px <= 0:
            return f
        low = max(5, int(px * lowest))
        while px > low and QFontMetrics(f).horizontalAdvance(text) > width:
            px -= 1
            f.setPixelSize(px)
        return f

    def draw_header_scaled(self, p, lw, mode):
        if mode == "clock":
            return self.draw_header_clock(p, lw)
        if self.compact():
            return self.draw_header_compact(p, lw)
        hh = self.hh_base
        tc, sc = self.pick_color("header"), QColor(self.s["sub_color"])
        line1, line2 = self.course_lines(self.course_info)
        place = self.s.get("header_clock", "auto")
        below = place == "below"
        if place == "auto":                 # the clock goes lower only when the track info cannot fit next to it
            narrow = self.fit_font(self.fnt(12, True), line1, int(lw - 115), 0.75)
            below = QFontMetrics(narrow).horizontalAdvance(line1) > int(lw - 115)

        cw = int(lw - 20) if below else int(lw - 115)   # room left of the clock (all the width when the clock is lower)
        f1, f2 = self.fnt(12, True), self.fnt(10)
        f1, f2 = self.fit_font(f1, line1, cw), self.fit_font(f2, line2, cw)     # a long track name gets smaller, not cut
        p.setFont(f1); p.setPen(tc)
        p.drawText(QRectF(10, 7, cw, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(f1).elidedText(line1, Qt.TextElideMode.ElideRight, cw))
        p.setFont(f2); p.setPen(sc)
        p.drawText(QRectF(10, 23, cw, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(f2).elidedText(line2, Qt.TextElideMode.ElideRight, cw))

        if below:                           # the clock shares the lower line with the terrain text
            p.setFont(self.fnt(18, True, mono=True)); p.setPen(tc)
            p.drawText(QRectF(lw - 100, 40, 90, 24), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.clock_text)
            tw = int(lw - 120)
        else:
            p.setFont(self.fnt(20, True, mono=True)); p.setPen(tc)
            p.drawText(QRectF(lw - 110, 6, 100, 28), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.clock_text)
            tw = int(lw - 20)

        f3 = self.fit_font(self.fnt(10, True), self.terrain_text, tw)
        p.setFont(f3); p.setPen(sc)
        p.drawText(QRectF(10, 44, tw, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(f3).elidedText(self.terrain_text, Qt.TextElideMode.ElideRight, tw))
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawLine(QPointF(0, hh - 1), QPointF(lw, hh - 1))

    def podium(self, i):
        """Colour of place i (0 = first) on the podium, from the Look tab."""
        c = QColor(str(self.s.get("podium_%d" % (i + 1), "")))
        return c if c.isValid() else QColor(PODIUM[i])

    def shape_path(self, rect):
        """The outline of a picture: circle, rounded square or square (Look tab)."""
        path = QPainterPath()
        shape = self.s.get("picture_shape", "circle")
        if shape == "rounded":
            path.addRoundedRect(rect, rect.width() * 0.22, rect.height() * 0.22)
        elif shape == "square":
            path.addRoundedRect(rect, 2, 2)
        else:
            path.addEllipse(rect)
        return path

    def draw_row_base(self, p, h, lw, y):
        """What is behind a row: the podium line (default), a card, or nothing (Look tab, Row style)."""
        style = self.s.get("row_style", "default")
        rh = self.rh
        if style == "cards":
            card = QPainterPath()
            card.addRoundedRect(QRectF(3, y + 2, lw - 6, rh - 4), 9, 9)
            fill = QColor(self.s["text_color"]); fill.setAlpha(18)
            p.fillPath(card, fill)
            if h.rank < 3:
                edge = self.podium(h.rank); edge.setAlpha(150)
                p.setPen(QPen(edge, 1.2)); p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(card)
        elif style != "plain" and h.rank < 3:
            c = self.podium(h.rank); c.setAlpha(110)
            p.setPen(QPen(c, 1))
            p.drawLine(QPointF(0, y + rh - 1), QPointF(lw, y + rh - 1))

    def draw_circle_picture(self, p, rect, pm, letter, color):
        """A picture (circle, rounded square or square; cropped to a square first). Without a picture: a dark
        shape with a letter."""
        circ = self.shape_path(rect)
        p.save()
        p.setClipPath(circ, Qt.ClipOperation.IntersectClip)    # stay inside the clip of the rows
        p.fillPath(circ, QColor("#383858"))
        if pm:
            side = min(pm.width(), pm.height())
            src = QRectF((pm.width() - side) / 2, 0, side, side)
            p.drawPixmap(rect, pm, src)
        elif letter:
            p.setFont(self.fnt(16, True)); p.setPen(color)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, letter)
        p.restore()

    def draw_pictures(self, p, h, rect, tc):
        """The round picture(s) of one uma: the uma, the player, or the uma with a small player badge.
        `rect` is the square for the big picture."""
        mode = self.picture_mode()
        upm, ppm = self.uma_pixmap(h), self.player_pixmap(h)
        big = (ppm or upm) if mode == "player" else upm
        # the circle is always dark, so the fallback letter is always white (not the text colour)
        self.draw_circle_picture(p, rect, big, (h.name[:1] or "?"), QColor("#ffffff"))
        if mode == "both" and ppm:      # small player picture on the corner of the uma picture
            bs = rect.width() / 2.0
            badge = QRectF(rect.right() - bs + 2, rect.bottom() - bs + 3, bs, bs)
            ring = QColor(self.s["bg"])
            p.setPen(QPen(ring, 2))
            p.setBrush(ring)
            p.drawPath(self.shape_path(badge.adjusted(-1.5, -1.5, 1.5, 1.5)))
            self.draw_circle_picture(p, badge, ppm, "", tc)

    def draw_rank_arrow(self, p, h, y):
        """A small green up / red down triangle above / below the rank number; it fades out."""
        if not h.move_dir or not self.s.get("rank_arrows", True):
            return
        age = time.monotonic() - h.move_at
        if age >= ARROW_SECONDS:
            h.move_dir = 0
            return
        solid = ARROW_SECONDS * 0.6
        fade = 1.0 if age < solid else max(0.0, (ARROW_SECONDS - age) / (ARROW_SECONDS - solid))
        col = QColor("#2ecc71" if h.move_dir > 0 else "#e74c3c")
        col.setAlphaF(fade)
        cx = 15.0
        tri = QPainterPath()
        if h.move_dir > 0:
            cy = y + 7
            tri.moveTo(cx, cy - 3.5); tri.lineTo(cx + 4.5, cy + 2.5); tri.lineTo(cx - 4.5, cy + 2.5)
        else:
            cy = y + self.rh - 7
            tri.moveTo(cx, cy + 3.5); tri.lineTo(cx + 4.5, cy - 2.5); tri.lineTo(cx - 4.5, cy - 2.5)
        tri.closeSubpath()
        p.fillPath(tri, col)

    racelog = None
    skill_log = ()

    def save_race_data(self, entries, line1, line2):
        """Keep the results and every skill of this race in race-data.jsonl (Settings > Cup Score > Race data)."""
        try:
            if self.racelog is None:
                self.racelog = RaceLog(os.path.join(_CFG_DIR, "race-data.jsonl"))
            rec = build_record(self.horses, entries, self.course_info, line1, line2, self.skill_log, self.times, self.frames)
            if self.racelog.add(rec):
                logbuf.add("race data saved (%d umas)" % len(rec["runners"]))
        except Exception as e:                      # never let this disturb the race
            logbuf.add("race data not saved: %s" % e)

    sheet_status = ""
    sheet_last = None
    sheet_jobs = ()

    def set_sheet_status(self, text):
        self.sheet_status = "%s  %s" % (time.strftime("%H:%M"), text)
        logbuf.add("Google Sheet: " + text)
        if getattr(self, "dialog", None) is not None:
            try:
                self.dialog.update_sheet_status()
            except Exception:
                pass

    def sheet_send(self, named=None):
        """Send the placings of a race to the Google Sheet (through the owner's Apps Script)."""
        named = named or self.sheet_last
        if not named:
            self.set_sheet_status("No race to send yet.")
            return
        self.sheet_last = named
        try:
            url = sheetwrite.check_url(self.s.get("sheet_write_url", ""))
        except ValueError as e:
            self.set_sheet_status("Not sent: %s" % e)
            return
        payload = sheetwrite.build_payload(self.s.get("sheet_write_secret", ""), self.s.get("sheet_write_round", 1), named)
        job = Job(lambda: sheetwrite.post(url, payload))
        job.done.connect(lambda res: self.set_sheet_status(sheetwrite.describe(res)))
        job.failed.connect(lambda msg: self.set_sheet_status("Not sent: %s" % msg))
        self.sheet_jobs = [j for j in self.sheet_jobs if j.isRunning()] + [job]
        job.start()
        self.set_sheet_status("Sending round %s ..." % payload["round"])

    def display_trainer(self, name):
        """A trainer name as the Look tab wants it: without the club tag, or as his Discord name."""
        shown = strip_club_tag(name) if self.s.get("strip_tags", False) else name
        if self.s.get("name_source") == "discord":              # his Discord name, when the pictures zip had it
            shown = self.players.discord_name_of(name) or shown
        return shown

    def name_parts(self, h):
        """(headline, small line under it) for a row, following the 'Names' choice in the Look tab."""
        mode = self.s.get("names", "both")
        trainer = self.display_trainer(h.trainer)
        club = self.players.club_of(h.trainer) if self.s.get("show_club", False) else ""
        if mode == "trainer" and trainer:
            return trainer, club
        if mode == "uma" or not trainer:
            return h.label, club
        return trainer, " · ".join(x for x in (h.label, club) if x)

    def gap_pair(self, h):
        """The two gap texts of a row, following 'Gap' in the Tower tab."""
        l1, l2 = h.gap_lines
        mode = self.s.get("row_gap", "both")
        if mode == "none":
            return ("", "") if h.gap_kind in ("lead", "box") else (l1, l2)
        if h.gap_kind != "box" or mode == "both":
            return l1, l2
        if mode == "time":
            return l1, ""
        return (l2.split()[-1] if l2 else ""), ""            # "length": the metres only

    def draw_team_stripe(self, p, h, y):
        """A thin stripe in the team colour for the players of a draft team."""
        if not (self.s.get("tower_team_color", True) and self.s.get("match_mode", False)):
            return
        t = self.match.team_of(h.trainer)
        if t is not None:
            p.fillRect(QRectF(0, y + 5, 3, self.rh - 10), QColor(self.match.teams[t]["color"]))

    def draw_row_compact(self, p, h, lw, y):
        """A small row: place, picture, trainer (and uma) on the left, the gap or finish time on the right."""
        tc, sc = self.pick_color("racer"), QColor(self.s["sub_color"])
        rh = self.rh
        self.draw_row_base(p, h, lw, y)
        self.draw_team_stripe(p, h, y)
        p.setFont(self.fnt(15, True))
        p.setPen(self.podium(h.rank) if h.rank < 3 else tc)
        p.drawText(QRectF(2, y, 24, rh), Qt.AlignmentFlag.AlignCenter, str(h.rank + 1))
        self.draw_rank_arrow(p, h, y)
        asz = 24
        self.draw_pictures(p, h, QRectF(28, y + (rh - asz) / 2.0, asz, asz), tc)
        gap_w = 62
        nx = 58
        name_w = int(lw - nx - gap_w - 6)
        head, subline = self.name_parts(h)
        tf = self.fnt(11.5, True)
        p.setFont(tf); p.setPen(tc)
        if subline:
            p.drawText(QRectF(nx, y + 3, name_w, 15), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(tf).elidedText(head, Qt.TextElideMode.ElideRight, name_w))
            nf = self.fnt(8.5)
            p.setFont(nf); p.setPen(sc)
            p.drawText(QRectF(nx, y + 18, name_w, 13), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(nf).elidedText(subline, Qt.TextElideMode.ElideRight, name_w))
        else:                                   # one name only: centred in the row
            p.drawText(QRectF(nx, y, name_w, rh), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(tf).elidedText(head, Qt.TextElideMode.ElideRight, name_w))
        l1 = self.gap_pair(h)[0]
        if h.gap_kind == "lead":
            p.setFont(self.fnt(10.5, True)); p.setPen(QColor("#d4a017"))
        elif h.gap_kind == "done":
            p.setFont(self.fnt(11.5, True)); p.setPen(tc)
        else:
            p.setFont(self.fnt(10.5, True)); p.setPen(tc)
        p.drawText(QRectF(lw - gap_w - 4, y, gap_w, rh), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, l1)

    def draw_row(self, p, h, lw, rows=None):
        self._role = "row"
        try:
            self.draw_row_inner(p, h, lw, rows)
        finally:
            self._role = ""

    def draw_row_inner(self, p, h, lw, rows=None):
        tc, sc = self.pick_color("racer"), QColor(self.s["sub_color"])
        if h.hidden:
            return
        y = self.hh + (h.y if h.y is not None else h.target)
        limit = self.hh + (rows if rows is not None else len(self.horses)) * self.rh
        if y >= limit or y > self.height() / (self.width() / self.bw) + self.rh:
            return
        if self.compact():
            return self.draw_row_compact(p, h, lw, y)
        self.draw_row_base(p, h, lw, y)

        self.draw_team_stripe(p, h, y)
        # rank
        p.setFont(self.fnt(17, True))
        p.setPen(self.podium(h.rank) if h.rank < 3 else tc)
        p.drawText(QRectF(2, y, 26, self.rh), Qt.AlignmentFlag.AlignCenter, str(h.rank + 1))
        self.draw_rank_arrow(p, h, y)

        # pictures: the uma and the player are two separate pictures
        ax, ay, asz = 30, y + 7, 34
        self.draw_pictures(p, h, QRectF(ax, ay, asz, asz), tc)

        # gate badge, style badge, then the names (the badges can be switched off in the Tower tab)
        x = 69
        if self.s.get("row_gate", True):
            gi = max(0, min(7, (h.gate or 1) - 1))
            gx, gy, gs = x, y + 16, 16
            gp = QPainterPath(); gp.addRoundedRect(QRectF(gx, gy, gs, gs), 4, 4)
            p.fillPath(gp, QColor(WAKU_COLORS[gi]))
            gf = QFont(); gf.setPixelSize(9 if h.id >= 10 else 10); gf.setBold(True)
            p.setFont(gf)
            p.setPen(QColor("#794016") if gi in WAKU_DARK else QColor("#ffffff"))
            p.drawText(QRectF(gx, gy, gs, gs), Qt.AlignmentFlag.AlignCenter, str(h.id))
            x += 22
        sub_x = x
        head, subline = self.name_parts(h)
        if self.s.get("row_style", True):
            # With two lines the badge sits level with the first line; with one name only (centred in the
            # row) the badge is centred in the row too.
            by = y + 9 if subline else y + (self.rh - 14) / 2.0
            bp = QPainterPath(); bp.addRoundedRect(QRectF(x, by, 14, 14), 3, 3)
            p.fillPath(bp, QColor(STYLE_COLOR.get(h.style, "#383858")))
            bf = QFont(); bf.setPixelSize(10); bf.setBold(True)
            p.setFont(bf); p.setPen(QColor("#1a1a28"))
            p.drawText(QRectF(x, by, 14, 14), Qt.AlignmentFlag.AlignCenter, STYLE_LABEL.get(h.style, "?"))
            x += 18
        name_x = x
        name_w = 100 + (109 - name_x) + (70 if self.s.get("row_gap", "both") == "none" else 0)
        tf = self.fnt(12, True)
        p.setFont(tf); p.setPen(tc)
        if not subline:                         # one name only: centred in the row, a little wider
            p.drawText(QRectF(name_x, y, name_w + 14, self.rh), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(tf).elidedText(head, Qt.TextElideMode.ElideRight, name_w + 14))
        else:
            p.drawText(QRectF(name_x, y + 8, name_w, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(tf).elidedText(head, Qt.TextElideMode.ElideRight, name_w))
            # uma name: "Meisho Doto", or "Meisho Doto (Halloween)" for an alternative outfit.
            # A long name is made a little smaller first, and only cut off when it still does not fit.
            full_w = name_w + (name_x - sub_x)
            nf = self.fnt(10)
            for px in (9.0, 8.0):
                if QFontMetrics(nf).horizontalAdvance(subline) <= full_w:
                    break
                nf = self.fnt(px)
            p.setFont(nf); p.setPen(sc)
            p.drawText(QRectF(sub_x, y + 25, full_w, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(nf).elidedText(subline, Qt.TextElideMode.ElideRight, full_w))

        # gap
        l1, l2 = self.gap_pair(h)
        if h.gap_kind == "lead":
            p.setFont(self.fnt(11, True)); p.setPen(QColor("#d4a017"))
            p.drawText(QRectF(lw - 92, y, 86, self.rh), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, l1)
        elif h.gap_kind == "done":
            p.setFont(self.fnt(13, True)); p.setPen(tc)
            p.drawText(QRectF(lw - 92, y, 86, self.rh), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, l1)
        elif h.gap_kind == "box":
            p.setFont(self.fnt(11, True)); p.setPen(tc)
            if l1 and l2:
                p.drawText(QRectF(lw - 120, y + 8, 114, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, l1)
                p.setFont(self.fnt(10)); p.setPen(sc)
                p.drawText(QRectF(lw - 120, y + 25, 114, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, l2)
            elif l1:                            # one gap only: centred in the row
                p.drawText(QRectF(lw - 120, y, 114, self.rh), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, l1)

    # ----- tray icon, show/hide, quit ------------------------------------------
    def set_overlay_visible(self, on):
        on = bool(on)
        if self.auto_hide_active():
            self.pinned = on         # placing the window: not remembered, next start it is hidden again
        else:
            self.s["show_overlay"] = on
            self.save_settings()
        if on:
            self.show()
            self.raise_()
        elif not (self.auto_hide_active() and self.racing):
            self.hide()              # during a race it goes away by itself when the race is over
        self.refresh_tray()

    def setup_tray(self, force=False):
        if not force and not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        icon_path = os.path.join(SCRIPT_DIR, "icon.png")
        self.base_pix = QPixmap(icon_path) if os.path.isfile(icon_path) else None
        self.tray = QSystemTrayIcon(self)
        self._tray_sig = None
        m = QMenu()
        self.menu = m
        self.act_status = m.addAction("Starting...")
        self.act_status.setEnabled(False)
        m.addSeparator()
        self.act_show = m.addAction("Show overlay window", lambda: self.set_overlay_visible(not self.window_wanted()))
        m.addAction("Menu / Settings...", self.open_settings)
        self.act_board = m.addAction("Show results board (to place it)", lambda: self.set_board_pinned(not self.board.pinned))
        self.act_stand = m.addAction("Show standings board (to place it)",
                                     lambda: self.set_standings_pinned(not self.standings.pinned))
        m.addAction("Show / hide the standings now", self.show_standings_now)
        self.act_luck = m.addAction("Show skill luck board (to place it)",
                                    lambda: self.set_luck_pinned(not self.luck.pinned))
        self.act_match = m.addAction("Show match board (to place it)",
                                     lambda: self.set_match_pinned(not self.mboard.pinned))
        m.addAction("Replay a saved race (test)...", self.test_replay)
        self.act_compact = m.addAction("Small corner tower (top 5 only)")
        self.act_compact.setCheckable(True)
        self.act_compact.triggered.connect(lambda on: self.set_setting("tower_style", "compact" if on else "full"))
        self.act_prev = m.addAction("Show preview race")
        self.act_prev.setCheckable(True)
        self.act_prev.triggered.connect(lambda on: self.set_preview(on))
        self.pic_actions = self.add_pictures_menu(m)
        self.view_menu_actions = self.add_view_menu(m)
        self.act_top = m.addAction("Always on top")
        self.act_top.setCheckable(True)
        self.act_top.triggered.connect(lambda on: self.set_setting("on_top", on))
        m.addSeparator()
        m.addAction("Open uma faces folder", lambda: open_folder(self.thumbs.uma))
        m.addAction("Open player pictures folder", lambda: open_folder(self.thumbs.players))
        m.addSeparator()
        m.addAction("Quit", self.quit_app)
        m.aboutToShow.connect(self.sync_tray_menu)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(self.on_tray_click)
        self.tray_active = True
        self.refresh_tray()
        self.tray.show()
        self._tray_timer = QTimer(self)
        self._tray_timer.timeout.connect(self.refresh_tray)
        self._tray_timer.start(1000)
        return True

    def on_tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.open_settings()

    def sync_tray_menu(self):
        self.act_show.setText("Hide overlay window" if self.window_wanted() else "Show overlay window")
        self.act_board.setText("Hide results board" if self.board.pinned else "Show results board (to place it)")
        self.act_stand.setText("Hide standings board" if self.standings.pinned else "Show standings board (to place it)")
        self.act_luck.setText("Hide skill luck board" if self.luck.pinned else "Show skill luck board (to place it)")
        self.act_match.setText("Hide match board" if self.mboard.pinned else "Show match board (to place it)")
        self.act_prev.setChecked(self.preview)
        self.act_compact.setChecked(self.compact())
        for mode, act in self.pic_actions.items():
            act.setChecked(mode == self.picture_mode())
        for key, act in self.view_menu_actions.items():
            act.setChecked(key == self.s.get("standings_view", "plain"))
        self.act_top.setChecked(bool(self.s.get("on_top", True)))

    def status_summary(self):
        if self.racing:
            return "Race in progress"
        return (self.status_text or "").split("\n")[0]

    def refresh_tray(self):
        if not self.tray_active:
            return
        color = "#3498db" if self.racing else STATE_COLORS.get(self.state, "#f1c40f")
        text = self.status_summary()
        sig = (color, text)
        if sig == self._tray_sig:
            return
        self._tray_sig = sig
        self.tray.setIcon(make_tray_icon(self.base_pix, color))
        self.tray.setToolTip(APP_NAME + " - " + text)
        self.act_status.setText("Status: " + text)

    def restart_now(self):
        self.quitting = True
        if self.isVisible():
            g = self.geometry()
            self.cfg["geometry"] = [g.x(), g.y(), g.width(), g.height()]
        if self.board.isVisible() or self.board.entries:
            self.board.remember()
        if self.standings.isVisible() or self.standings.entries:
            self.standings.remember()
        if self.luck.isVisible() or self.luck.entries:
            self.luck.remember()
        if self.mboard.isVisible() or self.mboard.entries:
            self.mboard.remember()
        save_config(self.cfg)
        try:
            self.source.stop()
        except Exception:
            pass
        if self.tray is not None:
            self.tray.hide()
        restart_program()

    def quit_app(self):
        if self.quitting:
            return
        self.quitting = True
        if self.isVisible():
            g = self.geometry()
            self.cfg["geometry"] = [g.x(), g.y(), g.width(), g.height()]
        if self.board.isVisible() or self.board.entries:
            self.board.remember()
        if self.standings.isVisible() or self.standings.entries:
            self.standings.remember()
        if self.luck.isVisible() or self.luck.entries:
            self.luck.remember()
        if self.mboard.isVisible() or self.mboard.entries:
            self.mboard.remember()
        save_config(self.cfg)
        try:
            self.source.stop()
        except Exception:
            pass
        if self.test_thread is not None:
            self.test_thread.stop()
        if self.dialog is not None:
            self.dialog.close()
        if self.tray is not None:
            self.tray.hide()
        self.board.close()
        self.standings.close()
        self.luck.close()
        self.mboard.close()
        if self.s.get("stop_server", True):
            stop_started_server()
        self.close()
        QApplication.instance().quit()

    # ----- settings helpers ----------------------------------------------------
    def save_settings(self):
        self.cfg["settings"] = dict(self.s)
        save_config(self.cfg)

    PICTURE_CHOICES = (("both", "Uma image + player picture"), ("uma", "Uma image only"),
                       ("player", "Player picture (uma image if none)"))

    def add_pictures_menu(self, menu):
        """A 'Pictures' submenu with three exclusive choices. Returns {mode: action}."""
        from PyQt6.QtGui import QActionGroup
        sub = menu.addMenu("Pictures")
        group = QActionGroup(sub)
        group.setExclusive(True)
        acts = {}
        for mode, text in self.PICTURE_CHOICES:
            a = sub.addAction(text)
            a.setCheckable(True)
            a.setChecked(mode == self.picture_mode())
            group.addAction(a)
            a.triggered.connect(lambda _=False, md=mode: self.set_setting("pictures", md))
            acts[mode] = a
        return acts

    def add_view_menu(self, menu):
        """'Standings view' submenu: Round 1, Round 2, Round 3, 1 + 2, 1 + 2 + 3. Returns {view: action}."""
        from PyQt6.QtGui import QActionGroup
        from .sheets import VIEWS
        sub = menu.addMenu("Standings view (sheet)")
        group = QActionGroup(sub)
        group.setExclusive(True)
        acts = {}
        for key, text in VIEWS:
            a = sub.addAction(text)
            a.setCheckable(True)
            a.setChecked(key == self.s.get("standings_view", "plain"))
            group.addAction(a)
            a.triggered.connect(lambda _=False, k=key: self.set_standings_view(k))
            acts[key] = a
        return acts

    def set_standings_view(self, key):
        self.set_setting("standings_view", key)
        if self.s.get("standings_mode") != "sheet":
            self.set_setting("standings_mode", "sheet")
        self.standings.refresh(True)      # reads the table this view needs (a cached one is used at once)
        self.standings.apply_raw()

    def cycle_pictures(self):
        order = [m for m, _ in self.PICTURE_CHOICES]
        self.set_setting("pictures", order[(order.index(self.picture_mode()) + 1) % len(order)])

    def set_setting(self, key, value):
        self.s[key] = value
        self.save_settings()
        if key in ("on_top", "title_bar"):
            self.apply_flags()
            self.board.apply_flags()
            self.standings.apply_flags()
        if key in ("standings_layout", "standings_rows", "standings_avatars"):
            self.standings.relayout()
        if key in ("tower_style", "compact_rows"):
            self.fit_to_rows()
            if key == "tower_style":
                self.refit_rows_now()
        if key in ("max_rows", "tower_header", "players_only", "header_scale"):
            self.fit_to_rows()
        if key == "start_delay" and getattr(self, "source", None) is not None:
            self.source.delay = float(value)
        if key == "auto_hide":
            self.sync_window_visibility()
        self.board.update()
        self.standings.update()
        self.update()

    def apply_theme(self, name):
        """Apply one of the colour sets from THEME_PRESETS."""
        preset = THEME_PRESETS.get(name)
        if not preset:
            return
        self.s.update(preset)
        self.save_settings()
        self.board.update()
        self.update()

    def apply_flags(self):
        was_visible = self.isVisible()
        geo = self.geometry()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(self.s.get("on_top", True)))
        frameless = bool(self.args.frameless or self.args.transparent or not self.s.get("title_bar", False))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, frameless)
        if was_visible:
            self.show()  # changing window flags hides the window, so show it again
        self.setGeometry(geo)

    def apply_source_choice(self):
        """Use the source / saved-races folder chosen in Settings.
        Returns True when it is active now, False when the program has to restart first."""
        kind, folder = choose_source(self.args, self.s, self.cfg)
        if kind == "watch" and self.source_kind == "watch" and isinstance(self.source, WatchThread):
            self.source.set_folder(folder, bool(self.s.get("watch_subfolders", True)))
            if folder:
                self.cfg["watch_dir"] = folder
                save_config(self.cfg)
            return True
        return kind == self.source_kind

    def reset_settings(self):
        keep ={k: self.s.get(k, DEFAULT_SETTINGS[k]) for k in KEEP_ON_RESET}
        self.s = dict(DEFAULT_SETTINGS)
        self.s.update(keep)          # only the look is reset, not your folder / source / update link
        self.save_settings()
        self.apply_flags()
        self.board.apply_flags()
        self.fit_to_rows()
        self.board.update()
        self.update()

    def apply_setup(self, key, tower_style=None, rebuild=True):
        """A ready-made setup (see setups.py): switches the right boards on and the others off."""
        st = get_setup(key)
        if st is None:
            return
        for k, v in st["settings"].items():
            self.set_setting(k, v)
        if tower_style in ("full", "compact"):
            self.set_setting("tower_style", tower_style)
        self.standings.refresh(True)
        if rebuild:
            QTimer.singleShot(0, lambda: self.rebuild_settings(st.get("tab") if st.get("tab") in ("Draft", "Cup Score") else None))

    def rebuild_settings(self, tab=None):
        """Open the settings window again from scratch, so every checkbox shows the new values."""
        old = getattr(self, "dialog", None)
        was_open = old is not None and old.isVisible()
        keep = old._tabs.currentIndex() if old is not None else 0
        if old is not None:
            old.close()
            old.deleteLater()
            self.dialog = None
        self.open_settings()
        if tab:
            self.dialog.show_tab(tab)
        elif was_open:
            self.dialog._tabs.setCurrentIndex(keep)

    def show_welcome(self):
        from .welcome import WelcomeDialog
        self.welcome = WelcomeDialog(self)
        self.welcome.show()
        self.welcome.raise_()
        self.welcome.activateWindow()

    def open_settings(self):
        if getattr(self, "dialog", None) is None:
            self.dialog = SettingsDialog(self)
        self.dialog.refresh_players()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    # ----- player pictures -----------------------------------------------------
    def refresh_player_images(self):
        for k in [k for k in self.pix if k.startswith("p:")]:
            self.pix.pop(k, None)
            self.pix_pending.discard(k)
        for h in self.horses:
            if h.pkey:
                self.want_img(h.pkey, {"kind": "player", "trainer": h.trainer})
        self.update()

    def set_player_image_file(self, trainer, src_path):
        import shutil
        safe = "".join(c if c not in '/\\:*?"<>|' else "_" for c in trainer).strip() or "player"
        ext = os.path.splitext(src_path)[1].lower() or ".png"
        for old in os.listdir(self.thumbs.players):      # drop an older picture with another extension
            b, e = os.path.splitext(old)
            if b.lower() == safe.lower() and e.lower() in IMG_EXTS:
                try:
                    os.remove(os.path.join(self.thumbs.players, old))
                except OSError:
                    pass
        dest = os.path.join(self.thumbs.players, safe + ext)
        shutil.copyfile(src_path, dest)
        self.players.set_image(trainer, "players/" + safe + ext)
        self.refresh_player_images()

    def set_player_image_url(self, trainer, url):
        self.players.set_image(trainer, url)
        self.refresh_player_images()

    def clear_player_image(self, trainer):
        self.players.set_image(trainer, "")
        self.refresh_player_images()

    # ----- uma pictures --------------------------------------------------------
    def refresh_uma_images(self):
        for k in [k for k in self.pix if k.startswith("c:")]:
            self.pix.pop(k, None)
            self.pix_pending.discard(k)
        for h in self.horses:
            for key, card in ((h.ukey, h.card_id), (h.bkey, h.chara_id * 100 + 1)):
                if key:
                    self.want_img(key, {"kind": "uma", "card_id": card, "chara_id": h.chara_id, "name": h.name})
        self.update()

    def uma_own_picture(self, card_id):
        """Path of the picture you chose for this uma (images/uma/<card id>.png), or None."""
        return find_file_ci(self.thumbs.uma, str(int(card_id)))

    def set_uma_image_file(self, card_id, src_path):
        import shutil
        self.clear_uma_image(card_id, refresh=False)
        ext = os.path.splitext(src_path)[1].lower()
        if ext not in IMG_EXTS:
            ext = ".png"
        shutil.copyfile(src_path, os.path.join(self.thumbs.uma, "%d%s" % (int(card_id), ext)))
        self.refresh_uma_images()

    def clear_uma_image(self, card_id, refresh=True):
        """Back to the default face (your picture file is deleted)."""
        while True:
            path = self.uma_own_picture(card_id)
            if not path:
                break
            try:
                os.remove(path)
            except OSError:
                break
        if refresh:
            self.refresh_uma_images()

    def set_default_faces(self, on):
        self.thumbs.use_default = bool(on)
        self.set_setting("default_faces", bool(on))
        self.refresh_uma_images()

    # ----- preview -------------------------------------------------------------
    def build_preview_race(self):
        """A made-up 8 uma race. Returns (sim, payload, rmap, finish_times)."""
        import math
        import random
        rnd = random.Random(7)
        umas = [("Special Week", 1001), ("Silence Suzuka", 1002), ("Tokai Teio", 1003), ("Maruzensky", 1004),
                ("Taiki Shuttle", 1005), ("Oguri Cap", 1006), ("Gold Ship", 1007), ("Vodka", 1008)]
        names = list(self.players.names())[:len(umas)]
        names += ["Player %d" % (i + 1) for i in range(len(names), len(umas))]
        total = 1600.0
        speeds = [40.5 + rnd.random() * 3.5 for _ in umas]
        times = [i * 0.5 for i in range(0, 110)]
        frames = []
        for t in times:
            frames.append([(min(total, max(0.0, sp * t + 3 * math.sin(t * 0.6 + i))), 0)
                           for i, sp in enumerate(speeds)])
        fins = [total / sp for sp in speeds]
        order = sorted(range(len(fins)), key=lambda i: fins[i])
        results = [{"finishOrder": order.index(i), "finishTime": fins[i],
                    "finishDiffTime": 0.0, "finishTimeRaw": fins[i]} for i in range(len(umas))]
        runners, rmap = [], {}
        for i, (u, cid) in enumerate(umas):
            runners.append({"name": u, "trainer": names[i], "style": 1 + i % 4, "gate": i + 1,
                            "frameOrder": i + 1, "charaId": cid, "dressId": 0})
            rmap[i + 1] = {"fo": i + 1, "chara_id": cid, "card_id": cid * 100 + 1}
        payload = {"runners": runners, "courseShape": {"distance": 1600}, "courseData": {"distance": 1600},
                   "courseInfo": {"trackName": "Preview", "surface": "Turf", "distType": "Mile", "distance": 1600,
                                  "direction": "Left", "ground": "Good", "weather": "Sunny", "season": "Spring"}}
        return {"times": times, "frames": frames, "results": results}, payload, rmap, fins

    def set_preview(self, on):
        if not on:
            if self.preview:
                self.preview = False
                self.racing = False
                self.horses, self.frames, self.times, self.results = [], [], [], []
                self.update()
            return
        if self.clock_active or (self.racing and not self.preview):
            return  # a real race is running - do not disturb it
        sim, payload, rmap, fins = self.build_preview_race()
        self.hide_deadline = None
        self.setup_race(sim, payload, rmap)
        self.preview = True
        self.preview_start = time.monotonic()
        self.preview_len = max(fins) + 4.0
        self.racing = True

    # ----- results board ---------------------------------------------------------------
    def on_race_finished(self):
        """The race is over and every uma has its final place: score it, queue the results board and
        then the standings board."""
        if self.board_done or not self.horses:
            return
        self.board_done = True
        entries = self.results_entries()
        line1, _line2 = self.course_lines(self.course_info)
        testing = self.test_thread is not None and self.test_thread.isRunning()
        counts = (not self.preview) and (not testing) and bool(getattr(self.source, "counts", True))
        match_on = bool(self.s.get("match_mode", False)) and counts
        scoring = bool(self.s.get("scoring", True)) and counts and not match_on
        if counts and self.s.get("race_data", True):
            self.save_race_data(entries, line1, _line2)
        if match_on:
            self.score_match(entries, line1)
        elif self.match.races or self.s.get("match_mode", False) or any(t["players"] for t in self.match.teams):
            if not self.s.get("match_mode", False):
                self.set_match_note("NOT counted: Team match mode is OFF (tick it in the Draft tab).")
            elif self.preview or testing:
                self.set_match_note("NOT counted: this was a preview or a test replay.")
            else:
                self.set_match_note("NOT counted: this race came from a saved file that was already there when "
                                    "the program started. Only races that happen after the start count.")
        if scoring:
            named = [e for e in entries if e["h"].trainer.strip()]
            for e in named:
                e["pts"] = points_for(e["place"], len(named))
            if len(named) >= 2:
                self.sheet_last = [{"name": e["h"].trainer, "place": e["place"]} for e in named]
                if self.s.get("sheet_write_auto", False) and self.s.get("sheet_write_url"):
                    self.sheet_send()
                self.book.add_race([{"name": e["h"].trainer, "uma": e["h"].label, "place": e["place"],
                                     "time": e["time"]} for e in named], title=line1)
        # the board comes in as the tower goes out, so the two are never both full-size at the same time
        delay = 1.0 if self.args.hold else max(0.5, float(self.args.hide_after))
        delay += max(0.0, float(self.s.get("results_delay", 0.0) or 0.0))
        shown = bool(self.s.get("results_board", True))
        if shown:
            self.board.present(entries, line1, delay)
        # When does each other board come in? "after": once the board before it has gone (one at a time).
        # "with": together with the results board. Either way plus its own extra seconds.
        cursor = delay + (float(self.s.get("results_seconds", 10.0)) + SLIDE_SECONDS + 0.2 if shown else 0.0)
        blocked = shown and self.board.hold_forever()         # the results board never leaves: nothing can follow it

        def slot(key):
            """Seconds from now until the board comes in, or None when it cannot (it would wait for ever)."""
            extra = max(0.0, float(self.s.get(key + "_delay", 0.0) or 0.0))
            if self.s.get(key + "_when", "after") == "with":
                return delay + extra
            return None if blocked else cursor + extra

        def follow(key, at, board):
            """A board that came in 'after' holds the line for the next one until it has gone again."""
            nonlocal cursor, blocked
            if self.s.get(key + "_when", "after") == "with":
                return
            if board.hold_forever():
                blocked = True
            else:
                cursor = at + board.stay() + SLIDE_SECONDS + 0.2

        if self.s.get("luck_board", False) and not self.args.hold:
            luck_entries, luck_footer = self.luck_entries()
            at = slot("luck")
            if luck_entries and at is not None:
                self.luck.present(luck_entries, luck_footer, at)
                follow("luck", at, self.luck)
        if match_on and self.s.get("match_board", True) and not self.args.hold:
            at = slot("match")
            if at is not None:
                self.mboard.present([{"match": self.match}], self.mboard.footer_text(), at)
        if self.s.get("standings_board", True) and counts and not self.args.hold and not match_on:
            every = int(self.s.get("standings_every", 1) or 0)        # 0 = only when you show it yourself
            done = int(self.cfg.get("races_since_standings", 0)) + 1
            due = every > 0 and done >= every
            self.cfg["races_since_standings"] = 0 if due else done
            save_config(self.cfg)
            at = slot("standings")
            if due and at is not None:
                self.standings.present(delay=at)

    def set_match_note(self, text):
        """Why the last race did or did not score, shown in the Draft tab."""
        self.match_note = "%s  %s" % (time.strftime("%H:%M"), text)
        logbuf.add("match: " + text)
        if getattr(self, "dialog", None) is not None:
            try:
                self.dialog.update_match_label()
            except Exception:
                pass

    def score_match(self, entries, title):
        """Give the race to the teams: the best placed team players score (4, 2, 1 ...). Players that are on
        no team (NPCs, other players) are skipped, so the next team player takes the placement."""
        named = [{"name": e["h"].trainer, "uma": e["h"].label, "place": e["place"], "time": e["time"]}
                 for e in entries if e["h"].trainer.strip()]
        race = self.match.add_race(named, title=title)
        if race:
            ta, tb = race["delta"]
            self.set_match_note("Counted: %s +%d, %s +%d." % (self.match.teams[0]["name"], ta,
                                                             self.match.teams[1]["name"], tb))
        elif not self.match.ready():
            self.set_match_note("NOT counted: add at least one player to each team (Draft tab).")
        elif not any(self.match.team_of(n["name"]) is not None for n in named):
            self.set_match_note("NOT counted: nobody in this race is on a team. Names in the race: %s. "
                                "Check how the players are spelled in the Draft tab."
                                % ", ".join(n["name"] for n in named[:12]))
        else:
            self.set_match_note("NOT counted again: this race was already scored.")
        scored = {}
        if race:
            scored = {norm_name(r["name"]): r for r in race["results"]}
        for e in entries:
            k = norm_name(e["h"].trainer)
            team = self.match.team_of(e["h"].trainer)
            if team is None:
                continue
            e["team_color"] = self.match.teams[team]["color"]
            r = scored.get(k)
            e["pts"] = "+%d" % r["points"] if r and r["points"] else "0"
        for e in entries:
            if "pts" not in e:
                e["pts"] = "-"                   # not on a team: no points
        self.mboard.refresh()

    def luck_entries(self):
        """(entries, footer) for the skill luck board of the race that just ran; ([], "") without skill data."""
        if not self.skill_acts:
            return [], ""
        rows = luck_table(self.horses, self.skill_acts)
        lucky, unlucky, all_hit = pick(rows, int(self.s.get("luck_rows", 3) or 3))
        out = []
        for place, r in enumerate(lucky, 1):
            out.append(dict(r, side="lucky", place=place))
        for place, r in enumerate(unlucky, 1):
            out.append(dict(r, side="unlucky", place=place))
        if all_hit:
            footer = "Hit every skill: " + ", ".join(all_hit[:3]) + (" +%d" % (len(all_hit) - 3) if len(all_hit) > 3 else "")
        else:
            known = any(r["total"] for r in rows)
            footer = "Skills that activated, out of the skills equipped" if known else "Skills that activated"
        return out, footer

    def sample_luck(self):
        """Made-up luck, to place and style the board before any race has been run."""
        sim, payload, rmap, _fins = self.build_preview_race()
        horses = self.build_horses(payload, rmap)
        rows = [{"h": h, "hit": 15 - 2 * i if i < 3 else 2 + i, "total": 15, "missed": 0}
                for i, h in enumerate(horses)]
        for r in rows:
            r["missed"] = r["total"] - r["hit"]
        lucky, unlucky, _all = pick(rows, int(self.s.get("luck_rows", 3) or 3))
        out = [dict(r, side="lucky", place=i) for i, r in enumerate(lucky, 1)]
        out += [dict(r, side="unlucky", place=i) for i, r in enumerate(unlucky, 1)]
        return out, "Skills that activated, out of the skills equipped"

    def sample_match(self):
        return [{"match": Match.sample()}], "First to 25 points"

    def set_match_pinned(self, on):
        """Show the match board so it can be placed: the real match when there is one, else a made-up one."""
        if on:
            real = bool(self.match.race_rows()) or any(t["players"] for t in self.match.teams)
            entries, footer = ([{"match": self.match}], "") if real else self.sample_match()
            self.mboard.set_data(entries, footer)
        self.mboard.set_pinned(on)
        self.refresh_tray()

    def set_luck_pinned(self, on):
        self.luck.set_pinned(on, self.sample_luck() if on and not self.luck.entries else None)
        self.refresh_tray()

    def results_entries(self):
        """Final placings, best first: place (ties share one), finish time and the gap to the winner."""
        out, win_t, prev_t, place = [], None, None, 0
        for i, h in enumerate(sorted(self.horses, key=lambda x: x.rank)):
            res = self.results[h.frame_idx] if h.frame_idx < len(self.results) else None
            t = float(res["finishTimeRaw"]) if res and res["finishTimeRaw"] > 0 else 0.0
            if t > 0 and prev_t is not None and abs(t - prev_t) < 0.0005:
                pass                                   # a tie: same place as the uma before
            else:
                place = i + 1
            if t > 0:
                if win_t is None:
                    win_t = t
                gap = "Winner" if t == win_t and place == 1 else "+%.3f" % (t - win_t)
            else:
                gap = ""
            out.append({"h": h, "place": place, "time": fmt_time(t) if t > 0 else "--", "gap": gap})
            prev_t = t if t > 0 else prev_t
        return out

    def sample_results(self):
        """Made-up placings, to place and style the board before any race has been run."""
        sim, payload, rmap, fins = self.build_preview_race()
        horses = self.build_horses(payload, rmap)
        order = sorted(range(len(horses)), key=lambda i: fins[i])
        out = []
        for place, i in enumerate(order, 1):
            out.append({"h": horses[i], "place": place, "time": fmt_time(fins[i]),
                        "gap": "Winner" if place == 1 else "+%.3f" % (fins[i] - fins[order[0]])})
        return out, self.course_lines(payload["courseInfo"])[0]

    def test_replay(self, path=None):
        """Play one saved race file (no game, no server) to see the tower, results and standings."""
        from PyQt6.QtWidgets import QFileDialog
        if self.clock_active or (self.racing and not self.preview):
            return                                    # a real race is running - do not disturb it
        if not path:
            start = self.s.get("saved_races_dir") or self.cfg.get("watch_dir") or os.path.expanduser("~")
            path, _ = QFileDialog.getOpenFileName(None, "Choose a saved race file", start,
                                                  "Race files (*.json);;All files (*)")
        if not path:
            return
        if self.preview:
            self.set_preview(False)
        if self.test_thread is not None and self.test_thread.isRunning():
            self.test_thread.stop()
            self.test_thread.wait(2000)
        t = TestReplayThread(path)
        t.race.connect(self.on_race)
        t.clock.connect(self.on_clock)
        t.error.connect(lambda msg: logbuf.add(msg))
        self.test_thread = t
        t.start()
        logbuf.add("test replay: " + os.path.basename(path))

    def show_standings_now(self):
        """Show (or hide) the standings board by hand, whatever the 'every N races' setting says."""
        if self.standings.isVisible() and self.standings.want > 0 and not self.standings.pinned:
            self.standings.hide_now()
        else:
            self.standings.show_now()
        self.cfg["races_since_standings"] = 0

    def sample_standings(self):
        """Made-up scores, to place and style the standings board before any race has been run."""
        names = ["Trainer %s" % c for c in "ABCDEFGHIJK"]
        return [{"name": n, "uma": "", "score": 11 - i, "last": 0} for i, n in enumerate(names)]

    def set_standings_pinned(self, on):
        self.standings.set_pinned(on, self.sample_standings())

    def set_board_pinned(self, on):
        """'Show results board': keep it on screen to place it. Shows sample placings if no race ran yet."""
        self.board.set_pinned(on, self.sample_results() if on and not self.board.entries else None)
        self.refresh_tray()

    # ----- menu / keyboard --------------------------------------------------------------
    def contextMenuEvent(self, ev):
        m = QMenu(self)
        m.addAction("Settings...", self.open_settings)
        self.add_pictures_menu(m)
        a4 = m.addAction("Show window title bar")
        a4.setCheckable(True)
        a4.setChecked(bool(self.s.get("title_bar", False)))
        a4.toggled.connect(lambda on: self.set_setting("title_bar", on))
        a2 = m.addAction("Always on top")
        a2.setCheckable(True)
        a2.setChecked(bool(self.s.get("on_top", True)))
        a2.toggled.connect(lambda on: self.set_setting("on_top", on))
        a5 = m.addAction("Small corner tower (top 5 only)")
        a5.setCheckable(True)
        a5.setChecked(self.compact())
        a5.toggled.connect(lambda on: self.set_setting("tower_style", "compact" if on else "full"))
        a3 = m.addAction("Show preview race")
        a3.setCheckable(True)
        a3.setChecked(self.preview)
        a3.toggled.connect(self.set_preview)
        m.addAction("Show results board (to place it)" if not self.board.pinned else "Hide results board",
                    lambda: self.set_board_pinned(not self.board.pinned))
        m.addAction("Show standings board (to place it)" if not self.standings.pinned else "Hide standings board",
                    lambda: self.set_standings_pinned(not self.standings.pinned))
        self.add_view_menu(m)
        m.addSeparator()
        if self.tray_active:
            m.addAction("Hide overlay window", lambda: self.set_overlay_visible(False))
        m.addAction("Quit", self.quit_app)
        m.exec(ev.globalPos())

    def keyPressEvent(self, ev):
        k = ev.key()
        if k == Qt.Key.Key_Escape:
            if self.tray_active:
                self.set_overlay_visible(False)
            else:
                self.quit_app()
        elif k == Qt.Key.Key_S:
            self.open_settings()
        elif k == Qt.Key.Key_T:   # quick switch: both -> uma only -> player picture
            self.cycle_pictures()
        elif k in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            # watch/demo mode only. Right/Up = race runs ahead, Left/Down = later.
            # Left/Right = 0.25 s per press, Up/Down = 1 s per press
            step = {Qt.Key.Key_Right: 0.25, Qt.Key.Key_Left: -0.25,
                    Qt.Key.Key_Up: 1.0, Qt.Key.Key_Down: -1.0}[k]
            src = getattr(self, "source", None)
            if src is not None:
                src.offset += step
                self.cfg["sync_offset"] = round(src.offset, 2)
                save_config(self.cfg)
                print("sync offset: %+.2f s" % src.offset)

    def closeEvent(self, ev):
        if self.tray_active and not self.quitting:
            self.set_overlay_visible(False)      # closing the window only hides it
            ev.ignore()
            return
        if not self.quitting:
            self.quit_app()
        ev.accept()
