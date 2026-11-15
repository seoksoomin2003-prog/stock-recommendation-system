"""Forecast layer FC-2: how likely a close reaches a level on the way.  Rules: reports/QSF_FORECAST_TOUCH_PROTOCOL.md.

FC-1 says where the close is likely to be N sessions later.  This says how likely it is that some close inside those N sessions
ends at or beyond a level, below (a stop) or above (a target).  The engine's own exit rules read closes, so closes are what is
counted; an intraday touch is not.  Distances are in units of FC-1's horizon volatility, and the probability at each distance is
the share of past paths of the day's stocks that went that far.  It changes no score, rank, limit or order plan.
"""
import json
import math
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from terminal.qsf import forecast as fc

VERSION = "FC-2"
PROTOCOL = "reports/QSF_FORECAST_TOUCH_PROTOCOL.md"
REPORT = Path("reports") / "qsf" / "QSF_FORECAST_TOUCH_TEST.json"
FIRST = "2026-11-16"             # the first session recorded with a touch table; nothing earlier is filled in
GRID = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0)          # distances, in units of the horizon volatility
TOLERANCE = {0.25: 0.05, 0.5: 0.05, 0.75: 0.05, 1.0: 0.05, 1.5: 0.03, 2.0: 0.02}      # allowed gap between forecast and outcome
SIDES = ("down", "up")
CROWDED = 2.0                    # a day on which touches were at least this many times the forecast
LIMITS = ["닿을 가능성은 종가 기준입니다. 장중에 잠깐 닿았다가 돌아온 것은 세지 않습니다. 프로그램의 손절·목표 규칙이 종가를 보기 때문입니다.",
          "오를지 내릴지를 말하지 않습니다. 같은 거리라면 모든 종목에 같은 가능성을 줍니다. 점수가 높다고 달라지지 않습니다.",
          "급변기에는 여러 종목이 한꺼번에 기준에 닿습니다. 평균이 맞아도 하루하루는 크게 벗어날 수 있습니다.",
          "손절에 먼저 닿을지 목표에 먼저 닿을지는 계산하지 않습니다.",
          "미국 과거 자료에는 인수·파산으로 사라진 종목 일부가 없습니다."]


def normal_touch(d: float) -> float:
    """A driftless random walk watched all the time reaches a level ``d`` volatilities away with this probability (reflection)."""
    return 2 * (1 - fc.phi(d))


def _extremes(path: np.ndarray, start: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Furthest log move below and above ``start`` along the last axis of ``path``, both as positive distances when reached; a path
    with no close has neither."""
    have = np.isfinite(path).any(axis=-1)
    lo = np.where(have, np.min(np.where(np.isfinite(path), path, np.inf), axis=-1), np.nan)
    hi = np.where(have, np.max(np.where(np.isfinite(path), path, -np.inf), axis=-1), np.nan)
    return start - lo, hi - start


def day_touch(adj: np.ndarray, i: int, cols: np.ndarray, window: int = fc.WINDOW) -> Dict[str, Any]:
    """Horizon volatility of every stock in ``cols`` at the close of row ``i`` (FC-1's own) and, per horizon and side, the probability
    of a close at or beyond each distance of GRID.  Reads rows ``i - window + 1 .. i`` and nothing after ``i``."""
    win = adj[max(0, i - window + 1):i + 1][:, cols].astype(float)
    r = fc.log_returns(win)
    days = r.shape[0]
    with np.errstate(invalid="ignore", divide="ignore"):
        lp = np.log(win)
    lp = np.where(np.isfinite(lp), lp, np.nan)
    out: Dict[str, Any] = {"vol": {}, "table": {}}
    for h in fc.HORIZONS:
        normal = {"down": [normal_touch(d) for d in GRID], "up": [normal_touch(d) for d in GRID], "pool": 0, "source": "NORMAL"}
        if days == 0:
            out["vol"][h], out["table"][h] = np.full(len(cols), np.nan), normal
            continue
        sig, cnt = fc.ewma_vol(r, fc.LAMBDA[h])
        ok = np.isfinite(win[-1]) & (cnt[-1] >= fc.MIN_RETURNS) & np.isfinite(sig[-1]) & (sig[-1] > 0)
        out["vol"][h] = np.where(ok, sig[-1] * math.sqrt(h), np.nan)
        down = up = np.empty(0)
        if days - h >= 1:                                   # past closes ``s`` whose ``h`` following sessions had ended by row ``i``
            path = sliding_window_view(lp[2:], h, axis=0)[:days - h]
            below, above = _extremes(path, lp[1:days - h + 1])
            scale = sig[:days - h] * math.sqrt(h)
            use = np.isfinite(below) & np.isfinite(scale) & (scale > 0) & (cnt[:days - h] >= fc.MIN_CAL_RETURNS) & ok[None, :]
            with np.errstate(invalid="ignore", divide="ignore"):
                down, up = (below / scale)[use], (above / scale)[use]
        if down.size >= fc.MIN_POOL:
            out["table"][h] = {"down": [float((down >= d).mean()) for d in GRID], "up": [float((up >= d).mean()) for d in GRID], "pool": int(down.size), "source": "EMPIRICAL"}
        else:
            out["table"][h] = {**normal, "pool": int(down.size)}
    return out


def reached(adj: np.ndarray, i: int, cols: np.ndarray, h: int) -> Tuple[np.ndarray, np.ndarray]:
    """Furthest closing log move below and above the close of row ``i`` within the next ``h`` rows.  A stock gone before then is
    read up to its last close; one with no close at all inside the horizon has no outcome."""
    with np.errstate(invalid="ignore", divide="ignore"):
        fut = np.log(adj[i + 1:i + h + 1][:, cols].astype(float))
        start = np.log(adj[i, cols].astype(float))
    below, above = _extremes(np.where(np.isfinite(fut), fut, np.nan).T, np.where(np.isfinite(start), start, np.nan))
    return below, above


def shares(exc: np.ndarray, vol: np.ndarray) -> Optional[Tuple[List[float], np.ndarray]]:
    """Share of the stocks whose furthest move reached each distance of GRID, and which stocks counted."""
    ok = np.isfinite(exc) & np.isfinite(vol)
    if not ok.any():
        return None
    return [float((exc[ok] >= d * vol[ok]).mean()) for d in GRID], ok


# ---------------------------------------------------------------------- the one historical check
def evaluate_day(adj: np.ndarray, i: int, cols: np.ndarray) -> Optional[Dict[str, Any]]:
    if len(cols) < fc.MIN_TEST_STOCKS:
        return None
    f = day_touch(adj, i, cols)
    row: Dict[str, Any] = {"stocks": int(len(cols))}
    for h in fc.HORIZONS:
        vol, table = f["vol"][h], f["table"][h]
        cell: Dict[str, Any] = {"source": table["source"]}
        for side, exc in zip(SIDES, reached(adj, i, cols, h)):
            got = shares(exc, vol)
            if got is None or got[1].sum() < fc.MIN_TEST_STOCKS:
                return None
            real, ok = got
            thirds = np.array_split(np.argsort(vol[ok], kind="mergesort"), 3)
            hit = exc[ok][:, None] >= np.array(GRID)[None, :] * vol[ok][:, None]
            cell[side] = {"n": int(ok.sum()), "forecast": table[side], "real": real, "by_vol": [[float(hit[t, g].mean()) for g in range(len(GRID))] for t in thirds]}
        row[str(h)] = cell
    return row


def _parts(x: Sequence[float]) -> Dict[str, Optional[float]]:
    half = len(x) // 2
    return {"all": fc._mean(x), "early": fc._mean(x[:half]), "late": fc._mean(x[half:])}


def summarize(days: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per horizon, side and distance: mean forecast, mean outcome and their gap over all days and each half; the checks that failed."""
    out: Dict[str, Any] = {"days": len(days), "first": days[0]["date"] if days else None, "last": days[-1]["date"] if days else None,
                           "mean_stocks": fc._mean([d["stocks"] for d in days]), "horizons": {}, "failed": []}
    for h in fc.HORIZONS:
        block: Dict[str, Any] = {"normal_days": int(sum(d[str(h)]["source"] == "NORMAL" for d in days))}
        for side in SIDES:
            cells = []
            for g, dist in enumerate(GRID):
                fore, real = [d[str(h)][side]["forecast"][g] for d in days], [d[str(h)][side]["real"][g] for d in days]
                gap = _parts([b - a for a, b in zip(fore, real)])
                years: Dict[str, List[float]] = {}
                for d, a, b in zip(days, fore, real):
                    years.setdefault(d["date"][:4], []).append(b - a)
                worst = max(years.items(), key=lambda kv: abs(np.mean(kv[1]))) if years else None
                ok = all(v is not None and abs(v) <= TOLERANCE[dist] + 1e-12 for v in gap.values())
                for part, v in gap.items():
                    if v is None or abs(v) > TOLERANCE[dist] + 1e-12:
                        out["failed"].append({"horizon": h, "side": side, "distance": dist, "part": part, "gap": v, "tolerance": TOLERANCE[dist]})
                cells.append({"distance": dist, "forecast": _parts(fore), "real": _parts(real), "gap": gap, "tolerance": TOLERANCE[dist], "pass": ok,
                              "normal": normal_touch(dist), "normal_gap": fc._mean([b - normal_touch(dist) for b in real]),
                              "crowded_share": fc._mean([float(b >= CROWDED * a) for a, b in zip(fore, real)]),
                              "worst_year": None if worst is None else {"year": worst[0], "gap": float(np.mean(worst[1])), "days": len(worst[1])},
                              "by_vol": [fc._mean([d[str(h)][side]["by_vol"][t][g] for d in days]) for t in range(3)]})
            block[side] = cells
        block["stock_days"] = int(sum(d[str(h)]["down"]["n"] for d in days))
        out["horizons"][str(h)] = block
    out["verdict"] = "TOUCH_CALIBRATED" if days and not out["failed"] else "TOUCH_NOT_CALIBRATED"
    return out


def evaluate(adj: np.ndarray, dates: Sequence[str], universe: Callable[[int], np.ndarray], log=lambda m: None) -> Dict[str, Any]:
    days = []
    rows = fc.check_rows(len(dates))
    for n, i in enumerate(rows):
        row = evaluate_day(adj, i, universe(i))
        if row:
            days.append({"date": str(dates[i]), **row})
        if n % 100 == 0:
            log(f"{n}/{len(rows)} {dates[i]}")
    return summarize(days)


def run_once(base: Path, log=print, loaders: Optional[Callable[[Path], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """The one run over both markets.  A stored result is returned as it is and nothing is computed again."""
    path = Path(base) / REPORT
    if path.exists():
        return {**json.loads(path.read_text(encoding="utf-8")), "status": "ALREADY_RUN"}
    markets = {}
    for market, (adj, dates, universe) in (loaders or fc._load_markets)(Path(base)).items():
        log(f"{market}: {dates[0]} ~ {dates[-1]}")
        markets[market] = {"data_first": dates[0], "data_last": dates[-1], **evaluate(adj, dates, universe, log)}
    doc = {"status": "REAL", "version": VERSION, "protocol": PROTOCOL, "ran_at": fc._utcnow().isoformat(),
           "settings": {"grid": list(GRID), "tolerance": {str(k): v for k, v in TOLERANCE.items()}, "horizons": list(fc.HORIZONS), "window": fc.WINDOW,
                        "lambda": {str(h): fc.LAMBDA[h] for h in fc.HORIZONS}, "min_pool": fc.MIN_POOL, "step": fc.STEP, "crowded": CROWDED, "basis": "close"},
           "markets": markets, "limits": LIMITS}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return doc


def check_result(base: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads((Path(base) / REPORT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------- the daily record and its reading
def table_doc(f: Dict[str, Any]) -> Dict[str, Any]:
    """The day's table as it is stored beside FC-1's ranges: one probability per horizon, side and distance, the same for every stock."""
    return {"version": VERSION, "protocol": PROTOCOL, "basis": "close", "grid": list(GRID),
            "horizons": {str(h): {"down": [round(p, 6) for p in f["table"][h]["down"]], "up": [round(p, 6) for p in f["table"][h]["up"]],
                                  "pool": f["table"][h]["pool"], "source": f["table"][h]["source"]} for h in fc.HORIZONS}}


def at_distance(table: Dict[str, Any], h: int, side: str, distance: float) -> Optional[float]:
    """The stored probability at ``distance`` volatilities, read between the two grid points around it.  Nearer than the first
    grid point or further than the last has no stored value."""
    grid, p = table["grid"], table["horizons"][str(h)][side]
    if not np.isfinite(distance) or distance < grid[0] or distance > grid[-1]:
        return None
    return float(np.interp(distance, grid, p))


def follow_day(doc: Dict[str, Any], adj: np.ndarray, i: int, cols: np.ndarray, rows: List[Dict[str, Any]], h: int) -> Optional[Dict[str, Any]]:
    """Forecast and outcome of one recorded day whose ``h`` sessions have ended."""
    table = doc.get("touch")
    if not table or not len(rows):
        return None
    vol = np.array([np.nan if r["vol"][str(h)] is None else r["vol"][str(h)] for r in rows], dtype=float)
    out: Dict[str, Any] = {"session": doc["session"]}
    for side, exc in zip(SIDES, reached(adj, i, cols, h)):
        got = shares(exc, vol)
        if got is None:
            return None
        out[side] = {"n": int(got[1].sum()), "forecast": table["horizons"][str(h)][side], "real": got[0]}
    return out


def read(days: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The running figures of the matured days and, once READ_AT of them exist, the one fixed reading of the first READ_AT."""
    def cells(sel: List[Dict[str, Any]], side: str) -> List[Dict[str, Any]]:
        out = []
        for g, dist in enumerate(GRID):
            fore, real = [d[side]["forecast"][g] for d in sel], [d[side]["real"][g] for d in sel]
            gap = _parts([b - a for a, b in zip(fore, real)])
            out.append({"distance": dist, "forecast": fc._mean(fore), "real": fc._mean(real), "gap": gap, "tolerance": TOLERANCE[dist],
                        "pass": all(v is not None and abs(v) <= TOLERANCE[dist] + 1e-12 for v in gap.values())})
        return out
    fixed = days[:fc.READ_AT] if len(days) >= fc.READ_AT else None
    reading = None
    if fixed:
        table = {side: cells(fixed, side) for side in SIDES}
        reading = {"days": fc.READ_AT, "first": fixed[0]["session"], "last": fixed[-1]["session"], **table,
                   "verdict": "TOUCH_CALIBRATED" if all(c["pass"] for side in SIDES for c in table[side]) else "TOUCH_NOT_CALIBRATED"}
    return {"matured": len(days), "first": days[0]["session"] if days else None, "last": days[-1]["session"] if days else None,
            **({side: cells(days, side) for side in SIDES} if days else {}), "read_at": fc.READ_AT, "reading": reading}
