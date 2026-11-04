"""Rule-based challenger models (v1, price-only).  Parameters are fixed in advance and never tuned.

Every model is a pure function ``(panel, i) -> ranked picks`` that only reads rows 0..i of the panel
(no look-ahead).  Missing data excludes a ticker; it is never scored as 0.
"""
from typing import Dict, List, Optional, Tuple

import numpy as np

from terminal.lab.panel import BENCH, Panel

TOP_N = 10
MIN_PRICE = 5.0
MIN_DOLLAR_ADV = 20e6

MODELS = {
    "MOM_12_1": {"name": "모멘텀 12-1", "style": "중장기",
                 "rule": "최근 1개월을 뺀 12개월 총수익률 상위 10종목, 동일 비중",
                 "params": {"lookback": 252, "skip": 21, "top_n": TOP_N}},
    "LOWVOL_252": {"name": "저변동성", "style": "장기 핵심 보유",
                   "rule": "최근 252거래일 일간 수익률 표준편차 하위 10종목, 동일 비중",
                   "params": {"window": 252, "min_obs": 240, "top_n": TOP_N}},
    "TREND_SWING": {"name": "추세 스윙", "style": "스윙",
                    "rule": "종가>200일선, 50일선>200일선 종목 중 6개월 수익률 상위 10종목, 동일 비중",
                    "params": {"sma_fast": 50, "sma_slow": 200, "lookback": 126, "top_n": TOP_N}},
    "BASE_SPY": {"name": "기준선: SPY", "style": "비교 기준", "rule": "SPY 단독 보유", "params": {}},
    "BASE_EW": {"name": "기준선: 동일가중", "style": "비교 기준",
                "rule": "필터를 통과한 유니버스 전체 동일 비중", "params": {}},
}
COMMON = {"universe": "현재 S&P 500", "min_price": MIN_PRICE, "min_dollar_adv20": MIN_DOLLAR_ADV}


def eligible(p: Panel, i: int, universe: List[str]) -> List[str]:
    """Price >= $5 at row i and 20-session mean dollar volume >= $20M (at least 15 valid sessions)."""
    out = []
    lo = max(0, i - 19)
    close, vol = p.f("close"), p.f("volume")
    for t in universe:
        j = p.col.get(t)
        if j is None or t == BENCH:
            continue
        c = close[i, j]
        if not np.isfinite(c) or c < MIN_PRICE:
            continue
        dv = close[lo:i + 1, j] * vol[lo:i + 1, j]
        dv = dv[np.isfinite(dv)]
        if len(dv) >= 15 and dv.mean() >= MIN_DOLLAR_ADV:
            out.append(t)
    return out


def _ret(adj: np.ndarray, j: int, a: int, b: int) -> Optional[float]:
    if a < 0:
        return None
    x, y = adj[a, j], adj[b, j]
    return float(y / x - 1) if np.isfinite(x) and np.isfinite(y) and x > 0 else None


def _rank(scored: List[Tuple[str, float]], descending: bool, n: int) -> List[Dict]:
    scored = sorted(scored, key=lambda x: ((-x[1]) if descending else x[1], x[0]))[:n]
    return [{"ticker": t, "score": round(s, 6), "rank": k + 1} for k, (t, s) in enumerate(scored)]


def score(code: str, p: Panel, i: int, universe: List[str]) -> Dict:
    """Ranked picks for model ``code`` as of row ``i`` (signal session = p.dates[i])."""
    elig = eligible(p, i, universe)
    adj, close = p.f("adj_close"), p.f("close")
    if code == "BASE_SPY":
        ok = BENCH in p.col and np.isfinite(close[i, p.col[BENCH]])
        return {"picks": [{"ticker": BENCH, "score": None, "rank": 1}] if ok else [], "eligible": int(ok)}
    if code == "BASE_EW":
        return {"picks": [{"ticker": t, "score": None, "rank": None} for t in sorted(elig)], "eligible": len(elig)}
    scored = []
    if code == "MOM_12_1":
        for t in elig:
            r = _ret(adj, p.col[t], i - 252, i - 21)
            if r is not None:
                scored.append((t, r))
        return {"picks": _rank(scored, True, TOP_N), "eligible": len(scored)}
    if code == "LOWVOL_252":
        for t in elig:
            j = p.col[t]
            if i < 252:
                continue
            seg = adj[i - 252:i + 1, j]
            r = seg[1:] / seg[:-1] - 1
            r = r[np.isfinite(r)]
            if len(r) >= 240:
                scored.append((t, float(r.std(ddof=1))))
        return {"picks": _rank(scored, False, TOP_N), "eligible": len(scored)}
    if code == "TREND_SWING":
        for t in elig:
            j = p.col[t]
            if i < 199:
                continue
            seg = close[i - 199:i + 1, j]
            if not np.isfinite(seg).all():
                continue
            sma200, sma50 = seg.mean(), seg[-50:].mean()
            if close[i, j] > sma200 and sma50 > sma200:
                r = _ret(adj, j, i - 126, i)
                if r is not None:
                    scored.append((t, r))
        return {"picks": _rank(scored, True, TOP_N), "eligible": len(scored)}
    raise ValueError(f"UNKNOWN_MODEL {code}")
