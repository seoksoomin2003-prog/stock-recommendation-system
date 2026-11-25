"""The assistant: what the program already worked out, put in the order a person should read it.

No model and no network of its own.  Every line is made by a fixed rule from a figure another module already computed, so the same day
always reads the same way.  It never says buy or sell: it lists what is due and what each condition reads today.  The score has no
confirmed return evidence, and the note on every answer says so.

Two things live here.  ``briefing`` is the day's list in three levels (ACT: about a loss, DUE: has a date, INFO: worth knowing).
``answer`` (further down) reads a typed question by keyword and answers it from the stored scan.  Each part of the briefing fails
alone: a part that could not be read is named, never left out silently.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Any, Callable, Dict, List, Optional

LEVELS = ("ACT", "DUE", "INFO")
LEVEL_KO = {"ACT": "먼저 볼 것", "DUE": "오늘 챙길 것", "INFO": "참고"}
STYLE_KO = {"LONG": "장기", "SWING": "스윙"}
MARKET_KO = {"US": "미국", "KR": "한국", "COIN": "코인"}
NOTE = ("비서는 프로그램이 이미 계산한 것을 정해진 규칙으로 정리해 보여 줄 뿐입니다. 투자 자문이 아니고 주문을 실행하지 않습니다. "
        "점수가 높은 종목의 수익이 더 좋다는 근거는 아직 확인되지 않았습니다.")
EARNINGS_DAYS = 5          # a holding's earnings within this many days is due; the scan's own entry block is a separate rule
FRESH_READING_DAYS = 14    # a verdict is shown as new for this long after its report was written
FRESH_ALERT_HOURS = 36     # the user's own alert conditions that fired since about yesterday morning
SHOWN_ORDERS = 3
SWING_DAYS_LEFT = 3
EX_DIVIDEND_DAYS = 5       # an ex-dividend date of a holding or a watched stock within this many days is listed
PART_KO = {"committee": "가상 포트폴리오 알림", "context": "지수와 거시 일정", "account": "보유 종목 점검", "plan": "주문 계획", "market": "시장 상태", "earnings": "실적 일정", "alerts": "내 알림 조건", "job": "자료 수집 상태",
           "top": "점수 상위 종목", "changes": "직전 기록과 달라진 점", "readings": "판정 일정", "mix": "매수 후보의 구성", "marked": "회피 표시", "gaps": "재무 기준에 따른 점수 차이", "dividends": "배당락일", "filings": "장중 새 공시"}
# the portfolio's own alert codes (terminal.portfolio.alerts) and the exit readings (automation.exit_alerts)
ALERT_LEVEL = {"STOP_HIT": "ACT", "NEAR_STOP": "ACT", "QSF_EXIT": "ACT", "QSF_THESIS_INVALIDATED": "ACT", "QSF_REDUCE": "ACT",
               "TARGET_HIT": "DUE", "NO_STOP": "DUE", "OVERWEIGHT": "DUE", "NO_PRICE": "DUE", "NO_STYLE": "DUE", "SECTOR_OVER": "DUE",
               "QSF_PARTIAL_TAKE_PROFIT": "DUE", "QSF_TIME_STOP_REVIEW": "DUE", "STYLE_DRIFT": "INFO"}
NEWS_STEPS = ("NEWS", "NEWS_KR")       # headlines feed no score: their failure is worth knowing, not due


def item(level: str, kind: str, text: str, ticker: Optional[str] = None, tab: Optional[str] = None, short: Optional[str] = None) -> Dict[str, Any]:
    """One line of the briefing.  ``tab``: where the figures behind it are shown.  ``short``: the same thing for the daily message."""
    return {"level": level, "level_label": LEVEL_KO[level], "kind": kind, "text": text, "ticker": ticker, "tab": tab, "short": short}


def price(v: Optional[float], market: str) -> str:
    if v is None:
        return "없음"
    return f"{v:,.0f}원" if market == "KR" else f"${v:,.2f}"


# ---------------------------------------------------------------------- the rules, each on plain data
def holding_items(portfolio: Dict[str, Any], signals: List[Dict[str, Any]], market: str) -> List[Dict[str, Any]]:
    """``portfolio``: Terminal.portfolio(market).  ``signals``: the items of Terminal.portfolio_signals(market)."""
    from terminal.automation import exit_alerts
    if (portfolio.get("integrity") or {}).get("status") != "OK":
        return [item("ACT", "JOURNAL_BROKEN", "거래 기록 검증에 실패해 보유 종목을 점검하지 못했습니다. '내 계좌'의 안내를 확인하세요.", tab="portfolio")]
    rows = portfolio.get("holdings") or []
    if not rows:
        return [item("INFO", "NO_HOLDINGS", f"{MARKET_KO[market]} 계좌에 기록된 보유 종목이 없습니다. 점검할 손절선이나 매도 조건이 없습니다.", tab="portfolio")]
    out, flagged = [], set()
    for a in list(portfolio.get("alerts") or []) + exit_alerts(signals):
        out.append(item(ALERT_LEVEL.get(a["code"], "DUE"), a["code"], a["text"], a.get("ticker"), "portfolio"))
        flagged.add(a.get("ticker"))
    for s in signals:
        if s.get("status") == "REAL" and s.get("sessions_left") is not None and 0 < s["sessions_left"] <= SWING_DAYS_LEFT:
            out.append(item("DUE", "SWING_LIMIT_NEAR", f"{s['ticker']}: 스윙 보유 기한({s.get('time_limit')})까지 {s['sessions_left']}거래일 남았습니다. 기한이 지나면 재평가 대상입니다.",
                            s["ticker"], "portfolio"))
            flagged.add(s["ticker"])
        elif s.get("status") == "UNAVAILABLE":
            out.append(item("DUE", "SIGNAL_UNAVAILABLE", f"{s['ticker']}: 자료를 읽지 못해 매도 조건을 점검하지 못했습니다.", s["ticker"], "portfolio"))
            flagged.add(s["ticker"])
    calm = [r["ticker"] for r in rows if r["ticker"] not in flagged]
    if calm:
        out.append(item("INFO", "HOLDINGS_CALM", f"보유 {len(rows)}종목 중 {len(calm)}종목은 걸린 조건이 없습니다: {', '.join(calm[:8])}{' 등' if len(calm) > 8 else ''}.", tab="portfolio"))
    return out


def candidate_split(by: Optional[Dict[str, Dict[str, int]]]) -> str:
    """Entry is read from 55 points, the buy band from 70: the count alone reads as if every candidate were a buy candidate."""
    parts = [f"{STYLE_KO[k]} {v['all']}건 중 {v['buy']}건" for k, v in (by or {}).items() if k in STYLE_KO and v.get("all")]
    if not parts:
        return ""
    return f"그중 매수 후보 구간({BUY_LINE:g}점 이상)은 {', '.join(parts)}이고, 나머지는 관망 구간(55~{BUY_LINE:g}점)이면서 진입 조건만 채운 종목입니다. "


def plan_items(plan: Dict[str, Any], market: str) -> List[Dict[str, Any]]:
    """``plan``: Terminal.order_plan(market).  Quantities come from the account the user recorded; without one only the count is known."""
    status = plan.get("status")
    if status == "NO_SCAN":
        return [item("DUE", "NO_SCAN", f"{MARKET_KO[market]} 점수 기록이 없어 진입 후보를 만들지 못했습니다. 자료 수집 상태를 확인하세요.", tab="qsf")]
    n = plan.get("candidates") or 0
    if status == "NO_ACCOUNT":
        return [item("INFO", "NO_ACCOUNT", f"{MARKET_KO[market]} 계좌가 기록돼 있지 않아 주문 수량·손절·한도를 계산하지 못했습니다. 지금 진입 가능 구간으로 읽힌 후보는 스윙·장기 합쳐 {n}건입니다. "
                     + candidate_split(plan.get("candidates_by")) +
                     "'내 계좌'에 입금과 거래를 기록하면 계좌 기준 계획과 보유 종목 점검이 만들어집니다.", tab="account",
                     short=f"계좌 미기록(진입 가능 후보 {n}건)")]
    if status != "REAL":
        return [item("DUE", "PLAN_UNAVAILABLE", "주문 계획을 만들지 못했습니다.", tab="qsf")]
    orders, out = plan.get("orders") or [], []
    for o in orders[:SHOWN_ORDERS]:
        target = f", 목표 {price(o['target'], market)}" if o.get("target") else ""
        out.append(item("DUE", "ORDER", f"{o.get('name') or o['ticker']}({o['ticker']}) {STYLE_KO.get(o['style'], o['style'])} {o['shares']:,}주: 지정가 상한 {price(o['limit'], market)}, "
                        f"손절 {price(o['stop'], market)}{target}, 계좌 비중 {o['weight_pct']:.1f}%, 걸린 한도 {o.get('binding_label') or o.get('binding')}.", o["ticker"], "qsf"))
    if len(orders) > SHOWN_ORDERS:
        out.append(item("INFO", "ORDERS_MORE", f"주문 계획이 {len(orders) - SHOWN_ORDERS}건 더 있습니다. 순위·카드 탭의 '주문 계획·가상 장부'에 모두 있습니다.", tab="qsf"))
    if not orders:
        why = sorted((plan.get("skipped_counts") or {}).items(), key=lambda kv: -kv[1])[:3]
        reasons = {s["code"]: s["reason"] for s in plan.get("skipped") or []}
        detail = "; ".join(f"{reasons.get(code, code)} {count}건" for code, count in why)
        out.append(item("INFO", "NO_ORDERS", f"오늘 계좌 한도 안에서 새로 낼 주문이 없습니다(후보 {n}건)." + (f" 빠진 이유: {detail}." if detail else ""), tab="qsf"))
    return out


def stance_items(stance: Optional[Dict[str, Any]], market: str) -> List[Dict[str, Any]]:
    """The market's stance, when it is not the normal one: the day's plan was made under it."""
    if not stance or stance.get("level") in (None, "NORMAL") or not stance.get("note"):
        return []
    return [item("INFO", "STANCE", f"{MARKET_KO[market]} {stance['note']} 점수와 기록은 그대로입니다.", tab="qsf")]


def market_items(state: Optional[Dict[str, Any]], market: str) -> List[Dict[str, Any]]:
    """``state``: the day's market state (the regime factors, apart from every score)."""
    if not state:
        return []
    score, factor, where = state.get("score_100"), float(state.get("size_factor") or 1.0), MARKET_KO[market]
    cap = state.get("new_exposure_cap")
    capped = f" 새 주문의 합계도 계좌의 {cap * 100:.0f}%까지만 잡습니다." if cap else ""
    if state.get("state") == "UNKNOWN" and factor < 1:
        # an unknown state is planned like an adverse one where the market has a brake; the line used to say "order size unchanged"
        seen = "값이 없습니다" if score is None else f"요인의 절반 이상이 비어 {score:.0f}/100이라는 값을 읽지 않습니다"
        return [item("DUE", "MARKET_UNKNOWN", f"{where} 시장 상태를 읽을 수 없습니다({seen}). 나쁜 날과 같게 새 주문의 위험 한도와 비중 한도를 {factor:g}배로 줄여 계산했습니다.{capped}",
                     tab="qsf", short=f"읽을 수 없음(나쁜 날로 취급, 새 주문 크기 {factor:g}배)")]
    if score is None:
        return [item("INFO", "MARKET_UNKNOWN", f"{where} 시장 상태를 읽을 수 없습니다(자료 없음). 이 시장은 주문 크기를 바꾸지 않습니다.", tab="qsf", short="읽을 수 없음")] if state.get("state") == "UNKNOWN" else []
    if state.get("state") == "ADVERSE" and factor < 1:
        return [item("DUE", "MARKET_ADVERSE", f"{where} 시장 상태 {score:.0f}/100({state.get('label')}): 새 주문의 위험 한도와 비중 한도를 {factor:g}배로 줄여 계산했습니다.{capped} "
                     "과거에 이런 날 뒤에는 변동성이 컸습니다.", tab="qsf", short=f"{score:.0f}/100({state.get('label')}, 새 주문 크기 {factor:g}배)")]
    if state.get("state") == "ADVERSE":
        return [item("INFO", "MARKET_ADVERSE", f"{where} 시장 상태 {score:.0f}/100({state.get('label')}). 이 시장은 과거 시험에서 이 값이 이후 수익이나 변동성을 가르지 못해 주문 크기는 그대로입니다.",
                     tab="qsf", short=f"{score:.0f}/100({state.get('label')})")]
    if state.get("state") == "UNKNOWN":
        return [item("INFO", "MARKET_UNKNOWN", f"{where} 시장 상태는 요인의 절반 이상이 비어 읽지 않습니다({score:.0f}/100은 참고 값). 이 시장은 주문 크기를 바꾸지 않습니다.", tab="qsf", short="읽을 수 없음")]
    return [item("INFO", "MARKET_STATE", f"{where} 시장 상태 {score:.0f}/100({state.get('label')}). 주문 크기는 그대로입니다.", tab="qsf",
                 short=f"{score:.0f}/100({state.get('label')})")]


def earnings_items(calendar: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Stored earnings dates of what the user holds or watches."""
    out = []
    for e in calendar.get("items") or []:
        if not (e.get("held") or e.get("watched")) or e.get("days_away") is None or not 0 <= e["days_away"] <= EARNINGS_DAYS:
            continue
        when = "오늘" if e["days_away"] == 0 else f"{e['days_away']}일 뒤"
        who = "보유 종목" if e.get("held") else "관심종목"
        out.append(item("DUE" if e.get("held") else "INFO", "EARNINGS_SOON", f"{who} {e.get('name') or e['ticker']}({e['ticker']}): 실적 발표 {e['date']}({when}).", e["ticker"], "assist"))
    return out


def alert_items(log: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    """The user's own alert conditions that fired since about yesterday morning."""
    out = []
    for a in log:
        try:
            at = datetime.fromisoformat(a["at"])
        except (KeyError, TypeError, ValueError):
            continue
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        if now - at <= timedelta(hours=FRESH_ALERT_HOURS) and a.get("text"):
            out.append(item("DUE", "MY_ALERT", f"내 알림 조건 발생: {a['text']}", a.get("ticker"), "assist"))
    return out


def job_items(status: Dict[str, Any], labels: Dict[str, str]) -> List[Dict[str, Any]]:
    """``status``: automation.status(base).  A step that failed, a record that stopped, a job that never ran."""
    out = []
    if not status.get("installed"):
        out.append(item("DUE", "JOB_NOT_INSTALLED", "매일 자동 실행이 등록돼 있지 않습니다. 기록이 쌓이지 않습니다. ops 폴더의 '자동 실행 다시 등록'을 실행하세요.", tab="lab"))
    steps = status.get("steps") or {}
    failed = [n for n, s in steps.items() if (s or {}).get("status") == "FAILED"]
    hard = [n for n in failed if n not in NEWS_STEPS]
    if hard:
        out.append(item("DUE", "JOB_FAILED", "오늘 자료 수집에서 실패한 단계: " + ", ".join(f"{labels.get(n, n)}({steps[n].get('detail') or '이유 없음'})" for n in hard)
                        + ". 다음 시간 실행이 다시 시도합니다. 며칠 이어지면 안내 문서(reports/RUNBOOK.md)를 보세요.", tab="lab"))
    for n in failed:
        if n in NEWS_STEPS:
            out.append(item("INFO", "NEWS_FAILED", f"{labels.get(n, n)} 실패: {steps[n].get('detail') or '이유 없음'}. 뉴스는 점수에 들어가지 않습니다.", tab="lab"))
    for note in status.get("notes") or []:
        out.append(item("DUE", "JOB_NOTE", str(note), tab="lab"))
    if status.get("running"):
        out.append(item("INFO", "JOB_RUNNING", "자료 수집이 지금 돌고 있습니다. 끝나면 이 화면의 내용이 바뀔 수 있습니다.", tab="lab"))
    if not steps:
        out.append(item("DUE", "JOB_NEVER", "자료 수집 기록이 없습니다. 위의 '지금 수집'을 누르면 시작합니다.", tab="lab"))
    return out


def top_items(top3: Dict[str, Any], market: str, deals: Iterable[str] = ()) -> List[Dict[str, Any]]:
    """The frozen top three of the newest session, and whether they were written before the market opened.  ``deals``: tickers with
    a merger or tender-offer filing on record; they are marked in the line, which also goes out in the daily message."""
    pinned = set(deals)
    tag = lambda t: " [합병 절차 공시]" if t in pinned else ""          # noqa: E731
    days = (((top3.get("strategies") or {}).get("SWING") or {}).get("days")) or []
    if not days:
        return []
    day = max(days, key=lambda d: d.get("session") or "")
    names = ", ".join(f"{x.get('name') or x['ticker']}({x['ticker']}) {x['score']:.1f}점{tag(x['ticker'])}" for x in day.get("top") or [])
    if not names:
        return []
    brief = ", ".join(f"{(x.get('name') if market == 'KR' else None) or x['ticker']} {x['score']:.1f}{tag(x['ticker'])}" for x in day.get("top") or [])
    out = [item("INFO", "TOP3", f"{MARKET_KO[market]} 스윙 점수 상위 3종목({day['session']} 기록): {names}. 진입 거래일은 {day.get('entry_session')}입니다. 순위일 뿐 매수 신호가 아닙니다.", tab="qsf",
                short=f"{brief} (진입 {day.get('entry_session')})")]
    if day.get("before_open") is False:
        out.append(item("INFO", "RECORD_LATE", f"{day['session']} 기록은 장 시작 뒤에 쓰였습니다. 규칙상 진입 거래일이 {day.get('entry_session')}로 하루 밀렸습니다. "
                        "맥이 아침에 잠들어 있으면 이렇게 됩니다.", tab="lab"))
    return out


def change_items(changes: Dict[str, Any], held: Optional[set] = None) -> List[Dict[str, Any]]:
    """Stocks that entered or left the buy band since the session before.  A holding that left it is due."""
    if changes.get("status") != "REAL":
        return []
    out, held = [], held or set()

    def names(rows):
        return ", ".join(f"{r.get('name') or r['ticker']}({r['ticker']})" for r in rows[:6]) + (" 등" if len(rows) > 6 else "")
    entered, left = changes.get("entered_buy") or [], changes.get("left_buy") or []
    for r in left:
        if r["ticker"] in held:
            out.append(item("DUE", "HELD_LEFT_BUY", f"보유 종목 {r.get('name') or r['ticker']}({r['ticker']})이 매수 후보 구간에서 빠졌습니다"
                            f"({r.get('previous_score', 0):.1f} → {r.get('score', 0):.1f}점). 매도 조건은 보유 종목 점검에서 따로 봅니다.", r["ticker"], "qsf"))
    if entered:
        out.append(item("INFO", "ENTERED_BUY", f"매수 후보 구간에 새로 들어온 종목 {len(entered)}개: {names(entered)}.", tab="qsf"))
    if left:
        out.append(item("INFO", "LEFT_BUY", f"매수 후보 구간에서 빠진 종목 {len(left)}개: {names(left)}.", tab="qsf"))
    if changes.get("model_changed"):
        out.append(item("INFO", "MODEL_CHANGED", f"점수 모델 버전이 바뀌었습니다({changes.get('model_version')}). 직전 기록과의 점수 차이에는 공식 변경이 섞여 있습니다.", tab="qsf"))
    return out


def reading_items(rows: List[Dict[str, Any]], fresh: set) -> List[Dict[str, Any]]:
    """``rows``: readings.status(...)["readings"].  ``fresh``: keys whose report was written in the last days."""
    out = []
    for r in rows:
        if r.get("state") == "READ" and r["key"] in fresh:
            why = " ".join(r.get("reasons") or [])
            out.append(item("INFO", "NEW_VERDICT", f"새 판정 · {r['label']}: {r.get('verdict')}. {r.get('meaning') or ''}. {why} {r.get('after') or ''}".replace("  ", " ").strip(), tab="qsf"))
        elif r.get("state") == "DUE" and r.get("attempts"):
            out.append(item("INFO", "VERDICT_STUCK", f"판정 '{r['label']}'은 기록이 충분한데 {r['attempts']}번 읽지 못했습니다. 매일 작업이 다시 시도합니다.", tab="qsf"))
    return out


def _index_lines(overview: Dict[str, Any]) -> Dict[str, List[str]]:
    """The overview's groups as sentences: each index with its day and month, sectors best and worst by the month."""
    out: Dict[str, List[str]] = {"index": [], "macro": [], "sector": []}
    groups = overview.get("groups") or []
    for g, key in zip(groups, ("index", "macro", "sector")):
        rows = [i for i in g.get("items") or [] if i.get("close") is not None and i.get("status") != "UNAVAILABLE"]
        if key == "sector":
            ranked = sorted((i for i in rows if i.get("change_1m_pct") is not None), key=lambda i: i["change_1m_pct"])
            if len(ranked) >= 4:
                say = lambda xs: ", ".join(f"{i['name']} {i['change_1m_pct']:+.1f}%" for i in xs)      # noqa: E731
                out[key] = [f"한 달 동안 가장 약한 업종: {say(ranked[:3])}.", f"가장 강한 업종: {say(ranked[::-1][:3])}."]
            continue
        for i in rows:
            month = f", 한 달 {i['change_1m_pct']:+.1f}%" if i.get("change_1m_pct") is not None else ""
            day = f"전일 대비 {i['change_pct']:+.2f}%" if i.get("change_pct") is not None else "전일 대비 자료 없음"
            out[key].append(f"{i['name']} {i['close']:,.2f}({day}{month}, {i.get('date')}).")
    return out


def macro_dates(items: List[Dict[str, Any]], market: str) -> List[Dict[str, Any]]:
    """Macro dates that belong to the market on screen: US dates move both markets, a Korean date is not listed under the US."""
    return [e for e in items if market != "US" or e.get("country") in (None, "US")]


def context_items(overview: Dict[str, Any], calendar: Dict[str, Any], market: str) -> List[Dict[str, Any]]:
    """The market in one line for the day's list, and official macro dates within three days."""
    out = []
    first = (_index_lines(overview)["index"] or [None])[:2]
    if first[0]:
        out.append(item("INFO", "MARKET_MOVE", f"{MARKET_KO[market]} 지수: " + " ".join(first), tab="overview"))
    for e in macro_dates(calendar.get("items") or [], market):
        if e.get("days_away") is not None and 0 <= e["days_away"] <= 3:
            when = "오늘" if e["days_away"] == 0 else f"{e['days_away']}일 뒤"
            out.append(item("INFO", "MACRO_DATE", f"거시 일정: {e.get('name')} {e.get('date_kst') or e.get('date')}({when}). 발표 전후에는 시장 전체가 크게 움직일 수 있습니다.", tab="macro"))
    return out


# The day's list keeps the investment items and the job's own state apart on screen (UI audit 2026-11-23): a failed news step is not
# 'something to do today' about the market.  The items stay in one list for the daily message and the assistant's answers.
OPS_KINDS = ("JOB_NOT_INSTALLED", "JOB_FAILED", "NEWS_FAILED", "JOB_NOTE", "JOB_RUNNING", "JOB_NEVER", "RECORD_ALERT")
# Today's figures: the same overview items the market tab shows, the ones a trader looks at first.  A symbol the overview does not
# carry is left out, never made up.
TILE_SYMBOLS = {"US": ("^GSPC", "^IXIC", "^VIX", "^TNX", "KRW=X"), "KR": ("^KS11", "^KQ11", "^KS200", "KRW=X")}
CANDIDATES_SHOWN = 5


def tiles(overview: Dict[str, Any], market: str, state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The overview items for Today's first row, in a fixed order, plus the market state.  Read only."""
    by = {i.get("symbol"): i for g in overview.get("groups") or [] for i in g.get("items") or []}
    got = [by[s] for s in TILE_SYMBOLS.get(market, ()) if s in by]
    shown = None
    if state and state.get("score_100") is not None:
        shown = {k: state.get(k) for k in ("score_100", "state", "label", "size_factor", "session")}
    return {"items": got, "market_state": shown, "source": overview.get("source"), "fetched_at": (overview.get("cache") or {}).get("fetched_at"), "basis": overview.get("basis")}


def candidates(rows: List[Dict[str, Any]], notes: Dict[str, Any], shown: int = CANDIDATES_SHOWN) -> Dict[str, Any]:
    """Today's candidates (user decision 2026-11-23): per style, the stocks whose entry status is 'enter now', by score, as the
    order plan reads them.  Each row carries its band and its largest push up and down from the ranking notes."""
    from terminal.qsf import order_plan as op
    note_rows, sectors = (notes or {}).get("rows") or {}, (notes or {}).get("sectors") or {}
    out = {}
    for strategy in ("SWING", "LONG_TERM"):
        ready = sorted((r for r in rows if r.get("strategy") == strategy and r.get("entry_status") == op.ENTRY_READY and r.get("actionability") == "ACTIONABLE" and r.get("score") is not None),
                       key=lambda r: -float(r["score"]))
        out[strategy] = {"total": len(ready), "buy_band": sum(1 for r in ready if float(r["score"]) >= BUY_LINE),
                         "rows": [{"ticker": r["ticker"], "name": r.get("name"), "score": r["score"], "band": r.get("band"), "band_label": r.get("band_label"), "action": r.get("action"),
                                   "confidence": r.get("confidence"),        # shown when LOW: the list had no word on it (assessment 2026-11-25)
                                   "sector": sectors.get(r["ticker"]), **{k: v for k, v in (note_rows.get(f"{r['ticker']}|{strategy}") or {}).items() if k in ("plus", "minus", "prev")}}
                                  for r in ready[:shown]]}
    from terminal.qsf.rank_notes import band_edges
    return {"session": (notes or {}).get("session"), "styles": out, "band_edges": band_edges(),
            "note": "진입 상태가 '지금 진입 가능'(장기는 '진입을 막는 조건 없음')인 종목을 점수순으로 보여 줍니다(주문 계획과 같은 기준). 매수 후보 구간(70점) 아래 종목도 있을 수 있으니 구간을 함께 보세요. 순위일 뿐 매수 신호가 아닙니다."}


def market_clause(state: Optional[Dict[str, Any]]) -> str:
    """The clause the Today first line ends with on an adverse or unreadable day (UI batch 1, user decision 2026-11-23): the line used
    to read "먼저 볼 것은 없습니다" on a day the market state was 15/100.  The levels and the rules are unchanged; only words."""
    if not state:
        return ""
    score, factor = state.get("score_100"), float(state.get("size_factor") or 1.0)
    size = "절반" if abs(factor - 0.5) < 1e-9 else f"{factor:g}배"
    if state.get("state") == "ADVERSE" and score is not None:
        return f" 시장 상태 나쁨({score:.0f}/100)" + (f" — 새 주문 크기 {size} 규칙 적용 중." if factor < 1 else ".")
    if state.get("state") == "UNKNOWN" and factor < 1:
        return f" 시장 상태를 읽을 수 없음 — 새 주문 크기 {size}{'으로' if size == '절반' else '로'} 계산 중."
    return ""


def headline(items: List[Dict[str, Any]]) -> str:
    n = {lv: sum(1 for i in items if i["level"] == lv) for lv in LEVELS}
    if n["ACT"]:
        return f"먼저 볼 것이 {n['ACT']}건 있습니다. 손실과 관련된 항목입니다."
    if n["DUE"]:
        return f"먼저 볼 것은 없습니다. 오늘 챙길 것이 {n['DUE']}건 있습니다."
    return "오늘 따로 챙길 것이 없습니다."


def committee_items(row: Optional[Dict[str, Any]], market: str, session: Optional[str]) -> List[Dict[str, Any]]:
    """The interrupts of the six paper portfolios on the newest recorded session, read from the record's last line (nothing is
    built here: the portfolios are made only by their button and by the daily record).  A fatal exit is told once per stock with
    the portfolios it left; an overweight notice on the day the holding crossed the line."""
    if not row or not session or row.get("session") != session:
        return []
    from terminal.committee import portfolios as cpf
    name = {k: v["name"].replace(" 포트폴리오", "") for k, v in cpf.SPEC.items()}
    gone: Dict[str, Dict[str, Any]] = {}
    out: List[Dict[str, Any]] = []
    for key, p in (row.get("portfolios") or {}).items():
        for n in p.get("fatal") or []:
            g = gone.setdefault(n["ticker"], {"name": n.get("name") or n["ticker"], "why": n.get("why"), "from": []})
            g["from"].append(name.get(key, key))
        for n in p.get("overweight") or []:
            # shown as long as it lasts (user decision 2026-11-23): the position is not cut, so the notice must not vanish after a day.
            # The daily message tells it on the day it crossed the line only.
            risk = " 줄이지 않기로 했으므로 이 포트폴리오의 결과가 이 한 종목에 크게 좌우됩니다."
            out.append(item("DUE" if n.get("new") else "INFO", "IC_INTERRUPT" if n.get("new") else "IC_OVERWEIGHT", f"가상 포트폴리오 알림 · {n['text']}{risk}", n["ticker"], tab="committee",
                            short=f"{name.get(key, key)} {n['ticker']} 비중 {n['weight'] * 100:.0f}%(규칙은 {n['cap'] * 100:.0f}%로 축소)" if n.get("new") else None))
    for t, g in gone.items():
        out.insert(0, item("DUE", "IC_INTERRUPT", f"가상 포트폴리오 알림 · {g['name']}({t})을 {', '.join(g['from'])} 포트폴리오에서 전부 뺐습니다. 이유: {g['why']}. 빠진 몫은 현금으로 둡니다. "
                                                  "가상 포트폴리오의 규칙이 한 일이고 주문이 아닙니다.", t, tab="committee", short=f"{t} 전량 제외({', '.join(g['from'])})"))
    return out


def daily_lines(briefs: List[Dict[str, Any]]) -> List[str]:
    """Three lines for the daily message, both markets on each: market state, the top three, the order plan; and a fourth on
    the days an interrupt of the six paper portfolios fired.  Tickers and counts only: no amount and no quantity leaves the machine."""
    rows: Dict[str, List[str]] = {"시장 상태": [], "스윙 상위 3": [], "주문 계획": [], "가상 포트폴리오 알림": []}
    for brief in briefs:
        if brief.get("status") != "REAL":
            continue
        by: Dict[str, Dict[str, Any]] = {}
        for i in brief["items"]:
            by.setdefault(i["kind"], i)
        where = MARKET_KO[brief["market"]]
        orders = [i["ticker"] for i in brief["items"] if i["kind"] == "ORDER"]
        plan = f"{brief.get('orders') or len(orders)}건({', '.join(orders)}{' 등' if (brief.get('orders') or 0) > len(orders) else ''})" if orders else \
            (by.get("NO_ACCOUNT") or {}).get("short") or ("새 주문 없음" if "NO_ORDERS" in by else None)
        fired = [i["short"] for i in brief["items"] if i["kind"] == "IC_INTERRUPT" and i.get("short")]
        for label, text in (("시장 상태", (by.get("MARKET_ADVERSE") or by.get("MARKET_UNKNOWN") or by.get("MARKET_STATE") or {}).get("short")), ("스윙 상위 3", (by.get("TOP3") or {}).get("short")), ("주문 계획", plan),
                            ("가상 포트폴리오 알림", ", ".join(fired[:4]) + (f" 외 {len(fired) - 4}건" if len(fired) > 4 else "") if fired else None)):
            if text:
                rows[label].append(f"{where} {text}")
    return [f"{label}: " + " · ".join(parts) for label, parts in rows.items() if parts]


# ---------------------------------------------------------------------- the day's list
def candidate_mix(terminal: Any, market: str) -> Optional[str]:
    """The day's swing buy candidates as a group: their sectors and how alike they move (``analyst_extra.concentration``)."""
    from terminal import analyst_extra as ax
    rows = (terminal.qsf.screen_rows(market).get("rows") or [])
    picks = [r for r in rows if r.get("strategy") == "SWING" and (r.get("score") or 0) >= ax.BUY and r.get("actionability") == "ACTIONABLE"]
    if len(picks) < 3:
        return None
    sector = {r["ticker"]: ax.SECTOR_KO.get(r.get("sector"), r.get("sector")) or r.get("industry") for r in picks}
    bench = ax.factor_data(terminal, market).get(ax.FACTORS[market]["market"][0]) or []
    return ax.concentration_line(ax.concentration([r["ticker"] for r in picks], sector.get, terminal.qsf._loader(market), bench))


def marked_items(rows: List[Dict[str, Any]], mine: List[str], market: str, new: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Avoid marks first: on what is held or watched (due), on stocks the score likes (reference), and the marks that are new
    since the record before (``analyst_extra.newly_marked``; due when one is held or watched)."""
    from terminal import analyst_extra as ax
    got = ax.liked_but_marked(rows, mine)
    label = lambda r: f"{r.get('name') or r['ticker']}({r['ticker']}, {', '.join(r['marks'])})"      # noqa: E731
    tested = ("한국의 과거 시험에서 근거가 나온 쪽은 점수가 아니라 이 표시였습니다(자금 조달 공시가 있는 종목은 이후 수익이 부진)." if market == "KR"
              else "미국에서는 이 표시를 수익으로 시험한 적이 없습니다. 참고 표시입니다.")
    out = []
    if got["mine"]:
        out.append(item("DUE", "AVOID_MINE", f"보유·관심 종목 가운데 회피 표시가 붙은 것: {', '.join(label(r) for r in got['mine'][:6])}. {tested}", got["mine"][0]["ticker"], "stock"))
    if got["liked"]:
        names = ", ".join(f"{r.get('name') or r['ticker']}({r['score']:.0f}점, {', '.join(r['marks'])})" for r in got["liked"][:5])
        out.append(item("INFO", "AVOID_LIKED", f"점수는 관심 구간 이상인데 회피 표시가 붙은 종목 {len(got['liked'])}개: {names}" + (" 등" if len(got["liked"]) > 5 else "") + f". {tested}", tab="qsf"))
    new = new or {}
    name_of = {r["ticker"]: r.get("name") or r["ticker"] for r in rows}
    said, fresh = [], set()
    for key, label in (("financing", "자금 조달 공시"), ("high_risk", "고위험")):
        codes = [c for c in new.get(key) or [] if c in name_of]            # only stocks of the scan: the records cover more
        if codes:
            fresh |= set(codes)
            said.append(f"{label} {', '.join(name_of[c] for c in codes[:5])}" + (f" 외 {len(codes) - 5}개" if len(codes) > 5 else ""))
    if said:
        churn = " 고위험은 위험 순위 상위 20%의 경계에 따라 날마다 드나듭니다." if any(c in name_of for c in new.get("high_risk") or []) else ""
        out.append(item("DUE" if fresh & set(mine) else "INFO", "AVOID_NEW", f"직전 기록({new.get('previous') or new.get('risk_previous')}) 뒤 새로 붙은 회피 표시: {'; '.join(said)}.{churn}", tab="qsf"))
    return out


def filing_items(base: Path, at: datetime, market: str) -> List[Dict[str, Any]]:
    """New important filings of held and watched stocks seen by the day's checks (terminal/filing_watch.py).  A fact to read,
    never a score or an order."""
    from terminal import filing_watch
    rows = [r for r in filing_watch.recent(base, at) if r.get("market") == market]
    return [item("DUE", "NEW_FILING", f"새 공시: {r.get('name') or r['ticker']}({r['ticker']}) {r['date']} {r['title']} — {r['label']}. "
                 "공시 사실만 알리며 점수와 판단은 다음 기록에서 정해집니다.", r["ticker"], "stock", short=f"새 공시 {r.get('name') or r['ticker']} {r['label']}")
            for r in rows[:8]]


def briefing(terminal: Any, market: str = "US", now: Optional[Callable[[], datetime]] = None) -> Dict[str, Any]:
    """The day's list for one market.  ``terminal``: terminal.services.Terminal.  Reads only; nothing is stored or sent."""
    if market == "COIN":
        return coin_briefing(terminal, now)
    from terminal import automation
    from terminal.qsf import changes as qsf_changes, readings as qsf_readings
    at = (now or terminal.now)()
    base = Path(terminal.base)
    items: List[Dict[str, Any]] = []
    failed: List[Dict[str, str]] = []
    seen: Dict[str, Any] = {}

    def part(name: str, make: Callable[[], List[Dict[str, Any]]]) -> None:
        try:
            items.extend(make())
        except Exception as exc:                    # one unreadable part never hides the others, and is named
            failed.append({"part": name, "label": PART_KO[name], "error": type(exc).__name__})

    def account() -> List[Dict[str, Any]]:
        book = seen["book"] = terminal.portfolio(market)
        signals = terminal.portfolio_signals(market)["items"] if book.get("holdings") else []
        return holding_items(book, signals, market)

    def plan() -> List[Dict[str, Any]]:
        got = seen["plan"] = terminal.order_plan(market)
        return plan_items(got, market) + stance_items(got.get("stance"), market)

    def market_state() -> List[Dict[str, Any]]:
        state = (seen.get("plan") or {}).get("market_state") or terminal.market_state(market)
        return market_items(state, market)

    def readings() -> List[Dict[str, Any]]:
        rows = qsf_readings.status(base, at.date(), automation.readings_state(base))["readings"]
        fresh = set()
        for r in rows:
            try:
                if r.get("state") == "READ" and at.timestamp() - (base / r["report"]).stat().st_mtime <= FRESH_READING_DAYS * 86400:
                    fresh.add(r["key"])
            except (OSError, KeyError, TypeError):
                pass
        return reading_items(rows, fresh)

    part("account", account)
    part("plan", plan)

    def committee_alerts() -> List[Dict[str, Any]]:
        from terminal.committee import record as crec
        rows = crec.read(base, market)
        return committee_items(rows[-1] if rows else None, market, terminal.qsf.latest(market).get("session"))
    part("committee", committee_alerts)
    part("market", market_state)
    def context() -> List[Dict[str, Any]]:
        seen["overview"] = terminal.overview(market)
        return context_items(seen["overview"], terminal.econ_calendar(market, 7), market)
    part("context", context)
    part("earnings", lambda: earnings_items(terminal.qsf.earnings_upcoming(market, 14)))
    part("alerts", lambda: alert_items(terminal.alerts_view().get("log") or [], at))
    part("job", lambda: job_items(automation.status(base), automation.STEP_NAMES))
    part("filings", lambda: filing_items(base, at, market))
    part("top", lambda: top_items(terminal.qsf.top3(market), market, {r["ticker"] for r in terminal.qsf.latest(market).get("rows") or [] if r.get("deal")}))

    def records() -> List[Dict[str, Any]]:
        # what stopped or is behind (a record, the backup, the Telegram send): it was shown on the lab tab only
        from terminal import record_status
        try:
            found = record_status.build(terminal).get("alerts") or []
        except AttributeError:          # a terminal that cannot report its records (the tests' stand-ins): nothing to add, the lab tab is unchanged
            return []
        return [item("DUE" if a.get("level") == "bad" else "INFO", "RECORD_ALERT", a["text"], tab="lab") for a in found]

    part("job", records)
    def top_still() -> List[Dict[str, Any]]:
        days = (((terminal.qsf.top3(market).get("strategies") or {}).get("SWING") or {}).get("days")) or []
        day = max(days, key=lambda d: d.get("session") or "") if days else {}
        out = []
        for x in day.get("top") or []:
            s = _snap(terminal, {"ticker": x["ticker"], "market": market}, "SWING")
            note = still_note(terminal, s)
            if note:
                out.append(item("INFO", "TOP_PINNED", f"상위 종목 {x.get('name') or x['ticker']}({x['ticker']}): {note}", x["ticker"], "stock"))
        return out

    part("top", top_still)

    def mix() -> List[Dict[str, Any]]:
        line = candidate_mix(terminal, market)
        return [item("INFO", "CANDIDATE_MIX", line, tab="qsf")] if line else []

    def marked() -> List[Dict[str, Any]]:
        mine = [h["ticker"] for h in (seen.get("book") or {}).get("holdings") or []] + [t for t in terminal.watchlist() if not t.startswith("^")]
        from terminal import analyst_extra as ax
        return marked_items(_rows(terminal, market), mine, market, ax.newly_marked(base) if market == "KR" else None)

    def gaps() -> List[Dict[str, Any]]:
        from terminal import analyst_extra as ax
        from terminal.qsf import fund_period
        rows = _rows(terminal, market)
        session = terminal.qsf.latest(market).get("session")
        mine = [h["ticker"] for h in (seen.get("book") or {}).get("holdings") or []] + [t for t in terminal.watchlist() if not t.startswith("^")]
        cands = [r["ticker"] for r in rows if (r.get("score") or 0) >= ax.BUY and r.get("actionability") == "ACTIONABLE"]
        got = ax.fund_gaps(_snaps(terminal, market, session), mine + cands) if session else {"all": 0}
        if not got["all"]:
            return []
        name_of = {r["ticker"]: r.get("name") or r["ticker"] for r in rows}
        listed = ", ".join(f"{name_of.get(x['ticker'], x['ticker'])} {x['annual']:.0f}→{x['trailing']:.0f}점({x['diff']:+.0f})" for x in got["listed"][:6])
        live = "최근 4분기" if fund_period.live_period(base, market) == "TRAILING" else "연간"
        return [item("INFO", "FUND_GAP", f"장기 점수가 재무 기준(연간 → 최근 4분기)에 따라 {ax.GAP:.0f}점 넘게 달라지는 종목이 {got['all']}개입니다(최근 4분기 쪽이 높은 종목 {got['up']}개). "
                     + (f"보유·관심·매수 후보 가운데: {listed}. " if listed else "보유·관심·매수 후보 가운데는 없습니다. ")
                     + f"라이브 점수는 {live} 재무를 읽습니다. 이런 종목은 점수 카드의 참고 점수를 함께 보세요.", tab="qsf")]

    def dividends() -> List[Dict[str, Any]]:
        from terminal import analyst_more as am
        soon = [d for d in terminal.qsf.dividends_upcoming(market, EX_DIVIDEND_DAYS).get("items") or []]
        return [item("DUE" if d.get("held") else "INFO", "EX_DIVIDEND", am.dividend_item_text(d), d["ticker"], "stock") for d in soon]

    def financial_share() -> List[Dict[str, Any]]:
        from terminal import analyst_more as am
        line = am.financial_share_line([r for r in terminal.qsf.screen_rows(market).get("rows") or [] if r.get("strategy") == "LONG_TERM"], BUY_LINE)
        return [item("INFO", "FINANCIAL_SHARE", line, tab="qsf")] if line else []

    part("dividends", dividends)
    part("mix", mix)
    part("mix", financial_share)
    part("marked", marked)
    part("gaps", gaps)

    part("changes", lambda: change_items(qsf_changes.report(terminal.qsf.latest(market), terminal.qsf.ledger, market, "SWING"),
                                         {h["ticker"] for h in (seen.get("book") or {}).get("holdings") or []}))
    part("readings", readings)
    if any(i["kind"] == "TOP3" for i in items):           # the note sits right under the list it is about
        notes = [i for i in items if i["kind"] == "TOP_PINNED"]
        rest = [i for i in items if i["kind"] != "TOP_PINNED"]
        under = next(n for n, i in enumerate(rest) if i["kind"] == "TOP3") + 1
        items = rest[:under] + notes + rest[under:]
    if any(i["kind"] == "NO_ACCOUNT" for i in items):
        items = [i for i in items if i["kind"] != "NO_HOLDINGS"]
    order = {lv: n for n, lv in enumerate(LEVELS)}
    items.sort(key=lambda i: order[i["level"]])          # a stable sort: inside a level the parts keep the order above
    plan_seen = seen.get("plan") or {}
    for i in items:
        if i["kind"] in OPS_KINDS:
            i["ops"] = True
    figures = cands = None
    try:                                                # Today's first row; a stand-in terminal without these simply shows none
        if seen.get("overview") is not None:
            figures = tiles(seen["overview"], market, plan_seen.get("market_state") or terminal.market_state(market))
    except AttributeError:
        pass
    except Exception as exc:
        failed.append({"part": "tiles", "label": "시장 숫자", "error": type(exc).__name__})
    try:
        cands = candidates(terminal.qsf.screen_rows(market).get("rows") or [], terminal.rank_notes(market))
    except AttributeError:
        pass
    except Exception as exc:
        failed.append({"part": "candidates", "label": "오늘의 후보", "error": type(exc).__name__})
    main = [i for i in items if not i.get("ops")]
    try:
        day_state = plan_seen.get("market_state") or terminal.market_state(market)
    except Exception:                                   # a stand-in terminal without it, or no state: the line goes without the clause
        day_state = None
    return {"status": "REAL", "market": market, "generated_at": at.isoformat(timespec="seconds"), "session": plan_seen.get("session"),
            "headline": headline(items), "headline_main": headline(main) + market_clause(day_state), "counts": {lv: sum(1 for i in items if i["level"] == lv) for lv in LEVELS}, "levels": LEVEL_KO,
            "orders": len(plan_seen.get("orders") or []), "items": items, "tiles": figures, "candidates": cands, "unread_parts": failed, "note": NOTE}


# ---------------------------------------------------------------------- questions, read by keyword
STRATEGY_KO = {"SWING": "스윙", "LONG_TERM": "장기"}
ENTRY_KO = {"ENTRY_NOW": "지금 진입 가능 구간", "WAIT_FOR_PULLBACK": "눌림 대기", "WAIT_FOR_BREAKOUT_CONFIRMATION": "돌파 확인 대기", "WAIT_FOR_EARNINGS": "실적 발표 대기",
            "OVERVALUED_AT_CURRENT_PRICE": "현재 가격 고평가", "NO_VALID_ENTRY_SETUP": "유효한 진입 근거 없음"}
LONG_READY = "진입을 막는 조건 없음"


def entry_ko(entry: Optional[str], strategy: Optional[str] = None) -> str:
    """The entry status in Korean.  A long-term ENTRY_NOW is named for what it is: no rule blocks entry (user decision 2026-11-23)."""
    return LONG_READY if entry == "ENTRY_NOW" and strategy == "LONG_TERM" else ENTRY_KO.get(entry, entry or "")


def entry_meaning(entry: Optional[str], strategy: Optional[str] = None) -> str:
    if entry == "ENTRY_NOW" and strategy == "LONG_TERM":
        return "장기 점수가 기준을 넘고 가격이 진입을 막을 만큼 비싸게 읽히지 않는다는 뜻입니다. '지금이 좋은 때'라는 뜻은 아닙니다."
    return ENTRY_MEANING.get(entry, "")


EXIT_KO = {"HOLD": "보유", "HOLD_AND_REVIEW": "보유하며 재검토", "PARTIAL_TAKE_PROFIT": "일부 차익 실현 검토", "REDUCE": "비중 축소 검토", "EXIT": "청산 검토",
           "THESIS_INVALIDATED": "투자 논리 무효", "TIME_STOP_REVIEW": "시간 손절 재평가"}
FACTOR_KO = {"trend_structure": "추세 구조", "relative_strength": "상대 강도", "momentum": "모멘텀", "breakout_volume": "돌파·거래량", "volatility_structure": "변동성 구조",
             "earnings_revenue_quality": "이익·매출의 질", "profitability": "수익성", "balance_sheet": "재무 상태", "cash_flow_quality": "현금흐름의 질", "risk_reward": "손익비",
             "atr_risk": "변동 폭 안정성", "liquidity": "유동성", "drawdown_gap": "낙폭·갭 안정성", "earnings_calendar": "실적 일정", "material_disclosures": "주요 공시",
             "insider_activity": "내부자 거래", "long_trend": "장기 추세", "momentum_persistence": "모멘텀 지속", "valuation": "가치(밸류에이션)", "business_quality": "사업의 질",
             "growth_quality": "성장의 질", "free_cash_flow": "잉여현금흐름", "balance_dilution": "부채·희석 안전성", "financial_resilience": "재무 복원력",
             "downside_drawdown": "하락 방어력", "leverage": "부채 안전성", "governance": "지배구조", "material_events": "주요 사건", "insider_ownership": "내부자 지분",
             "capital_allocation": "자본 배분", "vix_regime": "변동성 지수", "vix_term": "변동성 기간 구조", "credit_spread": "신용 스프레드", "index_trend_breadth": "지수 추세·시장 폭",
             "vkospi_regime": "한국 변동성 지수", "index_trend": "지수 추세", "breadth": "시장 폭", "usdkrw_regime": "원·달러 환율", "credit_liquidity": "신용 스프레드"}
BUY_LINE = 70.0
# (key, an example the screen shows, needs a stock, words that mean it).  Read in this order: the first that fits answers.
# five investor engines and a unified committee (terminal/committee, rules IC-1): asked with a stock for its five opinions and
# the committee's decision.  The six portfolios are a feature of their own, made only when asked for (user decision 2026-11-22);
# without a stock the answer says how to ask.
# "다섯" and "관점" alone are not enough: "장기 관점에서 어때", "다섯 거래일 뒤 범위", "상위 다섯 종목" are other questions
FIVE_WORDS = ("다섯 관점", "다섯관점", "5 관점", "5관점", "다섯 명", "다섯명", "5인", "버핏", "멍거", "그레이엄", "그레리엄", "그레이험", "린치", "드러켄", "거장", "팀 목록", "팀목록")
STOCK_INTENTS = (
    ("STOP", "삼성전자 손절 어디?", ("손절", "목표", "손익비", "익절")),
    ("RANGE", "삼성전자 얼마까지 움직일까?", ("범위", "얼마까지", "예측", "움직", "오를", "내릴", "떨어질")),
    ("EARNINGS", "삼성전자 실적 언제?", ("실적", "발표")),
    ("SELL_CHECK", "삼성전자 팔아야 해?", ("팔", "매도", "정리", "청산")),
    ("BUY_CHECK", "삼성전자 사도 돼?", ("사도", "살까", "사면", "매수", "들어가", "진입", "담아")),
    ("RISK", "삼성전자 위험해?", ("위험", "회피", "공시", "경고", "조심")),
    ("RANK", "삼성전자 몇 등이야?", ("몇 등", "몇등", "순위", "등수")),
    ("WHY", "삼성전자 점수 왜 낮아?", ("왜", "이유", "점수")),
    ("ANALYZE", "삼성전자 분석해 줘", ("분석", "리포트", "의견", "전망", "어때", "평가", "노트", "살펴")),
    ("FIVE", "삼성전자 다섯 관점은?", FIVE_WORDS),         # read before the others: see read_question
    ("PORTFOLIO", "삼성전자 포트폴리오 받아보기", ("포트폴리오",)),
)
PLAIN_INTENTS = (
    ("HELP", "뭘 물어볼 수 있어?", ("도움", "물어볼", "질문 목록", "질문목록", "help", "사용법", "명령어")),
    ("TRUST", "이 점수 믿어도 돼?", ("믿", "신뢰", "근거", "정확", "검증됐")),
    ("COST", "수수료는 얼마로 계산해?", ("수수료", "비용", "세금", "거래세")),
    ("ALERTS", "걸어 둔 알림 뭐 있어?", ("알림",)),
    ("VERDICTS", "판정은 언제 나와?", ("판정", "언제 나와", "검증 결과")),
    ("JOB", "오늘 수집 됐어?", ("수집", "기록 됐", "기록됐", "돌았", "실패", "백업")),
    ("CHANGES", "어제와 뭐가 달라졌어?", ("달라", "변화", "바뀐", "바뀌", "변했")),
    ("MARKET", "시장 상태 어때?", ("시장", "국면", "장세", "분위기", "증시", "급락", "폭락", "떨어", "지수")),
    ("HOLDINGS", "내 보유 종목 괜찮아?", ("보유", "내 종목", "계좌", "포트")),
    ("TOP", "오늘 상위 종목은?", ("상위", "후보", "추천", "뭐 살", "뭘 살", "1등", "1위")),
    ("TODAY", "오늘 뭐 해야 해?", ("오늘", "할 일", "할일", "브리핑", "뭐 해", "뭘 해", "요약")),
)
EXAMPLES = [e for _, e, _ in PLAIN_INTENTS[::-1]] + [e for _, e, _ in STOCK_INTENTS[::-1]]
EXAMPLE_STOCK = {"KR": "삼성전자", "US": "AAPL"}       # the stock the example questions name: one of the market on screen


def example_stock(market: str) -> str:
    return EXAMPLE_STOCK.get(market, EXAMPLE_STOCK["KR"])


def stock_examples(market: str) -> List[str]:
    """The questions that name a stock, written with a stock of the market on screen (a US screen showed 삼성전자)."""
    return [e.replace(EXAMPLE_STOCK["KR"], example_stock(market)) for _, e, _ in STOCK_INTENTS[::-1]]


def examples_for(market: str) -> List[str]:
    return [e for _, e, _ in PLAIN_INTENTS[::-1]] + stock_examples(market)
_SNAPS: Dict[Any, Any] = {}          # one session's snapshots, kept while the ledger does not change


def _rows(terminal: Any, market: str) -> List[Dict[str, Any]]:
    got = terminal.qsf.latest(market)
    return got.get("rows") or [] if got.get("status") == "REAL" else []


def find_stock(text: str, rows_by_market: Dict[str, List[Dict[str, Any]]]) -> Optional[Dict[str, str]]:
    """The scanned stock a line names: a Korean code, a US ticker, or the longest company name written in it."""
    import re
    names: Dict[str, Dict[str, str]] = {}
    tickers: Dict[str, Dict[str, str]] = {}
    for market, rows in rows_by_market.items():
        for r in rows:
            hit = {"ticker": r["ticker"], "market": market, "name": r.get("name") or r["ticker"]}
            tickers[r["ticker"].upper()] = hit
            if r.get("name"):
                names[r["name"].lower()] = hit
    for token in re.findall(r"[0-9][0-9A-Za-z]{5}|[A-Za-z][A-Za-z.\-]{0,9}", text):
        if token.upper() in tickers and (token.isupper() or len(token) >= 3 or token[0].isdigit()):      # 'a' or 'it' in a sentence is not a ticker
            return tickers[token.upper()]
    low = text.lower()
    found = [n for n in names if len(n) >= 2 and n in low]
    if found:
        return names[max(found, key=len)]
    for token in re.findall(r"[a-z]{4,}", low):                 # apple -> Apple Inc.
        first = [h for n, h in names.items() if n.split(" ")[0].strip(",.") == token]
        if len(first) == 1:
            return first[0]
    return None


def read_question(text: str, has_stock: bool) -> Optional[str]:
    low = text.lower()
    if has_stock and "포트폴리오" in low:                    # "삼성전자 포트폴리오 받아보기": asking is the button
        return "PORTFOLIO"
    if any(w in low for w in FIVE_WORDS):                   # "버핏이라면 어때": the five views, before "어때" is read as a note
        return "FIVE" if has_stock else "TEAM"
    if has_stock:
        return next((key for key, _, words in STOCK_INTENTS if any(w in low for w in words)), "ANALYZE")       # a name alone asks for the whole picture
    return next((key for key, _, words in PLAIN_INTENTS if any(w in low for w in words)), None)


def _snaps(terminal: Any, market: str, session: str) -> List[Dict[str, Any]]:
    from terminal.qsf import order_plan as op
    led = terminal.qsf.ledger
    key = (str(terminal.base), market, session, led._index_stamp())
    if key not in _SNAPS:
        _SNAPS.clear()
        _SNAPS[key] = op.session_snaps(led, market, session)
    return _SNAPS[key]


def _snap(terminal: Any, stock: Dict[str, str], strategy: str) -> Optional[Dict[str, Any]]:
    session = terminal.qsf.latest(stock["market"]).get("session")
    return next((s for s in _snaps(terminal, stock["market"], session) if s["ticker"] == stock["ticker"] and s["strategy"] == strategy and s.get("data_date") == session), None) if session else None


def _factors(snap: Dict[str, Any], lowest: bool, n: int = 3) -> str:
    rows = [f for f in snap.get("factors") or [] if f.get("weight") and f.get("normalized") is not None and f.get("scored", True) is not False]
    rows.sort(key=lambda f: f["normalized"], reverse=not lowest)
    return ", ".join(f"{FACTOR_KO.get(f['factor'], f['factor'])} {f['normalized'] * 100:.0f}/100(배점 {f['weight']:g})" for f in rows[:n]) or "없음"


# what each signal measures and the scale it is scored on, in plain words.  The third entry is the scoring line of terminal/qsf/factors.py
# the words were read from: a test checks the line is still there, so the words cannot drift from the code unnoticed.
FACTOR_INFO = {
    "risk_reward": ("목표까지의 이익 여지를 손절까지의 손실 여지로 나눈 값입니다(비용 반영)", "손익비가 1.0 이하면 0점, 3.0 이상이면 100점", 'ramp(lv["reward_risk"], 1.0, 3.0)'),
    "atr_risk": ("하루에 움직이는 폭과 1년 변동성입니다. 클수록 점수가 낮습니다", "하루 변동 폭이 가격의 6% 이상이면 0점·1.5% 이하면 100점, 연 변동성이 70% 이상이면 0점·20% 이하면 100점, 둘의 평균",
                 'ramp(t["atr_pct"], 0.06, 0.015), ramp(t["hist_vol"], 0.70, 0.20)'),
    "liquidity": ("20일 평균 거래대금입니다. 많을수록 사고팔기 쉽습니다", "한국은 10억 원 이하면 0점·500억 원 이상이면 100점, 미국은 2천만 달러 이하면 0점·5억 달러 이상이면 100점",
                  'lo, hi = (1e9, 5e10) if c["market"] == "KR" else (2e7, 5e8)'),
    "drawdown_gap": ("최근 1년에 고점에서 가장 크게 빠진 폭과 60일 안의 가장 큰 갭입니다", "낙폭이 -45% 이하면 0점·-10% 이내면 100점, 갭이 12% 이상이면 0점·1% 이하면 100점, 둘의 평균",
                     'ramp(t["max_drawdown_252"], -0.45, -0.10), ramp(t["max_gap_60"], 0.12, 0.01)'),
    "earnings_calendar": ("다음 실적 발표까지 남은 거래일입니다. 발표가 가까우면 점수가 낮습니다", "2거래일 이내면 0점, 15거래일 이상이면 100점", 'ramp(float(e["sessions"]), 2, 15)'),
    "material_disclosures": ("최근 공시 가운데 긍정·부정으로 분류된 건수입니다", "60점에서 시작해 긍정 1건마다 +10점, 부정 1건마다 -25점", "0.6 + 0.1 * len(pos) - 0.25 * len(neg)"),
    "insider_activity": ("임원 등 내부자의 장내 매수와 매도입니다", "매도만 있으면 0점, 매수만 있으면 100점, 거래가 없으면 50점", "ramp((buy - sell) / gross, -1.0, 1.0)"),
    "earnings_revenue_quality": ("매출·이익이 늘고 있는지와 이익이 현금으로 들어오는지입니다", "매출 성장 -5%~+20%, 주당이익 성장 -10%~+25%, 영업현금/순이익 0.5~1.2배를 각각 0~100점으로 보고 평균. 지금 적자라 주당이익 성장을 계산할 수 없으면 그 수치는 0점, 이익도 영업현금도 0 이하이면 현금 전환도 0점(QSF-1.5.0)",
                                 '_rr(f, "rev_growth", -0.05, 0.20), _eps_growth(f, "eps_growth", -0.10, 0.25), _cash_conversion(f)'),
    "profitability": ("자기자본이익률(ROE)과 영업이익률입니다", "둘 다 0% 이하면 0점·20% 이상이면 100점, 둘의 평균", '_rr(f, "roe", 0.0, 0.20), _rr(f, "op_margin", 0.0, 0.20)'),
    "balance_sheet": ("빚 부담과 단기 지급 능력입니다", "부채/자본이 2.0배 이상이면 0점·0.3배 이하면 100점, 유동비율이 0.8배 이하면 0점·2.0배 이상이면 100점, 둘의 평균(금융업은 자기자본/자산 4%~15%)",
                      '_rr(f, "debt_equity", 2.0, 0.3), ramp(f.get("current_ratio"), 0.8, 2.0)'),
    "cash_flow_quality": ("이익이 현금으로 들어오는 정도와 남는 현금입니다", "영업현금/순이익 0.5~1.2배, 잉여현금흐름 마진 -2%~+15%를 각각 0~100점으로 보고 평균. 이익도 영업현금도 0 이하이면 영업현금/순이익은 0점(QSF-1.5.0)",
                          '_cash_conversion(f), _rr(f, "fcf_margin", -0.02, 0.15)'),
    "trend_structure": ("이동평균선 여섯 조건 중 몇 개를 채웠는지입니다", "종가>200일선, 종가>50일선, 50일선>200일선, 20일선>50일선, 50일선 상승, 200일선 상승 가운데 채운 비율",
                        't["ma20"] > t["ma50"], (t["ma50_slope"] or 0) > 0, (t["ma200_slope"] or 0) > 0]'),
    "relative_strength": ("최근 수익률이 대상 종목 가운데 어느 위치인지입니다", "대상 안에서의 백분위 그대로(가장 약하면 0점, 가장 강하면 100점)", 'return obs(rank, {"percentile": rank, "rel_126": t.get("rel_126")},'),
    "momentum": ("RSI와 MACD로 본 최근 힘입니다", "RSI가 30 이하면 0점·55~65면 100점·85 이상이면 다시 0점, MACD 히스토그램이 가격의 -1% 이하면 0점·+1% 이상이면 100점, 둘의 평균",
                 'rsi_s = None if r is None else (ramp(r, 30, 55) if r < 55 else 1.0 if r <= 65 else ramp(r, 85, 65))'),
    "breakout_volume": ("52주 고점과의 거리, 돌파 여부, 거래량입니다", "52주 고점 대비 -25% 이하면 0점·고점이면 100점(두 번 셈), 여기에 거래량과 갭 점수를 평균", 'dist = ramp(t["dist_high"], -0.25, 0.0)'),
    "volatility_structure": ("볼린저 밴드 폭이 최근 1년 중 얼마나 좁은지입니다", "가장 좁으면 100점, 가장 넓으면 0점", 'None if t["bandwidth_pct"] is None else 1 - t["bandwidth_pct"]'),
    "long_trend": ("종가가 200일 평균보다 얼마나 위인지와 200일 평균의 3개월 기울기입니다", "200일선 대비 -15% 이하면 0점·+15% 이상이면 100점, 기울기 -5% 이하면 0점·+5% 이상이면 100점, 둘의 평균",
                   'pos = ramp(t["close"] / t["ma200"] - 1, -0.15, 0.15)'),
    "momentum_persistence": ("최근 한 달을 뺀 1년 수익률과 오른 달의 비율입니다", "수익률 -10% 이하면 0점·+30% 이상이면 100점, 여기에 오른 달 비율을 평균", 'mean([ramp(t["ret_12_1"], -0.10, 0.30), t["pos_month_share"]])'),
    "valuation": ("이익·자산·현금흐름에 비해 주가가 싼지입니다. 쌀수록 점수가 높습니다", "PER 40배 이상(또는 적자)이면 0점·10배 이하면 100점, PBR 8배 이상이면 0점·1.5배 이하면 100점, 잉여현금흐름 수익률 0% 이하면 0점·7% 이상이면 100점, 셋의 평균(금융업은 PER과 PBR 0.8~2.5배)",
                  '_rr(f, "pb", 8, 1.5), _rr(f, "fcf_yield", 0.0, 0.07)'),
    "business_quality": ("ROE, 영업이익률, 매출총이익률, 흑자를 낸 해의 비율입니다", "ROE 3%~25%, 영업이익률 0%~25%, 매출총이익률 15%~60%를 각각 0~100점으로 보고 흑자 연도 비율과 평균",
                         '_rr(f, "roe", 0.03, 0.25), _rr(f, "op_margin", 0.0, 0.25), _rr(f, "gross_margin", 0.15, 0.60), stable'),
    "growth_quality": ("3년 동안의 매출·주당이익 성장과 최근 매출 성장입니다", "3년 매출 성장 연 -2%~+15%, 3년 주당이익 성장 연 -5%~+20%, 최근 매출 성장 -5%~+20%를 각각 0~100점으로 보고 평균. 지금 적자라 3년 주당이익 성장을 계산할 수 없으면 그 수치는 0점(QSF-1.5.0)",
                       '_rr(f, "rev_cagr3", -0.02, 0.15), _eps_growth(f, "eps_cagr3", -0.05, 0.20), _rr(f, "rev_growth", -0.05, 0.20)'),
    "free_cash_flow": ("남는 현금(잉여현금흐름)의 크기와 꾸준함입니다", "잉여현금흐름 마진 -2% 이하면 0점·18% 이상이면 100점, 여기에 흑자 연도 비율을 평균", '_rr(f, "fcf_margin", -0.02, 0.18), f.get("fcf_years_positive")'),
    "balance_dilution": ("빚 부담과 주식 수가 늘었는지입니다", "부채/자본 2.0배 이상이면 0점·0.3배 이하면 100점, 주식 수가 1년에 5% 이상 늘면 0점·1% 이상 줄면 100점, 둘의 평균", 'dil = ramp(f.get("share_change"), 0.05, -0.01)'),
    "financial_resilience": ("어려운 때를 버틸 재무 여력입니다", "유동비율 0.8~2.0배, 이자보상배율 1.5~10배, 현금/부채 0.05~0.8배를 각각 0~100점으로 보고 평균(금융업은 자기자본/자산 4%~15%)",
                             'ramp(f.get("current_ratio"), 0.8, 2.0), ramp(f.get("interest_cover"), 1.5, 10), ramp(f.get("cash_debt"), 0.05, 0.8)'),
    "downside_drawdown": ("내릴 때의 변동성과 최근 1년 최대 낙폭입니다", "하방 변동성 45% 이상이면 0점·12% 이하면 100점, 낙폭 -50% 이하면 0점·-12% 이내면 100점, 둘의 평균",
                          'ramp(t["downside_vol"], 0.45, 0.12), ramp(t["max_drawdown_252"], -0.50, -0.12)'),
    "leverage": ("자본에 비한 빚의 크기입니다", "부채/자본이 2.5배 이상이면 0점, 0.2배 이하면 100점", '_rr(f, "debt_equity", 2.5, 0.2)'),
    "governance": ("최근 1년의 지배구조 경고 공시입니다", "없으면 80점, 1건마다 -30점", "max(0.0, 0.8 - 0.3 * len(g))"),
    "material_events": ("중요 사건 공시 가운데 긍정·부정으로 분류된 건수입니다", "60점에서 시작해 긍정 1건마다 +10점, 부정 1건마다 -30점", "0.6 + 0.1 * len(pos) - 0.3 * len(neg)"),
    "insider_ownership": ("내부자 지분율과 내부자의 장내 순매수입니다", "지분율 0%면 0점·10% 이상이면 100점, 여기에 순매수 점수를 평균", "mean([ramp(own, 0.0, 0.10), net])"),
    "capital_allocation": ("주식 수 변화와 배당·자사주 환원 여부입니다", "주식 수가 1년에 5% 이상 늘면 0점·2% 이상 줄면 100점, 환원이 있으면 100점·없으면 40점, 둘의 평균", 'ramp(f.get("share_change"), 0.05, -0.02)'),
}
ENTRY_MEANING = {"ENTRY_NOW": "점수와 손익비가 진입 기준을 채웠다는 뜻입니다.", "WAIT_FOR_PULLBACK": "점수는 되지만 지금 가격에서는 손익비가 모자라, 가격이 지지선 쪽으로 내려올 때를 기다린다는 뜻입니다.",
                 "WAIT_FOR_BREAKOUT_CONFIRMATION": "고점 돌파가 거래량과 함께 확인될 때까지 기다린다는 뜻입니다.", "WAIT_FOR_EARNINGS": "실적 발표가 임박해 발표 뒤로 미룬다는 뜻입니다.",
                 "OVERVALUED_AT_CURRENT_PRICE": "사업은 괜찮게 읽히지만 지금 가격이 비싸게 읽힌다는 뜻입니다.", "NO_VALID_ENTRY_SETUP": "점수나 손익비가 진입 기준에 못 미쳐, 지금은 들어갈 근거가 없다는 뜻입니다."}
SHARE_KO = ((0.2, "높은 편"), (0.6, "중간"), (1.01, "낮은 편"))


PINNED_ATR = 0.01          # a day's range under 1% of the price: three US stocks on 2026-11-20 (0.2% to 0.5%), the next lowest 1.7%
_JONG_DIGIT, _JONG_LETTER = set("013678"), set("LMNR")


def josa(word: str, pair: str) -> str:
    """The word with the particle that fits its last sound: josa('삼성전자', '은는') -> '삼성전자는'."""
    last = next((c for c in reversed(word) if c.isalnum()), "")
    if "가" <= last <= "힣":
        closed = (ord(last) - 0xAC00) % 28 != 0
        if pair == "으로로" and (ord(last) - 0xAC00) % 28 == 8:       # a final ㄹ takes 로
            closed = False
    else:
        closed = last in _JONG_DIGIT or last.upper() in _JONG_LETTER
    first, second = (pair[:2], pair[2:]) if pair == "으로로" else (pair[0], pair[1])
    return word + (first if closed else second)


def pinned(snap: Dict[str, Any]) -> Optional[str]:
    """A note when the price has hardly moved: common once a takeover price is set, and it flatters every volatility signal."""
    raw = next((f.get("raw") for f in snap.get("factors") or [] if f.get("factor") == "atr_risk" and isinstance(f.get("raw"), dict)), None) or {}
    atr = raw.get("atr_pct")
    if atr is None or atr >= PINNED_ATR:
        return None
    return (f"최근 하루 변동 폭이 가격의 {atr * 100:.1f}%로 거의 움직이지 않습니다. 인수·합병 가격이 정해진 종목 등에서 흔한 모습입니다. "
            "변동이 작아 위험 요인의 점수가 높게 나오지만 오를 여지도 작을 수 있으니, 최근 공시를 먼저 확인하세요.")


def still_note(terminal: Any, snap: Optional[Dict[str, Any]]) -> Optional[str]:
    """The pinned-price note, with the merger filings of the stored SEC list stated as a fact in place of the guess; the filings
    alone when the price still moves.  US only: the Korean list carries no such form."""
    from terminal import analyst_more as am
    if not snap:
        return None
    note = pinned(snap)
    try:
        deals = terminal.qsf.stored_deals(snap.get("cik"), snap.get("data_date")) if snap.get("market") == "US" and snap.get("cik") else []
    except Exception:
        deals = []
    line = am.deal_line(deals, still=bool(note))
    if line and note:
        return f"{note.split('. ')[0]}. {line} 변동이 작아 위험 요인의 점수가 높게 나옵니다."
    return line or note


def _pc(v: Optional[float], digits: int = 1, sign: bool = False) -> str:
    return "자료 없음" if v is None else f"{v * 100:{'+' if sign else ''}.{digits}f}%"


def _x(v: Optional[float], digits: int = 2) -> str:
    return "자료 없음" if v is None else f"{v:,.{digits}f}배"


NO_EQUITY = 99.0          # terminal/qsf/fundamentals.py stores this as debt over equity when equity is zero or negative: a mark, not a ratio


def _de(v: Optional[float]) -> str:
    return "계산 안 됨(자본이 0 이하)" if v == NO_EQUITY else _x(v)


def _money(v: Optional[float], market: str) -> str:
    if v is None:
        return "자료 없음"
    if market == "KR":
        return f"{v / 1e12:,.2f}조 원" if v >= 1e12 else f"{v / 1e8:,.0f}억 원"
    return f"{v / 1e8:,.1f}억 달러" if v >= 1e8 else f"{v / 1e4:,.0f}만 달러"


def figures(f: Dict[str, Any], snap: Dict[str, Any], market: str) -> str:
    """The stored figures behind one signal, as a sentence.  Only what the ledger holds: a figure it lacks reads '자료 없음'."""
    r, name, close = f.get("raw") if isinstance(f.get("raw"), dict) else {}, f.get("factor"), snap.get("price")
    g = r.get

    def dist(level: Optional[float]) -> str:
        return "" if not level or not close else f"({(level / close - 1) * 100:+.1f}%)"
    if name == "risk_reward":
        return f"목표 {price(g('target'), market)}{dist(g('target'))}, 손절 {price(g('stop'), market)}{dist(g('stop'))}, 왕복 비용 {g('cost_pct', 0):.2f}%를 뺀 손익비 {g('reward_risk', 0):.2f}"
    if name == "atr_risk":
        return f"하루 변동 폭이 가격의 {_pc(g('atr_pct'))}, 연 변동성 {_pc(g('hist_vol'), 0)}"
    if name == "liquidity":
        return f"20일 평균 거래대금 {_money(g('adv_value'), market)}"
    if name == "drawdown_gap":
        return f"최근 1년 최대 낙폭 {_pc(g('max_drawdown_252'))}, 60일 안의 최대 갭 {_pc(g('max_gap_60'))}"
    if name == "earnings_calendar":
        est = ", 과거 발표일로 추정한 날짜" if g("basis") == "ESTIMATE" else ""
        return f"다음 실적 발표 {g('next_earnings')}({g('sessions')}거래일 뒤{est})"
    if name in ("material_disclosures", "material_events"):
        days = f"최근 {g('window_days')}일 " if g("window_days") else ""
        return f"{days}긍정 공시 {g('positive', 0)}건, 부정 공시 {g('negative', 0)}건"
    if name == "insider_activity":
        return f"장내 매수 {g('open_market_buy', 0):,.0f}, 장내 매도 {g('open_market_sell', 0):,.0f}"
    if name == "earnings_revenue_quality":
        return f"매출 성장 {_pc(g('rev_growth'), sign=True)}, 주당이익 성장 {_pc(g('eps_growth'), sign=True)}, 영업현금/순이익 {_x(g('ocf_to_ni'))}"
    if name == "profitability":
        return f"ROE {_pc(g('roe'))}, 영업이익률 {_pc(g('op_margin'))}"
    if name == "balance_sheet":
        return f"자기자본/자산 {_pc(g('equity_assets'))}" if "equity_assets" in r else f"부채/자본 {_de(g('debt_equity'))}, 유동비율 {_x(g('current_ratio'))}"
    if name == "cash_flow_quality":
        return f"영업현금/순이익 {_x(g('ocf_to_ni'))}, 잉여현금흐름 마진 {_pc(g('fcf_margin'))}"
    if name == "trend_structure":
        return f"20일선 {price(g('ma20'), market)}, 50일선 {price(g('ma50'), market)}, 200일선 {price(g('ma200'), market)}, 종가 {price(close, market)}"
    if name == "relative_strength":
        return f"대상 안에서 백분위 {_pc(g('percentile'), 0)}, 지수 대비 6개월 수익 {_pc(g('rel_126'), sign=True)}"
    if name == "momentum":
        return f"RSI {g('rsi', 0):.0f}, MACD 히스토그램이 가격의 {_pc(g('macd_hist_pct'), 2, True)}"
    if name == "breakout_volume":
        return f"52주 고점 대비 {_pc(g('dist_high'), sign=True)}, 20일 고점 돌파 {'예' if g('breakout') else '아니오'}, 거래량이 20일 평균의 {_x(g('volume_ratio'))}"
    if name == "volatility_structure":
        return f"볼린저 밴드 폭이 최근 1년 중 하위 {_pc(g('bandwidth_pct'), 0)} 위치"
    if name == "long_trend":
        gap = f"종가가 200일선보다 {(close / g('ma200') - 1) * 100:+.1f}%, " if close and g("ma200") else ""
        return f"{gap}200일선의 3개월 기울기 {_pc(g('ma200_slope'), sign=True)}"
    if name == "momentum_persistence":
        return f"최근 한 달을 뺀 1년 수익률 {_pc(g('ret_12_1'), sign=True)}, 오른 달 비율 {_pc(g('pos_month_share'), 0)}"
    if name == "valuation":
        fcf = "" if "fcf_yield" not in r else f", 잉여현금흐름 수익률 {_pc(g('fcf_yield'))}"
        return f"PER {_x(g('pe'), 1)}, PBR {_x(g('pb'))}{fcf}"
    if name == "business_quality":
        return f"ROE {_pc(g('roe'))}, 영업이익률 {_pc(g('op_margin'))}, 매출총이익률 {_pc(g('gross_margin'))}, 흑자 연도 비율 {_pc(g('roe_years_positive'), 0)}"
    if name == "growth_quality":
        return f"3년 매출 성장 연 {_pc(g('rev_cagr3'), sign=True)}, 3년 주당이익 성장 연 {_pc(g('eps_cagr3'), sign=True)}, 최근 매출 성장 {_pc(g('rev_growth'), sign=True)}"
    if name == "free_cash_flow":
        return f"잉여현금흐름 마진 {_pc(g('fcf_margin'))}, 흑자 연도 비율 {_pc(g('fcf_years_positive'), 0)}"
    if name == "balance_dilution":
        first = f"자기자본/자산 {_pc(g('equity_assets'))}" if "equity_assets" in r else f"부채/자본 {_de(g('debt_equity'))}"
        return f"{first}, 주식 수 변화 {_pc(g('share_change'), sign=True)}"
    if name == "financial_resilience":
        return f"자기자본/자산 {_pc(g('equity_assets'))}" if "equity_assets" in r else f"유동비율 {_x(g('current_ratio'))}, 이자보상배율 {_x(g('interest_cover'), 1)}, 현금/부채 {_x(g('cash_debt'))}"
    if name == "downside_drawdown":
        return f"하방 변동성 {_pc(g('downside_vol'), 0)}, 최근 1년 최대 낙폭 {_pc(g('max_drawdown_252'))}"
    if name == "leverage":
        return f"부채/자본 {_de(g('debt_equity'))}"
    if name == "governance":
        return "지배구조 경고 공시 없음" if not g("issues") else "경고 공시: " + ", ".join(g("issues")[:3])
    if name == "insider_ownership":
        return f"내부자 지분 {_pc(g('insider_pct'))}"
    if name == "capital_allocation":
        back = "있음" if g("returns_capital") else "없음" if g("returns_capital") is not None else "알 수 없음"
        return f"주식 수 변화 {_pc(g('share_change'), sign=True)}, 배당·자사주 환원 {back}"
    return ""


def breakdown(snap: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The score taken apart: points each counted signal lost and kept.  The score is 100 x sum(points x value) / sum(points of the
    signals with a value), so the lost points add up to 100 minus the score.  None when the stored figures do not rebuild the score."""
    counted = [f for f in snap.get("factors") or [] if f.get("weight") and f.get("scored", True) is not False]
    have = [f for f in counted if f.get("normalized") is not None]
    total = sum(f["weight"] for f in have)
    if not total or snap.get("score") is None:
        return None
    rows = [{**f, "kept": 100 * f["weight"] * f["normalized"] / total, "lost": 100 * f["weight"] * (1 - f["normalized"]) / total} for f in have]
    if abs(sum(r["kept"] for r in rows) - snap["score"]) > 0.05:
        return None
    return {"rows": rows, "total": total, "empty": [f for f in counted if f.get("normalized") is None],
            "reference": [f for f in snap.get("factors") or [] if f.get("scored") is False and f.get("normalized") is not None]}


def _signal_line(f: Dict[str, Any], snap: Dict[str, Any], market: str, points: str, scale: bool = True) -> str:
    """One signal as a sentence: its value, the points, the stored figures, what it measures and (for a loss) the scale."""
    info = FACTOR_INFO.get(f["factor"])
    fig = figures(f, snap, market)
    return (f"{FACTOR_KO.get(f['factor'], f['factor'])} {f['normalized'] * 100:.0f}/100({points})" + (f": {fig}." if fig else ".")
            + (f" {info[0]}." if info else "") + (f" 채점 기준: {info[1]}." if info and scale else ""))


def _standing(terminal: Any, market: str, strategy: str, score: float) -> Dict[str, Any]:
    scored = sorted((r["score"] for r in _rows(terminal, market) if r["strategy"] == strategy and r.get("score") is not None), reverse=True)
    place = 1 + sum(1 for s in scored if s > score)
    share = place / len(scored) if scored else 1.0
    return {"place": place, "of": len(scored), "share": share, "word": next(w for cut, w in SHARE_KO if share <= cut), "buy": sum(1 for s in scored if s >= BUY_LINE),
            "median": scored[len(scored) // 2] if scored else None}


def _share(share: float) -> str:
    """Where a rank sits: the upper half reads from the top, the lower half from the bottom."""
    return f"상위 {max(1, round(share * 100))}%" if share <= 0.5 else f"하위 {max(1, round((1 - share) * 100))}%"


def _bands(score: float) -> List[str]:
    from terminal.qsf import config
    out = []
    above = [(lo, label) for lo, _, label in config.BANDS if lo > score]
    if above:
        lo, label = min(above)
        out.append(f"{lo - score:.1f}점 오르면 '{label}' 구간({lo:g}점 이상)입니다.")
    floor = max(((lo, label) for lo, _, label in config.BANDS if lo <= score), default=None)
    if floor and floor[0] > 0:
        out.append(f"{score - floor[0]:.1f}점 내리면 지금 구간('{floor[1]}')을 벗어납니다.")
    return out


def _basis(snap: Dict[str, Any], market: str) -> str:
    p = snap.get("provenance") or {}
    parts = [f"{snap.get('data_date')} 종가 {price(snap.get('price'), market)}"]
    if p.get("fund_filed"):
        parts.append(f"재무 {p['fund_filed']} 공시분")
    parts.append(f"모델 {snap.get('model_version')}")
    if snap.get("coverage") is not None:
        parts.append(f"데이터 반영률 {snap['coverage'] * 100:.0f}%")
    return "기준: " + " · ".join(parts)


def reply(title: str, summary: str, sections: List[Dict[str, Any]], tab: Optional[str] = None, follow: Optional[List[str]] = None, basis: Optional[str] = None) -> Dict[str, Any]:
    """An answer: the conclusion first, then titled groups of lines.  ``lines`` is the same thing flat."""
    sections = [{"title": s["title"], "lines": [x for x in s["lines"] if x]} for s in sections if any(s["lines"])]
    return {"title": title, "summary": summary, "sections": sections, "lines": [summary] + [x for s in sections for x in s["lines"]], "tab": tab, "follow": follow or [], "basis": basis}


def _others(name: str, skip: str, strategy: str) -> List[str]:
    """What to ask next about the same stock: the other fixed questions, with its name written in."""
    tail = " 장기" if strategy == "LONG_TERM" else ""
    asks = {"ANALYZE": f"{name} 분석해 줘", "WHY": f"{name}{tail} 점수 왜 이래?", "BUY_CHECK": f"{name}{tail} 사도 돼?", "STOP": f"{name}{tail} 손절 어디?", "RISK": f"{name} 위험해?", "RANGE": f"{name} 얼마까지 움직일까?",
            "EARNINGS": f"{name} 실적 언제?", "RANK": f"{name}{tail} 몇 등이야?", "SELL_CHECK": f"{name} 팔아야 해?", "FIVE": f"{name} 다섯 관점은?", "PORTFOLIO": f"{name} 포트폴리오 받아보기"}
    order = {"ANALYZE": ("WHY", "BUY_CHECK", "STOP", "RANGE"), "WHY": ("ANALYZE", "BUY_CHECK", "STOP", "RISK"), "BUY_CHECK": ("ANALYZE", "WHY", "STOP", "RISK"), "STOP": ("RANGE", "BUY_CHECK", "RISK"), "RISK": ("WHY", "STOP", "RANGE"),
             "RANGE": ("STOP", "RISK", "WHY"), "EARNINGS": ("BUY_CHECK", "WHY"), "RANK": ("WHY", "BUY_CHECK"), "SELL_CHECK": ("WHY", "STOP", "RISK"), "FIVE": ("PORTFOLIO", "ANALYZE", "WHY"), "PORTFOLIO": ("FIVE", "ANALYZE", "RISK")}
    out = [asks[k] for k in order.get(skip, ()) if k != skip]
    if skip == "WHY":
        out.insert(0, f"{name} 점수 왜 이래?" if strategy == "LONG_TERM" else f"{name} 장기 점수 왜 이래?")
    return out


# the ratios the sector comparison reads: (label, unit, digits, True when higher is better)
RATIO_INFO = {"pe": ("PER", "배", 1, False), "pb": ("PBR", "배", 2, False), "fcf_yield": ("잉여현금흐름 수익률", "%", 1, True), "op_margin": ("영업이익률", "%", 1, True),
              "roe": ("ROE", "%", 1, True), "rev_cagr3": ("3년 매출 성장(연)", "%", 1, True), "debt_equity": ("부채/자본", "배", 2, False)}
MIN_PEERS = 5
NOTE_LIMITS = ["증권사 추정치(컨센서스)는 야후가 모은 지금 값만 참고로 보여 주고 점수에는 쓰지 않습니다. 경영진의 전망과 뉴스의 뜻은 읽지 않습니다. 저장된 가격·재무·공시 분류로 쓴 노트입니다.",
               "업종 안에서의 위치는 스캔 대상 종목끼리의 비교이고, 미래 수익으로 검증된 것이 아닙니다.",
               "점수가 높은 종목의 수익이 더 좋았다는 근거는 아직 확인되지 않았습니다. 투자 자문이 아닙니다."]


def _middle(vals: List[float]) -> float:
    """The median of a sorted list; with an even count the mean of the two middle values, so no stock is its own median."""
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2


def sector_lines(peers: Dict[str, Any], ticker: str) -> List[str]:
    """Each ratio beside the scanned stocks of the same industry: the median and where this stock stands, best side first."""
    rows = peers.get("peers") or []
    me = next((p for p in rows if p.get("ticker") == ticker), None)
    if peers.get("status") != "REAL" or me is None:
        return []
    out = []
    for key, (label, unit, digits, high) in RATIO_INFO.items():
        mine = (me.get("ratios") or {}).get(key)
        # a company with no equity carries the mark 99 for debt over equity: it is not a ratio, so it enters neither the median nor the rank
        vals = sorted(v for v in ((p.get("ratios") or {}).get(key) for p in rows) if v is not None and not (key == "pe" and v <= 0) and not (key == "debt_equity" and v == NO_EQUITY))
        if mine is None or len(vals) < MIN_PEERS:
            continue
        if key == "debt_equity" and mine == NO_EQUITY:
            out.append(f"{label}: 자본이 0 이하라 계산되지 않습니다(업종 중앙값 {_middle(vals):.{digits}f}배). 빚이 자본보다 많다는 뜻이라 좋은 쪽이 아닙니다.")
            continue
        if key == "pe" and mine <= 0:
            out.append(f"{label}: 적자라 계산되지 않습니다(업종 중앙값 {_middle(vals):.{digits}f}배).")
            continue
        scale = 100 if unit == "%" else 1
        med = _middle(vals)
        place = 1 + sum(1 for v in vals if (v > mine if high else v < mine))
        side = "보다 높습니다" if mine > med else "보다 낮습니다" if mine < med else "와 같습니다"
        good = (mine > med) == high and mine != med
        out.append(f"{label} {mine * scale:.{digits}f}{unit}: 업종 중앙값 {med * scale:.{digits}f}{unit}{side}. {len(vals)}종목 중 좋은 쪽에서 {place}위"
                   + ("(업종보다 나은 쪽)." if good else "(업종보다 못한 쪽)." if mine != med else "."))
    return out


def _grade(peers: Dict[str, Any], strategy: str, part: str = "SCORE") -> Optional[str]:
    g = (((peers.get("grades") or {}).get(strategy) or {}).get(part) or {})
    return None if not g.get("grade") else f"{g['grade']}(업종 {g.get('n')}종목 중 상위 {max(1, round((1 - g['percentile']) * 100))}%)"


def key_lines(rows: Dict[str, Dict[str, Any]], base: Dict[str, Any], changes: List[Dict[str, Any]], gates: List[str], marks: List[str], still: Optional[str],
              down: List[Dict[str, Any]], market: str) -> List[str]:
    """The note in three lines, each made by a fixed rule: where the scores stand, what changed since the last record (and how far
    fresher statements would move the score), and the first risk that applies, in a fixed order."""
    from terminal import analyst_extra as ax
    scores = [f"{STRATEGY_KO[s]} {rows[s]['score']:.1f}점('{rows[s].get('band_label')}')" for s in ("LONG_TERM", "SWING") if rows.get(s) and rows[s].get("score") is not None]
    first = "점수: " + ", ".join(scores) + "." if scores else "점수: 최신 기록에 점수가 없습니다."
    if changes:
        c = changes[0]
        top = max(((d, v) for d, v in c["domains"].items() if d != "REGIME" and abs(v) >= 3), key=lambda kv: abs(kv[1]), default=None)
        second = f"달라진 것: {c['label']} 기록보다 {c['diff']:+.1f}점" + (f"(가장 크게 바뀐 영역: {ax.DOMAIN_KO.get(top[0], top[0])} {top[1]:+.0f})" if top else "") + "."
    else:
        second = "달라진 것: 비교할 지난 기록이 아직 없습니다."
    fp = base.get("fund_period") or {}
    a, t = fp.get("annual") or {}, fp.get("trailing") or {}
    gap = t["score"] - a["score"] if a.get("score") is not None and t.get("score") is not None and t.get("newer_quarter") else None
    if gap is not None and abs(gap) >= ax.GAP:
        second += f" 재무 기준이 {a.get('fiscal_end')}까지의 연간 보고서이고, 최근 4분기 재무로는 {STRATEGY_KO[base['strategy']]} {t['score']:.1f}점({gap:+.1f})입니다."
    if gates:
        third = f"먼저 볼 위험: 차단 조건 {len(gates)}건({gates[0]})."
    elif marks:
        third = f"먼저 볼 위험: 회피 표시({', '.join(marks)})."
    elif still:
        third = "먼저 볼 위험: 가격이 거의 움직이지 않는 종목입니다(인수·합병 가격이 정해졌을 수 있음). 공시를 먼저 확인하세요."
    elif down:
        r = down[0]
        third = f"먼저 볼 위험: 점수를 가장 많이 깎는 것은 {FACTOR_KO.get(r['factor'], r['factor'])}입니다({r['normalized'] * 100:.0f}/100, -{r['lost']:.1f}점)."
    else:
        third = "먼저 볼 위험: 걸린 차단 조건과 회피 표시가 없습니다. 안전하다는 뜻은 아닙니다."
    return [first, second, third]


def analyst_note(terminal: Any, stock: Dict[str, str], rows: Dict[str, Dict[str, Any]], follow: List[str]) -> Dict[str, Any]:
    """One stock the way an analyst's note is laid out: the view, valuation beside the sector, the business, the balance sheet,
    price, catalysts, risks, scenarios and what would change the view.  Every figure is one the scan stored; nothing is forecast."""
    from terminal.qsf import config
    market, ticker, name = stock["market"], stock["ticker"], stock["name"]
    swing, long_ = _snap(terminal, stock, "SWING"), _snap(terminal, stock, "LONG_TERM")
    base = long_ or swing
    head = f"{name}({ticker})"
    if base is None:
        return reply(f"{head} 분석 노트", f"{name}의 점수 기록이 최신 기록에 없어 노트를 쓰지 못했습니다.", [{"title": "할 수 있는 것", "lines": ["종목 탭에서 조회하면 그 자리에서 평가합니다."]}], "stock")
    close = base.get("price")
    try:
        peers = terminal.qsf.peers(ticker, market)
    except Exception:
        peers = {}
    by = lambda s: {f["factor"]: f for f in (s or {}).get("factors") or []}      # noqa: E731
    fs, fl = by(swing), by(long_)

    def fig(table: Dict[str, Any], key: str, snap: Optional[Dict[str, Any]]) -> str:
        f = table.get(key)
        return "" if not f or f.get("normalized") is None or snap is None else f"{FACTOR_KO[key]} {f['normalized'] * 100:.0f}/100: {figures(f, snap, market)}."

    # the view: what the program reads, never a call of its own
    views = []
    for strat, r in (("SWING", rows.get("SWING")), ("LONG_TERM", rows.get("LONG_TERM"))):
        if r and r.get("score") is not None:
            st = _standing(terminal, market, strat, float(r["score"]))
            grade = _grade(peers, strat)
            views.append(f"{STRATEGY_KO[strat]} {r['score']:.1f}점('{r.get('band_label')}', 판단 '{r.get('action_label')}', {st['of']}종목 중 {st['place']}위" + (f", 업종 등급 {grade}" if grade else "") + ")")
    group = f"{peers.get('group')} 업종" if peers.get("group") else "업종 정보 없음"
    summary = f"{name}({group}): 프로그램이 읽는 것은 " + " · ".join(views) + "입니다. 아래는 그 근거를 애널리스트 노트의 순서로 정리한 것입니다."

    sections: List[Dict[str, Any]] = []
    still = still_note(terminal, swing or base)
    if still:
        sections.append({"title": "먼저 알아 둘 것", "lines": [still]})
    # the debate: what holds the long-term score up and what drags it
    parts = breakdown(long_) if long_ else None
    down: List[Dict[str, Any]] = []
    if parts:
        up = sorted((r for r in parts["rows"] if r["kept"] >= 0.5 and r["normalized"] >= 0.6), key=lambda r: -r["kept"])[:3]
        down = sorted((r for r in parts["rows"] if r["lost"] >= 0.5 and r["normalized"] < 0.5), key=lambda r: -r["lost"])[:3]
        sections.append({"title": "핵심 논점 (장기 점수 기준)", "lines": [f"받치는 것: {_signal_line(r, long_, market, f'{r['kept']:.1f}점', scale=False)}" for r in up]
                         + [f"깎는 것: {_signal_line(r, long_, market, f'-{r['lost']:.1f}점', scale=False)}" for r in down]})
    from terminal import analyst_extra as ax
    try:                    # what changed since the notes of a week and a month ago, from the ledger's light records
        changes = ax.change_since(terminal.qsf.ledger, market, ticker, base["strategy"])
        moved = ax.change_lines(changes, {code: label for _, code, label in config.BANDS}.get)
    except Exception:
        changes, moved = [], []
    sections.append({"title": f"지난 기록 이후 달라진 것 ({STRATEGY_KO[base['strategy']]} 점수)", "lines": moved or ["비교할 지난 기록이 아직 없습니다(1주 전 기록부터 비교합니다)."]})
    sector = sector_lines(peers, ticker)
    one_month = next((p.get("change_1m") for p in peers.get("peers") or [] if p.get("ticker") == ticker), None)
    moves = sorted(p["change_1m"] for p in peers.get("peers") or [] if p.get("change_1m") is not None)
    if one_month is not None and len(moves) >= MIN_PEERS:
        mid = moves[len(moves) // 2]
        sector.append(f"최근 한 달 주가 {one_month * 100:+.1f}%: 업종 중앙값 {mid * 100:+.1f}%" + ("와 비슷합니다." if abs(one_month - mid) < 0.005 else "보다 나았습니다." if one_month > mid else "보다 부진했습니다."))
    from terminal import analyst_more as am
    raw_of = lambda key: (fl.get(key) or {}).get("raw") if isinstance((fl.get(key) or {}).get("raw"), dict) else {}      # noqa: E731
    try:                    # today's ratios inside the stock's own range over the stored prices (reference)
        own_range = am.valuation_lines(am.valuation_history(terminal.qsf._loader(market)(ticker), terminal.qsf.stored_annual(ticker, market, base.get("cik")),
                                                            raw_of("valuation").get("pe"), raw_of("valuation").get("pb"), raw_of("balance_dilution").get("share_change")))
    except Exception:
        own_range = []
    sections.append({"title": f"밸류에이션과 업종 안에서의 위치 ({peers.get('group') or '업종'} {len(peers.get('peers') or [])}종목)",
                     "lines": (sector or ["같은 업종의 스캔 종목이 모자라 비교하지 못했습니다."]) + own_range})
    try:                    # what the market expects, as Yahoo's stored record states it (reference; recorded apart for later)
        from terminal.qsf import expectations
        expected = expectations.lines(terminal.qsf.stored_info(ticker, market), close, market, date.fromisoformat(base["data_date"]))
    except Exception:
        expected = []
    if expected:
        sections.append({"title": "시장의 기대 (야후 집계, 참고)", "lines": expected})
    try:
        aged = ax.fund_age_lines(base, base["data_date"])
    except Exception:
        aged = []
    sections.append({"title": "실적과 이익의 질", "lines": aged + [fig(fl, "growth_quality", long_), fig(fl, "business_quality", long_), fig(fs, "earnings_revenue_quality", swing), fig(fl, "free_cash_flow", long_),
                                                    fig(fs, "cash_flow_quality", swing)]})
    sections.append({"title": "재무 건전성", "lines": [fig(fl, "financial_resilience", long_), fig(fs, "balance_sheet", swing), fig(fl, "leverage", long_), fig(fl, "balance_dilution", long_),
                                                 fig(fl, "capital_allocation", long_)]})
    sections.append({"title": "가격과 수급", "lines": [fig(fl, "long_trend", long_), fig(fs, "relative_strength", swing) or fig(fl, "relative_strength", long_), fig(fs, "breakout_volume", swing), fig(fs, "momentum", swing),
                                                 fig(fs, "atr_risk", swing), fig(fs, "liquidity", swing)]})
    try:                    # what the price has moved with: the market, a theme beyond the market, a rate or a currency
        data, extra = dict(ax.factor_data(terminal, market)), []
        own = ax.own_sector(terminal, market, next((r for r in terminal.qsf.screen_rows(market).get("rows") or [] if r.get("ticker") == ticker), None))
        if own and own[2]:
            data[own[0]] = own[2]
            extra.append((own[0], own[1], "RETURN"))
        rate = ax.kr_yield(terminal) if market == "KR" else []
        if rate:
            data[ax.KR_YIELD[0]] = rate
            extra.append(ax.KR_YIELD)
        moves_with = ax.exposure_lines(ax.exposure(terminal.qsf._loader(market)(ticker), data, market, extra=extra))
    except Exception:
        moves_with = []
    sections.append({"title": "무엇과 같이 움직였나 (노출)", "lines": moves_with or ["기준 지수 자료를 받지 못해 계산하지 못했습니다."]})
    # catalysts: dates the program holds, never a guess at what they will bring
    raw = (fs.get("earnings_calendar") or {}).get("raw") if isinstance((fs.get("earnings_calendar") or {}).get("raw"), dict) else {}
    cat = []
    if raw.get("next_earnings"):
        cat.append(f"다음 실적 발표 {raw['next_earnings']}({raw.get('sessions')}거래일 뒤" + (", 과거 발표일로 추정)." if raw.get("basis") == "ESTIMATE" else ")."))
    else:
        cat.append("다음 실적 발표일이 저장돼 있지 않습니다.")
    cat += [fig(fs, "material_disclosures", swing), fig(fl, "governance", long_)]
    try:
        for e in macro_dates(terminal.econ_calendar(market, 14).get("items") or [], market)[:3]:
            cat.append(f"거시 일정: {e.get('name')} {e.get('date_kst') or e.get('date')}({e.get('days_away')}일 뒤).")
    except Exception:
        pass
    try:                    # how the price moved around past results announcements: stored dates, stored prices
        days, basis = terminal.qsf._past_result_dates(market, base["data_date"], ticker if market == "KR" else None, base.get("cik"))
        bench = ax.factor_data(terminal, market).get(ax.FACTORS[market]["market"][0]) or []
        cat += am.reaction_lines(am.reactions(terminal.qsf._loader(market)(ticker), days, bench), basis)
    except Exception:
        pass
    sections.append({"title": "촉매와 일정", "lines": cat})
    # risks
    row = rows.get("SWING") or rows.get("LONG_TERM") or {}
    gates = sorted({g.get("text") or g.get("code") for s in (swing, long_) if s for g in s.get("gates") or []})
    risk = [f"차단 조건: {g}." for g in gates]
    if row.get("high_risk"):
        risk.append("고위험 표시: 변동성과 낙폭이 대상 가운데 나쁜 쪽입니다.")
    if (row.get("filing_events") or {}).get("financing"):
        risk.append("자금 조달 공시: 한국의 과거 시험에서 이런 종목은 이후 수익이 부진했습니다.")
    risk += [fig(fs, "drawdown_gap", swing), fig(fl, "downside_drawdown", long_)]
    try:
        state = terminal.market_state(market)
        if state.get("score_100") is not None:
            risk.append(f"시장 상태 {state['score_100']:.0f}/100({state.get('label')}): 종목과 무관하게 시장 전체가 받는 위험입니다.")
    except Exception:
        pass
    sections.append({"title": "위험", "lines": risk or ["걸린 차단 조건과 회피 표시가 없습니다. 안전하다는 뜻은 아닙니다."]})
    # scenarios: the stored cases and ranges, with their assumptions
    scen = []
    cases = ((long_ or {}).get("holding") or {}).get("scenarios") or {}
    for c in cases.get("cases") or []:
        if c.get("price") and close:
            scen.append(f"{c.get('case')}: {c.get('assumption')} → 1년 뒤 {price(c['price'], market)}(지금 대비 {(c['price'] / close - 1) * 100:+.1f}%).")
    if scen:
        scen.append(f"계산법: {cases.get('method')}")
    try:
        from terminal.qsf import forecast
        got = forecast.stock(terminal.base, market, ticker)
        r20 = (got.get("ranges") or {}).get("20")
        if got.get("status") == "REAL" and r20 and got.get("close"):
            scen.append(f"20거래일 뒤 종가의 80% 범위: {price(r20['p80'][0], market)} ~ {price(r20['p80'][1], market)}"
                        f"({(r20['p80'][0] / got['close'] - 1) * 100:+.1f}% ~ {(r20['p80'][1] / got['close'] - 1) * 100:+.1f}%). 방향은 말하지 않는 범위입니다.")
    except Exception:
        pass
    if swing and swing.get("stop"):
        entry = swing.get("entry_status")
        scen.append(f"스윙 계획의 손절 {price(swing['stop'], market)}, 목표 {price(swing.get('target'), market)}, 손익비 {((swing.get('holding') or {}).get('reward_risk') or 0):.2f}."
                    + (f" 진입 판단은 '{ENTRY_KO.get(entry, entry)}'입니다. {ENTRY_MEANING.get(entry, '')}".rstrip() if entry else ""))
    sections.append({"title": "시나리오", "lines": scen})
    # what would change the view
    hold = (long_ or {}).get("holding") or {}
    change = (_bands(float(rows["LONG_TERM"]["score"])) if rows.get("LONG_TERM") and rows["LONG_TERM"].get("score") is not None else []) \
        + [f"장기 보유 논리가 깨지는 조건: {x}." for x in (hold.get("invalidation") or [])[:3]] + [f"다음 실적에서 볼 것: {x}." for x in (hold.get("milestones") or [])[:3]]
    sections.append({"title": "견해가 바뀌는 조건", "lines": change})
    try:                    # five investor engines and the committee (reference; never the people's own opinion, never scored)
        from terminal.committee import service as cs
        five = cs.stock(terminal, ticker, market)
        if five["status"] == "OK" and five["committee"]["valid"]:          # nothing to add when no view could judge
            sections.append({"title": "다섯 투자자와 투자위원회 (참고)", "lines": committee_lines(five) + [f"투자위원회: {five['committee']['decision_ko']}. {five['committee']['thesis']}", five["note"]]})
    except Exception:
        pass
    sections.append({"title": "이 노트의 한계", "lines": NOTE_LIMITS})
    try:                    # a bank has no gross margin: "not applicable" in place of "no data", and why its score reads differently
        mine = next((r for r in terminal.qsf.screen_rows(market).get("rows") or [] if r.get("ticker") == ticker), None) or {}
        if am.is_financial(mine.get("sector")):
            for sec in sections:
                sec["lines"] = [am.financial_wording(x) for x in sec["lines"]]
                if sec["title"].startswith("밸류에이션"):
                    sec["lines"] = sec["lines"] + [am.FINANCIAL_NOTE]
    except Exception:
        pass
    sections.insert(0, {"title": "핵심 세 줄", "lines": key_lines(rows, base, changes, gates, ax.marks_of(row), still, down, market)})
    return reply(f"{head} 분석 노트", summary, sections, "stock", follow, _basis(base, market))


def committee_lines(view: Dict[str, Any]) -> List[str]:
    """The five opinions in one line each, as the note and the answers write them."""
    return [f"{o['name']}({o['philosophy']}) {o['recommendation_ko']}" + ("" if o["score"] is None else f", 점수 {o['score']:.0f}, 신뢰 {o['confidence']}") + f": {o['opinion']}" for o in view["investors"]]


def five_answer(terminal: Any, stock: Dict[str, str], follow: List[str]) -> Dict[str, Any]:
    """Five investor engines and the unified committee on one stock (terminal/committee, rules IC-1): rule results, not advice."""
    from terminal.committee import service as cs
    view = cs.stock(terminal, stock["ticker"], stock["market"])
    head = f"{stock['name']}({stock['ticker']})"
    if view["status"] != "OK":
        return reply(f"{head} 다섯 투자자와 투자위원회", view["reason"], [], "qsf", follow)
    c = view["committee"]
    snap = _snap(terminal, stock, "LONG_TERM") or _snap(terminal, stock, "SWING")
    sc = c["scores"]
    scores = ", ".join(f"{c['score_labels'][k]} {'자료 없음' if sc[k] is None else f'{sc[k]:.0f}'}" for k in ("attractiveness", "confidence", "agreement", "quality", "valuation", "growth", "regime", "downside", "data"))
    return reply(f"{head} 다섯 투자자와 투자위원회", f"투자위원회 판정: {c['decision_ko']}. {c['reasons'][0] if c['reasons'] else ''}",
                 [{"title": "다섯 투자자의 의견", "lines": committee_lines(view)},
                  {"title": "투자위원회가 그렇게 정한 이유", "lines": c["reasons"] + [c["thesis"]]},
                  {"title": "의견이 갈린 곳", "lines": [f"{d['kind_ko']}: {d['text']}" for d in c["disagreements"]]},
                  {"title": "따로 본 위험", "lines": [f"{'중대' if r['level'] == 'CRITICAL' else '주요'} 위험, {r['name']}: {r['text']}({r['raised_by']}의 관심사)" for r in c["material_risks"]]},
                  {"title": "들어갈 조건과 나올 조건", "lines": [f"들어갈 조건, {x}" for x in c["entry_conditions"]] + [f"나올 조건, {x}" for x in c["exit_conditions"]]},
                  {"title": "위원회의 아홉 점수(합치지 않음)", "lines": [scores]},
                  {"title": "이 답의 한계", "lines": [view["note"]]}], "qsf", follow, _basis(snap, stock["market"]) if snap else None)


def portfolio_answer(terminal: Any, stock: Dict[str, str], follow: List[str]) -> Dict[str, Any]:
    """Asking is the button: the six portfolios are made now, and the answer says where this stock is in each."""
    from terminal.committee import service as cs
    p = cs.stock_in_portfolios(terminal, stock["ticker"], stock["market"])
    head = f"{stock['name']}({stock['ticker']})"
    if p["status"] != "OK":
        return reply(f"{head} 여섯 포트폴리오", p["reason"], [], "committee", follow)
    inside = [x for x in p["places"] if x["in"]]
    summary = (f"{stock['name']}: 여섯 포트폴리오 가운데 {len(inside)}곳에 듭니다(" + ", ".join(f"{x['name']} {x['weight'] * 100:.1f}%" for x in inside) + ")." if inside
               else f"{stock['name']}: 여섯 포트폴리오 어디에도 들지 않습니다. 이유는 아래에 관점마다 적었습니다.")
    ports = [f"{q['name']}: {q['count']}종목, 현금 {q['cash'] * 100:.0f}%. " + (", ".join(f"{r['name']} {r['weight'] * 100:.1f}%" for r in q["holdings"][:5]) + (" 등" if q["count"] > 5 else "") if q["holdings"] else (q["cash_reasons"] or ["종목 없음"])[0])
             for q in p["portfolios"]]
    return reply(f"{head} 여섯 포트폴리오", summary,
                 [{"title": "이 종목의 자리", "lines": [f"{x['name']}: {'편입 ' + format(x['weight'] * 100, '.1f') + '%' if x['in'] else '없음'}. {x['why']}" for x in p["places"]]},
                  {"title": "여섯 포트폴리오(지금 만든 것)", "lines": ports},
                  {"title": "이 포트폴리오의 한계", "lines": [f"{p['session']} 스캔 기록으로 지금 만들었습니다. 전체 종목과 비중은 '투자위원회' 탭의 '여섯 포트폴리오 받아보기'에서 봅니다.",
                                                   "주문을 내지 않는 가상 포트폴리오입니다. 금액과 수량은 계산하지 않습니다.", p["note"]]}], "committee", follow)


# ---------------------------------------------------------------------- '사도 돼?': 결론 먼저 (사용자 결정 2026-11-24)
# 점검표만 보여 주던 답을, 프로그램이 이미 쓰는 규칙으로 내린 결론 하나로 시작합니다.  새 계산은 없습니다: 차단 조건, 회피 표시,
# 관찰 기준(구간 경계 55점), 지금 고른 성향의 후보 판정(stance.judge, 순위표의 '성향 후보'와 같은 함수), 기록된 진입 판단을 읽기만 합니다.
#   사지 않음: 차단 조건 · 회피 표시 · 실행 대상 아님 · 관찰 기준 미만 · 유효한 진입 근거 없음
#   기다림:   성향 후보가 아님(선 미달, 신뢰도, 큰 움직임) · 눌림/돌파 확인/실적 대기 · 지금 가격에서 비쌈 · 스윙 실적 임박
#             · 신뢰도 낮음(어느 성향이든, 2026-11-25 결정) · 빠진 자료 때문에 구간을 낮춘 종목(2026-11-25 결정)
#             · 재무 점검이 '값은 싼데 나빠지는 중'이거나 ROE 급락으로 읽은 종목(2026-11-25 결정, 진입 상태와 주문 계획은 그대로)
#   사도 됨:  위에 걸린 것이 없고 진입 판단이 '지금 진입 가능'
# 나쁜 날(미국)은 결론을 바꾸지 않고 '크기 절반'을 덧붙입니다(2026-11-16 결정과 같음).  점수와 기록은 바뀌지 않습니다.
VERDICT_KO = {"OK": "사도 됨", "WAIT": "기다림", "NO": "사지 않음"}
VERDICT_CAVEAT = "프로그램 규칙이 내린 결론입니다. 점수가 높은 종목의 수익이 더 좋았다는 근거는 아직 확인되지 않았고, 주문은 직접 정합니다."


def _falling(fc: Optional[Dict[str, Any]]) -> Optional[str]:
    """The line of the figures' check (terminal/fund_checks.py) that makes the buy check wait: the cheap-and-worsening pattern,
    or the ROE fall the holding rule reads as a broken thesis.  None otherwise."""
    fc = fc or {}
    roe = next((x["text"] for x in fc.get("flags") or [] if x.get("code") == "ROE_DOWN"), None)
    if fc.get("pattern") == "CHEAP_AND_WORSENING":
        return fc.get("pattern_ko") or roe
    return roe


def pullback_zone(snap: Dict[str, Any]) -> Optional[List[float]]:
    """The swing rule's waiting zone around the 20-day line (terminal/qsf/holding.py ``_zone(pull, atr, 0.5)``), rebuilt from the
    values the record kept: the 20-day line and the daily range as a share of the price.  None when either is missing."""
    from terminal.qsf import holding
    raw = {f.get("factor"): f.get("raw") for f in snap.get("factors") or [] if isinstance(f.get("raw"), dict)}
    ma20, atr_pct, price = (raw.get("trend_structure") or {}).get("ma20"), (raw.get("atr_risk") or {}).get("atr_pct"), snap.get("price")
    if not ma20 or not atr_pct or not price:
        return None
    z = holding._zone(float(ma20), float(atr_pct) * float(price), 0.5)
    return [z["low"], z["high"]] if z else None


def buy_verdict(snap: Dict[str, Any], strategy: str, market: str, *, gates: List[str], marks: List[str], earnings: Dict[str, Any],
                soon: bool, level: str, wide: Iterable[str], state: Dict[str, Any], held: bool) -> Dict[str, Any]:
    """The conclusion of '사도 돼?' for one strategy: key OK / WAIT / NO, the deciding reason, what would change it, the other
    reasons of the same weight, notes and the stance line it was judged against."""
    from terminal.qsf import config, stance as qs
    p, label = qs.PRESETS[level], qs.LABELS[level]
    score, entry = float(snap["score"]), snap.get("entry_status")
    seen = snap.get("conservative_score")
    hold_start = config.BANDS[2][0]
    close = snap.get("price")
    no: List[tuple] = []
    wait: List[tuple] = []
    if gates:
        no.append(("차단 조건이 있습니다: " + "; ".join(gates) + ".", "차단 조건이 풀려야 다시 봅니다."))
    for m in marks:
        no.append((m, "이 표시가 없어져야 다시 봅니다."))
    if snap.get("actionability") != "ACTIONABLE" and not gates:
        no.append(("자료가 모자라 실행 대상이 아닙니다.", "빠진 자료가 채워지면 다시 봅니다."))
    if score < hold_start:
        no.append((f"점수 {score:.1f}점이 관찰 기준 {hold_start:g}점 미만입니다.", f"{hold_start:g}점 이상으로 오르면 다시 봅니다."))
    elif entry == "NO_VALID_ENTRY_SETUP" and not gates and snap.get("deal_pin"):
        # the reason is the merger, not "the score or the reward-to-risk falls short" (assessment 2026-11-25)
        pin = snap["deal_pin"]
        no.append((f"합병 절차로 가격이 인수 가격 근처에 묶인 종목입니다({pin.get('label')} {pin.get('date')}). 오를 여지가 인수 가격까지뿐이라 진입 대상에서 뺍니다.",
                   "거래가 끝나거나 깨져 가격이 다시 움직이면 다시 봅니다."))
    elif entry == "NO_VALID_ENTRY_SETUP" and not gates and snap.get("band_held_back"):
        seen_txt = f"{float(seen):.1f}점" if seen is not None else "기준 미만"
        wait.append((f"자료가 빠진 요인을 중간값으로 보면 {seen_txt}으로 매수 후보 기준에 못 미쳐, 진입 판단을 미룬 종목입니다.", "빠진 자료가 채워지면 다시 봅니다."))
    elif entry == "NO_VALID_ENTRY_SETUP" and not gates:
        no.append((f"진입 판단이 '{entry_ko(entry, strategy)}'입니다. {entry_meaning(entry, strategy)}".strip(), "진입 근거가 생기면 다시 봅니다."))
    why = qs.judge(snap, level, set(wide))
    if why == "LINE":
        low = seen is not None and float(seen) < score
        used = min(score, float(seen)) if low else score
        wait.append((f"점수 {used:.1f}점" + (f"(자료가 빠진 요인을 낮게 본 점수, 기록된 점수는 {score:.1f}점)" if low else "")
                     + f"이 지금 고른 성향 '{label}'의 후보 선 {p['line']:g}점에 {p['line'] - used:.1f}점 모자랍니다.", f"{p['line']:g}점 이상이 되면 다시 봅니다."))
    elif why == "CONFIDENCE":
        wait.append((f"자료 신뢰도가 낮아 '{label}' 성향의 후보에서 빠집니다.", "자료가 채워지거나 성향을 바꾸면 달라집니다."))
    elif why == "VOLATILE":
        wait.append((f"하루 움직임이 큰 쪽 3분의 1에 들어 '{label}' 성향의 후보에서 빠집니다.", "움직임이 줄거나 성향을 바꾸면 달라집니다."))
    worse = _falling(snap.get("fund_checks"))
    if worse:
        # the entry rule reads price and valuation, not the direction of the figures; a stock this program itself marks as
        # "cheap and worsening" or whose ROE fall would read "thesis invalidated" on a holder is not a "사도 됨" (user decision
        # 2026-11-25; the entry status and the order plan are unchanged, and the rule is untested on returns)
        wait.append((f"이 프로그램의 재무 점검이 '나빠지는 중'으로 읽었습니다: {worse}", "다음 실적에서 이 수치가 돌아서면 다시 봅니다."))
    if snap.get("confidence") == "LOW" and why != "CONFIDENCE":
        # whatever the stance: a score built on missing or old figures is not a "사도 됨" (user decision 2026-11-25)
        wait.append(("이 점수를 믿는 정도가 '낮음'입니다. 계산에 쓸 자료가 일부 없거나 오래됐습니다.", "자료가 채워져 신뢰도가 오르면 다시 봅니다."))
    rr = (snap.get("holding") or {}).get("reward_risk")
    if entry == "WAIT_FOR_PULLBACK":
        zone, need = pullback_zone(snap), config.SWING["min_reward_risk"]
        pct = lambda v: f"{(v / close - 1) * 100:+.1f}%".replace("-0.0%", "0.0%").replace("+0.0%", "0.0%")      # noqa: E731
        where = f"20일선 부근 {price(zone[0], market)}~{price(zone[1], market)}" if zone else ""
        if zone and close and close > zone[1]:
            to = f"가격이 {where}(지금보다 {pct(zone[0])}~{pct(zone[1])})로 내려오면 손익비가 나아지는지 규칙이 다시 봅니다."
        elif zone and close:
            # 이미 그 부근이거나 아래: 가격이 더 내려오는 것이 답이 아니라, 목표까지의 여유가 모자란 것입니다
            to = f"가격이 이미 {where}이거나 그 아래입니다. 목표까지의 여유가 작아 손익비가 모자란 것이라, 손익비가 {need:g} 이상으로 계산되는 날 규칙이 다시 진입을 봅니다."
        else:
            to = f"가격이 20일선 부근으로 내려오거나 손익비가 {need:g} 이상으로 계산되면 규칙이 다시 진입을 봅니다."
        wait.append(("지금 가격에서는 손익비가 모자라 눌림을 기다리는 자리입니다" + (f"(지금 {rr:.2f}, 기준 {need:g})." if rr is not None else "."), to))
    elif entry == "WAIT_FOR_BREAKOUT_CONFIRMATION":
        wait.append(("고점을 넘었지만 거래량이 붙지 않아 돌파를 확인하는 중입니다.", "거래량이 붙은 돌파가 확인되면 다시 봅니다."))
    elif entry == "WAIT_FOR_EARNINGS":
        wait.append(("실적 발표를 확인하고 판단하는 자리입니다.", f"실적 발표({earnings.get('next_earnings') or '날짜 미상'}) 뒤에 다시 봅니다."))
    elif entry == "OVERVALUED_AT_CURRENT_PRICE":
        wait.append(("지금 가격에서는 비싸게 읽혀 진입을 막습니다.", "가격이 내려오거나 이익이 늘어 밸류에이션이 기준 안으로 들어오면 다시 봅니다."))
    if strategy == "SWING" and soon and entry != "WAIT_FOR_EARNINGS":
        wait.append((f"실적 발표가 {earnings.get('next_earnings')}({earnings.get('sessions')}거래일 뒤)로 임박했습니다.", "발표 뒤에 다시 봅니다."))
    if not no and not wait and entry != "ENTRY_NOW":
        wait.append(("기록에 진입 판단이 없습니다.", "다음 기록에서 다시 봅니다."))
    key = "NO" if no else "WAIT" if wait else "OK"
    reasons = no or wait or [(f"점수 {score:.1f}점이 '{label}' 성향의 후보 선 {p['line']:g}점 이상이고, 진입 판단이 '{entry_ko(entry, strategy)}'이며 막는 조건이 없습니다.", None)]
    notes = []
    if key == "OK" and strategy == "LONG_TERM":
        notes.append(entry_meaning(entry, strategy))
    if float(state.get("size_factor") or 1) < 1 and state.get("score_100") is not None:
        notes.append(f"오늘은 시장 상태가 {state['score_100']:.0f}/100({state.get('label')})이라 새 주문 크기를 {float(state['size_factor']):g}배로 줄여 계산합니다.")
    if held:
        notes.append("이미 보유 중입니다. 더 사는 것은 종목 비중 한도를 먼저 보세요.")
    lines = " · ".join(f"{qs.LABELS[k]} {qs.PRESETS[k]['line']:g}" for k in qs.LEVELS)
    basis = f"기준: 지금 고른 {MARKET_KO.get(market, market)} 성향 '{label}'의 후보 선 {p['line']:g}점입니다({lines}). 성향은 순위·카드 탭 위 줄에서 바꾸고, 바꾸면 이 결론도 달라질 수 있습니다."
    return {"key": key, "label": VERDICT_KO[key], "why": reasons[0][0], "change": reasons[0][1], "also": [r[0] for r in reasons[1:]], "notes": notes,
            "basis": basis, "stance": level, "line": p["line"], "candidate": why is None}


def decision_cautions(terminal: Any, snap: Dict[str, Any], ticker: str, market: str, strategy: str, key: str) -> List[str]:
    """Two facts that can speak against a conclusion and sat in folded sections (assessment 2026-11-25): the long-term score on
    the other statement basis, and a committee decision that disagrees with "사도 됨".  They change no conclusion: both are
    untested rule sets, and the user reads them beside the verdict."""
    from terminal import analyst_extra as ax
    out = []
    line = ax.gap_line(snap.get("fund_period"), strategy)
    if line:
        out.append(line)
    from terminal import fund_checks
    fc = snap.get("fund_checks") or {}
    if fc.get("pattern") in ("CHEAP_AND_WORSENING", "GOOD_BUT_DEAR") or fc.get("direction") == "DETERIORATING":
        out += fund_checks.lines({**fc, "status": "REAL"}, 3)       # the falling figures, in the words a holder is told
    if key == "OK":
        try:
            from terminal.committee import service as cs
            five = cs.stock(terminal, ticker, market)
            c = five.get("committee") or {}
            if five.get("status") == "OK" and c.get("valid") and c.get("decision") in ("AVOID", "SELL", "REDUCE", "WAIT"):
                out.append(f"다섯 투자자 규칙을 모은 투자위원회의 판정은 '{c.get('decision_ko') or c.get('decision')}'로 이 결론과 다릅니다. 점수와 위원회는 서로 다른 규칙이고, "
                           "둘 다 수익으로 검증되지 않았습니다.")
        except Exception:
            pass
    return out


def stock_answer(terminal: Any, intent: str, stock: Dict[str, str], strategy: str) -> Dict[str, Any]:
    """One stock, from the stored scan only: nothing is fetched and nothing is scored again."""
    from terminal.qsf import config
    market, ticker, name = stock["market"], stock["ticker"], stock["name"]
    rows = {r["strategy"]: r for r in _rows(terminal, market) if r["ticker"] == ticker}
    if intent == "ANALYZE":
        return analyst_note(terminal, stock, rows, _others(name if market == "KR" else ticker, intent, strategy))
    if intent == "FIVE":
        return five_answer(terminal, stock, _others(name if market == "KR" else ticker, intent, strategy))
    if intent == "PORTFOLIO":
        return portfolio_answer(terminal, stock, _others(name if market == "KR" else ticker, intent, strategy))
    row, snap = rows.get(strategy), _snap(terminal, stock, strategy)
    head, kind = f"{name}({ticker})", STRATEGY_KO[strategy]
    if row is None or snap is None or row.get("score") is None:
        return reply(head, f"{name}의 {kind} 점수가 최신 기록에 없습니다. 자료가 모자라 점수를 내지 못한 날일 수 있습니다.", [{"title": "할 수 있는 것", "lines": ["종목 탭에서 조회하면 그 자리에서 다시 평가합니다."]}], "stock")
    score = float(row["score"])
    st = _standing(terminal, market, strategy, score)
    basis, follow = _basis(snap, market), _others(name if market == "KR" else ticker, intent, strategy)
    still = still_note(terminal, snap)
    other = rows.get("LONG_TERM" if strategy == "SWING" else "SWING")
    other_line = f"{STRATEGY_KO[other['strategy']]} 점수는 {other['score']:.1f}점('{other.get('band_label')}')입니다." if other and other.get("score") is not None else ""
    standing = f"{st['of']}종목 중 {st['place']}위({_share(st['share'])})"
    gates = [g.get("text") or g.get("code") for g in snap.get("gates") or []]
    entry = snap.get("entry_status")
    entry_line = f"진입 판단은 '{entry_ko(entry, strategy)}'입니다. {entry_meaning(entry, strategy)}".strip()
    hold = snap.get("holding") or {}
    close = snap.get("price")

    def away(level: Optional[float]) -> str:
        return f"지금보다 {(level / close - 1) * 100:+.1f}%" if level and close else ""

    if intent == "WHY":
        gap = f"이고 매수 후보 구간({BUY_LINE:g}점 이상)까지 {BUY_LINE - score:.1f}점 모자랍니다" if score < BUY_LINE else f"입니다({BUY_LINE:g}점 이상이 매수 후보 구간)"
        summary = (f"{name}의 {kind} 점수는 {score:.1f}점으로 {standing}, 대상 안에서 {st['word']}입니다(대상의 중간값 {st['median']:.1f}점). '{row.get('band_label')}' 구간{gap}."
                   + (" 오늘은 매수 후보 구간에 든 종목이 하나도 없습니다." if st["buy"] == 0 else ""))
        parts = breakdown(snap)
        sections: List[Dict[str, Any]] = []
        if parts:
            lost = sorted((r for r in parts["rows"] if r["lost"] >= 0.5), key=lambda r: -r["lost"])[:3]
            kept = sorted((r for r in parts["rows"] if r["kept"] >= 0.5 and all(r["factor"] != x["factor"] for x in lost)), key=lambda r: -r["kept"])[:3]
            if lost:
                sections.append({"title": f"점수를 깎은 것 (100점에서 {100 - score:.1f}점을 잃었고, 아래 {len(lost)}가지가 {sum(r['lost'] for r in lost):.1f}점)",
                                 "lines": [_signal_line(r, snap, market, f"{r['lost']:.1f}점 잃음") for r in lost]})
            if kept:
                sections.append({"title": "점수를 받친 것", "lines": [_signal_line(r, snap, market, f"{r['kept']:.1f}점 얻음", scale=False) for r in kept]})
            out = [f"{FACTOR_KO.get(f['factor'], f['factor'])}(배점 {f['weight']:g}): " + ("이 종목에는 해당하지 않아" if f.get("status") == "NOT_APPLICABLE" else "자료가 없어")
                   + " 계산에서 빠졌고, 남은 요인으로만 점수를 냈습니다" + (f"({f['reason']})." if f.get("reason") else ".") for f in parts["empty"]]
            for key, d in (snap.get("domains") or {}).items():
                if d.get("reference") and d.get("score_100") is not None:
                    out.append(f"{config.DOMAIN_LABELS.get(key, key)} 영역은 이 점수에 들어가지 않습니다(참고값 {d['score_100']:.0f}/100)." + (" '시장 상태'로 따로 보여 줍니다." if key == "REGIME" else
                               " 한국 스윙에서는 과거에 순위를 거꾸로 매겨 2026-11-11에 뺐습니다." if key == "TECHNICAL" else ""))
            if out:
                sections.append({"title": "점수에 들어가지 않은 것", "lines": out})
        else:
            sections.append({"title": "요인별 점수", "lines": ["저장된 수치로 점수를 정확히 다시 나눌 수 없어 요인 점수만 보여 드립니다.", f"낮은 요인: {_factors(snap, True)}.", f"높은 요인: {_factors(snap, False)}."]})
        if still:
            sections.insert(0, {"title": "먼저 알아 둘 것", "lines": [still]})
        sections.append({"title": "프로그램이 이 점수로 읽는 것", "lines": [f"판단은 '{row.get('action_label')}'입니다.", entry_line] + [f"차단 조건: {g}. 차단 조건이 있으면 점수와 상관없이 매수 후보에서 빠집니다." for g in gates]
                         + [other_line]})
        sections.append({"title": "무엇이 달라지면 바뀌나", "lines": _bands(score) + ["가격 요인은 매 거래일 종가로, 재무 요인은 새 사업보고서가 나올 때 다시 계산됩니다.",
                                                                               "점수가 높은 종목의 수익이 더 좋았다는 근거는 아직 확인되지 않았습니다. 순위의 설명으로만 읽으세요."]})
        return reply(f"{head} {kind} 점수가 이렇게 나온 이유", summary, sections, "stock", follow, basis)

    if intent == "RANK":
        summary = f"{name}의 {kind} 점수 {score:.1f}점은 {snap.get('data_date')}에 점수가 나온 {standing}입니다."
        lines = [f"같은 날 {kind} 점수의 중간값은 {st['median']:.1f}점이고, 매수 후보 구간({BUY_LINE:g}점 이상)에 든 종목은 {st['buy']}개입니다."]
        if other and other.get("score") is not None:
            so = _standing(terminal, market, other["strategy"], float(other["score"]))
            lines.append(f"{STRATEGY_KO[other['strategy']]} 점수는 {other['score']:.1f}점으로 {so['of']}종목 중 {so['place']}위({_share(so['share'])})입니다.")
        return reply(f"{head} 순위", summary, [{"title": "대상 안에서의 위치", "lines": lines},
                                             {"title": "읽을 때 주의", "lines": ["순위는 그날 대상 종목끼리의 비교입니다. 순위가 높다고 수익이 더 좋았다는 근거는 아직 확인되지 않았습니다."]}], "qsf", follow, basis)

    if intent == "STOP":
        if strategy == "LONG_TERM" or not snap.get("stop"):
            lines = [f"{x}." for x in (hold.get("invalidation") or [])[:5]]
            cut = [f"비중을 줄일 조건: {x}." for x in (hold.get("reduce_conditions") or [])[:3]]
            watch = [f"{x}." for x in (hold.get("milestones") or [])[:3]]
            return reply(f"{head} 장기 보유의 기준", f"{name}의 장기 점수에는 가격으로 정한 손절선이 없습니다. 장기 보유는 가격이 아니라 사업과 재무가 유지되는지를 봅니다.",
                         [{"title": "보유 논리가 깨지는 조건", "lines": lines + cut}, {"title": "다음 실적에서 지켜볼 것", "lines": watch},
                          {"title": "가격 손절을 쓰고 싶다면", "lines": ["주문 계획은 장기 종목에 변동 폭(ATR)의 5배 아래를 손절로 씁니다. 배수는 매매 보조 탭의 위험 관리 설정에서 바꿉니다.",
                                                              str(hold.get("review_note") or ""), f"스윙 기준의 손절선은 '{name} 손절 어디?'로 볼 수 있습니다."]}], "stock", follow, basis)
        target = snap.get("target")
        summary = (f"{name}의 스윙 기준 손절선은 {price(snap['stop'], market)}({away(snap['stop'])})" + (f", 목표는 {price(target, market)}({away(target)})" if target else "") + f"입니다. 기준 종가는 {price(close, market)}입니다.")
        rr = hold.get("reward_risk")
        ratio = [] if rr is None else [f"비용을 뺀 손익비는 {rr:.2f}입니다. 목표까지의 이익 여지가 손절까지의 손실 여지의 {rr:.2f}배라는 뜻이고, 1보다 작으면 기대 이익이 감수할 손실보다 작습니다."]
        how = [f"손절: {hold['stop_method']}." if hold.get("stop_method") else "", f"목표: {hold['target_method']}." if hold.get("target_method") else ""] + [f"{x}." for x in (hold.get("why") or [])[:2]]
        plan = [f"예상 보유 {hold['expected_sessions']}거래일, 첫 재검토 {hold.get('first_review')}." if hold.get("expected_sessions") else "", str(hold.get("time_stop_note") or "")]
        return reply(f"{head} 손절·목표", summary, [{"title": "손익비", "lines": ratio}, {"title": "어떻게 정한 값인가", "lines": how},
                                                {"title": "이 계획이 무효가 되는 조건", "lines": [f"{x}." for x in (hold.get("invalidation") or [])[:3]]},
                                                {"title": "보유 기간", "lines": plan},
                                                {"title": "주의", "lines": [str(hold.get("gap_note") or ""), "이 값은 그날 종가 기준의 계획이고 주문이 아닙니다. 계좌를 기록하면 주문 계획에 수량과 함께 나옵니다."]}], "stock", follow, basis)

    if intent == "RANGE":
        from terminal.qsf import forecast
        got = forecast.stock(terminal.base, market, ticker)
        if got.get("status") != "REAL" or not got.get("ranges"):
            return reply(f"{head} 가격 범위", f"{name}의 가격 범위 기록이 없습니다.", [], "stock", follow)
        base = got.get("close")
        rng = sorted(got["ranges"].items(), key=lambda kv: int(kv[0]))

        def span(pair: List[float]) -> str:
            return f"{price(pair[0], market)} ~ {price(pair[1], market)}({(pair[0] / base - 1) * 100:+.1f}% ~ {(pair[1] / base - 1) * 100:+.1f}%)"
        h0, r0 = rng[0]
        summary = f"{name}의 {h0}거래일 뒤 종가는 80% 가능성으로 {span(r0['p80'])} 사이로 봅니다. 기준 종가는 {price(base, market)}({got.get('session')})입니다."
        lines = [f"{h}거래일 뒤: 80% 가능성 {span(r['p80'])}, 50% 가능성 {span(r['p50'])}." for h, r in rng]
        test = got.get("test") or {}
        checked = (f"범위의 폭은 과거 자료({test.get('first')}~{test.get('last')}, {test.get('days')}일)에서 실제로 그 비율만큼 들어맞는지 확인했습니다." if test.get("verdict") == "RANGE_CALIBRATED"
                   else "범위의 폭은 과거 자료로 확인되지 않았습니다. 어림으로만 보세요.")
        return reply(f"{head} 가격 범위", summary, [{"title": "먼저 알아 둘 것", "lines": [still or ""]}, {"title": "기간별 범위", "lines": lines},
                                                 {"title": "읽는 법", "lines": [checked, "오를지 내릴지는 말하지 않습니다. 점수의 방향 예측력이 확인되지 않아 범위의 가운데를 지금 가격에 둡니다.",
                                                                           "80% 범위라는 것은 다섯 번에 한 번은 이 밖에서 끝난다는 뜻입니다.", str(got.get("path_note") or "")]}], "stock", follow)

    raw = next((f.get("raw") or {} for f in snap.get("factors") or [] if f.get("factor") == "earnings_calendar" and isinstance(f.get("raw"), dict)), {})
    estimated = raw.get("basis") == "ESTIMATE"
    block = config.EARNINGS_BLOCK_SESSIONS_ESTIMATE if estimated else config.EARNINGS_BLOCK_SESSIONS
    if intent == "EARNINGS":
        if not raw.get("next_earnings"):
            return reply(f"{head} 실적 발표", f"{name}의 다음 실적 발표일이 저장돼 있지 않습니다.", [{"title": "이것이 뜻하는 것", "lines": ["실적 일정 요인은 점수 계산에서 빠지고, 발표 직전 진입 차단도 걸리지 않습니다. 발표일은 직접 확인하세요."]}],
                         "assist", follow, basis)
        left = raw.get("sessions")
        summary = f"{name}의 다음 실적 발표는 {raw['next_earnings']}" + (f"({left}거래일 뒤)" if left is not None else "") + "로 저장돼 있습니다."
        source = ("회사가 확정한 날짜가 아닙니다. 작년 같은 분기의 발표일" + (f"({raw['from']})" if raw.get("from") else "") + "로 추정했습니다. 실제 발표는 며칠 앞뒤일 수 있습니다." if estimated
                  else "Yahoo 실적 일정에서 읽은 날짜입니다. 회사가 확정하기 전에는 추정치일 수 있습니다.")
        f = next((x for x in snap.get("factors") or [] if x.get("factor") == "earnings_calendar"), {})
        effect = [f"실적 일정 요인은 지금 {f['normalized'] * 100:.0f}/100입니다. {FACTOR_INFO['earnings_calendar'][1]}." if f.get("normalized") is not None else "",
                  f"스윙은 발표 {block}거래일 전부터 새 진입을 막습니다" + ("(추정일이라 폭을 넓게 잡음)." if estimated else ".")
                  + (" 지금 그 안에 있습니다." if left is not None and left <= block else " 지금은 그 밖입니다." if left is not None else "")]
        return reply(f"{head} 실적 발표", summary, [{"title": "이 날짜의 출처", "lines": [source]}, {"title": "점수와 진입에 미치는 것", "lines": effect}], "assist", follow, basis)

    marks = []
    if row.get("high_risk"):
        marks.append("고위험 표시: 변동성과 낙폭이 대상 가운데 나쁜 쪽입니다. 한국의 과거 시험에서 이 표시는 이후 수익이 더 나빴던 쪽을 가려냈습니다.")
    filing = row.get("filing_events") or {}
    if filing.get("financing"):
        marks.append("자금 조달 공시: 최근 유상증자나 사채 발행류 공시가 있습니다. 한국의 과거 시험에서 이런 종목은 이후 수익이 부진했습니다.")
    notes = ["자사주 취득 공시가 있습니다. 시장 대비 우위는 확인되지 않아 좋게도 나쁘게도 세지 않습니다."] if filing.get("buyback") else []
    unknown = ["고위험 표시와 공시 표시 가운데 일부는 자료가 없어 확인하지 못했습니다."] if row.get("high_risk_unknown") or row.get("filing_unknown") else []

    if intent == "RISK":
        clear = not gates and not marks
        summary = (f"{name}에 걸린 차단 조건과 회피 표시는 없습니다. 다만 표시가 없다는 것이 안전하다는 뜻은 아닙니다." if clear
                   else f"{name}에는 차단 조건 {len(gates)}건, 회피 표시 {len(marks)}건이 있습니다.")
        risk = [_signal_line(f, snap, market, f"배점 {f['weight']:g}", scale=False) for f in snap.get("factors") or []
                if f.get("domain") == "RISK" and f.get("weight") and f.get("normalized") is not None]
        return reply(f"{head} 위험 점검", summary, [{"title": "차단 조건", "lines": [f"{g}. 차단 조건이 있으면 점수와 상관없이 매수 후보에서 빠집니다." for g in gates] or ["없음."]},
                                                 {"title": "회피 표시", "lines": marks or ["없음."]}, {"title": "위험 요인의 실제 수치", "lines": risk},
                                                 {"title": "참고", "lines": notes + unknown}], "stock", follow, basis)
    held = False
    try:
        held = ticker in terminal._book(market)[2]["positions"]
    except Exception:
        pass
    if intent == "SELL_CHECK":
        if not held:
            would = [f"{x}." for x in (hold.get("exit_triggers") or hold.get("invalidation") or [])[:7]]
            return reply(f"{head} 매도 점검", f"{josa(name, '은는')} 보유 기록이 없어 매도 조건을 계산하지 않았습니다. 매도 조건은 매수가, 매수일, 손절선이 있어야 읽을 수 있습니다.",
                         [{"title": f"보유했다면 보는 조건({kind})", "lines": would}, {"title": "지금의 점수", "lines": [f"{kind} 점수 {score:.1f}점('{row.get('band_label')}'), 판단 '{row.get('action_label')}'.", other_line]},
                          {"title": "할 수 있는 것", "lines": ["'내 계좌'에 거래를 기록하면 이 종목의 손절·기한·청산 조건을 매일 점검해 '오늘' 탭에 올립니다."]}], "portfolio", follow, basis)
        sig = next((s for s in terminal.portfolio_signals(market)["items"] if s.get("ticker") == ticker), None)
        if not sig or sig.get("status") != "REAL":
            return reply(f"{head} 매도 점검", f"{name}의 자료를 읽지 못해 매도 조건을 점검하지 못했습니다.", [], "portfolio", follow)
        ex = sig["exit"]
        hit = [f"{c['text']}" for c in ex.get("conditions") or [] if c.get("action") != "HOLD"][:6]
        return reply(f"{head} 매도 점검", f"{name}의 보유 판단은 '{EXIT_KO.get(ex['action'], ex['action'])}'입니다. {ex['reason']}",
                     [{"title": "걸린 조건", "lines": hit or ["없음."]}, {"title": "읽을 때 주의", "lines": ["판단은 규칙이 읽은 것이고 자동 매도는 없습니다. 주문은 직접 정합니다."]}], "portfolio", follow, basis)

    # BUY_CHECK: the conclusion first (user decision 2026-11-24), then the checklist it came from
    from terminal.qsf import stance as qs
    state = terminal.market_state(market)
    soon = raw.get("sessions") is not None and raw["sessions"] <= block
    level = qs.level(Path(terminal.base), market)
    session = snap.get("data_date")
    wide = qs.volatile(_snaps(terminal, market, session)) if qs.PRESETS[level]["drop_volatile"] and session else set()
    judged = dict(gates=gates, marks=marks, earnings=raw, soon=soon, level=level, wide=wide, state=state, held=held)
    v = buy_verdict(snap, strategy, market, **judged)
    other_snap = _snap(terminal, stock, "LONG_TERM" if strategy == "SWING" else "SWING")
    other_line = ""
    if other_snap is not None and other_snap.get("score") is not None:
        ov = buy_verdict(other_snap, other_snap["strategy"], market, **{**judged, "gates": [g.get("text") or g.get("code") for g in other_snap.get("gates") or []]})
        other_line = f"{STRATEGY_KO[other_snap['strategy']]}: {ov['label']} · " + ("" if ov["why"].startswith("점수") else f"점수 {float(other_snap['score']):.1f}점 · ") + ov["why"]
    stance_why = {"LINE": f"후보 선 {v['line']:g}점 미만", "CONFIDENCE": "자료 신뢰도 미달", "VOLATILE": "움직임이 큰 쪽", "NOT_ACTIONABLE": "실행 대상 아님"}
    pick = qs.judge(snap, level, set(wide))
    checks = [("성향 후보", pick is None, f"{kind} {score:.1f}점('{row.get('band_label')}' 구간), {standing}. 지금 성향 '{qs.LABELS[level]}'의 후보 선은 {v['line']:g}점입니다"
               + (f"({stance_why.get(pick, pick)})." if pick else ".")),
              ("진입 판단", entry == "ENTRY_NOW", f"'{entry_ko(entry, strategy)}'. {entry_meaning(entry, strategy)}" + (f" 지금 손익비는 {hold['reward_risk']:.2f}입니다." if hold.get("reward_risk") is not None else "")),
              ("차단 조건", not gates, ("; ".join(gates) + ". 점수와 상관없이 매수 후보에서 빠집니다.") if gates else "없음."),
              ("실적 발표", (not soon) if raw.get("next_earnings") else None, (f"{raw['next_earnings']}({raw.get('sessions')}거래일 뒤)" + ("로 임박했습니다. 발표 전후에는 가격이 크게 움직일 수 있습니다." if soon else "로 임박하지 않았습니다."))
               if raw.get("next_earnings") else "저장된 날짜가 없습니다. 직접 확인하세요."),
              ("회피 표시", not marks, " ".join(marks) if marks else "없음."),
              ("시장 상태", (state.get("state") != "ADVERSE") if state.get("score_100") is not None else None,
               (f"{state['score_100']:.0f}/100({state.get('label')}). " + ("나쁜 날에는 새 주문 크기를 줄여 계산합니다." if float(state.get("size_factor") or 1) < 1 else
                                                                         "이 시장에서는 과거에 이 값이 이후 수익을 가르지 못했습니다." if state.get("state") == "ADVERSE" else "")) if state.get("score_100") is not None else "자료 없음."),
              ("보유 여부", not held, "이미 보유 중입니다. 추가 매수는 종목 비중 한도를 먼저 보세요." if held else "보유 기록 없음.")]
    mark = lambda ok: "○" if ok else "✕" if ok is False else "–"      # noqa: E731
    passed = sum(1 for _, ok, _ in checks if ok)
    cautions = decision_cautions(terminal, snap, ticker, market, strategy, v["key"])
    summary = f"{v['label']} ({kind}, 프로그램 규칙 기준) — {v['why']}"
    ans = reply(f"{head} 사도 돼? ({kind})", summary,
                [{"title": "결론 자세히", "lines": ([f"바뀌는 조건: {v['change']}"] if v["change"] else []) + [f"함께 걸린 것: {x}" for x in v["also"]] + [f"같이 볼 것: {x}" for x in cautions] + v["notes"] + [v["basis"], VERDICT_CAVEAT]},
                 {"title": "다른 전략", "lines": [other_line]},
                 {"title": f"점검표 ({len(checks)}개 중 {passed}개 통과 · ○ 통과 · ✕ 걸림 · – 확인 못 함)", "lines": [f"{mark(ok)} {label}: {text}" for label, ok, text in checks]},
                 {"title": "참고", "lines": ([still] if still else []) + notes + unknown},
                 {"title": "다음에 볼 것", "lines": ["수량, 지정가 상한, 손절은 '통합 계좌'에 계좌를 기록하면 '주문 계획'에 계좌 기준으로 나옵니다."]}], "stock", follow, basis)
    ans["verdict"] = {"key": v["key"], "label": v["label"], "strategy": kind, "why": v["why"], "change": v["change"], "other": other_line, "cautions": cautions,
                      "caveat": VERDICT_CAVEAT}          # inside the conclusion box: it sat under it (assessment 2026-11-25)
    return ans


def plain_answer(terminal: Any, intent: str, market: str) -> Dict[str, Any]:
    from terminal import automation
    from terminal.qsf import changes as qsf_changes, config, readings as qsf_readings
    where, base = MARKET_KO[market], Path(terminal.base)
    other = "미국" if market == "KR" else "한국"
    texts = lambda items: [i["text"] for i in items]      # noqa: E731
    switch = f"지금 보는 시장은 {where}입니다. {other} 것은 위의 시장 버튼을 바꾼 뒤 물으세요."
    if intent == "HELP":
        got = reply(f"물어볼 수 있는 것 {len(EXAMPLES)}가지", "정해진 질문만 알아듣습니다. 아래 예를 누르거나 비슷하게 적으면 됩니다.",
                    [{"title": f"종목 없이 묻는 것 {len(PLAIN_INTENTS)}가지", "lines": [e for _, e, _ in PLAIN_INTENTS[::-1]]},
                     {"title": f"종목을 넣어 묻는 것 {len(STOCK_INTENTS)}가지", "lines": stock_examples(market)},
                     {"title": "쓰는 법", "lines": [f"종목은 '{example_stock(market)}' 자리에 코드, 티커, 회사명을 적습니다(스캔 대상: 미국 S&P 500, 한국 시가총액 상위 300).", "'장기'를 넣으면 장기 점수로, 없으면 스윙 점수로 답합니다.",
                                                "이 목록은 'help', '도움말', '?'로 언제든 다시 볼 수 있습니다."]}])
        return {**got, "examples": examples_for(market)}
    if intent == "TEAM":                                    # the five investors asked without a stock: say how to ask
        from terminal.committee import investors as civ
        eg = example_stock(market)
        return reply("다섯 투자자는 종목을 넣어 묻습니다", f"종목을 넣어 물어 주세요. 예: '{eg} 다섯 관점은?', '{eg} 포트폴리오 받아보기'.",
                     [{"title": "할 수 있는 것", "lines": [f"'{eg} 다섯 관점은?': 그 종목에 대한 다섯 투자자(버핏식·멍거식·그레이엄식·린치식·드러켄밀러식)의 의견과 통합 투자위원회의 판정을 봅니다. 점수 카드에도 나옵니다.",
                                                   f"'{eg} 포트폴리오 받아보기': 여섯 포트폴리오(다섯 투자자와 투자위원회)를 그때 만들고 그 종목이 어디에 드는지 보여 줍니다.",
                                                   "여섯 포트폴리오 전체는 '투자위원회' 탭의 '여섯 포트폴리오 받아보기'로 봅니다. 포트폴리오는 요청할 때만 만듭니다."]},
                      {"title": "한계", "lines": [civ.NOTE, switch]}], "committee", [f"{eg} 다섯 관점은?", f"{eg} 포트폴리오 받아보기"])
    if intent == "TODAY":
        brief = briefing(terminal, market)
        groups = [{"title": LEVEL_KO[lv], "lines": [i["text"] for i in brief["items"] if i["level"] == lv][:6]} for lv in LEVELS]
        return reply(f"오늘 할 일({where})", brief["headline"], groups + [{"title": "읽지 못한 부분", "lines": [p["label"] for p in brief["unread_parts"]]}], "today",
                     ["오늘 상위 종목은?", "시장 상태 어때?", "어제와 뭐가 달라졌어?"])
    if intent == "TRUST":
        return reply("이 점수를 얼마나 믿을 수 있나", "점수가 높은 종목의 수익이 더 좋았다는 근거는 아직 확인되지 않았습니다. 지금은 순위와 위험을 정리해 보는 도구로 쓰는 것이 맞습니다.",
                     [{"title": "과거 자료로 확인한 것", "lines": [config.VALIDATION_NOTICE]},
                      {"title": "근거가 나온 쪽", "lines": ["한국의 회피 쪽입니다: 자금 조달 공시가 있는 종목은 이후 수익이 부진했습니다. 위험 등급이 나쁜 종목은 이후 변동성과 손실 크기가 더 컸습니다(수익을 맞힌 것은 아닙니다).", "가격 범위의 폭입니다: 5·20거래일 뒤 종가가 범위 안에 든 비율이 과거 자료와 맞았습니다.",
                                                  "살 종목을 고르는 힘은 확인되지 않았습니다."]},
                      {"title": "앞으로", "lines": ["매일의 기록으로 한 번씩 판정합니다(스윙 2027년 말, 장기 2030년쯤). 때가 되면 스스로 읽고 텔레그램으로 알립니다.",
                                                "1년 기록으로는 꽤 큰 효과만 확인됩니다. '근거 없음'이 나와도 작은 효과가 없다는 뜻은 아닙니다."]}], "qsf", ["판정은 언제 나와?", "오늘 상위 종목은?"])
    if intent == "COST":
        c = config.COSTS[market]
        return reply(f"{where} 거래 비용 가정", f"{where} 주식은 사고파는 왕복 비용을 {config.round_trip_cost(market) * 100:.2f}%로 계산합니다.",
                     [{"title": "구성", "lines": [str(c.get("basis") or "")]},
                      {"title": "어디에 쓰이나", "lines": ["손익비, 가상 장부, 판정의 수익 계산에 모두 이 비용을 뺍니다.", "스프레드와 슬리피지는 가정값이라 실제 체결과 다를 수 있습니다. 거래대금이 작은 종목은 더 클 수 있습니다."]},
                      {"title": "참고", "lines": [switch]}], "qsf")
    if intent == "ALERTS":
        view = terminal.alerts_view()
        rules = [r for r in view.get("rules") or [] if r.get("status") == "ACTIVE"]
        fired = texts(alert_items(view.get("log") or [], terminal.now()))
        return reply("내 알림 조건", f"켜 둔 알림 조건은 {len(rules)}개이고, 어제 아침 이후 발생한 알림은 {len(fired)}건입니다.",
                     [{"title": "켜 둔 조건", "lines": [str(r.get("name") or r.get("type")) for r in rules[:10]] or ["없습니다. 매매 보조 탭의 알림 센터에서 가격, 등락폭, 점수 구간, 실적 임박 조건을 추가할 수 있습니다."]},
                      {"title": "최근 발생", "lines": fired or ["없습니다."]},
                      {"title": "알아 둘 것", "lines": ["하루 한 번, 매일 자동 실행 때 일봉 종가로 확인해 텔레그램으로 보냅니다. 실시간 알림이 아닙니다."]}], "assist")
    if intent == "VERDICTS":
        got = qsf_readings.status(base, terminal.now().date(), automation.readings_state(base))
        waiting = sorted((r for r in got["readings"] if r.get("state") == "WAITING" and r.get("expected")), key=lambda r: r["expected"])
        read = [f"{r['label']}: {r.get('verdict')}. {r.get('meaning') or ''}" for r in got["readings"] if r.get("state") == "READ"]
        nxt = [f"{r['label']}: {r['expected']} 무렵({r['left']}거래일 남음)." for r in waiting[:4]]
        first = f" 가장 먼저 나오는 것은 {waiting[0]['label']}({waiting[0]['expected']} 무렵)입니다." if waiting else ""
        return reply("판정 일정", f"판정 {got['total']}건 가운데 {got['read']}건을 읽었습니다.{first}",
                     [{"title": "이미 읽은 판정", "lines": read[:6]}, {"title": "다음에 나올 판정", "lines": nxt},
                      {"title": "알아 둘 것", "lines": ["판정은 기록이 충분히 쌓인 날 매일 작업이 스스로 한 번 읽고 텔레그램으로 알립니다. 사람이 할 일은 없습니다.",
                                                  "대부분의 판정은 결과만 알려 주고 점수나 규칙을 자동으로 바꾸지 않습니다. 전체 목록은 순위·카드 탭의 '판정 일정'에 있습니다."]}], "qsf", ["이 점수 믿어도 돼?"])
    if intent == "JOB":
        st = automation.status(base)
        steps = st.get("steps") or {}
        bad = texts(job_items(st, automation.STEP_NAMES))
        ok = [automation.STEP_NAMES.get(n, n) for n, s in steps.items() if (s or {}).get("status") == "OK"]
        failed = [n for n, s in steps.items() if (s or {}).get("status") == "FAILED"]
        late = texts([i for i in top_items(terminal.qsf.top3(market), market) if i["kind"] == "RECORD_LATE"])
        summary = (f"기준 거래일 {st.get('latest_session')}의 수집은 {len(steps)}단계 중 {len(ok)}단계가 끝났" + (f"고 {len(failed)}단계가 실패했습니다." if failed else "습니다. 실패한 단계는 없습니다.")) if steps else "자료 수집 기록이 없습니다."
        return reply("자료 수집 상태", summary, [{"title": "챙길 것", "lines": bad + late}, {"title": "끝난 단계", "lines": [", ".join(ok)] if ok else []},
                                             {"title": "알아 둘 것", "lines": ["매일 07:10부터 매시간 시도하고, 그날 할 일이 끝났으면 건너뜁니다. 맥이 잠들어 있으면 깨어난 뒤에 돕니다.",
                                                                         "지금 바로 돌리려면 위의 '지금 수집'을 누릅니다."]}], "lab")
    if intent == "CHANGES":
        ch = qsf_changes.report(terminal.qsf.latest(market), terminal.qsf.ledger, market, "SWING")
        if ch.get("status") != "REAL":
            return reply("직전 기록과 달라진 점", "비교할 직전 기록이 없습니다.", [], "qsf")
        move = lambda r: f"{r.get('name') or r['ticker']}({r['ticker']}) {r['previous_score']:.1f} → {r['score']:.1f}점({r['delta']:+.1f})"      # noqa: E731
        entered, left = ch.get("entered_buy") or [], ch.get("left_buy") or []
        summary = (f"{where} 스윙 점수는 {ch.get('previous_session')} 기록과 견줘, 매수 후보 구간에 {len(entered)}종목이 새로 들어오고 {len(left)}종목이 빠졌습니다." if entered or left
                   else f"{where} 스윙 점수는 {ch.get('previous_session')} 기록과 견줘 매수 후보 구간을 드나든 종목이 없습니다.")
        return reply(f"{where} 스윙 점수: {ch.get('previous_session')} → {ch.get('session')}", summary,
                     [{"title": "매수 후보 구간", "lines": texts(change_items(ch))}, {"title": "점수가 가장 많이 오른 종목", "lines": [move(r) for r in (ch.get("up") or [])[:5]]},
                      {"title": "점수가 가장 많이 내린 종목", "lines": [move(r) for r in (ch.get("down") or [])[:5]]},
                      {"title": "알아 둘 것", "lines": [f"두 기록에 모두 있는 {ch.get('compared')}종목을 비교했습니다. 하루 사이의 점수 변화는 대부분 가격 요인에서 나옵니다.", switch]}], "qsf",
                     ["오늘 상위 종목은?"] + ([f"{(ch['down'][0].get('name') if market == 'KR' else None) or ch['down'][0]['ticker']} 점수 왜 이래?"] if ch.get("down") else []))
    if intent == "MARKET":
        state = terminal.market_state(market)
        if state.get("score_100") is None:
            return reply(f"{where} 시장 상태", f"{where} 시장 상태 기록이 없습니다.", [], "qsf")
        raws = {f["factor"]: (f.get("raw") if isinstance(f.get("raw"), dict) else {}) for f in state.get("factors") or []}
        parts = [f"{FACTOR_KO.get(f['factor'], f['factor'])}: {f['normalized'] * 100:.0f}/100" if f.get("normalized") is not None else f"{FACTOR_KO.get(f['factor'], f['factor'])}: 자료 없음({f.get('reason') or '받지 못함'})"
                 for f in state.get("factors") or []]
        stress = []
        idx = raws.get("index_trend_breadth") or raws.get("index_trend") or {}
        if idx.get("close") and idx.get("ma200"):
            stress.append(f"대표 지수는 200일 평균보다 {(idx['close'] / idx['ma200'] - 1) * 100:+.1f}%, 50일 평균보다 {(idx['close'] / idx['ma50'] - 1) * 100:+.1f}%입니다.")
        width = (raws.get("index_trend_breadth") or {}).get("breadth") or (raws.get("breadth") or {}).get("breadth")
        if width is not None:
            stress.append(f"200일 평균 위에 있는 종목은 {width * 100:.0f}%입니다. 절반보다 적으면 하락이 일부 종목이 아니라 시장 전체에 퍼져 있다는 뜻입니다.")
        vix = raws.get("vix_regime") or {}
        if vix.get("vix") is not None:
            stress.append(f"변동성 지수(VIX) {vix['vix']:.1f}: 최근 5년 가운데 상위 {max(1, round((1 - (vix.get('percentile_5y') or 0)) * 100))}% 수준입니다.")
        term = (raws.get("vix_term") or {}).get("vix_vix3m")
        if term is not None:
            stress.append(f"단기 변동성이 3개월 변동성의 {term:.2f}배입니다. 1을 넘으면 지금 당장의 불안이 더 크다는 뜻입니다.")
        credit = raws.get("credit_spread") or {}
        if credit.get("spread") is not None:
            stress.append(f"하이일드 신용 스프레드 {credit['spread']:.2f}%p: 가용 이력 안에서 높은 쪽 {max(1, round((1 - (credit.get('percentile') or 0)) * 100))}% 위치입니다. 주가보다 신용이 얼마나 흔들리는지를 봅니다.")
        fx = raws.get("usdkrw_regime") or {}
        if fx.get("usdkrw") is not None:
            stress.append(f"원/달러 {fx['usdkrw']:,.0f}원, 3개월 변화 {(fx.get('change_63') or 0) * 100:+.1f}%입니다.")
        try:
            lines = _index_lines(terminal.overview(market))
        except Exception:
            lines = {"index": [], "macro": [], "sector": []}
        scored = [r["score"] for r in _rows(terminal, market) if r["strategy"] == "SWING" and r.get("score") is not None]
        book = ([f"스윙 점수의 중간값은 {sorted(scored)[len(scored) // 2]:.1f}점이고, {len(scored)}종목 가운데 매수 후보 구간({BUY_LINE:g}점 이상)은 {sum(1 for s in scored if s >= BUY_LINE)}개입니다."] if scored else [])
        try:
            ch = qsf_changes.report(terminal.qsf.latest(market), terminal.qsf.ledger, market, "SWING")
            if ch.get("status") == "REAL":
                book.append(f"직전 기록과 견줘 매수 후보 구간에 {len(ch.get('entered_buy') or [])}종목이 들어오고 {len(ch.get('left_buy') or [])}종목이 빠졌습니다.")
        except Exception:
            pass
        try:
            dates = [f"{e.get('name')} {e.get('date_kst') or e.get('date')}({e.get('days_away')}일 뒤)." for e in (terminal.econ_calendar(market, 14).get("items") or [])[:4]]
        except Exception:
            dates = []
        return reply(f"{where} 시장 노트({state.get('session')})", texts(market_items(state, market))[0],
                     [{"title": "지수", "lines": lines["index"]}, {"title": "얼마나 불안한가", "lines": stress}, {"title": "업종", "lines": lines["sector"]},
                      {"title": "금리·환율·원자재", "lines": lines["macro"]}, {"title": "점수로 본 시장", "lines": book},
                      {"title": "시장 상태 점수의 구성 (100에 가까울수록 좋음)", "lines": parts}, {"title": "다가오는 일정", "lines": dates},
                      {"title": "읽을 때 주의", "lines": [str(state.get("note") or ""), "프로그램은 가격과 지표만 읽습니다. 왜 움직였는지(뉴스의 뜻)는 판단하지 않습니다.",
                                                   "시장 상태는 종목 점수에 들어가지 않습니다. 모든 종목에 같은 값이라 순위를 바꾸지 못합니다.", switch]}], "overview", ["오늘 상위 종목은?", "어제와 뭐가 달라졌어?", "오늘 뭐 해야 해?"])
    if intent == "HOLDINGS":
        book = terminal.portfolio(market)
        items = holding_items(book, terminal.portfolio_signals(market)["items"] if book.get("holdings") else [], market)
        act = [i for i in items if i["level"] == "ACT"]
        n = len(book.get("holdings") or [])
        summary = (f"{where} 계좌에 기록된 보유 종목이 없습니다." if not n else f"{where} 보유 {n}종목 가운데 먼저 볼 것이 {len(act)}건 있습니다." if act else f"{where} 보유 {n}종목에 손실과 관련해 먼저 볼 것은 없습니다.")
        return reply(f"{where} 보유 종목 점검", summary, [{"title": LEVEL_KO[lv], "lines": [i["text"] for i in items if i["level"] == lv and n]} for lv in LEVELS]
                     + ([{"title": "할 수 있는 것", "lines": ["'내 계좌'에 입금과 거래(매수가, 손절가, 장기·스윙 구분)를 기록하면 손절선, 보유 기한, 청산 조건을 매일 점검합니다.", switch]}] if not n else []), "portfolio")
    plan, top3 = terminal.order_plan(market), terminal.qsf.top3(market)                     # TOP
    days = (((top3.get("strategies") or {}).get("SWING") or {}).get("days")) or []
    day = max(days, key=lambda d: d.get("session") or "") if days else {}
    best = (day.get("top") or [{}])[0]
    summary = (f"{where} 스윙 점수 1위는 {best.get('name') or best.get('ticker')}({best.get('ticker')}) {best['score']:.1f}점입니다({day.get('session')} 기록). 순위일 뿐 매수 신호가 아닙니다." if best.get("score") is not None
               else f"{where} 상위 종목 기록이 없습니다.")
    rows = {r["ticker"]: r for r in _rows(terminal, market) if r["strategy"] == "SWING"}
    tops = [f"{x.get('rank')}위 {x.get('name') or x['ticker']}({x['ticker']}) {x['score']:.1f}점: '{(rows.get(x['ticker']) or {}).get('band_label') or '구간 없음'}', 진입 판단 '{ENTRY_KO.get((rows.get(x['ticker']) or {}).get('entry_status'), '자료 없음')}'."
            for x in day.get("top") or []]
    past = ("미국 과거 구간 시험에서 상위 3종목의 수익은 무작위로 고른 3종목과 구분되지 않았습니다. 상위라는 이유만으로 사지 마세요." if market == "US"
            else "한국의 상위 3종목은 과거 구간으로 시험한 적이 없고, 2026-11-09부터 매일 고정해 추적하고 있습니다. 상위라는 이유만으로 사지 마세요.")
    still = []
    for x in day.get("top") or []:
        s = _snap(terminal, {"ticker": x["ticker"], "market": market}, "SWING")
        if s and still_note(terminal, s):
            still.append(f"{x.get('name') or x['ticker']}({x['ticker']}): {still_note(terminal, s)}")
    try:
        mix_line = candidate_mix(terminal, market)
    except Exception:
        mix_line = None
    return reply(f"{where} 점수 상위와 진입 후보", summary, [{"title": f"스윙 상위 3종목(진입 거래일 {day.get('entry_session')})", "lines": tops}, {"title": "먼저 알아 둘 것", "lines": still},
                                                       {"title": "매수 후보의 구성", "lines": [mix_line or ""]},
                                                       {"title": "주문 계획", "lines": texts(plan_items(plan, market))}, {"title": "읽을 때 주의", "lines": [past, switch]}], "qsf",
                 [f"{best.get('name') if market == 'KR' else best.get('ticker')} 점수 왜 이래?", f"{best.get('name') if market == 'KR' else best.get('ticker')} 사도 돼?"] if best.get("ticker") else [])


TICKER_LIKE = r"(?<![0-9A-Za-z])(?:[0-9][0-9A-Z]{5}|[A-Z]{2,5})(?![0-9A-Za-z])"


def answer(terminal: Any, text: str, market: str = "US") -> Dict[str, Any]:
    """A typed line read by keyword.  It answers the fixed questions in ``EXAMPLES`` and says so when it does not know one."""
    import re
    text = " ".join(str(text or "").split())[:200]
    if not text:
        return {"status": "UNKNOWN", "title": "질문이 비어 있습니다", "summary": "아래 예처럼 물어보세요.", "sections": [], "lines": ["아래 예처럼 물어보세요."], "examples": examples_for(market), "note": NOTE}
    if market == "COIN":
        return coin_answer(terminal, text)
    if text.lower().strip(" ?？!.") in ("", "help", "h", "도움", "도움말", "질문", "목록"):
        text = "help"
    stock = None if text == "help" else find_stock(text, {m: _rows(terminal, m) for m in ("KR", "US")})
    intent = read_question(text, stock is not None)
    code = None if stock or text == "help" else next(iter(re.findall(TICKER_LIKE, text)), None)
    if code and (intent is None or any(w in text.lower() for _, _, words in STOCK_INTENTS for w in words)):
        say = f"'{code}'{josa(code, '은는')[len(code):]} 스캔 대상(미국 S&P 500, 한국 시가총액 상위 300)에 없어 저장된 점수가 없습니다."
        from terminal import symbols                         # a mistyped ticker gets the scanned stocks it may have meant, from stored names only
        near = [x for x in symbols.suggest(symbols.universe({m: _rows(terminal, m) for m in ("KR", "US")}), code, market)["items"] if x["match"] != "EXACT"][:4]
        maybe = [{"title": "혹시 이 종목인가요", "lines": [f"{x['ticker']} {x['name']}({MARKET_KO[x['market']]})" for x in near]}] if near else []
        ask = [f"{x['name'] if x['market'] == 'KR' else x['ticker']} 분석해 줘" for x in near]
        return {"status": "UNKNOWN_STOCK", "question": text, "ticker": code, "tab": "stock", "title": "스캔 대상이 아닌 종목입니다", "summary": say + (" 비슷한 종목을 아래에 적었습니다." if near else ""),
                "sections": maybe + [{"title": "할 수 있는 것", "lines": ["아래 버튼으로 종목 탭을 열면 시세와 재무를 보고, 순위·카드 탭의 '평가'에 코드를 넣으면 그 자리에서 점수를 계산합니다(처음에는 수십 초 걸릴 수 있습니다)."]}],
                "lines": [say], "follow": ask, "suggestions": near, "note": NOTE}
    if intent is None:
        say = "비서는 정해진 질문만 규칙으로 읽습니다. 아래 예 가운데 가까운 것을 누르거나 비슷하게 적어 주세요."
        return {"status": "UNKNOWN", "question": text, "title": "이 질문은 알아듣지 못했습니다", "summary": say,
                "sections": [{"title": "종목을 물었다면", "lines": ["회사명이 스캔 대상(미국 S&P 500, 한국 시가총액 상위 300)의 이름과 다르거나 대상이 아닐 수 있습니다. 종목 코드로 적어 보세요."]}],
                "lines": [say], "examples": examples_for(market), "note": NOTE}
    strategy = "LONG_TERM" if "장기" in text else "SWING"
    try:
        got = stock_answer(terminal, intent, stock, strategy) if stock else plain_answer(terminal, intent, market)
    except Exception as exc:                               # an unreadable source is said, never guessed around
        say = f"필요한 자료를 읽지 못했습니다({type(exc).__name__}). 자료 수집이 도는 중이거나 기록 파일을 읽지 못한 경우입니다."
        return {"status": "UNAVAILABLE", "question": text, "intent": intent, "title": "답을 만들지 못했습니다", "summary": say, "sections": [], "lines": [say], "follow": ["오늘 수집 됐어?"], "note": NOTE}
    return {"status": "REAL", "question": text, "intent": intent, "ticker": (stock or {}).get("ticker"), "market": (stock or {}).get("market", market), **got, "note": NOTE}


# ---------------------------------------------------------------------- the coin market (terminal/coin_bridge.py)
COIN_EXAMPLES = ["코인 상위는?", "코인 시장 상태 어때?", "비트코인 분석해 줘", "솔라나 점수 왜 이래?", "이 코인 점수 믿어도 돼?"]
COIN_TRUST = ["점수(α)는 사용자의 다른 프로젝트 horizon_bot_beta가 등록해 기록 중인 값입니다. 터미널은 그 값을 읽어 보여 줄 뿐 새 점수를 만들지 않습니다.",
              "신호 셋(자금조달비, 낮은 변동성, 낮은 베타)은 이미 본 과거 자료(2021~2026-08)에서 7일 기준으로 여섯 해 모두 같은 방향이었습니다. 다만 그 자료는 여러 번 본 것이라 증거가 아니고 후보를 고른 근거입니다.",
              "큰 코인 사이에서 모멘텀은 거꾸로 작동했고, 짧은 반전은 있지만 비용을 넘기에는 너무 빨리 사라졌습니다.",
              "돈으로 본 결과: 점수 1위 코인 하나를 산 시험은 -62.7%였습니다(같은 기간 대상 30개 평균 -79.2%, 비트코인 보유 +40.2%). 다른 코인보다 덜 떨어졌을 뿐 시장 하락을 견디지 못했습니다.",
              "시장 방향을 맞히려는 시험도 실패했습니다(예측과 실제의 상관 -0.08).",
              "판정은 앞으로의 기록으로 합니다(시장 중립 그림자 장부 2027-05-15). 그 전에는 이 점수를 '덜 나쁜 코인을 가리는 약한 순위'로만 읽는 것이 맞습니다."]


def _coin_time(close_ms: int) -> str:
    from zoneinfo import ZoneInfo
    return datetime.fromtimestamp(close_ms / 1000, timezone.utc).astimezone(ZoneInfo("Asia/Seoul")).strftime("%m월 %d일 %H:%M")


def _coin_label(r: Dict[str, Any]) -> str:
    return f"{r['name']}({r['coin']})" if r.get("name") else r["coin"]


def _usdt(v: Optional[float]) -> str:
    if v is None:
        return "자료 없음"
    return f"{v:,.2f} USDT" if v >= 1 else f"{v:.6f} USDT"


def _coin_read(terminal: Any = None) -> Dict[str, Any]:
    from terminal import coin_bridge
    return coin_bridge.read(base=getattr(terminal, "base", None))


def _simple(d: Dict[str, Any]) -> bool:
    """True on a machine without the predictor's files: the rank is the plain one made from public data, not the registered score."""
    return d.get("mode") == "SIMPLE"


def _coin_value(d: Dict[str, Any], r: Dict[str, Any]) -> str:
    """The figure the coin is ranked by, in words."""
    return f"간이 점수 {r['score']:.0f}점" if _simple(d) else f"{r['alpha'] * 100:+.2f}%"


def _coin_basis(d: Dict[str, Any]) -> str:
    return f"기준: {_coin_time(d['close_ms'])} 마감(4시간봉) · " + ("거래소 공개 시세로 만든 간이 순위(등록된 점수 아님)" if _simple(d) else f"horizon_bot_beta 점수 v{d.get('version')}")


def _coin_stale(d: Dict[str, Any]) -> Optional[str]:
    if d.get("status") != "STALE":
        return None
    if _simple(d):
        return (f"코인 시세가 {d['age_hours']:.0f}시간 전 마감({_coin_time(d['close_ms'])}) 기준입니다. 거래소에서 새 시세를 받지 못해 저장해 둔 값을 보여 줍니다"
                + (f"({d['fetch_error']})" if d.get("fetch_error") else "") + ". 인터넷 연결을 확인하세요. 10분 뒤 다시 받습니다.")
    return (f"코인 점수가 {d['age_hours']:.0f}시간 전 마감({_coin_time(d['close_ms'])}) 기준입니다. 4시간마다 새로 나와야 하는 값이라 오래된 것입니다. "
            "예측기가 멈췄거나 맥이 잠들어 있었습니다(horizon_bot_beta 폴더의 ./run_predictor.sh status 로 확인).")


def coin_items(d: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The coin day's list from one read of the bridge."""
    if d.get("status") == "UNAVAILABLE":
        return [item("DUE", "COIN_UNAVAILABLE", f"코인 자료를 읽지 못했습니다. {d.get('reason')}", tab="coin")]
    out = []
    stale = _coin_stale(d)
    if stale:
        out.append(item("DUE", "COIN_STALE", stale, tab="coin"))
    m, rows = d["market"], d["rows"]
    if _simple(d):
        out.append(item("INFO", "COIN_SIMPLE", d["mode_note"], tab="coin"))
    if m.get("btc_price") is not None:
        vs = f", 200일 평균보다 {m['btc_vs_200d'] * 100:+.1f}%" if m.get("btc_vs_200d") is not None else ""
        out.append(item("INFO", "COIN_MARKET", f"비트코인 {_usdt(m['btc_price'])}(7일 {(m.get('btc_change_7d') or 0) * 100:+.1f}%, 30일 {(m.get('btc_change_30d') or 0) * 100:+.1f}%{vs}). "
                        f"대상 {m['coins']}개 가운데 7일 동안 내린 코인이 {m['falling_7d']}개, 200일 평균 위에 있는 코인이 {m['above_200d']}개입니다.", tab="coin"))
    top = ", ".join(f"{_coin_label(r)} {_coin_value(d, r)}" for r in rows[:3])
    if _simple(d):
        out.append(item("INFO", "COIN_TOP", f"간이 순위 상위 3개({_coin_time(d['close_ms'])} 마감): {top}. 세 신호의 순위를 같은 비중으로 합친 점수(0~100)이고, 기대수익이 아니며 오를지 내릴지를 말하지 않습니다.", tab="coin"))
    else:
        out.append(item("INFO", "COIN_TOP", f"상대 순위 상위 3개({_coin_time(d['close_ms'])} 마감): {top}. 숫자는 7일 동안 대상의 중간 코인보다 더 오를 것으로 본 폭이고, 오를지 내릴지를 말하지 않습니다.", tab="coin"))
        over = [r for r in rows if r["beats_cost"]]
        out.append(item("INFO", "COIN_COST", f"기대 폭이 왕복 비용({d['cost_round_trip'] * 100:.2f}%)을 넘는 코인은 {len(over)}개입니다" + (f": {', '.join(_coin_label(r) for r in over[:5])}." if over else ". 지금은 순위 차이가 비용보다 작습니다."), tab="coin"))
    out.append(item("INFO", "COIN_CAVEAT", d["caveats"][-3] + " " + d["caveats"][-2], tab="coin"))      # the spot caveat and the result in money, in either mode
    return out


def coin_briefing(terminal: Any, now: Optional[Callable[[], datetime]] = None) -> Dict[str, Any]:
    at = (now or terminal.now)()
    failed: List[Dict[str, str]] = []
    try:
        d = _coin_read(terminal)
        items = coin_items(d)
    except Exception as exc:
        d, items = {}, []
        failed.append({"part": "coin", "label": "코인 예측기 자료", "error": type(exc).__name__})
    order = {lv: n for n, lv in enumerate(LEVELS)}
    items.sort(key=lambda i: order[i["level"]])
    return {"status": "REAL", "market": "COIN", "generated_at": at.isoformat(timespec="seconds"), "session": _coin_time(d["close_ms"]) + " 마감" if d.get("close_ms") else None,
            "headline": headline(items), "counts": {lv: sum(1 for i in items if i["level"] == lv) for lv in LEVELS}, "levels": LEVEL_KO, "orders": 0, "items": items,
            "unread_parts": failed, "note": ("코인 순위는 거래소 공개 시세로 만든 간이 순위입니다(등록된 점수 아님). " if _simple(d) else "코인 점수는 horizon_bot_beta의 예측기가 계산한 값을 읽어 보여 주는 것입니다. ") + NOTE}


def find_coin(text: str, rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    import re
    low = text.lower()
    for r in sorted(rows, key=lambda r: -len(r.get("name") or "")):
        if r.get("name") and r["name"] in text:
            return r
    tokens = {x.upper() for x in re.findall(r"[A-Za-z]{2,10}", text)}
    for r in rows:
        if r["coin"] in tokens or r["symbol"] in tokens:
            return r
    return next((r for r in rows if len(r["coin"]) >= 3 and r["coin"].lower() in low.split()), None)


def coin_note(d: Dict[str, Any], r: Dict[str, Any]) -> Dict[str, Any]:
    """One coin: where it ranks, the three signals behind the score with their real values, its price, and what the score cannot say."""
    n, label = r["of"], _coin_label(r)
    unit = " (1,000개 단위로 거래되는 계약)" if r.get("per_thousand") else ""
    cost = d["cost_round_trip"]
    if _simple(d):
        summary = (f"{label}의 간이 순위는 대상 {n}개 중 {r['rank']}위입니다(간이 점수 {r['score']:.0f}점, 0~100). 세 신호의 순위를 같은 비중으로 합친 값이고 등록된 점수(α)가 아니어서, "
                   "기대수익과 비용 비교가 없습니다. 오를지 내릴지를 말하는 값이 아닙니다.")
        recomputed = "참고: 위 수치는 터미널이 거래소 공개 시세에서 horizon_bot_beta와 같은 정의로 계산한 값입니다. 대상 30개를 최근 거래대금으로 골라, 그 예측기의 대상이나 순위와 다를 수 있습니다."
    else:
        summary = (f"{label}의 상대 순위는 대상 {n}개 중 {r['rank']}위입니다. 앞으로 7일 동안 대상의 중간 코인보다 {r['alpha'] * 100:+.2f}% 움직일 것으로 본 값이고, "
                   + ("왕복 비용({:.2f}%)을 넘습니다.".format(cost * 100) if r["beats_cost"] else "왕복 비용({:.2f}%)을 넘지 못합니다.".format(cost * 100)) + " 오를지 내릴지를 말하는 값이 아닙니다.")
        recomputed = "참고: 위 수치는 터미널이 예측기의 봉 자료에서 같은 정의로 다시 계산한 값이라, 예측기 안의 값과 조금 다를 수 있습니다."
    place = lambda k: f"대상 {n}개 중 낮은 순서로 {r[k]}위" if r.get(k) else "순위 없음"      # noqa: E731
    signals = []
    if r.get("funding") is not None:
        signals.append(f"자금조달비 {r['funding'] * 100:+.4f}%(8시간마다, 연으로 {r['funding_year'] * 100:+.1f}%): {place('funding_place')}. 낮거나 음수일수록 롱 쪽이 덜 붐빈다는 뜻이라 점수에 유리합니다. 현물에는 이 비용이 없습니다.")
    if r.get("sigma_day") is not None:
        signals.append(f"변동성 하루 약 {r['sigma_day'] * 100:.1f}%: {place('sigma_place')}. 낮을수록 점수에 유리합니다.")
    if r.get("beta") is not None:
        signals.append(f"베타 {r['beta']:.2f}(대상 코인 평균이 1% 움직일 때 이 코인이 움직이는 폭): {place('beta_place')}. 낮을수록 점수에 유리합니다.")
    px = [f"가격 {_usdt(r['price'])}{unit}.", "최근 움직임: " + ", ".join(f"{k} {v * 100:+.1f}%" for k, v in (("1일", r.get("change_1d")), ("7일", r.get("change_7d")), ("30일", r.get("change_30d"))) if v is not None) + ".",
          "200일 평균 " + ("위에 있습니다." if r.get("above_200d") else "아래에 있습니다." if r.get("above_200d") is not None else "자료가 모자랍니다.")]
    m = d["market"]
    market = [f"비트코인은 7일 {(m.get('btc_change_7d') or 0) * 100:+.1f}%, 200일 평균보다 {(m.get('btc_vs_200d') or 0) * 100:+.1f}%입니다. 대상 {m['coins']}개 가운데 {m['falling_7d']}개가 7일 동안 내렸습니다.", m["note"]]
    sections = [{"title": "먼저 알아 둘 것", "lines": [_coin_stale(d) or ""]}, {"title": "점수를 만든 신호 셋", "lines": signals + [recomputed]},
                {"title": "가격", "lines": px}, {"title": "시장", "lines": market}, {"title": "이 점수가 말하지 않는 것", "lines": d["caveats"]}]
    return reply(f"{label} 코인 노트", summary, sections, "coin", ["코인 상위는?", "코인 시장 상태 어때?", "이 코인 점수 믿어도 돼?"], _coin_basis(d))


def coin_answer(terminal: Any, text: str) -> Dict[str, Any]:
    """The coin market's fixed questions, answered from one read of the bridge."""
    text = " ".join(str(text or "").split())[:200]
    done = lambda got, intent, ticker=None: {"status": "REAL", "question": text, "intent": intent, "ticker": ticker, "market": "COIN", **got, "note": NOTE}      # noqa: E731
    try:
        d = _coin_read(terminal)
    except Exception as exc:
        say = f"코인 자료를 읽지 못했습니다({type(exc).__name__})."
        return {"status": "UNAVAILABLE", "question": text, "title": "답을 만들지 못했습니다", "summary": say, "sections": [], "lines": [say], "note": NOTE}
    if d.get("status") == "UNAVAILABLE":
        say = f"코인 자료를 읽지 못했습니다. {d.get('reason')}"
        return {"status": "UNAVAILABLE", "question": text, "title": "코인 자료 없음", "summary": say, "sections": [], "lines": [say], "tab": "coin", "note": NOTE}
    low = text.lower()
    rows, basis = d["rows"], _coin_basis(d)
    if any(w in low for w in ("믿", "신뢰", "근거", "정확", "검증")) and _simple(d):
        return done(reply("코인 간이 순위를 얼마나 믿을 수 있나", "지금 보이는 것은 간이 순위입니다. 수익으로 시험한 적이 없어, 등록된 점수보다도 근거가 약합니다.",
                          [{"title": "지금 보이는 순위", "lines": [d["mode_note"]]}, {"title": "등록된 점수에서 확인한 것 (참고)", "lines": COIN_TRUST[1:]},
                           {"title": "이 순위가 말하지 않는 것", "lines": d["caveats"][1:]}], "coin", ["코인 상위는?", "코인 시장 상태 어때?"], basis), "COIN_TRUST")
    if any(w in low for w in ("믿", "신뢰", "근거", "정확", "검증")):
        return done(reply("코인 점수를 얼마나 믿을 수 있나", "코인 점수는 대상 코인끼리의 약한 순위이고, 살 코인을 고르는 힘이 확인된 것은 아닙니다.", [{"title": "지금까지 확인한 것", "lines": COIN_TRUST},
                                                                                                         {"title": "이 점수가 말하지 않는 것", "lines": d["caveats"]}], "coin", ["코인 상위는?", "코인 시장 상태 어때?"], basis), "COIN_TRUST")
    coin = find_coin(text, rows)
    if coin:
        return done(coin_note(d, coin), "COIN_NOTE", coin["coin"])
    stale = _coin_stale(d)
    if any(w in low for w in ("시장", "상태", "분위기", "장세", "급락", "폭락", "떨어")):
        m = d["market"]
        lines = [f"비트코인 {_usdt(m['btc_price'])}: 7일 {(m.get('btc_change_7d') or 0) * 100:+.1f}%, 30일 {(m.get('btc_change_30d') or 0) * 100:+.1f}%.",
                 f"비트코인은 200일 평균보다 {m['btc_vs_200d'] * 100:+.1f}%입니다." if m.get("btc_vs_200d") is not None else "",
                 f"비트코인은 최근 1년 고점보다 {m['btc_from_high_1y'] * 100:+.1f}%입니다." if m.get("btc_from_high_1y") is not None else "",
                 f"대상 {m['coins']}개 가운데 7일 동안 내린 코인 {m['falling_7d']}개, 200일 평균 위에 있는 코인 {m['above_200d']}개({m['above_200d_of']}개 중).",
                 f"평균 자금조달비 {m['funding_mean'] * 100:+.4f}%(8시간): 음수면 숏이 롱에게 내는 상태, 곧 하락에 건 쪽이 붐빈다는 뜻입니다." if m.get("funding_mean") is not None else ""]
        fall = m["falling_7d"] == m["coins"]
        return done(reply("코인 시장 노트", f"대상 {m['coins']}개 가운데 {m['falling_7d']}개가 7일 동안 내렸습니다" + (": 전부입니다." if fall else ".") + " 순위가 높은 코인도 시장이 내리면 내립니다.",
                          [{"title": "먼저 알아 둘 것", "lines": [stale or ""]}, {"title": "지금의 모습", "lines": lines}, {"title": "읽을 때 주의", "lines": [m["note"], d["caveats"][0]]}], "coin",
                          ["코인 상위는?", "비트코인 분석해 줘", "이 코인 점수 믿어도 돼?"], basis), "COIN_MARKET")
    if any(w in low for w in ("상위", "순위", "후보", "추천", "뭐 살", "뭘 살", "1등", "1위", "오늘", "할 일", "요약")):
        top = [f"{r['rank']}위 {_coin_label(r)}: " + (_coin_value(d, r) if _simple(d) else f"기대 상대 폭 {r['alpha'] * 100:+.2f}%") + (" (비용을 넘음)" if r["beats_cost"] else "") + f", 7일 {(r.get('change_7d') or 0) * 100:+.1f}%, 하루 변동성 {(r.get('sigma_day') or 0) * 100:.1f}%." for r in rows[:5]]
        low_rows = [f"{r['rank']}위 {_coin_label(r)}: {_coin_value(d, r)}." for r in rows[-3:]]
        first = (f"간이 순위 1위는 {_coin_label(rows[0])}입니다({_coin_value(d, rows[0])}). 등록된 점수가 아니고, 순위일 뿐 매수 신호가 아닙니다." if _simple(d)
                 else f"상대 순위 1위는 {_coin_label(rows[0])}입니다({rows[0]['alpha'] * 100:+.2f}%, 7일 동안 대상의 중간 코인 대비). 순위일 뿐 매수 신호가 아닙니다.")
        return done(reply("코인 간이 순위" if _simple(d) else "코인 상대 순위", first,
                          [{"title": "먼저 알아 둘 것", "lines": [stale or ""]}, {"title": "상위 5개", "lines": top}, {"title": "하위 3개", "lines": low_rows}, {"title": "읽을 때 주의", "lines": d["caveats"][:3]}], "coin",
                          [f"{rows[0]['name'] or rows[0]['coin']} 분석해 줘", "코인 시장 상태 어때?", "이 코인 점수 믿어도 돼?"], basis), "COIN_TOP")
    help_ = text.lower().strip(" ?？!.") in ("", "help", "h", "도움", "도움말", "질문", "목록") or any(w in low for w in ("물어볼", "사용법", "명령어"))
    say = "코인 시장에서는 아래 다섯 가지를 물어볼 수 있습니다. 코인은 이름이나 기호로 적습니다(대상: " + ("최근 거래대금이 큰 30개" if _simple(d) else "예측기가 고른 30개") + ")." if help_ else "이 질문은 알아듣지 못했습니다. 코인 시장에서는 아래 질문을 알아듣습니다."
    return {"status": "REAL" if help_ else "UNKNOWN", "question": text, "intent": "COIN_HELP" if help_ else None, "market": "COIN", "title": "코인에 대해 물어볼 수 있는 것", "summary": say,
            "sections": [{"title": "대상 코인", "lines": [", ".join(r["coin"] for r in rows)]}], "lines": [say], "examples": COIN_EXAMPLES, "note": NOTE}

