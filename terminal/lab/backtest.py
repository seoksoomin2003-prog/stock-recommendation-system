"""Research lab: monthly-rebalanced historical simulation of the challenger rules (REFERENCE ONLY).

Rebalance on the first session of each month: signal from data through the previous session close,
fill at that session's open (adj basis), buy-and-hold until the next rebalance open.  Costs are applied on
traded weight (one-way bps).  Uses TODAY's S&P 500 members -> survivorship bias (results are inflated).
"""
import math
from typing import Dict, List, Optional

import numpy as np

from terminal.lab import models
from terminal.lab.panel import BENCH, Panel

WARMUP = 253
SIM_VERSION = "SIM-1.1"          # 1.1: picks restricted to members that had joined the index
COSTS_BPS = (0.0, 10.0)
LIMITATIONS = [
    "생존 편향(남아 있음): 현재 S&P 500 구성 종목만 사용합니다. 각 종목은 지수 편입일 이후에만 선택되도록 했지만, "
    "그사이 지수에서 탈락·상장폐지된 종목은 빠져 있어 결과가 여전히 부풀려질 수 있습니다.",
    "규칙과 매개변수는 미리 고정했지만, 널리 알려진 규칙이라 과거에 잘 맞았던 것이 선택되었을 수 있습니다.",
    "체결은 시가 기준이며 슬리피지·세금은 반영하지 않았습니다 (비용은 시나리오로만 표시).",
    "과거 성과는 미래 수익을 보장하지 않습니다. 판단은 전향적 비교(모델 탭)를 기준으로 하세요.",
]


def _adj_open(p: Panel, i: int) -> np.ndarray:
    o, c, a = p.f("open")[i], p.f("close")[i], p.f("adj_close")[i]
    with np.errstate(invalid="ignore", divide="ignore"):
        return o * a / c


def rebalance_rows(p: Panel) -> List[int]:
    rows = []
    for i in range(max(WARMUP, 1), len(p.dates)):
        if p.dates[i][:7] != p.dates[i - 1][:7]:
            rows.append(i)
    return rows


def members_at(universe: List[str], added: Optional[Dict[str, Optional[str]]], day: str) -> List[str]:
    """Current members that had already joined the index on ``day`` (unknown join date -> excluded)."""
    if added is None:
        return list(universe)
    return [t for t in universe if added.get(t) and added[t] <= day]


def simulate(p: Panel, code: str, universe: List[str], cost_bps: float = 0.0,
             added: Optional[Dict[str, Optional[str]]] = None) -> Dict:
    rows = rebalance_rows(p)
    if len(rows) < 2:
        return {"status": "UNAVAILABLE", "reason": "가격 이력이 부족합니다 (최소 13개월)."}
    adj = p.f("adj_close")
    nav_dates, nav = [], []
    value = 1.0
    holdings = {}           # ticker -> (units)
    turnover_total = 0.0
    member_counts = []
    for k, r in enumerate(rows):
        end = rows[k + 1] if k + 1 < len(rows) else len(p.dates)
        ao = _adj_open(p, r)
        # value the old book at this open
        if holdings:
            v = 0.0
            for t, u in holdings.items():
                px = ao[p.col[t]]
                v += u * px if np.isfinite(px) else u * last_px.get(t, 0.0)
            value = v
        old_w = {t: (u * (ao[p.col[t]] if np.isfinite(ao[p.col[t]]) else last_px.get(t, 0.0))) / value
                 for t, u in holdings.items()} if holdings else {}
        members = members_at(universe, added, p.dates[r - 1])
        member_counts.append(len(members))
        picks = [x["ticker"] for x in models.score(code, p, r - 1, members)["picks"]]
        picks = [t for t in picks if np.isfinite(ao[p.col[t]])]
        if not picks:
            holdings = {}
        else:
            w = 1.0 / len(picks)
            new_w = {t: w for t in picks}
            traded = sum(abs(new_w.get(t, 0) - old_w.get(t, 0)) for t in set(new_w) | set(old_w))
            turnover_total += traded / 2
            value *= 1 - traded * cost_bps / 1e4
            holdings = {t: value * w / ao[p.col[t]] for t in picks}
        last_px = {t: ao[p.col[t]] for t in holdings}
        for i in range(r, end):
            v = 0.0
            for t, u in holdings.items():
                px = adj[i, p.col[t]]
                if np.isfinite(px):
                    last_px[t] = px
                v += u * last_px[t]
            nav_dates.append(p.dates[i])
            nav.append(v if holdings else value)
    return {"status": "REAL", "dates": nav_dates, "nav": nav, "rebalances": len(rows),
            "avg_turnover": turnover_total / len(rows), "members_first": member_counts[0],
            "members_last": member_counts[-1], **metrics(nav_dates, nav)}


def benchmark(p: Panel) -> Dict:
    rows = rebalance_rows(p)
    if len(rows) < 2 or BENCH not in p.col:
        return {"status": "UNAVAILABLE"}
    j = p.col[BENCH]
    start = _adj_open(p, rows[0])[j]
    dates, nav, last = [], [], start
    for i in range(rows[0], len(p.dates)):
        px = p.f("adj_close")[i, j]
        last = px if np.isfinite(px) else last
        dates.append(p.dates[i])
        nav.append(float(last / start))
    return {"status": "REAL", "dates": dates, "nav": nav, **metrics(dates, nav)}


def metrics(dates: List[str], nav: List[float]) -> Dict:
    a = np.asarray(nav, dtype=float)
    if len(a) < 2:
        return {}
    r = a[1:] / a[:-1] - 1
    years = len(a) / 252
    peak = np.maximum.accumulate(a)
    dd = a / peak - 1
    by_year: Dict[str, float] = {}
    start_val = a[0]
    for k in range(len(a)):
        y = dates[k][:4]
        if k + 1 == len(a) or dates[k + 1][:4] != y:
            by_year[y] = float(a[k] / start_val - 1)
            start_val = a[k]
    sd = float(r.std(ddof=1)) if len(r) > 1 else float("nan")
    return {"total_return": float(a[-1] / a[0] - 1), "cagr": float((a[-1] / a[0]) ** (1 / years) - 1),
            "vol": sd * math.sqrt(252), "sharpe": float(r.mean() / sd * math.sqrt(252)) if sd > 0 else None,
            "max_drawdown": float(dd.min()), "by_year": by_year, "start": dates[0], "end": dates[-1]}


def run_all(p: Panel, universe: List[str], added: Optional[Dict[str, Optional[str]]] = None) -> Dict:
    bench = benchmark(p)
    out = {"benchmark": {k: v for k, v in bench.items()}, "models": {}, "limitations": LIMITATIONS,
           "costs_bps": list(COSTS_BPS)}
    for code in ("MOM_12_1", "LOWVOL_252", "TREND_SWING", "BASE_EW"):
        res = {}
        for c in COSTS_BPS:
            s = simulate(p, code, universe, c, added)
            if s.get("status") == "REAL" and bench.get("by_year"):
                s["excess_by_year"] = {y: s["by_year"][y] - bench["by_year"].get(y, float("nan"))
                                       for y in s["by_year"] if y in bench["by_year"]}
            res[str(int(c))] = s
        out["models"][code] = res
    return out
