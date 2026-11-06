"""Loading uma images and player pictures in the background."""

import json
import os
from PyQt6.QtCore import QThread, pyqtSignal
from concurrent.futures import ThreadPoolExecutor

from .constants import IMG_EXTS, IS_WINDOWS
from .util import http_get


def find_wine_thumb_dirs(preferred=""):
    """Looks for the character_thumbs folder of Race Overlay inside your Wine/Proton prefixes."""
    import glob
    if IS_WINDOWS:                   # Windows: Race Overlay runs natively, look for its folder
        from .diagnostics import find_race_overlay
        d = find_race_overlay(preferred)       # the folder chosen in the Home tab wins
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

    def cards_of(self, chara_id):
        """Card ids of this uma that have a picture on this computer (images/uma, Race Overlay's character_thumbs)."""
        import re
        pat = re.compile(r"chara_stand_%d_(\d+)\." % int(chara_id))
        found = set()
        for d in [self.uma] + self.extra_dirs:
            try:
                for n in os.listdir(d):
                    m = pat.match(n)
                    if m:
                        found.add(int(m.group(1)))
            except OSError:
                pass
        return found

    def _uma(self, spec):
        card, chara, name = spec.get("card_id", 0), spec.get("chara_id", 0), spec.get("name", "")
        # Another outfit only takes a picture made for that card. A picture named after the uma or her
        # character id is her normal outfit, so it must not stand in for Halloween, Summer, ...
        alt = bool(card and chara and card != chara * 100 + 1)
        for stem in ((str(card),) if alt else (str(card), str(chara), name)):
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


# ----- share your pictures as a zip (so a friend does not have to collect them again) -----------------

PACK_JSON = ("images.json", "players.json", "outfits.json", "umas.json")
MAX_PACK_BYTES = 400 * 1024 * 1024


def export_pictures(images_dir, zip_path):
    """Save players/, uma/ and the picture lists as a zip. Returns the number of pictures."""
    import zipfile
    n = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for sub in ("players", "uma"):
            base = os.path.join(images_dir, sub)
            if not os.path.isdir(base):
                continue
            for name in sorted(os.listdir(base)):
                if os.path.splitext(name)[1].lower() in IMG_EXTS and os.path.isfile(os.path.join(base, name)):
                    z.write(os.path.join(base, name), "images/%s/%s" % (sub, name))
                    n += 1
        for name in PACK_JSON:
            p = os.path.join(images_dir, name)
            if os.path.isfile(p):
                z.write(p, "images/" + name)
    return n


def _merge_json(old_bytes, new_bytes):
    try:
        old = json.loads(old_bytes.decode("utf-8"))
        new = json.loads(new_bytes.decode("utf-8"))
        if isinstance(old, dict) and isinstance(new, dict):
            old.update(new)
            return json.dumps(old, indent=2, ensure_ascii=False).encode("utf-8")
    except (ValueError, UnicodeDecodeError):
        pass
    return new_bytes


LAST_PACK = {"players": 0, "clubs": []}       # what the last player pack brought: how many trainers, which clubs


def _import_player_pack(z, records_name, images_dir):
    """A zip with pfp_records.json (discord id -> in-game name) and <discord id>.png pictures:
    each picture becomes the picture of that trainer. Returns how many trainers got a picture."""
    try:
        records = json.loads(z.read(records_name).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, KeyError):
        raise ValueError("pfp_records.json could not be read.")
    if not isinstance(records, dict):
        raise ValueError("pfp_records.json has an unexpected format.")
    folder = records_name.rsplit("/", 1)[0] + "/" if "/" in records_name else ""
    names = {i.filename: i for i in z.infolist() if not i.is_dir()}
    players_dir = os.path.join(images_dir, "players")
    os.makedirs(players_dir, exist_ok=True)
    db_path = os.path.join(images_dir, "players.json")
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            db = json.load(f)
        if not isinstance(db, dict):
            db = {}
    except Exception:
        db = {}
    low = {k.strip().lower(): k for k in db}
    n = 0
    clubs = set()
    for did, rec in records.items():
        if not isinstance(rec, dict):
            continue
        src = None
        for ext in sorted(IMG_EXTS):
            src = names.get("%s%s%s" % (folder, did, ext))
            if src:
                break
        if src is None:
            continue
        data = z.read(src)
        ext = os.path.splitext(src.filename)[1].lower()
        wanted = []
        for key in (rec.get("in_game_name"), rec.get("display_name")):      # the name seen in the race, and the Discord name
            key = (key or "").strip()
            if key and key.lower() not in [w.lower() for w in wanted]:
                wanted.append(key)
        if not wanted:
            continue
        safe = "".join(c if c not in '/\\:*?"<>|' else "_" for c in wanted[0]).strip() or str(did)
        with open(os.path.join(players_dir, safe + ext), "wb") as f:
            f.write(data)
        for key in wanted:
            k = low.get(key.lower(), key)
            e = db.setdefault(k, {"image": "", "seen": 0, "last_uma": "", "last_seen": ""})
            e["image"] = "players/" + safe + ext
            if rec.get("club_name"):
                e["club"] = rec["club_name"]
                clubs.add(rec["club_name"])
            low[key.lower()] = k
        n += 1
    tmp = db_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
    os.replace(tmp, db_path)
    LAST_PACK["players"], LAST_PACK["clubs"] = n, sorted(clubs, key=str.lower)
    return n


def import_pictures(zip_path, images_dir):
    """Copy the pictures of a zip made by export_pictures() (or a zip of an 'images' folder) into images_dir.
    Only pictures and the picture lists are taken, nothing outside images_dir is ever written.
    Returns the number of pictures. Raises ValueError for a zip without pictures."""
    import zipfile
    n = 0
    with zipfile.ZipFile(zip_path) as z:
        if sum(i.file_size for i in z.infolist()) > MAX_PACK_BYTES:
            raise ValueError("The zip is too big to be a picture pack.")
        for info in z.infolist():                       # a list of player pictures made from Discord
            if info.filename.replace("\\", "/").rsplit("/", 1)[-1] == "pfp_records.json" and ".." not in info.filename:
                return _import_player_pack(z, info.filename, images_dir)
        for info in z.infolist():
            if info.is_dir():
                continue
            parts = [p for p in info.filename.replace("\\", "/").split("/") if p not in ("", ".")]
            if ".." in parts or not parts:
                continue
            if parts[0].lower() == "images":
                parts = parts[1:]
            if len(parts) == 2 and parts[0] in ("players", "uma") \
                    and os.path.splitext(parts[1])[1].lower() in IMG_EXTS:
                dest = os.path.join(images_dir, parts[0], parts[1])
                n += 1
            elif parts[-1].startswith("chara_stand_") and os.path.splitext(parts[-1])[1].lower() in IMG_EXTS:
                dest = os.path.join(images_dir, "uma", parts[-1])      # Race Overlay's character_thumbs (every outfit)
                n += 1
            elif len(parts) == 1 and parts[0] in PACK_JSON:
                dest = os.path.join(images_dir, parts[0])
            else:
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            data = z.read(info)
            if parts[-1] in PACK_JSON and os.path.isfile(dest):
                data = _merge_json(read_file(dest), data)
            with open(dest, "wb") as f:
                f.write(data)
    if n == 0:
        raise ValueError("No pictures found in this zip. Choose a zip made with \"Save my pictures as a zip\".")
    return n
