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
from typing import Any, Callable, Dict, List, Optional

LEVELS = ("ACT", "DUE", "INFO")
LEVEL_KO = {"ACT": "먼저 볼 것", "DUE": "오늘 챙길 것", "INFO": "참고"}
STYLE_KO = {"LONG": "장기", "SWING": "스윙"}
MARKET_KO = {"US": "미국", "KR": "한국"}
NOTE = ("비서는 프로그램이 이미 계산한 것을 정해진 규칙으로 정리해 보여 줄 뿐입니다. 투자 자문이 아니고 주문을 실행하지 않습니다. "
        "점수가 높은 종목의 수익이 더 좋다는 근거는 아직 확인되지 않았습니다.")
EARNINGS_DAYS = 5          # a holding's earnings within this many days is due; the scan's own entry block is a separate rule
FRESH_READING_DAYS = 14    # a verdict is shown as new for this long after its report was written
FRESH_ALERT_HOURS = 36     # the user's own alert conditions that fired since about yesterday morning
SHOWN_ORDERS = 3
SWING_DAYS_LEFT = 3
PART_KO = {"account": "보유 종목 점검", "plan": "주문 계획", "market": "시장 상태", "earnings": "실적 일정", "alerts": "내 알림 조건", "job": "자료 수집 상태",
           "top": "점수 상위 종목", "changes": "직전 기록과 달라진 점", "readings": "판정 일정"}
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
        return [item("ACT", "JOURNAL_BROKEN", "거래 기록 검증에 실패해 보유 종목을 점검하지 못했습니다. 포트폴리오 탭의 안내를 확인하세요.", tab="portfolio")]
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


def plan_items(plan: Dict[str, Any], market: str) -> List[Dict[str, Any]]:
    """``plan``: Terminal.order_plan(market).  Quantities come from the account the user recorded; without one only the count is known."""
    status = plan.get("status")
    if status == "NO_SCAN":
        return [item("DUE", "NO_SCAN", f"{MARKET_KO[market]} 점수 기록이 없어 진입 후보를 만들지 못했습니다. 자료 수집 상태를 확인하세요.", tab="qsf")]
    n = plan.get("candidates") or 0
    if status == "NO_ACCOUNT":
        return [item("INFO", "NO_ACCOUNT", f"{MARKET_KO[market]} 계좌가 기록돼 있지 않아 주문 수량·손절·한도를 계산하지 못했습니다. 지금 진입 가능 구간으로 읽힌 후보는 스윙·장기 합쳐 {n}건입니다. "
                     "포트폴리오 탭에 입금과 거래를 기록하면 계좌 기준 계획과 보유 종목 점검이 만들어집니다.", tab="portfolio",
                     short=f"계좌 미기록(진입 가능 후보 {n}건)")]
    if status != "REAL":
        return [item("DUE", "PLAN_UNAVAILABLE", "주문 계획을 만들지 못했습니다.", tab="qsf")]
    orders, out = plan.get("orders") or [], []
    for o in orders[:SHOWN_ORDERS]:
        target = f", 목표 {price(o['target'], market)}" if o.get("target") else ""
        out.append(item("DUE", "ORDER", f"{o.get('name') or o['ticker']}({o['ticker']}) {STYLE_KO.get(o['style'], o['style'])} {o['shares']:,}주: 지정가 상한 {price(o['limit'], market)}, "
                        f"손절 {price(o['stop'], market)}{target}, 계좌 비중 {o['weight_pct']:.1f}%, 걸린 한도 {o.get('binding_label') or o.get('binding')}.", o["ticker"], "qsf"))
    if len(orders) > SHOWN_ORDERS:
        out.append(item("INFO", "ORDERS_MORE", f"주문 계획이 {len(orders) - SHOWN_ORDERS}건 더 있습니다. 점수 탭의 '주문 계획·모의 장부'에 모두 있습니다.", tab="qsf"))
    if not orders:
        why = sorted((plan.get("skipped_counts") or {}).items(), key=lambda kv: -kv[1])[:3]
        reasons = {s["code"]: s["reason"] for s in plan.get("skipped") or []}
        detail = "; ".join(f"{reasons.get(code, code)} {count}건" for code, count in why)
        out.append(item("INFO", "NO_ORDERS", f"오늘 계좌 한도 안에서 새로 낼 주문이 없습니다(후보 {n}건)." + (f" 빠진 이유: {detail}." if detail else ""), tab="qsf"))
    return out


def market_items(state: Optional[Dict[str, Any]], market: str) -> List[Dict[str, Any]]:
    """``state``: the day's market state (the regime factors, apart from every score)."""
    if not state or state.get("score_100") is None:
        return []
    score, factor, where = state["score_100"], float(state.get("size_factor") or 1.0), MARKET_KO[market]
    if state.get("state") == "ADVERSE" and factor < 1:
        return [item("DUE", "MARKET_ADVERSE", f"{where} 시장 상태 {score:.0f}/100({state.get('label')}): 새 주문의 위험 한도와 비중 한도를 {factor:g}배로 줄여 계산했습니다. "
                     "과거에 이런 날 뒤에는 변동성이 컸습니다.", tab="qsf", short=f"{score:.0f}/100({state.get('label')}, 새 주문 크기 {factor:g}배)")]
    if state.get("state") == "ADVERSE":
        return [item("INFO", "MARKET_ADVERSE", f"{where} 시장 상태 {score:.0f}/100({state.get('label')}). 이 시장은 과거 시험에서 이 값이 이후 수익이나 변동성을 가르지 못해 주문 크기는 그대로입니다.",
                     tab="qsf", short=f"{score:.0f}/100({state.get('label')})")]
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


def top_items(top3: Dict[str, Any], market: str) -> List[Dict[str, Any]]:
    """The frozen top three of the newest session, and whether they were written before the market opened."""
    days = (((top3.get("strategies") or {}).get("SWING") or {}).get("days")) or []
    if not days:
        return []
    day = max(days, key=lambda d: d.get("session") or "")
    names = ", ".join(f"{x.get('name') or x['ticker']}({x['ticker']}) {x['score']:.1f}점" for x in day.get("top") or [])
    if not names:
        return []
    brief = ", ".join(f"{(x.get('name') if market == 'KR' else None) or x['ticker']} {x['score']:.1f}" for x in day.get("top") or [])
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


def headline(items: List[Dict[str, Any]]) -> str:
    n = {lv: sum(1 for i in items if i["level"] == lv) for lv in LEVELS}
    if n["ACT"]:
        return f"먼저 볼 것이 {n['ACT']}건 있습니다. 손실과 관련된 항목입니다."
    if n["DUE"]:
        return f"먼저 볼 것은 없습니다. 오늘 챙길 것이 {n['DUE']}건 있습니다."
    return "오늘 따로 챙길 것이 없습니다."


def daily_lines(briefs: List[Dict[str, Any]]) -> List[str]:
    """Three lines for the daily message, both markets on each: market state, the top three, the order plan.
    Tickers and counts only: no amount and no quantity leaves the machine."""
    rows: Dict[str, List[str]] = {"시장 상태": [], "스윙 상위 3": [], "주문 계획": []}
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
        for label, text in (("시장 상태", (by.get("MARKET_ADVERSE") or by.get("MARKET_STATE") or {}).get("short")), ("스윙 상위 3", (by.get("TOP3") or {}).get("short")), ("주문 계획", plan)):
            if text:
                rows[label].append(f"{where} {text}")
    return [f"{label}: " + " · ".join(parts) for label, parts in rows.items() if parts]


# ---------------------------------------------------------------------- the day's list
def briefing(terminal: Any, market: str = "US", now: Optional[Callable[[], datetime]] = None) -> Dict[str, Any]:
    """The day's list for one market.  ``terminal``: terminal.services.Terminal.  Reads only; nothing is stored or sent."""
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
        return plan_items(got, market)

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
    part("market", market_state)
    part("earnings", lambda: earnings_items(terminal.qsf.earnings_upcoming(market, 14)))
    part("alerts", lambda: alert_items(terminal.alerts_view().get("log") or [], at))
    part("job", lambda: job_items(automation.status(base), automation.STEP_NAMES))
    part("top", lambda: top_items(terminal.qsf.top3(market), market))
    part("changes", lambda: change_items(qsf_changes.report(terminal.qsf.latest(market), terminal.qsf.ledger, market, "SWING"),
                                         {h["ticker"] for h in (seen.get("book") or {}).get("holdings") or []}))
    part("readings", readings)
    if any(i["kind"] == "NO_ACCOUNT" for i in items):
        items = [i for i in items if i["kind"] != "NO_HOLDINGS"]
    order = {lv: n for n, lv in enumerate(LEVELS)}
    items.sort(key=lambda i: order[i["level"]])          # a stable sort: inside a level the parts keep the order above
    plan_seen = seen.get("plan") or {}
    return {"status": "REAL", "market": market, "generated_at": at.isoformat(timespec="seconds"), "session": plan_seen.get("session"),
            "headline": headline(items), "counts": {lv: sum(1 for i in items if i["level"] == lv) for lv in LEVELS}, "levels": LEVEL_KO,
            "orders": len(plan_seen.get("orders") or []), "items": items, "unread_parts": failed, "note": NOTE}


# ---------------------------------------------------------------------- questions, read by keyword
STRATEGY_KO = {"SWING": "스윙", "LONG_TERM": "장기"}
ENTRY_KO = {"ENTRY_NOW": "지금 진입 가능 구간", "WAIT_FOR_PULLBACK": "눌림 대기", "WAIT_FOR_BREAKOUT_CONFIRMATION": "돌파 확인 대기", "WAIT_FOR_EARNINGS": "실적 발표 대기",
            "OVERVALUED_AT_CURRENT_PRICE": "현재 가격 고평가", "NO_VALID_ENTRY_SETUP": "유효한 진입 근거 없음"}
EXIT_KO = {"HOLD": "보유", "HOLD_AND_REVIEW": "보유하며 재검토", "PARTIAL_TAKE_PROFIT": "일부 차익 실현 검토", "REDUCE": "비중 축소 검토", "EXIT": "청산 검토",
           "THESIS_INVALIDATED": "투자 논리 무효", "TIME_STOP_REVIEW": "시간 손절 재평가"}
FACTOR_KO = {"trend_structure": "추세 구조", "relative_strength": "상대 강도", "momentum": "모멘텀", "breakout_volume": "돌파·거래량", "volatility_structure": "변동성 구조",
             "earnings_revenue_quality": "이익·매출의 질", "profitability": "수익성", "balance_sheet": "재무 상태", "cash_flow_quality": "현금흐름의 질", "risk_reward": "손익비",
             "atr_risk": "변동 폭 위험", "liquidity": "유동성", "drawdown_gap": "낙폭·갭 위험", "earnings_calendar": "실적 일정", "material_disclosures": "주요 공시",
             "insider_activity": "내부자 거래", "long_trend": "장기 추세", "momentum_persistence": "모멘텀 지속", "valuation": "가치(밸류에이션)", "business_quality": "사업의 질",
             "growth_quality": "성장의 질", "free_cash_flow": "잉여현금흐름", "balance_dilution": "주식 수 희석", "financial_resilience": "재무 복원력",
             "downside_drawdown": "하락 위험", "leverage": "부채", "governance": "지배구조", "material_events": "주요 사건", "insider_ownership": "내부자 지분",
             "capital_allocation": "자본 배분", "vix_regime": "변동성 지수", "vix_term": "변동성 기간 구조", "credit_spread": "신용 스프레드", "index_trend_breadth": "지수 추세·시장 폭",
             "vkospi_regime": "한국 변동성 지수", "index_trend": "지수 추세", "breadth": "시장 폭", "usdkrw_regime": "원·달러 환율", "credit_liquidity": "신용 스프레드"}
BUY_LINE = 70.0
# (key, an example the screen shows, needs a stock, words that mean it).  Read in this order: the first that fits answers.
STOCK_INTENTS = (
    ("STOP", "삼성전자 손절 어디?", ("손절", "목표", "손익비", "익절")),
    ("RANGE", "삼성전자 얼마까지 움직일까?", ("범위", "얼마까지", "예측", "움직", "오를", "내릴", "떨어질")),
    ("EARNINGS", "삼성전자 실적 언제?", ("실적", "발표")),
    ("SELL_CHECK", "삼성전자 팔아야 해?", ("팔", "매도", "정리", "청산")),
    ("BUY_CHECK", "삼성전자 사도 돼?", ("사도", "살까", "사면", "매수", "들어가", "진입", "담아")),
    ("RISK", "삼성전자 위험해?", ("위험", "회피", "공시", "경고", "조심")),
    ("RANK", "삼성전자 몇 등이야?", ("몇 등", "몇등", "순위", "등수")),
    ("WHY", "삼성전자 점수 왜 낮아?", ("왜", "이유", "점수", "어때", "평가")),
)
PLAIN_INTENTS = (
    ("HELP", "뭘 물어볼 수 있어?", ("도움", "물어볼", "질문 목록", "질문목록", "help", "사용법", "명령어")),
    ("TRUST", "이 점수 믿어도 돼?", ("믿", "신뢰", "근거", "정확", "검증됐")),
    ("COST", "수수료는 얼마로 계산해?", ("수수료", "비용", "세금", "거래세")),
    ("ALERTS", "걸어 둔 알림 뭐 있어?", ("알림",)),
    ("VERDICTS", "판정은 언제 나와?", ("판정", "언제 나와", "검증 결과")),
    ("JOB", "오늘 수집 됐어?", ("수집", "기록 됐", "기록됐", "돌았", "실패", "백업")),
    ("CHANGES", "어제와 뭐가 달라졌어?", ("달라", "변화", "바뀐", "바뀌", "변했")),
    ("MARKET", "시장 상태 어때?", ("시장", "국면", "장세", "분위기")),
    ("HOLDINGS", "내 보유 종목 괜찮아?", ("보유", "내 종목", "계좌", "포트")),
    ("TOP", "오늘 상위 종목은?", ("상위", "후보", "추천", "뭐 살", "뭘 살", "1등", "1위")),
    ("TODAY", "오늘 뭐 해야 해?", ("오늘", "할 일", "할일", "브리핑", "뭐 해", "뭘 해", "요약")),
)
EXAMPLES = [e for _, e, _ in PLAIN_INTENTS[::-1]] + [e for _, e, _ in STOCK_INTENTS[::-1]]
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
    if has_stock:
        return next((key for key, _, words in STOCK_INTENTS if any(w in low for w in words)), "WHY")
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


def _domains(snap: Dict[str, Any]) -> str:
    from terminal.qsf import config
    parts = [f"{config.DOMAIN_LABELS.get(k, k)} {v['score_100']:.0f}" for k, v in (snap.get("domains") or {}).items() if not v.get("reference") and v.get("score_100") is not None and v.get("points") is not None]
    return ", ".join(parts)


def _score_line(row: Dict[str, Any]) -> str:
    return f"{STRATEGY_KO[row['strategy']]} {row['score']:.1f}점({row.get('band_label')}, {row.get('action_label')})"


def stock_answer(terminal: Any, intent: str, stock: Dict[str, str], strategy: str) -> Dict[str, Any]:
    """One stock, from the stored scan only: nothing is fetched and nothing is scored again."""
    market, ticker = stock["market"], stock["ticker"]
    rows = {r["strategy"]: r for r in _rows(terminal, market) if r["ticker"] == ticker}
    row, snap = rows.get(strategy), _snap(terminal, stock, strategy)
    head = f"{stock['name']}({ticker})"
    if row is None or snap is None or row.get("score") is None:
        return {"title": head, "lines": [f"{STRATEGY_KO[strategy]} 점수가 최신 기록에 없습니다. 종목 탭에서 조회하면 그 자리에서 평가합니다."], "tab": "stock"}
    both = " · ".join(_score_line(r) for r in (rows.get("SWING"), rows.get("LONG_TERM")) if r and r.get("score") is not None)
    session = snap.get("data_date")
    gates = [g.get("text") or g.get("code") for g in snap.get("gates") or []]
    kind = STRATEGY_KO[strategy]
    if intent == "WHY":
        lines = [f"{both}. 기준 거래일 {session}.", f"{kind} 점수의 영역별 점수(100점 만점): {_domains(snap)}.",
                 f"점수를 가장 깎은 요인: {_factors(snap, True)}.", f"점수를 가장 올린 요인: {_factors(snap, False)}.",
                 f"진입 판단: {ENTRY_KO.get(snap.get('entry_status'), snap.get('entry_status'))}. 데이터 반영률 {(snap.get('coverage') or 0) * 100:.0f}%."]
        if gates:
            lines.append("차단 조건: " + "; ".join(gates) + ".")
        return {"title": f"{head} 점수가 이렇게 나온 이유", "lines": lines, "tab": "stock"}
    if intent == "RANK":
        scored = sorted((r["score"] for r in _rows(terminal, market) if r["strategy"] == strategy and r.get("score") is not None), reverse=True)
        place = scored.index(row["score"]) + 1
        return {"title": f"{head} 순위", "lines": [f"{kind} 점수 {row['score']:.1f}점은 {session}에 점수가 나온 {len(scored)}종목 중 {place}위(상위 {place / len(scored) * 100:.0f}%)입니다.",
                                                  "순위가 높다고 수익이 더 좋았다는 근거는 아직 확인되지 않았습니다."], "tab": "qsf"}
    if intent == "STOP":
        hold = snap.get("holding") or {}
        lines = []
        if snap.get("stop"):
            lines.append(f"{kind} 기준 손절선 {price(snap['stop'], market)}, 기준 종가 {price(snap.get('price'), market)}" + (f", 목표 {price(snap['target'], market)}" if snap.get("target") else "") + ".")
        if hold.get("reward_risk") is not None:
            lines.append(f"비용을 반영한 손익비는 {hold['reward_risk']:.2f}입니다(1 미만이면 기대 이익이 감수할 손실보다 작다는 뜻).")
        lines += [f"무효 조건: {x}." for x in (hold.get("invalidation") or [])[:2]]
        if hold.get("gap_note"):
            lines.append(hold["gap_note"])
        return {"title": f"{head} 손절·목표", "lines": lines or [f"{kind} 기록에 손절선이 없습니다. 장기 보유의 손절은 직접 정한 값(주문 계획에서는 변동 폭의 5배)을 씁니다."], "tab": "stock"}
    if intent == "RANGE":
        from terminal.qsf import forecast
        got = forecast.stock(terminal.base, market, ticker)
        if got.get("status") != "REAL":
            return {"title": f"{head} 가격 범위", "lines": ["이 종목의 가격 범위 기록이 없습니다."], "tab": "stock"}
        lines = []
        for h, r in sorted((got.get("ranges") or {}).items(), key=lambda kv: int(kv[0])):
            lines.append(f"{h}거래일 뒤 종가: 80% 가능성으로 {price(r['p80'][0], market)} ~ {price(r['p80'][1], market)}, 50% 가능성으로 {price(r['p50'][0], market)} ~ {price(r['p50'][1], market)}.")
        lines.append(f"기준 종가 {price(got.get('close'), market)}({got.get('session')}). 범위의 폭은 과거 자료로 맞춰 본 값이고, 오를지 내릴지는 말하지 않습니다(방향 예측력은 0으로 계산).")
        return {"title": f"{head} 가격 범위", "lines": lines, "tab": "stock"}
    if intent == "EARNINGS":
        raw = next((f.get("raw") or {} for f in snap.get("factors") or [] if f.get("factor") == "earnings_calendar" and isinstance(f.get("raw"), dict)), {})
        if not raw.get("next_earnings"):
            return {"title": f"{head} 실적 발표", "lines": ["저장된 다음 실적 발표일이 없습니다."], "tab": "assist"}
        basis = " 회사가 확정한 날짜가 아니라 과거 발표일로 추정한 값입니다." if raw.get("basis") == "ESTIMATE" else " 회사 확정 전에는 추정치일 수 있습니다."
        return {"title": f"{head} 실적 발표", "lines": [f"다음 실적 발표 {raw['next_earnings']}" + (f"(약 {raw['sessions']}거래일 뒤)" if raw.get("sessions") is not None else "") + "." + basis,
                                                     "스윙은 발표가 임박하면 새 진입을 막습니다."], "tab": "assist"}
    marks = []
    if row.get("high_risk"):
        marks.append("고위험 표시(변동성·낙폭이 대상 중 하위)")
    filing = row.get("filing_events") or {}
    if filing.get("financing"):
        marks.append("최근 자금 조달 공시(과거 시험에서 이후 수익이 부진했던 유형)")
    notes = ["자사주 취득 공시가 있습니다(시장 대비 우위는 확인되지 않아 좋게도 나쁘게도 세지 않습니다)."] if filing.get("buyback") else []
    if intent == "RISK":
        lines = ["차단 조건: " + ("; ".join(gates) if gates else "없음") + ".", "회피 표시: " + ("; ".join(marks) if marks else "없음") + ".", *notes,
                 f"위험 영역에서 가장 낮은 요인: {_factors({**snap, 'factors': [f for f in snap.get('factors') or [] if f.get('domain') == 'RISK']}, True, 2)}."]
        if row.get("high_risk_unknown") or row.get("filing_unknown"):
            lines.append("일부 표시는 자료가 없어 확인하지 못했습니다. 표시가 없다는 것이 안전하다는 뜻은 아닙니다.")
        return {"title": f"{head} 위험 점검", "lines": lines, "tab": "stock"}
    held = False
    try:
        held = ticker in terminal._book(market)[2]["positions"]
    except Exception:
        pass
    if intent == "SELL_CHECK":
        if not held:
            return {"title": f"{head} 매도 점검", "lines": ["보유 기록이 없어 매도 조건을 계산하지 않습니다. 매도 조건은 매수가, 보유 기간, 손절선이 있어야 읽을 수 있습니다.",
                                                         f"참고: {both}."], "tab": "portfolio"}
        sig = next((s for s in terminal.portfolio_signals(market)["items"] if s.get("ticker") == ticker), None)
        if not sig or sig.get("status") != "REAL":
            return {"title": f"{head} 매도 점검", "lines": ["자료를 읽지 못해 매도 조건을 점검하지 못했습니다."], "tab": "portfolio"}
        ex = sig["exit"]
        lines = [f"보유 판단: {EXIT_KO.get(ex['action'], ex['action'])}. {ex['reason']}"] + [f"걸린 조건: {c['text']}" for c in ex.get("conditions") or [] if c.get("action") != "HOLD"][:5]
        return {"title": f"{head} 매도 점검", "lines": lines + ["판단은 규칙이 읽은 것이고 주문은 직접 정합니다."], "tab": "portfolio"}
    # BUY_CHECK: a checklist, never an answer of yes or no
    state = terminal.market_state(market)
    raw = next((f.get("raw") or {} for f in snap.get("factors") or [] if f.get("factor") == "earnings_calendar" and isinstance(f.get("raw"), dict)), {})

    def check(ok: Optional[bool], text: str) -> str:
        return ("○ " if ok else "✕ " if ok is False else "– ") + text
    soon = raw.get("sessions") is not None and raw["sessions"] <= 5
    lines = [check(row["score"] >= BUY_LINE, f"점수 구간: {kind} {row['score']:.1f}점({row.get('band_label')}). 매수 후보 구간은 {BUY_LINE:g}점 이상입니다."),
             check(snap.get("entry_status") == "ENTRY_NOW", f"진입 판단: {ENTRY_KO.get(snap.get('entry_status'), snap.get('entry_status'))}."),
             check(not gates, "차단 조건: " + ("; ".join(gates) if gates else "없음") + "."),
             check(not soon if raw.get("next_earnings") else None, f"실적 발표: {raw.get('next_earnings') or '날짜 없음'}" + (" (임박)" if soon else "") + "."),
             check(not marks, "회피 표시: " + ("; ".join(marks) if marks else "없음") + "."),
             check(state.get("state") != "ADVERSE" if state.get("score_100") is not None else None,
                   f"시장 상태: {state.get('score_100', 0):.0f}/100({state.get('label')})." if state.get("score_100") is not None else "시장 상태: 자료 없음."),
             check(not held, "이미 보유 중입니다." if held else "보유 기록 없음.")]
    passed = sum(1 for x in lines if x.startswith("○"))
    lines += [f"– 참고: {x}" for x in notes]
    lines.append(f"{len(lines) - len(notes)}개 중 {passed}개가 걸림 없이 통과했습니다. 이 점검표는 살지 말지에 대한 답이 아닙니다. 점수 구간의 수익 근거는 아직 확인되지 않았고, 수량과 손절은 주문 계획에서 계좌 기준으로 봅니다.")
    return {"title": f"{head} 매수 전 점검표({kind})", "lines": lines, "tab": "stock"}


def plain_answer(terminal: Any, intent: str, market: str) -> Dict[str, Any]:
    from terminal import automation
    from terminal.qsf import changes as qsf_changes, config, readings as qsf_readings
    where, base = MARKET_KO[market], Path(terminal.base)
    texts = lambda items: [i["text"] for i in items]      # noqa: E731
    if intent == "HELP":
        return {"title": f"물어볼 수 있는 것 {len(EXAMPLES)}가지", "examples": EXAMPLES,
                "lines": ["정해진 질문만 알아듣습니다. 아래 예를 누르거나 비슷하게 적으면 됩니다.",
                          f"종목 없이 묻는 것 {len(PLAIN_INTENTS)}가지: " + " / ".join(e for _, e, _ in PLAIN_INTENTS[::-1]),
                          f"종목을 넣어 묻는 것 {len(STOCK_INTENTS)}가지: " + " / ".join(e for _, e, _ in STOCK_INTENTS[::-1]),
                          "종목은 '삼성전자' 자리에 코드, 티커, 회사명을 적습니다(스캔 대상: 미국 S&P 500, 한국 시가총액 상위 300). '장기'를 넣으면 장기 점수로 답합니다.",
                          "이 목록은 'help', '도움말', '?'로 언제든 다시 볼 수 있습니다."]}
    if intent == "TODAY":
        brief = briefing(terminal, market)
        return {"title": f"오늘 할 일({where})", "lines": [brief["headline"]] + [f"[{i['level_label']}] {i['text']}" for i in brief["items"] if i["level"] != "INFO"][:8]
                + ([] if brief["counts"]["ACT"] + brief["counts"]["DUE"] else ["참고 항목은 아래 목록에 있습니다."]), "tab": "today"}
    if intent == "TRUST":
        return {"title": "이 점수를 얼마나 믿을 수 있나", "lines": [config.VALIDATION_NOTICE, "지금까지 근거가 나온 것은 한국의 회피 쪽(자금 조달 공시, 위험 등급)과 가격 범위의 폭입니다. 살 종목을 고르는 힘은 확인되지 않았습니다.",
                                                         "앞으로의 기록으로 한 번씩 판정합니다(스윙 2027년 말, 장기 2030년쯤). 일정은 점수 탭의 '추적·검증'에 있습니다."], "tab": "qsf"}
    if intent == "COST":
        c = config.COSTS[market]
        return {"title": f"{where} 거래 비용 가정", "lines": [f"왕복 {config.round_trip_cost(market) * 100:.2f}%로 계산합니다.", str(c.get("basis") or ""), "스프레드와 슬리피지는 가정값이라 실제와 다를 수 있습니다."], "tab": "qsf"}
    if intent == "ALERTS":
        view = terminal.alerts_view()
        rules = [r for r in view.get("rules") or [] if r.get("status") == "ACTIVE"]
        fired = texts(alert_items(view.get("log") or [], terminal.now()))
        return {"title": "내 알림 조건", "lines": ([f"켜 둔 조건 {len(rules)}개: " + "; ".join(r.get("name") or r.get("type") for r in rules[:8]) + "."] if rules else ["켜 둔 알림 조건이 없습니다. 매매 보조 탭의 알림 센터에서 추가합니다."])
                + (fired or ["어제 아침 이후 발생한 알림이 없습니다."]), "tab": "assist"}
    if intent == "VERDICTS":
        got = qsf_readings.status(base, terminal.now().date(), automation.readings_state(base))
        waiting = sorted((r for r in got["readings"] if r.get("state") == "WAITING" and r.get("expected")), key=lambda r: r["expected"])
        read = [f"{r['label']}: {r.get('verdict')} ({r.get('meaning')})" for r in got["readings"] if r.get("state") == "READ"]
        nxt = [f"다음 판정: {r['label']} · {r['expected']} 무렵({r['left']}거래일 남음)." for r in waiting[:3]]
        return {"title": "판정 일정", "lines": [f"판정 {got['total']}건 중 {got['read']}건을 읽었습니다. 때가 되면 매일 작업이 스스로 읽고 텔레그램으로 알립니다."] + read[:5] + nxt, "tab": "qsf"}
    if intent == "JOB":
        st = automation.status(base)
        done = [f"{automation.STEP_NAMES.get(n, n)} {s.get('status')}" for n, s in (st.get("steps") or {}).items()]
        return {"title": "자료 수집 상태", "lines": [f"최근 기준 거래일 {st.get('latest_session')}. " + ", ".join(done) + "."] + (texts(job_items(st, automation.STEP_NAMES)) or ["실패한 단계가 없습니다."])
                + texts([i for i in top_items(terminal.qsf.top3(market), market) if i["kind"] == "RECORD_LATE"]), "tab": "lab"}
    if intent == "CHANGES":
        ch = qsf_changes.report(terminal.qsf.latest(market), terminal.qsf.ledger, market, "SWING")
        if ch.get("status") != "REAL":
            return {"title": "직전 기록과 달라진 점", "lines": ["비교할 직전 기록이 없습니다."], "tab": "qsf"}
        move = lambda r: f"{r.get('name') or r['ticker']}({r['ticker']}) {r['previous_score']:.1f} → {r['score']:.1f}"      # noqa: E731
        return {"title": f"{where} 스윙 점수: {ch.get('previous_session')} → {ch.get('session')}", "lines": (texts(change_items(ch)) or ["매수 후보 구간을 드나든 종목이 없습니다."])
                + ["가장 많이 오른 점수: " + "; ".join(move(r) for r in (ch.get("up") or [])[:3]) + ".", "가장 많이 내린 점수: " + "; ".join(move(r) for r in (ch.get("down") or [])[:3]) + "."], "tab": "qsf"}
    if intent == "MARKET":
        state = terminal.market_state(market)
        if state.get("score_100") is None:
            return {"title": f"{where} 시장 상태", "lines": ["시장 상태 기록이 없습니다."], "tab": "qsf"}
        parts = [f"{FACTOR_KO.get(f['factor'], f['factor'])} {f['normalized'] * 100:.0f}/100" if f.get("normalized") is not None else f"{FACTOR_KO.get(f['factor'], f['factor'])} 자료 없음" for f in state.get("factors") or []]
        return {"title": f"{where} 시장 상태({state.get('session')})", "lines": texts(market_items(state, market)) + ["구성 요인: " + ", ".join(parts) + ".", str(state.get("note") or "")], "tab": "qsf"}
    if intent == "HOLDINGS":
        book = terminal.portfolio(market)
        return {"title": f"{where} 보유 종목 점검", "lines": texts(holding_items(book, terminal.portfolio_signals(market)["items"] if book.get("holdings") else [], market)), "tab": "portfolio"}
    plan = terminal.order_plan(market)                     # TOP
    return {"title": f"{where} 점수 상위와 진입 후보", "lines": texts(top_items(terminal.qsf.top3(market), market)) + texts(plan_items(plan, market)), "tab": "qsf"}


def answer(terminal: Any, text: str, market: str = "US") -> Dict[str, Any]:
    """A typed line read by keyword.  It answers the fixed questions in ``EXAMPLES`` and says so when it does not know one."""
    text = " ".join(str(text or "").split())[:200]
    if not text:
        return {"status": "UNKNOWN", "title": "질문이 비어 있습니다", "lines": ["아래 예처럼 물어보세요."], "examples": EXAMPLES, "note": NOTE}
    if text.lower().strip(" ?？!.") in ("", "help", "h", "도움", "도움말", "질문", "목록"):
        text = "help"
    stock = None if text == "help" else find_stock(text, {m: _rows(terminal, m) for m in ("KR", "US")})
    intent = read_question(text, stock is not None)
    if intent is None:
        return {"status": "UNKNOWN", "question": text, "title": "이 질문은 알아듣지 못했습니다",
                "lines": ["비서는 정해진 질문만 규칙으로 읽습니다. 종목을 물었다면 스캔 대상(미국 S&P 500, 한국 시가총액 상위 300)이 아니거나 이름이 달라서일 수 있습니다. 종목 탭에서 코드로 조회해 보세요."],
                "examples": EXAMPLES, "note": NOTE}
    strategy = "LONG_TERM" if "장기" in text else "SWING"
    try:
        got = stock_answer(terminal, intent, stock, strategy) if stock else plain_answer(terminal, intent, market)
    except Exception as exc:                               # an unreadable source is said, never guessed around
        return {"status": "UNAVAILABLE", "question": text, "intent": intent, "title": "답을 만들지 못했습니다", "lines": [f"필요한 자료를 읽지 못했습니다({type(exc).__name__})."], "note": NOTE}
    return {"status": "REAL", "question": text, "intent": intent, "ticker": (stock or {}).get("ticker"), "market": (stock or {}).get("market", market), **got,
            "lines": [x for x in got["lines"] if x], "note": NOTE}
