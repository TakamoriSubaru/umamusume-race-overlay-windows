"""Tells you when a new version is out (checked on GitHub when the program starts) and installs it for you."""

import os
import sys
import time

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QMessageBox, QProgressDialog

from .constants import APP_VERSION, SCRIPT_DIR, FROZEN
from .updater import (Job, check_update_files, download_update, fetch_manifest, install_update, version_tuple)

CHECK_EVERY_MS = 6 * 60 * 60 * 1000      # and once more every 6 hours while the program stays open
FIRST_CHECK_MS = 12 * 1000               # a few seconds after start, so the start-up is not slowed down


class AutoUpdate:
    """One per overlay: `start()` once. Everything runs in the background; a window only shows when there is news."""

    def __init__(self, ov):
        self.ov = ov
        self.jobs = []                      # running background jobs (kept so Qt does not delete a thread that is still running)
        self.busy = False
        self.timer = QTimer(ov)
        self.timer.timeout.connect(self.check)

    def start(self):
        self.timer.start(CHECK_EVERY_MS)
        QTimer.singleShot(FIRST_CHECK_MS, self.check)

    def spawn(self, fn, done, failed):
        self.jobs = [j for j in self.jobs if not j.isFinished()]
        job = Job(fn)
        job.done.connect(done)
        job.failed.connect(failed)
        self.jobs.append(job)
        job.start()

    # ----- checking --------------------------------------------------------------------
    def check(self, manual=False):
        """manual=True (the "Check online" button) also says "you have the newest version"."""
        s = self.ov.s
        url = str(s.get("update_url", "")).strip()
        if self.busy or not url or (not manual and not s.get("auto_update_check", True)):
            return
        self.busy = True
        self.spawn(lambda: fetch_manifest(url), lambda m: self.on_manifest(m, manual), lambda msg: self.on_failed(msg, manual))

    def on_failed(self, msg, manual):
        self.busy = False
        if manual:
            QMessageBox.information(self.ov, "Update", "Could not check for updates:\n%s" % msg)

    def on_manifest(self, m, manual):
        self.busy = False
        ver = str(m.get("version", ""))
        if version_tuple(ver) <= version_tuple(APP_VERSION):
            if manual:
                QMessageBox.information(self.ov, "Update", "You have the newest version (%s)." % APP_VERSION)
            return
        if not manual and self.ov.s.get("update_skip", "") == ver:
            return
        self.ask(m)

    # ----- asking and installing -----------------------------------------------------------
    def ask(self, m):
        ver = str(m.get("version", ""))
        notes = str(m.get("notes", "")).strip()
        box = QMessageBox(self.ov.dialog or self.ov)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("New version available")
        box.setText("<b>Version %s is out</b> (you have %s)." % (ver, APP_VERSION))
        box.setInformativeText("Update now? The program closes and starts again by itself.\n"
                               "Your settings and pictures are kept." + ("\n\n" + notes[:1200] if notes else ""))
        yes = box.addButton("Update now", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        skip = box.addButton("Skip this version", QMessageBox.ButtonRole.DestructiveRole)
        box.exec()
        if box.clickedButton() is yes:
            self.install(m)
        elif box.clickedButton() is skip:
            self.ov.set_setting("update_skip", ver)

    def install(self, m):
        if self.busy:
            return
        self.busy = True
        self.wait = QProgressDialog("Downloading version %s ..." % m.get("version", ""), "", 0, 0, self.ov.dialog or self.ov)
        self.wait.setCancelButton(None)
        self.wait.setWindowModality(Qt.WindowModality.WindowModal)
        self.wait.setMinimumDuration(0)
        self.wait.show()
        self.spawn(lambda: self.download(m), self.downloaded, self.download_failed)

    def download_failed(self, msg):
        self.busy = False
        self.wait.close()
        QMessageBox.warning(self.ov, "Update", "The download did not work:\n%s\n\nNothing was changed." % msg)

    def download(self, m):
        if FROZEN:                            # the packaged .exe: the whole new folder is needed
            from .util import http_get
            url = m.get("update_zip") or m.get("zip")
            if not url or not str(url).lower().startswith("https://"):
                raise ValueError("The update description has no download link.")
            return ("zip", http_get(url, timeout=900))
        return ("files", download_update(m))

    def downloaded(self, result):
        self.wait.close()
        try:
            self.apply(result)
        except Exception as e:
            self.busy = False
            QMessageBox.warning(self.ov, "Update", "Could not install the update:\n%s\n\nNothing was changed, or the "
                                "old files are backed up." % e)

    def apply(self, result):
        kind, data = result
        if kind == "zip":
            apply_windows_update(data, self.ov)       # starts a small helper and closes the program
            return
        new_ver = check_update_files(data)
        replaced, backup = install_update(data, SCRIPT_DIR)
        QMessageBox.information(self.ov, "Update", "Updated to version %s (%d files).\nThe program restarts now." % (new_ver, len(replaced)))
        self.ov.restart_now()


def safe_extract(zip_bytes, dest):
    """Unzip into dest. Refuses paths that would leave dest. Returns the folder that holds the .exe."""
    import io
    import zipfile
    exe = os.path.basename(sys.executable)
    base = os.path.realpath(dest)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        if sum(i.file_size for i in z.infolist()) > 1500 * 1024 * 1024:
            raise ValueError("The update zip is far too big.")
        for info in z.infolist():
            parts = [p for p in info.filename.replace("\\", "/").split("/") if p]
            target = os.path.realpath(os.path.join(base, *parts))
            if target != base and not target.startswith(base + os.sep):
                raise ValueError("The update zip has a bad path: %s" % info.filename)
        z.extractall(base)
    for folder, _dirs, files in os.walk(base):
        if exe in files:
            return folder
    raise ValueError("%s is not in the update zip." % exe)


SCRIPT_LINES = [
    "@echo off",
    'set "SRC=@SRC@"',
    'set "DST=@DST@"',
    'set "WORK=@WORK@"',
    "set /a n=0",
    ":wait",
    'tasklist /FI "PID eq @PID@" 2>nul | find "@PID@" >nul',
    "if errorlevel 1 goto copy",
    "set /a n+=1",
    "if %n% GTR 90 goto copy",
    "ping -n 2 127.0.0.1 >nul",
    "goto wait",
    ":copy",
    'robocopy "%SRC%" "%DST%" /E /XD "Server Files" /R:30 /W:1 /NFL /NDL /NJH /NJS /NP >nul',
    "if errorlevel 8 goto failed",
    'start "" "%DST%\\@EXE@" @ARGS@',
    "goto done",
    ":failed",
    'echo The update could not copy every file. Download the newest zip from the GitHub releases page. > "%DST%\\update_failed.txt"',
    'start "" "%DST%\\@EXE@" @ARGS@',
    ":done",
    '(goto) 2>nul & rd /s /q "%WORK%"',
    "",
]


def update_script(src, dst, exe, pid, args, work):
    """The Windows helper: waits until this program has closed, copies the new files over the old ones
    (never the 'Server Files' folder), then starts the program again."""
    text = "\r\n".join(SCRIPT_LINES)
    for key, val in (("@SRC@", src), ("@DST@", dst), ("@WORK@", work), ("@PID@", str(pid)), ("@EXE@", exe), ("@ARGS@", args)):
        text = text.replace(key, val)
    return text


def apply_windows_update(zip_bytes, ov):
    import subprocess
    import tempfile
    work = tempfile.mkdtemp(prefix="uma_update_")
    src = safe_extract(zip_bytes, os.path.join(work, "new"))
    exe = os.path.basename(sys.executable)
    script = os.path.join(work, "apply.cmd")
    args = subprocess.list2cmdline(sys.argv[1:])
    with open(script, "w", encoding="mbcs", errors="replace", newline="") as f:
        f.write(update_script(src, SCRIPT_DIR, exe, os.getpid(), args, work))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(["cmd", "/c", script], creationflags=flags, close_fds=True, cwd=work)
    QMessageBox.information(ov, "Update", "The update is installed while the program closes.\nIt starts again by itself in a few seconds.")
    ov.quit_app()
