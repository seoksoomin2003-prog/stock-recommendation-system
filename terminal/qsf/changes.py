"""What moved between the newest scan and the session recorded before it.  Read only; nothing here feeds a score.

When the model version differs between the two, the difference is not only new information, and the result says so.
"""
from typing import Any, Dict, List, Optional

TOP = 10
BUY = "BUY"
DOMAIN_LIMIT = 1.0          # a smaller move in a domain is not offered as the reason


def _num(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v else None


def _domain_score(v: Any) -> Optional[float]:
    return _num(v.get("score_100") if isinstance(v, dict) else v)


def _largest_move(now: Dict[str, Any], before: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The domain that moved most, either way: it can run against the score, because weights differ.  None when no domain moved enough to say."""
    moves = []
    for d, v in (now or {}).items():
        a, b = _domain_score(v), _domain_score((before or {}).get(d))
        if a is not None and b is not None:
            moves.append((d, a - b))
    if not moves:
        return None
    d, delta = max(moves, key=lambda x: (abs(x[1]), x[0]))
    return {"domain": d, "change": delta} if abs(delta) >= DOMAIN_LIMIT else None


def _item(cur: Dict[str, Any], prev: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    now, was = _num(cur.get("score")), _num((prev or {}).get("score"))
    return {"ticker": cur.get("ticker"), "name": cur.get("name"), "score": now, "previous_score": was, "delta": now - was if now is not None and was is not None else None,
            "action_label": cur.get("action_label"), "previous_action": (prev or {}).get("action"), "actionability": cur.get("actionability"), "entry_status": cur.get("entry_status"), "gates": cur.get("gates") or [],
            "reason": _largest_move(cur.get("domains") or {}, (prev or {}).get("domains") or {}) if prev else None}


def compare(cur_rows: List[Dict[str, Any]], prev_rows: List[Dict[str, Any]], strategy: str, top: int = TOP) -> Dict[str, Any]:
    cur = {r["ticker"]: r for r in cur_rows if r.get("strategy") == strategy}
    prev = {r["ticker"]: r for r in prev_rows if r.get("strategy") == strategy}
    both = [t for t in cur if t in prev]
    entered = [_item(cur[t], prev[t]) for t in both if cur[t].get("action") == BUY and prev[t].get("action") != BUY]
    left = [_item(cur[t], prev[t]) for t in both if cur[t].get("action") != BUY and prev[t].get("action") == BUY]
    moved = [m for m in (_item(cur[t], prev[t]) for t in both) if m["delta"] is not None]
    by_score = lambda m: (-(m["score"] if m["score"] is not None else -1), str(m["ticker"]))      # noqa: E731
    return {"strategy": strategy, "compared": len(both), "entered_buy": sorted(entered, key=by_score), "left_buy": sorted(left, key=by_score),
            "new_in_scan": sorted(t for t in cur if t not in prev), "gone_from_scan": sorted(t for t in prev if t not in cur),
            "up": sorted([m for m in moved if m["delta"] > 0], key=lambda m: (-m["delta"], str(m["ticker"])))[:top], "down": sorted([m for m in moved if m["delta"] < 0], key=lambda m: (m["delta"], str(m["ticker"])))[:top]}


def report(latest: Dict[str, Any], ledger: Any, market: str, strategy: str) -> Dict[str, Any]:
    if latest.get("status") != "REAL":
        return {"status": latest.get("status") or "UNAVAILABLE", "reason": latest.get("reason")}
    if ledger.read_index().get("status") != "OK":
        return {"status": "UNAVAILABLE", "reason": "원장을 읽지 못해 비교하지 않습니다."}
    session = latest.get("session")
    previous = ledger.session_before(market, session) if session else None
    rows = ledger.of_session(market, previous, strategy) if previous else []
    if not rows:
        return {"status": "NO_PREVIOUS", "session": session, "reason": "비교할 이전 기록이 없습니다."}
    versions = sorted({str(s.get("model_version")) for s in rows})
    return {"status": "REAL", "market": market, "session": session, "previous_session": previous, "model_version": latest.get("model_version"), "previous_model_versions": versions,
            "model_changed": versions != [str(latest.get("model_version"))], **compare(latest.get("rows") or [], rows, strategy)}
