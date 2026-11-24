"""A US stock whose price is held near an agreed deal price (decision 14 (가) of 2026-11-22, delegated to the assistant by the
user on 2026-11-24: "너의 추천대로 해").

A merger or tender-offer filing alone does not say the stock is the one being bought: the buyer files a tender offer (SC TO-T)
and a buyer whose own holders vote files a merger proxy.  On 2026-11-23 thirteen scanned stocks had such a filing; four of them
(BIIB, GILD, MRK, LLY) were buyers.  The price says which side a stock is on: a target trades in a narrow band under the deal
price.  The three pinned names had a 20-session annualised volatility of 1.6%, 4.9% and 6.2%; the other ten 20% or more.  The
line of 10% sits inside that gap.  It was set from this split of filings, not from any return, and is not to be tuned.

What it does: the score stays as computed; a pinned stock is not given a buy band (the card says why), so it leaves the buy
candidates and the order plan.  The pre-registered top-3 record (reports/QSF_TOP3_TRACKING_PROTOCOL.md) ranks by score and is
not changed.  The rule lives in reports/QSF_DEAL_PIN_2026_11_24.md.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

PIN_VOL = 10.0          # annualised %, 20 sessions
WINDOW = 20


def vol20(bars: Sequence[Dict[str, Any]]) -> Optional[float]:
    """Annualised standard deviation of the last 20 daily log returns, in %.  None with fewer than 21 closes."""
    closes = [float(b["close"]) for b in bars[-(WINDOW + 1):] if b.get("close")]
    if len(closes) < WINDOW + 1 or min(closes) <= 0:
        return None
    rets = [math.log(b / a) for a, b in zip(closes, closes[1:])]
    mean = sum(rets) / len(rets)
    return math.sqrt(sum((r - mean) ** 2 for r in rets) / len(rets)) * math.sqrt(252) * 100


def pin(deals: Optional[List[Dict[str, Any]]], bars: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """{form, date, label, vol20} when the stock has a deal filing of the last year and its price barely moves; else None."""
    if not deals:
        return None
    v = vol20(bars)
    if v is None or v >= PIN_VOL:
        return None
    d = deals[0]
    return {"form": d.get("form"), "date": d.get("date"), "label": d.get("label"), "vol20": round(v, 2)}


def band_label(p: Dict[str, Any]) -> str:
    return f"보유·관찰 · 합병 절차로 가격이 묶여 매수 후보에서 뺌({p['label']} {p['date']}, 20일 변동성 {p['vol20']:.1f}%)"


def why(p: Dict[str, Any]) -> str:
    return (f"{p['date']}에 '{p['label']}'이(가) 올라왔고 최근 20거래일 변동성이 연 {p['vol20']:.1f}%로 거의 움직이지 않습니다. "
            "인수 가격에 묶인 종목은 추세·변동성 요인이 높게 나와도 오를 여지가 인수가까지뿐이라, 점수는 그대로 두고 매수 후보 구간을 주지 않습니다.")
