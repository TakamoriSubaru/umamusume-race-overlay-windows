"""Why did a skill that an uma brought not activate? The game does not save that, so this works it out from the
race: it checks the skill's condition (from umdb.json) against where every uma was at every moment.
Three answers, never more sure than the data allows:
  "cond"    the condition was never true in this race (sure, as far as the condition uses things we can see)
  "wit"     the condition could be met, so most likely the wit check failed (a guess, not sure)
  "unknown" the condition needs things the race file does not hold (corners, slopes, random places ...)"""

import re

TERM = re.compile(r"^([a-z_0-9]+)(==|!=|<=|>=|<|>)(-?\d+)$")
STYLE = ("", "Front", "Pace", "Late", "End")
DIST = ("", "Short", "Mile", "Medium", "Long")
GROUND = ("", "Turf", "Dirt")
LABELS = {"order": "place", "order_rate": "place in the field (%)", "distance_rate": "race progress (%)",
          "remain_distance": "metres left", "hp_per": "stamina (%)", "bashin_diff_infront": "gap to the uma in front",
          "bashin_diff_behind": "gap to the uma behind", "post_number": "gate", "popularity": "popularity"}
NEEDS = {"corner": "a corner", "is_finalcorner": "the final corner", "slope": "a slope", "up_slope_random": "an uphill",
         "phase_random": "a random place in the race", "phase_firsthalf_random": "a random place in the race",
         "phase_laterhalf_random": "a random place in the race", "straight_random": "a random straight",
         "all_corner_random": "a random corner", "corner_random": "a random corner", "is_lastspurt": "the last spurt",
         "is_overtake": "an overtake", "change_order_onetime": "a change of place", "accumulatetime": "race time",
         "track_id": "the track", "rotation": "the track direction", "is_move_lane": "a lane change",
         "blocked_side_continuetime": "being blocked", "blocked_front_continuetime": "being blocked",
         "temptation_count": "temptation", "distance_diff_top": "the distance to the leader", "near_count": "umas nearby",
         "is_behind_in": "being behind", "is_badstart": "the start", "random_lot": "a random roll"}
NAME_MAPS = {"distance_type": {"short": 1, "mile": 2, "medium": 3, "long": 4},
             "ground_condition": {"good": 1, "yielding": 2, "soft": 3, "heavy": 4},
             "weather": {"sunny": 1, "cloudy": 2, "rainy": 3, "snowy": 4},
             "season": {"spring": 1, "summer": 2, "autumn": 3, "fall": 3, "winter": 4}}


def parse(cond):
    """'a>1&b<2@c==3' -> [[(a,>,1),(b,<,2)], [(c,==,3)]]  (a list of alternatives, each a list of terms that all must hold)."""
    out = []
    for alt in (cond or "").split("@"):
        terms = []
        for t in alt.split("&"):
            m = TERM.match(t.strip())
            terms.append((m.group(1), m.group(2), int(m.group(3))) if m else (t.strip(), None, None))
        out.append(terms)
    return out


def _cmp(a, op, b):
    return {"==": a == b, "!=": a != b, "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]


def term_true(term, st):
    """True / False / None (not known)."""
    name, op, val = term
    cands = st.get(name)
    if op is None or cands is None:
        return None
    res = {_cmp(c, op, val) for c in cands}
    return res.pop() if len(res) == 1 else None


def and_(vals):
    if any(v is False for v in vals):
        return False
    return True if all(v is True for v in vals) else None


def or_(vals):
    if any(v is True for v in vals):
        return True
    return False if all(v is False for v in vals) else None


def expr_value(groups, st):
    """groups = list of condition strings of one skill (any of them can make it activate)."""
    return or_([or_([and_([term_true(t, st) for t in alt]) for alt in parse(c)]) for c in groups])


def friendly(term, runner_style):
    name, op, val = term
    if name == "running_style" and op in ("==", "!="):
        return "needs %s style (she ran %s)" % (STYLE[val], runner_style) if op == "==" else "not for %s style" % STYLE[val]
    if name == "distance_type" and op in ("==", "!="):
        return ("needs a %s race" if op == "==" else "not for a %s race") % DIST[val].lower() if 0 < val < 5 else "needs another distance"
    if name == "ground_type" and op in ("==", "!="):
        return ("needs %s" if op == "==" else "not on %s") % GROUND[val] if 0 < val < 3 else "needs another ground"
    if name in ("ground_condition", "weather", "season"):
        return "needs other %s" % name.replace("_", " ")
    sym = {"==": "=", "!=": "not", "<=": "<=", ">=": ">=", "<": "<", ">": ">"}[op] if op else "?"
    return "%s %s %s" % (LABELS.get(name, name.replace("_", " ")), sym, val)


def static_state(info, style, gate, popularity, total):
    st = {"always": [1], "running_style": [int(style or 0)], "post_number": [int(gate or 0)]}
    info = info or {}
    for key, name in (("distType", "distance_type"), ("ground", "ground_condition"), ("weather", "weather"), ("season", "season")):
        v = NAME_MAPS[name].get(str(info.get(key) or "").strip().lower())
        if v:
            st[name] = [v]
    surf = str(info.get("surface") or "").lower()
    if surf in ("turf", "dirt"):
        st["ground_type"] = [1 if surf == "turf" else 2]
    if total:
        st["is_basis_distance"] = [1 if int(total) % 400 == 0 else 0]
    if popularity:
        st["popularity"] = [int(popularity)]
    return st


def samples(data, steps=4):
    """Times to look at: every frame time and a few moments between the frames."""
    ts = []
    base = data["times"]
    for k, t in enumerate(base):
        ts.append(t)
        if k + 1 < len(base):
            for s in range(1, steps + 1):
                ts.append(t + (base[k + 1] - t) * s / float(steps + 1))
    return ts


def _lin(xs, ys, x):
    import bisect
    if not xs:
        return None
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect.bisect_left(xs, x)
    x0, x1 = xs[i - 1], xs[i]
    return ys[i] if x1 == x0 else ys[i - 1] + (ys[i] - ys[i - 1]) * (x - x0) / (x1 - x0)


def analyse(data, recs, info):
    """Fills runner["hit"], runner["miss"], runner["wit_chance"] for every runner of the analysis data."""
    runners, total = data["runners"], data["total"]
    ts = samples(data)
    n = len(runners)
    dist = []                                # dist[j][s]: how far runner j was at sample s
    hp = []
    for r in runners:
        dist.append([total if (r["t"] and t > r["t"][-1]) else _lin(r["t"], r["dist"], t) for t in ts])
        hp.append([_lin(r["t"], r["hp"], t) if r["hp"] else None for t in ts])
    order = []                               # order[j][s]: 1 = leading
    for s in range(len(ts)):
        col = sorted(range(n), key=lambda j: (-(dist[j][s] or 0.0), j))
        row = [0] * n
        for pos, j in enumerate(col):
            row[j] = pos + 1
        order.append(row)
    for j, r in enumerate(runners):
        stt = static_state(data.get("info"), r["h"].style, r["h"].gate, r.get("popularity"), total)
        wit = ((r.get("stats") or {}).get("WitBase") or (r.get("stats") or {}).get("Wit"))
        r["wit_chance"] = max(20.0, 100.0 - 9000.0 / float(wit)) if wit else None
        hit_ids = {a["id"] for a in r["acts"]}
        r["hit"], r["miss"] = [], []
        first = {}
        for a in r["acts"]:
            e = first.setdefault(a["id"], {"id": a["id"], "name": a["name"], "t": a["t"], "dist": a["dist"], "count": 0})
            e["count"] += 1
        r["hit"] = sorted(first.values(), key=lambda e: e["t"])
        h0 = r.get("hp0")
        for sid in dict.fromkeys(r["brought"]):
            if sid in hit_ids:
                continue
            rec = recs.get(sid) or {}
            name = rec.get("name") or ("Skill %d" % sid)
            groups = [g.get("condition") or "" for g in (rec.get("conditionGroups") or [])]
            item = {"id": sid, "name": name, "kind": "unknown", "text": "can't tell"}
            if not groups:
                item["text"] = "no condition known"
                r["miss"].append(item)
                continue
            ever_true, any_unknown = False, False
            term_ever = {}
            unknown_names = set()
            for s in range(len(ts)):
                d = dist[j][s]
                if d is None:
                    continue
                o = order[s][j]
                st = dict(stt)
                st["distance_rate"] = [d / total * 100.0]
                st["remain_distance"] = [total - d]
                st["order"] = [o]
                st["order_rate"] = [100.0 * o / n, 100.0 * (o - 1) / max(1, n - 1)]
                dr = d / total
                st["phase"] = [0] if dr < 1 / 6.0 else ([1] if dr < 2 / 3.0 else [2, 3])
                if h0 and hp[j][s] is not None:
                    st["hp_per"] = [100.0 * hp[j][s] / h0]
                ahead = [dist[k][s] for k in range(n) if k != j and dist[k][s] is not None and dist[k][s] > d]
                behind = [dist[k][s] for k in range(n) if k != j and dist[k][s] is not None and dist[k][s] < d]
                if ahead:
                    st["bashin_diff_infront"] = [(min(ahead) - d) / 2.5]
                if behind:
                    st["bashin_diff_behind"] = [(d - max(behind)) / 2.5]
                v = expr_value(groups, st)
                if v is True:
                    ever_true = True
                    break
                if v is None:
                    any_unknown = True
                for c in groups:
                    for alt in parse(c):
                        for t in alt:
                            tv = term_true(t, st)
                            term_ever[t] = term_ever.get(t, False) or (tv is True)
                            if tv is None:
                                unknown_names.add(t[0])
            if ever_true:
                if int(rec.get("activateLot") or 0) == 1:
                    item["kind"] = "wit"
                    item["text"] = ("probably the wit check (about %.0f%% to pass)" % r["wit_chance"]) if r["wit_chance"] else "probably the wit check"
                else:
                    item["text"] = "can't tell (this skill has no wit check)"
            elif not any_unknown:
                item["kind"] = "cond"
                first_alt = parse(groups[0])[0]
                bad = [t for t in first_alt if not term_ever.get(t, False)]
                item["text"] = "condition not met: " + (friendly(bad[0], r["style"]) if bad else "never all true together")
            else:
                need = [NEEDS.get(x) for x in sorted(unknown_names) if NEEDS.get(x)]
                item["text"] = "can't tell: needs %s" % (need[0] if need else "course details")
            r["miss"].append(item)
