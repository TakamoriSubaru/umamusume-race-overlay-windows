"""Windows: starts the original Race Overlay once Uma Musume is running.

Race Overlay is a separate community program. It is NOT part of this repository and is never changed.
Its server (resources/server.exe) only answers once it has found the running game, and a game that is still
loading is not found yet (its log then says "is not running"). So we do not wait a long fixed time: we start
the server, and when it did not find the game we stop it and try again a moment later."""

import os
import socket
import subprocess
import threading
import time

from .constants import TMP_DIR
from . import logbuf

SERVER_LOG = os.path.join(TMP_DIR, "race-overlay-server.log")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

LAST = {"text": ""}  # the last thing the starter said (shown in the Help tab)
_STARTED = []        # the processes this program started (and closes again when it quits)


def server_up(port=5315):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def stop_started():
    """Close the Race Overlay processes this program started. Returns how many were asked to stop."""
    n = 0
    for p in list(_STARTED):
        if p.poll() is None:
            n += 1
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True, timeout=10,
                               creationflags=_NO_WINDOW)
            except Exception:
                try:
                    p.terminate()
                except Exception:
                    pass
        _STARTED.remove(p)
    return n


class ServerStarter(threading.Thread):
    """Runs in the background: waits for the game, then starts Race Overlay's server until it answers."""

    def __init__(self, get_setting, game_match="umamusume", port=5315):
        super().__init__(daemon=True)
        self.get = get_setting
        self.game_match = game_match or "umamusume"
        self.port = port
        self.stop_flag = threading.Event()
        self.proc = None

    def say(self, text):
        LAST["text"] = text
        logbuf.add("Race Overlay: " + text)

    def stop(self):
        self.stop_flag.set()

    def wait(self, seconds):
        return self.stop_flag.wait(seconds)          # True when we were asked to stop

    def run(self):
        from .diagnostics import find_race_overlay
        from .util import process_running
        try:
            if not self.get("start_race_overlay", True):
                return
            folder, warned = None, False
            while not folder:                       # keeps looking: drop the folder in, or choose it, no restart
                folder = find_race_overlay(self.get("race_overlay_dir", ""))
                if folder:
                    break
                if not warned:
                    self.say("the Race Overlay folder was NOT found. It is a separate program (not inside this "
                             "one): put its folder, with 'Race Overlay.exe' and 'resources', next to "
                             "UmaRaceOverlay.exe or choose it in the Home tab (More). Looking again every few "
                             "seconds.")
                    warned = True
                if self.wait(5.0):
                    return
            mode = self.get("race_overlay_start", "server") or "server"
            self.say("found in %s, waiting for Uma Musume ..." % folder)
            while not process_running(self.game_match):
                if self.wait(2.0):
                    return
            if self.wait(5.0):                      # the game needs a moment before it can be found
                return
            if mode in ("server", "both"):
                self.start_server(folder)
            if mode in ("app", "both") and not self.stop_flag.is_set():
                self.start_app(folder)
        except Exception as e:                      # never let a problem here stop the overlay
            self.say("could not start: %s" % e)

    def start_server(self, folder):
        exe = os.path.join(folder, "resources", "server.exe")
        if not os.path.isfile(exe):
            self.say("%s is missing." % exe)
            return
        tries = 0
        while not server_up(self.port):
            tries += 1
            if tries > 40 or self.stop_flag.is_set():
                break
            self.close_mine()
            try:
                log = open(SERVER_LOG, "wb")
                self.proc = subprocess.Popen([exe], cwd=os.path.dirname(exe), stdout=log, stderr=subprocess.STDOUT,
                                             creationflags=_NO_WINDOW)
                _STARTED.append(self.proc)
            except OSError as e:
                self.say("server.exe did not start: %s" % e)
                return
            for _ in range(40):
                if server_up(self.port) or self.stop_flag.is_set() or self.proc.poll() is not None:
                    break
                if self.log_says_no_game():
                    break                           # did not find the game: try again
                if self.wait(1.0):
                    return
            if server_up(self.port):
                break
            if self.wait(3.0):
                return
        if server_up(self.port):
            self.say("server is running.")
        else:
            self.say("the server did not start. Is Uma Musume running? Log: %s" % SERVER_LOG)

    def log_says_no_game(self):
        try:
            with open(SERVER_LOG, "rb") as f:
                return b"is not running" in f.read()
        except OSError:
            return False

    def close_mine(self):
        """Close the server we started before (only ours; a Race Overlay you opened yourself is left alone)."""
        if self.proc is not None and self.proc.poll() is None:
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True,
                               timeout=10, creationflags=_NO_WINDOW)
            except Exception:
                pass
            time.sleep(1.0)
        if self.proc in _STARTED:
            _STARTED.remove(self.proc)
        self.proc = None

    def start_app(self, folder):
        from .util import process_running
        if process_running("Race Overlay.exe"):
            return                                  # already running
        exe = os.path.join(folder, "Race Overlay.exe")
        if os.path.isfile(exe):
            p = subprocess.Popen([exe], cwd=folder)
            _STARTED.append(p)
