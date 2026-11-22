"""Pre-registered historical check of the QSF 1.2 candidate.  Criteria: reports/QSF_1_2_VALIDATION_PROTOCOL.md.

Research only: it never writes to the QSF ledger and never changes the live score.  Prices and extracted filings are kept in
data/qsf/research/ (git-ignored); the report goes to reports/qsf/QSF_1_2_VALIDATION.json.  It takes no parameters to search.
"""
import gzip
import json
import math
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from terminal import sources
from terminal.qsf import config, engine, fundamentals, pit

START = "2014-01-02"
STEP = 21
HISTORY = 320
PERIOD = "15y"
CHUNK = 50
HORIZONS = {"SWING": (5, 10, 20, 30), "LONG_TERM": (63, 126, 252)}
PRIMARY = {"SWING": 20, "LONG_TERM": 252}
VARIANTS = ("A", "B", "C")
FIELDS = ("open", "high", "low", "close", "adj_close", "volume")
MIN_IC, MIN_T, MIN_BUY_DATES = 0.02, 2.24, 12
BUY_SCORE = 70.0
LIMITS = ["지수에서 빠진 종목이 없어 결과가 부풀려질 수 있습니다 (생존 편향).", "섹터는 현재 GICS 분류를 과거에도 적용했습니다.",
          "시장 국면과 이벤트·지배구조 영역은 시점 기준 이력이 없어 빠졌습니다.", "장기 252거래일의 독립 표본은 약 12개뿐입니다.", "비용은 가정값입니다."]


# ---------------------------------------------------------------------- data
def download_prices(symbols: List[str], path: Path, download=None, progress=None) -> Dict[str, Any]:
    """Split-adjusted OHLC, dividend-adjusted close, volume and split events, in chunks.  A failed chunk is reported, not hidden."""
    def _dl(chunk):
        import yfinance as yf
        return yf.download(chunk, period=PERIOD, interval="1d", auto_adjust=False, actions=True, progress=False, group_by="column", threads=False)
    download = download or _dl
    frames, failed = [], []
    for k in range(0, len(symbols), CHUNK):
        chunk = symbols[k:k + CHUNK]
        try:
            frames.append(download(chunk))
        except Exception as exc:
            failed += [(s, type(exc).__name__) for s in chunk]
        if progress:
            progress(min(k + CHUNK, len(symbols)), len(symbols))
    dates = sorted({d for f in frames for d in f.index})
    pos = {d: i for i, d in enumerate(dates)}
    data = {x: np.full((len(dates), len(symbols)), np.nan) for x in FIELDS}
    col = {s: j for j, s in enumerate(symbols)}
    names = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "adj_close": "Adj Close", "volume": "Volume"}
    splits: Dict[str, List] = {}
    for f in frames:
        rows = [pos[d] for d in f.index]
        for field, name in names.items():
            for s in f[name].columns:
                data[field][rows, col[s]] = f[name][s].to_numpy(dtype=float)
        if "Stock Splits" in f.columns.get_level_values(0):
            for s in f["Stock Splits"].columns:
                x = f["Stock Splits"][s].dropna()
                x = x[x > 0]
                if len(x):
                    splits[s] = [(d.strftime("%Y-%m-%d"), float(v)) for d, v in x.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, dates=np.array([d.strftime("%Y-%m-%d") for d in dates]), symbols=np.array(symbols), **data)
    tmp.replace(path)
    path.with_suffix(".splits.json").write_text(json.dumps(splits), encoding="utf-8")
    return {"dates": len(dates), "symbols": len(symbols), "failed": failed}


def download_facts(ciks: Dict[str, str], folder: Path, fetch=None, progress=None) -> Dict[str, Any]:
    """Extracted series per company; the source file is discarded.  An existing file is kept, so a stopped run can resume."""
    fetch = fetch or sources.sec_companyfacts
    folder.mkdir(parents=True, exist_ok=True)
    failed = []
    for n, (t, cik) in enumerate(sorted(ciks.items()), 1):
        f = folder / f"{t}.json.gz"
        if not f.exists():
            try:
                facts = fetch(cik)
                rec = {"annual": fundamentals.extract_us(facts), "full": pit.extract_full(facts)}
                tmp = f.with_suffix(".tmp")
                with gzip.open(tmp, "wt", encoding="utf-8") as out:
                    json.dump(rec, out)
                tmp.replace(f)
            except Exception as exc:
                failed.append((t, type(exc).__name__))
        if progress:
            progress(n, len(ciks))
    return {"companies": len(ciks), "failed": failed}


class Prices:
    def __init__(self, path: Path):
        z = np.load(path, allow_pickle=False)
        self.dates = [str(d) for d in z["dates"]]
        self.symbols = [str(s) for s in z["symbols"]]
        self.col = {s: j for j, s in enumerate(self.symbols)}
        self.data = {x: z[x] for x in FIELDS}

    def bars(self, j: int, i0: int, i1: int) -> List[Dict[str, Any]]:
        d, out = self.data, []
        o, h, lo, c, a, v = (d[x][i0:i1, j] for x in FIELDS)
        for k in np.flatnonzero(np.isfinite(c)):
            out.append({"date": self.dates[i0 + k], "open": float(o[k]) if o[k] == o[k] else None, "high": float(h[k]) if h[k] == h[k] else None,
                        "low": float(lo[k]) if lo[k] == lo[k] else None, "close": float(c[k]), "adj_close": float(a[k]) if a[k] == a[k] else None,
                        "volume": float(v[k]) if v[k] == v[k] else None})
        return out

    def forward(self, i: int, h: int, cost: float = 0.0) -> np.ndarray:
        """Next-open to h-th-session close on the dividend-adjusted basis, for every symbol; NaN when a price is missing."""
        if i + h >= len(self.dates):
            return np.full(len(self.symbols), np.nan)
        d = self.data
        with np.errstate(invalid="ignore", divide="ignore"):
            entry = d["open"][i + 1] * d["adj_close"][i + 1] / d["close"][i + 1]
            return d["adj_close"][i + h] / entry - 1 - cost


# ---------------------------------------------------------------------- funds
def _raw_close(close: float, splits: pit.Splits, as_of: str) -> float:
    """Yahoo's close is restated for later splits; this is the price actually quoted on ``as_of``."""
    return close * splits.factor(as_of)


def fund_views(rec: Dict[str, Any], close: float, splits: pit.Splits, as_of: str, is_financial: bool) -> Dict[str, Dict[str, Any]]:
    raw = _raw_close(close, splits, as_of)
    annual = {k: [r for r in v if r["filed"] <= as_of] for k, v in rec["annual"].items()}
    a = fundamentals.metrics(pit.adjust_shares(annual, as_of, splits), raw, as_of, is_financial=is_financial, source="SEC 10-K (시점 기준)")
    view = pit.with_ttm_eps(pit.adjust_shares(pit.ttm_view(rec["full"], as_of), as_of, splits))
    b = fundamentals.metrics(view, raw, as_of, is_financial=is_financial, source="SEC 10-K·10-Q TTM (시점 기준)")
    return {"A": a, "B": b}


def usable(res: Dict[str, Any]) -> bool:
    """Live rules minus total coverage: regime and events have no history here, so the total cannot reach its live level by design."""
    return res["score"] is not None and not res["gates"] and not res["short_domains"]


# ---------------------------------------------------------------------- scoring
def score_dates(px: Prices, members: Callable[[str], List[str]], facts: Dict[str, Dict], sectors: Dict[str, Optional[str]], split_map: Dict[str, List],
                progress=None, first: str = START, last: Optional[str] = None, views: Callable = fund_views) -> List[Dict[str, Any]]:
    start = next(i for i, d in enumerate(px.dates) if d >= first)
    bench_j = px.col["SPY"]
    max_h = max(max(v) for v in HORIZONS.values())
    rows = [i for i in range(max(start, HISTORY), len(px.dates) - 1, STEP) if last is None or px.dates[i] <= last]
    split_obj = {t: pit.Splits(split_map.get(t) or []) for t in px.symbols}
    out: List[Dict[str, Any]] = []
    adj = px.data["adj_close"]
    for n, i in enumerate(rows, 1):
        day = px.dates[i]
        i0 = max(0, i - HISTORY + 1)
        bench = px.bars(bench_j, i0, i + 1)
        names = [t for t in members(day) if t in px.col and t in facts and np.isfinite(px.data["close"][i, px.col[t]])]
        funds, ctxs, rets = {}, {}, {}
        for t in names:
            b = px.bars(px.col[t], i0, i + 1)
            if len(b) < config.MIN_BARS or b[-1]["date"] != day:
                continue
            ctxs[t] = {"market": "US", "bars": b, "bench": bench, "bench_name": "SPY", "events": None, "regime": None, "earnings": None, "expected_session": day}
            funds[t] = views(facts[t], b[-1]["close"], split_obj[t], day, sectors.get(t) == "Financials")
            a = adj[:, px.col[t]]
            if i >= 126 and a[i] == a[i] and a[i - 126] == a[i - 126] and a[i - 126] > 0:
                rets[t] = a[i] / a[i - 126] - 1
        ordered = sorted(rets.values())
        ranks = {t: float(np.searchsorted(ordered, v, side="right") / len(ordered)) for t, v in rets.items()} if len(ordered) >= 20 else {}
        rel = pit.sector_ranks({t: f["B"] for t, f in funds.items() if f["B"].get("status") in ("REAL", "STALE")}, sectors)
        for t, ctx in ctxs.items():
            base = dict(ctx, rs_rank=ranks.get(t))
            fund = funds[t]
            c = dict(fund["B"], rel=rel[t]) if t in rel else fund["B"]
            rec: Dict[str, Any] = {"i": i, "t": t, "sector": sectors.get(t)}
            a = adj[:, px.col[t]]
            if i >= 252 and a[i - 21] == a[i - 21] and a[i - 252] == a[i - 252] and a[i - 252] > 0:
                rec["mom_12_1"] = float(a[i - 21] / a[i - 252] - 1)
            for strategy in HORIZONS:
                for v, f in (("A", fund["A"]), ("B", fund["B"]), ("C", c)):
                    res = engine.score(dict(base, fund=f), strategy)
                    base.setdefault("tech", res["tech"])
                    base.setdefault("levels", res["levels"])
                    if usable(res):
                        rec[f"{strategy}|{v}"] = res["score"]
                        if v == "C":
                            for d in ("TECHNICAL", "FUNDAMENTAL", "RISK"):
                                rec[f"{strategy}|{d}"] = res["domains"][d]["score_100"]
            out.append(rec)
        if progress:
            progress(n, len(rows), day, len(ctxs))
    return out


# ---------------------------------------------------------------------- statistics
def rank(x: np.ndarray) -> np.ndarray:
    """Average ranks, ties shared."""
    order = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    r[order] = np.arange(len(x), dtype=float)
    vals, inv, cnt = np.unique(x, return_inverse=True, return_counts=True)
    s = np.zeros(len(vals))
    np.add.at(s, inv, r)
    return (s / cnt)[inv]


def newey_west_t(x: List[float], lag: int) -> Optional[float]:
    a = np.asarray(x, dtype=float)
    n = len(a)
    if n < 3:
        return None
    e = a - a.mean()
    var = float((e * e).sum() / n)
    for k in range(1, min(lag, n - 1) + 1):
        var += 2 * (1 - k / (lag + 1)) * float((e[k:] * e[:-k]).sum() / n)
    return float(a.mean() / math.sqrt(var / n)) if var > 0 else None


def per_date(score: np.ndarray, ret: np.ndarray, cost: float, sector: Optional[np.ndarray] = None) -> Optional[Dict[str, Any]]:
    ok = np.isfinite(score) & np.isfinite(ret)
    if ok.sum() < 30:
        return None
    s, r = score[ok], ret[ok]
    ex = r - r.mean()
    out: Dict[str, Any] = {"n": int(ok.sum()), "ic": float(np.corrcoef(rank(s), rank(ex))[0, 1]) if s.std() > 0 and ex.std() > 0 else None}
    q = rank(s) / (len(s) - 1)
    top, bot = ex[q >= 0.8], ex[q <= 0.2]
    out["spread_net"] = float(top.mean() - bot.mean() - cost) if len(top) and len(bot) else None
    buy = ex[s >= BUY_SCORE]
    out["buy_excess"], out["buy_n"] = (float(buy.mean()) if len(buy) else None), int(len(buy))
    if sector is not None:
        sec = sector[ok]
        neutral = ex.copy()
        for g in set(sec):
            m = sec == g
            neutral[m] = ex[m] - ex[m].mean()
        out["ic_sector_neutral"] = float(np.corrcoef(rank(s), rank(neutral))[0, 1]) if neutral.std() > 0 and s.std() > 0 else None
    return out


def summarize(rows: List[Dict[str, Any]], h: int) -> Dict[str, Any]:
    """``rows``: per_date outputs in date order, each with ``date``."""
    rows = [r for r in rows if r and r.get("ic") is not None]
    if not rows:
        return {"dates": 0, "status": "UNAVAILABLE"}
    mid = rows[len(rows) // 2]["date"]
    lag = max(1, math.ceil(h / STEP))

    def m(sel, key):
        v = [r[key] for r in sel if r.get(key) is not None]
        return float(np.mean(v)) if v else None
    early, late = [r for r in rows if r["date"] < mid], [r for r in rows if r["date"] >= mid]
    ic = [r["ic"] for r in rows]
    return {"dates": len(rows), "first": rows[0]["date"], "last": rows[-1]["date"], "split": mid, "lag": lag, "mean_n": float(np.mean([r["n"] for r in rows])),
            "ic": float(np.mean(ic)), "t": newey_west_t(ic, lag), "ic_positive_share": float(np.mean([x > 0 for x in ic])), "ic_sector_neutral": m(rows, "ic_sector_neutral"),
            "spread_net": m(rows, "spread_net"), "buy_excess": m(rows, "buy_excess"), "buy_dates": sum(1 for r in rows if r.get("buy_excess") is not None),
            "buy_trades": sum(r.get("buy_n", 0) for r in rows),
            "early": {"ic": m(early, "ic"), "spread_net": m(early, "spread_net"), "dates": len(early)}, "late": {"ic": m(late, "ic"), "spread_net": m(late, "spread_net"), "dates": len(late)}}


def verdict(s: Dict[str, Any]) -> Dict[str, Any]:
    """The protocol's five conditions, unchanged.  ``WEAK_POSITIVE_EVIDENCE`` is the strongest word this check can return."""
    gt = lambda v, x: v is not None and v > x      # noqa: E731
    # ``t_bar``: the bar for this summary's own design (terminal/qsf/calibrate.py), set by the readings that have not run yet
    checks = {"ic": s.get("ic") is not None and s["ic"] >= MIN_IC, "t": s.get("t") is not None and s["t"] >= (s.get("t_bar") or MIN_T),
              "ic_both_halves": gt((s.get("early") or {}).get("ic"), 0) and gt((s.get("late") or {}).get("ic"), 0),
              "spread_both_halves": gt((s.get("early") or {}).get("spread_net"), 0) and gt((s.get("late") or {}).get("spread_net"), 0),
              "buy_band": gt(s.get("buy_excess"), 0) and s.get("buy_dates", 0) >= MIN_BUY_DATES}
    return {"verdict": "WEAK_POSITIVE_EVIDENCE" if all(checks.values()) else "NO_EVIDENCE", "checks": checks}


def bucket_table(score: np.ndarray, ret: np.ndarray, bench: np.ndarray, excess: np.ndarray, cost: float) -> Dict[str, Any]:
    """What happened to the stocks of each score band: arrays are pooled over dates.  Descriptive, not independent samples."""
    out = {}
    for lo, hi in config.BUCKETS:
        m = np.isfinite(score) & np.isfinite(ret) & (score >= lo) & (score < hi)
        n = int(m.sum())
        rel = ret[m] - bench[m] - cost
        rel = rel[np.isfinite(rel)]
        out[f"{lo:g}-{min(hi, 100):.0f}"] = {"n": n, "mean_net": float((ret[m] - cost).mean()) if n else None, "median_net": float(np.median(ret[m] - cost)) if n else None,
                                             "win_rate": float((ret[m] - cost > 0).mean()) if n else None, "mean_vs_bench_net": float(rel.mean()) if len(rel) else None,
                                             "beat_bench_rate": float((rel > 0).mean()) if len(rel) else None, "mean_vs_average": float(excess[m].mean()) if n else None,
                                             "beat_average_rate": float((excess[m] > 0).mean()) if n else None}
    return out


def analyze(px: Prices, recs: List[Dict[str, Any]]) -> Dict[str, Any]:
    cost = config.round_trip_cost("US")
    by_i: Dict[int, List[Dict]] = {}
    for r in recs:
        by_i.setdefault(r["i"], []).append(r)
    out: Dict[str, Any] = {"cost_round_trip": cost, "tables": {}, "buckets": {}}

    def buckets(key: str, h: int) -> Dict[str, Any]:
        sc, rt, be, ex = [], [], [], []
        for i in sorted(by_i):
            fwd = px.forward(i, h)
            g = by_i[i]
            score = np.array([r[key] if r.get(key) is not None else np.nan for r in g], dtype=float)
            ret = np.array([fwd[px.col[r["t"]]] for r in g], dtype=float)
            ok = np.isfinite(score) & np.isfinite(ret)
            if ok.sum() < 30:
                continue
            sc.append(score[ok])
            rt.append(ret[ok])
            be.append(np.full(int(ok.sum()), fwd[px.col["SPY"]]))
            ex.append(ret[ok] - ret[ok].mean())
        if not sc:
            return {}
        return bucket_table(*(np.concatenate(x) for x in (sc, rt, be, ex)), cost)

    def table(key: str, h: int, strategy_rows=None) -> Dict[str, Any]:
        rows = []
        for i in sorted(by_i):
            fwd = px.forward(i, h)
            g = by_i[i]
            score = np.array([r.get(key, np.nan) if r.get(key) is not None else np.nan for r in g], dtype=float)
            ret = np.array([fwd[px.col[r["t"]]] for r in g], dtype=float)
            sec = np.array([r["sector"] or "?" for r in g])
            d = per_date(score, ret, cost, sec)
            if d:
                d["date"] = px.dates[i]
                rows.append(d)
        return summarize(rows, h)
    for strategy, hs in HORIZONS.items():
        for h in hs:
            for name in (*VARIANTS, "TECHNICAL", "FUNDAMENTAL", "RISK"):
                out["tables"][f"{strategy}|{name}|{h}"] = table(f"{strategy}|{name}", h)
            out["tables"][f"{strategy}|mom_12_1|{h}"] = table("mom_12_1", h)
            for name in VARIANTS:
                out["buckets"][f"{strategy}|{name}|{h}"] = buckets(f"{strategy}|{name}", h)
    out["primary"] = {s: {"horizon": PRIMARY[s], **out["tables"][f"{s}|C|{PRIMARY[s]}"], **verdict(out["tables"][f"{s}|C|{PRIMARY[s]}"])} for s in PRIMARY}
    return out


# ---------------------------------------------------------------------- run
def _universe(base: Path) -> Dict[str, Any]:
    d = json.loads((base / "data" / "sp500_universe_cache.json").read_text(encoding="utf-8"))
    tick = lambda t: str(t).upper().replace(".", "-")      # noqa: E731
    return {"tickers": sorted({tick(t) for t in d["tickers"]}), "sectors": {tick(k): v.get("gics_sector") for k, v in d["constituents"].items()},
            "ciks": {tick(k): str(v) for k, v in d["ciks"].items()}}


def prepare(base: Path, log=print) -> Dict[str, Any]:
    u = _universe(base)
    root = base / "data" / "qsf" / "research"
    t0 = time.time()
    p = download_prices(u["tickers"] + ["SPY"], root / "prices15y.npz", progress=lambda a, b: log(f"prices {a}/{b} {time.time() - t0:.0f}s"))
    f = download_facts({t: c for t, c in u["ciks"].items() if t in set(u["tickers"])}, root / "facts", progress=lambda a, b: a % 25 == 0 and log(f"facts {a}/{b} {time.time() - t0:.0f}s"))
    return {"prices": p, "facts": f}


def run(base: Path, log=print) -> Dict[str, Any]:
    from terminal.lab.backtest import members_at
    u = _universe(base)
    root = base / "data" / "qsf" / "research"
    px = Prices(root / "prices15y.npz")
    splits = json.loads((root / "prices15y.splits.json").read_text(encoding="utf-8"))
    added = json.loads((base / "data" / "lab" / "membership.json").read_text(encoding="utf-8"))["added"]
    added = {str(k).upper().replace(".", "-"): v for k, v in added.items()}
    facts = {}
    for f in sorted((root / "facts").glob("*.json.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            facts[f.name[:-8]] = json.load(fh)
    t0 = time.time()
    recs = score_dates(px, lambda day: members_at(u["tickers"], added, day), facts, u["sectors"], splits,
                       progress=lambda n, m, d, k: log(f"{n}/{m} {d} {k} stocks {time.time() - t0:.0f}s"))
    with gzip.open(root / "scores.json.gz", "wt", encoding="utf-8") as fh:      # later analysis needs no rescoring
        json.dump({"dates": px.dates, "records": recs}, fh)
    result = analyze(px, recs)
    result.update(status="REAL", model="QSF-1.2 candidate (research only)", protocol="reports/QSF_1_2_VALIDATION_PROTOCOL.md", limitations=LIMITS, evaluations=len(recs),
                  companies=len(facts), price_last=px.dates[-1])
    out = base / "reports" / "qsf" / "QSF_1_2_VALIDATION.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result
