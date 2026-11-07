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
        for k, e in self.data.items():                  # the Discord name (or another name) of a player
            if any(str(a).strip().lower() == low for a in e.get("aliases", ())):
                return k
        return None

    def remove_keys(self, keys):
        """Forget these exact rows (their picture files stay). Returns how many were removed."""
        n = 0
        for k in keys:
            if k in self.data:
                del self.data[k]
                n += 1
        if n:
            self.save()
        return n

    def club_of(self, name):
        """The club of a trainer (from a player pictures zip), or ""."""
        k = self.key_for(name or "")
        return str((self.data.get(k) or {}).get("club", "")) if k else ""

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
# in images/outfits.json.
BUILTIN_OUTFITS = {
    105840: "Halloween",      # Meisho Doto
}


THEME_WORDS = (        # a short name for the usual event outfits, found in the official card name
    ("Halloween", ("halloween", "vampire", "jiangshi", "mummy", "lantern", "pumpkin", "witch", "lunatic")),
    ("Summer", ("summer", "vacances", "swimsuit")),
    ("Christmas", ("christmas", "caroler", "santa", "noel")),
    ("New Year", ("new year",)),
    ("Valentine", ("valentine", "chocolat")),
    ("Wedding", ("wedding", "bride", "bridal")),
    ("Autumn", ("autumn",)),
    ("Cheerleader", ("cheerleader",)),
)


def short_outfit_name(title):
    """"Vampire Makeover!" -> "Halloween". Names that are not a known event stay as the card name."""
    low = title.lower()
    for short, words in THEME_WORDS:
        if any(w in low for w in words):
            return short
    return title


# Event names of outfits (card id -> name), matched from the list of alts with the card names in umdb.json.
# Only the ones that are certain. Everything else uses the card name, or what you put in images/outfits.json.
CARD_EVENTS = {
    100102: "Summer",        # Special Week, Hopp'n Happy Heart
    106802: "New Year",      # Kitasan Black, Crane's Ambition
    100202: "Summer",
    100402: "Summer",
    100802: "Christmas",
    101202: "Wedding",
    101602: "BLAZE",
    101902: "Halloween",
    102102: "Festival",
    102302: "Christmas",
    102702: "Valentine",
    103002: "Halloween",
    103402: "Festival",
    103702: "Valentine",
    103802: "Wedding",
    104502: "Halloween",
    105002: "Steampunk",
    105102: "Wedding",
    105202: "New Year",
    105302: "Summer Trip",
    105802: "Halloween",
    105902: "Camping",
    106102: "Cheerleader",
    106902: "Ballroom",
    107102: "Ballroom",
}


class CardTitles:
    """Official names of the outfit cards, read from Race Overlay's umdb.json (resources folder), for example
    card 100402 = "Hot☆Summer Night". It is only read when it is needed, and may be missing."""

    def __init__(self, paths_fn):
        self.paths_fn = paths_fn        # returns the places to look, best first
        self.titles = None
        self.source = ""

    def load(self):
        self.titles = {}
        for path in self.paths_fn():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                cards = d.get("card") or []
                self.titles = {int(c["id"]): str(c.get("name", "")).strip().strip("[]").strip()
                               for c in cards if isinstance(c, dict) and "id" in c}
                self.source = path
                break
            except Exception:
                continue

    def title(self, card_id):
        if self.titles is None:
            self.load()
        try:
            return short_outfit_name(self.titles.get(int(card_id), ""))
        except (TypeError, ValueError):
            return ""


# The race gives the outfit as a dress id = uma id * 100 + a number. For a normal event outfit that number
# is the same for every uma (30 = Summer for Special Week, Maruzensky, Gold Ship...; seen in your own outfits.json).
# A number below 10 means the dress id is the card id itself (100102 = card 100102).
SUFFIX_EVENTS = {
    10: "New Year", 16: "Steampunk", 20: "Ballroom", 23: "Camping", 26: "Wedding", 30: "Summer",
    40: "Halloween", 43: "Festival", 46: "Christmas", 50: "Cheerleader",
}


def is_alt_outfit(chara_id, dress_id):
    """True when the dress is another outfit of this uma (not her normal one, and not a made-up id of a background runner)."""
    if not (chara_id and dress_id):
        return False
    chara, dress = int(chara_id), int(dress_id)
    return dress // 100 == chara and dress != chara * 100 + 1


class OutfitsDB:
    """images/outfits.json - every alternative outfit seen in a race, and the name you gave it."""

    def __init__(self, path):
        self.path = path
        self.data = {}          # "105840" -> {"uma": "Meisho Doto", "label": "Halloween", "card": 105802}
        self.titles = None      # CardTitles: the official outfit names, when umdb.json is found
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

    def card_event(self, card_id):
        """The event name of a card when it is known ("Halloween"), else ""."""
        card_id = int(card_id)
        ev = CARD_EVENTS.get(card_id, "")
        if not ev and self.titles is not None:
            t = self.titles.title(card_id)
            raw = self.titles.titles.get(card_id, "") if self.titles.titles else ""
            if t and t != raw:                       # short_outfit_name found a theme in the title
                ev = t
        return ev

    def card_for(self, chara_id, dress_id, candidates=()):
        """The card (= the picture) of an outfit when the race only tells the dress id, or 0 when it cannot tell.
        candidates: card ids of this uma that exist on this computer (from the picture folders)."""
        chara, dress = int(chara_id or 0), int(dress_id or 0)
        if not is_alt_outfit(chara, dress):
            return 0
        suffix = dress % 100
        if suffix < 10:
            return dress
        cards = {int(c) for c in candidates} | {c for c in CARD_EVENTS if c // 100 == chara}
        if self.titles is not None:
            self.titles.title(0)                      # makes sure umdb.json is loaded
            cards |= {c for c in (self.titles.titles or {}) if c // 100 == chara}
        cards = sorted(c for c in cards if c // 100 == chara and c != chara * 100 + 1)
        event = SUFFIX_EVENTS.get(suffix, "")
        if event:
            for c in cards:
                if self.card_event(c) == event:
                    return c
        unknown = [c for c in cards if not self.card_event(c)]
        if len(unknown) == 1 and (not event or len(cards) == 1 or all(not self.card_event(c) for c in cards)):
            return unknown[0]
        if not event and len(cards) == 1:
            return cards[0]
        if event and unknown:                        # an event outfit: the oldest card that has no other event
            return unknown[0]
        return 0

    def auto_label(self, dress_id, card_id=0):
        """The name the program finds by itself: the event of the outfit (Halloween, Summer...), else the official card name."""
        dress = int(dress_id or 0)
        if not card_id:
            card_id = (self.data.get(str(dress)) or {}).get("card", 0)
        auto = BUILTIN_OUTFITS.get(dress, "")
        if not auto and card_id:
            auto = CARD_EVENTS.get(int(card_id), "")
        if not auto and dress % 100 >= 10:
            auto = SUFFIX_EVENTS.get(dress % 100, "")
        if not auto and self.titles is not None and card_id:
            auto = self.titles.title(card_id)
        return auto

    def label_for(self, chara_id, dress_id, card_id=0):
        """"" for the default outfit, otherwise the outfit name: yours, else the official one,
        else "Alt" when nothing is known."""
        if not is_alt_outfit(chara_id, dress_id):
            return ""
        mine = (self.data.get(str(int(dress_id))) or {}).get("label", "").strip()
        return mine or self.auto_label(dress_id, card_id) or "Alt"

    def display(self, name, chara_id, dress_id, card_id=0):
        lab = self.label_for(chara_id, dress_id, card_id)
        return "%s (%s)" % (name, lab) if lab else name

    def touch(self, chara_id, dress_id, uma, card_id=0):
        """Remember an alternative outfit so it is saved in outfits.json. True if it is new."""
        if not is_alt_outfit(chara_id, dress_id):
            return False
        key = str(int(dress_id))
        if key in self.data:
            self.data[key]["uma"] = uma
            if card_id:
                self.data[key]["card"] = int(card_id)
            return False
        self.data[key] = {"uma": uma, "label": "", "card": int(card_id or 0)}
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
            out.append((did, v.get("uma", ""), v.get("label", ""), self.auto_label(did)))
        return sorted(out, key=lambda r: (r[1].lower(), r[0]))
