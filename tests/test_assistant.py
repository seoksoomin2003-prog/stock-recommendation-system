"""The assistant (terminal/assistant.py): the day's list and the fixed questions.  Rules on plain data, a stand-in terminal, no network."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from terminal import assistant as A, server
from terminal.automation import Daily

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)
kinds = lambda items: [i["kind"] for i in items]                 # noqa: E731
by_kind = lambda items: {i["kind"]: i for i in items}            # noqa: E731


# ---------------------------------------------------------------------- the rules of the day's list
def holding(ticker, **kw):
    return {"ticker": ticker, "close": 100.0, "stop": 90.0, "target": 130.0, "weight_pct": 5.0, "style": "SWING", **kw}


def signal(ticker, action="HOLD", code="X", left=None):
    return {"status": "REAL", "ticker": ticker, "sessions_left": left, "time_limit": "2026-12-01",
            "exit": {"action": action, "reason": "이유.", "conditions": [{"code": code, "action": action, "text": "조건"}]}}


def test_holdings_are_sorted_into_loss_date_and_calm():
    book = {"integrity": {"status": "OK"}, "holdings": [holding("AAA"), holding("BBB"), holding("CCC"), holding("DDD")],
            "alerts": [{"level": "bad", "code": "STOP_HIT", "ticker": "AAA", "text": "AAA: 종가가 손절가 이하입니다."},
                       {"level": "warn", "code": "NO_STOP", "ticker": "BBB", "text": "BBB: 손절가가 설정되지 않았습니다."}]}
    got = A.holding_items(book, [signal("AAA", "EXIT", "STOP_BREACH"), signal("BBB"), signal("CCC", "REDUCE", "MOMENTUM_DETERIORATION"), signal("DDD", left=2)], "US")
    k = by_kind(got)
    assert k["STOP_HIT"]["level"] == "ACT" and k["NO_STOP"]["level"] == "DUE" and k["QSF_REDUCE"]["level"] == "ACT" and k["QSF_REDUCE"]["ticker"] == "CCC"
    assert "QSF_EXIT" not in k                                   # the portfolio's own stop alert already says it
    assert k["SWING_LIMIT_NEAR"]["level"] == "DUE" and "2거래일" in k["SWING_LIMIT_NEAR"]["text"] and "HOLDINGS_CALM" not in k
    calm = A.holding_items({**book, "alerts": []}, [signal("AAA"), signal("BBB"), signal("CCC"), signal("DDD")], "US")
    assert kinds(calm) == ["HOLDINGS_CALM"] and "보유 4종목 중 4종목" in calm[0]["text"] and calm[0]["level"] == "INFO"
    assert kinds(A.holding_items({"integrity": {"status": "BROKEN"}, "holdings": [holding("AAA")]}, [], "US")) == ["JOURNAL_BROKEN"]
    assert kinds(A.holding_items({"integrity": {"status": "OK"}, "holdings": [], "alerts": []}, [], "KR")) == ["NO_HOLDINGS"]
    unread = A.holding_items({**book, "alerts": []}, [{"status": "UNAVAILABLE", "ticker": "AAA"}], "US")
    assert by_kind(unread)["SIGNAL_UNAVAILABLE"]["level"] == "DUE"


def order(ticker, shares=10):
    return {"ticker": ticker, "name": f"{ticker} Inc.", "style": "SWING", "shares": shares, "limit": 101.5, "stop": 95.0, "target": 115.0, "weight_pct": 4.2, "binding": "RISK", "binding_label": "거래당 위험"}


def test_the_order_plan_reads_by_what_the_account_allows():
    assert kinds(A.plan_items({"status": "NO_SCAN"}, "US")) == ["NO_SCAN"]
    none = A.plan_items({"status": "NO_ACCOUNT", "candidates": 322}, "US")[0]
    assert none["kind"] == "NO_ACCOUNT" and none["level"] == "INFO" and "322건" in none["text"] and none["short"] == "계좌 미기록(진입 가능 후보 322건)"
    plan = {"status": "REAL", "candidates": 9, "orders": [order(t) for t in ("AAA", "BBB", "CCC", "DDD", "EEE")]}
    got = A.plan_items(plan, "US")
    assert kinds(got) == ["ORDER", "ORDER", "ORDER", "ORDERS_MORE"] and got[0]["level"] == "DUE" and got[0]["ticker"] == "AAA"
    assert "10주" in got[0]["text"] and "$101.50" in got[0]["text"] and "손절 $95.00" in got[0]["text"] and "거래당 위험" in got[0]["text"] and "2건 더" in got[3]["text"]
    kr = A.plan_items({"status": "REAL", "candidates": 1, "orders": [{**order("005930"), "limit": 71200.0, "stop": 65000.0, "target": None}]}, "KR")
    assert "71,200원" in kr[0]["text"] and "목표" not in kr[0]["text"]
    empty = A.plan_items({"status": "REAL", "candidates": 7, "orders": [], "skipped_counts": {"NO_CASH": 5, "SECTOR_FULL": 2},
                          "skipped": [{"code": "NO_CASH", "reason": "현금 부족"}, {"code": "SECTOR_FULL", "reason": "섹터 한도"}]}, "US")
    assert kinds(empty) == ["NO_ORDERS"] and "현금 부족 5건" in empty[0]["text"] and "섹터 한도 2건" in empty[0]["text"]


def test_market_state_is_due_only_where_it_changes_the_order_size():
    us = A.market_items({"score_100": 15.4, "state": "ADVERSE", "label": "나쁨", "size_factor": 0.5}, "US")[0]
    kr = A.market_items({"score_100": 25.4, "state": "ADVERSE", "label": "나쁨", "size_factor": 1.0}, "KR")[0]
    ok = A.market_items({"score_100": 71.0, "state": "FAVORABLE", "label": "좋음", "size_factor": 1.0}, "US")[0]
    assert us["level"] == "DUE" and "0.5배" in us["text"] and us["short"] == "15/100(나쁨, 새 주문 크기 0.5배)"
    assert kr["level"] == "INFO" and "그대로" in kr["text"] and kr["short"] == "25/100(나쁨)" and ok["kind"] == "MARKET_STATE" and ok["level"] == "INFO"
    assert A.market_items(None, "US") == [] and A.market_items({"score_100": None}, "US") == []


def test_earnings_alerts_job_top_changes_and_verdicts():
    cal = {"items": [{"ticker": "AAA", "name": "A", "date": "2026-11-24", "days_away": 3, "held": True, "watched": False},
                     {"ticker": "BBB", "name": "B", "date": "2026-11-25", "days_away": 4, "held": False, "watched": True},
                     {"ticker": "CCC", "name": "C", "date": "2026-11-24", "days_away": 3, "held": False, "watched": False},
                     {"ticker": "DDD", "name": "D", "date": "2026-12-10", "days_away": 19, "held": True, "watched": False}]}
    e = A.earnings_items(cal)
    assert [(i["ticker"], i["level"]) for i in e] == [("AAA", "DUE"), ("BBB", "INFO")] and "3일 뒤" in e[0]["text"]
    log = [{"at": (NOW - timedelta(hours=5)).isoformat(), "text": "AAA 종가 100 이상", "ticker": "AAA"}, {"at": (NOW - timedelta(days=4)).isoformat(), "text": "옛 알림"}, {"at": "깨진 값", "text": "x"}]
    assert [i["text"] for i in A.alert_items(log, NOW)] == ["내 알림 조건 발생: AAA 종가 100 이상"]
    labels = {"QSF": "QSF 점수 기록(미국)", "NEWS_KR": "뉴스 기록(한국)"}
    job = A.job_items({"installed": True, "steps": {"QSF": {"status": "FAILED", "detail": "코드 2"}, "NEWS_KR": {"status": "FAILED", "detail": "거절"}, "SCAN": {"status": "OK"}},
                       "notes": ["한국 결합 점수 기록이 3거래일째 멈춰 있습니다."], "running": {"pid": 1}}, labels)
    k = by_kind(job)
    assert k["JOB_FAILED"]["level"] == "DUE" and "QSF 점수 기록(미국)(코드 2)" in k["JOB_FAILED"]["text"] and "뉴스" not in k["JOB_FAILED"]["text"]
    assert k["NEWS_FAILED"]["level"] == "INFO" and k["JOB_NOTE"]["level"] == "DUE" and "JOB_RUNNING" in k
    assert kinds(A.job_items({"installed": False, "steps": {}}, labels)) == ["JOB_NOT_INSTALLED", "JOB_NEVER"]
    assert A.job_items({"installed": True, "steps": {"SCAN": {"status": "OK"}}}, labels) == []
    top = {"strategies": {"SWING": {"days": [{"session": "2026-11-19", "top": []}, {"session": "2026-11-20", "entry_session": "2026-11-24", "before_open": False,
                                                                                    "top": [{"ticker": "138930", "name": "BNK금융지주", "score": 67.87}, {"ticker": "064350", "name": "현대로템", "score": 65.8}]}]}}}
    t = A.top_items(top, "KR")
    assert kinds(t) == ["TOP3", "RECORD_LATE"] and "BNK금융지주(138930) 67.9점" in t[0]["text"] and "매수 신호가 아닙니다" in t[0]["text"] and t[0]["short"].startswith("BNK금융지주 67.9, 현대로템 65.8")
    assert "2026-11-24" in t[1]["text"] and A.top_items({}, "US") == []
    us = A.top_items({"strategies": {"SWING": {"days": [{"session": "2026-11-20", "entry_session": "2026-11-23", "before_open": True, "top": [{"ticker": "TECH", "name": "Bio-Techne", "score": 76.4}]}]}}}, "US")
    assert kinds(us) == ["TOP3"] and us[0]["short"] == "TECH 76.4 (진입 2026-11-23)"
    ch = {"status": "REAL", "entered_buy": [{"ticker": "TECH", "name": "Bio-Techne"}], "left_buy": [{"ticker": "AAPL", "name": "Apple", "score": 69.8, "previous_score": 71.2}], "model_changed": True, "model_version": "QSF-9"}
    c = A.change_items(ch, {"AAPL"})
    assert kinds(c) == ["HELD_LEFT_BUY", "ENTERED_BUY", "LEFT_BUY", "MODEL_CHANGED"] and c[0]["level"] == "DUE" and "71.2 → 69.8" in c[0]["text"]
    assert kinds(A.change_items(ch)) == ["ENTERED_BUY", "LEFT_BUY", "MODEL_CHANGED"] and A.change_items({"status": "UNAVAILABLE"}) == []
    rows = [{"key": "a", "state": "READ", "label": "한국 묶음 도전자 점수 · 스윙", "verdict": "LIVE_BETTER", "meaning": "지금 공식이 나았습니다", "reasons": ["잰 것: 가~나."], "after": "바뀌지 않습니다."},
            {"key": "b", "state": "READ", "label": "옛 판정", "verdict": "NO_EVIDENCE"}, {"key": "c", "state": "DUE", "label": "막힌 판정", "attempts": 4}, {"key": "d", "state": "WAITING", "label": "기다림"}]
    r = A.reading_items(rows, {"a"})
    assert kinds(r) == ["NEW_VERDICT", "VERDICT_STUCK"] and "LIVE_BETTER" in r[0]["text"] and "잰 것: 가~나." in r[0]["text"] and "4번" in r[1]["text"]


def test_headline_and_the_daily_message_lines_carry_no_amount():
    it = lambda level: A.item(level, "X", "t")              # noqa: E731
    assert "먼저 볼 것이 2건" in A.headline([it("ACT"), it("ACT"), it("DUE")]) and "오늘 챙길 것이 1건" in A.headline([it("DUE"), it("INFO")]) and A.headline([it("INFO")]) == "오늘 따로 챙길 것이 없습니다."
    us = {"status": "REAL", "market": "US", "orders": 5, "items": A.market_items({"score_100": 15.4, "state": "ADVERSE", "label": "나쁨", "size_factor": 0.5}, "US")
          + A.plan_items({"status": "REAL", "candidates": 9, "orders": [order(t, shares=1234) for t in ("AAA", "BBB", "CCC", "DDD", "EEE")]}, "US")}
    kr = {"status": "REAL", "market": "KR", "orders": 0, "items": A.plan_items({"status": "NO_ACCOUNT", "candidates": 150}, "KR")
          + A.top_items({"strategies": {"SWING": {"days": [{"session": "2026-11-20", "entry_session": "2026-11-23", "top": [{"ticker": "138930", "name": "BNK금융지주", "score": 67.87}]}]}}}, "KR")}
    lines = A.daily_lines([us, kr, {"status": "UNAVAILABLE"}])
    assert lines == ["시장 상태: 미국 15/100(나쁨, 새 주문 크기 0.5배)", "스윙 상위 3: 한국 BNK금융지주 67.9 (진입 2026-11-23)", "주문 계획: 미국 5건(AAA, BBB, CCC 등) · 한국 계좌 미기록(진입 가능 후보 150건)"]
    assert "1234" not in "".join(lines) and "$" not in "".join(lines) and A.daily_lines([]) == []
    text = Daily.compose("2026-11-20", {}, {"status": "OK", "items": []}, [], [], brief=lines)
    assert "[오늘 볼 것]\n시장 상태: 미국 15/100" in text and "순위는 매수 신호가 아닙니다" in text
    assert "[오늘 볼 것]" not in Daily.compose("2026-11-20", {}, {"status": "OK", "items": []}, [], []) and "[오늘 볼 것]" not in Daily.compose("2026-11-20", {}, {"status": "OK", "items": []}, [], [], brief=[])


# ---------------------------------------------------------------------- a stand-in terminal
def factor(name, domain, weight, normalized, **kw):
    return {"factor": name, "domain": domain, "weight": weight, "normalized": normalized, "status": "REAL", **kw}


def snap(ticker, market, strategy, score, **kw):
    factors = [factor("risk_reward", "RISK", 6, 0.0), factor("atr_risk", "RISK", 5, 0.1), factor("balance_sheet", "FUNDAMENTAL", 3, 1.0), factor("liquidity", "RISK", 5, 0.9),
               factor("trend_structure", "TECHNICAL", 0, 0.95, scored=False), factor("earnings_calendar", "EVENTS", 4, 1.0, raw={"next_earnings": "2027-01-27", "sessions": 44, "basis": "ESTIMATE"})]
    return {"ticker": ticker, "market": market, "strategy": strategy, "score": score, "data_date": "2026-11-20", "price": 183100.0 if market == "KR" else 250.0, "stop": 158079.3 if market == "KR" else 230.0,
            "target": 208941.5 if market == "KR" else 290.0, "entry_status": "NO_VALID_ENTRY_SETUP", "coverage": 0.925, "gates": [], "factors": factors,
            "domains": {"RISK": {"score_100": 26.2, "points": 5.2}, "FUNDAMENTAL": {"score_100": 85.9, "points": 8.6}, "REGIME": {"score_100": 25.4, "points": 0.0, "reference": True}},
            "holding": {"reward_risk": 0.96, "invalidation": ["종가가 158,079.30 아래로 마감"], "gap_note": "손절은 체결을 보장하지 않습니다."}, **kw}


def row(ticker, name, strategy, score, **kw):
    return {"ticker": ticker, "name": name, "strategy": strategy, "score": score, "band_label": "보유·관찰", "action_label": "관찰", **kw}


class FakeLedger:
    def __init__(self, snaps):
        self.snaps = snaps

    def _index_stamp(self):
        return 1

    def _live_rows(self):
        return [{"market": m, "session": "2026-11-20"} for m in ("KR", "US")]

    def _load(self, r):
        return [s for s in self.snaps if s["market"] == r["market"]]

    def read_index(self):
        return {"status": "OK"}

    def session_before(self, market, session):
        return None


class FakeQsf:
    def __init__(self, base):
        self.base = base
        self.rows = {"KR": [row("005930", "삼성전자", "SWING", 53.9, filing_events={"financing": False, "buyback": True}), row("005930", "삼성전자", "LONG_TERM", 64.2),
                            row("005935", "삼성전자우", "SWING", 40.0), row("373220", "LG에너지솔루션", "SWING", 30.0, high_risk=True, filing_events={"financing": True, "buyback": False})],
                     "US": [row("AAPL", "Apple Inc.", "SWING", 71.5), row("A", "Agilent Technologies, Inc.", "SWING", 60.0), row("IT", "Gartner, Inc.", "SWING", 55.0), row("TECH", "Bio-Techne Corporation", "SWING", 76.4)]}
        self.ledger = FakeLedger([snap("005930", "KR", "SWING", 53.9), snap("005930", "KR", "LONG_TERM", 64.2), snap("005935", "KR", "SWING", 40.0),
                                  snap("373220", "KR", "SWING", 30.0, gates=[{"code": "SEVERE_EVENT", "text": "중대한 공시: 횡령·배임 (2026-10-14)"}]),
                                  snap("AAPL", "US", "SWING", 71.5, entry_status="ENTRY_NOW"), snap("A", "US", "SWING", 60.0), snap("IT", "US", "SWING", 55.0), snap("TECH", "US", "SWING", 76.4)])

    def latest(self, market):
        return {"status": "REAL", "session": "2026-11-20", "rows": self.rows[market]}

    def top3(self, market):
        return {"strategies": {"SWING": {"days": [{"session": "2026-11-20", "entry_session": "2026-11-23", "before_open": True, "top": [{"ticker": "TECH", "name": "Bio-Techne", "score": 76.4}]}]}}}

    def earnings_upcoming(self, market, days):
        return {"items": []}


class FakeTerminal:
    def __init__(self, base, held=(), plan=None, broken=()):
        self.base, self.held, self.plan, self.broken = base, set(held), plan or {"status": "NO_ACCOUNT", "candidates": 150, "session": "2026-11-20"}, set(broken)
        self.qsf = FakeQsf(base)
        self.now = lambda: NOW

    def _fail(self, name):
        if name in self.broken:
            raise OSError(name)

    def portfolio(self, market="US"):
        self._fail("portfolio")
        return {"integrity": {"status": "OK"}, "holdings": [holding(t) for t in sorted(self.held)], "alerts": []}

    def portfolio_signals(self, market="US"):
        return {"items": [signal(t, "REDUCE", "MOMENTUM_DETERIORATION") for t in sorted(self.held)]}

    def order_plan(self, market="US"):
        self._fail("plan")
        return self.plan

    def market_state(self, market="US"):
        return {"score_100": 25.4, "state": "ADVERSE", "label": "나쁨", "size_factor": 1.0, "session": "2026-11-20", "factors": [{"factor": "index_trend", "normalized": 0.0}], "note": "참고 표시입니다."}

    def alerts_view(self):
        return {"rules": [], "log": []}

    def _book(self, market="US"):
        return [], {"status": "OK"}, {"positions": {t: {} for t in self.held}}


@pytest.fixture(autouse=True)
def quiet_job(monkeypatch):
    """The job's state is this machine's own (launchd, the real state file): the tests read a fixed one."""
    from terminal import automation
    monkeypatch.setattr(automation, "status", lambda base: {"installed": True, "steps": {"SCAN": {"status": "OK"}}, "latest_session": "2026-11-20", "notes": []})
    monkeypatch.setattr(automation, "readings_state", lambda base: {})


@pytest.fixture()
def term(tmp_path):
    return FakeTerminal(tmp_path)


def test_the_briefing_orders_by_level_and_names_a_part_it_could_not_read(tmp_path):
    b = A.briefing(FakeTerminal(tmp_path), "KR")
    assert b["status"] == "REAL" and b["market"] == "KR" and b["session"] == "2026-11-20" and b["unread_parts"] == [] and b["note"] == A.NOTE
    assert "NO_ACCOUNT" in kinds(b["items"]) and "NO_HOLDINGS" not in kinds(b["items"])                 # one line says the account is not recorded
    levels = [A.LEVELS.index(i["level"]) for i in b["items"]]
    assert levels == sorted(levels) and b["counts"] == {lv: sum(1 for i in b["items"] if i["level"] == lv) for lv in A.LEVELS}
    held = A.briefing(FakeTerminal(tmp_path, held=["005930"], plan={"status": "REAL", "session": "2026-11-20", "candidates": 3, "orders": [order("373220")]}), "KR")
    assert held["items"][0]["kind"] == "QSF_REDUCE" and held["items"][0]["level"] == "ACT" and held["counts"]["ACT"] == 1 and held["orders"] == 1 and "먼저 볼 것이 1건" in held["headline"]
    cut = A.briefing(FakeTerminal(tmp_path, broken={"portfolio", "plan"}), "KR")
    assert [p["part"] for p in cut["unread_parts"]] == ["account", "plan"] and cut["unread_parts"][0]["label"] == "보유 종목 점검" and "TOP3" in kinds(cut["items"])


# ---------------------------------------------------------------------- questions
def test_a_line_names_a_scanned_stock_by_code_ticker_or_name(term):
    rows = {m: term.qsf.latest(m)["rows"] for m in ("KR", "US")}
    find = lambda text: (A.find_stock(text, rows) or {}).get("ticker")          # noqa: E731
    assert find("005930 손절 어디?") == "005930" and find("삼성전자 점수 왜 낮아?") == "005930" and find("삼성전자우 어때") == "005935"      # the longest name written wins
    assert find("AAPL 사도 돼?") == "AAPL" and find("aapl 왜") == "AAPL" and find("apple 왜 낮아") == "AAPL" and find("tech 실적 언제") == "TECH"
    assert find("it is a test") is None and find("IT 어때") == "IT" and find("오늘 뭐 해야 해?") is None and find("비트코인 전망") is None


def test_every_example_question_is_read_as_its_own_kind():
    for key, example, _ in A.STOCK_INTENTS:
        assert A.read_question(example, True) == key, example
    for key, example, _ in A.PLAIN_INTENTS:
        assert A.read_question(example, False) == key, example
    assert A.read_question("삼성전자", True) == "WHY" and A.read_question("비트코인 전망", False) is None
    assert len(A.EXAMPLES) == len(A.STOCK_INTENTS) + len(A.PLAIN_INTENTS) == 19


def test_stock_answers_come_from_the_stored_scan(term):
    why = A.answer(term, "삼성전자 점수 왜 낮아?", "US")
    assert why["status"] == "REAL" and why["intent"] == "WHY" and why["ticker"] == "005930" and why["market"] == "KR" and why["note"] == A.NOTE
    text = " ".join(why["lines"])
    assert "스윙 53.9점" in text and "장기 64.2점" in text and "손익비 0/100(배점 6)" in text and "재무 상태 100/100" in text and "추세 구조" not in text and "시장 국면" not in text      # reference rows are not the score
    buy = A.answer(term, "AAPL 사도 돼?", "KR")
    assert buy["intent"] == "BUY_CHECK" and buy["lines"][0].startswith("○ 점수 구간") and buy["lines"][1].startswith("○ 진입 판단") and buy["lines"][5].startswith("✕ 시장 상태")
    assert "살지 말지에 대한 답이 아닙니다" in buy["lines"][-1] and "7개 중" in buy["lines"][-1]
    for word in ("사세요", "매수하세요", "파세요", "매도하세요", "추천합니다"):
        assert word not in json.dumps(buy, ensure_ascii=False) and word not in json.dumps(why, ensure_ascii=False)
    kr = A.answer(term, "삼성전자 사도 돼?", "KR")
    assert kr["lines"][4].startswith("○ 회피 표시: 없음") and any(x.startswith("– 참고: 자사주 취득") for x in kr["lines"])       # a buyback is a note, not a mark against
    risk = A.answer(term, "LG에너지솔루션 위험해?", "KR")
    assert "횡령·배임" in risk["lines"][0] and "고위험 표시" in risk["lines"][1] and "자금 조달 공시" in risk["lines"][1]
    stop = A.answer(term, "005930 손절 어디?", "KR")
    assert "158,079원" in stop["lines"][0] and "208,942원" in stop["lines"][0] and "0.96" in stop["lines"][1]
    assert "2027-01-27" in A.answer(term, "삼성전자 실적 언제?", "KR")["lines"][0] and "추정한 값" in A.answer(term, "삼성전자 실적 언제?", "KR")["lines"][0]
    rank = A.answer(term, "TECH 몇 등이야?", "KR")
    assert "4종목 중 1위" in rank["lines"][0] and "근거는 아직 확인되지 않았습니다" in rank["lines"][1]
    sell = A.answer(term, "삼성전자 팔아야 해?", "KR")
    assert sell["intent"] == "SELL_CHECK" and "보유 기록이 없어" in sell["lines"][0]
    held = A.answer(FakeTerminal(term.base, held=["005930"]), "삼성전자 팔아야 해?", "KR")
    assert "비중 축소 검토" in held["lines"][0] and "주문은 직접 정합니다" in held["lines"][-1]
    assert A.answer(term, "삼성전자 장기 점수", "KR")["lines"][1].startswith("장기 점수의 영역별")


def test_plain_answers_and_what_it_does_not_know(term):
    assert A.answer(term, "시장 상태 어때?", "KR")["intent"] == "MARKET" and "지수 추세 0/100" in " ".join(A.answer(term, "시장 상태 어때?", "KR")["lines"])
    assert "왕복 0.53%" in A.answer(term, "수수료는 얼마로 계산해?", "KR")["lines"][0]
    assert A.answer(term, "오늘 상위 종목은?", "US")["lines"][0].startswith("미국 스윙 점수 상위 3종목")
    for typed in ("뭘 물어볼 수 있어?", "help", "도움말", "?", "명령어 뭐 있어"):
        got = A.answer(term, typed, "KR")
        assert got["status"] == "REAL" and got["intent"] == "HELP" and got["examples"] == A.EXAMPLES and "19가지" in got["title"], typed
        assert "종목 없이 묻는 것 11가지" in got["lines"][1] and "종목을 넣어 묻는 것 8가지" in got["lines"][2] and "'help'" in got["lines"][-1]
    trust = A.answer(term, "이 점수 믿어도 돼?", "KR")
    assert trust["intent"] == "TRUST" and "확인되지 않았습니다" in trust["lines"][1]
    today = A.answer(term, "오늘 뭐 해야 해?", "KR")
    assert today["intent"] == "TODAY" and today["tab"] == "today" and today["lines"][0] == "오늘 따로 챙길 것이 없습니다."
    unknown = A.answer(term, "비트코인 전망", "KR")
    assert unknown["status"] == "UNKNOWN" and unknown["examples"] == A.EXAMPLES and "알아듣지 못했습니다" in unknown["title"]
    assert A.answer(term, "   ", "KR")["status"] == "UNKNOWN" and A.answer(term, "HELP 삼성전자", "KR")["intent"] != "HELP" and len(A.answer(term, "가" * 500 + " 시장", "KR")["question"]) <= 200
    broken = FakeTerminal(term.base)
    broken.market_state = lambda market="US": (_ for _ in ()).throw(OSError("x"))
    lost = A.answer(broken, "시장 상태 어때?", "KR")
    assert lost["status"] == "UNAVAILABLE" and "OSError" in lost["lines"][0]


# ---------------------------------------------------------------------- wiring
def test_the_assistant_asks_no_network_and_is_wired_into_the_server_and_the_first_screen(term):
    src = (ROOT / "terminal" / "assistant.py").read_text(encoding="utf-8")
    for banned in ("import requests", "urllib", "http://", "https://", "openai", "anthropic", "socket"):
        assert banned not in src, banned
    r = server.routes(term)
    assert r[("GET", "/api/assistant/today")]({"market": "KR"}, {})["status"] == "REAL"
    assert r[("POST", "/api/assistant/ask")]({}, {"q": "AAPL 왜?", "market": "US"})["intent"] == "WHY"
    with pytest.raises(ValueError):
        r[("GET", "/api/assistant/today")]({"market": "JP"}, {})
    html = (server.STATIC / "index.html").read_text(encoding="utf-8")
    assert html.index('data-tab="today"') < html.index('data-tab="overview"') and 'id="tab-today" class="tab on"' in html and html.index("assistant.js") < html.index("command.js")
    js = (server.STATIC / "assistant.js").read_text(encoding="utf-8")
    assert "RENDER.today = renderToday" in js and "/api/assistant/ask" in js and "esc(i.text)" in js and "innerHTML = a." not in js
    assert 'RENDER.today ? "today" : "overview"' in (server.STATIC / "app.js").read_text(encoding="utf-8")
    cmd = (server.STATIC / "command.js").read_text(encoding="utf-8")
    assert "askAssistant(q)" in cmd and 'today: ["오늘", "비서"' in cmd and 'askAssistant("help")' in cmd and '"도움말"' in cmd
    auto = (ROOT / "terminal" / "automation.py").read_text(encoding="utf-8")
    assert "self._notes(st), self._brief())" in auto and "assistant.daily_lines" in auto
