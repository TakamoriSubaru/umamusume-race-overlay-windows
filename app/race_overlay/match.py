"""Team match (draft): two teams, a few players each. After every race the best placed team players score
points for their team (4, 2 and 1 by default) and the first team to reach the target (25) wins.

Only players that are on a team can score. Everybody else (NPCs, players of nobody's team) is skipped, so
"the next eligible finisher takes the placement" happens by itself. Everything is saved in match.json."""

import csv
import json
import os
import time

from .constants import CONFIG_DIR
from .scoring import ScoreBook, norm_name

MATCH_FILE = os.path.join(CONFIG_DIR, "match.json")

DEFAULT_TEAMS = [
    {"name": "Team 1", "color": "#4aa3ff", "players": [], "picks": []},
    {"name": "Team 2", "color": "#ff6b81", "players": [], "picks": []},
]


def parse_points(text, default=(4, 2, 1)):
    """'4,2,1' -> [4, 2, 1]. Anything unreadable gives the default."""
    out = []
    for part in str(text or "").replace(";", ",").replace(" ", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            return list(default)
    return out[:10] or list(default)


def clean_lines(value):
    """A list of names from a list or from text with one name per line (empty lines and doubles go away)."""
    if isinstance(value, str):
        value = value.splitlines()
    out, seen = [], set()
    for v in value or []:
        v = str(v).strip()
        if v and norm_name(v) not in seen:
            seen.add(norm_name(v))
            out.append(v)
    return out


class Match:
    def __init__(self, path=MATCH_FILE):
        self.path = path
        self.teams = [dict(t, players=list(t["players"]), picks=list(t["picks"])) for t in DEFAULT_TEAMS]
        self.target = 25
        self.points = [4, 2, 1]
        self.races = []          # a scored race, or a hand-made change: {"manual": True, "note", "delta": [a, b]}
        self.load()

    # ----- saving -----------------------------------------------------------------------
    def load(self):
        if not self.path:
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            return
        try:
            for i, t in enumerate((d.get("teams") or [])[:2]):
                self.teams[i]["name"] = str(t.get("name") or self.teams[i]["name"])[:40]
                self.teams[i]["color"] = str(t.get("color") or self.teams[i]["color"])
                self.teams[i]["players"] = clean_lines(t.get("players"))
                self.teams[i]["picks"] = clean_lines(t.get("picks"))
            self.target = max(1, int(d.get("target", 25)))
            self.points = parse_points(",".join(str(x) for x in d.get("points", [4, 2, 1])))
            self.races = [r for r in d.get("races", []) if isinstance(r, dict) and len(r.get("delta") or []) == 2]
        except Exception as e:
            print("could not read match.json:", e)

    def save(self):
        if not self.path:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"teams": self.teams, "target": self.target, "points": self.points,
                           "races": self.races}, f, indent=1, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception as e:
            print("could not save match.json:", e)

    @classmethod
    def sample(cls):
        """A made-up match (nothing saved), to place and style the board before a real match."""
        m = cls(path=None)
        m.teams = [{"name": "Team Sakura", "color": "#f381a2", "players": ["Trainer A", "Trainer B", "Trainer C"],
                    "picks": ["Special Week", "Tokai Teio", "Silence Suzuka", "Mejiro McQueen", "Oguri Cap",
                              "Gold Ship"]},
                   {"name": "Team Mint", "color": "#74d27c", "players": ["Trainer D", "Trainer E", "Trainer F"],
                    "picks": ["Vodka", "Daiwa Scarlet", "Grass Wonder", "El Condor Pasa", "Taiki Shuttle",
                              "Rice Shower"]}]
        m.races = [{"delta": [7, 0], "results": [], "title": ""}, {"delta": [2, 5], "results": [], "title": ""},
                   {"delta": [4, 3], "results": [], "title": ""}]
        return m

    # ----- teams and rules ----------------------------------------------------------------
    def set_team(self, i, name=None, color=None, players=None, picks=None):
        t = self.teams[i]
        if name is not None:
            t["name"] = name.strip()[:40] or DEFAULT_TEAMS[i]["name"]
        if color:
            t["color"] = color
        if players is not None:
            t["players"] = clean_lines(players)
        if picks is not None:
            t["picks"] = clean_lines(picks)
        self.save()

    def set_rules(self, target=None, points=None):
        if target is not None:
            self.target = max(1, int(target))
        if points is not None:
            self.points = parse_points(points)
        self.save()

    def team_of(self, name):
        """0 or 1 for a player on that team, None for everybody else."""
        k = norm_name(name)
        if not k:
            return None
        for i, t in enumerate(self.teams):
            if any(norm_name(p) == k for p in t["players"]):
                return i
        return None

    def ready(self):
        """True when both teams have at least one player."""
        return all(t["players"] for t in self.teams)

    # ----- scoring --------------------------------------------------------------------------
    def score_entries(self, entries):
        """entries: [{"name", "uma", "place", "time"}] best first. Returns [{"name", "uma", "team", "rank",
        "points"}] for the players that are on a team, ranked 1, 2, 3 ... among themselves."""
        out = []
        for e in sorted(entries, key=lambda e: int(e.get("place", 99))):
            team = self.team_of(e.get("name"))
            if team is None:
                continue
            rank = len(out) + 1
            pts = self.points[rank - 1] if rank <= len(self.points) else 0
            out.append({"name": e["name"], "uma": e.get("uma", ""), "team": team, "rank": rank,
                        "points": pts, "place": int(e.get("place", rank)), "time": e.get("time", "")})
        return out

    def add_race(self, entries, title=""):
        """Score a race for the teams. Returns the race (with 'delta') or None when nobody on a team ran, or
        when this very race was already counted."""
        res = self.score_entries(entries)
        if not res:
            return None
        rid = ScoreBook.race_id([{"name": e["name"], "uma": e.get("uma", ""), "time": e.get("time", "")}
                                 for e in entries if norm_name(e.get("name"))])
        if any(r.get("id") == rid and time.time() - r.get("at", 0) < 6 * 3600 for r in self.races[-5:]):
            return None
        delta = [0, 0]
        for r in res:
            delta[r["team"]] += r["points"]
        race = {"id": rid, "at": time.time(), "title": title, "results": res, "delta": delta}
        self.races.append(race)
        self.save()
        return race

    def adjust(self, team, points, note=""):
        """A ruling by hand (dispute, remake, penalty): add or take away points for a team."""
        delta = [0, 0]
        delta[int(team)] = int(points)
        self.races.append({"manual": True, "at": time.time(), "note": note, "delta": delta})
        self.save()

    def undo_last(self):
        if self.races:
            self.races.pop()
            self.save()
            return True
        return False

    def new_match(self):
        """Forget the races and rulings; the teams, players and picks stay."""
        self.races = []
        self.save()

    # ----- reading ---------------------------------------------------------------------------
    def totals(self):
        a = sum(int(r["delta"][0]) for r in self.races)
        b = sum(int(r["delta"][1]) for r in self.races)
        return [a, b]

    def winner(self):
        """The first team that reached the target (the higher one when both pass it in the same race), else None."""
        a = b = 0
        for r in self.races:
            a += int(r["delta"][0])
            b += int(r["delta"][1])
            if (a >= self.target or b >= self.target) and a != b:
                return 0 if a > b else 1
        return None

    def race_rows(self):
        """[(label, delta_a, delta_b)] oldest first: 'R1', 'R2' ... and 'Ruling' for changes by hand."""
        out, n = [], 0
        for r in self.races:
            if r.get("manual"):
                out.append(("Ruling", int(r["delta"][0]), int(r["delta"][1])))
            else:
                n += 1
                out.append(("R%d" % n, int(r["delta"][0]), int(r["delta"][1])))
        return out

    def race_count(self):
        return sum(1 for r in self.races if not r.get("manual"))

    def export_csv(self, path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Race", self.teams[0]["name"], self.teams[1]["name"]])
            for label, da, db in self.race_rows():
                w.writerow([label, da, db])
            a, b = self.totals()
            w.writerow(["Total", a, b])
