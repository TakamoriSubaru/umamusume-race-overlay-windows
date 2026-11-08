"""Checks that show whether everything is set up (no terminal needed), and log files to look at."""

import glob
import os
import socket
import time
from urllib.parse import urlparse

from .constants import IS_WINDOWS, SCRIPT_DIR, TMP_DIR
from .util import process_running

# The log files the start scripts write.
if IS_WINDOWS:
    LOG_FILES = (
        ("Race Overlay server", os.path.join(TMP_DIR, "race-overlay-server.log")),
    )
else:
    LOG_FILES = (
        ("Start script", "/tmp/race-overlay-native.log"),
        ("Race Overlay server", "/tmp/race-overlay-server.log"),
        ("Race Overlay program", "/tmp/race-overlay-wine.log"),
    )


def port_open(host, port, timeout=0.4):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def find_race_overlay(preferred=""):
    """Folder of the original Race Overlay (the one with Race Overlay.exe), or None.
    `preferred` is the folder chosen in the settings (Windows)."""
    home = os.path.expanduser("~")
    cands = [os.path.expanduser(preferred or ""), os.environ.get("RACE_OVERLAY_DIR", ""),
             os.path.join(SCRIPT_DIR, "Server Files"), os.path.join(SCRIPT_DIR, "..", "Server Files"),
             os.path.join(SCRIPT_DIR, "server"), os.path.join(SCRIPT_DIR, "..", "Race Overlay"),
             os.path.join(SCRIPT_DIR, "Race Overlay"),
             os.path.join(home, "Documents", "Server Files"),
             os.path.join(home, "Documents", "Race Overlay"), os.path.join(home, "Downloads", "Race Overlay"),
             os.path.join(home, "Desktop", "Race Overlay"), os.path.join(home, "Race Overlay")]
    pats = ["~/.local/share/Steam/steamapps/compatdata/*/pfx/drive_c/Race Overlay",
            "~/Documents/*/Race Overlay", "~/Downloads/*/Race Overlay"]
    if IS_WINDOWS:
        for env in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(env)
            if base:
                cands += [os.path.join(base, "Race Overlay"), os.path.join(base, "Programs", "Race Overlay")]
        cands += ["C:\\Race Overlay"]
        pats = ["~/Documents/*/Race Overlay", "~/Downloads/*/Race Overlay", "~/Desktop/*/Race Overlay",
                "~/OneDrive/Documents/Race Overlay", "~/OneDrive/Desktop/Race Overlay"]
    for pat in pats:
        cands += glob.glob(os.path.expanduser(pat))
    for d in cands:
        if d and os.path.isfile(os.path.join(d, "Race Overlay.exe")):
            return os.path.realpath(d)
    if IS_WINDOWS:
        return _search_folders(home)
    return None


_SEARCH = {"at": -100.0, "found": None}


def _search_folders(home):
    """Any folder (a few levels deep) next to the program, in Documents, Downloads or on the Desktop that
    holds Race Overlay.exe, whatever the folder is called ('Race Overlay 1.4', 'race-overlay-win' ...).
    The result is remembered for a while, so asking again and again stays cheap."""
    now = time.monotonic()
    if now - _SEARCH["at"] < 20.0:
        f = _SEARCH["found"]
        return f if f and os.path.isfile(os.path.join(f, "Race Overlay.exe")) else None
    roots = [SCRIPT_DIR, os.path.dirname(SCRIPT_DIR)]
    for sub in ("Documents", "Downloads", "Desktop", "OneDrive/Documents", "OneDrive/Desktop"):
        roots.append(os.path.join(home, sub))
    seen, found = set(), None
    for root in roots:
        root = os.path.realpath(root)
        if root in seen or not os.path.isdir(root):
            continue
        seen.add(root)
        budget = 2500                                  # folders looked at per place
        base = root.rstrip("\\/").count(os.sep)
        for cur, dirs, files in os.walk(root):
            budget -= 1
            if "Race Overlay.exe" in files:
                found = cur
                break
            if budget <= 0 or cur.count(os.sep) - base >= 3:
                dirs[:] = []
        if found:
            break
    _SEARCH["at"], _SEARCH["found"] = now, found
    return os.path.realpath(found) if found else None


def run_checks(ov):
    """[(state, title, hint)] with state "ok", "bad", "warn" or "info"."""
    out = []
    game_match = getattr(ov.args, "game_match", "") or "umamusume"
    game = process_running(game_match)
    out.append(("ok" if game else "warn",
                "Uma Musume is running" if game else "Uma Musume is not running",
                "" if game else "Start the game. The overlay waits for it."))

    kind = getattr(ov, "source_kind", "live")
    if kind == "live":
        u = urlparse(ov.base)
        host, port = u.hostname or "127.0.0.1", u.port or 5315
        up = port_open(host, port)
        out.append(("ok" if up else "bad",
                    "Race Overlay server answers (%s:%s)" % (host, port) if up
                    else "Race Overlay server does not answer (%s:%s)" % (host, port),
                    "" if up else (("The overlay starts it by itself a few seconds after the game is running. "
                                    "Look at the 'Race Overlay server' log below.") if IS_WINDOWS else
                                   "The start script starts it about 15 seconds after the game. "
                                   "Look at the 'Race Overlay server' log below.")))
        found = find_race_overlay(ov.s.get("race_overlay_dir", ""))
        out.append(("ok" if found else "warn",
                    "Race Overlay folder found: %s" % found if found else "Race Overlay folder not found",
                    "" if found else (("Race Overlay is a separate program and is NOT inside this one. Put its folder "
                                        "(the one with 'Race Overlay.exe' and 'resources') next to "
                                        "UmaRaceOverlay.exe, or choose it in the Home tab (More). "
                                        "The server then starts by itself, no restart needed."
                                       if IS_WINDOWS else
                                       "Put the folder with 'Race Overlay.exe' next to the app folder "
                                       "or set RACE_OVERLAY_DIR in settings.sh."))))
    else:
        out.append(("info", "Source: %s" % kind, ""))
        if IS_WINDOWS:
            from .winserver import LAST
            if LAST["text"]:
                out.append(("info", "Race Overlay starter: " + LAST["text"], ""))

    if ov.horses:
        out.append(("ok", "A race is loaded (%d umas)" % len(ov.horses), ""))
    else:
        out.append(("info", "No race loaded yet", "The tower appears when a race starts."))

    if ov.thumbs.use_default and not ov.thumbs.extra_dirs:
        out.append(("warn", "No default uma faces found",
                    "Choose your own pictures in the People tab (Umas), or put Race Overlay in a place the program can find."))
    elif ov.thumbs.use_default:
        out.append(("ok", "Default uma faces found", ""))
    out.append(("info", "Status: %s" % ov.status_summary(), ""))
    return out


def read_tail(path, max_lines=400, hide_fixme=True):
    """The last lines of a log file ('' if it is missing)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 200_000))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return ""
    lines = text.splitlines()
    if hide_fixme:
        lines = [x for x in lines if ":fixme:" not in x and "Fontconfig error" not in x]
    return "\n".join(lines[-max_lines:])
