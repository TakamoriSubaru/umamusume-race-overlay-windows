"""Small helpers (HTTP, process list, time text, opening folders)."""

import os
import subprocess
import urllib.request
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices

from .constants import IS_WINDOWS, TMP_DIR



def http_get(url, timeout=5):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (RaceOverlayNative)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def process_running(needle):
    """True if any running process has `needle` (case-insensitive) in its command line."""
    if IS_WINDOWS:
        return any(needle.lower() in n for n in windows_process_names())
    needle = needle.lower().encode()
    me = str(os.getpid())
    try:
        pids = [d for d in os.listdir("/proc") if d.isdigit() and d != me]
    except OSError:
        return False
    for pid in pids:
        try:
            with open("/proc/%s/cmdline" % pid, "rb") as f:
                cmd = f.read().lower()
        except OSError:
            continue
        if needle in cmd and b"race_overlay_native" not in cmd:
            return True
    return False


def windows_process_names():
    """Lower case image names of the running programs (Windows). [] when the list cannot be read."""
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        names = []
        for line in out.decode("utf-8", "replace").splitlines():
            line = line.strip()
            if line.startswith('"'):
                names.append(line.split('","')[0].strip('"').lower())
        return names
    except Exception:
        return []


SERVER_MARKER = os.path.join(TMP_DIR, "race-overlay-server.started")


def stop_started_server():
    """Close the Race Overlay server, but only if the start script started it (so a Race Overlay you
    opened yourself is left alone). Returns how many processes were asked to stop."""
    if IS_WINDOWS:
        from .winserver import stop_started
        return stop_started()
    import signal
    if not os.path.exists(SERVER_MARKER):
        return 0
    n, me = 0, os.getpid()
    try:
        pids = [int(d) for d in os.listdir("/proc") if d.isdigit() and int(d) != me]
    except OSError:
        pids = []
    for pid in pids:
        try:
            with open("/proc/%d/cmdline" % pid, "rb") as f:
                cmd = f.read().lower()
        except OSError:
            continue
        first = cmd.split(b"\0")[0]
        if first.endswith(b"server.exe") or (b"server.exe" in cmd and b"wine" in first):
            try:
                os.kill(pid, signal.SIGTERM)
                n += 1
            except OSError:
                pass
    try:
        os.remove(SERVER_MARKER)
    except OSError:
        pass
    return n


def _safe_listdir(folder):
    try:
        return [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
    except OSError:
        return []


def fmt_time(s):
    if not s or s < 0:
        return "0.00"
    m = int(s // 60)
    r = s - m * 60
    return "%d:%05.2f" % (m, r) if m > 0 else "%.2f" % r


def open_folder(path):
    os.makedirs(path, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
