"""A portfolio around one stock, made from the five views' differing opinions, and only when it is asked for (rules FP-1).

User request (2026-11-22): the portfolio the five views make is a feature of its own.  It is chosen at a stock ("포트폴리오
받아보기"), and nothing is made until that button is pressed.  Decisions the same day: the portfolio is built around the
stock the button was pressed on, the weights follow how many of the five views find a stock to meet their criteria, and the
market-wide team list leaves the screens (the daily record of terminal/five_views.py stays).

How it is made.  (1) Each view says whether it would hold the stock: it does when the stock meets its criteria.  The stock
enters when at least one view holds it.  (2) Each view has ``PER_VIEW`` places.  A view that holds the stock has used one of
them on it; taking turns, each view fills its remaining places with the stocks that meet its own checklist best and are not
in yet.  So the views that do not hold the stock bring more of what it lacks.  A sector holds at most ``SECTOR_CAP`` stocks,
so one cheap sector cannot fill the list.  (3) A stock's weight is its number of holding views over the sum of those numbers.

What to expect.  The stocks a view adds are its best of the whole market, so two portfolios share many names; they differ by
the stock asked for, by which views have a place left, and by the sector the stock already takes.  A stock no view holds
gets the same list as any other such stock: what the five would hold instead.

What this is not.  Not these people's portfolio, not advice and not an order: the criteria are terminal/five_views.py's,
untested on returns, and no score reads any of it.  Amounts and share counts are not computed.  No network is asked.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from terminal import five_views as fv

RULES = "FP-1"
PER_VIEW, SECTOR_CAP = 2, 2
HOLD_KO = {fv.MEETS: "담음", fv.PARTLY: "담지 않음", fv.FAILS: "담지 않음", fv.UNKNOWN: "판단하지 않음"}
NOTE = "주문을 내지 않는 참고 포트폴리오입니다. 금액, 수량, 손절은 계산하지 않습니다. 비중은 '기준에 맞음'으로 본 관점의 수에 비례합니다."


def _order(survey: Dict[str, Dict[str, Any]], key: str, seed: str) -> List[Dict[str, Any]]:
    """The stocks one view holds, the ones that meet its own checklist best first; ties go to the stock more views hold."""
    rows = [e for t, e in survey.items() if t != seed and e["views"][key]["verdict"] == fv.MEETS]
    return sorted(rows, key=lambda e: (-e["views"][key]["share"], -e["views"][key]["met"], -e["agree"], -e["mean_share"], e["ticker"]))


def _seed_lines(me: Dict[str, Any]) -> List[str]:
    out = []
    for key, name, _motto, _fn in fv.VIEWS:
        v = me["views"][key]
        if v["verdict"] == fv.UNKNOWN:
            out.append(f"{name}: 판단하지 않음. 확인할 수 있는 기준이 {v['known']}개뿐입니다.")
            continue
        why = ", ".join(v["pro"]) if v["verdict"] == fv.MEETS else (v["capped"] or "걸리는 것: " + ", ".join(v["con"])) if (v["capped"] or v["con"]) else ""
        out.append(f"{name}: {HOLD_KO[v['verdict']]}({v['label']}, 기준 {v['known']}개 중 {v['met']}개 충족). {why}".rstrip() + ("" if why.endswith(".") or not why else "."))
    return out


def build(survey: Dict[str, Dict[str, Any]], seed: str, per_view: int = PER_VIEW, sector_cap: int = SECTOR_CAP) -> Dict[str, Any]:
    """``survey``: ``five_views.survey`` of one session.  ``seed``: the stock the portfolio was asked for."""
    me = survey.get(seed)
    if me is None:
        return {"status": "NO_VIEW", "rules": RULES, "seed": seed, "rows": [], "lines": [], "seed_lines": [], "by_view": [],
                "reason": "이 종목은 저장된 자료가 모자라 다섯 관점 모두 판단하지 않았습니다. 판단할 수 없는 종목을 중심으로 포트폴리오를 만들지 않습니다."}
    names = {key: name for key, name, *_ in fv.VIEWS}
    picked: Dict[str, Optional[str]] = {}                    # ticker -> the view that added it (None: the stock asked for)
    sectors: Dict[str, int] = {}

    def take(e: Dict[str, Any], by: Optional[str]) -> None:
        picked[e["ticker"]] = by
        if e.get("sector"):
            sectors[e["sector"]] = sectors.get(e["sector"], 0) + 1

    if me["agree"] >= 1:
        take(me, None)
    queues = {key: _order(survey, key, seed) for key in names}
    held = {key: len(q) for key, q in queues.items()}        # the other stocks each view holds
    passed: Dict[str, set] = {key: set() for key in names}   # stocks a view would have added but for the sector limit
    places = {key: per_view - (1 if me["views"][key]["verdict"] == fv.MEETS else 0) for key in names}      # a holder's first place is the stock itself
    for turn in range(per_view):
        for key in names:
            if turn >= places[key]:
                continue
            for e in queues[key]:
                if e["ticker"] in picked:
                    continue
                if e.get("sector") and sectors.get(e["sector"], 0) >= sector_cap:
                    passed[key].add(e["ticker"])
                    continue
                take(e, key)
                break
            queues[key] = [e for e in queues[key] if e["ticker"] not in picked]
    total = sum(survey[t]["agree"] for t in picked)
    rows = []
    for t, by in picked.items():
        e = survey[t]
        against = [names[k] for k in names if e["views"][k]["verdict"] == fv.FAILS]
        first = next((k for k in names if e["views"][k]["verdict"] == fv.FAILS and e["views"][k]["con"]), None)
        rows.append({"ticker": t, "name": e.get("name") or t, "sector": e.get("sector"), "is_seed": by is None, "weight": round(e["agree"] / total, 4), "agree": e["agree"],
                     "agree_names": e["agree_names"], "added_by": None if by is None else names[by], "against": against,
                     "why": ", ".join(e["views"][by]["pro"]) if by else "", "against_why": f"{names[first]}: {e['views'][first]['con'][0]}" if first else ""})
    rows.sort(key=lambda r: (not r["is_seed"], -r["weight"], r["ticker"]))
    by_view = [{"key": key, "name": names[key], "holds_seed": me["views"][key]["verdict"] == fv.MEETS, "held": held[key],
                "added": [t for t, by in picked.items() if by == key], "passed_for_sector": len(passed[key])} for key in names]
    return {"status": "OK" if rows else "EMPTY", "rules": RULES, "seed": seed, "seed_name": me.get("name") or seed, "seed_in": me["agree"] >= 1, "seed_agree": me["agree"],
            "seed_lines": _seed_lines(me), "rows": rows, "by_view": by_view, "per_view": per_view, "sector_cap": sector_cap, "lines": _lines(me, rows, by_view, sector_cap)}


def _lines(me: Dict[str, Any], rows: List[Dict[str, Any]], by_view: List[Dict[str, Any]], sector_cap: int) -> List[str]:
    """The portfolio in sentences: the head, one line per stock, what each view added, and what this is not."""
    head = me.get("name") or me["ticker"]
    if not rows:
        return [f"{head}: 다섯 관점 가운데 이 종목을 담는 관점이 없고, 각 관점이 더할 종목도 없어 포트폴리오를 만들지 않았습니다.", fv.NOTE]
    seed = next((r for r in rows if r["is_seed"]), None)
    first = (f"{head} 중심의 {len(rows)}종목입니다. 다섯 관점 가운데 {me['agree']}개({', '.join(me['agree_names'])})가 이 종목을 담아 비중은 {seed['weight'] * 100:.1f}%입니다."
             if seed else f"{head}: 다섯 관점 가운데 이 종목을 담는 관점이 없어 넣지 않았습니다. 대신 각 관점이 자기 기준으로 고른 {len(rows)}종목입니다.")
    out = [first]
    for r in rows:
        tail = "" if r["is_seed"] else f" {r['added_by']}이 더함({r['why']})." if r["why"] else f" {r['added_by']}이 더함."
        other = f" 다른 의견: {r['against_why']}." if r["against_why"] else ""
        out.append(f"{r['name']}({r['ticker']}) {r['weight'] * 100:.1f}%: {r['agree']}개 관점이 담음({', '.join(r['agree_names'])}).{tail}{other}")
    for v in by_view:
        if not v["added"]:
            out.append(f"{v['name']}: 더한 종목 없음(이 관점의 기준에 맞는 다른 종목 {v['held']}개" + (f", 업종 한도로 넘긴 종목 {v['passed_for_sector']}개)." if v["passed_for_sector"] else ")."))
    sectors: Dict[str, int] = {}
    for r in rows:
        if r.get("sector"):
            sectors[r["sector"]] = sectors.get(r["sector"], 0) + 1
    if sectors:
        out.append("업종: " + ", ".join(f"{k} {n}" for k, n in sorted(sectors.items(), key=lambda kv: (-kv[1], kv[0]))) + f". 한 업종은 {sector_cap}종목까지만 담습니다.")
    return out + [NOTE, fv.NOTE]
