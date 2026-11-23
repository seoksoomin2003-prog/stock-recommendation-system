"""Why a stock sits where it does: each factor's push away from the middle, read from what was recorded.  Display only.

A score is 100 x (sum of weight x normalized) / (sum of the weights that have data), so it is exactly 50 plus, for every factor
with data, 100 x (normalized - 0.5) x weight / (that sum of weights).  That push is a factor's 'points' here: the points of all
factors add up to the score minus 50.  Strengths and weaknesses follow the engine's own rule (engine.score: normalized 0.6 or more,
0.4 or less, three each), so the card's sentence, the card's balance box and the ranking table name the same factors.

Nothing here scores, records or reads the network: the ranking's notes come from the ledger snapshots the scan wrote, the card's
from the card itself.  Added 2026-11-23 (UI audit, items 1-3).
"""
from typing import Any, Dict, Iterable, List, Optional, Tuple

STRONG, WEAK, SHOWN = 0.6, 0.4, 3


def band_edges() -> List[float]:
    """The score lines where a band starts, read from the engine's settings so the page never keeps its own copy.  Display only: the
    'near an edge' mark (UI batch 1, user decision 2026-11-23).  The buy band's exit line (67) is left out: it holds only for a stock
    already in the band the session before, and with it 30 of the US top 50 carried the mark on 2026-11-23 (13 without it)."""
    from terminal.qsf import config as cfg
    return sorted({float(b[0]) for b in cfg.BANDS if b[0] > 0}, reverse=True)


def bands() -> Dict[str, Any]:
    """Every score band (start, key, Korean name), highest first, read from the engine's settings.  The page colours score bars and
    action labels from this list instead of keeping its own copy of the edges (UI batch 5 P3-12).  Display only; edges unchanged."""
    from terminal.qsf import config as cfg
    return {"bands": [{"start": float(s), "key": k, "label": lab} for s, k, lab in sorted(cfg.BANDS, key=lambda b: -b[0])]}


def _name(fid: str) -> str:
    from terminal.assistant import FACTOR_KO          # the Korean factor names live with the assistant; imported late to avoid a cycle
    return FACTOR_KO.get(fid, fid)


def balance(factors: Iterable[Dict[str, Any]], shown: int = SHOWN) -> Dict[str, Any]:
    """The strongest pushes up and down among the scored factors with data, in points of the 100-point score.  ``missing``: the
    scored factors without data (they are not in the score; the card's buy band reads them at the middle)."""
    rows = list(factors or [])
    used = [f for f in rows if f.get("contribution") is not None and f.get("normalized") is not None and (f.get("weight") or 0) > 0 and f.get("scored") is not False]
    total = sum(float(f["weight"]) for f in used)
    missing = [f["factor"] for f in rows if f.get("contribution") is None and f.get("scored") is not False and (f.get("weight") or 0) > 0 and f.get("status") == "MISSING"]
    labels = {f["factor"]: _name(f["factor"]) for f in rows if f.get("factor")}
    if not total:
        return {"plus": [], "minus": [], "points_sum": None, "missing": [_name(m) for m in missing], "labels": labels}

    def one(f: Dict[str, Any]) -> Dict[str, Any]:
        return {"factor": f["factor"], "label": _name(f["factor"]), "normalized": f["normalized"], "weight": f["weight"],
                "points": 100.0 * (float(f["normalized"]) - 0.5) * float(f["weight"]) / total, "text": f.get("explanation") or f.get("reason")}
    pushes = [one(f) for f in used]
    plus = sorted((p for p in pushes if p["normalized"] >= STRONG), key=lambda p: p["points"], reverse=True)[:shown]
    minus = sorted((p for p in pushes if p["normalized"] <= WEAK), key=lambda p: p["points"])[:shown]
    return {"plus": plus, "minus": minus, "points_sum": sum(p["points"] for p in pushes), "missing": [_name(m) for m in missing], "labels": labels}


def short(b: Dict[str, Any]) -> Dict[str, Any]:
    """The table's one line: the largest push each way, label and points only.  ``plus_more`` / ``minus_more``: the next ones (up to
    two each way), so the page can skip a factor that nearly every shown row shares (UI batch 6 P2-25).  Display only."""
    one = lambda x: {"label": x["label"], "points": round(x["points"], 1)}      # noqa: E731
    return {"plus": one(b["plus"][0]) if b["plus"] else None, "minus": one(b["minus"][0]) if b["minus"] else None,
            "plus_more": [one(x) for x in b["plus"][1:3]], "minus_more": [one(x) for x in b["minus"][1:3]]}


def _session_snaps(ledger: Any, market: str, session: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in ledger._live_rows():
        if r["market"] == market and r["session"] == session:
            out += ledger._load(r)
    return out


def previous_session(ledger: Any, market: str, session: str) -> Optional[str]:
    days = sorted({r["session"] for r in ledger._live_rows() if r["market"] == market and r["session"] < session})
    return days[-1] if days else None


def notes(ledger: Any, market: str, session: str) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """{(ticker, strategy): {"plus", "minus", "prev", "prev_session"}} for one recorded session.  ``prev``: the score recorded at the
    session before (None when the stock had none).  A ticker scanned twice in a session keeps its last snapshot, as the screens do."""
    now = {}
    for s in _session_snaps(ledger, market, session):
        if s.get("data_date") == session and s.get("score") is not None:
            now[(s["ticker"], s["strategy"])] = s
    before = previous_session(ledger, market, session)
    prev = {}
    if before:
        for s in _session_snaps(ledger, market, before):
            if s.get("data_date") == before and s.get("score") is not None:
                prev[(s["ticker"], s["strategy"])] = float(s["score"])
    return {k: {**short(balance(s.get("factors") or [])), "prev": prev.get(k), "prev_session": before} for k, s in now.items()}
