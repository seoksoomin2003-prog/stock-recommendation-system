"""Pre-registered swing chart-factor research.  Rules: reports/QSF_SWING_RESEARCH_PROTOCOL.md.

Development sees only returns that end before TEST_START.  The test runs once; a second run is refused.  Nothing here changes the
live score, the QSF ledger or P6-11B.
"""
import csv
import gzip
import json
import math
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from terminal.qsf import config, pit, validate, validate_oos, validate_open, validate_pit
from terminal.qsf.research_score import MIN_ADV, MIN_BARS, MIN_PRICE, MIN_T, TEST_START, dev_rows, test_rows, test_verdict

GOOD_HIGH = {"high_52w": True, "ma200_ratio": True, "ma50_200": True, "mom_12_1": True, "mom_6_1": True, "resid_mom_12_1": True, "breakout_55": True, "breakout_vol": True,
             "vcp": False, "nr7": True, "rev_1m": False, "rev_1w": False, "rev_resid_1m": False, "rev_sector_1m": False, "rsi2": False, "boll_z": False, "pullback_uptrend": False,
             "vol_252": False, "ivol_21": False, "max_21": False, "vol_surge": True, "obv_20": True, "pattern_net": True, "sue": True}
FACTORS = tuple(GOOD_HIGH)
HORIZONS = {"SWING_10": 10, "SWING_20": 20}
STEP = 5
HISTORY = 320
BONFERRONI_T = 2.86
RARE = ("breakout_vol", "nr7", "pattern_net")
PATTERN_WINDOW, PATTERN_FRESH, PATTERN_TOL, PATTERN_GAP = 38, 5, 0.015, 23
SUE_MAX_AGE, SUE_MIN_CHANGES = 92, 5
DEV_REPORT = Path("reports") / "qsf" / "QSF_SWING_DEV.json"
TEST_REPORT = Path("reports") / "qsf" / "QSF_SWING_TEST.json"
PROTOCOL = "reports/QSF_SWING_RESEARCH_PROTOCOL.md"


# ---------------------------------------------------------------------- window helpers
def _win(a: np.ndarray, i: int, n: int) -> np.ndarray:
    """The ``n`` rows ending at ``i``; only rows up to ``i`` are ever read."""
    return a[max(0, i - n + 1):i + 1]


def _nanmean(x: np.ndarray, need: int) -> np.ndarray:
    n = np.isfinite(x).sum(axis=0)
    out = np.full(x.shape[1], np.nan)
    ok = n >= need
    out[ok] = np.nansum(x[:, ok], axis=0) / n[ok]
    return out


def _nanstd(x: np.ndarray, need: int) -> np.ndarray:
    m = _nanmean(x, need)
    n = np.isfinite(x).sum(axis=0)
    out = np.full(x.shape[1], np.nan)
    ok = n >= need
    out[ok] = np.sqrt(np.nansum((x[:, ok] - m[ok]) ** 2, axis=0) / n[ok])
    return out


def _nanext(x: np.ndarray, need: int, fn) -> np.ndarray:
    out = np.full(x.shape[1], np.nan)
    ok = np.isfinite(x).sum(axis=0) >= need
    if ok.any():
        out[ok] = fn(x[:, ok], axis=0)
    return out


def _safe(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        out = a / b
    out[~np.isfinite(out)] = np.nan
    return out


def _returns(adj: np.ndarray, i: int, n: int) -> np.ndarray:
    w = _win(adj, i, n + 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return w[1:] / w[:-1] - 1


def rsi2(adj: np.ndarray, i: int, warm: int = 30) -> np.ndarray:
    """Wilder RSI with period 2.  A gap in the window leaves the value empty."""
    d = np.diff(_win(adj, i, warm + 1), axis=0)
    out = np.full(adj.shape[1], np.nan)
    if d.shape[0] < warm:
        return out
    ok = np.isfinite(d).all(axis=0)
    if not ok.any():
        return out
    x = d[:, ok]
    up, dn = np.clip(x, 0, None), np.clip(-x, 0, None)
    gain, loss = up[:2].mean(axis=0), dn[:2].mean(axis=0)
    for k in range(2, x.shape[0]):
        gain, loss = (gain + up[k]) / 2, (loss + dn[k]) / 2
    with np.errstate(invalid="ignore", divide="ignore"):
        rs = 100 * gain / (gain + loss)
    rs[(gain + loss) == 0] = 50.0
    out[ok] = rs
    return out


def _residual(ret: np.ndarray, mkt: np.ndarray, need: int) -> Tuple[np.ndarray, np.ndarray]:
    """Slope on the market and each column's residuals, on the rows where both have a value."""
    m = np.where(np.isfinite(ret), mkt[:, None], np.nan)
    n = np.isfinite(ret) & np.isfinite(m)
    beta = np.full(ret.shape[1], np.nan)
    enough = n.sum(axis=0) >= need
    if enough.any():
        r, mm = ret[:, enough], m[:, enough]
        rd, md = r - np.nanmean(r, axis=0), mm - np.nanmean(mm, axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            beta[enough] = np.nansum(rd * md, axis=0) / np.nansum(md * md, axis=0)
    return beta, ret - beta * mkt[:, None]


def price_features(d: Dict[str, np.ndarray], i: int, spy: int) -> Dict[str, np.ndarray]:
    """All price and volume factors at row ``i`` for every column.  Reads nothing after row ``i``."""
    a, c, h, lo, v = d["adj_close"], d["close"], d["high"], d["low"], d["volume"]
    n = a.shape[1]

    def ret(x: int, y: int) -> np.ndarray:
        if i < y:
            return np.full(n, np.nan)
        return _safe(a[i - x].astype(float), a[i - y].astype(float)) - 1
    f: Dict[str, np.ndarray] = {"mom_12_1": ret(21, 252), "mom_6_1": ret(21, 126), "rev_1m": ret(0, 21), "rev_1w": ret(0, 5)}
    ma200, ma50, ma20 = _nanmean(_win(a, i, 200), 160), _nanmean(_win(a, i, 50), 40), _nanmean(_win(a, i, 20), 20)
    f["high_52w"] = _safe(c[i].astype(float), _nanext(_win(h, i, 252), 200, np.nanmax))
    f["ma200_ratio"] = _safe(a[i].astype(float), ma200)
    f["ma50_200"] = _safe(ma50, ma200)
    prior_55 = _nanext(_win(h, i - 1, 55), 45, np.nanmax) if i else np.full(n, np.nan)
    f["breakout_55"] = _safe(c[i].astype(float), prior_55)
    prior_20, vol_20 = _nanext(_win(h, i - 1, 20), 20, np.nanmax), _nanmean(_win(v, i - 1, 20), 20)
    with np.errstate(invalid="ignore"):
        hit = (c[i] > prior_20) & (v[i] >= 1.5 * vol_20)
    f["breakout_vol"] = np.where(np.isfinite(prior_20) & np.isfinite(vol_20) & np.isfinite(c[i]) & np.isfinite(v[i]), hit.astype(float), np.nan)
    prev = _win(c, i - 1, 60)
    hh, ll = _win(h, i, 60), _win(lo, i, 60)
    if prev.shape[0] == hh.shape[0]:
        with np.errstate(invalid="ignore"):
            tr = np.maximum(hh - ll, np.maximum(np.abs(hh - prev), np.abs(ll - prev)))
        f["vcp"] = _safe(_nanmean(tr[-10:], 10), _nanmean(tr, 55))
    else:
        f["vcp"] = np.full(n, np.nan)
    rng = _win(h, i, 7) - _win(lo, i, 7)
    f["nr7"] = np.full(n, np.nan)
    if rng.shape[0] == 7:
        full = np.isfinite(rng).all(axis=0)
        f["nr7"][full] = (rng[-1, full] < rng[:-1, full].min(axis=0)).astype(float)
    rs = rsi2(a, i)
    f["rsi2"] = rs
    with np.errstate(invalid="ignore"):
        f["pullback_uptrend"] = np.where(a[i] > ma200, rs, np.nan)
    f["boll_z"] = _safe(a[i].astype(float) - ma20, _nanstd(_win(a, i, 20), 20))
    r252, r21 = _returns(a, i, 252), _returns(a, i, 21)
    f["vol_252"] = _nanstd(r252, 200)
    f["max_21"] = _nanext(r21, 21, np.nanmax)
    _, resid_21 = _residual(r21, r21[:, spy], 21)
    f["ivol_21"] = _nanstd(resid_21, 21)
    if r252.shape[0] == 252:
        form = r252[:231]
        _, e_form = _residual(form, form[:, spy], 180)
        sigma = _nanstd(e_form, 180)
        f["resid_mom_12_1"] = _safe(np.where(np.isfinite(sigma), np.nansum(e_form, axis=0), np.nan), sigma)
        beta_recent, _ = _residual(form, form[:, spy], 180)
        recent = r252[231:] - beta_recent * r252[231:, spy][:, None]
        last_21 = np.where(np.isfinite(recent).all(axis=0) & np.isfinite(sigma), np.nansum(recent, axis=0), np.nan)
        f["rev_resid_1m"] = _safe(last_21, sigma)
    else:
        f["resid_mom_12_1"] = f["rev_resid_1m"] = np.full(n, np.nan)
    f["vol_surge"] = _safe(_nanmean(_win(v, i, 5), 5), _nanmean(_win(v, i, 60), 50))
    v20, r20 = _win(v, i, 20).astype(float), r21[-20:]
    if v20.shape[0] == 20 and r20.shape[0] == 20:
        good = np.isfinite(v20) & np.isfinite(r20)
        total = np.where(good, v20, 0.0).sum(axis=0)
        up = np.where(good & (r20 > 0), v20, 0.0).sum(axis=0)
        f["obv_20"] = np.where(good.sum(axis=0) >= 18, _safe(up, total), np.nan)
    else:
        f["obv_20"] = np.full(n, np.nan)
    return f


# ---------------------------------------------------------------------- patterns
def extrema(series: np.ndarray) -> List[Tuple[int, float, str]]:
    """Slope sign changes of the 3-day average: (position, level, 'max' or 'min')."""
    s = np.convolve(series, np.ones(3) / 3, mode="valid")
    out, off = [], 2
    for k in range(1, len(s) - 1):
        if s[k] > s[k - 1] and s[k] >= s[k + 1]:
            out.append((k + off, float(s[k]), "max"))
        elif s[k] < s[k - 1] and s[k] <= s[k + 1]:
            out.append((k + off, float(s[k]), "min"))
    return out


def _near(a: float, b: float, tol: float = PATTERN_TOL) -> bool:
    avg = (a + b) / 2
    return avg > 0 and abs(a - avg) <= tol * avg and abs(b - avg) <= tol * avg


def _double(ex: List[Tuple[int, float, str]], kind: str) -> bool:
    picks = [e for e in ex if e[2] == kind]
    if len(picks) < 2:
        return False
    last = picks[-1]
    earlier = [e for e in picks[:-1] if last[0] - e[0] >= PATTERN_GAP]
    if not earlier:
        return False
    other = max(earlier, key=lambda e: e[1]) if kind == "max" else min(earlier, key=lambda e: e[1])
    return _near(other[1], last[1])


def pattern_signal(closes: np.ndarray) -> Optional[int]:
    """Simplified Lo-Mamaysky-Wang shapes on the last 38 sessions.  +1 bullish, -1 bearish, 0 neither or both; None without data."""
    w = closes[-PATTERN_WINDOW:]
    if len(w) < PATTERN_WINDOW or not np.isfinite(w).all():
        return None
    ex = extrema(w)
    if not ex or ex[-1][0] < len(w) - PATTERN_FRESH:
        return 0
    bear = bull = False
    if len(ex) >= 5:
        e = ex[-5:]
        v = [x[1] for x in e]
        wings = _near(v[0], v[4]) and _near(v[1], v[3])
        bear = e[0][2] == "max" and v[2] > v[0] and v[2] > v[4] and wings
        bull = e[0][2] == "min" and v[2] < v[0] and v[2] < v[4] and wings
    if ex[-1][2] == "max":
        bear = bear or _double(ex, "max")
    else:
        bull = bull or _double(ex, "min")
    return 0 if bull == bear else (1 if bull else -1)


# ---------------------------------------------------------------------- earnings
def sue_point(net_income: List[Dict[str, Any]], day: str) -> Optional[Tuple[float, str]]:
    """Latest year-on-year quarterly change over the spread of the last eight, and its filing date.  Only filings up to ``day`` count."""
    pts = pit.ttm_points(net_income, day)
    if len(pts) < SUE_MIN_CHANGES + 1:
        return None
    changes = np.diff([p["val"] for p in pts])[-8:]
    sd = float(np.std(changes))
    return (float(changes[-1] / sd), pts[-1]["filed"]) if sd > 0 else None


def sue_at(net_income: List[Dict[str, Any]], day: str) -> Optional[float]:
    p = sue_point(net_income, day)
    return p[0] if p and pit._days(p[1], day) <= SUE_MAX_AGE else None


# ---------------------------------------------------------------------- features
def eligible(d: Dict[str, np.ndarray], i: int, cols: Sequence[int]) -> List[int]:
    out = []
    for j in cols:
        c = d["close"][i, j]
        if not np.isfinite(c) or c < MIN_PRICE:
            continue
        if int(np.isfinite(d["close"][max(0, i - HISTORY + 1):i + 1, j]).sum()) < MIN_BARS:
            continue
        value = (d["close"][max(0, i - 19):i + 1, j] * d["volume"][max(0, i - 19):i + 1, j])
        if not np.isfinite(value).any() or np.nanmean(value) < MIN_ADV:
            continue
        out.append(j)
    return out


def sector_demean(values: np.ndarray, groups: np.ndarray, keep: np.ndarray) -> np.ndarray:
    """Value minus its sector's average among the eligible names; an unknown sector or a thin one stays empty."""
    out = np.full(len(values), np.nan)
    for g in set(groups[keep & np.isfinite(values)]):
        if g == "?":
            continue
        m = keep & np.isfinite(values) & (groups == g)
        if int(m.sum()) >= pit.MIN_PEERS:
            out[m] = values[m] - values[m].mean()
    return out


def build_features(px: validate.Prices, members: Callable[[str], List[str]], net_income: Dict[str, List[Dict]], sectors: Dict[str, Optional[str]], progress=None) -> Dict[str, Any]:
    d, spy = px.data, px.col["SPY"]
    rows = list(range(HISTORY, len(px.dates) - 1, STEP))
    groups = np.array([sectors.get(s) or "?" for s in px.symbols])
    tensor = np.full((len(rows), len(px.symbols), len(FACTORS)), np.nan, dtype=np.float32)
    cache: Dict[Tuple[str, str], Optional[Tuple[float, str]]] = {}
    pos = {name: k for k, name in enumerate(FACTORS)}
    counts = []
    for n, i in enumerate(rows):
        day = px.dates[i]
        cols = sorted({px.col[t] for t in members(day) if t in px.col})
        keep_cols = eligible(d, i, cols)
        keep = np.zeros(len(px.symbols), dtype=bool)
        keep[keep_cols] = True
        f = price_features(d, i, spy)
        f["rev_sector_1m"] = sector_demean(f["rev_1m"], groups, keep)
        pat, sue = np.full(len(px.symbols), np.nan), np.full(len(px.symbols), np.nan)
        for j in keep_cols:
            s = pattern_signal(d["adj_close"][i - PATTERN_WINDOW + 1:i + 1, j])
            if s is not None:
                pat[j] = s
            t = px.symbols[j]
            rows_ni = net_income.get(t)
            if rows_ni:
                seen = [r["filed"] for r in rows_ni if r["filed"] <= day]
                if seen:
                    key = (t, max(seen))
                    if key not in cache:
                        cache[key] = sue_point(rows_ni, day)
                    p = cache[key]
                    if p is not None and pit._days(p[1], day) <= SUE_MAX_AGE:
                        sue[j] = p[0]
        f["pattern_net"], f["sue"] = pat, sue
        for name, k in pos.items():
            tensor[n, keep, k] = f[name][keep]
        counts.append({"date": day, "members": len(cols), "eligible": len(keep_cols)})
        if progress:
            progress(n + 1, len(rows), day)
    return {"rows": rows, "tensor": tensor, "counts": counts}


def rank_tensor(tensor: np.ndarray, factors: Sequence[str] = FACTORS, good_high: Optional[Dict[str, bool]] = None) -> np.ndarray:
    """Percentile within the whole eligible universe, 1 at the good end; empty stays empty."""
    good_high = good_high or GOOD_HIGH
    out = np.full(tensor.shape, np.nan, dtype=np.float32)
    for n in range(tensor.shape[0]):
        for k, name in enumerate(factors):
            x = tensor[n, :, k].astype(float)
            m = np.isfinite(x)
            c = int(m.sum())
            if c < 30:
                continue
            r = validate.rank(x[m]) / (c - 1)
            out[n, m, k] = r if good_high[name] else 1 - r
    return out


def composite(ranks_row: np.ndarray, chosen: List[str], factors: Sequence[str] = FACTORS) -> np.ndarray:
    idx = [list(factors).index(f) for f in chosen]
    x = ranks_row[:, idx].astype(float)
    have = np.isfinite(x).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.nansum(x, axis=1) / np.where(have > 0, have, np.nan) * 100
    s[have * 2 < len(idx)] = np.nan
    return s


def _ic(s: np.ndarray, r: np.ndarray) -> Optional[float]:
    ok = np.isfinite(s) & np.isfinite(r)
    if ok.sum() < 30 or s[ok].std() == 0:
        return None
    ex = r[ok] - r[ok].mean()
    if ex.std() == 0:
        return None
    return float(np.corrcoef(validate.rank(s[ok]), validate.rank(ex))[0, 1])


def lag_of(h: int) -> int:
    return max(1, math.ceil(h / STEP))


def select(ranks: np.ndarray, px: validate.Prices, rows: List[int], picks: List[int], h: int, factors: Sequence[str] = FACTORS) -> Dict[str, Any]:
    """The protocol's rule, on development dates only."""
    if any(px.dates[rows[n] + h] >= TEST_START for n in picks):
        raise ValueError("TEST_DATA_IN_DEVELOPMENT")
    returns = {n: px.forward(rows[n], h) for n in picks}
    table = {}
    for k, name in enumerate(factors):
        ics = [v for v in (_ic(ranks[n, :, k].astype(float), returns[n]) for n in picks) if v is not None]
        half = len(ics) // 2
        t = validate.newey_west_t(ics, lag_of(h))
        early, late = (float(np.mean(ics[:half])), float(np.mean(ics[half:]))) if half else (None, None)
        table[name] = {"ic": float(np.mean(ics)) if ics else None, "t": t, "early": early, "late": late, "dates": len(ics),
                       "chosen": bool(t is not None and t >= MIN_T and early is not None and early > 0 and late > 0),
                       "above_bonferroni": bool(t is not None and t >= BONFERRONI_T)}
    return {"horizon": h, "factors": table, "chosen": [f for f in factors if table[f]["chosen"]], "above_bonferroni": [f for f in factors if table[f]["above_bonferroni"]],
            "first": px.dates[rows[picks[0]]] if picks else None, "last": px.dates[rows[picks[-1]]] if picks else None}


def rare_signals(tensor: np.ndarray, px: validate.Prices, rows: List[int], picks: List[int], h: int) -> Dict[str, Any]:
    """How often the on/off signals fired and what followed, excess of the same day's average.  Pooled, not independent."""
    out: Dict[str, Any] = {}
    for name in RARE:
        k = FACTORS.index(name)
        on, off = [], []
        for n in picks:
            r = px.forward(rows[n], h)
            x = tensor[n, :, k].astype(float)
            ok = np.isfinite(x) & np.isfinite(r)
            if ok.sum() < 30:
                continue
            ex = r[ok] - r[ok].mean()
            on.append(ex[x[ok] > 0])
            off.append(ex[x[ok] < 0])
        on_all, off_all = np.concatenate(on) if on else np.array([]), np.concatenate(off) if off else np.array([])
        out[name] = {"positive_n": int(len(on_all)), "positive_excess": float(on_all.mean()) if len(on_all) else None, "negative_n": int(len(off_all)), "negative_excess": float(off_all.mean()) if len(off_all) else None}
    return out


def evaluate(ranks: np.ndarray, px: validate.Prices, rows: List[int], picks: List[int], h: int, chosen: List[str], symbols: List[str], sectors: Dict[str, Optional[str]]) -> Dict[str, Any]:
    cost = config.round_trip_cost("US")
    daily, sc, rt, be, ex = [], [], [], [], []
    spy = px.col["SPY"]
    groups = np.array([sectors.get(s) or "?" for s in symbols])
    above, below = [], []
    a = px.data["adj_close"][:, spy]
    for n in picks:
        i = rows[n]
        r = px.forward(i, h)
        s = composite(ranks[n], chosen)
        day = validate.per_date(s, r, cost, groups)
        if not day:
            continue
        ok = np.isfinite(s) & np.isfinite(r)
        e = r[ok] - r[ok].mean()
        q = validate.rank(s[ok]) / (ok.sum() - 1)
        day.update(date=px.dates[i], top_excess=float(e[q >= 0.8].mean()))
        daily.append(day)
        if day.get("ic") is not None:
            (above if a[i] > np.nanmean(a[i - 199:i + 1]) else below).append(day["ic"])
        sc.append(s[ok]); rt.append(r[ok]); ex.append(e); be.append(np.full(int(ok.sum()), r[spy]))     # noqa: E702
    out = validate.summarize(daily, h)
    if daily:
        out["lag"] = lag_of(h)
        out["t"] = validate.newey_west_t([d["ic"] for d in daily if d.get("ic") is not None], lag_of(h))
        out["top_excess"] = float(np.mean([d["top_excess"] for d in daily]))
        out["buckets"] = validate.bucket_table(*(np.concatenate(x) for x in (sc, rt, be, ex)), cost)
        out["ic_spy_above_200d"] = {"ic": float(np.mean(above)) if above else None, "dates": len(above)}
        out["ic_spy_below_200d"] = {"ic": float(np.mean(below)) if below else None, "dates": len(below)}
    return out


# ---------------------------------------------------------------------- runs
def _load(base: Path):
    root, names, px = validate_oos._load(base)
    return root, names, px


def _sectors(base: Path, root: Path) -> Dict[str, Optional[str]]:
    out = dict(validate._universe(base)["sectors"])
    for f in ("sectors.json", "sectors_open.json", "sectors_oos.json"):
        out.update(json.loads((root / "survivorship" / f).read_text(encoding="utf-8")))
    return out


def _members(base: Path, root: Path) -> Callable[[str], List[str]]:
    from terminal.lab.backtest import members_at
    u0 = validate._universe(base)
    with (root / "survivorship" / "hist_updated.csv").open(newline="", encoding="utf-8") as fh:
        keys, snaps = validate_pit.load_history(list(csv.reader(fh)))
    added = {str(k).upper().replace(".", "-"): v for k, v in json.loads((base / "data" / "lab" / "membership.json").read_text(encoding="utf-8"))["added"].items()}
    previous = validate_open.open_members(validate_pit.members_fn(lambda day: members_at(u0["tickers"], added, day), keys, snaps), keys, snaps, validate_open.load_universe(base))
    return validate_oos.old_members(previous, keys, snaps, validate_oos.load_old(base))


def _net_income(root: Path) -> Dict[str, List[Dict]]:
    out: Dict[str, List[Dict]] = {}
    for folder in ("facts", "facts_recovered", "facts_open", "facts_oos"):
        for f in sorted((root / folder).glob("*.json.gz")):
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                rows = (json.load(fh).get("full") or {}).get("net_income") or []
            out[f.name[:-8]] = rows
    return out


def develop(base: Path, log=print) -> Dict[str, Any]:
    root, _, px = _load(base)
    sectors = _sectors(base, root)
    t0 = time.time()
    b = build_features(px, _members(base, root), _net_income(root), sectors, progress=lambda n, m, d: n % 50 == 0 and log(f"{n}/{m} {d} {time.time() - t0:.0f}s"))
    np.savez_compressed(root / "swing_features.npz", rows=np.array(b["rows"]), tensor=b["tensor"])
    ranks = rank_tensor(b["tensor"])
    res = {}
    for s, h in HORIZONS.items():
        picks = dev_rows(px, b["rows"], h)
        res[s] = select(ranks, px, b["rows"], picks, h)
        res[s]["rare"] = rare_signals(b["tensor"], px, b["rows"], picks, h)
    out = {"status": "DEVELOPED", "protocol": PROTOCOL, "strategies": res, "factors": list(FACTORS), "bonferroni_t": BONFERRONI_T,
           "universe": {"first": b["counts"][0], "last": b["counts"][-1], "mean_eligible": float(np.mean([c["eligible"] for c in b["counts"]]))}}
    (base / DEV_REPORT).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def _live_swing_ic(base: Path, root: Path, px: validate.Prices, first: str) -> Dict[str, Any]:
    """The live-style swing score over the same dates, at its own 21-session spacing.  Reference only."""
    path = root / "scores_open.json.gz"
    if not path.exists():
        return {"status": "UNAVAILABLE"}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        z = json.load(fh)
    by: Dict[str, Dict[str, float]] = {}
    for r in z["records"]:
        v = r.get("SWING|A")
        if v is not None:
            by.setdefault(z["dates"][r["i"]], {})[r["t"]] = v
    pos = {d: i for i, d in enumerate(px.dates)}
    ics = []
    for day in sorted(by):
        i = pos.get(day)
        if day < first or i is None or i + 20 >= len(px.dates):
            continue
        s = np.full(len(px.symbols), np.nan)
        for t, v in by[day].items():
            if t in px.col:
                s[px.col[t]] = v
        ic = _ic(s, px.forward(i, 20))
        if ic is not None:
            ics.append(ic)
    return {"ic": float(np.mean(ics)) if ics else None, "t": validate.newey_west_t(ics, 1), "dates": len(ics)}


def test_once(base: Path) -> Dict[str, Any]:
    target = base / TEST_REPORT
    if target.exists():
        raise RuntimeError("이미 시험을 실행했습니다. 프로토콜상 다시 실행할 수 없습니다.")
    root, _, px = _load(base)
    dev = json.loads((base / DEV_REPORT).read_text(encoding="utf-8"))
    sectors = _sectors(base, root)
    z = np.load(root / "swing_features.npz")
    rows = [int(i) for i in z["rows"]]
    ranks = rank_tensor(z["tensor"])
    out: Dict[str, Any] = {"status": "TESTED", "protocol": PROTOCOL, "strategies": {}, "live_swing_reference": _live_swing_ic(base, root, px, TEST_START)}
    for s, h in HORIZONS.items():
        chosen = dev["strategies"][s]["chosen"]
        picks = test_rows(px, rows, h)
        control_k = FACTORS.index("mom_12_1")
        control = [v for v in (_ic(ranks[n, :, control_k].astype(float), px.forward(rows[n], h)) for n in picks) if v is not None]
        control_out = {"ic": float(np.mean(control)) if control else None, "t": validate.newey_west_t(control, lag_of(h)), "dates": len(control)}
        if not chosen:
            out["strategies"][s] = {"status": "NO_MODEL", "chosen": [], "horizon": h, "control_mom_12_1": control_out, "reason": "개발 구간에서 채택된 요인이 없어 시험하지 않았습니다."}
            continue
        res = evaluate(ranks, px, rows, picks, h, chosen, px.symbols, sectors)
        each = {}
        for f in chosen:
            k = FACTORS.index(f)
            ics = [v for v in (_ic(ranks[n, :, k].astype(float), px.forward(rows[n], h)) for n in picks) if v is not None]
            each[f] = {"ic": float(np.mean(ics)) if ics else None, "t": validate.newey_west_t(ics, lag_of(h)), "dates": len(ics)}
        out["strategies"][s] = {"status": "TESTED", "chosen": chosen, "horizon": h, **res, **test_verdict(res), "each_factor": each, "control_mom_12_1": control_out}
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
