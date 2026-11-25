"""Backtest of the score as it is today on the history this device holds.  Rules: reports/QSF_BACKTEST_CURRENT_PROTOCOL.md
(user instruction 2026-11-25: "우리 프로그램의 점수 매기는 알고리즘으로 백테스팅을 돌려봐").

The live scoring code (``engine.score`` with the live weights, QSF-1.6.0) is run on what was public on each evaluation day, with
the two replays this project already has: the US one (S&P 500 members of the day with the recovered and open-archive names,
SEC filings by filing date) and the Korean one (KRX snapshots with delisted names, DART statements by receipt date, the live
universe of the top 300 by market value).  Nothing is searched or tuned here: one formula, one run.

Every window read here was read by an earlier test.  The result is a description of the current formula on used history, not
new independent evidence, and the report says so.  Research only: no ledger, no forward record and no live score is touched.
"""
from __future__ import annotations

import gzip
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from terminal.qsf import config, validate

PROTOCOL = "reports/QSF_BACKTEST_CURRENT_PROTOCOL.md"
VERSION = "BT-1"
REPORT = {m: Path("reports") / "qsf" / f"QSF_BACKTEST_CURRENT_{m}.json" for m in ("US", "KR")}
HOLD = 21                               # sessions between evaluation days and of every portfolio hold: holds never overlap
PER_YEAR = 252 / HOLD
HORIZONS = {"SWING": (5, 10, 20), "LONG_TERM": (63, 126, 252)}
PRIMARY = {"SWING": 20, "LONG_TERM": 252}
BUY = validate.BUY_SCORE
MIN_NAMES = 30
NOTE = ("이 결과는 지금 공식을 이미 여러 번 본 과거 구간에 다시 적용한 것입니다. 새로운 독립 증거가 아니며, 이 결과를 보고 고른 변경은 "
        "앞으로 쌓이는 기록으로만 확인할 수 있습니다.")


# ---------------------------------------------------------------------- scores of the current formula
def _stored(path: Path) -> Optional[List[Dict[str, Any]]]:
    """Scores this module stored under today's formula, or None."""
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return None
    return doc.get("records") if doc.get("model_version") == config.MODEL_VERSION else None


def us_scores(base: Path, log=print) -> Dict[str, Any]:
    """Every evaluation day's live-style scores (annual statements as filed, the live reading).  Reads no return."""
    from terminal.lab.backtest import members_at
    from terminal.qsf import fundamentals, pit, validate_corrected as vc, validate_open, validate_pit
    root = Path(base) / "data" / "qsf" / "research"
    u0, names = validate._universe(base), validate_open.load_universe(base)
    keys, snaps = vc._history(root)
    added = vc._added(base)
    px = validate_open.OpenPrices(root / "prices15y_open.npz", names)
    splits: Dict[str, Any] = {}
    for f in ("prices15y.splits.json", "prices_recovered.splits.json", "prices_open.splits.json"):
        splits.update(json.loads((root / f).read_text(encoding="utf-8")))
    sectors = {**u0["sectors"], **json.loads((root / "survivorship" / "sectors.json").read_text(encoding="utf-8")),
               **json.loads((root / "survivorship" / "sectors_open.json").read_text(encoding="utf-8"))}
    previous = validate_pit.members_fn(lambda day: members_at(u0["tickers"], added, day), keys, snaps)

    def live_view(rec, close, split, as_of, is_financial):
        raw = validate._raw_close(close, split, as_of)
        a = fundamentals.metrics(pit.adjust_shares(vc.as_of_annual(rec["annual"], as_of), as_of, split), raw, as_of, is_financial=is_financial, source="SEC 10-K (시점 기준)")
        return {"A": a, "B": a}                      # one reading, the live one: the candidate readings of earlier tests are not rerun
    out = _stored(root / "scores_current_us.json.gz")           # scores hold no return: a run stopped after scoring picks them up
    if out is None:
        t0 = time.time()
        recs = validate.score_dates(px, validate_open.open_members(previous, keys, snaps, names), vc.load_facts(root), sectors, splits,
                                    progress=lambda n, m, d, k: log(f"US {n}/{m} {d} {k} {time.time() - t0:.0f}s") if n % 10 == 0 or n == m else None, views=live_view)
        out = [{"i": r["i"], "t": r["t"], "sector": r.get("sector"), "SWING": r.get("SWING|A"), "LONG_TERM": r.get("LONG_TERM|A")} for r in recs]
        with gzip.open(root / "scores_current_us.json.gz", "wt", encoding="utf-8") as fh:
            json.dump({"dates": px.dates, "records": out, "model_version": config.MODEL_VERSION}, fh)
    return {"px": px, "records": out, "bench": lambda i, h: float(px.forward(i, h)[px.col["SPY"]]), "bench_name": "SPY(다음 날 시가 진입, 배당 포함)"}


def kr_scores(base: Path, log=print) -> Dict[str, Any]:
    """The same for Korea: the live universe (top 300 by market value), the live engine as it is today.  Reads no return."""
    from terminal.qsf import research_kr_live as rk
    base = Path(base)
    px = rk.ensure_panel(base, log)
    st = rk._statements(base)
    rows = rk.eval_rows(px)
    out = _stored(base / rk.DATA / "scores_current_cap.json.gz")
    if out is None:
        recs: List[Dict[str, Any]] = []
        t0 = time.time()
        for n, i in enumerate(rows, 1):
            recs.extend(rk.score_day(px, i, st, "cap"))
            if n % 10 == 0 or n == len(rows):
                log(f"KR {n}/{len(rows)} {px.dates[i]} {time.time() - t0:.0f}s")
        out = [{"i": r["i"], "t": r["t"], "sector": None, "SWING": r.get("SWING"), "LONG_TERM": r.get("LONG_TERM")} for r in recs]
        with gzip.open(base / rk.DATA / "scores_current_cap.json.gz", "wt", encoding="utf-8") as fh:
            json.dump({"dates": px.dates, "rows": rows, "records": out, "model_version": config.MODEL_VERSION}, fh)
    view = rk._View(px)
    return {"px": view, "records": out, "bench": lambda i, h: float(px.market_return(i, h)), "bench_name": "시가총액 가중 시장(전 종목)"}


# ---------------------------------------------------------------------- statistics
def _by_day(records: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    out: Dict[int, List[Dict[str, Any]]] = {}
    for r in records:
        out.setdefault(r["i"], []).append(r)
    return out


def _day_arrays(px: Any, group: List[Dict[str, Any]], key: str, i: int, h: int):
    fwd = px.forward(i, h)
    score = np.array([r[key] if r.get(key) is not None else np.nan for r in group], dtype=float)
    ret = np.array([fwd[px.col[r["t"]]] for r in group], dtype=float)
    ok = np.isfinite(score) & np.isfinite(ret)
    return score[ok], ret[ok], [r["t"] for r, k in zip(group, ok) if k]


def rank_table(px: Any, by_i: Dict[int, List[Dict[str, Any]]], key: str, h: int, cost: float) -> Dict[str, Any]:
    """The five conditions' inputs (``validate.summarize``) for one strategy and horizon, and the verdict they give."""
    rows = []
    for i in sorted(by_i):
        score, ret, _ = _day_arrays(px, by_i[i], key, i, h)
        d = validate.per_date(score, ret, cost) if len(score) >= MIN_NAMES else None
        if d:
            d["date"] = px.dates[i]
            rows.append(d)
    if len(rows) < 6:
        return {"status": "UNAVAILABLE", "dates": len(rows)}
    s = validate.summarize(rows, h)
    return {**s, **validate.verdict(s)}


def quintiles(px: Any, by_i: Dict[int, List[Dict[str, Any]]], key: str, h: int, cost: float, bench: Callable[[int, int], float]) -> Dict[str, Any]:
    """Mean forward return of each fifth of the day's scores (1 = lowest), net of the round-trip cost, and against the index.
    ``monotone``: whether each fifth earned more than the one below it.  ``band``: the same for scores of ``BUY`` or more."""
    fifths: List[List[float]] = [[] for _ in range(5)]
    band, band_n, idx = [], [], []
    for i in sorted(by_i):
        score, ret, _ = _day_arrays(px, by_i[i], key, i, h)
        b = bench(i, h)
        if len(score) < MIN_NAMES or not math.isfinite(b):
            continue
        order = np.argsort(score, kind="stable")
        for k, part in enumerate(np.array_split(order, 5)):
            fifths[k].append(float(ret[part].mean()) - cost)
        idx.append(b)
        hit = score >= BUY
        if hit.any():
            band.append(float(ret[hit].mean()) - cost - b)
            band_n.append(int(hit.sum()))
    if not idx:
        return {"status": "UNAVAILABLE"}
    means = [float(np.mean(f)) for f in fifths]
    return {"dates": len(idx), "fifth_net": means, "index": float(np.mean(idx)), "top_minus_bottom": means[4] - means[0], "top_minus_index": means[4] - float(np.mean(idx)),
            "monotone": all(means[k + 1] > means[k] for k in range(4)),
            "band": {"dates": len(band), "mean_names": float(np.mean(band_n)) if band_n else 0.0, "minus_index": float(np.mean(band)) if band else None,
                     "positive_share": float(np.mean([x > 0 for x in band])) if band else None}}


def _metrics(r: np.ndarray) -> Dict[str, Any]:
    """Figures of a series of non-overlapping ``HOLD``-session returns."""
    if len(r) < 6:
        return {"periods": int(len(r))}
    growth = np.cumprod(1 + r)
    peak = np.maximum.accumulate(growth)
    sd = float(r.std(ddof=1))
    down = r[r < 0]
    dsd = float(np.sqrt((down ** 2).mean())) if len(down) else 0.0
    years = len(r) / PER_YEAR
    return {"periods": int(len(r)), "cagr_pct": float((growth[-1] ** (1 / years) - 1) * 100), "vol_pct": sd * math.sqrt(PER_YEAR) * 100,
            "sharpe": float(r.mean() / sd * math.sqrt(PER_YEAR)) if sd > 0 else None, "sortino": float(r.mean() / dsd * math.sqrt(PER_YEAR)) if dsd > 0 else None,
            "max_drawdown_pct": float((growth / peak - 1).min() * 100), "worst_period_pct": float(r.min() * 100), "positive_share": float((r > 0).mean())}


def portfolios(px: Any, by_i: Dict[int, List[Dict[str, Any]]], key: str, cost: float, bench: Callable[[int, int], float]) -> Dict[str, Any]:
    """Made-up accounts rebalanced every ``HOLD`` sessions at the next open, equal weight: the top fifth by score, the scores of
    ``BUY`` or more (cash when there is none), and every scored stock.  Cost: the round trip on the share of the account that
    changed hands.  Beside them the index.  Figures only describe this history."""
    days = sorted(by_i)
    series: Dict[str, List[float]] = {"TOP_FIFTH": [], "BUY_BAND": [], "ALL_SCORED": [], "INDEX": []}
    held: Dict[str, set] = {"TOP_FIFTH": set(), "BUY_BAND": set(), "ALL_SCORED": set()}
    turn: Dict[str, List[float]] = {k: [] for k in held}
    names_n: Dict[str, List[int]] = {k: [] for k in held}
    dates: List[str] = []
    for i in days:
        score, ret, names = _day_arrays(px, by_i[i], key, i, HOLD)
        b = bench(i, HOLD)
        if len(score) < MIN_NAMES or not math.isfinite(b):
            continue
        order = np.argsort(score, kind="stable")
        picks = {"TOP_FIFTH": set(order[-max(1, len(order) // 5):].tolist()), "BUY_BAND": set(np.flatnonzero(score >= BUY).tolist()), "ALL_SCORED": set(range(len(score)))}
        for k, sel in picks.items():
            now = {names[j] for j in sel}
            if not now:                              # nothing in the band: the account waits in cash
                series[k].append(0.0)
                turn[k].append(1.0 if held[k] else 0.0)
            else:
                changed = len(now - held[k]) / len(now)          # the share bought this time (equal weights: the same share is sold)
                series[k].append(float(np.mean([ret[j] for j in sel])) - cost * changed)
                turn[k].append(changed)
            names_n[k].append(len(now))
            held[k] = now
        series["INDEX"].append(b)
        dates.append(px.dates[i])
    out: Dict[str, Any] = {"hold_sessions": HOLD, "first": dates[0] if dates else None, "last": dates[-1] if dates else None, "accounts": {}}
    idx = np.array(series["INDEX"])
    half = len(idx) // 2
    for k, v in series.items():
        r = np.array(v)
        m = _metrics(r)
        if k != "INDEX" and len(r) >= 6:
            ex = r - idx
            sd = float(ex.std(ddof=1))
            m.update(mean_turnover=float(np.mean(turn[k])), mean_names=float(np.mean(names_n[k])), excess_per_period_pct=float(ex.mean() * 100),
                     excess_t=float(ex.mean() / (sd / math.sqrt(len(ex)))) if sd > 0 else None, beat_index_share=float((ex > 0).mean()),
                     excess_early_pct=float(ex[:half].mean() * 100), excess_late_pct=float(ex[half:].mean() * 100),
                     by_year={y: float((np.prod(1 + r[[d[:4] == y for d in dates]]) - np.prod(1 + idx[[d[:4] == y for d in dates]])) * 100) for y in sorted({d[:4] for d in dates})})
        out["accounts"][k] = m
    return out


def analyse(scored: Dict[str, Any], market: str) -> Dict[str, Any]:
    px, by_i, bench = scored["px"], _by_day(scored["records"]), scored["bench"]
    cost = config.round_trip_cost(market)
    out: Dict[str, Any] = {"cost_round_trip_pct": cost * 100, "benchmark": scored["bench_name"], "evaluation_days": len(by_i), "strategies": {}}
    days = sorted(by_i)
    out["first"], out["last"] = px.dates[days[0]], px.dates[days[-1]]
    out["mean_scored"] = {s: float(np.mean([sum(1 for r in by_i[i] if r.get(s) is not None) for i in days])) for s in HORIZONS}
    for strategy, hs in HORIZONS.items():
        block: Dict[str, Any] = {"primary_horizon": PRIMARY[strategy], "horizons": {}}
        for h in hs:
            block["horizons"][str(h)] = {"rank": rank_table(px, by_i, strategy, h, cost), "fifths": quintiles(px, by_i, strategy, h, cost, bench)}
        block["accounts"] = portfolios(px, by_i, strategy, cost, bench)
        p = block["horizons"][str(PRIMARY[strategy])]
        rank_ok = p["rank"].get("verdict") == "WEAK_POSITIVE_EVIDENCE"
        money = (p["fifths"].get("top_minus_index") or 0) > 0 and ((block["accounts"]["accounts"].get("TOP_FIFTH") or {}).get("excess_early_pct") or 0) > 0 \
            and ((block["accounts"]["accounts"].get("TOP_FIFTH") or {}).get("excess_late_pct") or 0) > 0
        block["reading"] = "RANK_AND_MONEY" if rank_ok and money else "RANK_ONLY" if rank_ok else "MONEY_ONLY" if money else "NEITHER"
        out["strategies"][strategy] = block
    return out


def run(base: Path, market: str, log=print, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> Dict[str, Any]:
    """One market, once: a report on file is returned as it is and nothing is run again."""
    base = Path(base)
    target = base / REPORT[market]
    if target.exists():
        return json.loads(target.read_text(encoding="utf-8"))
    scored = us_scores(base, log) if market == "US" else kr_scores(base, log)
    res = {"status": "REAL", "protocol": PROTOCOL, "version": VERSION, "market": market, "model_version": config.MODEL_VERSION, "run_at": now().isoformat(),
           **analyse(scored, market), "rerun_of_used_windows": True, "note": NOTE}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res
