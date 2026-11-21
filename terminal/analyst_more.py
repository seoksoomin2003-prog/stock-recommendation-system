"""Reference readings added after the third audit (reports/ANALYST_AUDIT_3_2026_11_22.md).  None of them enters a score.

- ``reactions``: how the price moved around the company's past results announcements, from stored dates and stored prices.
- ``valuation_history``: where today's P/E and P/B stand inside the stock's own range over the stored prices.
- ``deal_line``: merger and tender-offer filings as a stated fact.
- ``financial_wording`` / ``financial_note``: a bank has no gross margin; "no data" is the wrong word for it.
- ``financial_share_line``: how much of the long-term buy list is financial companies.
- ``dividend_item_text``: an ex-dividend date within the next days.
"""
from __future__ import annotations

from bisect import bisect_right
from typing import Any, Dict, List, Optional, Sequence

SHOWN_REACTIONS = 8
MIN_REACTIONS = 3
MIN_SAMPLES = 60            # weekly samples: a little over a year
STEP = 5                    # one sample a week
MAX_SHARE_CHANGE = 0.05     # the range assumes an unchanged share count; past this yearly change it is not computed
FINANCIAL_SECTORS = ("Financial Services", "금융")
FINANCIAL_SHARE = 0.25
NOT_APPLICABLE = ("영업이익률", "매출총이익률", "영업현금/순이익", "잉여현금흐름 마진", "부채/자본", "순부채/EBITDA", "이자보상배율", "유동비율")
FINANCIAL_NOTE = ("금융업(은행·보험·증권)은 매출총이익, 영업현금흐름, 부채비율이 다른 업종과 같은 뜻이 아니어서 그 요인을 비워 두고 남은 요인으로만 채점합니다. "
                  "낮은 PER·PBR은 업의 구조이기도 해서, 같은 점수라도 다른 업종의 점수와 바로 견주기 어렵습니다.")


# ---------------------------------------------------------------------------------------------- results announcements
def reactions(bars: Sequence[Dict[str, Any]], dates: Sequence[str], bench: Optional[Sequence[Dict[str, Any]]] = None, shown: int = SHOWN_REACTIONS) -> List[Dict[str, Any]]:
    """Per past announcement day: the move from the close before it to the close of the session after it, and to the fifth
    session after it.  The two-session window is used because the stored date does not say whether the results came before the
    open or after the close.  ``rel``: the same first move less the benchmark's.  Newest first."""
    days = [b["date"] for b in bars]
    close = {b["date"]: b["close"] for b in bars if b.get("close")}
    bclose = {b["date"]: b["close"] for b in bench or [] if b.get("close")}
    out = []
    for d in sorted(set(dates), reverse=True):
        i = bisect_right(days, d) - 1                 # the announcement session, or the last session before a non-trading date
        if i < 0 or days[i] != d:
            i += 1                                    # announced on a day without trading: the next session is the first to react
        before, after, fifth = i - 1, i + 1, i + 5
        if before < 0 or after >= len(days):
            continue
        a, b = close.get(days[before]), close.get(days[after])
        if not a or not b:
            continue
        row: Dict[str, Any] = {"date": d, "move": b / a - 1, "five": None, "rel": None}
        if fifth < len(days) and close.get(days[fifth]):
            row["five"] = close[days[fifth]] / a - 1
        if bclose.get(days[before]) and bclose.get(days[after]):
            row["rel"] = row["move"] - (bclose[days[after]] / bclose[days[before]] - 1)
        out.append(row)
        if len(out) >= shown:
            break
    return out


def reaction_lines(rows: Sequence[Dict[str, Any]], basis: Optional[str] = None) -> List[str]:
    if len(rows) < MIN_REACTIONS:
        return []
    moves = [r["move"] for r in rows]
    size = sum(abs(m) for m in moves) / len(moves)
    up = sum(1 for m in moves if m > 0)
    each = ", ".join(f"{r['date'][2:7]} {r['move'] * 100:+.1f}%" for r in rows)
    out = [f"지난 {len(rows)}번의 실적 발표 전후 움직임(발표 전날 종가 → 발표 다음 거래일 종가): 평균 크기 {size * 100:.1f}%, 오른 적 {up}번, 내린 적 {len(rows) - up}번, 가장 큰 하락 {min(moves) * 100:+.1f}%."]
    out.append(f"발표별: {each}.")
    fives = [r["five"] for r in rows if r.get("five") is not None]
    rels = [r["rel"] for r in rows if r.get("rel") is not None]
    tail = []
    if len(fives) >= MIN_REACTIONS:
        same = sum(1 for r in rows if r.get("five") is not None and (r["five"] > 0) == (r["move"] > 0))
        tail.append(f"발표 뒤 5거래일까지 같은 방향이 이어진 것은 {len(fives)}번 중 {same}번")
    if len(rels) >= MIN_REACTIONS:
        tail.append(f"지수의 움직임을 뺀 평균 크기는 {sum(abs(x) for x in rels) / len(rels) * 100:.1f}%")
    if tail:
        out.append("; ".join(tail) + ".")
    out.append("지난 발표 때의 크기를 보여 줄 뿐 다음 발표의 방향을 말하지 않습니다." + (f" 발표일 기준: {basis}." if basis else ""))
    return out


# ---------------------------------------------------------------------------------------------- valuation against its own past
def _known(series: Sequence[Dict[str, Any]], day: str) -> Optional[float]:
    """The newest fiscal year's value among the rows filed on or before ``day``; for one year, the latest filing of it."""
    best = None
    for r in series or []:
        if r.get("val") is None or not r.get("filed") or not r.get("end") or r["filed"] > day:
            continue
        if best is None or (r["end"], r["filed"]) > (best["end"], best["filed"]):
            best = r
    return None if best is None else float(best["val"])


def valuation_history(bars: Sequence[Dict[str, Any]], annual: Optional[Dict[str, Any]], pe_now: Optional[float], pb_now: Optional[float],
                      share_change: Optional[float] = None) -> Dict[str, Any]:
    """Weekly P/E and P/B over the stored prices, each with the annual figure that had been filed by that day.

    Built from today's ratio: ratio_t = ratio_now x (price_t / price_now) x (figure_now / figure_t).  That holds the share
    count still, so the range is not computed when the count moved more than ``MAX_SHARE_CHANGE`` in a year, and the unknown
    count change is said beside the result.  Loss years have no P/E and are left out of its range."""
    if share_change is not None and abs(share_change) > MAX_SHARE_CHANGE:
        return {"status": "SKIPPED", "reason": f"주식 수가 1년에 {share_change * 100:+.1f}% 바뀌어, 주식 수를 그대로 두고 계산하는 자기 이력 범위를 내지 않았습니다."}
    rows = [b for b in bars if b.get("close") and b.get("date")]
    if len(rows) < MIN_SAMPLES * STEP or not annual:
        return {"status": "UNAVAILABLE", "reason": "저장된 가격이나 재무가 모자랍니다."}
    last = rows[-1]
    out: Dict[str, Any] = {"status": "REAL", "from": rows[0]["date"], "to": last["date"], "share_change_known": share_change is not None}
    for key, now, series in (("pe", pe_now, annual.get("net_income")), ("pb", pb_now, annual.get("equity"))):
        base = _known(series or [], last["date"])
        if not now or now <= 0 or not base or base <= 0:
            continue
        vals = []
        for b in rows[::-STEP]:                       # weekly, counted back from the newest bar
            then = _known(series, b["date"])
            if then and then > 0:
                vals.append(now * (b["close"] / last["close"]) * (base / then))
        if len(vals) < MIN_SAMPLES:
            continue
        vals.sort()
        out[key] = {"now": now, "low": vals[0], "mid": vals[len(vals) // 2], "high": vals[-1], "place": sum(1 for v in vals if v <= now) / len(vals), "n": len(vals)}
    if "pe" not in out and "pb" not in out:
        return {"status": "UNAVAILABLE", "reason": "이익이나 자본이 0 이하인 기간이 길어 범위를 내지 못했습니다."}
    return out


def valuation_lines(h: Optional[Dict[str, Any]]) -> List[str]:
    if not h or h.get("status") == "UNAVAILABLE":
        return []
    if h.get("status") == "SKIPPED":
        return [h["reason"]]
    out = []
    for key, label in (("pe", "PER"), ("pb", "PBR")):
        v = h.get(key)
        if not v:
            continue
        word = "자기 이력에서 가장 싼 쪽" if v["place"] <= 0.2 else "자기 이력에서 가장 비싼 쪽" if v["place"] >= 0.8 else "자기 이력의 가운데 부근"
        out.append(f"자기 이력 대비 {label} {v['now']:.1f}배: {h['from'][:7]}부터의 범위 {v['low']:.1f}~{v['high']:.1f}배(중앙 {v['mid']:.1f}배) 중 아래에서 {v['place'] * 100:.0f}% 위치, {word}.")
    if out:
        out.append("주마다 그날까지 제출된 연간 재무로 계산했고, 주식 수는 그대로였다고 본 참고값입니다" + ("." if h.get("share_change_known") else "(주식 수 변화를 알 수 없는 종목입니다)."))
    return out


# ---------------------------------------------------------------------------------------------- merger filings
def deal_line(filings: Sequence[Dict[str, Any]], still: bool = False) -> Optional[str]:
    """``filings``: ``events.deal_filings`` (newest first).  ``still``: the price hardly moves, which is how a target trades."""
    if not filings:
        return None
    kinds = []
    for f in filings:
        if f["label"] not in [k[0] for k in kinds]:
            kinds.append((f["label"], f["form"], f["date"]))
    what = ", ".join(f"{label}({form}, {day})" for label, form, day in kinds[:3])
    tail = ("가격이 거의 움직이지 않는 것과 함께 보면 인수되는 쪽으로 읽힙니다. 인수 가격이 정해진 종목은 더 오를 여지가 작고, 거래가 깨지면 크게 내릴 수 있습니다."
            if still else "이 서류는 인수하는 쪽이 낼 때도 있으니 공시 원문에서 어느 쪽인지 확인하세요.")
    return f"SEC에 인수·합병 절차 공시가 있습니다: {what}. {tail} 점수는 이 공시를 읽지 않습니다."


# ---------------------------------------------------------------------------------------------- financial companies
def is_financial(sector: Optional[str]) -> bool:
    return bool(sector) and sector in FINANCIAL_SECTORS


def financial_wording(line: str) -> str:
    """In a financial company's note an item its business does not have reads "not applicable", not "no data"."""
    for name in NOT_APPLICABLE:
        line = line.replace(f"{name} 자료 없음", f"{name} 해당 없음(금융업)")
    return line


def financial_share_line(rows: Sequence[Dict[str, Any]], buy: float = 70.0, share: float = FINANCIAL_SHARE) -> Optional[str]:
    """``rows``: long-term screen rows (score, sector, actionability).  Said only when financials crowd the buy list."""
    scored = [r for r in rows if r.get("score") is not None]
    picks = [r for r in scored if r["score"] >= buy and r.get("actionability") == "ACTIONABLE"]
    fin = [r for r in picks if is_financial(r.get("sector"))]
    if len(picks) < 8 or len(fin) / len(picks) < share:
        return None
    all_fin = sum(1 for r in scored if is_financial(r.get("sector")))
    return (f"장기 매수 후보 {len(picks)}개 중 금융업이 {len(fin)}개({len(fin) / len(picks) * 100:.0f}%)입니다. 대상 전체에서 금융업은 {all_fin / len(scored) * 100:.0f}%입니다. "
            "금융업은 현금흐름·부채 요인이 빠진 채 채점돼 점수가 높게 나오는 편이니, 장기 상위 목록을 금융 비중이 큰 목록으로 읽으세요.")


# ---------------------------------------------------------------------------------------------- ex-dividend dates
def dividend_item_text(d: Dict[str, Any]) -> str:
    when = "오늘" if d["days_away"] == 0 else f"{d['days_away']}일 뒤"
    who = "보유" if d.get("held") else "관심"
    return (f"{who} 종목 {d.get('name') or d['ticker']}({d['ticker']}) 배당락일 {d['date']}({when}). 배당락일에 사면 이번 배당을 받지 못하고, 그날 주가는 보통 배당만큼 낮게 시작합니다. "
            "야후가 모은 날짜라 회사 공시와 다를 수 있습니다.")
