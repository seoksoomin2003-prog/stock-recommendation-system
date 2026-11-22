"""The one reading of the six portfolios' paper record (reports/IC1_PAPER_READING_PROTOCOL.md, user decision 2026-11-22).

At 240 paper days a market's record is read once: each portfolio's daily return after costs, less the index's, and whether
its mean is distinguishable from nothing.  The protocol was written before the first record line.  The reading reports; it
changes no rule, no score and no portfolio.  The daily job asks for it by itself (terminal/qsf/readings.py).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from terminal.committee import portfolios, record
from terminal.qsf import validate
from utils import durable

PROTOCOL = "reports/IC1_PAPER_READING_PROTOCOL.md"
READ_AT, LAG, BAR, MAX_NO_INDEX = 240, 5, 3.0, 24
REPORTS = {"KR": Path("reports") / "qsf" / "IC1_PAPER_KR.json", "US": Path("reports") / "qsf" / "IC1_PAPER_US.json"}
BETTER, WORSE, UNKNOWN, ANY_BETTER = "BETTER", "WORSE", "NOT_DISTINGUISHED", "PAPER_BETTER"
WORD = {BETTER: "지수보다 나음", WORSE: "지수보다 못함", UNKNOWN: "구분되지 않음"}


def judge(t: Optional[float]) -> str:
    return UNKNOWN if t is None else BETTER if t >= BAR else WORSE if t <= -BAR else UNKNOWN


def evaluate_once(base: Path, market: str, price: Callable[[str, str], Optional[float]], benchmark: Callable[[str], Optional[float]], one_way_cost: float) -> Dict[str, Any]:
    """The protocol's one reading.  Refused before 240 paper days, after a report exists, and without enough index prices."""
    base = Path(base)
    target = base / REPORTS[market]
    if target.exists():
        raise RuntimeError("이미 읽었습니다. 규칙상 다시 읽지 않습니다.")
    rows = record.read(base, market)
    if len(rows) < READ_AT + 2:
        raise RuntimeError(f"기록이 {len(rows)}거래일입니다. {READ_AT + 2}거래일(모의 하루 수익 {READ_AT}개)이 되기 전에는 읽지 않습니다.")
    rows = rows[:READ_AT + 2]
    perf = record.performance(rows, price, benchmark, one_way_cost, keep_daily=True)
    index = perf["benchmark_daily"]
    if sum(1 for b in index if b is None) > MAX_NO_INDEX:
        raise RuntimeError("비교 지수의 가격이 없는 날이 너무 많아 읽지 않습니다.")
    out: Dict[str, Any] = {}
    reasons: List[str] = []
    for key in portfolios.ORDER:
        s = dict(perf["portfolios"].get(key) or {})
        daily = s.pop("daily", [])
        excess = [r - b for r, b in zip(daily, index) if b is not None]
        t = validate.newey_west_t(excess, LAG) if len(excess) >= 3 else None
        code = judge(t)
        invested = [1.0 - float(((r.get("portfolios") or {}).get(key) or {}).get("cash", 1.0)) for r in rows[:READ_AT]]
        out[key] = {**s, "verdict": code, "t": None if t is None else round(t, 3), "mean_excess_daily": round(sum(excess) / len(excess), 6) if excess else None, "excess_days": len(excess),
                    "average_invested": round(sum(invested) / len(invested), 4)}
        reasons.append(f"{portfolios.SPEC[key]['name']}: {WORD[code]}(t {'계산 안 됨' if t is None else f'{t:+.2f}'}, 기준 ±{BAR:g}). 누적 {s.get('total_return', 0) * 100:+.1f}%, "
                       f"지수 {(s.get('benchmark_return') or 0) * 100:+.1f}%, 평균 투자 비중 {out[key]['average_invested'] * 100:.0f}%.")
    verdict = ANY_BETTER if any(v["verdict"] == BETTER for v in out.values()) else UNKNOWN
    res = {"status": "REAL", "protocol": PROTOCOL, "rules": rows[0].get("rules"), "market": market, "first": rows[0]["session"], "last": rows[-1]["session"], "records": len(rows), "days": READ_AT,
           "bar": BAR, "lag": LAG, "verdict": verdict, "portfolios": out, "reasons": reasons + ["큰 차이만 잡히는 읽기입니다. '구분되지 않음'은 '효과 없음'이 아니라 '아직 모름'입니다."],
           "kind": "PAPER", "note": "모의 기록의 읽기입니다. 과거로 거슬러 계산한 값도 실제 계좌의 수익도 아닙니다. 이 결과로 아무것도 자동으로 바뀌지 않습니다."}
    target.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(target, json.dumps(res, ensure_ascii=False, indent=1))
    return res
