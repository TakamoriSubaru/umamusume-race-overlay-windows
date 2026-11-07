"""Points per race and the score book (a small file that remembers every race you scored).

Rule (like "stage points" in NASCAR): with N players, 1st place gets N points, 2nd gets N-1 ...
and the last one gets 1. Players that tie share the same place, so they get the same points."""

import csv
import json
import os
import time
import unicodedata

from .constants import CONFIG_DIR

SCORES_FILE = os.path.join(CONFIG_DIR, "scores.json")


def points_for(place, n, bonus_winner=0):
    """Points for `place` (1 = winner) in a race with `n` players."""
    pts = max(0, int(n) - int(place) + 1)
    if place == 1:
        pts += int(bonus_winner)
    return pts


def norm_name(name):
    """One spelling for a name, so 'Takamori ' and 'takamori' are the same player."""
    return unicodedata.normalize("NFKC", str(name or "")).strip().casefold()


def strip_club_tag(name):
    """'CLUB｜Name' and '[CLUB] Name' become 'Name' (the name is kept when nothing would be left)."""
    s = str(name or "")
    for sep in ("｜", "|"):
        if sep in s:
            s = s.split(sep)[-1]
    if s.lstrip().startswith("[") and "]" in s:
        s = s.split("]", 1)[-1]
    s = s.strip()
    return s or str(name or "").strip()


def rank_rows(rows):
    """rows: dicts with 'score'. Sorts best first and numbers them 1, 2, 3 ... (equal points keep the
    order they came in, so the numbers never repeat)."""
    rows = sorted(rows, key=lambda r: -r["score"])
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows


class ScoreBook:
    def __init__(self, path=SCORES_FILE):
        self.path = path
        self.races = []
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.races = [r for r in d.get("races", []) if isinstance(r, dict) and r.get("results")]
        except Exception:
            self.races = []

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"races": self.races}, f, indent=1, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception as e:
            print("could not save scores.json:", e)

    @staticmethod
    def race_id(results):
        """The same race always gets the same id, so a replayed file is never counted twice."""
        parts = sorted("%s|%s|%s" % (norm_name(r["name"]), r.get("uma", ""), r.get("time", "")) for r in results)
        return "||".join(parts)

    def add_race(self, entries, title="", bonus_winner=0, when=None):
        """entries: [{"name", "uma", "place", "time"}]. Returns the scored race (with points) or None if
        it was already counted or has no named players."""
        entries = [e for e in entries if norm_name(e.get("name"))]
        if len(entries) < 2:
            return None
        n = len(entries)
        res = [{"name": e["name"], "uma": e.get("uma", ""), "place": int(e["place"]),
                "time": e.get("time", ""), "points": points_for(int(e["place"]), n, bonus_winner)}
               for e in entries]
        rid = self.race_id(res)
        if any(r.get("id") == rid and time.time() - r.get("at", 0) < 6 * 3600 for r in self.races[-5:]):
            return None
        race = {"id": rid, "at": when or time.time(), "title": title, "results": res}
        self.races.append(race)
        self.save()
        return race

    def undo_last(self):
        if self.races:
            self.races.pop()
            self.save()
            return True
        return False

    def clear(self):
        self.races = []
        self.save()

    def totals(self):
        """Best first: [{'name', 'uma', 'score', 'races', 'last', 'rank'}]."""
        acc = {}
        for ri, race in enumerate(self.races):
            for r in race["results"]:
                k = norm_name(r["name"])
                a = acc.setdefault(k, {"name": r["name"], "uma": "", "score": 0, "races": 0, "last": 0})
                a["name"] = r["name"]
                a["uma"] = r.get("uma", "")
                a["score"] += int(r["points"])
                a["races"] += 1
                a["last"] = int(r["points"]) if ri == len(self.races) - 1 else 0
        return rank_rows(list(acc.values()))

    def export_races(self, path):
        """Every counted race in one file, to send to a friend (Add races from a file...)."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"format": "uma-race-overlay-scores", "races": self.races}, f, indent=1, ensure_ascii=False)

    def import_races(self, path):
        """Adds the races of a file made by export_races. A race that is already counted (same id) is skipped,
        so two friends who both saw round 2 never count it twice. Returns (added, skipped)."""
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        incoming = d.get("races") if isinstance(d, dict) else None
        if not isinstance(incoming, list):
            raise ValueError("This is not a races file made by this program.")
        have = {r.get("id") for r in self.races}
        added = skipped = 0
        for r in incoming:
            ok = isinstance(r, dict) and isinstance(r.get("results"), list) and r["results"] and all(
                isinstance(x, dict) and "name" in x and "points" in x for x in r["results"])
            if not ok:
                skipped += 1
                continue
            rid = r.get("id") or self.race_id(r["results"])
            if rid in have:
                skipped += 1
                continue
            have.add(rid)
            self.races.append({"id": rid, "at": float(r.get("at") or 0), "title": str(r.get("title", "")),
                               "results": [{"name": str(x["name"]), "uma": str(x.get("uma", "")), "place": int(x.get("place", 0)),
                                            "time": str(x.get("time", "")), "points": int(x["points"])} for x in r["results"]]})
            added += 1
        if added:
            self.races.sort(key=lambda r: r.get("at", 0))
            self.save()
        return added, skipped

    def export_csv(self, path):
        rows = self.totals()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Rank", "Player", "Points", "Races"])
            for r in rows:
                w.writerow([r["rank"], r["name"], r["score"], r["races"]])
