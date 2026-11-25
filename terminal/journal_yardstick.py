"""Each closed trade of the user's own journal beside the same money in the market's index fund over the same days.

User decision 2026-11-25, after the BT-1 backtest and the five-seat debate (reports/reliability_debate_2026_11_25/): no score's top
band beat the index in the record, so the journal says what the plain alternative would have done.  The user's own trades are the
one sample nobody has read yet.

It is a yardstick, not a test: twenty trades swing by luck alone, and the note says so.  Prices alone on both sides (the trade's
profit is counted on the prices paid and received; the fund's on its closes), so a dividend is on neither side.  The fund is
bought at the close of the day the position was opened and sold at the close of the day of the sale; a position built in several
buys is measured from its first one.  No fee is counted on the fund's side.  It changes no score, plan or rule.
"""
from __future__ import annotations

import bisect
from typing import Any, Dict, List, Optional, Sequence

SMALL = 20
NOTE = ("점검용 잣대이고 통계 판정이 아닙니다. 같은 날 같은 금액을 이 시장의 지수 ETF에 넣었다가 같은 날 뺐다면 어땠을지를 가격만으로 견준 값입니다(배당과 ETF 쪽 수수료는 넣지 않음). "
        "여러 번에 나눠 산 종목은 처음 산 날부터 잽니다. 거래 20건의 합계는 우연만으로도 크게 흔들립니다.")


def _close(dates: Sequence[str], closes: Sequence[float], day: str) -> Optional[float]:
    """The fund's last close on or before ``day``; None before its first bar."""
    i = bisect.bisect_right(dates, day) - 1
    return closes[i] if i >= 0 else None


def mark(closed: Sequence[Dict[str, Any]], bars: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """``closed`` (portfolio.replay's sales) with the fund's return over the same days.  A sale the fund has no price for keeps
    None: never zero."""
    rows = sorted((b for b in bars or [] if b.get("date") and b.get("close")), key=lambda b: b["date"])
    dates, closes = [b["date"] for b in rows], [float(b["close"]) for b in rows]
    last = dates[-1] if dates else ""
    out = []
    for c in closed:
        a, z = (_close(dates, closes, c["opened"]), _close(dates, closes, c["date"])) if dates and c.get("opened") and c["date"] <= last else (None, None)
        row = dict(c)
        if a and z:
            idx = z / a - 1
            staked = c["avg_cost"] * c["qty"]
            row.update(index_return_pct=idx * 100, vs_index_pct=c["return_pct"] - idx * 100, index_pnl=staked * idx, vs_index_pnl=c["pnl"] - staked * idx)
        else:
            row.update(index_return_pct=None, vs_index_pct=None, index_pnl=None, vs_index_pnl=None)
        out.append(row)
    return out


def summary(marked: Sequence[Dict[str, Any]], fund: str) -> Dict[str, Any]:
    got = [m for m in marked if m.get("vs_index_pnl") is not None]
    n = len(got)
    return {"fund": fund, "count": len(marked), "compared": n, "ahead": sum(1 for m in got if m["vs_index_pnl"] > 0),
            "pnl": sum(m["pnl"] for m in got) if n else None, "index_pnl": sum(m["index_pnl"] for m in got) if n else None,
            "vs_index_pnl": sum(m["vs_index_pnl"] for m in got) if n else None,
            "mean_vs_index_pct": sum(m["vs_index_pct"] for m in got) / n if n else None, "small_sample": n < SMALL, "note": NOTE}
