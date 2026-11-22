"""The market's expectations as Yahoo's company record states them, recorded so that their history exists one day.

Analyst estimates, target prices, short interest and ex-dividend dates are in the record the scan already downloads for every
stock (kept seven days), so recording them asks nothing new of the network.  Nobody gives the history of these numbers away:
a revision can only be measured against what was written down on an earlier day, and a day that was not written cannot be
rebuilt.  Hence this record.  It is a record only: no score reads it, and no test of it is defined here.  A test needs its own
rule document, committed before any return is computed.

Limits, stated wherever the numbers are shown: Yahoo is not an official source, the values cannot be checked against one, and a
record is refreshed about once a week, so the series is weekly at best.

Store: ``research_data/expectations_{kr,us}/YYYY-MM.jsonl``, append only, one line per (stock, download).  A stock whose stored
record has not been downloaded again since its last line is not written again.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from utils import durable

from terminal.sources import EXPECT_FIELDS

FOLDERS = {"KR": "expectations_kr", "US": "expectations_us"}
SUFFIXES = {"US": ("",), "KR": (".KS", ".KQ")}
KO = {"buy": "매수", "strong_buy": "적극 매수", "hold": "보유", "underperform": "시장 하회", "sell": "매도"}
SOURCE = "야후가 모은 값이고 공식 자료가 아닙니다. 맞춰 볼 공식 자료가 없어 참고로만 적습니다."
FEW_ANALYSTS = 3            # fewer opinions than this is said beside the number


def row_of(ticker: str, rec: Optional[Dict[str, Any]], session: str) -> Optional[Dict[str, Any]]:
    """One line of the record from a cache entry (``stored_at``, ``data``); None when the entry carries no expectation field."""
    data = (rec or {}).get("data") or {}
    fields = {k: data[k] for k in EXPECT_FIELDS if data.get(k) is not None}
    if not fields or not rec.get("stored_at"):
        return None
    fetched = datetime.fromtimestamp(float(rec["stored_at"]), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"ticker": ticker, "fetched": fetched, "session": session, "price": data.get("currentPrice") or data.get("regularMarketPrice"), **fields}


def _files(folder: Path) -> List[Path]:
    return sorted(folder.glob("*.jsonl"))


def _last_fetched(folder: Path) -> Dict[str, str]:
    """Per stock, the download time of its newest line.  Every file is read: the store grows by a few hundred lines a week."""
    out: Dict[str, str] = {}
    for f in _files(folder):
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue                                      # a torn last line is left as it is and skipped
            if r.get("ticker") and r.get("fetched", "") > out.get(r["ticker"], ""):
                out[r["ticker"]] = r["fetched"]
    return out


def record(base: Path, market: str, session: str, tickers: Iterable[str], read: Callable[[str], Optional[Dict[str, Any]]]) -> Dict[str, Any]:
    """``read``: the score service's cache reader.  Appends the stocks whose record was downloaded since their last line."""
    folder = Path(base) / "research_data" / FOLDERS[market]
    folder.mkdir(parents=True, exist_ok=True)
    seen, rows, held = _last_fetched(folder), [], 0
    for t in sorted(set(tickers)):
        rec = next((r for r in (read(f"info:{t}{sfx}") for sfx in SUFFIXES[market]) if r), None)
        row = row_of(t, rec, session)
        if row is None:
            continue
        held += 1
        if row["fetched"] > seen.get(t, ""):
            rows.append(row)
    if rows:          # written like the other forward records: locked, chained, on the disk, and never after a cut line (audit 2026-11-22, ENG-05)
        durable.append_chained(folder, f"{session[:7]}.jsonl", rows)
    return {"status": "OK", "market": market, "session": session, "written": len(rows), "with_expectations": held}


def status(base: Path, market: str) -> Dict[str, Any]:
    folder = Path(base) / "research_data" / FOLDERS[market]
    lines, first, last, names = 0, None, None, set()
    for f in _files(folder) if folder.exists() else []:
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            lines += 1
            names.add(r.get("ticker"))
            day = (r.get("fetched") or "")[:10]
            first, last = min(first or day, day), max(last or day, day)
    return {"market": market, "lines": lines, "stocks": len(names), "first": first, "last": last}


def _money(v: float, market: str) -> str:
    return f"{v:,.0f}원" if market == "KR" else f"${v:,.2f}"


def lines(info: Optional[Dict[str, Any]], close: Optional[float], market: str, today: Optional[date] = None) -> List[str]:
    """The note's section.  Each line states a stored value; none says what the stock will do."""
    d = info or {}
    out: List[str] = []
    n = d.get("numberOfAnalystOpinions")
    who = f"증권사 {n:.0f}곳" if n else "증권사"
    thin = f" 의견이 {n:.0f}곳뿐이라 값이 크게 흔들릴 수 있습니다." if n and n < FEW_ANALYSTS else ""
    mean, low, high = d.get("targetMeanPrice"), d.get("targetLowPrice"), d.get("targetHighPrice")
    if mean and close:
        span = f", 범위 {_money(low, market)} ~ {_money(high, market)}" if low and high else ""
        out.append(f"목표주가: {who} 평균 {_money(mean, market)}(지금 가격 대비 {(mean / close - 1) * 100:+.1f}%){span}.{thin}")
    cur, nxt = d.get("epsCurrentYear"), d.get("forwardEps")
    if cur and nxt and cur > 0:
        out.append(f"예상 주당이익: 올해 {_money(cur, market)}, 다음 해 {_money(nxt, market)}({(nxt / cur - 1) * 100:+.1f}%)." + (f" 다음 해 예상 이익 기준 PER {close / nxt:.1f}배." if close and nxt > 0 else ""))
    elif cur and close and cur > 0:
        out.append(f"예상 주당이익: 올해 {_money(cur, market)}(이 값 기준 PER {close / cur:.1f}배).")
    rec = d.get("recommendationMean")
    if rec:
        key = KO.get(str(d.get("recommendationKey") or ""), None)
        out.append(f"투자의견 평균 {rec:.2f}(1 적극 매수 ~ 5 매도" + (f", '{key}' 쪽" if key else "") + ").")
    short, prior, part = d.get("sharesShort"), d.get("sharesShortPriorMonth"), d.get("shortPercentOfFloat")
    if short and part is not None:
        moved = f", 한 달 전보다 {(short / prior - 1) * 100:+.0f}%" if prior else ""
        when = f"{d['dateShortInterest']} 기준 " if d.get("dateShortInterest") else ""
        out.append(f"공매도 잔고: {when}유통주식의 {part * 100:.1f}%{moved}" + (f", 평균 거래량으로 {d['shortRatio']:.1f}일치" if d.get("shortRatio") else "") + ".")
    if d.get("heldPercentInstitutions") is not None:
        out.append(f"기관 보유 비율 {d['heldPercentInstitutions'] * 100:.0f}%.")
    ex = d.get("exDividendDate")
    if ex:
        ahead = (date.fromisoformat(ex) - today).days if today else None
        rate = f", 연 배당금 {_money(d['dividendRate'], market)}" if d.get("dividendRate") else ""
        out.append(f"배당락일 {ex}" + ("(지난 날짜)" if ahead is not None and ahead < 0 else f"({ahead}일 뒤)" if ahead is not None else "") + f"{rate}.")
    if out:
        out.append(SOURCE + " 점수에 들어가지 않습니다. 과거 값은 어디서도 받을 수 없어, 받는 대로 따로 기록해 이력을 쌓고 있습니다.")
    return out
