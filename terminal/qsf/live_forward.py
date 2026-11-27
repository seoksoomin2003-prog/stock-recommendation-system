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

from terminal.qsf import calibrate, config, engine, ledger as ledger_mod, validate, wording
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


# What a reading reads of a snapshot, and of each of its factors.  A whole snapshot is about 37 KB in memory (its holding plan and
# the factors' sources and sentences are most of it); a sample of 260 US sessions held whole took 5-6 GB and the 819 of the long
# verdict would take 15-19 GB, more than the computer has (drill of 2026-11-28).  Keeping these fields changes no figure: nothing
# below reads another.  A new reading that needs another field adds it here (tests/test_live_forward.py holds the two lists).
ROW_FIELDS = ("ticker", "strategy", "score", "actionability", "data_date", "entry_session", "benchmark", "model_version", "price")
FACTOR_FIELDS = ("factor", "weight", "normalized", "scored", "status")


def light(s: Dict[str, Any]) -> Dict[str, Any]:
    """A snapshot cut to what the readings read (``ROW_FIELDS``, the statement basis, ``FACTOR_FIELDS`` of each factor).  A field
    the snapshot does not carry stays absent, so ``.get`` answers as it did on the whole snapshot."""
    out = {k: s[k] for k in ROW_FIELDS if k in s}
    if "fund_period" in s:
        fp = s["fund_period"]
        out["fund_period"] = {"live": fp.get("live")} if isinstance(fp, dict) else fp
    if "factors" in s:
        out["factors"] = [{k: f[k] for k in FACTOR_FIELDS if k in f} if isinstance(f, dict) else f for f in s["factors"] or []]
    return out


def session_rows(led: Ledger, market: str, strategy: str, first: str = FIRST) -> Dict[str, List[Dict[str, Any]]]:
    """Session -> the rows that count: a score, not INSUFFICIENT_DATA, and a price of that very session.  A day under MIN_ROWS is left out.
    Each row is the snapshot cut to what the readings read (``light``)."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for r in led._live_rows():
        if r["market"] != market or r["session"] < first:
            continue
        for s in led._load(r):
            if s.get("strategy") == strategy and s.get("score") is not None and s.get("actionability") != "INSUFFICIENT_DATA" and s.get("data_date") == r["session"]:
                out.setdefault(r["session"], []).append(light(s))
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


def _fifths_median(sc: np.ndarray, r: np.ndarray, cost: float) -> Optional[float]:
    """Median return of the top fifth less the bottom fifth's, net of one round trip.  A rank correlation can be positive while
    the means are equal (a few large winners among the low scores); the median beside the mean lets a reader see which it is."""
    q = validate.rank(sc) / (len(sc) - 1)
    top, bot = r[q >= 0.8], r[q <= 0.2]
    return float(np.median(top) - np.median(bot) - cost) if len(top) and len(bot) else None


def without_factor(fid: str) -> Callable[[List[Dict[str, Any]]], np.ndarray]:
    """A reference score: the recorded factor values weighted as the live score weights them, with one factor left out."""
    def one(snap: Dict[str, Any]) -> float:
        w = c = 0.0
        for f in snap.get("factors") or []:
            if f.get("factor") == fid or f.get("scored") is False or f.get("normalized") is None or f.get("status") not in engine._QUALITY:
                continue
            w, c = w + float(f["weight"]), c + float(f["weight"]) * float(f["normalized"])
        return 100 * c / w if w else float("nan")
    return lambda snaps: np.array([one(x) for x in snaps])


def within_sector(sector_of: Callable[[str, Optional[str]], Optional[str]]) -> Callable[[List[Dict[str, Any]]], np.ndarray]:
    """A reference score: the recorded score less the mean of its sector that day.  The ledger keeps no sector: ``sector_of``
    is asked with the ticker and the snapshot's date, so a dated copy (``sector_archive``, kept monthly from 2026-11) can answer
    for that month; where there is none the caller falls back to the sectors of the day of the reading.  The report says so."""
    def many(snaps: List[Dict[str, Any]]) -> np.ndarray:
        sc = np.array([float(x["score"]) for x in snaps])
        sec = [sector_of(x["ticker"], x.get("data_date")) for x in snaps]
        out = np.full(len(sc), np.nan)
        for g in {x for x in sec if x}:
            m = np.array([x == g for x in sec])
            if m.sum() >= 3:
                out[m] = sc[m] - sc[m].mean()
        return out
    return many


def day_stats(session: str, snaps: List[Dict[str, Any]], px: Prices, h: int, cost: float,
              variant: Optional[Callable[[List[Dict[str, Any]]], np.ndarray]] = None) -> Optional[Dict[str, Any]]:
    """One session's cross-section, or None while its holds have not ended.  Returns are net of one round trip."""
    score, net, bench, own, price, kept = [], [], [], [], [], []
    for s in snaps:
        o = px.outcome(s, session, h, cost)
        if not o:
            continue
        score.append(float(s["score"]))
        net.append(o["net"])
        kept.append(s)
        own.append(float("nan"))
        price.append(float("nan"))
        if o.get("relative_net") is not None and not o.get("stopped"):
            bench.append(o["net"] - o["relative_net"])                   # the index's return over the same days
            own[-1] = bench[-1]                                          # this stock's own index
            if o.get("relative_price_net") is not None:
                price[-1] = o["relative_price_net"]                      # the same comparison on prices alone
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
    pr = np.array(price)

    def price_of(mask: np.ndarray) -> Optional[float]:
        return float(np.nanmean(pr[mask])) if np.isfinite(pr[mask]).any() else None
    d.update(date=session, universe_net=float(r.mean()), index=idx, universe_effect=float(r.mean()) - index_of(every),
             buy_index=index_of(sc >= BUY) if len(buy) else None, top_index=index_of(q >= 0.8) if len(top) else None,
             buy_net=float(buy.mean()) if len(buy) else None, top_net=float(top.mean()) if len(top) else None,
             buy_price=price_of(sc >= BUY) if len(buy) else None, top_price=price_of(q >= 0.8) if len(top) else None,
             spread_median=_fifths_median(sc, r, cost),
             versions=sorted({str(s.get("model_version")) for s in snaps}))
    if variant is not None:                          # a reference score rebuilt from the same records: figures only, never a verdict
        v = variant(kept)
        ok = np.isfinite(v)
        got = validate.per_date(v[ok], r[ok], cost) if ok.sum() >= MIN_ROWS else None
        d["variant"] = {"ic": got["ic"], "spread_net": got.get("spread_net"), "spread_median": _fifths_median(v[ok], r[ok], cost), "n": int(ok.sum())} if got and got.get("ic") is not None else None
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
                "universe_effect": _mean(sel, lambda r: r["universe_effect"]),
                "buy_minus_index_price": _mean(sel, lambda r: r.get("buy_price")), "top_minus_index_price": _mean(sel, lambda r: r.get("top_price")),
                "spread_median": _mean(sel, lambda r: r.get("spread_median"))}
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


SPLIT_SAYS = {"PASSED": "수익 조건(조건 B)을 채웠습니다.",
              "SCORE_SIDE_POSITIVE": "수익 조건(조건 B)은 못 채웠지만, 점수 효과(점수 상위 묶음 − 스캔 전체)는 전·후반 모두 양수였습니다. 지수에 뒤진 몫은 대상(같은 비중으로 든 스캔 전체 − 지수)과 "
                                     "비용 쪽에 있습니다. 점수 효과가 우연과 구분되는지는 이 수치로 알 수 없습니다.",
              "SCORE_SIDE_NOT_POSITIVE": "수익 조건(조건 B)을 못 채웠고, 점수 효과(점수 상위 묶음 − 스캔 전체)도 전·후반 모두 양수는 아니었습니다."}


def money_split(s: Dict[str, Any], cost: float, top_band: bool, money: bool) -> Dict[str, Any]:
    """Condition B's one figure in its three parts (fixed 2026-11-25, before the first outcome matured): the scanned stocks at
    equal weight against the index before cost, the cost of the round trip every stock pays, and the band against the scanned
    stocks.  band − index = universe_before_cost − cost + score_effect.  The sentence is one of three written beforehand; the
    verdict and its conditions are not touched.  ``price_only``: the same comparison without dividends on either side."""
    key, eff, pkey = ("top_minus_index", "top_score_effect", "top_minus_index_price") if top_band else ("buy_minus_index", "score_effect", "buy_minus_index_price")
    gt = lambda v: v is not None and v > 0          # noqa: E731

    def part(p: Dict[str, Any]) -> Dict[str, Any]:
        u = p.get("universe_effect")
        return {"band_minus_index": p.get(key), "universe_before_cost": None if u is None else u + cost, "cost": cost, "score_effect": p.get(eff), "band_minus_index_price_only": p.get(pkey)}
    code = "PASSED" if money else "SCORE_SIDE_POSITIVE" if gt(s["early"].get(eff)) and gt(s["late"].get(eff)) else "SCORE_SIDE_NOT_POSITIVE"
    return {"all": part(s["all"]), "early": part(s["early"]), "late": part(s["late"]), "reading": code, "says": SPLIT_SAYS[code],
            "condition_b_price_only": gt(s["early"].get(pkey)) and gt(s["late"].get(pkey)),
            "price_only_note": "배당을 뺀 가격만으로 양쪽을 잰 값입니다. 한국 종목의 수정 종가에는 배당이 들어 있고 코스피·코스닥 지수에는 없어, 수정 종가 기준 비교는 배당만큼 종목 쪽에 유리합니다. "
                               "판정은 수정 종가 기준 그대로이고 이 값은 옆에 적는 참고입니다."}


REFERENCE_NOTE = ("참고 줄입니다(2026-11-25에 미리 정함). 같은 기록의 요인 값으로 다시 만든 점수의 수치만 적고, 통과도 탈락도 없으며 t 기준을 붙이지 않습니다. "
                  "이 줄을 근거로 공식을 바꾸지 않습니다: 바꾸려면 새로 등록한 기록이 필요합니다.")


def reference_line(days: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    got = [d["variant"] for d in days if d.get("variant")]
    if not got:
        return {"variant": name, "status": "UNAVAILABLE", "note": REFERENCE_NOTE}
    mean = lambda k: float(np.mean([g[k] for g in got if g.get(k) is not None])) if any(g.get(k) is not None for g in got) else None      # noqa: E731
    return {"variant": name, "status": "REAL", "dates": len(got), "mean_n": float(np.mean([g["n"] for g in got])), "ic": mean("ic"), "spread_net": mean("spread_net"),
            "spread_median": mean("spread_median"), "note": REFERENCE_NOTE}


CANDIDATE_1_NOTE = ("판정 뒤 규칙 3절 후보 1번(스윙 점수에서 손익비 요인을 뺀다)의 조건 가운데 '참고 줄이 실제 점수보다 나쁘지 않다'를 읽은 값입니다(2026-11-25에 정의). "
                    "같은 거래일에서 참고 줄의 평균 순위 상관과 중앙값 스프레드가 둘 다 실제 점수의 값 이상이면 '나쁘지 않다'입니다. 두 점수의 순위가 거의 같아 이 조건은 우연으로도 채워질 수 있습니다. "
                    "그래서 두 시장 모두에서 채워져도 얻는 것은 채택이 아니라 새 기록으로 한 번 더 등록할 자격입니다.")


def candidate_1(primary: Dict[str, Any], ref: Dict[str, Any]) -> Dict[str, Any]:
    """"Not worse", defined before any outcome matured: the reference line's mean rank correlation and its median spread are both
    at or above the live score's on the same days.  One market's reading; the rule asks for both markets and for EN-1."""
    live_ic, live_med = primary.get("ic"), (primary.get("all") or {}).get("spread_median")
    figures = (ref.get("ic"), ref.get("spread_median"), live_ic, live_med)
    known = ref.get("status") == "REAL" and all(v is not None for v in figures)
    return {"reference_ic": ref.get("ic"), "live_ic": live_ic, "reference_spread_median": ref.get("spread_median"), "live_spread_median": live_med,
            "not_worse": bool(ref["ic"] >= live_ic and ref["spread_median"] >= live_med) if known else None, "note": CANDIDATE_1_NOTE}


def variant_of(strategy: str, sector_of: Optional[Callable[[str], Optional[str]]]):
    """(name, function) of the one reference score a strategy's verdict carries, or (name, None) when it cannot be built."""
    if strategy == "SWING":
        return "손익비 요인을 뺀 점수", without_factor("risk_reward")
    return "업종 평균을 뺀 점수(달마다 보관한 업종 분류, 없는 달은 판정 날의 분류)", within_sector(sector_of) if sector_of else None


# A reading's t bar is set for a pay-off that does not persist from month to month.  When it does, the chance of a false pass is
# larger: two agents of the score audit of 2026-11-25 simulated it separately (AGENT_06 section 5, AGENT_08 second pass).  These are
# their points for the 240-session swing verdict: (correlation of neighbouring 20-session blocks, false passes in percent).
PERSIST_POINTS = ((0.0, 1.25), (0.09, 2.5), (0.18, 3.9), (0.26, 5.4), (0.31, 5.9), (0.35, 7.7), (0.41, 10.0), (0.47, 14.6))
# The same lag-1 value means a different chance by the SHAPE of the persistence (assessment 2026-11-26, simulated on random numbers,
# 48,000 series a point, the lag-1 measured as ``persistence`` measures it on 12 blocks).  The points above fit a short memory (each
# day's pay-off leaning on the day before; the last four were added that day).  These are for a slow drift (a part of the pay-off
# that keeps its sign for about three months), which the t's 20-session lag cannot see: far more false passes at the same lag-1.
PERSIST_SLOW = ((-0.08, 1.25), (-0.03, 3.7), (0.09, 8.2), (0.19, 11.2), (0.32, 14.1), (0.43, 15.9))
PERSIST_MIN_BLOCKS = 8


def persistence(days: List[Dict[str, Any]], h: int) -> Dict[str, Any]:
    """How far the rank correlation of one block of ``h`` sessions carries into the next (user decision 2026-11-25, roadmap P3-3).
    A reference figure beside the verdict: it reads the same day figures the verdict reads and changes nothing.  With a dozen
    blocks the figure itself is rough (about one over the square root of the count), and the note says so."""
    ic = np.array([d["ic"] for d in days][::h], dtype=float)
    n = len(ic)
    note = ("판정의 t 기준은 점수의 성과가 달마다 독립일 때 우연 통과가 1.25%가 되도록 맞춘 값입니다. 성과가 이웃한 달로 이어지면 우연 통과가 그보다 커집니다. "
            "이 수치는 참고이고 판정의 조건과 낱말을 바꾸지 않습니다.")
    if n < PERSIST_MIN_BLOCKS or float(ic.std()) < 1e-12:
        return {"status": "UNAVAILABLE", "blocks": n, "note": note}
    e = ic - ic.mean()
    r = float((e[:-1] * e[1:]).sum() / (e * e).sum())
    xs, ys = [p[0] for p in PERSIST_POINTS], [p[1] for p in PERSIST_POINTS]
    slow = float(np.interp(r, [p[0] for p in PERSIST_SLOW], [p[1] for p in PERSIST_SLOW]))
    return {"status": "REAL", "blocks": n, "block_sessions": h, "lag1": r, "rough_by": float(1 / math.sqrt(n)),
            "false_pass_pct_about": float(np.interp(max(r, 0.0), xs, ys)), "beyond_table": bool(r > xs[-1]), "false_pass_pct_if_slow": slow,
            "says": (f"{h}거래일 묶음 {n}개의 이웃한 묶음 사이 순위 상관의 이어짐은 {r:+.2f}입니다(묶음이 {n}개뿐이라 ±{1 / math.sqrt(n):.2f}쯤 흔들리는 값). "
                     + ("이어짐이 없거나 반대여서 우연 통과는 기준대로 1.25%쯤으로 봅니다." if r <= 0 else
                        f"이 값이 참이라면 우연 통과는 1.25%가 아니라 약 {float(np.interp(r, xs, ys)):.1f}%{' 이상' if r > xs[-1] else ''}입니다(240거래일 스윙 판정 기준의 모의실험 값).")
                     + f" 다만 같은 값이라도 이어짐의 모양에 따라 다릅니다: 성과의 일부가 석 달쯤 같은 쪽으로 머무는 느린 쏠림이라면 약 {slow:.1f}%입니다. 묶음 {n}개로는 어느 쪽인지 가릴 수 없습니다."),
            "note": note}


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


def late_days(rows: Dict[str, List[Dict[str, Any]]], used: Sequence[str], calendar: Sequence[str]) -> Dict[str, Any]:
    """How many sessions of the sample were recorded after the next open.  Such a record enters one session later (its
    ``entry_session`` is past the session that follows it), so no passed open is used; the report says how many there were
    because the verdict reads them together with the days recorded on time (assessment 2026-11-26).  Changes no condition."""
    nxt = {d: calendar[i + 1] for i, d in enumerate(calendar[:-1])}
    late = [d for d in used if nxt.get(d) and any((x.get("entry_session") or "") > nxt[d] for x in rows[d])]
    return {"late": len(late), "of": len(used), "sessions": late[:40],
            "note": "다음 개장 뒤에 적힌 날입니다. 이런 날의 진입은 한 거래일 뒤로 계산했습니다. 판정 조건에는 쓰지 않는 참고 수치입니다."}


def formula_mix(rows: Dict[str, List[Dict[str, Any]]], used: Sequence[str]) -> Optional[Dict[str, Any]]:
    """None when every record of the sample was scored by one formula on one statement basis; otherwise what is mixed.
    The statement basis (annual or trailing four quarters) can be switched by ``.env`` or a button under the same model version
    (terminal/qsf/fund_period.py), so the version alone does not say the sample is one formula (assessment 2026-11-26).
    A record from before 2026-11-23 has no basis written and was scored on annual statements."""
    versions = sorted({str(x.get("model_version")) for d in used for x in rows[d]})
    bases = sorted({str((x.get("fund_period") or {}).get("live") or "ANNUAL") for d in used for x in rows[d]})
    if len(versions) <= 1 and len(bases) <= 1:
        return None
    what = ([f"점수 공식이 둘 이상입니다({', '.join(versions)})"] if len(versions) > 1 else []) + ([f"재무 기준이 둘 이상입니다({', '.join(bases)})"] if len(bases) > 1 else [])
    return {"versions": versions, "fund_bases": bases,
            "reasons": [f"이 {len(used)}거래일의 기록에는 " + ", ".join(what) + ". 한 공식의 기록이 아니어서 읽지 않았고, 수익도 읽지 않았습니다."]}


def evaluate_once(base: Path, market: str, strategy: str, loader: Callable[[str], List[Dict]], bench: List[Dict], log=print,
                  benches: Optional[Dict[str, List[Dict]]] = None, sector_of: Optional[Callable[[str], Optional[str]]] = None) -> Dict[str, Any]:
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
    mixed = formula_mix(rows, used)
    if mixed:                                        # decided before any return is read (user decision 2026-11-26, as the continuation readings do)
        res = {"status": "REAL", "protocol": PROTOCOL, "market": market, "strategy": strategy, "horizon": h, "sessions_used": len(used), "first": used[0], "last": used[-1],
               "verdict": "MIXED_FORMULA", **mixed, "note": NOTE}
        out.parent.mkdir(parents=True, exist_ok=True)
        durable.write_text(out, json.dumps(res, ensure_ascii=False, indent=1))
        wording.seal(base, out)
        log(f"{market} {strategy}: {res['verdict']}")
        return res
    cost = config.round_trip_cost(market)
    vname, variant = variant_of(strategy, sector_of)
    days = [d for d in (day_stats(s, rows[s], px, h, cost, variant) for s in used) if d]
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
           "money_split": money_split(primary, cost, top, reading(primary, top)["condition_b"]), "reference": [reference_line(days, vname)],
           "persistence": persistence(days, h), "late_days": late_days(rows, used, px.calendar),
           **({"candidate_1": candidate_1(primary, reference_line(days, vname))} if strategy == "SWING" else {}),
           "benchmarks": sorted(px.benches) or None,
           "by_version": {k: {"dates": len(v), "ic": float(np.mean(v))} for k, v in sorted(versions.items())}, "note": NOTE}
    out.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(out, json.dumps(res, ensure_ascii=False, indent=1))
    wording.seal(base, out)                          # the word "매수 후보" comes back only from a file this run wrote (wording.earned)
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
               "순위 조건 다섯 가지 가운데 못 채운 것: " + (", ".join(failed) if failed else "없음") + f". 수익 조건({'그날 상위 20%가' if top else '70점 이상 구간이'} 지수를 전·후반 모두 이김): {'채움' if r['condition_b'] else '못 채움'}.",
               "이 읽기는 짧은 기록을 봅니다. 작은 효과는 잡지 못하고, '구분되지 않음'은 효과가 없다는 뜻이 아닙니다.",
               "무엇이 나와도 점수, 규칙, 주된 판정(240거래일·20거래일 수익)은 바뀌지 않습니다."]
    res = {"status": "REAL", "protocol": PROTOCOL, "kind": "EARLY", "market": market, "strategy": "SWING", "horizon": h, "sessions_used": len(used), "first": used[0], "last": used[-1],
           "cost_round_trip_pct": cost * 100, "verdict": verdict, "condition_a": r["condition_a"], "condition_b": r["condition_b"], "band": r["band"], "t_bar": s["t_bar"],
           "t_nominal": EARLY_T, "summary": s, "reasons": reasons, "applies_itself": False, "note": NOTE}
    out.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(out, json.dumps(res, ensure_ascii=False, indent=1))
    log(f"{market} SWING early {n}: {verdict}")
    return res


# ---------------------------------------------------------------------- continuation readings (pre-registered 2026-11-25)
# User decision 2026-11-25 (reports/QSF_AFTER_VERDICT_RULES_2026_11_25.md): a swing verdict that does not pass is not a reason to
# change the formula.  At a true rank correlation of 0.05 the 240-session verdict finds it about one time in eight (Korea) or
# fourteen (the US); the only way to more power is the same formula read over a longer record.  So the same record is read again
# at 480, 720 and 960 matured sessions: the same horizon, the same conditions, the first n sessions from FIRST.  Three more looks,
# so each uses a stricter nominal bar: together they pass by chance about as often as ONE verdict (1.25%), which makes the swing
# family 2.5% a market.  A reading is skipped once an earlier one passed, and is not made on a record of more than one formula.
CONTINUE = (480, 720, 960)
CONTINUE_T = 2.64                       # a one-sided chance of 0.41% a look: three looks, 1.25% together (calibrated for the overlap below)
PASSED = "WEAK_POSITIVE_EVIDENCE"


def continue_path(base: Path, market: str, n: int) -> Path:
    return Path(base) / REPORT_DIR / f"QSF_LIVE_FORWARD_CONT_{market}_SWING_{n}.json"


def _read(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def continue_once(base: Path, market: str, n: int, loader: Callable[[str], List[Dict]], bench: List[Dict], log=print,
                  benches: Optional[Dict[str, List[Dict]]] = None) -> Dict[str, Any]:
    """One continuation reading of the swing score: the first ``n`` matured sessions, read once, after every earlier reading."""
    if n not in CONTINUE:
        raise ValueError(n)
    base, h, strategy = Path(base), PRIMARY["SWING"], "SWING"
    top = (market, strategy) in TOP_BAND
    out = continue_path(base, market, n)
    if out.exists():
        raise RuntimeError("이어 읽기는 한 번만 합니다. 이미 결과가 있습니다.")
    before = [report_path(base, market, strategy)] + [continue_path(base, market, m) for m in CONTINUE if m < n]
    if not all(p.exists() for p in before):
        raise RuntimeError("앞선 판정이나 이어 읽기가 아직 없습니다. 순서대로 읽습니다.")
    head = {"status": "REAL", "protocol": "reports/QSF_AFTER_VERDICT_RULES_2026_11_25.md", "kind": "CONTINUATION", "market": market, "strategy": strategy, "horizon": h,
            "sessions_wanted": n, "applies_itself": False, "note": NOTE}

    def write(res: Dict[str, Any]) -> Dict[str, Any]:
        out.parent.mkdir(parents=True, exist_ok=True)
        durable.write_text(out, json.dumps(res, ensure_ascii=False, indent=1))
        wording.seal(base, out)
        log(f"{market} SWING continuation {n}: {res['verdict']}")
        return res
    if any(_read(p).get("verdict") == PASSED for p in before):
        return write({**head, "verdict": "ALREADY_PASSED", "reasons": ["앞선 판정이 이미 순위와 수익 조건을 모두 채웠습니다. 이 읽기는 수익을 읽지 않았습니다."]})
    led = Ledger(base)
    if led.verify()["status"] != "OK":
        raise RuntimeError("원장 검증에 실패해 읽지 않습니다.")
    rows = session_rows(led, market, strategy)
    px = Prices(loader, bench, benches)
    ready = matured_sessions(list(rows), px.calendar, h)
    if len(ready) < n:
        raise RuntimeError(f"아직 읽을 수 없습니다. 만기 거래일 {len(ready)}개, 기준 {n}개입니다.")
    used = ready[:n]                                 # exactly the fixed sample, whenever this is run
    mixed = formula_mix(rows, used)
    if mixed:                                        # decided before any return is read
        return write({**head, "verdict": "MIXED_FORMULA", **mixed, "first": used[0], "last": used[-1]})
    cost = config.round_trip_cost(market)
    days = [d for d in (day_stats(s, rows[s], px, h, cost) for s in used) if d]
    if len(days) < n // 2:
        raise RuntimeError(f"수익을 계산할 수 있는 날이 {len(days)}일뿐입니다. 시세를 확인하세요.")
    s = summarize(days, h)
    s["t_bar"], s["t_nominal"] = calibrate.bar(CONTINUE_T, len(days), h, 1, h), CONTINUE_T
    r = reading(s, top)
    failed = [k for k, ok in r["condition_a"].items() if not ok]
    t_txt = "계산할 수 없음" if s["t"] is None else f"{s['t']:+.2f}"
    split = money_split(s, cost, top, r["condition_b"])
    reasons = [f"처음 {len(used)}거래일({used[0]} ~ {used[-1]})의 스윙 점수와 그 뒤 {h}거래일 수익의 순위 상관: 평균 {s['ic']:+.3f}, t {t_txt} (기준 {s['t_bar']:g}. 여러 번 읽는 만큼 첫 판정보다 엄격한 값입니다).",
               "순위 조건 다섯 가지 가운데 못 채운 것: " + (", ".join(failed) if failed else "없음") + ".", split["says"],
               "이 읽기는 첫 판정과 같은 공식, 같은 기록을 더 길게 본 것입니다. 통과하지 못해도 공식을 바꿀 이유가 아닙니다."]
    return write({**head, "sessions_used": len(used), "first": used[0], "last": used[-1], "cost_round_trip_pct": cost * 100, **r, "t_nominal": CONTINUE_T, "primary": s,
                  "money_split": split, "persistence": persistence(days, h), "late_days": late_days(rows, used, px.calendar), "versions": sorted({str(x.get("model_version")) for d in used for x in rows[d]}), "reasons": reasons})
