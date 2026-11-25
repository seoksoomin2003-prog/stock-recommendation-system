"""New filings of held and watched stocks, checked during the day (user decision 2026-11-24: "만들어").

Every ``EVERY_S`` seconds while a market's filing hours are open, the terminal server asks the official filing lists (OpenDART for
Korea, SEC EDGAR for the US) about the stocks in the user's account and watch list.  A filing whose title or 8-K item is on the
lists below is written to ``data/terminal/filing_alerts.jsonl``, shown on the 오늘 screen and sent by Telegram when Telegram is set
up.  No score reads it and nothing is decided from it: the daily scan reads the same lists as before.

The first look at a stock only records what is already there, so adding a stock never sends its old filings.  A failed request
is logged by type and tried again at the next turn.  Headlines (news) are a separate record (terminal/news.py).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from terminal.qsf import events

log = logging.getLogger(__name__)
EVERY_S = 1800
MAX_PER_MARKET = 60
STATE = Path("data") / "terminal" / "filing_watch.json"
ALERTS = Path("data") / "terminal" / "filing_alerts.jsonl"
SEEN_DAYS = 30
CATCH_UP_DAYS = 7       # after days without a turn (the Mac asleep), the next turn asks back to the last one, at most this far
PAUSE_S = 0.25          # between two requests to the same provider (SEC asks for at most 10 a second)
SEOUL, NEW_YORK = ZoneInfo("Asia/Seoul"), ZoneInfo("America/New_York")
# Filing hours, local weekdays: OpenDART takes filings until about 19:00 KST; EDGAR accepts 06:00-22:00 ET.
HOURS = {"KR": (SEOUL, 7, 20), "US": (NEW_YORK, 6, 22)}

# Korean report titles worth a message (title words, spaces removed).  The event lists the score uses, plus what a holder wants
# to hear the same day even though the score does not count it.
KR_EXTRA = (("자기주식처분", "자사주 처분"), ("최대주주변경", "최대주주 변경"), ("합병", "합병"), ("분할", "분할"), ("공개매수", "공개매수"),
            ("영업양수", "영업 양수"), ("영업양도", "영업 양도"), ("단일판매ㆍ공급계약", "단일 판매·공급 계약"), ("무상증자", "무상증자"),
            ("매매거래정지", "매매 거래 정지"), ("조회공시", "조회공시"), ("불성실공시", "불성실공시법인 지정"), ("잠정", "잠정 실적"),
            ("투자주의", "투자주의·경고"), ("투자경고", "투자주의·경고"))
KR_WORDS = tuple(events.KR_SEVERE) + tuple(events.KR_NEGATIVE) + tuple(events.KR_POSITIVE) + tuple(events.KR_GOV) + KR_EXTRA
US_8K_EXTRA = {"1.01": "중요 계약 체결 (8-K 1.01)", "2.01": "자산 인수·처분 완료 (8-K 2.01)", "2.02": "실적 발표 (8-K 2.02)",
               "5.01": "지배권 변경 (8-K 5.01)", "5.02": "임원·이사 변경 (8-K 5.02)"}
US_8K = {**US_8K_EXTRA, **events.NEGATIVE_8K, **events.GOV_8K, **events.SEVERE_8K}
US_FORMS = {**events.DEAL_FORMS, **events.GOV_FORMS}


def open_now(market: str, at: datetime) -> bool:
    zone, start, end = HOURS[market]
    local = at.astimezone(zone)
    return local.weekday() < 5 and start <= local.hour < end


def kr_label(title: str) -> Optional[str]:
    name = (title or "").replace(" ", "")
    for key, label in KR_WORDS:
        if key in name:
            return label
    return None


def us_label(form: str, items: str) -> Optional[str]:
    base = form[:-2] if form.endswith("/A") else form
    for f in (form, base):
        if f in US_FORMS:
            return US_FORMS[f]
    if base == "8-K":
        got = [US_8K[i.strip()] for i in str(items or "").split(",") if i.strip() in US_8K]
        return ", ".join(got) if got else None
    return None


def targets(terminal: Any) -> Dict[str, List[str]]:
    """{market: tickers} from the account's open positions and the watch list, at most MAX_PER_MARKET each."""
    from terminal import portfolio as pf
    out: Dict[str, List[str]] = {"US": [], "KR": []}
    for market in ("US", "KR"):
        try:
            out[market] += sorted(terminal._book(market)[2]["positions"])
        except Exception as exc:
            log.warning("filing watch: %s holdings unreadable (%s)", market, type(exc).__name__)
    try:
        for t in terminal.watchlist():
            if t.startswith("^") or "=" in t:          # an index or a rate files nothing (a name without a CIK is skipped later)
                continue
            m = pf.market_of(t)
            if m in out and t not in out[m]:
                out[m].append(t)
    except Exception as exc:
        log.warning("filing watch: watch list unreadable (%s)", type(exc).__name__)
    return {m: v[:MAX_PER_MARKET] for m, v in out.items()}


def _kr_found(terminal: Any, ticker: str, day: str, since: Optional[str] = None) -> List[Dict[str, Any]]:
    """``since`` (YYYYMMDD): the first day asked, for the days no turn ran; the day alone otherwise."""
    qsf = terminal.qsf
    if not qsf.dart.configured:
        return []
    corp = qsf._corp_code(ticker)
    if not corp:
        return []
    got = events.kr_filings(qsf.dart._get, corp, since or day, day)

    def iso(r):
        d = str(r.get("rcept_dt") or day)
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return [{"key": f"KR:{r.get('rcept_no')}", "date": iso(r), "title": (r.get("report_nm") or "").strip(),
             "label": kr_label(r.get("report_nm") or ""), "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['rcept_no']}" if r.get("rcept_no") else None}
            for r in got["rows"] if r.get("rcept_no")]


def _us_found(terminal: Any, ticker: str, since: str) -> List[Dict[str, Any]]:
    cik = terminal._cik(ticker)
    if not cik:
        return []
    # One list for the watch, the card and the score (assessment 2026-11-25: the watch could announce an 8-K while the card's
    # events and the deal pin still read a list up to 20 hours old).  The fresh list is stored where they read it.
    refresh = getattr(terminal.qsf, "refresh_us_filings", None)
    rows = (refresh(cik) or {}).get("filings") or [] if refresh else events.recent_filings(terminal.src.sec_submissions(cik))
    out = []
    for r in rows:
        if not r.get("date") or r["date"] < since or not r.get("accession"):
            continue
        acc = r["accession"]
        out.append({"key": f"US:{acc}", "date": r["date"], "title": r["form"] + (f" (항목 {r['items']})" if r.get("items") else ""),
                    "label": us_label(r["form"], r.get("items") or ""),
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{r.get('doc') or ''}"})
    return out


def _read_state(base: Path) -> Dict[str, Any]:
    try:
        return json.loads((Path(base) / STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"seen": {}, "known": [], "through": {}}


def _write_state(base: Path, state: Dict[str, Any], today: str) -> None:
    cut = (datetime.fromisoformat(today) - timedelta(days=SEEN_DAYS)).date().isoformat()
    state["seen"] = {k: v for k, v in state.get("seen", {}).items() if v >= cut}
    path = Path(base) / STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def check(terminal: Any, at: Optional[datetime] = None, markets: Iterable[str] = ("KR", "US"), send: Optional[Callable[[str], Any]] = None,
          pause: Callable[[float], None] = time.sleep) -> Dict[str, Any]:
    """One turn.  Returns {"asked", "failed", "new": [alerts]}.  ``send``: the Telegram sender (tests pass a stand-in)."""
    at = at or datetime.now(timezone.utc)
    base = Path(terminal.base)
    state = _read_state(base)
    seen, known = state.setdefault("seen", {}), set(state.setdefault("known", []))
    names = {}
    asked, failed, new = 0, [], []
    through = state.setdefault("through", {})
    for market in markets:
        if not open_now(market, at):
            continue
        local = at.astimezone(HOURS[market][0]).date()
        # the first day to ask: the day of this market's last turn (it may have ended before the day's last filing), never
        # more than CATCH_UP_DAYS back; with no earlier turn, today (Korea) or yesterday (US, whose filings come in the evening)
        try:
            last = datetime.fromisoformat(through[market]).date() if through.get(market) else None
        except (TypeError, ValueError):
            last = None
        first = max(min(last, local), local - timedelta(days=CATCH_UP_DAYS)) if last else local
        mine = targets(terminal).get(market, [])
        if market == "KR" and mine and not terminal.qsf.dart.configured:
            failed.append({"market": "KR", "ticker": "*", "error": "NO_DART_KEY"})       # said once, not passed over in silence
            continue
        before = len(failed)
        for ticker in mine:
            if asked or failed:
                pause(PAUSE_S)
            try:
                found = (_kr_found(terminal, ticker, local.strftime("%Y%m%d"), first.strftime("%Y%m%d")) if market == "KR"
                         else _us_found(terminal, ticker, (min(first, local - timedelta(days=1)) if last else local - timedelta(days=1)).isoformat()))
            except Exception as exc:                      # tried again next turn; the type only, never a URL or a key
                failed.append({"market": market, "ticker": ticker, "error": type(exc).__name__})
                continue
            asked += 1
            first = f"{market}:{ticker}" not in known
            for f in found:
                if f["key"] in seen:
                    continue
                seen[f["key"]] = f["date"]
                if first or not f["label"]:
                    continue
                if ticker not in names:
                    names[ticker] = _name(terminal, ticker, market)
                new.append({"at": at.isoformat(), "market": market, "ticker": ticker, "name": names[ticker], **{k: f[k] for k in ("date", "title", "label", "url")}})
            known.add(f"{market}:{ticker}")
        if len(failed) == before:               # a turn with a failed request is asked again from the same day
            through[market] = local.isoformat()
    state["known"], state["last_run"] = sorted(known), at.isoformat()
    _write_state(base, state, at.date().isoformat())
    if new:
        with open(base / ALERTS, "a", encoding="utf-8") as fh:
            fh.writelines(json.dumps(a, ensure_ascii=False) + "\n" for a in new)
        try:
            from terminal import notify
            (send or notify.send_telegram)(text(new))
        except Exception as exc:
            log.warning("filing watch: message not sent (%s)", type(exc).__name__)
    return {"asked": asked, "failed": failed, "new": new}


def _name(terminal: Any, ticker: str, market: str) -> Optional[str]:
    try:
        if market == "KR":
            return terminal._kr_name(ticker)
        row = next((r for r in terminal.qsf.latest("US").get("rows") or [] if r.get("ticker") == ticker), None)
        return (row or {}).get("name")
    except Exception:
        return None


def text(alerts: List[Dict[str, Any]]) -> str:
    lines = ["새 공시 (보유·관심 종목, 장중 확인)"]
    for a in alerts:
        who = f"{a['name']}({a['ticker']})" if a.get("name") else a["ticker"]
        lines.append(f"· {who} {a['date']} {a['title']} — {a['label']}")
    lines.append("공시 사실을 알리는 것이며 점수와 판단은 바뀌지 않았습니다. 매매 지시가 아닙니다.")
    return "\n".join(lines)


def recent(base: Path, now: datetime, days: int = 2) -> List[Dict[str, Any]]:
    """Alerts of the last ``days`` days, newest first, for the 오늘 screen."""
    cut = now.astimezone(timezone.utc) - timedelta(days=days)        # a naive time is the device's own clock
    try:
        rows = [json.loads(l) for l in (Path(base) / ALERTS).read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []
    out = []
    for r in rows:
        try:
            if datetime.fromisoformat(r["at"]) >= cut:
                out.append(r)
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out, key=lambda r: datetime.fromisoformat(r["at"]), reverse=True)


def start(terminal: Any, every: float = EVERY_S, sleep: Callable[[float], None] = time.sleep, turns: Optional[int] = None) -> threading.Thread:
    """The server's own loop (the real server only).  ``turns``: stop after this many rounds (tests)."""
    def run():
        n = 0
        while turns is None or n < turns:
            try:
                check(terminal)
            except Exception as exc:
                log.warning("filing watch turn failed: %s", type(exc).__name__)
            n += 1
            sleep(every)
    th = threading.Thread(target=run, name="filing-watch", daemon=True)
    th.start()
    return th
