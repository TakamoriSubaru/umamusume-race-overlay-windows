"""Where races come from: the Race Overlay server (live) and saved race files (watch / demo)."""

import json
import os
import threading
import time
import urllib.request
from PyQt6.QtCore import QThread, pyqtSignal

from .constants import IS_WINDOWS, TRACK_NAMES
from .luck import skill_ids
from .simdata import parse_sim
from .util import _safe_listdir, http_get, process_running


def result_map_from_latest(d):
    m = {}
    if d and d.get("horses"):
        for h in d["horses"]:
            m[h.get("fo")] = h
    return m


class SseThread(QThread):
    race = pyqtSignal(dict, dict)   # payload, {frameOrder: result}
    clock = pyqtSignal(dict)
    status = pyqtSignal(str)
    quit_request = pyqtSignal()

    def __init__(self, base_url, game_match="", quit_with_game=False):
        super().__init__()
        self.base = base_url.rstrip("/")
        self.game_match = game_match
        self.quit_with_game = quit_with_game
        self.offset = 0.0  # unused in live mode (the real game clock is used)
        self.counts = True   # races from this source give points
        self._stop = False
        self._last_result_raw = ""

    def stop(self):
        self._stop = True

    def _game_gone(self):
        return bool(self.game_match) and not process_running(self.game_match)

    def run(self):
        was_running = False
        left_at = None
        while not self._stop:
            if self.game_match:
                if self._game_gone():
                    if was_running:
                        if left_at is None:
                            left_at = time.monotonic()
                        elif self.quit_with_game and time.monotonic() - left_at > 5:
                            self.quit_request.emit()
                            return
                    self.status.emit("Waiting for Uma Musume to start...")
                    time.sleep(1.0)
                    continue
                was_running = True
                left_at = None
            try:
                self.status.emit("Connecting to Race Overlay server...\n(it starts a bit after the game)")
                with urllib.request.urlopen(self.base + "/events", timeout=30) as resp:
                    self.status.emit("Connected. Waiting for a race...")
                    buf = []
                    last_check = time.monotonic()
                    for raw in resp:
                        if self._stop:
                            return
                        if self.game_match and time.monotonic() - last_check > 2:
                            last_check = time.monotonic()
                            if self._game_gone():
                                break
                        line = raw.decode("utf-8", "replace").rstrip("\r\n")
                        if line == "":
                            if buf:
                                self._handle("\n".join(buf))
                                buf = []
                        elif line.startswith("data:"):
                            d = line[5:]
                            if d.startswith(" "):
                                d = d[1:]
                            buf.append(d)
            except Exception:
                if IS_WINDOWS:
                    self.status.emit("Race Overlay server not reachable yet.\nIs the Race Overlay folder found?\n"
                                     "(Help tab shows why)")
                else:
                    self.status.emit("Race Overlay server not reachable yet.\nIs Race Overlay running?\n"
                                     "(see /tmp/race-overlay-wine.log)")
            for _ in range(20):
                if self._stop:
                    return
                time.sleep(0.1)

    def _handle(self, text):
        try:
            data = json.loads(text)
        except Exception:
            return
        t = data.get("type")
        if t == "clock":
            self.clock.emit(data)
        elif t == "race":
            threading.Thread(target=self._race_worker, args=(data,), daemon=True).start()

    def _fetch_latest(self):
        try:
            raw = http_get(self.base + "/latest-result").decode("utf-8", "replace")
            return raw, json.loads(raw)
        except Exception:
            return "", None

    def _race_worker(self, payload):
        # The server updates /latest-result slightly after the race event, so retry a few times.
        prev = self._last_result_raw
        rmap = {}
        for i in range(8):
            raw, d = self._fetch_latest()
            rmap = result_map_from_latest(d)
            ready = bool(rmap) if prev == "" else (raw != prev and bool(rmap))
            if raw:
                self._last_result_raw = raw
            if ready:
                break
            if i < 7:
                time.sleep(0.35)
        self.race.emit(payload, rmap)


def payload_from_saved_race(path):
    """Build the same data the live server would send, from a horseACT race JSON."""
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    style_to_course = {"Right": "Right", "Left": "Left"}
    runners, rmap = [], {}
    for h in d["raceHorse"]:
        rd = h.get("responseHorseData", {})
        fo = rd.get("frame_order", h["horseIndex"] + 1)
        runners.append({
            "name": h["charaName"], "trainer": h.get("trainerName", ""),
            "style": rd.get("running_style", 2), "gate": h.get("postNumber", fo),
            "frameOrder": fo, "charaId": h["charaId"], "dressId": h.get("raceDressId", 0),
            "skills": skill_ids(rd.get("skill_array")),
        })
        rmap[fo] = {
            "fo": fo, "chara_id": h["charaId"], "card_id": rd.get("card_id", h["charaId"] * 100 + 1),
            "finishOrder": h["finishOrder"], "finishTimeRaw": h["finishTimeRaw"],
        }
    dist = d["raceCourseSet"]["distance"]
    info = {
        "trackName": TRACK_NAMES.get((d.get("raceTrack") or {}).get("id"), ""), "surface": "Turf" if d["raceCourseSet"]["ground"] == 1 else "Dirt",
        "distType": d.get("courseDistanceType", ""), "distance": dist,
        "direction": style_to_course.get(d.get("rotationCategory", ""), ""),
        "ground": d.get("groundCondition", ""), "weather": d.get("weather", ""),
        "season": d.get("season", ""),
    }
    payload = {
        "type": "race", "replay": d["simDataBase64"].replace("\n", ""), "runners": runners,
        "courseId": d["raceCourseSet"]["id"], "courseInfo": info,
        "courseShape": {"distance": dist}, "courseData": {"distance": dist},
    }
    return payload, rmap


def choose_source(args, settings=None, cfg=None):
    """Where the races come from: always the live server (exact race clock). Only --demo plays a file.
    Returns (kind, folder) with kind = "demo" or "live"."""
    if args.demo:
        return "demo", ""
    return "live", ""


class ReplayBase(QThread):
    """Plays a saved race by faking the same events the live server would send."""
    race = pyqtSignal(dict, dict)
    clock = pyqtSignal(dict)
    status = pyqtSignal(str)
    quit_request = pyqtSignal()

    def __init__(self, speed=1.0):
        super().__init__()
        self.speed = speed
        self.offset = 0.0     # sync nudge in seconds (arrow keys in the window change it)
        self.delay = 0.0      # saved races only: seconds from "file saved" to "gates open"
        self.counts = True    # does the race that plays now give points? (not for demos / old files)
        self._stop = False

    def stop(self):
        self._stop = True

    def _sleep(self, s):
        end = time.monotonic() + s
        while time.monotonic() < end and not self._stop:
            time.sleep(0.02)

    def play(self, payload, rmap, interrupt=None, t0=0.0, preroll=1.0, delay=0.0):
        """delay = seconds the race really starts AFTER t0 = 0. Until then nothing is sent, so the
        overlay stays hidden (the game writes the race file when the race loads, not when it starts)."""
        sim = parse_sim(payload["replay"])
        max_t = max((r["finishTimeRaw"] for r in sim["results"]), default=sim["times"][-1])
        self.race.emit(payload, rmap)
        if preroll > 0:
            self._sleep(preroll)
        start = time.monotonic()
        ticks = 0
        sent = False
        while not self._stop:
            ticks += 1
            if interrupt and ticks % 10 == 0 and interrupt():
                break
            t = (time.monotonic() - start) * self.speed + t0 + self.offset - delay
            if t < 0:                      # race has not started yet: show nothing
                self._sleep(0.1)
                continue
            if t > max_t + 2:
                break
            sent = True
            self.clock.emit({"type": "clock", "active": True, "time": t, "aiStates": {}})
            self._sleep(0.1)
        if sent:
            self.clock.emit({"type": "clock", "active": False, "time": 0})


class DemoThread(ReplayBase):
    """--demo: replay one saved race file over and over."""

    def __init__(self, path, speed=1.0):
        super().__init__(speed)
        self.path = path
        self.counts = False

    def run(self):
        payload, rmap = payload_from_saved_race(self.path)
        while not self._stop:
            self.play(payload, rmap)
            self._sleep(6.0)


class TestReplayThread(ReplayBase):
    """Menu > "Replay a saved race (test)": play one race file once, no game and no server needed."""
    error = pyqtSignal(str)

    def __init__(self, path, delay=3.0):
        super().__init__(1.0)
        self.path = path
        self.delay = delay
        self.counts = False

    def run(self):
        try:
            payload, rmap = payload_from_saved_race(self.path)
        except Exception as e:
            self.error.emit("Could not read %s: %s" % (os.path.basename(self.path), e))
            return
        self.play(payload, rmap, preroll=0.0, delay=self.delay)
