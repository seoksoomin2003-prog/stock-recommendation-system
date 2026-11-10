"""The one forward verdict of the live score, per market and strategy.  Rules: reports/QSF_LIVE_FORWARD_PROTOCOL.md.

The QSF ledger is only read.  Every recorded session counts (not one in twenty); overlap is handled by a Newey-West t with the
horizon as lag.  The conditions are the ones the historical checks used (``validate.verdict``), plus the money condition, and the
buy band's return against the index is split into what the score added and what the scanned universe added.  The evaluation is
refused until the fixed number of matured sessions exists, uses exactly that many, and is written once.
"""
import json
import math
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

from terminal.qsf import config, ledger as ledger_mod, validate
from terminal.qsf.ledger import Ledger

PROTOCOL = "reports/QSF_LIVE_FORWARD_PROTOCOL.md"
FIRST = "2026-11-09"                                   # the first ledger session of QSF-1.1.8 in both markets
PRIMARY = {"SWING": 20, "LONG_TERM": 63}
EXTRA = {"SWING": (5, 10), "LONG_TERM": (21,)}
NEED = {s: config.MIN_INDEPENDENT * h for s, h in PRIMARY.items()}
MIN_ROWS = 30
BUY = validate.BUY_SCORE
REPORT_DIR = Path("reports") / "qsf"
NOTE = "NO_EVIDENCE는 '효과 없음'이 아니라 '이 기록으로는 모름'입니다. 겹치는 표본이라 1년 기록의 검정력은 낮습니다."


def report_path(base: Path, market: str, strategy: str) -> Path:
    return Path(base) / REPORT_DIR / f"QSF_LIVE_FORWARD_{market}_{strategy}.json"


def session_rows(led: Ledger, market: str, strategy: str, first: str = FIRST) -> Dict[str, List[Dict[str, Any]]]:
    """Session -> the rows that count: a score, not INSUFFICIENT_DATA, and a price of that very session.  A day under MIN_ROWS is left out."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for r in led._live_rows():
        if r["market"] != market or r["session"] < first:
            continue
        for s in led._load(r):
            if s.get("strategy") == strategy and s.get("score") is not None and s.get("actionability") != "INSUFFICIENT_DATA" and s.get("data_date") == r["session"]:
                out.setdefault(r["session"], []).append(s)
    return {d: v for d, v in sorted(out.items()) if len(v) >= MIN_ROWS}


class Prices:
    """Bars per ticker, loaded once, with what ``ledger.outcome`` needs to answer quickly."""

    def __init__(self, loader: Callable[[str], List[Dict]], bench: List[Dict]):
        self.loader, self.bench = loader, bench
        self.bench_by_date = {b["date"]: b for b in bench}
        self.calendar = sorted(self.bench_by_date)
        self.cache: Dict[str, Any] = {}

    def outcome(self, snap: Dict[str, Any], session: str, h: int, cost: float) -> Optional[Dict[str, float]]:
        if snap["ticker"] not in self.cache:
            bars = self.loader(snap["ticker"]) or []
            days = [b.get("date") for b in bars]
            self.cache[snap["ticker"]] = (bars, days if all(isinstance(d, str) for d in days) and days == sorted(days) else None)
        bars, days = self.cache[snap["ticker"]]
        return ledger_mod.outcome(bars, self.bench, session, h, cost, snap.get("entry_session"), days, self.bench_by_date, self.calendar)


def day_stats(session: str, snaps: List[Dict[str, Any]], px: Prices, h: int, cost: float) -> Optional[Dict[str, Any]]:
    """One session's cross-section, or None while its holds have not ended.  Returns are net of one round trip."""
    score, net, bench = [], [], []
    for s in snaps:
        o = px.outcome(s, session, h, cost)
        if not o:
            continue
        score.append(float(s["score"]))
        net.append(o["net"])
        if o.get("relative_net") is not None and not o.get("stopped"):
            bench.append(o["net"] - o["relative_net"])                   # the index's return over the same days
    if len(score) < MIN_ROWS or not bench:
        return None
    sc, r = np.array(score), np.array(net)
    d = validate.per_date(sc, r, cost)
    if not d or d.get("ic") is None:
        return None
    idx = float(np.median(bench))
    q = validate.rank(sc) / (len(sc) - 1)
    buy, top = r[sc >= BUY], r[q >= 0.8]
    d.update(date=session, universe_net=float(r.mean()), index=idx, universe_effect=float(r.mean()) - idx,
             buy_net=float(buy.mean()) if len(buy) else None, top_net=float(top.mean()) if len(top) else None,
             versions=sorted({str(s.get("model_version")) for s in snaps}))
    return d


def _mean(rows: List[Dict[str, Any]], f: Callable[[Dict[str, Any]], Optional[float]]) -> Optional[float]:
    v = [x for x in (f(r) for r in rows) if x is not None]
    return float(np.mean(v)) if v else None


def summarize(rows: List[Dict[str, Any]], h: int) -> Dict[str, Any]:
    """``rows``: day_stats in date order.  The same fields ``validate.verdict`` reads, with the lag in sessions."""
    mid = rows[len(rows) // 2]["date"]
    early, late = [r for r in rows if r["date"] < mid], [r for r in rows if r["date"] >= mid]
    ic = [r["ic"] for r in rows]

    def part(sel):
        return {"dates": len(sel), "ic": _mean(sel, lambda r: r["ic"]), "spread_net": _mean(sel, lambda r: r.get("spread_net")),
                "buy_minus_index": _mean(sel, lambda r: None if r["buy_net"] is None else r["buy_net"] - r["index"]),
                "score_effect": _mean(sel, lambda r: None if r["buy_net"] is None else r["buy_net"] - r["universe_net"]),
                "top_minus_index": _mean(sel, lambda r: None if r["top_net"] is None else r["top_net"] - r["index"]),
                "top_score_effect": _mean(sel, lambda r: None if r["top_net"] is None else r["top_net"] - r["universe_net"]),
                "universe_effect": _mean(sel, lambda r: r["universe_effect"])}
    separate = ic[::h]
    sd = float(np.std(separate, ddof=1)) if len(separate) > 2 else 0.0
    return {"dates": len(rows), "first": rows[0]["date"], "last": rows[-1]["date"], "split": mid, "lag": h, "mean_n": float(np.mean([r["n"] for r in rows])),
            "ic": float(np.mean(ic)), "t": validate.newey_west_t(ic, h), "ic_positive_share": float(np.mean([x > 0 for x in ic])),
            "spread_net": _mean(rows, lambda r: r.get("spread_net")), "buy_excess": _mean(rows, lambda r: r.get("buy_excess")),
            "buy_dates": sum(1 for r in rows if r.get("buy_excess") is not None), "buy_trades": sum(r.get("buy_n", 0) for r in rows),
            "all": part(rows), "early": part(early), "late": part(late),
            "separate_samples": {"samples": len(separate), "ic": float(np.mean(separate)), "t": float(np.mean(separate) / (sd / math.sqrt(len(separate)))) if sd > 0 else None}}


def reading(s: Dict[str, Any]) -> Dict[str, Any]:
    """Condition A is ``validate.verdict`` unchanged; condition B is the buy band against the index in both halves."""
    a = validate.verdict(s)
    gt = lambda v: v is not None and v > 0          # noqa: E731
    money = gt(s["early"]["buy_minus_index"]) and gt(s["late"]["buy_minus_index"])
    rank_ok = a["verdict"] == "WEAK_POSITIVE_EVIDENCE"
    return {"verdict": "WEAK_POSITIVE_EVIDENCE" if rank_ok and money else "RANK_ONLY" if rank_ok else "NO_EVIDENCE", "condition_a": a["checks"], "condition_b": money}


def matured_sessions(sessions: Sequence[str], calendar: Sequence[str], h: int) -> List[str]:
    """Sessions whose h-session hold from the next session's open can have ended on this calendar."""
    where = {d: n for n, d in enumerate(calendar)}
    return [d for d in sessions if d in where and where[d] + h < len(calendar)]


def status(base: Path, calendars: Dict[str, Sequence[str]]) -> Dict[str, Any]:
    """Counts only: no price is read and no return is computed."""
    led = Ledger(Path(base))
    out: Dict[str, Any] = {"protocol": PROTOCOL, "first": FIRST, "cohorts": {}}
    for market in config.MARKETS:
        for strategy, h in PRIMARY.items():
            days = list(session_rows(led, market, strategy))
            done = len(matured_sessions(days, calendars.get(market) or [], h))
            out["cohorts"][f"{market}_{strategy}"] = {"horizon": h, "recorded": len(days), "matured": done, "needed": NEED[strategy], "ready": done >= NEED[strategy],
                                                     "evaluated": report_path(base, market, strategy).exists()}
    return out


def _pooled(base: Path, strategy: str) -> Optional[Dict[str, Any]]:
    got = {}
    for market in config.MARKETS:
        p = report_path(base, market, strategy)
        if not p.exists():
            return None
        got[market] = json.loads(p.read_text(encoding="utf-8"))["primary"]["t"]
    if any(v is None for v in got.values()):
        return None
    z = sum(got.values()) / math.sqrt(len(got))
    return {"t": got, "combined": z, "engine_level_reference": z >= validate.MIN_T, "note": "참고 근거입니다. 시장별 판정을 바꾸지 않습니다."}


def evaluate_once(base: Path, market: str, strategy: str, loader: Callable[[str], List[Dict]], bench: List[Dict], log=print) -> Dict[str, Any]:
    base = Path(base)
    out = report_path(base, market, strategy)
    if out.exists():
        raise RuntimeError("판정은 한 번만 합니다. 이미 결과가 있습니다.")
    led = Ledger(base)
    if led.verify()["status"] != "OK":
        raise RuntimeError("원장 검증에 실패해 판정하지 않습니다.")
    h, need = PRIMARY[strategy], NEED[strategy]
    rows = session_rows(led, market, strategy)
    px = Prices(loader, bench)
    ready = matured_sessions(list(rows), px.calendar, h)
    if len(ready) < need:
        raise RuntimeError(f"아직 판정할 수 없습니다. 만기 거래일 {len(ready)}개, 기준 {need}개입니다.")
    used = ready[:need]                              # exactly the fixed sample, whenever this is run
    cost = config.round_trip_cost(market)
    days = [d for d in (day_stats(s, rows[s], px, h, cost) for s in used) if d]
    if len(days) < need // 2:
        raise RuntimeError(f"수익을 계산할 수 있는 날이 {len(days)}일뿐입니다. 시세를 확인하세요.")
    primary = summarize(days, h)
    extra = {}
    for x in EXTRA[strategy]:
        got = [d for d in (day_stats(s, rows[s], px, x, cost) for s in used) if d]
        extra[str(x)] = {**summarize(got, x), **reading(summarize(got, x))} if len(got) > 2 * x else {"dates": len(got), "status": "UNAVAILABLE"}
    versions: Dict[str, List[float]] = {}
    for d in days:
        versions.setdefault("+".join(d["versions"]), []).append(d["ic"])
    res = {"status": "REAL", "protocol": PROTOCOL, "market": market, "strategy": strategy, "horizon": h, "sessions_used": len(used), "first": used[0], "last": used[-1],
           "cost_round_trip_pct": cost * 100, **reading(primary), "primary": primary, "other_horizons": extra,
           "by_version": {k: {"dates": len(v), "ic": float(np.mean(v))} for k, v in sorted(versions.items())}, "note": NOTE}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    pooled = _pooled(base, strategy)
    if pooled:
        (base / REPORT_DIR / f"QSF_LIVE_FORWARD_POOLED_{strategy}.json").write_text(json.dumps(pooled, ensure_ascii=False, indent=1), encoding="utf-8")
        res["pooled"] = pooled
    log(f"{market} {strategy}: {res['verdict']}")
    return res
