"""Pre-registered combined score.  Rules: reports/QSF_ENSEMBLE_PROTOCOL.md.

Signals come from themes that replicated in the literature, grouped by theme and weighted equally.  No return decides which signal
enters or how much it weighs: the only thing measured before the run is how alike the themes are, without returns.  The evaluation runs
once and a second run is refused.  Nothing here changes the live score, the QSF ledger or P6-11B.
"""
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from terminal.qsf import config, pit, research_insider as ri, research_score as sc, research_swing as rs, validate, validate_corrected as vc

PROTOCOL = "reports/QSF_ENSEMBLE_PROTOCOL.md"
REPORT = Path("reports") / "qsf" / "QSF_ENSEMBLE.json"
FUND_FILE = "ensemble_fund.npz"
START = "2014-01-02"
TEST_START = "2022-01-01"
HORIZONS = {"SWING_20": 20, "LONG_252": 252}
MERGE_AT = 0.5
MIN_SHARE = 0.7       # a stock needs this share of the theme groups, and a theme half of its signals

THEMES: Dict[str, Sequence[str]] = {
    "value": ("earnings_yield", "book_yield", "fcf_yield"),
    "profitability": ("roe", "op_margin", "gp_assets"),
    "profit_growth": ("rev_growth", "eps_growth", "sue"),
    "accruals": ("accruals",),
    "investment": ("asset_growth",),
    "issuance": ("share_change",),
    "low_risk": ("vol_252", "ivol_21", "max_21"),
    "momentum": ("mom_12_1", "mom_6_1", "resid_mom_12_1", "high_52w"),
    "reversal": ("rev_1m", "rev_resid_1m"),
    "insider": ("insider_opp_buyers", "insider_net"),
}
FUND = tuple(s for s in sc.FACTORS if s in {x for v in THEMES.values() for x in v} and s in sc.SECTOR_RELATIVE)
SWING = tuple(s for s in rs.FACTORS if s in {x for v in THEMES.values() for x in v})
INSIDER = THEMES["insider"]


def fund_tensor(px: validate.Prices, members, facts: Dict[str, Dict], splits: Dict[str, List], rows: List[int], progress=None) -> np.ndarray:
    """Raw company ratios on the same dates as the price signals.  Only what was filed by each date is read."""
    d = px.data
    out = np.full((len(rows), len(px.symbols), len(FUND)), np.nan, dtype=np.float32)
    split_obj = {t: pit.Splits(splits.get(t) or []) for t in px.symbols}
    for n, i in enumerate(rows):
        day = px.dates[i]
        if day < START:
            continue
        for j in rs.eligible(d, i, sorted({px.col[t] for t in members(day) if t in px.col})):
            t = px.symbols[j]
            if t not in facts:
                continue
            raw = float(d["close"][i, j]) * split_obj[t].factor(day)
            f = sc.fund_features(vc.ttm_view(facts[t]["full"], day, split_obj[t]), raw)
            for k, name in enumerate(FUND):
                v = f.get(name)
                if v is not None and np.isfinite(v):
                    out[n, j, k] = v
        if progress:
            progress(n + 1, len(rows), day)
    return out


def signal_ranks(fund: np.ndarray, swing: np.ndarray, insider: np.ndarray, symbols: List[str], sectors: Dict[str, Optional[str]]) -> Dict[str, np.ndarray]:
    """Percentile of every signal, 1 at the good end.  Company ratios rank inside their sector, as in the earlier research."""
    groups = np.array([sectors.get(s) or "?" for s in symbols])
    out: Dict[str, np.ndarray] = {}
    for k, name in enumerate(FUND):
        m = np.full(fund.shape[:2], np.nan, dtype=np.float32)
        for n in range(fund.shape[0]):
            m[n] = sc.percentile(fund[n, :, k].astype(float), sc.GOOD_HIGH[name], groups)
        out[name] = m
    r = rs.rank_tensor(swing)
    for name in SWING:
        out[name] = r[:, :, rs.FACTORS.index(name)]
    r = rs.rank_tensor(insider, ri.FACTORS, ri.GOOD_HIGH)
    for name in INSIDER:
        out[name] = r[:, :, ri.FACTORS.index(name)]
    return out


def _mean(stack: List[np.ndarray], need: float) -> np.ndarray:
    x = np.stack(stack).astype(float)
    have = np.isfinite(x).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.nansum(x, axis=0) / np.where(have > 0, have, np.nan)
    s[have < need * len(stack)] = np.nan
    return s


def theme_scores(ranks: Dict[str, np.ndarray], themes: Dict[str, Sequence[str]] = THEMES) -> Dict[str, np.ndarray]:
    return {t: _mean([ranks[s] for s in sig], 0.5) for t, sig in themes.items()}


def theme_correlation(scores: Dict[str, np.ndarray], picks: Sequence[int]) -> Dict[str, Dict[str, Optional[float]]]:
    """Mean same-day rank correlation between themes.  Reads no return."""
    names = list(scores)
    out: Dict[str, Dict[str, Optional[float]]] = {a: {} for a in names}
    for x, a in enumerate(names):
        for b in names[x:]:
            v = []
            for n in picks:
                p, q = scores[a][n], scores[b][n]
                ok = np.isfinite(p) & np.isfinite(q)
                if ok.sum() >= 30 and p[ok].std() > 0 and q[ok].std() > 0:
                    v.append(float(np.corrcoef(validate.rank(p[ok]), validate.rank(q[ok]))[0, 1]))
            out[a][b] = out[b][a] = float(np.mean(v)) if v else None
    return out


def merge_groups(corr: Dict[str, Dict[str, Optional[float]]], at: float = MERGE_AT) -> List[List[str]]:
    """Themes this alike count as one group, transitively.  The sign does not matter: alike is alike."""
    groups = [[t] for t in corr]
    for a in corr:
        for b in corr:
            v = corr[a][b]
            if a < b and v is not None and abs(v) >= at:
                ga = next(g for g in groups if a in g)
                gb = next(g for g in groups if b in g)
                if ga is not gb:
                    ga.extend(gb)
                    groups.remove(gb)
    return [sorted(g) for g in groups]


def combine(scores: Dict[str, np.ndarray], groups: List[List[str]]) -> np.ndarray:
    return _mean([_mean([scores[t] for t in g], 0.5) for g in groups], MIN_SHARE) * 100


def evaluate(score: np.ndarray, px: validate.Prices, rows: List[int], picks: List[int], h: int, sectors: Dict[str, Optional[str]]) -> Dict[str, Any]:
    cost = config.round_trip_cost("US")
    groups = np.array([sectors.get(s) or "?" for s in px.symbols])
    daily, sc_, rt, be, ex, above, below = [], [], [], [], [], [], []
    spy = px.col["SPY"]
    a = px.data["adj_close"][:, spy]
    for n in picks:
        i = rows[n]
        r = px.forward(i, h)
        s = score[n].astype(float)
        day = validate.per_date(s, r, cost, groups)
        if not day:
            continue
        ok = np.isfinite(s) & np.isfinite(r)
        e = r[ok] - r[ok].mean()
        q = validate.rank(s[ok]) / (ok.sum() - 1)
        day.update(date=px.dates[i], top_excess=float(e[q >= 0.8].mean()), n=int(ok.sum()))
        daily.append(day)
        if day.get("ic") is not None:
            (above if a[i] > np.nanmean(a[i - 199:i + 1]) else below).append(day["ic"])
        sc_.append(s[ok]); rt.append(r[ok]); ex.append(e); be.append(np.full(int(ok.sum()), r[spy]))     # noqa: E702
    out = validate.summarize(daily, h)
    if daily:
        out["t"] = validate.newey_west_t([d["ic"] for d in daily if d.get("ic") is not None], rs.lag_of(h))
        out["top_excess"] = float(np.mean([d["top_excess"] for d in daily]))
        out["mean_stocks"] = float(np.mean([d["n"] for d in daily]))
        out["buckets"] = validate.bucket_table(*(np.concatenate(x) for x in (sc_, rt, be, ex)), cost)
        out["ic_spy_above_200d"] = {"ic": float(np.mean(above)) if above else None, "dates": len(above)}
        out["ic_spy_below_200d"] = {"ic": float(np.mean(below)) if below else None, "dates": len(below)}
    return out


def windows(px: validate.Prices, rows: List[int], h: int) -> Dict[str, List[int]]:
    early = [n for n, i in enumerate(rows) if START <= px.dates[i] and i + h < len(px.dates) and px.dates[i + h] < TEST_START]
    test = [n for n, i in enumerate(rows) if px.dates[i] >= TEST_START and i + h < len(px.dates)]
    return {"early": early, "test": test}


# ---------------------------------------------------------------------- runs
def _inputs(base: Path):
    root, _, px = rs._load(base)
    z = np.load(root / "swing_features_corrected.npz")
    rows = [int(i) for i in z["rows"]]
    y = np.load(root / "insider_features.npz")
    if [int(i) for i in y["rows"]] != rows:
        raise ValueError("ROWS_DIFFER")
    return root, px, rows, z["tensor"], y["tensor"]


def _splits(root: Path) -> Dict[str, List]:
    out: Dict[str, List] = {}
    for f in ("prices_2008.splits.json", "prices_oos_open.splits.json"):
        out.update(json.loads((root / f).read_text(encoding="utf-8")))
    return out


def prepare(base: Path, log=print) -> Dict[str, Any]:
    """Company ratios and how alike the themes are.  No return is computed."""
    root, px, rows, swing, insider = _inputs(base)
    t0 = time.time()
    fund = fund_tensor(px, rs._members(base, root), vc.load_facts(root), _splits(root), rows, progress=lambda n, m, d: n % 100 == 0 and log(f"{n}/{m} {d} {time.time() - t0:.0f}s"))
    np.savez_compressed(root / FUND_FILE, tensor=fund)
    scores = theme_scores(signal_ranks(fund, swing, insider, px.symbols, rs._sectors(base, root)))
    picks = [n for n, i in enumerate(rows) if START <= px.dates[i] < TEST_START]
    corr = theme_correlation(scores, picks)
    return {"status": "PREPARED", "correlation": corr, "groups": merge_groups(corr), "dates": len(picks), "coverage": {t: float(np.mean(np.isfinite(scores[t][picks]).sum(axis=1))) for t in scores}}


def run_once(base: Path, log=print) -> Dict[str, Any]:
    target = base / REPORT
    if target.exists():
        raise RuntimeError("이미 시험을 실행했습니다. 프로토콜상 다시 실행할 수 없습니다.")
    root, px, rows, swing, insider = _inputs(base)
    sectors = rs._sectors(base, root)
    fund = np.load(root / FUND_FILE)["tensor"]
    scores = theme_scores(signal_ranks(fund, swing, insider, px.symbols, sectors))
    corr = theme_correlation(scores, [n for n, i in enumerate(rows) if START <= px.dates[i] < TEST_START])
    groups = merge_groups(corr)
    score = combine(scores, groups)
    out: Dict[str, Any] = {"status": "TESTED", "protocol": PROTOCOL, "groups": groups, "correlation": corr, "strategies": {}}
    for s, h in HORIZONS.items():
        w = windows(px, rows, h)
        test = evaluate(score, px, rows, w["test"], h, sectors)
        early = evaluate(score, px, rows, w["early"], h, sectors)
        themes = {}
        for t, m in scores.items():
            ics = {k: [v for v in (rs._ic(m[n].astype(float), px.forward(rows[n], h)) for n in w[k]) if v is not None] for k in w}
            themes[t] = {k: {"ic": float(np.mean(v)) if v else None, "t": validate.newey_west_t(v, rs.lag_of(h)), "dates": len(v)} for k, v in ics.items()}
        out["strategies"][s] = {"horizon": h, **test, **sc.test_verdict(test), "earlier_2014_2021": early, "themes": themes}
        log(f"{s} done")
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
