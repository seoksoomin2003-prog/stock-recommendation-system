"""Which forward records have stopped growing.

Every side record of the daily job is wrapped so that it can never fail its step: a record that raises is one line in the day's log
and the step stays OK.  That is right for the day, and wrong for the year: a record that stops is never mentioned again, its
one-time reading never falls due, and nobody is there to notice.  This module looks at the outcome instead of the cause: the
records of one market are written from the same sessions, so one that falls several sessions behind the others has stopped.

Read only, and index lines only: no record file is opened, so nothing of a sealed comparison book is read.
"""
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from terminal.qsf import kr_forward as kf

LAG = 3                 # sessions behind the market's newest record before a record counts as stopped (a day's lag is ordinary)
ARCHIVE_DAYS = 6        # days without a write before the price archive counts as stopped (a long weekend is four)
STORES = Path("research_data")
ARCHIVE = Path("data") / "qsf" / "price_archive"
LABELS = {"krx_forward": "한국 결합 점수", "krx_forward_fund": "한국 재무 점수", "krx_forward_events": "한국 공시 사건", "us_challenger": "미국 도전자 점수",
          "kr_swing_challenger": "한국 스윙 도전자", "kr_swing_prior": "한국 이전 스윙 공식", "kr_challenger": "한국 묶음 도전자 점수", "kr_cap_universe": "한국 시가총액 대상", "kr_traded_universe": "한국 거래대금 대상",
          "kr_method": "한국 독자 매매법", "regime_weights_kr": "국면 가중치(한국)", "regime_weights_us": "국면 가중치(미국)", "paper_book_kr": "모의 장부(한국)",
          "paper_book_us": "모의 장부(미국)", "forecast_kr": "예측 범위(한국)", "forecast_us": "예측 범위(미국)", "score_split_kr": "점수 분리 비교(한국)",
          "score_split_us": "점수 분리 비교(미국)", "turnover_book_kr": "회전율 규칙 비교 장부(한국)", "turnover_book_us": "회전율 규칙 비교 장부(미국)",
          "rank_book_kr": "순위 규칙 비교 장부(한국)", "rank_book_us": "순위 규칙 비교 장부(미국)"}


def market_of(store: str) -> str:
    return "US" if store.endswith("_us") or store.startswith("us_") else "KR"


def look(base: Path, stores: Iterable[str], finished: Iterable[str] = (), now: Optional[float] = None) -> List[Dict[str, Any]]:
    """The records that stopped, each with why.  ``finished``: stores that end by design (a comparison book after its reading).
    A store with no record yet is not judged: it has not started."""
    base, done = Path(base), set(finished)
    out: List[Dict[str, Any]] = []
    sessions: Dict[str, List[str]] = {}
    for name in stores:
        if name in done:
            continue
        try:
            rows, torn = kf._index_rows(base / STORES / name / "index.jsonl")
        except (OSError, ValueError):
            out.append({"store": name, "label": LABELS.get(name, name), "problem": "INDEX_UNREADABLE"})
            continue
        if torn:
            out.append({"store": name, "label": LABELS.get(name, name), "problem": "INDEX_TORN"})
        if rows:
            sessions[name] = sorted({r["session"] for r in rows})
    for market in ("KR", "US"):
        mine = {n: s for n, s in sessions.items() if market_of(n) == market}
        newest = max(mine.values(), key=lambda s: s[-1], default=[])
        for name, days in sorted(mine.items()):
            behind = sum(1 for d in newest if d > days[-1])
            if behind >= LAG and not any(o["store"] == name for o in out):
                out.append({"store": name, "label": LABELS.get(name, name), "problem": "BEHIND", "last": days[-1], "behind": behind})
    stamp = time.time() if now is None else now
    for market, ko in (("KR", "한국"), ("US", "미국")):
        p = base / ARCHIVE / f"{market}.json.gz"
        if p.exists() and (stamp - p.stat().st_mtime) / 86400 > ARCHIVE_DAYS:
            out.append({"store": f"price_archive_{market.lower()}", "label": f"가격 보관 파일({ko})", "problem": "STALE", "days": int((stamp - p.stat().st_mtime) / 86400)})
    return out


def phrase(item: Dict[str, Any]) -> str:
    if item["problem"] == "BEHIND":
        return f"{item['label']}(마지막 {item['last']}, {item['behind']}거래일 뒤처짐)"
    if item["problem"] == "STALE":
        return f"{item['label']}({item['days']}일째 갱신 없음)"
    return f"{item['label']}(색인 파일 손상)"


def text(items: List[Dict[str, Any]]) -> Optional[str]:
    """One line for the daily message and the record screen; None when every record is in step."""
    if not items:
        return None
    return (f"기록이 멈춘 곳 {len(items)}개: " + ", ".join(phrase(i) for i in items[:6]) + (" 외" if len(items) > 6 else "") +
            ". 그 기록의 판정이 그만큼 늦어집니다. 사흘 넘게 이어지면 reports/RUNBOOK.md 5절을 보세요.")


# ---------------------------------------------------------------------- a scan that ran, on inputs that were not what they should be
ERROR_SHARE = 0.10      # stocks dropped by an error, of the stocks asked for
STALE_SHARE = 0.20      # stocks scored from a stored copy of their filings because the source did not answer
YAHOO_SHARE = 0.10      # Korean stocks on Yahoo bars alone because the KRX-built bars could not be made
LATEST = Path("data") / "qsf"


def quality(base: Path) -> List[str]:
    """Lines about the newest whole scan of each market (``latest_<market>.json``, the scan's own summary).  A scan with any
    scored stock is recorded and its step is OK; these are the cases where it was OK on degraded inputs, which no message said."""
    import json
    out: List[str] = []
    for market, ko in (("KR", "한국"), ("US", "미국")):
        try:
            d = json.loads((Path(base) / LATEST / f"latest_{market}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        asked = int(d.get("tickers") or 0)
        if not asked:
            continue
        errors = d.get("errors") or {}
        if len(errors) / asked >= ERROR_SHARE:
            kinds = sorted(set(errors.values()), key=lambda k: -list(errors.values()).count(k))
            out.append(f"{ko} 점수 스캔({d.get('session')}): {asked}종목 중 {len(errors)}종목이 오류로 빠졌습니다({', '.join(kinds[:2])}).")
        stale = (d.get("stale_inputs") or {}).get("stocks") or 0
        if stale / asked >= STALE_SHARE:
            out.append(f"{ko} 점수 스캔({d.get('session')}): {asked}종목 중 {stale}종목을 저장해 둔 재무 사본으로 계산했습니다(가장 오래된 것 {(d.get('stale_inputs') or {}).get('oldest_days')}일). 자료를 주는 곳이 응답하지 않고 있습니다.")
        src = (d.get("price_source") or {}).get("by_source") or {}
        yahoo = sum(n for k, n in src.items() if "KRX" not in k)
        if market == "KR" and sum(src.values()) and yahoo / sum(src.values()) >= YAHOO_SHARE:
            out.append(f"한국 점수 스캔({d.get('session')}): {sum(src.values())}종목 중 {yahoo}종목을 KRX 자료 없이 Yahoo 일봉만으로 계산했습니다. KRX 키와 자료를 확인하세요.")
    return out
