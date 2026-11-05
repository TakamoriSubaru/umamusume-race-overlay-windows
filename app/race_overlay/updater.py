"""Updating the program (from a zip or online) with a backup."""

import io
import json
import os
import re
import sys
import time
import zipfile
from PyQt6.QtCore import QThread, pyqtSignal

from .constants import APP_VERSION
from .util import http_get


UPDATE_FILES = {"race_overlay_native.py", "icon.png", "start_auto.sh", "start_overlay.sh",
                "start_race_overlay.sh", "launch_with_game.sh", "install_launcher.sh", "settings.sh", "lib.sh"}


KEEP_IF_EXISTS = {"settings.sh"}   # your own edits are never overwritten

# The program itself is the folder "race_overlay" (one .py file per part). Only plain
# race_overlay/<name>.py files are accepted, never other folders or paths.
PACKAGE_DIR_NAME = "race_overlay"
PACKAGE_FILE_RE = re.compile(r"^race_overlay/[A-Za-z_]+\.py$")


def is_update_path(name):
    """True for the files an update may replace."""
    return name in UPDATE_FILES or bool(PACKAGE_FILE_RE.match(name))


def update_key(zip_path):
    """Name an update file by the part of its path that matters: 'race_overlay/main.py', 'icon.png', ...
    Returns None for anything we do not update."""
    parts = [x for x in zip_path.replace("\\", "/").split("/") if x not in ("", ".")]
    if not parts or ".." in parts:
        return None
    if len(parts) >= 2 and parts[-2] == PACKAGE_DIR_NAME:
        key = PACKAGE_DIR_NAME + "/" + parts[-1]
        return key if PACKAGE_FILE_RE.match(key) else None
    return parts[-1] if parts[-1] in UPDATE_FILES else None


def version_tuple(v):
    nums = re.findall(r"\d+", str(v))
    return tuple(int(n) for n in nums) or (0,)


def source_version(data):
    m = re.search(rb'APP_VERSION\s*=\s*"([^"]+)"', data)
    return m.group(1).decode() if m else None


def url_allowed(url):
    u = url.strip().lower()
    return u.startswith("https://") or u.startswith("http://127.0.0.1") or u.startswith("http://localhost")


def files_from_zip(data):
    """{file name: bytes} for the files we know, whatever folder they are in inside the zip."""
    out = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            name = update_key(info.filename)
            if not info.is_dir() and name and info.file_size < 20 * 1024 * 1024:
                out[name] = z.read(info)
    return out


def read_update_file(path):
    with open(path, "rb") as f:
        data = f.read()
    if path.lower().endswith(".zip"):
        files = files_from_zip(data)
    elif os.path.basename(path) == "race_overlay_native.py":
        files = {"race_overlay_native.py": data}
    else:
        raise ValueError("Choose the .zip file of the new version.")
    return files


def check_update_files(files):
    """Returns the new version string. Raises ValueError when the update is not usable."""
    ver_src = files.get("race_overlay/constants.py") or files.get("race_overlay_native.py")
    if ver_src is None:
        raise ValueError("race_overlay/constants.py was not found in the update.")
    ver = source_version(ver_src)
    if not ver:
        raise ValueError("This does not look like a version of this program (no version number).")
    for name, data in files.items():
        if name.endswith(".py"):
            try:
                compile(data, name, "exec")
            except SyntaxError as e:
                raise ValueError("%s is broken (line %s). Nothing was changed." % (name, e.lineno))
    return ver


def install_update(files, target_dir, old_version=APP_VERSION):
    """Backs up the current files, then replaces them. Returns (replaced names, backup folder)."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(target_dir, "backup", "%s_%s" % (old_version, stamp))
    os.makedirs(backup, exist_ok=True)
    replaced = []
    for name, data in files.items():
        if not is_update_path(name):
            continue
        dest = os.path.join(target_dir, *name.split("/"))
        if name in KEEP_IF_EXISTS and os.path.exists(dest):
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.exists(dest):
            bak = os.path.join(backup, *name.split("/"))
            os.makedirs(os.path.dirname(bak), exist_ok=True)
            with open(dest, "rb") as f_old, open(bak, "wb") as f_bak:
                f_bak.write(f_old.read())
        tmp = dest + ".new"
        with open(tmp, "wb") as f:
            f.write(data)
        if name.endswith(".sh"):
            os.chmod(tmp, 0o755)
        os.replace(tmp, dest)
        replaced.append(name)
    return replaced, backup


def fetch_manifest(url):
    if not url_allowed(url):
        raise ValueError("The update link must start with https://")
    m = json.loads(http_get(url, timeout=10).decode("utf-8"))
    if not isinstance(m, dict) or "version" not in m:
        raise ValueError("That link is not an update description (latest.json).")
    return m


def download_update(manifest):
    link = manifest.get("update_zip") or manifest.get("zip")      # the small zip without the server files, when there is one
    if link:
        if not url_allowed(link):
            raise ValueError("The zip link must start with https://")
        return files_from_zip(http_get(link, timeout=300))
    files = {}
    for name, url in (manifest.get("files") or {}).items():
        key = update_key(name)
        if key:
            if not url_allowed(url):
                raise ValueError("Every download link must start with https://")
            files[key] = http_get(url, timeout=60)
    return files


class Job(QThread):
    """Runs a function in the background so the window does not freeze."""
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn())
        except Exception as e:
            self.failed.emit(str(e) or e.__class__.__name__)


def restart_program():
    """Start the (updated) program again with the same options."""
    if sys.platform == "win32":          # os.execv does not replace the process on Windows
        import subprocess
        args = [sys.executable] + (sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv)
        subprocess.Popen(args, close_fds=True)
        os._exit(0)
    os.execv(sys.executable, [sys.executable] + sys.argv)
