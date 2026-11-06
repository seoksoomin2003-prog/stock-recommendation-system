"""Pre-registered research score.  Rules: reports/QSF_RESEARCH_SCORE_PROTOCOL.md.

Development sees only returns that end before TEST_START.  The test runs once; a second run is refused.  Nothing here changes the
live score, the QSF ledger or P6-11B.
"""
import gzip
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from terminal.qsf import config, pit, validate

TEST_START = "2022-01-01"
SECTOR_RELATIVE = ("earnings_yield", "book_yield", "fcf_yield", "roe", "op_margin", "gp_assets", "accruals", "asset_growth", "share_change", "rev_growth", "eps_growth", "debt_equity")
PRICE_FACTORS = ("mom_12_1", "mom_6_1", "rev_1m", "vol_252", "high_52w")
FACTORS = PRICE_FACTORS + SECTOR_RELATIVE
GOOD_HIGH = {"mom_12_1": True, "mom_6_1": True, "rev_1m": False, "vol_252": False, "high_52w": True, "earnings_yield": True, "book_yield": True, "fcf_yield": True, "roe": True,
             "op_margin": True, "gp_assets": True, "accruals": False, "asset_growth": False, "share_change": False, "rev_growth": True, "eps_growth": True, "debt_equity": False}
HORIZON = {"SWING": 20, "LONG_TERM": 252}
MIN_T = 2.0
MIN_PRICE, MIN_ADV, MIN_BARS = 5.0, 20_000_000.0, 200


def _last(rows: Optional[List[Dict]], back: int = 0) -> Optional[float]:
    return rows[-1 - back]["val"] if rows and len(rows) > back else None


def fund_features(view: Dict[str, List[Dict]], price: float) -> Dict[str, Optional[float]]:
    """Ratios from a split-adjusted TTM view; a missing input leaves the value empty, never zero."""
    def div(a, b):
        return a / b if a is not None and b not in (None, 0) else None

    def growth(k):
        a, b = _last(view.get(k)), _last(view.get(k), 1)
        return a / b - 1 if a is not None and b is not None and b > 0 else None
    shares, eps = _last(view.get("shares_avg")), _last(view.get("eps"))
    ni, eq, assets, ocf, capex = (_last(view.get(k)) for k in ("net_income", "equity", "assets", "ocf", "capex"))
    mcap = price * shares if price and shares else None
    fcf = ocf - capex if ocf is not None and capex is not None else None
    debt = None
    if _last(view.get("debt_long")) is not None or _last(view.get("debt_short")) is not None:
        debt = (_last(view.get("debt_long")) or 0.0) + (_last(view.get("debt_short")) or 0.0)
    elif _last(view.get("liabilities")) is not None:
        debt = _last(view.get("liabilities"))
    return {"earnings_yield": div(eps, price), "book_yield": div(eq, mcap), "fcf_yield": div(fcf, mcap), "roe": div(ni, eq) if (eq or 0) > 0 else None,
            "op_margin": div(_last(view.get("op_income")), _last(view.get("revenue"))), "gp_assets": div(_last(view.get("gross_profit")), assets),
            "accruals": div(ni - ocf, assets) if ni is not None and ocf is not None else None, "asset_growth": growth("assets"), "share_change": growth("shares_avg"),
            "rev_growth": growth("revenue"), "eps_growth": growth("eps"), "debt_equity": div(debt, eq) if (eq or 0) > 0 else None}


def price_features(adj: np.ndarray, high: np.ndarray, close: np.ndarray, i: int) -> Dict[str, Optional[float]]:
    """Each array is one symbol's history; only rows up to ``i`` are read."""
    def ret(a, b):
        x, y = adj[i - a] if i >= a else np.nan, adj[i - b] if i >= b else np.nan
        return float(x / y - 1) if np.isfinite(x) and np.isfinite(y) and y > 0 else None
    w = adj[max(0, i - 252):i + 1]
    d = np.diff(w[np.isfinite(w)])
    base = w[np.isfinite(w)][:-1] if len(d) else w
    vol = float(np.std(d / base)) if len(d) >= 200 else None
    hi = high[max(0, i - 251):i + 1]
    hi = hi[np.isfinite(hi)]
    return {"mom_12_1": ret(21, 252), "mom_6_1": ret(21, 126), "rev_1m": ret(0, 21), "vol_252": vol, "high_52w": float(close[i] / hi.max()) if len(hi) >= 200 and np.isfinite(close[i]) else None}


def percentile(x: np.ndarray, good_high: bool, groups: Optional[np.ndarray] = None, min_peers: int = pit.MIN_PEERS) -> np.ndarray:
    """0..1, 1 is the good end; NaN stays NaN.  A group with too few values gets no rank."""
    out = np.full(len(x), np.nan)
    for g in (set(groups) if groups is not None else {None}):
        m = np.isfinite(x) & (groups == g if groups is not None else True)
        n = int(m.sum())
        if n < min_peers:
            continue
        r = validate.rank(x[m]) / (n - 1)
        out[m] = r if good_high else 1 - r
    return out


def earlier_view(full: Dict[str, List[Dict]], day: str, splits: pit.Splits) -> Dict[str, List[Dict]]:
    return pit.with_ttm_eps(pit.adjust_shares(pit.ttm_view(full, day), day, splits))


def build_features(px: validate.Prices, members: Callable[[str], List[str]], facts: Dict[str, Dict], sectors: Dict[str, Optional[str]], split_map: Dict[str, List], progress=None, view_of: Callable = earlier_view) -> Dict[str, Any]:
    start = next(i for i, d in enumerate(px.dates) if d >= validate.START)
    rows = list(range(max(start, validate.HISTORY), len(px.dates) - 1, validate.STEP))
    split_obj = {t: pit.Splits(split_map.get(t) or []) for t in px.symbols}
    tensor = np.full((len(rows), len(px.symbols), len(FACTORS)), np.nan, dtype=np.float32)
    d = px.data
    for n, i in enumerate(rows):
        day = px.dates[i]
        for t in members(day):
            j = px.col.get(t)
            if j is None or t not in facts or not np.isfinite(d["close"][i, j]):
                continue
            c = d["close"][max(0, i - 319):i + 1, j]
            if int(np.isfinite(c).sum()) < MIN_BARS or d["close"][i, j] < MIN_PRICE:
                continue
            value = np.nanmean((d["close"][:, j] * d["volume"][:, j])[max(0, i - 19):i + 1])
            if not np.isfinite(value) or value < MIN_ADV:
                continue
            f = price_features(d["adj_close"][:, j], d["high"][:, j], d["close"][:, j], i)
            raw = float(d["close"][i, j]) * split_obj[t].factor(day)
            view = view_of(facts[t]["full"], day, split_obj[t])
            f.update(fund_features(view, raw))
            for k, name in enumerate(FACTORS):
                v = f.get(name)
                if v is not None and np.isfinite(v):
                    tensor[n, j, k] = v
        if progress:
            progress(n + 1, len(rows), day)
    return {"rows": rows, "tensor": tensor}


def rank_tensor(tensor: np.ndarray, symbols: List[str], sectors: Dict[str, Optional[str]]) -> np.ndarray:
    groups = np.array([sectors.get(s) or "?" for s in symbols])
    out = np.full(tensor.shape, np.nan, dtype=np.float32)
    for n in range(tensor.shape[0]):
        for k, name in enumerate(FACTORS):
            x = tensor[n, :, k].astype(float)
            out[n, :, k] = percentile(x, GOOD_HIGH[name], groups if name in SECTOR_RELATIVE else None)
    return out


def dev_rows(px: validate.Prices, rows: List[int], h: int) -> List[int]:
    """Positions whose whole return window ended before the test period."""
    return [n for n, i in enumerate(rows) if i + h < len(px.dates) and px.dates[i + h] < TEST_START]


def test_rows(px: validate.Prices, rows: List[int], h: int) -> List[int]:
    return [n for n, i in enumerate(rows) if px.dates[i] >= TEST_START and i + h < len(px.dates)]


def select(ranks: np.ndarray, px: validate.Prices, rows: List[int], picks: List[int], h: int) -> Dict[str, Any]:
    """The protocol's rule, applied to development dates only."""
    if any(px.dates[rows[n] + h] >= TEST_START for n in picks):
        raise ValueError("TEST_DATA_IN_DEVELOPMENT")
    table = {}
    for k, name in enumerate(FACTORS):
        ics = []
        for n in picks:
            r = px.forward(rows[n], h)
            s = ranks[n, :, k].astype(float)
            ok = np.isfinite(s) & np.isfinite(r)
            if ok.sum() >= 30 and s[ok].std() > 0:
                ex = r[ok] - r[ok].mean()
                ics.append(float(np.corrcoef(validate.rank(s[ok]), validate.rank(ex))[0, 1]))
        lag = max(1, int(np.ceil(h / validate.STEP)))
        half = len(ics) // 2
        t = validate.newey_west_t(ics, lag)
        early, late = (float(np.mean(ics[:half])), float(np.mean(ics[half:]))) if half else (None, None)
        table[name] = {"ic": float(np.mean(ics)) if ics else None, "t": t, "early": early, "late": late, "dates": len(ics),
                       "chosen": bool(t is not None and t >= MIN_T and early is not None and early > 0 and late > 0)}
    return {"horizon": h, "factors": table, "chosen": [f for f in FACTORS if table[f]["chosen"]], "first": px.dates[rows[picks[0]]] if picks else None, "last": px.dates[rows[picks[-1]]] if picks else None}


def composite(ranks_row: np.ndarray, chosen: List[str]) -> np.ndarray:
    """Average percentile of the chosen factors x 100; empty when under half of them have a value."""
    idx = [FACTORS.index(f) for f in chosen]
    x = ranks_row[:, idx].astype(float)
    have = np.isfinite(x).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.nansum(x, axis=1) / np.where(have > 0, have, np.nan) * 100
    s[have * 2 < len(idx)] = np.nan
    return s


def test_verdict(s: Dict[str, Any]) -> Dict[str, Any]:
    """The protocol's five conditions; the fifth reads the top fifth instead of a score band."""
    v = validate.verdict({**s, "buy_excess": s.get("top_excess"), "buy_dates": validate.MIN_BUY_DATES})
    return v


def evaluate(ranks: np.ndarray, px: validate.Prices, rows: List[int], picks: List[int], h: int, chosen: List[str], symbols: List[str], sectors: Dict[str, Optional[str]]) -> Dict[str, Any]:
    cost = config.round_trip_cost("US")
    daily, sc, rt, be, ex = [], [], [], [], []
    spy = px.col["SPY"]
    groups = np.array([sectors.get(s) or "?" for s in symbols])
    for n in picks:
        i = rows[n]
        r = px.forward(i, h)
        s = composite(ranks[n], chosen)
        d = validate.per_date(s, r, cost, groups)
        if not d:
            continue
        ok = np.isfinite(s) & np.isfinite(r)
        e = r[ok] - r[ok].mean()
        q = validate.rank(s[ok]) / (ok.sum() - 1)
        d.update(date=px.dates[i], top_excess=float(e[q >= 0.8].mean()))
        daily.append(d)
        sc.append(s[ok]); rt.append(r[ok]); ex.append(e); be.append(np.full(int(ok.sum()), r[spy]))     # noqa: E702
    out = validate.summarize(daily, h)
    if daily:
        out["top_excess"] = float(np.mean([d["top_excess"] for d in daily]))
        out["buckets"] = validate.bucket_table(*(np.concatenate(x) for x in (sc, rt, be, ex)), cost)
    return out


def _load(base: Path):
    from terminal.lab.backtest import members_at
    u = validate._universe(base)
    root = base / "data" / "qsf" / "research"
    px = validate.Prices(root / "prices15y.npz")
    splits = json.loads((root / "prices15y.splits.json").read_text(encoding="utf-8"))
    added = json.loads((base / "data" / "lab" / "membership.json").read_text(encoding="utf-8"))["added"]
    added = {str(k).upper().replace(".", "-"): v for k, v in added.items()}
    return u, root, px, splits, lambda day: members_at(u["tickers"], added, day)


def develop(base: Path, log=print) -> Dict[str, Any]:
    u, root, px, splits, members = _load(base)
    facts = {}
    for f in sorted((root / "facts").glob("*.json.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            facts[f.name[:-8]] = json.load(fh)
    b = build_features(px, members, facts, u["sectors"], splits, progress=lambda n, m, d: n % 20 == 0 and log(f"{n}/{m} {d}"))
    np.savez_compressed(root / "features.npz", rows=np.array(b["rows"]), tensor=b["tensor"])
    ranks = rank_tensor(b["tensor"], px.symbols, u["sectors"])
    res = {s: select(ranks, px, b["rows"], dev_rows(px, b["rows"], h), h) for s, h in HORIZON.items()}
    out = {"status": "DEVELOPED", "protocol": "reports/QSF_RESEARCH_SCORE_PROTOCOL.md", "strategies": res, "factors": list(FACTORS)}
    (base / "reports" / "qsf" / "QSF_RESEARCH_SCORE_DEV.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def test_once(base: Path) -> Dict[str, Any]:
    target = base / "reports" / "qsf" / "QSF_RESEARCH_SCORE_TEST.json"
    if target.exists():
        raise RuntimeError("이미 시험을 실행했습니다. 프로토콜상 다시 실행할 수 없습니다.")
    u, root, px, _, _ = _load(base)
    dev = json.loads((base / "reports" / "qsf" / "QSF_RESEARCH_SCORE_DEV.json").read_text(encoding="utf-8"))
    z = np.load(root / "features.npz")
    rows = [int(i) for i in z["rows"]]
    ranks = rank_tensor(z["tensor"], px.symbols, u["sectors"])
    out: Dict[str, Any] = {"status": "TESTED", "protocol": "reports/QSF_RESEARCH_SCORE_PROTOCOL.md", "strategies": {}}
    for s, h in HORIZON.items():
        chosen = dev["strategies"][s]["chosen"]
        if not chosen:
            out["strategies"][s] = {"status": "NO_MODEL", "chosen": [], "reason": "개발 구간에서 채택된 요인이 없어 시험하지 않았습니다."}
            continue
        res = evaluate(ranks, px, rows, test_rows(px, rows, h), h, chosen, px.symbols, u["sectors"])
        out["strategies"][s] = {"status": "TESTED", "chosen": chosen, "horizon": h, **res, **test_verdict(res)}
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
