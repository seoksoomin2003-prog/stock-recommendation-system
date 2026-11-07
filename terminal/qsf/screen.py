"""Filter and sort the newest scan.  Read only: it recomputes nothing and no score, record or ledger sees it.

A stock missing a value a filter asks about is left out and counted, never treated as 0.
"""
from typing import Any, Dict, List, Optional, Tuple

ACTIONS = ("BUY", "WATCH", "AVOID", "HOLD", "REDUCE", "SELL", "BLOCKED", "INSUFFICIENT_DATA")
STRATEGIES = ("SWING", "LONG_TERM")
ENTRY_STATES = ("ENTRY_NOW", "WAIT_FOR_PULLBACK", "WAIT_FOR_BREAKOUT_CONFIRMATION", "WAIT_FOR_EARNINGS", "OVERVALUED_AT_CURRENT_PRICE", "NO_VALID_ENTRY_SETUP")
CONFIDENCE = {"INSUFFICIENT": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
DOMAINS = {"technical": "TECHNICAL", "fundamental": "FUNDAMENTAL", "risk": "RISK", "events": "EVENTS"}
SORTS = ("score", "price", "coverage", *DOMAINS)
MAX_LIMIT = 2000
MAX_QUERY = 40


def _number(raw: Any, name: str, low: float, high: float) -> Optional[float]:
    if raw in (None, ""):
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"INVALID_{name.upper()}") from None
    if not low <= v <= high:       # NaN fails here too
        raise ValueError(f"INVALID_{name.upper()}")
    return v


def _flag(raw: Any, name: str) -> bool:
    if raw in (None, "", "0"):
        return False
    if raw == "1":
        return True
    raise ValueError(f"INVALID_{name.upper()}")


def parse(q: Dict[str, Any]) -> Dict[str, Any]:
    """Query words to filter values.  Anything not understood is refused rather than quietly ignored, so a list is never wider than it says."""
    strategy = q.get("strategy") or "SWING"
    if strategy not in STRATEGIES:
        raise ValueError("INVALID_STRATEGY")
    actions = [a for a in str(q.get("action") or "").split(",") if a]
    if any(a not in ACTIONS for a in actions):
        raise ValueError("INVALID_ACTION")
    entry = q.get("entry") or None
    if entry is not None and entry not in ENTRY_STATES:
        raise ValueError("INVALID_ENTRY")
    conf = q.get("confidence") or None
    if conf is not None and conf not in CONFIDENCE:
        raise ValueError("INVALID_CONFIDENCE")
    sort = q.get("sort") or "score"
    if sort not in SORTS:
        raise ValueError("INVALID_SORT")
    order = q.get("order") or "desc"
    if order not in ("asc", "desc"):
        raise ValueError("INVALID_ORDER")
    return {"sector": str(q.get("sector") or "")[:MAX_QUERY] or None, "strategy": strategy, "actions": actions, "entry": entry, "confidence": conf, "sort": sort, "order": order,
            "actionable": _flag(q.get("actionable"), "actionable"), "no_financing": _flag(q.get("no_financing"), "no_financing"), "no_high_risk": _flag(q.get("no_high_risk"), "no_high_risk"), "buyback": _flag(q.get("buyback"), "buyback"),
            "minimums": {k: v for k in DOMAINS if (v := _number(q.get(f"min_{k}"), f"min_{k}", 0, 100)) is not None}, "min_score": _number(q.get("min_score"), "min_score", 0, 100),
            "text": str(q.get("q") or "").strip().casefold()[:MAX_QUERY], "limit": int(_number(q.get("limit"), "limit", 1, MAX_LIMIT) or 100), "offset": int(_number(q.get("offset"), "offset", 0, 1e6) or 0)}


def _value(row: Dict[str, Any], key: str) -> Optional[float]:
    v = (row.get("domains") or {}).get(DOMAINS[key]) if key in DOMAINS else row.get(key)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v else None


def _keep(row: Dict[str, Any], f: Dict[str, Any]) -> Tuple[bool, bool]:
    """Whether the stock passes, and whether it failed only because a value was missing."""
    if f["actions"] and row.get("action") not in f["actions"]:
        return False, False
    if f["actionable"] and row.get("actionability") != "ACTIONABLE":
        return False, False
    if f["entry"] and row.get("entry_status") != f["entry"]:
        return False, False
    if f["confidence"] and CONFIDENCE.get(row.get("confidence"), -1) < CONFIDENCE[f["confidence"]]:
        return False, False
    if f["text"] and f["text"] not in str(row.get("ticker") or "").casefold() and f["text"] not in str(row.get("name") or "").casefold():
        return False, False
    marks = row.get("filing_events") or {}
    if (f["no_financing"] and marks.get("financing")) or (f["no_high_risk"] and row.get("high_risk")):
        return False, False
    missing = bool(row.get("filing_unknown") and (f["no_financing"] or f["buyback"])) or bool(f["sector"] and not row.get("sector"))
    if f["sector"] and row.get("sector") and row["sector"] != f["sector"]:
        return False, False
    if f["buyback"] and not missing and not marks.get("buyback"):
        return False, False
    for key, low in [*f["minimums"].items(), *([("score", f["min_score"])] if f["min_score"] is not None else [])]:
        v = _value(row, key)
        if v is None:
            missing = True
        elif v < low:
            return False, False
    return not missing, missing


def _counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """How many stocks per sector, most first.  A stock with no sector is left out of the table rather than given one."""
    found: Dict[str, int] = {}
    for r in rows:
        if r.get("sector"):
            found[r["sector"]] = found.get(r["sector"], 0) + 1
    return dict(sorted(found.items(), key=lambda x: (-x[1], x[0])))


def screen(latest: Dict[str, Any], query: Dict[str, Any]) -> Dict[str, Any]:
    f = parse(query)
    if latest.get("status") != "REAL":
        return {"status": latest.get("status") or "UNAVAILABLE", "rows": [], "total": 0, "matched": 0, "missing_value": 0, "reason": latest.get("reason")}
    rows = [r for r in latest.get("rows") or [] if r.get("strategy") == f["strategy"]]
    kept: List[Dict[str, Any]] = []
    missing = 0
    for r in rows:
        ok, lacked = _keep(r, f)
        missing += lacked
        if ok:
            kept.append(r)
    known = [r for r in kept if _value(r, f["sort"]) is not None]
    unknown = [r for r in kept if _value(r, f["sort"]) is None]       # stays at the bottom in either order
    known.sort(key=lambda r: (_value(r, f["sort"]), str(r.get("ticker"))), reverse=f["order"] == "desc")
    ordered = known + sorted(unknown, key=lambda r: str(r.get("ticker")))
    page = ordered[f["offset"]:f["offset"] + f["limit"]]
    return {"status": "REAL", "market": latest.get("market"), "session": latest.get("session"), "model_version": latest.get("model_version"), "generated_at": latest.get("generated_at"), "strategy": f["strategy"],
            "total": len(rows), "matched": len(ordered), "missing_value": missing, "offset": f["offset"], "limit": f["limit"], "sort": f["sort"], "order": f["order"], "sectors": _counts(rows), "matched_sectors": _counts(ordered), "rows": page}
