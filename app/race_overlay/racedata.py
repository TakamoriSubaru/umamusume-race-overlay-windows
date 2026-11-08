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


def _levels(raw):
    """{skill id: level} from a skill_array like [{"skill_id": 100191, "level": 5}, ...]."""
    out = {}
    for x in raw or []:
        if not isinstance(x, dict):
            continue
        try:
            sid, lv = int(x.get("skill_id")), int(x.get("level") or 0)
        except (TypeError, ValueError):
            continue
        if sid > 0 and sid not in out:
            out[sid] = lv
    return out


def read_race_file(path):
    """One saved race file (horseACT .json) -> a race record: who ran and which skills each uma brought.
    None when the file is not a race."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        at = os.path.getmtime(path)
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not isinstance(d.get("raceHorse"), list):
        return None
    runners = []
    for h in d["raceHorse"]:
        if not isinstance(h, dict):
            continue
        rdata = h.get("responseHorseData") or {}
        lv = _levels(rdata.get("skill_array"))
        name = h.get("charaName") or ""
        runners.append({"idx": h.get("horseIndex", len(runners)), "gate": h.get("postNumber"),
                        "trainer": h.get("trainerName") or rdata.get("trainer_name") or "", "uma": name, "label": name,
                        "place": h.get("finishOrder"), "time": "", "equipped": list(lv),
                        "levels": {str(k): v for k, v in lv.items()}})
    if not runners:
        return None
    key = "%s|%s" % (d.get("randomSeed"), "||".join(sorted("%s|%s" % (r["trainer"], r["uma"]) for r in runners)))
    return {"id": key, "at": at, "src": os.path.basename(path), "course": "", "runners": runners}


def records_from_paths(paths):
    """Race records from files and/or folders (folders are searched, including the folders inside).
    Returns (records, files looked at). The same race saved twice counts once."""
    files = []
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, names in os.walk(p):
                files += [os.path.join(root, n) for n in names if n.lower().endswith(".json")]
        elif os.path.isfile(p):
            files.append(p)
    seen, out = set(), []
    for fp in sorted(files):
        rec = read_race_file(fp)
        if rec and rec["id"] not in seen:
            seen.add(rec["id"])
            out.append(rec)
    return out, len(files)


def skill_tables(records, skills):
    """The sheets for the spreadsheet. All of it is about the skills each uma BROUGHT (not what activated):
    Who has what (one row per uma), Skill counts (how many umas brought each skill) and All skills (one row per skill per uma)."""
    def name(sid):
        return skills.get(sid, {}).get("name") or str(sid)

    def rarity(sid):
        r = skills.get(sid, {}).get("rarity")
        return RARITY.get(r, r or "")

    who, allrows, count = [], [], {}
    for n, r in enumerate(sorted(records, key=lambda x: (x.get("at", 0), x.get("src", ""))), 1):
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(r.get("at", 0)))
        for u in sorted(r["runners"], key=lambda x: (x.get("place") or 99, x.get("idx", 0))):
            eq = u.get("equipped") or []
            lv = u.get("levels") or {}
            label = u.get("label") or u.get("uma")
            labels = []
            for sid in eq:
                level = lv.get(str(sid))
                labels.append(name(sid) + (" (Lvl %s)" % level if level and level > 1 else ""))
                allrows.append([n, when, u.get("place"), u.get("trainer"), label, sid, name(sid), rarity(sid), level or ""])
                count.setdefault(sid, []).append(u.get("trainer") or label)
            who.append([n, when, r.get("src", "live race"), u.get("place"), u.get("gate"), u.get("trainer"), label, len(eq),
                        ", ".join(labels)])
    crow = []
    for sid, people in sorted(count.items(), key=lambda kv: (-len(kv[1]), name(kv[0]).lower())):
        tally = {}
        for p in people:
            tally[p] = tally.get(p, 0) + 1
        crow.append([name(sid), rarity(sid), len(people),
                     ", ".join(p if k == 1 else "%s (%d)" % (p, k) for p, k in tally.items()), sid])
    return [
        ("Who has what", ["Race", "Date", "File", "Place", "Gate", "Trainer", "Uma", "Skills", "Skills they brought"], who),
        ("Skill counts", ["Skill", "Rarity", "Umas that brought it", "Who", "Skill id"], crow),
        ("All skills", ["Race", "Date", "Place", "Trainer", "Uma", "Skill id", "Skill", "Rarity", "Level"], allrows),
    ]


def export_skills_xlsx(path, records, skills):
    write_xlsx(path, skill_tables(records, skills))
