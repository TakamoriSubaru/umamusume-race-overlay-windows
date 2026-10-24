"""Loading uma images and player pictures in the background."""

import json
import os
from PyQt6.QtCore import QThread, pyqtSignal
from concurrent.futures import ThreadPoolExecutor

from .constants import IMG_EXTS, IS_WINDOWS
from .util import http_get


def find_wine_thumb_dirs():
    """Looks for the character_thumbs folder of Race Overlay inside your Wine/Proton prefixes."""
    import glob
    if IS_WINDOWS:                   # Windows: Race Overlay runs natively, look for its folder
        from .diagnostics import find_race_overlay
        d = find_race_overlay()
        thumbs = os.path.join(d, "resources", "character_thumbs") if d else ""
        return [thumbs] if thumbs and os.path.isdir(thumbs) else []
    pats = [
        "~/.local/share/Steam/steamapps/compatdata/*/pfx/drive_c/Race Overlay/resources/character_thumbs",
        "~/.steam/steam/steamapps/compatdata/*/pfx/drive_c/Race Overlay/resources/character_thumbs",
        "~/.wine/drive_c/Race Overlay/resources/character_thumbs",
    ]
    out = []
    for pat in pats:
        out += glob.glob(os.path.expanduser(pat))
    return out


def find_file_ci(folder, stem):
    """folder/<stem>.<png|jpg|webp...> ignoring upper/lower case."""
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    low = stem.lower()
    for n in names:
        base, ext = os.path.splitext(n)
        if base.lower() == low and ext.lower() in IMG_EXTS:
            return os.path.join(folder, n)
    return None


def read_file(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return b""


class ImageStore(QThread):
    """Loads avatars in the background.

    Player pictures (by trainer name):  images/players/<trainer>.png   or   images/images.json
    Uma pictures:                       images/uma/<card id | chara id | uma name>.png,
                                        Race Overlay's character_thumbs folder, then the server.
    """
    loaded = pyqtSignal(str, bytes)  # key, image bytes (empty = not found)

    def __init__(self, base_url, images_dir, extra_dirs):
        super().__init__()
        self.base = base_url.rstrip("/")
        self.dir = images_dir
        self.players = os.path.join(images_dir, "players")
        self.uma = os.path.join(images_dir, "uma")
        self.cache = os.path.join(images_dir, "cache")
        self.map_file = os.path.join(images_dir, "images.json")
        self.extra_dirs = [d for d in extra_dirs if d]
        self.use_default = True      # False = only the pictures in images/uma (and nothing from Race Overlay)
        for d in (self.players, self.uma, self.cache):
            os.makedirs(d, exist_ok=True)
        if not os.path.exists(self.map_file):
            with open(self.map_file, "w", encoding="utf-8") as f:
                json.dump({
                    "_help": "Map a trainer name to a picture file or a web link, e.g. "
                             "\"Takamori\": \"https://example.com/me.png\"",
                    "ExampleTrainer": "https://example.com/picture.png",
                }, f, indent=2)
        self.pool = ThreadPoolExecutor(max_workers=4)

    def request(self, key, spec):
        self.pool.submit(self._work, key, spec)

    def _work(self, key, spec):
        try:
            data = self._player(spec["trainer"]) if spec["kind"] == "player" else self._uma(spec)
        except Exception:
            data = b""
        self.loaded.emit(key, data or b"")

    def _download(self, url):
        import hashlib
        cp = os.path.join(self.cache, hashlib.sha1(url.encode()).hexdigest() + ".img")
        data = read_file(cp)
        if data:
            return data
        data = http_get(url, timeout=8)
        with open(cp, "wb") as f:
            f.write(data)
        return data

    def _load_ref(self, v):
        if v.lower().startswith(("http://", "https://")):
            return self._download(v)
        path = os.path.expanduser(v)
        if not os.path.isabs(path):
            path = os.path.join(self.dir, path)
        return read_file(path)

    def _db_image(self, trainer):
        try:
            with open(os.path.join(self.dir, "players.json"), "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return ""
        for k, v in data.items():
            if k.strip().lower() == trainer.strip().lower() and isinstance(v, dict):
                return v.get("image", "") or ""
        return ""

    def _player(self, trainer):
        val = self._db_image(trainer)
        if val:
            data = self._load_ref(val)
            if data:
                return data
        safe = trainer.replace("/", "_").replace("\\", "_")
        try:
            with open(self.map_file, "r", encoding="utf-8") as f:
                mapping = json.load(f)
        except Exception:
            mapping = {}
        for k, v in mapping.items():
            if k.startswith("_") or not isinstance(v, str):
                continue
            if k.strip().lower() == trainer.strip().lower():
                if v.lower().startswith(("http://", "https://")):
                    return self._download(v)
                path = os.path.expanduser(v)
                if not os.path.isabs(path):
                    path = os.path.join(self.dir, path)
                return read_file(path)
        path = find_file_ci(self.players, safe)
        return read_file(path) if path else b""

    def _uma(self, spec):
        card, chara, name = spec.get("card_id", 0), spec.get("chara_id", 0), spec.get("name", "")
        for stem in (str(card), str(chara), name):
            if stem and stem != "0":
                path = find_file_ci(self.uma, stem)
                if path:
                    return read_file(path)
        if not self.use_default:
            return b""
        fname = "chara_stand_%d_%d.webp" % (card // 100, card)
        for d in [self.uma] + self.extra_dirs:
            p = os.path.join(d, fname)
            if os.path.isfile(p):
                return read_file(p)
        try:
            return http_get("%s/thumbs/%s" % (self.base, fname), timeout=4)
        except Exception:
            return b""

    def run(self):
        self.exec()
