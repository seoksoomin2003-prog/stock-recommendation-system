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

from terminal.qsf import calibrate, config, ledger as ledger_mod, validate
from terminal.qsf.ledger import Ledger
from utils import durable

PROTOCOL = "reports/QSF_LIVE_FORWARD_PROTOCOL.md"
# The first ledger session the verdicts read.  Until 2026-11-22 it was 2026-11-09 (the first session of QSF-1.1.8): ten sessions
# recorded under seven earlier formulas would have been judged together with the rest.  User decision 2026-11-22: the sample
# starts at the first session recorded under QSF-1.5.0.  No return of any recorded session had been read when it was moved.
# Moved again on 2026-11-25 (user decision) to the first session recorded under QSF-1.6.0, the version the score is frozen at:
# two sessions (11-23, 11-24) under the former capital-spending reading are left out.  Again no return had been read.
FIRST = "2026-11-25"
PRIMARY = {"SWING": 20, "LONG_TERM": 63}
EXTRA = {"SWING": (5, 10), "LONG_TERM": (21,)}
NEED = {s: config.MIN_INDEPENDENT * h for s, h in PRIMARY.items()}
MIN_ROWS = 30
BUY = validate.BUY_SCORE
REPORT_DIR = Path("reports") / "qsf"
# Cohorts whose money conditions read the top fifth of the day instead of the score band of 70: no Korean swing score has ever
# reached 70, so the band condition could not be met whatever the score was worth (audit 2026-11-22, QNT-06; user decision).
TOP_BAND = (("KR", "SWING"),)
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

    def __init__(self, loader: Callable[[str], List[Dict]], bench: List[Dict], benches: Optional[Dict[str, List[Dict]]] = None):
        """``benches``: {a snapshot's recorded benchmark: its bars}.  A stock is compared with the index it was recorded against
        (a KOSDAQ stock with the KOSDAQ index: user decision 2026-11-22); without an entry, with ``bench``."""
        self.loader, self.bench = loader, bench
        self.benches = {k: (v, {b["date"]: b for b in v}) for k, v in (benches or {}).items() if v}
        self.bench_by_date = {b["date"]: b for b in bench}
        self.calendar = sorted(self.bench_by_date)
        self.cache: Dict[str, Any] = {}

    def outcome(self, snap: Dict[str, Any], session: str, h: int, cost: float) -> Optional[Dict[str, float]]:
        if snap["ticker"] not in self.cache:
            bars = self.loader(snap["ticker"]) or []
            days = [b.get("date") for b in bars]
            self.cache[snap["ticker"]] = (bars, days if all(isinstance(d, str) for d in days) and days == sorted(days) else None)
        bars, days = self.cache[snap["ticker"]]
        bench, by_date = self.benches.get(snap.get("benchmark")) or (self.bench, self.bench_by_date)
        return ledger_mod.outcome(bars, bench, session, h, cost, snap.get("entry_session"), days, by_date, self.calendar)


def day_stats(session: str, snaps: List[Dict[str, Any]], px: Prices, h: int, cost: float) -> Optional[Dict[str, Any]]:
    """One session's cross-section, or None while its holds have not ended.  Returns are net of one round trip."""
    score, net, bench, own = [], [], [], []
    for s in snaps:
        o = px.outcome(s, session, h, cost)
        if not o:
            continue
        score.append(float(s["score"]))
        net.append(o["net"])
        own.append(float("nan"))
        if o.get("relative_net") is not None and not o.get("stopped"):
            bench.append(o["net"] - o["relative_net"])                   # the index's return over the same days
            own[-1] = bench[-1]                                          # this stock's own index
    if len(score) < MIN_ROWS or not bench:
        return None
    sc, r = np.array(score), np.array(net)
    d = validate.per_date(sc, r, cost)
    if not d or d.get("ic") is None:
        return None
    idx = float(np.median(bench))
    q = validate.rank(sc) / (len(sc) - 1)
    buy, top = r[sc >= BUY], r[q >= 0.8]
    ix = np.array(own)
    one_index = float(np.nanmax(ix) - np.nanmin(ix)) < 1e-12             # every stock against the same index (the US): the day's index, as before

    def index_of(mask: np.ndarray) -> float:
        """The mean index return of these stocks' own indexes: KOSDAQ names against the KOSDAQ index."""
        return idx if one_index or not np.isfinite(ix[mask]).any() else float(np.nanmean(ix[mask]))
    every = np.ones(len(sc), dtype=bool)
    d.update(date=session, universe_net=float(r.mean()), index=idx, universe_effect=float(r.mean()) - index_of(every),
             buy_index=index_of(sc >= BUY) if len(buy) else None, top_index=index_of(q >= 0.8) if len(top) else None,
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
                "buy_minus_index": _mean(sel, lambda r: None if r["buy_net"] is None else r["buy_net"] - (r["index"] if r.get("buy_index") is None else r["buy_index"])),
                "score_effect": _mean(sel, lambda r: None if r["buy_net"] is None else r["buy_net"] - r["universe_net"]),
                "top_minus_index": _mean(sel, lambda r: None if r["top_net"] is None else r["top_net"] - (r["index"] if r.get("top_index") is None else r["top_index"])),
                "top_score_effect": _mean(sel, lambda r: None if r["top_net"] is None else r["top_net"] - r["universe_net"]),
                "universe_effect": _mean(sel, lambda r: r["universe_effect"])}
    separate = ic[::h]
    sd = float(np.std(separate, ddof=1)) if len(separate) > 2 else 0.0
    return {"dates": len(rows), "first": rows[0]["date"], "last": rows[-1]["date"], "split": mid, "lag": h, "mean_n": float(np.mean([r["n"] for r in rows])),
            "ic": float(np.mean(ic)), "t": validate.newey_west_t(ic, h), "t_bar": calibrate.bar(validate.MIN_T, len(ic), h, 1, h), "t_nominal": validate.MIN_T,
            "ic_positive_share": float(np.mean([x > 0 for x in ic])),
            "spread_net": _mean(rows, lambda r: r.get("spread_net")), "buy_excess": _mean(rows, lambda r: r.get("buy_excess")),
            "buy_dates": sum(1 for r in rows if r.get("buy_excess") is not None), "buy_trades": sum(r.get("buy_n", 0) for r in rows),
            "all": part(rows), "early": part(early), "late": part(late),
            "separate_samples": {"samples": len(separate), "ic": float(np.mean(separate)), "t": float(np.mean(separate) / (sd / math.sqrt(len(separate)))) if sd > 0 else None}}


def reading(s: Dict[str, Any], top_band: bool = False) -> Dict[str, Any]:
    """Condition A is ``validate.verdict`` with the t bar of this sample's own design; condition B is the buy band against the
    index in both halves.  ``top_band`` (the cohorts of ``TOP_BAND``): the two conditions that read the band of 70 read the
    day's top fifth instead, as the challenger readings do."""
    checks = dict(validate.verdict(s)["checks"])
    gt = lambda v: v is not None and v > 0          # noqa: E731
    if top_band:
        checks["buy_band"] = gt(s["all"]["top_score_effect"])
    key = "top_minus_index" if top_band else "buy_minus_index"
    money = gt(s["early"][key]) and gt(s["late"][key])
    rank_ok = all(checks.values())
    return {"verdict": "WEAK_POSITIVE_EVIDENCE" if rank_ok and money else "RANK_ONLY" if rank_ok else "NO_EVIDENCE", "condition_a": checks, "condition_b": money,
            "band": "TOP_FIFTH" if top_band else "SCORE_70", "t_bar": s.get("t_bar")}


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
    got, bars = {}, {}
    for market in config.MARKETS:
        p = report_path(base, market, strategy)
        if not p.exists():
            return None
        primary = json.loads(p.read_text(encoding="utf-8"))["primary"]
        got[market], bars[market] = primary["t"], primary.get("t_bar") or validate.MIN_T
    if any(v is None for v in got.values()):
        return None
    z = sum(got.values()) / math.sqrt(len(got))
    # two independent statistics of the same inflated spread combine into one of that spread: the reference uses the markets' own bar
    bar = max(bars.values())
    return {"t": got, "combined": z, "t_bar": bar, "engine_level_reference": z >= bar, "note": "참고 근거입니다. 시장별 판정을 바꾸지 않습니다."}


def evaluate_once(base: Path, market: str, strategy: str, loader: Callable[[str], List[Dict]], bench: List[Dict], log=print,
                  benches: Optional[Dict[str, List[Dict]]] = None) -> Dict[str, Any]:
    base = Path(base)
    top = (market, strategy) in TOP_BAND
    out = report_path(base, market, strategy)
    if out.exists():
        raise RuntimeError("판정은 한 번만 합니다. 이미 결과가 있습니다.")
    led = Ledger(base)
    if led.verify()["status"] != "OK":
        raise RuntimeError("원장 검증에 실패해 판정하지 않습니다.")
    h, need = PRIMARY[strategy], NEED[strategy]
    rows = session_rows(led, market, strategy)
    px = Prices(loader, bench, benches)
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
        extra[str(x)] = {**summarize(got, x), **reading(summarize(got, x), top)} if len(got) > 2 * x else {"dates": len(got), "status": "UNAVAILABLE"}
    versions: Dict[str, List[float]] = {}
    for d in days:
        versions.setdefault("+".join(d["versions"]), []).append(d["ic"])
    res = {"status": "REAL", "protocol": PROTOCOL, "market": market, "strategy": strategy, "horizon": h, "sessions_used": len(used), "first": used[0], "last": used[-1],
           "cost_round_trip_pct": cost * 100, **reading(primary, top), "primary": primary, "other_horizons": extra,
           "benchmarks": sorted(px.benches) or None,
           "by_version": {k: {"dates": len(v), "ic": float(np.mean(v))} for k, v in sorted(versions.items())}, "note": NOTE}
    out.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(out, json.dumps(res, ensure_ascii=False, indent=1))
    pooled = _pooled(base, strategy)
    if pooled:
        durable.write_text(base / REPORT_DIR / f"QSF_LIVE_FORWARD_POOLED_{strategy}.json", json.dumps(pooled, ensure_ascii=False, indent=1))
        res["pooled"] = pooled
    log(f"{market} {strategy}: {res['verdict']}")
    return res

# ---------------------------------------------------------------------- early readings (pre-registered 2026-11-25)
# User decision 2026-11-25 ("중간 판정 미리 등록"): the first verdict is a year away, so two earlier readings of the swing score
# are fixed now, before the first session of the sample is recorded.  They read the five-session outcome of the first 60 and the
# first 120 matured sessions, against a stricter bar because they are extra looks.  They decide nothing: the verdicts above stay
# the ones that answer whether the score works.  Rules: reports/QSF_LIVE_FORWARD_PROTOCOL.md, "중간 읽기".
EARLY = {60: 5, 120: 5}                 # matured sessions read -> the outcome's length in sessions
EARLY_T = 2.75                          # nominal bar: a one-sided chance of 0.3% a look, so four early looks (two markets, two days) together pass by chance about as often as ONE verdict (1.25%); calibrated for the overlap like theirs
EARLY_KO = {"EARLY_POSITIVE": "순위와 수익 조건을 모두 채움(이른 근거)", "EARLY_RANK_ONLY": "순위 조건만 채움", "EARLY_NOTHING": "구분되지 않음", "EARLY_AGAINST": "순위가 반대로 나옴(통계로 구분됨)"}


def early_path(base: Path, market: str, n: int) -> Path:
    return Path(base) / REPORT_DIR / f"QSF_LIVE_FORWARD_EARLY_{market}_SWING_{n}.json"


def early_once(base: Path, market: str, n: int, loader: Callable[[str], List[Dict]], bench: List[Dict], log=print,
               benches: Optional[Dict[str, List[Dict]]] = None) -> Dict[str, Any]:
    """One early reading of the swing score: the first ``n`` matured sessions, five-session outcomes, read once."""
    if n not in EARLY:
        raise ValueError(n)
    base, h = Path(base), EARLY[n]
    top = (market, "SWING") in TOP_BAND
    out = early_path(base, market, n)
    if out.exists():
        raise RuntimeError("중간 읽기는 한 번만 합니다. 이미 결과가 있습니다.")
    led = Ledger(base)
    if led.verify()["status"] != "OK":
        raise RuntimeError("원장 검증에 실패해 읽지 않습니다.")
    rows = session_rows(led, market, "SWING")
    px = Prices(loader, bench, benches)
    ready = matured_sessions(list(rows), px.calendar, h)
    if len(ready) < n:
        raise RuntimeError(f"아직 읽을 수 없습니다. 만기 거래일 {len(ready)}개, 기준 {n}개입니다.")
    used = ready[:n]                                 # exactly the fixed sample, whenever this is run
    cost = config.round_trip_cost(market)
    days = [d for d in (day_stats(s, rows[s], px, h, cost) for s in used) if d]
    if len(days) < n // 2:
        raise RuntimeError(f"수익을 계산할 수 있는 날이 {len(days)}일뿐입니다. 시세를 확인하세요.")
    s = summarize(days, h)
    s["t_bar"], s["t_nominal"] = calibrate.bar(EARLY_T, len(days), h, 1, h), EARLY_T
    r = reading(s, top)
    against = s["t"] is not None and s["t"] <= -s["t_bar"]
    verdict = "EARLY_AGAINST" if against else {"WEAK_POSITIVE_EVIDENCE": "EARLY_POSITIVE", "RANK_ONLY": "EARLY_RANK_ONLY"}.get(r["verdict"], "EARLY_NOTHING")
    failed = [k for k, ok in r["condition_a"].items() if not ok]
    t_txt = "계산할 수 없음" if s["t"] is None else f"{s['t']:+.2f}"
    reasons = [f"처음 {len(used)}거래일({used[0]} ~ {used[-1]})의 스윙 점수와 그 뒤 {h}거래일 수익의 순위 상관: 평균 {s['ic']:+.3f}, t {t_txt} (기준 {s['t_bar']:g}. 주된 판정보다 엄격한 값입니다).",
               "순위 조건 다섯 가지 가운데 못 채운 것: " + (", ".join(failed) if failed else "없음") + f". 수익 조건(매수 구간이 지수를 전·후반 모두 이김): {'채움' if r['condition_b'] else '못 채움'}.",
               "이 읽기는 짧은 기록을 봅니다. 작은 효과는 잡지 못하고, '구분되지 않음'은 효과가 없다는 뜻이 아닙니다.",
               "무엇이 나와도 점수, 규칙, 주된 판정(240거래일·20거래일 수익)은 바뀌지 않습니다."]
    res = {"status": "REAL", "protocol": PROTOCOL, "kind": "EARLY", "market": market, "strategy": "SWING", "horizon": h, "sessions_used": len(used), "first": used[0], "last": used[-1],
           "cost_round_trip_pct": cost * 100, "verdict": verdict, "condition_a": r["condition_a"], "condition_b": r["condition_b"], "band": r["band"], "t_bar": s["t_bar"],
           "t_nominal": EARLY_T, "summary": s, "reasons": reasons, "applies_itself": False, "note": NOTE}
    out.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(out, json.dumps(res, ensure_ascii=False, indent=1))
    log(f"{market} SWING early {n}: {verdict}")
    return res
