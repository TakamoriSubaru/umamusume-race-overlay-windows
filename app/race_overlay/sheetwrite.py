"""Sends the placings of a finished race to a Google Sheet (through a small Apps Script the sheet owner adds)."""

import json
import urllib.request

ALLOWED_PREFIX = "https://script.google.com/"

# The script the owner pastes into the sheet (Extensions > Apps Script). It also exists here so the program can copy it.
APPS_SCRIPT = r'''// Umalliance race overlay -> this Google Sheet.
// The overlay sends the finishing order of a race here and this script writes each player's placing into the
// "Placing" column of the Group Stage tab. Your own formulas do the rest.
//
// 1. Change the secret code below to anything you like (letters and numbers), and type the same code in the overlay.
// 2. Press Deploy > New deployment > type "Web app". Execute as: Me. Who has access: Anyone. Press Deploy and allow access.
// 3. Copy the "Web app" link (it ends in /exec) into the overlay: Points tab > Send placings to the Google Sheet.

var SECRET = "CHANGE-ME";
var TAB_PREFIX = "Group Stage Round ";   // the tabs are called "Group Stage Round 1", "Group Stage Round 2", ...
var HEADER_ROW = 4;                      // the row with Trainer / Discord / Uma / Style / Placing

function norm(s) {
  return String(s === null || s === undefined ? "" : s).normalize("NFKC").trim().toLowerCase();
}

function out(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}

function doGet() {
  return out({ ok: true, hello: "The race overlay link works." });
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(20000);
    return out(handle(JSON.parse(e.postData.contents)));
  } catch (err) {
    return out({ ok: false, error: String(err) });
  } finally {
    try { lock.releaseLock(); } catch (x) {}
  }
}

// every group block of the tab: where its Trainer / Discord / Placing columns are
function findBlocks(header) {
  var blocks = [];
  for (var c = 0; c < header.length; c++) {
    if (norm(header[c]) !== "trainer") continue;
    var b = { trainer: c, discord: -1, placing: -1 };
    for (var j = c + 1; j < header.length && norm(header[j]) !== "trainer"; j++) {
      if (norm(header[j]) === "discord" && b.discord < 0) b.discord = j;
      if (norm(header[j]) === "placing" && b.placing < 0) b.placing = j;
    }
    if (b.placing >= 0) blocks.push(b);
  }
  return blocks;
}

function handle(req) {
  if (req.secret !== SECRET) return { ok: false, error: "Wrong secret code." };
  var results = (req.results || []).filter(function (r) { return norm(r.name); });
  if (results.length < 2) return { ok: false, error: "Fewer than 2 players in the race." };
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TAB_PREFIX + req.round);
  if (!sheet) return { ok: false, error: 'No tab called "' + TAB_PREFIX + req.round + '".' };
  var data = sheet.getDataRange().getValues();
  var blocks = findBlocks(data[HEADER_ROW - 1] || []);
  if (!blocks.length) return { ok: false, error: "No Trainer / Placing headers found in row " + HEADER_ROW + "." };

  results.sort(function (a, b) { return a.place - b.place; });
  var placeOf = {};                                  // 1, 2, 3 ... among the named players of the race
  results.forEach(function (r, i) { placeOf[norm(r.name)] = i + 1; });

  // which group is this race? the block that has most of its players
  var best = null;
  blocks.forEach(function (b) {
    var rows = [];
    for (var r = HEADER_ROW; r < data.length; r++) {
      var row = data[r];
      var t = norm(row[b.trainer]), d = b.discord >= 0 ? norm(row[b.discord]) : "";
      if (!t && !d) { if (rows.length) break; else continue; }
      var key = placeOf[t] ? t : (placeOf[d] ? d : "");
      rows.push({ row: r, key: key });
    }
    var hits = rows.filter(function (x) { return x.key; }).length;
    if (!best || hits > best.hits) best = { b: b, rows: rows, hits: hits };
  });
  if (!best || best.hits === 0) {
    return { ok: false, error: "Nobody of this race is in the Round " + req.round + " tab. Check the round and the names." };
  }

  var written = 0, existing = [], seen = {};
  best.rows.forEach(function (x) {
    if (!x.key) return;
    seen[x.key] = true;
    var cell = sheet.getRange(x.row + 1, best.b.placing + 1);
    if (String(cell.getValue()).trim() !== "") { existing.push(data[x.row][best.b.trainer]); return; }
    cell.setValue(placeOf[x.key]);
    written++;
  });
  var missing = results.filter(function (r) { return !seen[norm(r.name)]; }).map(function (r) { return r.name; });
  var group = String((data[HEADER_ROW - 2] || [])[best.b.trainer] || "").trim();
  return { ok: true, group: group, written: written, existing: existing, missing: missing };
}
'''


def check_url(url):
    url = (url or "").strip()
    if not url.startswith(ALLOWED_PREFIX) or "/exec" not in url:
        raise ValueError("The link must be the Web app link from Google (it starts with https://script.google.com/ "
                         "and ends in /exec).")
    return url


def build_payload(secret, round_no, entries):
    """entries: [{"name", "place"}] of the named players. The placing sent is the order among them."""
    named = [{"name": str(e["name"]), "place": int(e["place"])} for e in entries if str(e.get("name", "")).strip()]
    return {"secret": secret, "round": int(round_no), "results": named}


def post(url, payload, timeout=40):
    """POST the payload and return the answer of the script as a dict. (Google answers with a redirect that
    urllib follows by itself.)"""
    url = check_url(url)
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "text/plain;charset=utf-8"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
    try:
        return json.loads(body)
    except ValueError:
        raise ValueError("Google did not answer like the script. Check that it is deployed as a Web app with "
                         "access for Anyone, and that the link is the newest deployment.")


def ping(url, timeout=25):
    """GET the link: the script answers {"ok": true} when it is set up."""
    url = check_url(url)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
    try:
        return json.loads(body)
    except ValueError:
        raise ValueError("The link did not answer like the script (is it deployed for Anyone?).")


def describe(res):
    """One friendly line for the status label."""
    if not isinstance(res, dict):
        return "No answer."
    if not res.get("ok"):
        return "Not sent: %s" % res.get("error", "unknown error")
    bits = ["%s: %d placing%s written" % (res.get("group") or "group", res.get("written", 0), "" if res.get("written") == 1 else "s")]
    if res.get("existing"):
        bits.append("%d already had a placing (not changed): %s" % (len(res["existing"]), ", ".join(res["existing"][:4])))
    if res.get("missing"):
        bits.append("not found in the sheet: %s" % ", ".join(res["missing"][:4]))
    return "; ".join(bits) + "."
