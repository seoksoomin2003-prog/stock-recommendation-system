"""The US challenger score, written down every session and kept apart from the live score.  Rules: reports/QSF_US_CHALLENGER_PROTOCOL.md.

Signals that move together count as one bundle and every bundle weighs the same.  The inputs are the normalized values the QSF ledger
already holds, so both scores read the same data.  The ledger is only read.  A record is written once and chained by hash.  No return is
computed while the record grows, and the single evaluation of each strategy is refused until enough sessions have matured.
"""
import gzip
import json
from datetime import datetime, time as clock, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

import numpy as np

from terminal.qsf import config, kr_forward as kf, research_ensemble as en, research_kr as kr, research_swing as rs, validate
from terminal.qsf.ledger import Ledger
from terminal.qsf.research_score import test_verdict
from utils import durable, nyse_calendar

PROTOCOL = "reports/QSF_US_CHALLENGER_PROTOCOL.md"
FOLDER = Path("research_data") / "us_challenger"
FIRST = "2026-11-09"       # the first ledger session after the input corrections of QSF-1.1.6 and 1.1.7
MIN_ROWS = 400             # fewer than this in one strategy is a partial day, not a day
STEP = 5
MIN_T = 2.0
HORIZONS = {"SWING": 20, "LONG_TERM": 63}
REPORTS = {"SWING": Path("reports") / "qsf" / "QSF_US_CHALLENGER_SWING.json", "LONG_TERM": Path("reports") / "qsf" / "QSF_US_CHALLENGER_LONG.json"}
BUNDLES: Dict[str, List[List[str]]] = {     # settled before the first record, from a measurement that read no return
    "SWING": [["trend_structure", "relative_strength", "breakout_volume", "atr_risk", "drawdown_gap"], ["momentum"], ["volatility_structure"], ["earnings_revenue_quality"],
              ["profitability"], ["balance_sheet"], ["cash_flow_quality"], ["risk_reward"], ["liquidity"], ["insider_activity"]],
    "LONG_TERM": [["long_trend", "relative_strength", "momentum_persistence"], ["valuation"], ["business_quality", "free_cash_flow"], ["growth_quality"],
                  ["balance_dilution", "financial_resilience", "leverage"], ["downside_drawdown"], ["liquidity"], ["insider_ownership"], ["capital_allocation"]],
}
NEW_YORK = ZoneInfo("America/New_York")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def next_open(session: str) -> datetime:
    return datetime.combine(nyse_calendar.next_session(session), clock(9, 30), NEW_YORK)


def _percentile(values: np.ndarray) -> np.ndarray:
    """0 to 1 among the stocks that have a value, ties shared.  An empty value stays empty."""
    out = np.full(len(values), np.nan)
    ok = np.isfinite(values)
    if ok.sum() >= 2:
        out[ok] = validate.rank(values[ok]) / (ok.sum() - 1)
    return out


def score_strategy(snaps: List[Dict[str, Any]], strategy: str) -> List[Dict[str, Any]]:
    """``snaps``: one session and one strategy, with a live score.  Reads each signal's normalized value, nothing else."""
    bundles = BUNDLES[strategy]
    table = [{f["factor"]: f.get("normalized") for f in s["factors"]} for s in snaps]

    def column(name: str) -> np.ndarray:
        return np.array([np.nan if t.get(name) is None else float(t[name]) for t in table], dtype=float)
    ranks = {name: _percentile(column(name)) for b in bundles for name in b}
    final = en.combine(ranks, bundles)
    per_bundle = [en._mean([ranks[n] for n in b], 0.5) * 100 for b in bundles]

    def val(x: Any) -> Optional[float]:
        v = float(x)
        return round(v, 3) if np.isfinite(v) else None
    return [{"ticker": s["ticker"], "score": val(final[i]), "bundles": [val(p[i]) for p in per_bundle], "live": val(s["score"]), "actionability": s.get("actionability")} for i, s in enumerate(snaps)]


def score_session(snaps: List[Dict[str, Any]], session: str) -> Dict[str, Any]:
    """A stock whose ledger date is not this session is left out.  A partial day raises, and is asked again at the next run."""
    fresh = [s for s in snaps if s.get("data_date") == session and s.get("score") is not None]
    out: Dict[str, Any] = {}
    for strategy in BUNDLES:
        rows = sorted((s for s in fresh if s["strategy"] == strategy), key=lambda s: s["ticker"])
        if len(rows) < MIN_ROWS:
            raise ValueError("TOO_FEW_STOCKS")
        out[strategy] = score_strategy(rows, strategy)
    return {"session": session, "protocol": PROTOCOL, "bundles": BUNDLES, "model_versions": sorted({str(s.get("model_version")) for s in fresh}), "strategies": out}


def _session_snaps(led: Ledger, session: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in led._live_rows():
        if r["market"] == "US" and r["session"] == session:
            out += led._load(r)
    return out


def write_record(base: Path, led: Ledger, day: str, at: datetime, late: bool) -> bool:
    """Write-once.  A file left without its index line by a crash gets the line it was written with."""
    folder = Path(base) / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    if day in {r["session"] for r in kf.read_index(base, FOLDER)}:
        return False
    p = folder / f"{day}.json.gz"
    if not p.exists():
        doc = {**score_session(_session_snaps(led, day), day), "recorded_at": at.isoformat(), "late": late, "before_next_open": at < next_open(day)}
        tmp = p.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False)
        durable.replace(tmp, p)
    doc = kf._read_day(folder, day)
    stocks = len(doc["strategies"]["SWING"])
    kf._append_index(folder, day, doc["recorded_at"], doc["late"], doc["before_next_open"], stocks)
    return True


def record(base: Path, now: Callable[[], datetime] = _utcnow, first: str = FIRST) -> Dict[str, Any]:
    """OK: caught up to the last finished session.  WAITING: the ledger does not have that session yet, or it is partial."""
    at = now()
    led = Ledger(Path(base))
    if led.verify()["status"] != "OK":
        return {"status": "FAILED", "reason": "LEDGER_BROKEN"}
    expected = nyse_calendar.latest_completed_session(at).isoformat()
    sessions = sorted({r["session"] for r in led._live_rows() if r["market"] == "US" and r["session"] >= first})
    done = {r["session"] for r in kf.read_index(base, FOLDER)}
    wrote: List[str] = []
    partial: List[str] = []
    for day in sessions:
        if day in done:
            continue
        try:
            if write_record(base, led, day, at, day != sessions[-1]):
                wrote.append(day)
        except ValueError as exc:
            if str(exc) != "TOO_FEW_STOCKS":
                raise
            partial.append(day)
    last = max(done | set(wrote), default=None)
    fine = expected < first or (last is not None and last >= expected)
    return {"status": "OK" if fine and not partial else "WAITING", "written": wrote, "partial": partial, "last": last, "expected": expected}


def status(base: Path, calendar: Optional[Sequence[str]]) -> Dict[str, Any]:
    """Dates and counts only.  ``calendar`` None means the sessions could not be established."""
    out = kf.status(base, calendar, FOLDER)
    out.pop("price_check", None)
    sessions = [r["session"] for r in kf.read_index(base, FOLDER)]
    cal = list(calendar) if calendar is not None else []
    h = HORIZONS["LONG_TERM"]
    matured = sum(1 for s in sessions if sum(1 for d in cal if d > s) >= h)
    out.update(first_due=FIRST, long_horizon=h, long_matured=matured, long_independent=matured / h, long_needed=config.MIN_INDEPENDENT * h)
    return out


# ---------------------------------------------------------------------- the one evaluation of each strategy
class Panel(validate.Prices):
    """Prices held in memory.  A stock whose quotes stop is held at its last price, so a stock that vanished is not dropped as a winner would be."""

    def __init__(self, dates: List[str], symbols: List[str], data: Dict[str, np.ndarray]):
        self.dates, self.symbols, self.data = dates, symbols, data
        self.col = {s: j for j, s in enumerate(symbols)}


def build_panel(tickers: Sequence[str], loader: Callable[[str], List[Dict]], ledger_close: Dict[str, Dict[str, float]]) -> Panel:
    bench = loader("SPY") or []
    if not bench:
        raise RuntimeError("SPY 시세가 없어 평가하지 않습니다.")
    dates = [b["date"] for b in bench]
    place = {d: i for i, d in enumerate(dates)}
    symbols = ["SPY"] + sorted(set(tickers) - {"SPY"})
    data = {k: np.full((len(dates), len(symbols)), np.nan) for k in ("open", "close", "adj_close")}
    for j, t in enumerate(symbols):
        bars = [b for b in (bench if t == "SPY" else loader(t) or []) if b.get("close") and b.get("adj_close")]
        if not bars:       # no quotes at all: the closes the ledger stored on the day, with the open taken as the close
            bars = [{"date": d, "open": p, "close": p, "adj_close": p} for d, p in sorted((ledger_close.get(t) or {}).items())]
        for b in bars:
            i = place.get(b["date"])
            if i is not None:
                data["open"][i, j], data["close"][i, j], data["adj_close"][i, j] = b.get("open") or np.nan, b["close"], b["adj_close"]
        have = np.flatnonzero(np.isfinite(data["close"][:, j]))
        if not len(have):
            continue
        prev = have[0]
        for i in range(have[0] + 1, len(dates)):
            if np.isfinite(data["close"][i, j]):
                prev = i
            else:          # traded at the last price, so the open equals the close
                data["open"][i, j] = data["close"][i, j] = data["close"][prev, j]
                data["adj_close"][i, j] = data["adj_close"][prev, j]
    return Panel(dates, symbols, data)


def _top_vs_spy(score: np.ndarray, px: Panel, rows: List[int], h: int, cost: float) -> Dict[str, Any]:
    ns = list(range(score.shape[0]))[::max(1, h // STEP)]
    ret = np.stack([px.forward(rows[n], h) for n in ns])
    tops = []
    for n in ns:
        out = np.zeros(score.shape[1], dtype=bool)
        idx = np.flatnonzero(np.isfinite(score[n]))
        out[idx[np.argsort(-score[n][idx])[:max(1, len(idx) // 5)]]] = True
        tops.append(out)
    path = kr.rebalance_path(tops, ret, cost)
    market = [float(v) for v in ret[:, px.col["SPY"]]]
    a, b = kf._half(path), kf._half(market)
    parts = [{"top_fifth": kr.annual_growth(a[k], h, 252), "spy": kr.annual_growth(b[k], h, 252)} for k in (0, 1)]
    beats = all(p["top_fifth"] is not None and p["spy"] is not None and p["top_fifth"] > p["spy"] for p in parts)
    return {"periods": len(ns), "top_fifth": kr.annual_growth(path, h, 252), "spy": kr.annual_growth(market, h, 252), "early": parts[0], "late": parts[1], "beats_spy_in_both_halves": beats}


def paired_ic(score: np.ndarray, live: np.ndarray, px: Panel, rows: List[int], h: int) -> Dict[str, Any]:
    """Same stocks and same dates, challenger minus live.  Both matrices hold values only where both scores exist."""
    diff = []
    for n, i in enumerate(rows):
        r = px.forward(i, h)
        a, b = rs._ic(score[n], r), rs._ic(live[n], r)
        if a is not None and b is not None:
            diff.append(a - b)
    if not diff:
        return {"dates": 0, "mean": None, "t": None, "early": None, "late": None, "supports_challenger": False}
    x, y = kf._half(diff)
    t = validate.newey_west_t(diff, rs.lag_of(h))
    early, late = float(np.mean(x)) if x else None, float(np.mean(y)) if y else None
    good = np.mean(diff) > 0 and t is not None and t >= MIN_T and (early or 0) > 0 and (late or 0) > 0
    return {"dates": len(diff), "mean": float(np.mean(diff)), "t": t, "early": early, "late": late, "supports_challenger": bool(good)}


def evaluate_once(base: Path, strategy: str, loader: Callable[[str], List[Dict]], calendar: Sequence[str], log=print) -> Dict[str, Any]:
    target = Path(base) / REPORTS[strategy]
    if target.exists():
        raise RuntimeError("이미 평가했습니다. 규칙상 다시 평가할 수 없습니다.")
    if kf.verify(base, FOLDER)["status"] != "OK":
        raise RuntimeError("기록 검증에 실패해 평가하지 않습니다.")
    index = kf.read_index(base, FOLDER)
    if not index:
        raise RuntimeError("기록이 없습니다.")
    h = HORIZONS[strategy]
    cal = list(calendar)
    where = {d: n for n, d in enumerate(cal)}
    matured = [r["session"] for r in index if r["session"] in where and where[r["session"]] + h < len(cal)]
    need = config.MIN_INDEPENDENT * h
    if len(matured) < need:
        raise RuntimeError(f"아직 평가할 수 없습니다. 만기 거래일 {len(matured)}개, 기준 {need}개입니다.")
    folder = Path(base) / FOLDER
    chosen = matured[::STEP]
    records = {d: kf._read_day(folder, d)["strategies"][strategy] for d in chosen}
    closes: Dict[str, Dict[str, float]] = {}
    led = Ledger(Path(base))
    for s in led.snapshots(market="US", strategy=strategy):
        if s.get("price"):
            closes.setdefault(s["ticker"], {})[s["data_date"]] = float(s["price"])
    px = build_panel(sorted({r["ticker"] for v in records.values() for r in v}), loader, closes)
    place = {d: i for i, d in enumerate(px.dates)}
    chosen = [d for d in chosen if d in place]
    rows = [place[d] for d in chosen]
    score, live = np.full((len(rows), len(px.symbols)), np.nan), np.full((len(rows), len(px.symbols)), np.nan)
    for n, d in enumerate(chosen):
        for r in records[d]:
            j = px.col.get(r["ticker"])
            if j is not None and r["score"] is not None and r["live"] is not None and r.get("actionability") != "INSUFFICIENT_DATA":
                score[n, j], live[n, j] = r["score"], r["live"]
    picks = list(range(len(rows)))
    cost = config.round_trip_cost("US")
    test, base_test = en.evaluate(score, px, rows, picks, h, {}, cost), en.evaluate(live, px, rows, picks, h, {}, cost)
    verdict, base_verdict = test_verdict(test), test_verdict(base_test)
    paired = paired_ic(score, live, px, rows, h)
    later = [v for v in (rs._ic(score[n], px.forward(rows[n] + 1, h)) for n in picks) if v is not None]
    out = {"status": "EVALUATED", "protocol": PROTOCOL, "strategy": strategy, "horizon": h, "dates": len(rows), "first": chosen[0], "last": chosen[-1], "cost": cost,
           "challenger": {**test, **verdict, "top_vs_spy": _top_vs_spy(score, px, rows, h, cost)}, "live": {**base_test, **base_verdict, "top_vs_spy": _top_vs_spy(live, px, rows, h, cost)},
           "paired_ic": paired, "supports_challenger": verdict["verdict"] == "WEAK_POSITIVE_EVIDENCE" and paired["supports_challenger"],
           "one_day_later_entry_ic": float(np.mean(later)) if later else None, "late_share": sum(1 for r in index if r["late"]) / len(index)}
    target.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(target, json.dumps(out, ensure_ascii=False, indent=1, default=str))
    return out
