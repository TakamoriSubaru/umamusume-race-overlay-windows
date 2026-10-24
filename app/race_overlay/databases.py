"""Players database (images/players.json) and outfits (images/outfits.json)."""

import json
import os
import time



class PlayersDB:
    """images/players.json - every trainer seen in a race, plus the picture you chose for them."""

    def __init__(self, path):
        self.path = path
        self.data = {}
        self._mtime = 0.0
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.data = d if isinstance(d, dict) else {}
            self._mtime = os.path.getmtime(self.path)
        except Exception:
            self.data = {}

    def reload_if_changed(self):
        try:
            m = os.path.getmtime(self.path)
        except OSError:
            return False
        if m != self._mtime:
            self._load()
            return True
        return False

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
            self._mtime = os.path.getmtime(self.path)
        except Exception as e:
            print("could not save players.json:", e)

    def key_for(self, name):
        low = name.strip().lower()
        for k in self.data:
            if k.strip().lower() == low:
                return k
        return None

    def _entry(self, name):
        k = self.key_for(name) or name.strip()
        return self.data.setdefault(k, {"image": "", "seen": 0, "last_uma": "", "last_seen": ""})

    def touch(self, name, uma):
        e = self._entry(name)
        e["seen"] = int(e.get("seen", 0)) + 1
        e["last_uma"] = uma
        e["last_seen"] = time.strftime("%Y-%m-%d %H:%M:%S")

    def add(self, name):
        self._entry(name)
        self.save()

    def set_image(self, name, value):
        self._entry(name)["image"] = value
        self.save()

    def names(self):
        return [n for n, _ in self.rows()]

    def rows(self):
        return sorted(self.data.items(), key=lambda kv: kv[1].get("last_seen", ""), reverse=True)


class UmasDB:
    """images/umas.json - every uma (by card id) seen in a race, so you can give her your own picture."""

    def __init__(self, path):
        self.path = path
        self.data = {}          # "100101" -> {"name": "...", "chara_id": 1001, "seen": 3}
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                self.data = {str(k): v for k, v in d.items() if isinstance(v, dict)}
        except Exception:
            self.data = {}

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception as e:
            print("could not save umas.json:", e)

    def touch(self, card_id, chara_id, name):
        """Remember a uma. True if she is new."""
        if not card_id:
            return False
        key = str(int(card_id))
        new = key not in self.data
        e = self.data.setdefault(key, {"name": name, "chara_id": int(chara_id or 0), "seen": 0})
        e["name"] = name or e.get("name", "")
        e["chara_id"] = int(chara_id or e.get("chara_id", 0) or 0)
        e["seen"] = int(e.get("seen", 0)) + 1
        return new

    def add(self, card_id, name):
        self.touch(card_id, int(card_id) // 100, name)
        self.data[str(int(card_id))]["seen"] = 0
        self.save()

    def rows(self):
        """[(card_id, chara_id, name, seen)] sorted by name."""
        out = []
        for k, v in self.data.items():
            try:
                out.append((int(k), int(v.get("chara_id", 0) or 0), v.get("name", ""), int(v.get("seen", 0))))
            except ValueError:
                continue
        return sorted(out, key=lambda r: (r[2].lower(), r[0]))


# Names of alternative outfits, by race dress id. The default outfit of a uma has the dress id
# chara id * 100 + 1 (for example 100201 = Silence Suzuka) and is shown with just her name.
# Everything else is an alternative outfit: shown as "Name (Outfit)". You can name more of them
# in the People tab (Outfits) (they are saved in images/outfits.json).
BUILTIN_OUTFITS = {
    105840: "Halloween",      # Meisho Doto
}


def is_alt_outfit(chara_id, dress_id):
    return bool(chara_id and dress_id and int(dress_id) != int(chara_id) * 100 + 1)


class OutfitsDB:
    """images/outfits.json - every alternative outfit seen in a race, and the name you gave it."""

    def __init__(self, path):
        self.path = path
        self.data = {}          # "105840" -> {"uma": "Meisho Doto", "label": "Halloween"}
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                self.data = {str(k): v for k, v in d.items() if isinstance(v, dict)}
        except Exception:
            self.data = {}

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception as e:
            print("could not save outfits.json:", e)

    def label_for(self, chara_id, dress_id):
        """"" for the default outfit, otherwise the outfit name ("Alt" while it has no name yet)."""
        if not is_alt_outfit(chara_id, dress_id):
            return ""
        mine = (self.data.get(str(int(dress_id))) or {}).get("label", "").strip()
        return mine or BUILTIN_OUTFITS.get(int(dress_id), "") or "Alt"

    def display(self, name, chara_id, dress_id):
        lab = self.label_for(chara_id, dress_id)
        return "%s (%s)" % (name, lab) if lab else name

    def touch(self, chara_id, dress_id, uma):
        """Remember an alternative outfit so it shows up in the People tab (Outfits). True if it is new."""
        if not is_alt_outfit(chara_id, dress_id):
            return False
        key = str(int(dress_id))
        if key in self.data:
            self.data[key]["uma"] = uma
            return False
        self.data[key] = {"uma": uma, "label": ""}
        return True

    def set_label(self, dress_id, label):
        e = self.data.setdefault(str(int(dress_id)), {"uma": "", "label": ""})
        e["label"] = label.strip()
        self.save()

    def rows(self):
        out = []
        for k, v in self.data.items():
            try:
                did = int(k)
            except ValueError:
                continue
            out.append((did, v.get("uma", ""), v.get("label", "")))
        return sorted(out, key=lambda r: (r[1].lower(), r[0]))
