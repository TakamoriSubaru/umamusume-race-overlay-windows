"""Reads a score table from a Google Sheet (link), a .csv file or a .xlsx file.

No account and no extra packages: a Google Sheet must be shared as "Anyone with the link can view"
(or published to the web); the program then downloads it as CSV."""

import csv
import io
import os
import re
import zipfile
import xml.etree.ElementTree as ET

from .scoring import rank_rows
from .util import http_get


def col_index(letter):
    """'A' -> 0, 'B' -> 1, 'AA' -> 26. Returns None for anything that is not a column letter."""
    s = str(letter or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{1,3}", s):
        return None
    n = 0
    for ch in s:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def google_csv_url(link):
    """Turn a normal Google Sheets link into its CSV download link. Returns None if it is not one."""
    m = re.search(r"docs\.google\.com/spreadsheets/d/(?:e/)?([A-Za-z0-9_-]+)", link or "")
    if not m:
        return None
    sid = m.group(1)
    g = re.search(r"[?#&]gid=(\d+)", link)
    if "/d/e/" in link:                       # "publish to the web" link
        url = "https://docs.google.com/spreadsheets/d/e/%s/pub?output=csv" % sid
        return url + ("&gid=" + g.group(1) if g else "")
    return "https://docs.google.com/spreadsheets/d/%s/export?format=csv%s" % (sid, "&gid=" + g.group(1) if g else "")


def parse_csv(text):
    return [row for row in csv.reader(io.StringIO(text))]


def _xlsx_rows(path, sheet=""):
    """Tiny .xlsx reader (values only, no formulas)."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
                shared.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])))
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        targets = {r.get("Id"): r.get("Target") for r in rels}
        sheets = [(s.get("name"), targets.get(s.get(rel))) for s in wb.find("m:sheets", ns)]
        if not sheets:
            return []
        pick = next((s for s in sheets if sheet and s[0].strip().lower() == sheet.strip().lower()), sheets[0])
        t = pick[1].lstrip("/")
        t = t if t.startswith("xl/") else "xl/" + t
        rows = []
        for row in ET.fromstring(z.read(t)).iter("{%s}row" % ns["m"]):
            cells = {}
            for c in row.findall("m:c", ns):
                ci = col_index(re.sub(r"\d+", "", c.get("r", "")))
                if ci is None:
                    continue
                v = c.find("m:v", ns)
                if c.get("t") == "s" and v is not None:
                    val = shared[int(v.text)]
                elif c.get("t") == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter("{%s}t" % ns["m"]))
                else:
                    val = v.text if v is not None and v.text is not None else ""
                cells[ci] = val
            r_no = int(row.get("r", len(rows) + 1))
            while len(rows) < r_no - 1:
                rows.append([])
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
        return rows


def load_rows(source, sheet=""):
    """source = Google Sheets link, other web link to a CSV, or a path to .csv / .xlsx. Returns rows of text."""
    source = (source or "").strip().strip('"')
    if not source:
        raise ValueError("No sheet chosen yet.")
    if re.match(r"https?://", source):
        url = google_csv_url(source) or source
        data = http_get(url, timeout=20)
        text = data.decode("utf-8-sig", "replace") if isinstance(data, bytes) else str(data)
        if text.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
            raise ValueError("Google wants a sign-in. Share the sheet as \"Anyone with the link can view\".")
        return parse_csv(text)
    path = os.path.expanduser(source)
    if not os.path.isfile(path):
        raise ValueError("File not found: " + path)
    if path.lower().endswith((".xlsx", ".xlsm")):
        return _xlsx_rows(path, sheet)
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return parse_csv(f.read())


def to_number(text):
    t = str(text or "").strip().replace(",", ".").replace(" ", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return int(v) if v == int(v) else v


VIEWS = (("plain", "The columns above (no rounds)"), ("r1", "Round 1"), ("r2", "Round 2"), ("r3", "Round 3"),
         ("r12", "After Round 2"), ("r123", "Overall Total"))
VIEW_PICKS = {"r1": (0,), "r2": (1,), "r3": (2,), "r12": (0, 1), "r123": (0, 1, 2)}
SINGLE_VIEWS = ("plain", "r1", "r2", "r3")      # one list of points (the others add rounds up)


def view_title(view):
    return dict(VIEWS).get(view, "")


def parse_letters(text, per_group, groups=None):
    """'B,C,D; G,H,I' -> [['B','C','D'], ['G','H','I']]. Raises ValueError when it does not fit."""
    out = [[c.strip().upper() for c in g.split(",") if c.strip()] for g in str(text).split(";") if g.strip()]
    if not out or any(len(g) != per_group or any(col_index(c) is None for c in g) for g in out) \
            or (groups and len(out) != groups):
        raise ValueError("Columns must look like %s." % ("B,C,D; G,H,I; L,M,N" if per_group == 3 else "Q,R,S,T"))
    return out


def read_rounds(rows, name_col, round_cols, view, first_row=4):
    """One name column and one points column per round (the 'Final Rankings' block).
    `view` picks which rounds are added up: r1, r2, r3, r12 or r123."""
    ni = col_index(name_col)
    cols = [col_index(c) for c in round_cols]
    picks = VIEW_PICKS.get(view)
    if ni is None or not picks or any(c is None for c in cols) or max(picks) >= len(cols):
        raise ValueError("Combined columns must look like Q,R,S,T (player, round 1, 2, 3).")
    out, started = [], False
    for r in rows[max(0, int(first_row) - 1):]:
        name = r[ni].strip() if ni < len(r) else ""
        vals = [to_number(r[cols[i]]) if cols[i] < len(r) else None for i in picks]
        if not name and all(v is None for v in vals):
            if started:
                break
            continue
        if not name or all(v is None for v in vals):
            continue
        started = True
        out.append({"name": name, "uma": "", "score": sum(v for v in vals if v is not None), "races": 0, "last": 0})
    return rank_rows(out)


OLD_DEFAULTS = ("B,C,D; G,H,I; L,M,N", "Q,R,S,T")      # earlier versions saved these; they mean "automatic"


def is_auto(text):
    t = str(text or "").strip().lower()
    return t in ("", "auto", "automatic") or str(text).strip().upper() in OLD_DEFAULTS


def _cells(row):
    return [str(c).strip().lower() for c in row]


def detect_layout(rows):
    """Find the tables by their header names instead of by column letters. Google leaves hidden columns
    out of its CSV, which moves every letter: the headers stay the same.
    Returns {"blocks": [(player, uma, points), ...], "final": (player, r1, r2, r3) or None, "first_row": n}."""
    for ri, row in enumerate(rows[:20]):
        c = _cells(row)
        if "trainer" not in c and "member" not in c:
            continue
        blocks = []
        for i, name in enumerate(c):
            if name != "trainer":
                continue
            uma = next((j for j in range(i + 1, min(i + 4, len(c))) if c[j] == "uma"), None)
            score = next((j for j in range(i + 1, min(i + 5, len(c))) if c[j] in ("score", "points", "pts")), None)
            if score is not None:
                blocks.append((i, uma, score))
        final = None
        if "member" in c:
            m = c.index("member")
            rs = [next((j for j in range(m + 1, len(c)) if c[j] == "round %d" % k), None) for k in (1, 2, 3)]
            if all(r is not None for r in rs):
                final = (m,) + tuple(rs)
        if blocks or final:
            return {"blocks": blocks, "final": final, "first_row": ri + 2}     # first_row is 1-based
    return None


def _letter(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def drop_zero(rows_out, hide):
    out = [r for r in rows_out if not (hide and r["score"] <= 0)]
    return rank_rows(out)


def read_view(rows, s):
    """The list to show for the chosen view. s = the program's settings."""
    view = s.get("standings_view", "plain")
    hide = bool(s.get("standings_hide_zero", True))
    first = s.get("standings_first_row", 4)
    if view == "plain":
        return drop_zero(read_standings(rows, s.get("standings_name_col", "B"), s.get("standings_score_col", "D"),
                                        s.get("standings_uma_col", "C"), first), hide)
    auto = None
    if view in ("r1", "r2", "r3"):
        text = s.get("standings_round_blocks", "auto")
        if is_auto(text):
            auto = detect_layout(rows)
            k = VIEW_PICKS[view][0]
            if not auto or len(auto["blocks"]) <= k:
                raise ValueError("Could not find the Round %d table. Look for the headers Trainer / Uma / Score "
                                 "or type the columns by hand." % (k + 1))
            name, uma, score = auto["blocks"][k]
            return drop_zero(read_standings(rows, _letter(name), _letter(score),
                                            _letter(uma) if uma is not None else "", auto["first_row"]), hide)
        name, uma, score = parse_letters(text, 3, 3)[VIEW_PICKS[view][0]]
        return drop_zero(read_standings(rows, name, score, uma, first), hide)
    text = s.get("standings_total_cols", "auto")
    if is_auto(text):
        auto = detect_layout(rows)
        if not auto or not auto["final"]:
            raise ValueError("Could not find the Final Rankings table (headers Member / Round 1 / Round 2 / Round 3). "
                             "Type the columns by hand.")
        cols = [_letter(i) for i in auto["final"]]
        return drop_zero(read_rounds(rows, cols[0], cols[1:], view, auto["first_row"]), hide)
    cols = parse_letters(text, 4, 1)[0]
    return drop_zero(read_rounds(rows, cols[0], cols[1:], view, first), hide)


def read_standings(rows, name_col="B", score_col="D", uma_col="C", first_row=4):
    """Pick the player / score columns out of the table. Rows without a name or without a number are skipped
    (headers, empty lines, notes). Reading stops at the first fully empty row after the list started."""
    ni, si, ui = col_index(name_col), col_index(score_col), col_index(uma_col)
    if ni is None or si is None:
        raise ValueError("Column letters must look like B or D.")
    out, started = [], False
    for r in rows[max(0, int(first_row) - 1):]:
        get = lambda i: (r[i].strip() if i is not None and i < len(r) else "")
        name, score = get(ni), to_number(get(si))
        if not name and score is None:
            if started:
                break
            continue
        if not name or score is None:
            continue
        started = True
        out.append({"name": name, "uma": get(ui), "score": score, "races": 0, "last": 0})
    return rank_rows(out)
