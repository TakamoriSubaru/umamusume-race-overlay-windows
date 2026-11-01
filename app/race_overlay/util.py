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
    """Close Race Overlay's server (server.exe) when the overlay quits. Returns how many processes were stopped.
    Only server.exe is closed: a Race Overlay window you opened yourself stays. Windows: closes what this
    program started. Linux: asks every server.exe to stop, and forces the ones that do not."""
    if IS_WINDOWS:
        from .winserver import stop_started
        return stop_started()
    import signal
    import time
    me = os.getpid()

    def server_pids():
        try:
            pids = [int(d) for d in os.listdir("/proc") if d.isdigit() and int(d) != me]
        except OSError:
            return []
        found = []
        for pid in pids:
            try:
                with open("/proc/%d/cmdline" % pid, "rb") as f:
                    cmd = f.read().lower()
            except OSError:
                continue
            first = cmd.split(b"\0")[0]
            if first.endswith(b"server.exe") or (b"server.exe" in cmd and b"wine" in first):
                found.append(pid)
        return found

    todo = server_pids()
    for pid in todo:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    for _ in range(15):                          # up to 1.5 s to stop by itself
        if not any(os.path.exists("/proc/%d" % p) for p in todo):
            break
        time.sleep(0.1)
    for pid in todo:                             # still there: force it
        if os.path.exists("/proc/%d" % pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    try:
        os.remove(SERVER_MARKER)
    except OSError:
        pass
    return len(todo)


def install_exit_hooks(quit_cb, stop_cb):
    """Also stop the server when the overlay is ended from outside: Ctrl+C or closing the terminal
    (quit_cb = the normal quit) and, as a last resort, when Python exits (stop_cb)."""
    import atexit
    import signal
    for name in ("SIGINT", "SIGTERM", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, lambda *_a: quit_cb())
        except (ValueError, OSError):
            pass
    atexit.register(stop_cb)


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
