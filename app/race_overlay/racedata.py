"""Saves what happened in every race (who ran, how they placed, which skills they brought and when each one
activated) and turns it into a spreadsheet (.xlsx, made here without any extra package)."""

import bisect
import json
import os
import time
import zipfile
from xml.sax.saxutils import escape

STYLE_NAMES = {1: "Front", 2: "Pace", 3: "Late", 4: "End"}
RARITY = {1: "Normal", 2: "Rare", 3: "Unique", 4: "Unique+", 5: "Unique++"}


def _num(v, nd=3):
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


class RaceLog:
    """One line of json per race in race-data.jsonl."""

    def __init__(self, path):
        self.path = path
        self.ids = None

    def _load_ids(self):
        if self.ids is None:
            self.ids = set(r.get("id") for r in self.records())
        return self.ids

    def records(self):
        out = []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            r = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(r, dict) and r.get("runners"):
                            out.append(r)
        except OSError:
            pass
        return out

    def count(self):
        return len(self.records())

    def add(self, rec):
        """Returns False when this exact race is already saved (a replayed file)."""
        ids = self._load_ids()
        if rec["id"] in ids:
            return False
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        ids.add(rec["id"])
        return True

    def clear(self):
        try:
            os.remove(self.path)
        except OSError:
            pass
        self.ids = set()


def build_record(horses, entries, info, line1, line2, skill_log, times, frames):
    """horses: the Horse objects; entries: results_entries() (place, time, gap per horse)."""
    info = info or {}
    total = _num(info.get("distance"), 1)
    by_h = {id(e["h"]): e for e in entries}
    runners = []
    for h in sorted(horses, key=lambda x: x.frame_idx):
        e = by_h.get(id(h), {})
        acts = []
        for horse, skill, t in skill_log:
            if horse != h.frame_idx:
                continue
            dist = None
            if times and frames and t is not None:
                k = min(max(bisect.bisect_left(times, t), 0), len(frames) - 1)
                row = frames[k]
                if h.frame_idx < len(row):
                    dist = _num(row[h.frame_idx][0], 1)
            acts.append({"id": int(skill), "time": _num(t, 2), "dist": dist,
                         "pct": round(100.0 * dist / total, 1) if dist is not None and total else None})
        runners.append({"idx": h.frame_idx, "gate": h.gate, "trainer": h.trainer, "uma": h.name, "label": h.label,
                        "card": h.card_id, "dress": h.dress_id, "style": h.style,
                        "place": e.get("place"), "time": e.get("time", ""), "gap": e.get("gap", ""),
                        "equipped": list(h.skills or []), "acts": acts})
    key = "||".join(sorted("%s|%s|%s" % (r["trainer"], r["uma"], r["time"]) for r in runners))
    return {"id": key, "at": time.time(), "course": line1, "course2": line2,
            "info": {k: info.get(k) for k in ("trackName", "surface", "distType", "distance", "direction", "ground", "weather", "season")},
            "runners": runners}


def load_skills(paths):
    """{skill id: info} from umdb.json (first file that exists)."""
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        out = {}
        for s in d.get("skill") or []:
            if isinstance(s, dict) and "id" in s:
                out[int(s["id"])] = s
        if out:
            return out
    return {}


def _cond(info):
    groups = info.get("conditionGroups") or []
    return " | ".join(g.get("condition", "") for g in groups if isinstance(g, dict))


def _effects(info):
    bits = []
    for g in info.get("conditionGroups") or []:
        for e in g.get("effects") or []:
            bits.append("%s:%s" % (e.get("type"), e.get("value")))
    return ", ".join(bits)


def tables(records, skills):
    """The four sheets as (name, header, rows)."""
    races, runners, srows = [], [], []
    stat = {}
    for n, r in enumerate(sorted(records, key=lambda x: x.get("at", 0)), 1):
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(r.get("at", 0)))
        inf = r.get("info") or {}
        races.append([n, when, r.get("course", ""), r.get("course2", ""), inf.get("trackName") or "", inf.get("surface") or "",
                      inf.get("distance") or "", inf.get("ground") or "", inf.get("weather") or "", inf.get("season") or "",
                      len(r["runners"])])
        for u in r["runners"]:
            eq = u.get("equipped") or []
            acted = {a["id"] for a in u.get("acts", [])}
            runners.append([n, when, u.get("place"), u.get("gate"), u.get("trainer"), u.get("label") or u.get("uma"),
                            STYLE_NAMES.get(u.get("style"), ""), u.get("time"), u.get("gap"),
                            len(eq) if eq else "", len(acted)])
            seen = set()
            for a in u.get("acts", []):
                info = skills.get(a["id"], {})
                srows.append([n, when, u.get("place"), u.get("trainer"), u.get("label") or u.get("uma"), a["id"],
                              info.get("name", ""), RARITY.get(info.get("rarity"), info.get("rarity") or ""),
                              "yes" if a["id"] in eq else ("no" if eq else "unknown"), a.get("time"), a.get("dist"), a.get("pct"),
                              info.get("gradeValue", ""), _cond(info), _effects(info)])
                s = stat.setdefault(a["id"], {"eq": 0, "hit": 0, "uses": 0, "dist": []})
                s["uses"] += 1
                if a["id"] not in seen:
                    seen.add(a["id"])
                    s["hit"] += 1
                if a.get("dist") is not None:
                    s["dist"].append(a["dist"])
            for sid in eq:                         # brought but never activated
                s = stat.setdefault(sid, {"eq": 0, "hit": 0, "uses": 0, "dist": []})
                s["eq"] += 1
                if sid not in acted:
                    info = skills.get(sid, {})
                    srows.append([n, when, u.get("place"), u.get("trainer"), u.get("label") or u.get("uma"), sid,
                                  info.get("name", ""), RARITY.get(info.get("rarity"), info.get("rarity") or ""),
                                  "yes", "", "", "", info.get("gradeValue", ""), _cond(info), _effects(info)])
    summary = []
    for sid, s in sorted(stat.items(), key=lambda kv: (-kv[1]["hit"], kv[0])):
        info = skills.get(sid, {})
        eq = s["eq"]
        summary.append([sid, info.get("name", ""), RARITY.get(info.get("rarity"), info.get("rarity") or ""), eq or "",
                        s["hit"], s["uses"], round(100.0 * s["hit"] / eq, 1) if eq else "",
                        round(sum(s["dist"]) / len(s["dist"]), 1) if s["dist"] else "", _cond(info)])
    return [
        ("Races", ["Race", "Date", "Course", "Details", "Track", "Surface", "Distance (m)", "Ground", "Weather", "Season", "Runners"], races),
        ("Runners", ["Race", "Date", "Place", "Gate", "Trainer", "Uma", "Style", "Finish time", "Gap", "Skills equipped", "Skills activated"], runners),
        ("Skills", ["Race", "Date", "Place", "Trainer", "Uma", "Skill id", "Skill", "Rarity", "Equipped", "Time (s)", "Distance (m)",
                    "Race progress (%)", "Grade value", "Condition", "Effects (type:value)"], srows),
        ("Skill summary", ["Skill id", "Skill", "Rarity", "Times equipped", "Races activated", "Activations", "Activation rate (%)",
                           "Average distance (m)", "Condition"], summary),
    ]


def _col(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _clean(text):
    return "".join(c for c in str(text) if c in "\t\n\r" or ord(c) >= 32)


def _sheet_xml(header, rows):
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
           '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>',
           "<cols>%s</cols>" % "".join('<col min="%d" max="%d" width="%d" customWidth="1"/>' % (i + 1, i + 1, 14 if i else 8)
                                       for i in range(len(header))),
           "<sheetData>"]

    def cell(ref, v, style=0):
        if v is None or v == "":
            return ""
        if isinstance(v, bool):
            v = "yes" if v else "no"
        if isinstance(v, (int, float)):
            return '<c r="%s" s="%d"><v>%s</v></c>' % (ref, style, repr(v))
        return '<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, style, escape(_clean(v)))

    out.append('<row r="1">%s</row>' % "".join(cell(_col(i) + "1", h, 1) for i, h in enumerate(header)))
    for n, row in enumerate(rows, 2):
        out.append('<row r="%d">%s</row>' % (n, "".join(cell("%s%d" % (_col(i), n), v) for i, v in enumerate(row))))
    out.append("</sheetData>")
    if header:
        out.append('<autoFilter ref="A1:%s%d"/>' % (_col(len(header) - 1), max(1, len(rows) + 1)))
    out.append("</worksheet>")
    return "".join(out)


def write_xlsx(path, sheets):
    """sheets: [(name, header, rows)]. A plain .xlsx with a bold header row, a frozen first row and filters."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + "".join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % (i + 1) for i in range(len(sheets)))
                   + "</Types>")
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   "</Relationships>")
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(name), i + 1, i + 1)
                             for i, (name, _h, _r) in enumerate(sheets))
                   + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1) for i in range(len(sheets)))
                   + '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>' % (len(sheets) + 1)
                   + "</Relationships>")
        z.writestr("xl/styles.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
                   '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
                   '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
                   '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                   '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
                   '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
                   '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
                   "</styleSheet>")
        for i, (_n, header, rows) in enumerate(sheets):
            z.writestr("xl/worksheets/sheet%d.xml" % (i + 1), _sheet_xml(header, rows))


def export_xlsx(path, records, skills):
    write_xlsx(path, tables(records, skills))


def race_tables(rec, skills):
    """ONE race, kept simple: every skill and how many umas of that race brought it (and who).
    When the race data does not list the skills each uma brought, it lists the skills that activated instead."""
    brought, active = {}, {}
    for u in rec["runners"]:
        who = u.get("trainer") or u.get("label") or u.get("uma")
        for sid in dict.fromkeys(u.get("equipped") or []):
            brought.setdefault(sid, []).append(who)
        for sid in dict.fromkeys(a["id"] for a in u.get("acts", [])):
            active.setdefault(sid, []).append(who)
    known = bool(brought)
    src = brought if known else active
    rows = []
    for sid in sorted(src, key=lambda i: (-len(src[i]), skills.get(i, {}).get("name", ""), i)):
        info = skills.get(sid, {})
        rows.append([info.get("name") or sid, len(src[sid]), ", ".join(src[sid])])
    head = ["Skill", "Umas that brought it" if known else "Umas it activated for", "Who"]
    return [("Skills in this race" if known else "Activated skills (brought: unknown)", head, rows)]
