"""The daily record of the five engines, the committee and the six portfolios, and what the record has earned on paper (IC-1).

One line per session and market, appended once: every judged stock's five recommendations and the committee's decision as
letters, the scores, and the six portfolios with their weights.  The next day's engines read the last line to know what each
portfolio holds (a held stock is kept until its engine says sell).  Nothing is rewritten.

Paper performance is read from this record alone, forward from the day it started: no return before the first line is ever
computed, and none is shown as if it were a track record.  A day's fall of more than half is booked as the loss it is; a day's
rise of more than half is left out until explained; a holding whose price is gone is carried at its last close (user decision
2026-11-22, before the first line was written: the first rule left out both, so a crash and a delisting cost nothing).  A day's weights are the ones recorded two sessions before its
close: a portfolio made after the close of day D is taken to be bought at the close of D+1 and earns from D+1 to D+2.  That
is one day slower than the record and never looks ahead.  Costs are the program's Toss fee table on what changed hands.
Ratios that need a history (annualised return, Sharpe, Sortino, Calmar, alpha, beta) are not given before ``MIN_RATIO_DAYS``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from utils import durable

from terminal.committee import council, portfolios
from terminal.committee import investors as iv

FOLDERS = {"KR": "committee_kr", "US": "committee_us"}
CODES = {iv.STRONG_BUY: "S", iv.BUY: "B", iv.HOLD: "H", iv.WAIT: "W", iv.REDUCE: "R", iv.SELL: "X", iv.AVOID: "A", iv.NO_DATA: "N", council.CONDITIONAL_BUY: "C"}
MIN_RATIO_DAYS, YEAR, JUMP = 60, 252, 0.5


def _files(base: Path, market: str) -> List[Path]:
    folder = Path(base) / "research_data" / FOLDERS[market]
    return sorted(folder.glob("*.jsonl")) if folder.is_dir() else []


def read(base: Path, market: str) -> List[Dict[str, Any]]:
    """Every recorded line in session order.  A line that cannot be read is left out, never repaired."""
    out = []
    for path in _files(base, market):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("session"):
                out.append(row)
    return sorted(out, key=lambda r: r["session"])


def stamp(base: Path, market: str) -> Any:
    return tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in _files(base, market))


def before(rows: List[Dict[str, Any]], session: str) -> Optional[Dict[str, Any]]:
    older = [r for r in rows if r["session"] < session]
    return older[-1] if older else None


def held(row: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    return {key: dict(p.get("holdings") or {}) for key, p in ((row or {}).get("portfolios") or {}).items()}


def line(market: str, session: str, book: Dict[str, Dict[str, Any]], ports: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    stocks = {t: "".join(CODES[e["opinions"][k]["recommendation"]] for k in iv.ORDER) + CODES[e["committee"]["decision"]] for t, e in book.items()}
    scores = {t: [None if e["opinions"][k]["score"] is None else round(e["opinions"][k]["score"]) for k in iv.ORDER] + [None if e["committee"]["scores"]["attractiveness"] is None else round(e["committee"]["scores"]["attractiveness"])]
              for t, e in book.items()}
    return {"session": session, "market": market, "rules": iv.RULES, "order": list(iv.ORDER) + ["COMMITTEE"], "codes": CODES, "stocks": stocks, "scores": scores,
            "portfolios": {key: {"cash": p["cash"], "holdings": {r["ticker"]: r["weight"] for r in p["holdings"]},
                                 # the day's interrupts (2026-11-23): overweight notices (nothing traded) and fatal exits
                                 **({"overweight": [{k: n[k] for k in ("ticker", "name", "weight", "cap", "new", "text")} for n in p["overweight"]]} if p.get("overweight") else {}),
                                 **({"fatal": [{k: n[k] for k in ("ticker", "name", "weight", "why")} for n in p["fatal"]]} if p.get("fatal") else {})}
                           for key, p in ports.items()}}


def append(base: Path, market: str, session: str, book: Dict[str, Dict[str, Any]], ports: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Written like the other forward records (audit 2026-11-22, ENG-05): one writer at a time, never after a cut line, each line
    chained to the one before, on the disk before it counts.  A cut line stops the record (``durable.TornFile``) until a person looks."""
    folder = Path(base) / "research_data" / FOLDERS[market]
    wrote = durable.append_chained(folder, f"{session[:7]}.jsonl", [line(market, session, book, ports)], skip=lambda: any(r["session"] == session for r in read(base, market)))
    if not wrote:
        return {"status": "ALREADY", "session": session}
    return {"status": "OK", "session": session, "stocks": len(book), "holdings": {key: p["count"] for key, p in ports.items()}}


# ------------------------------------------------------------------------------------------------- paper performance
def _stats(daily: List[float], bench: List[Optional[float]]) -> Dict[str, Any]:
    n = len(daily)
    if not n:
        return {"days": 0}
    value, peak, worst = 1.0, 1.0, 0.0
    for r in daily:
        value *= 1.0 + r
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0)
    out: Dict[str, Any] = {"days": n, "total_return": round(value - 1.0, 5), "max_drawdown": round(worst, 5), "win_rate": round(sum(1 for r in daily if r > 0) / n, 4)}
    pairs = [(r, b) for r, b in zip(daily, bench) if b is not None]
    if pairs:
        bv = 1.0
        for _r, b in pairs:
            bv *= 1.0 + b
        out["benchmark_return"], out["benchmark_days"] = round(bv - 1.0, 5), len(pairs)
    if n < MIN_RATIO_DAYS:
        out["ratios"] = f"기록이 {n}거래일뿐이라 연환산 수익률, 변동성, 샤프·소르티노·칼마 비율, 알파·베타는 계산하지 않습니다({MIN_RATIO_DAYS}거래일부터)."
        return out
    mean = sum(daily) / n
    var = sum((r - mean) ** 2 for r in daily) / (n - 1)
    down = [min(r, 0.0) ** 2 for r in daily]
    vol, dvol = (var * YEAR) ** 0.5, (sum(down) / n * YEAR) ** 0.5
    cagr = value ** (YEAR / n) - 1.0
    out.update({"cagr": round(cagr, 5), "volatility": round(vol, 5), "sharpe": None if vol == 0 else round(mean * YEAR / vol, 3), "sortino": None if dvol == 0 else round(mean * YEAR / dvol, 3),
                "calmar": None if worst == 0 else round(cagr / abs(worst), 3), "ratios": "무위험 수익률을 0으로 둔 값입니다."})
    if len(pairs) >= MIN_RATIO_DAYS:
        mr, mb = sum(r for r, _b in pairs) / len(pairs), sum(b for _r, b in pairs) / len(pairs)
        vb = sum((b - mb) ** 2 for _r, b in pairs)
        beta = None if vb == 0 else sum((r - mr) * (b - mb) for r, b in pairs) / vb
        out["beta"], out["alpha"] = (None, None) if beta is None else (round(beta, 3), round((mr - beta * mb) * YEAR, 5))
    return out


def _move(price: Callable[[str, str], Optional[float]], ticker: str, a: str, b: str) -> Optional[float]:
    p0, p1 = price(ticker, a), price(ticker, b)
    return p1 / p0 - 1.0 if p0 and p1 else None


def performance(rows: List[Dict[str, Any]], price: Callable[[str, str], Optional[float]], benchmark: Callable[[str], Optional[float]], one_way_cost: float,
                keep_daily: bool = False) -> Dict[str, Any]:
    """Paper results of each recorded portfolio.  ``price(ticker, session)`` and ``benchmark(session)`` give a close or None.
    ``keep_daily``: also give each portfolio's daily returns and the index's (the one reading of terminal/committee/reading.py)."""
    sessions = [r["session"] for r in rows]
    out: Dict[str, Any] = {"kind": "PAPER", "kind_ko": "모의 기록(기록을 시작한 날부터, 과거로 거슬러 계산한 값 없음)", "first_session": sessions[0] if sessions else None,
                           "last_session": sessions[-1] if sessions else None, "records": len(rows), "portfolios": {}, "one_way_cost": one_way_cost,
                           "method": "D일 장 마감 뒤 정한 매매를 D+1일 종가에 한 것으로 보고 D+1일에서 D+2일까지의 수익부터 셉니다. 모의 계좌의 비중은 그 하루 동안 가격을 따라 움직인 뒤의 값입니다. "
                                     "배당은 수정 종가에 든 만큼만 반영됩니다."}
    if len(rows) < 3:
        out["status"], out["reason"] = "TOO_SHORT", f"기록이 {len(rows)}거래일입니다. 사흘째 기록부터 첫 하루 수익이 계산됩니다."
        return out
    keys = list((rows[-1].get("portfolios") or {}))
    bench = []
    for i in range(len(rows) - 2):
        b0, b1 = benchmark(sessions[i + 1]), benchmark(sessions[i + 2])
        bench.append(None if not b0 or not b1 else b1 / b0 - 1.0)
    for key in keys:
        daily, costs, turns, unpriced, jumps, stays = [], 0.0, [], set(), [], {}
        ended: List[int] = []
        last: Dict[str, float] = {}
        held: Dict[str, float] = {}                       # what the paper book holds after the last trade
        moved: Dict[str, Optional[float]] = {}            # how each of those moved over the day it was just held
        known: Dict[str, float] = {}                      # each holding's last close on file
        carried: Dict[str, str] = {}                      # holdings valued at that close because the day's price was gone: ticker -> first such session
        for i in range(len(rows) - 2):
            w = dict(((rows[i].get("portfolios") or {}).get(key) or {}).get("holdings") or {})
            # Recorded weights follow prices since 2026-11-23: a weight that only moved with its price was not traded.  What was
            # traded is the gap between today's weights and yesterday's after the same price moves.
            was = portfolios.drift(last, (lambda t, a=sessions[i - 1], b=sessions[i]: _move(price, t, a, b)) if i else None)
            # The trade decided on day D is done at the close of D+1, a day later.  By then the book's own holdings have moved
            # with D+1's prices, so the book ends up holding "what it held, moved, plus the decided change", not the recorded
            # weights.  Until 2026-11-23 the recorded weights were multiplied by the next day's returns as they stood
            # (assessment 2026-11-23: about +-0.4-0.9% over 240 days; fixed before the first record line existed).
            before = portfolios.drift(held, moved.get) if i else {}
            now = {t: v if t not in last else max(0.0, before.get(t, 0.0) + v - was.get(t, 0.0)) for t, v in w.items()}
            whole = sum(now.values())
            if whole > 1.0:                               # never more than the book has
                now = {t: v / whole for t, v in now.items()}
            traded = sum(abs(now.get(t, 0.0) - before.get(t, 0.0)) for t in set(now) | set(before))
            for t in set(last) - set(w):
                ended.append(stays.pop(t, 1))
            for t in w:
                stays[t] = stays.get(t, 0) + 1
            r, moved = 0.0, {}
            for t, weight in now.items():
                p0, p1 = price(t, sessions[i + 1]) or known.get(t), price(t, sessions[i + 2])
                if p0 and not p1:                         # the price is gone (halted, delisted): carried at its last close, and said
                    known[t] = p0
                    carried.setdefault(t, sessions[i + 2])
                    continue
                if not p0 or not p1:
                    unpriced.add(t)                       # never priced since it was bought: nothing to value it by
                    continue
                known[t] = p1
                move = p1 / p0 - 1.0
                if abs(move) > JUMP:
                    booked = move < 0                     # a fall is taken as real (prices are split-adjusted); an unexplained rise is not counted
                    jumps.append({"ticker": t, "session": sessions[i + 2], "move": round(move, 4), "booked": booked})
                    if not booked:
                        continue
                r += weight * move
                moved[t] = move
            cost = traded * one_way_cost
            daily.append(r - cost)
            costs += cost
            turns.append(traded)
            last, held = w, now
        stats = _stats(daily, bench)
        stats.update({"cost_total": round(costs, 5), "turnover_per_day": round(sum(turns) / len(turns), 4) if turns else None,
                      "average_holding_sessions": round(sum(ended) / len(ended), 1) if ended else None, "positions_closed": len(ended),
                      "unpriced": sorted(unpriced), "price_breaks": jumps[:10], "carried_at_last_close": dict(sorted(carried.items())[:20])})
        if keep_daily:
            stats["daily"] = daily
        out["portfolios"][key] = stats
    if keep_daily:
        out["benchmark_daily"] = bench
    out["status"] = "OK"
    return out
