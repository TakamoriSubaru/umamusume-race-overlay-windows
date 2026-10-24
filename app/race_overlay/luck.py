"""Skill luck: who triggered the most of the skills they brought, and who missed the most.

The race data lists every skill that really activated. A saved race file (and, when the server sends it,
live data) also lists the skills each trainer equipped. Hit = equipped and activated."""


def skill_ids(raw):
    """A list of skill ids from whatever the data gives: [123, ...] or [{"skill_id": 123, ...}, ...]."""
    out = []
    for x in raw or []:
        v = x.get("skill_id") if isinstance(x, dict) else x
        try:
            v = int(v)
        except (TypeError, ValueError):
            continue
        if v > 0 and v not in out:
            out.append(v)
    return out


def luck_table(horses, acts):
    """One row per uma: hit / total (total None when the equipped skills are not known).
    acts = {horse index: [skill ids that activated]}."""
    rows = []
    for h in horses:
        done = set(acts.get(h.frame_idx, []))
        eq = list(getattr(h, "skills", None) or [])
        if eq:
            hit = len([s for s in eq if s in done])
            total = len(eq)
        else:
            hit, total = len(done), None
        rows.append({"h": h, "hit": hit, "total": total, "missed": (total - hit) if total else 0})
    return rows


def pick(rows, per_side):
    """(luckiest, unluckiest, all_hit_names). Each list is best-first / worst-first and never shares an uma."""
    known = [r for r in rows if r["total"]]
    if known:
        key = lambda r: (r["hit"] / float(r["total"]), r["hit"])
        lucky = sorted(known, key=key, reverse=True)
        unlucky = sorted(known, key=lambda r: (r["hit"] / float(r["total"]), -r["missed"]))
    else:                                     # equipped skills unknown: count what activated
        lucky = sorted(rows, key=lambda r: r["hit"], reverse=True)
        unlucky = sorted(rows, key=lambda r: r["hit"])
    n = max(1, min(per_side, len(lucky) // 2))
    lucky_rows = lucky[:n]
    taken = set(id(r) for r in lucky_rows)
    unlucky_rows = [r for r in unlucky if id(r) not in taken][:n]
    all_hit = [r["h"].trainer or r["h"].label for r in known if r["hit"] == r["total"]]
    return lucky_rows, unlucky_rows, all_hit
