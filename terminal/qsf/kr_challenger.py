"""The Korean bundle challenger score, written down every session and kept apart from the live score.  Rules: reports/QSF_KR_CHALLENGER_PROTOCOL.md.

The Korean counterpart of ``us_challenger``: signals that move together count as one bundle and every bundle weighs the same.  The inputs
are the normalized values the QSF ledger already holds for the signals the live Korean score counts, so both scores read the same data.
The ledger is only read.  A record is written once and chained by hash.  No return is computed while the record grows, and the single
evaluation of each strategy is refused until enough sessions have matured.  No result changes the live score.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from terminal.qsf import config, kr_forward as kf, kr_swing_challenger as sc, research_ensemble as en, research_kr as kr, research_swing as rs, us_challenger as uc
from terminal.qsf.ledger import Ledger
from terminal.qsf.research_score import test_verdict
from utils import durable

PROTOCOL = "reports/QSF_KR_CHALLENGER_PROTOCOL.md"
FOLDER = Path("research_data") / "kr_challenger"
FIRST = "2026-11-18"       # the first Korean ledger session after the five the bundles were measured on; its ledger did not exist when the rules were committed
MIN_ROWS = 200             # fewer than this in one strategy is a partial day, not a day
STEP = 5
MIN_T = 2.0
HORIZONS = {"SWING": 20, "LONG_TERM": 63}
REPORTS = {"SWING": Path("reports") / "qsf" / "QSF_KR_CHALLENGER_SWING.json", "LONG_TERM": Path("reports") / "qsf" / "QSF_KR_CHALLENGER_LONG.json"}
BUNDLES: Dict[str, List[List[str]]] = {     # settled before the first record, from the mean rank correlation of five ledger sessions; no return was read
    "SWING": [["earnings_revenue_quality"], ["profitability"], ["balance_sheet"], ["cash_flow_quality"], ["risk_reward"], ["atr_risk", "drawdown_gap"], ["liquidity"],
              ["earnings_calendar"], ["material_disclosures"]],
    "LONG_TERM": [["long_trend", "relative_strength", "momentum_persistence", "valuation", "downside_drawdown"], ["business_quality", "growth_quality", "free_cash_flow"],
                  ["balance_dilution", "financial_resilience", "leverage"], ["liquidity"], ["material_events"]],
}
INDEX = "IDX_KOSPI"        # research_kr_live.BOARD_INDEX["KOSPI"]: every KOSPI common stock, capitalisation-weighted, built from the KRX day files
INDEX_KO = "KRX 일별 자료로 만든 코스피 보통주 시가총액 가중 지수"
CHECK_KO = {"ic": "평균 IC 0.02 이상", "t": "t 2.24 이상", "ic_both_halves": "IC가 전반·후반 모두 양수", "spread_both_halves": "비용 차감 스프레드가 전반·후반 모두 양수",
            "buy_band": "상위 20%의 초과 수익이 양수"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def score_strategy(snaps: List[Dict[str, Any]], strategy: str) -> List[Dict[str, Any]]:
    """``snaps``: one session and one strategy, with a live score.  Reads each signal's normalized value, nothing else."""
    bundles = BUNDLES[strategy]
    table = [{f["factor"]: f.get("normalized") for f in s.get("factors") or []} for s in snaps]

    def column(name: str) -> np.ndarray:
        return np.array([np.nan if t.get(name) is None else float(t[name]) for t in table], dtype=float)
    ranks = {name: uc._percentile(column(name)) for b in bundles for name in b}
    final = en.combine(ranks, bundles)
    per_bundle = [en._mean([ranks[n] for n in b], 0.5) * 100 for b in bundles]

    def val(x: Any) -> Optional[float]:
        v = float(x)
        return round(v, 3) if np.isfinite(v) else None
    return [{"strategy": strategy, "ticker": s["ticker"], "score": val(final[i]), "bundles": [val(p[i]) for p in per_bundle], "live": val(s["score"]),
             "actionability": s.get("actionability"), "entry_session": s.get("entry_session")} for i, s in enumerate(snaps)]


def score_session(snaps: List[Dict[str, Any]], session: str) -> Dict[str, Any]:
    """A stock whose ledger date is not this session is left out.  A partial day raises, and is asked again at the next run."""
    fresh = [s for s in snaps if s.get("data_date") == session and s.get("score") is not None]
    rows: List[Dict[str, Any]] = []
    for strategy in BUNDLES:
        part = sorted((s for s in fresh if s.get("strategy") == strategy), key=lambda s: s["ticker"])
        if len(part) < MIN_ROWS:
            raise ValueError("TOO_FEW_STOCKS")
        rows += score_strategy(part, strategy)
    return {"session": session, "protocol": PROTOCOL, "bundles": BUNDLES, "model_versions": sorted({str(s.get("model_version")) for s in fresh}), "rows": rows}


def _session_snaps(led: Ledger, session: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in led._live_rows():
        if r["market"] == "KR" and r["session"] == session:
            out += led._load(r)
    return out


def record(base: Path, now: Callable[[], datetime] = _utcnow, first: str = FIRST) -> Dict[str, Any]:
    """OK: every Korean ledger session from ``first`` is written.  WAITING: a session in the ledger is still partial."""
    at = now()
    led = Ledger(Path(base))
    if led.verify()["status"] != "OK":
        return {"status": "FAILED", "reason": "LEDGER_BROKEN"}
    sessions = sorted({r["session"] for r in led._live_rows() if r["market"] == "KR" and r["session"] >= first})
    done = {r["session"] for r in kf.read_index(base, FOLDER)}
    wrote: List[str] = []
    partial: List[str] = []
    for day in sessions:
        if day in done:
            continue
        try:
            late = day != sessions[-1]
            if kf.write_record(base, day, at, late, store=FOLDER, scorer=lambda b, d: score_session(_session_snaps(led, d), d)):
                wrote.append(day)
        except ValueError as exc:
            if str(exc) != "TOO_FEW_STOCKS":
                raise
            partial.append(day)
    return {"status": "WAITING" if partial else "OK", "written": wrote, "partial": partial, "last": max(done | set(wrote), default=None), "sessions_in_ledger": len(sessions)}


def status(base: Path) -> Dict[str, Any]:
    """Dates and counts only."""
    rows = kf.read_index(base, FOLDER)
    return {"records": len(rows), "first": rows[0]["session"] if rows else None, "last": rows[-1]["session"] if rows else None, "late": sum(1 for r in rows if r.get("late")),
            "first_due": FIRST, "needed": {s: config.MIN_INDEPENDENT * h for s, h in HORIZONS.items()}, "horizons": HORIZONS,
            "evaluated": {s: (Path(base) / p).exists() for s, p in REPORTS.items()}}


# ---------------------------------------------------------------------- the one evaluation of each strategy
class _View:
    """What the shared evaluation code reads: forward returns by stock column, and the KOSPI index under ``SPY``."""

    def __init__(self, px: Any):
        self.px, self.dates, self.symbols = px, px.dates, px.symbols
        self.col = dict(px.col)
        self.bench = px.col[INDEX]
        self.col["SPY"] = self.bench
        self.data = {"adj_close": px.data["close"]}

    def index_return(self, i: int, h: int) -> float:
        m = self.px.data["close"][:, self.bench]
        return float(m[i + h] / m[i] - 1) if 0 <= i and i + h < len(self.dates) else float("nan")

    def forward(self, i: int, h: int, cost: float = 0.0) -> np.ndarray:
        out = self.px.forward(i, h, cost)
        out[self.bench] = self.index_return(i, h)
        return out


def _entry_row(rows: List[Dict[str, Any]], place: Dict[str, int]) -> Optional[int]:
    """The panel row before the ledger's entry session: forward() enters at the open of the row after it."""
    entries = {r["entry_session"] for r in rows if r.get("entry_session")}
    if len(entries) != 1:
        return None
    i = place.get(next(iter(entries)), 0) - 1
    return i if i >= 0 else None


def _top_fifth(score: np.ndarray, view: _View, rows: List[int], h: int, cost: float) -> Dict[str, Any]:
    """The top fifth held for the horizon and replaced, beside the KOSPI index and the equal-weight average of the day's sample."""
    ns = list(range(score.shape[0]))[::max(1, h // STEP)]
    ret = np.stack([view.forward(rows[n], h) for n in ns])
    tops, sample = [], []
    for k, n in enumerate(ns):
        idx = np.flatnonzero(np.isfinite(score[n]))
        pick = np.zeros(score.shape[1], dtype=bool)
        pick[idx[np.argsort(-score[n][idx], kind="mergesort")[:max(1, len(idx) // 5)]]] = True
        tops.append(pick)
        got = ret[k][idx]
        sample.append(float(np.nanmean(got)) if np.isfinite(got).any() else float("nan"))
    path = kr.rebalance_path(tops, ret, cost)
    index = [float(v) for v in ret[:, view.bench]]
    a, b, c = kf._half(path), kf._half(index), kf._half(sample)
    parts = [{"top_fifth": kr.annual_growth(a[k], h), "kospi": kr.annual_growth(b[k], h), "sample_average": kr.annual_growth(c[k], h)} for k in (0, 1)]
    beats = all(p["top_fifth"] is not None and p["kospi"] is not None and p["top_fifth"] > p["kospi"] for p in parts)
    return {"periods": len(ns), "top_fifth": kr.annual_growth(path, h), "kospi": kr.annual_growth(index, h), "sample_average": kr.annual_growth(sample, h),
            "early": parts[0], "late": parts[1], "beats_kospi_in_both_halves": beats}


def verdict(own: bool, paired: Dict[str, Any]) -> str:
    """The protocol's four words.  ``own``: the challenger passed the five conditions.  ``paired``: challenger minus live, per date."""
    if own and paired.get("supports_challenger"):
        return "CHALLENGER_BETTER"
    m, t, early, late = paired.get("mean"), paired.get("t"), paired.get("early"), paired.get("late")
    if m is not None and t is not None and m < 0 and t <= -MIN_T and early is not None and early < 0 and late is not None and late < 0:
        return "LIVE_BETTER"
    return "CHALLENGER_HAS_EVIDENCE" if own else "NO_EVIDENCE"


def _n(v: Any, form: str = "+.3f") -> str:
    return "없음" if v is None else format(float(v), form)


def reasons(res: Dict[str, Any]) -> List[str]:
    """Why the verdict is what it is, with the values: what was measured, each score's five conditions, and the difference."""
    lines = [f"잰 것: {res['first']}~{res['last']} 기록 중 {res['dates']}일(5거래일 간격), {res['horizon']}거래일 보유, 한국 왕복 비용 {res['cost'] * 100:.2f}% 차감."]
    for key, name in (("challenger", "도전자"), ("live", "라이브")):
        s = res[key]
        failed = [CHECK_KO.get(k, k) for k, ok in (s.get("checks") or {}).items() if not ok]
        lines.append(f"{name}: 평균 IC {_n(s.get('ic'))}, t {_n(s.get('t'), '+.2f')}, 상위 20% 초과 수익 {_n(s.get('top_excess'), '+.4f')}. "
                     + ("5개 조건을 모두 채웠습니다." if not failed else "걸린 조건: " + ", ".join(failed) + "."))
    p = res["paired_ic"]
    lines.append(f"IC 차이(도전자 − 라이브): 평균 {_n(p.get('mean'))}, t {_n(p.get('t'), '+.2f')}(기준 +2.0 이상 또는 −2.0 이하), 전반 {_n(p.get('early'))}, 후반 {_n(p.get('late'))}.")
    return lines


def evaluate_once(base: Path, strategy: str, log=print, panel: Any = None) -> Dict[str, Any]:
    base = Path(base)
    target = base / REPORTS[strategy]
    if target.exists():
        raise RuntimeError("이미 평가했습니다. 규칙상 다시 평가할 수 없습니다.")
    if kf.verify(base, FOLDER)["status"] != "OK":
        raise RuntimeError("기록 검증에 실패해 평가하지 않습니다.")
    index = kf.read_index(base, FOLDER)
    if not index:
        raise RuntimeError("기록이 없습니다.")
    if panel is None:
        from terminal.qsf import research_kr_live
        panel = research_kr_live.ensure_panel(base, log)
    view = _View(panel)
    place = {d: n for n, d in enumerate(view.dates)}
    h = HORIZONS[strategy]
    need = config.MIN_INDEPENDENT * h
    folder = base / FOLDER
    matured: List[Dict[str, Any]] = []
    for r in index:                                  # in record order, and no further than the record that completes the count
        rows = [x for x in kf._read_day(folder, r["session"])["rows"] if x.get("strategy") == strategy]
        i = _entry_row(rows, place)
        if i is not None and i + h < len(view.dates):
            matured.append({"session": r["session"], "row": i, "rows": rows, "late": bool(r.get("late"))})
            if len(matured) == need:
                break
    if len(matured) < need:
        raise RuntimeError(f"아직 평가할 수 없습니다. 만기 거래일 {len(matured)}개, 기준 {need}개입니다.")
    chosen = matured[::STEP]
    rows_i = [m["row"] for m in chosen]
    score, live = np.full((len(chosen), len(view.symbols)), np.nan), np.full((len(chosen), len(view.symbols)), np.nan)
    for n, m in enumerate(chosen):
        for r in m["rows"]:
            j = panel.col.get(r["ticker"])
            if j is not None and r["score"] is not None and r["live"] is not None and r.get("actionability") != "INSUFFICIENT_DATA":
                score[n, j], live[n, j] = r["score"], r["live"]
    picks = list(range(len(chosen)))
    cost = config.round_trip_cost("KR")
    test, base_test = en.evaluate(score, view, rows_i, picks, h, {}, cost), en.evaluate(live, view, rows_i, picks, h, {}, cost)
    for t in (test, base_test):
        for regime in ("ic_spy_above_200d", "ic_spy_below_200d"):      # not in the rules
            t.pop(regime, None)
    own, base_own = test_verdict(test), test_verdict(base_test)
    paired = uc.paired_ic(score, live, view, rows_i, h)
    apart = picks[::max(1, h // STEP)]                                 # samples a whole horizon apart, the former way of reading

    def ics(m: np.ndarray, shift: int = 0, which: Optional[List[int]] = None) -> List[float]:
        return [v for v in (rs._ic(m[n], view.forward(rows_i[n] + shift, h)) for n in (picks if which is None else which)) if v is not None]
    a, b = ics(score, which=apart), ics(live, which=apart)
    later = ics(score, 1)
    out = {"status": "EVALUATED", "protocol": PROTOCOL, "strategy": strategy, "horizon": h, "dates": len(chosen), "first": chosen[0]["session"], "last": chosen[-1]["session"],
           "records_used": len(matured), "cost": cost, "index": INDEX_KO,
           "verdict": verdict(own["verdict"] == "WEAK_POSITIVE_EVIDENCE", paired),
           "challenger": {**test, **own, "top_fifth_path": _top_fifth(score, view, rows_i, h, cost)}, "live": {**base_test, **base_own, "top_fifth_path": _top_fifth(live, view, rows_i, h, cost)},
           "paired_ic": paired,
           "samples_a_horizon_apart": {"samples": len(apart), "challenger": {"mean": float(np.mean(a)) if a else None, "t": sc._t(a)}, "live": {"mean": float(np.mean(b)) if b else None, "t": sc._t(b)}},
           "one_day_later_entry_ic": float(np.mean(later)) if later else None, "late_share": sum(1 for m in matured if m["late"]) / len(matured),
           "note": "NO_EVIDENCE는 '효과 없음'이 아니라 '이 기록으로는 모름'입니다. 어느 결과도 라이브 점수를 바꾸지 않습니다."}
    out["reasons"] = reasons(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(target, json.dumps(out, ensure_ascii=False, indent=1, default=str))
    return out
