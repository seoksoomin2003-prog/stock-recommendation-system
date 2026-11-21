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


def snap(ticker, market, strategy, score, liq=0.9, **kw):
    px = 183100.0 if market == "KR" else 250.0
    factors = [factor("risk_reward", "RISK", 6, 0.0, raw={"reward_risk": 0.96, "stop": px * 0.86335, "target": px * 1.14113, "cost_pct": 0.53}),
               factor("atr_risk", "RISK", 5, 0.1, raw={"atr_pct": 0.068, "hist_vol": 0.78}), factor("balance_sheet", "FUNDAMENTAL", 3, 1.0, raw={"debt_equity": 0.3, "current_ratio": 2.33}),
               factor("liquidity", "RISK", 5, liq, raw={"adv_value": 3.77e12}), factor("trend_structure", "TECHNICAL", 0, 0.95, scored=False),
               factor("earnings_calendar", "EVENTS", 4, 1.0, raw={"next_earnings": "2027-01-27", "sessions": 44, "basis": "ESTIMATE", "from": "2026-01-29"})]
    return {"ticker": ticker, "market": market, "strategy": strategy, "score": score, "data_date": "2026-11-20", "price": px, "stop": px * 0.86335, "target": px * 1.14113,
            "entry_status": "NO_VALID_ENTRY_SETUP", "coverage": 0.925, "gates": [], "factors": factors, "model_version": "QSF-1.4.1", "provenance": {"fund_filed": "2026-03-10"},
            "domains": {"RISK": {"score_100": 26.2, "points": 5.2}, "FUNDAMENTAL": {"score_100": 85.9, "points": 8.6}, "REGIME": {"score_100": 25.4, "points": 0.0, "reference": True}},
            "holding": {"reward_risk": 0.96, "invalidation": ["종가가 158,079.30 아래로 마감"], "gap_note": "손절은 체결을 보장하지 않습니다.", "stop_method": "2 ATR 시나리오",
                        "exit_triggers": ["종가 손절선 이탈", "목표 도달"], "expected_sessions": 5, "first_review": "2026-11-30"}, **kw}


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

    def _rows(self):
        return [{**r, "file": r["market"]} for r in self._live_rows()]

    def side(self, row):                    # one recorded session: nothing earlier to compare with
        return {}


class FakeQsf:
    def __init__(self, base):
        self.base = base
        self.rows = {"KR": [row("005930", "삼성전자", "SWING", 53.9, filing_events={"financing": False, "buyback": True}), row("005930", "삼성전자", "LONG_TERM", 64.2),
                            row("005935", "삼성전자우", "SWING", 40.0), row("373220", "LG에너지솔루션", "SWING", 30.0, high_risk=True, filing_events={"financing": True, "buyback": False})],
                     "US": [row("AAPL", "Apple Inc.", "SWING", 71.5), row("A", "Agilent Technologies, Inc.", "SWING", 60.0), row("IT", "Gartner, Inc.", "SWING", 55.0), row("TECH", "Bio-Techne Corporation", "SWING", 76.4)]}
        self.ledger = FakeLedger([snap("005930", "KR", "SWING", 53.9, liq=(53.9 * 0.23 - 7.5) / 5), snap("005930", "KR", "LONG_TERM", 64.2), snap("005935", "KR", "SWING", 40.0),
                                  snap("373220", "KR", "SWING", 30.0, gates=[{"code": "SEVERE_EVENT", "text": "중대한 공시: 횡령·배임 (2026-10-14)"}]),
                                  snap("AAPL", "US", "SWING", 71.5, entry_status="ENTRY_NOW"), snap("A", "US", "SWING", 60.0), snap("IT", "US", "SWING", 55.0), snap("TECH", "US", "SWING", 76.4)])

    def latest(self, market):
        return {"status": "REAL", "session": "2026-11-20", "rows": self.rows[market]}

    def top3(self, market):
        return {"strategies": {"SWING": {"days": [{"session": "2026-11-20", "entry_session": "2026-11-23", "before_open": True, "top": [{"ticker": "TECH", "name": "Bio-Techne", "score": 76.4}]}]}}}

    dividends: list = []

    def dividends_upcoming(self, market, days):
        return {"status": "REAL", "items": [d for d in self.dividends if d["days_away"] <= days]}

    def earnings_upcoming(self, market, days):
        return {"items": []}

    def screen_rows(self, market):
        return {"rows": [{**r, "sector": "기술"} for r in self.rows[market]]}

    def _loader(self, market):
        return lambda ticker: []

    class cache:                            # the Korean treasury yield is not on disk
        @staticmethod
        def read(key):
            return None

    def peers(self, ticker, market="US"):
        ratio = lambda pe, roe: {"pe": pe, "pb": None, "roe": roe}      # noqa: E731
        rows = [{"ticker": "005930", "ratios": ratio(27.7, 0.104), "change_1m": -0.146}] + [{"ticker": f"P{k}", "ratios": ratio(10.0 + 5 * k, 0.05 + 0.02 * k), "change_1m": -0.05 * k} for k in range(6)]
        return {"status": "REAL", "group": "기술", "peers": rows, "grades": {"SWING": {"SCORE": {"grade": "A", "percentile": 0.85, "n": 7}}}} if ticker == "005930" else {"status": "UNAVAILABLE"}


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
        return {"score_100": 25.4, "state": "ADVERSE", "label": "나쁨", "size_factor": 1.0, "session": "2026-11-20", "note": "참고 표시입니다.",
                "factors": [{"factor": "index_trend", "normalized": 0.0, "raw": {"close": 4869.96, "ma200": 6525.3, "ma50": 6107.8}}, {"factor": "breadth", "normalized": 0.0, "raw": {"breadth": 0.157, "n": 299}}]}

    def alerts_view(self):
        return {"rules": [], "log": []}

    def overview(self, market="US"):
        one = lambda name, close, day, month: {"name": name, "close": close, "change_pct": day, "change_1m_pct": month, "date": "2026-11-20", "status": "REAL"}      # noqa: E731
        return {"groups": [{"title": "지수", "items": [one("코스피", 4869.96, -3.1, -12.3), one("코스닥", 700.0, -2.0, None)]},
                           {"title": "금리·환율·원자재", "items": [one("원/달러", 1334.79, 0.33, 0.7)]},
                           {"title": "섹터 ETF", "items": [one("기술", 1.0, -7.3, -18.3), one("에너지", 1.0, 0.1, -10.4), one("금융", 1.0, -1.8, -6.0), one("유틸리티", 1.0, 0.2, -0.4), one("필수소비재", 1.0, 0.3, 0.5)]}]}

    def econ_calendar(self, market="US", days=14):
        return {"items": [{"name": "FOMC 금리 결정", "date": "2026-11-23", "date_kst": "2026-11-23", "days_away": 2}]}

    def _book(self, market="US"):
        return [], {"status": "OK"}, {"positions": {t: {} for t in self.held}}

    def watchlist(self):
        return []

    ROTATION = {"US": ("SPY", "S&P 500 (SPY)", []), "KR": ("^KS11", "코스피", [])}

    class cache:                            # no reference prices are on disk and none are fetched
        @staticmethod
        def cached(key, ttl, fetch):
            return {"data": {}}


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
    assert A.read_question("삼성전자", True) == "ANALYZE" and A.read_question("비트코인 전망", False) is None      # a name alone asks for the whole picture
    assert A.read_question("삼성전자 점수 어때", True) == "WHY" and A.read_question("증시 왜 이렇게 급락해?", False) == "MARKET"
    assert len(A.EXAMPLES) == len(A.STOCK_INTENTS) + len(A.PLAIN_INTENTS) == 22


def flat(a):
    return " ".join(a["lines"])


def test_an_answer_gives_the_conclusion_first_then_titled_groups_and_what_to_ask_next(term):
    why = A.answer(term, "삼성전자 점수 왜 낮아?", "US")
    assert why["status"] == "REAL" and why["intent"] == "WHY" and why["ticker"] == "005930" and why["market"] == "KR" and why["note"] == A.NOTE
    assert why["summary"].startswith("삼성전자의 스윙 점수는 53.9점으로 3종목 중 1위(상위 33%)") and "중간값 40.0점" in why["summary"] and "16.1점 모자랍니다" in why["summary"]
    assert "매수 후보 구간에 든 종목이 하나도 없습니다" in why["summary"] and why["lines"][0] == why["summary"]
    titles = [s["title"] for s in why["sections"]]
    assert titles[0].startswith("점수를 깎은 것 (100점에서 46.1점을 잃었고") and titles[1:] == ["점수를 받친 것", "점수에 들어가지 않은 것", "프로그램이 이 점수로 읽는 것", "무엇이 달라지면 바뀌나"]
    assert why["lines"] == [why["summary"]] + [x for s in why["sections"] for x in s["lines"]]
    lost = why["sections"][0]["lines"]
    assert lost[0].startswith("손익비 0/100(26.1점 잃음)") and "목표 208,941원(+14.1%), 손절 158,079원(-13.7%)" in lost[0] and "손익비 0.96" in lost[0]
    assert "채점 기준: 손익비가 1.0 이하면 0점, 3.0 이상이면 100점." in lost[0] and "하루 변동 폭이 가격의 6.8%" in lost[1] and lost[1].startswith("변동 폭 안정성 10/100")      # every signal reads one way: 100 is the good end
    kept = why["sections"][1]["lines"]
    assert kept[0].startswith("유동성 98/100(21.3점 얻음)") and "3.77조 원" in kept[0] and "채점 기준" not in kept[0]
    out = " ".join(why["sections"][2]["lines"])
    assert "시장 국면 영역은 이 점수에 들어가지 않습니다(참고값 25/100)" in out and "추세 구조" not in flat(why)                    # reference rows are told apart, never scored
    assert "'유효한 진입 근거 없음'" in flat(why) and "장기 점수는 64.2점" in flat(why) and "1.1점 오르면 '보유·관찰' 구간(55점 이상)" in flat(why)
    assert why["basis"].startswith("기준: 2026-11-20 종가 183,100원") and "데이터 반영률 92%" in why["basis"]
    assert why["follow"] == ["삼성전자 장기 점수 왜 이래?", "삼성전자 분석해 줘", "삼성전자 사도 돼?", "삼성전자 손절 어디?", "삼성전자 위험해?"]
    for q in why["follow"]:                                                       # every follow-up is itself a question it can answer
        assert A.answer(term, q, "KR")["status"] == "REAL", q
    assert A.answer(term, "삼성전자 장기 점수", "KR")["title"] == "삼성전자(005930) 장기 점수가 이렇게 나온 이유"
    assert why["follow"][0] == "삼성전자 장기 점수 왜 이래?" and "삼성전자 분석해 줘" in why["follow"]
    us = A.answer(term, "AAPL 왜?", "KR")
    assert us["follow"][0] == "AAPL 장기 점수 왜 이래?" and "$250.00" in us["basis"]             # a US stock is asked about by its ticker


def test_the_score_is_taken_apart_into_points_lost_and_kept():
    s = snap("005930", "KR", "SWING", 53.9)
    parts = A.breakdown({**s, "score": 100 * (6 * 0.0 + 5 * 0.1 + 3 * 1.0 + 5 * 0.9 + 4 * 1.0) / 23})
    assert parts["total"] == 23 and sum(r["kept"] + r["lost"] for r in parts["rows"]) == pytest.approx(100.0)
    assert sum(r["lost"] for r in parts["rows"]) == pytest.approx(100 - 100 * 12 / 23) and [f["factor"] for f in parts["reference"]] == ["trend_structure"]
    assert A.breakdown({**s, "score": 99.0}) is None                              # stored figures that do not rebuild the score are not passed off as its parts
    empty = {**s, "score": 100 * 12 / 23, "factors": s["factors"] + [factor("insider_activity", "EVENTS", 3, None, reason="내부자 공시를 해석할 수 없습니다")]}
    assert [f["factor"] for f in A.breakdown(empty)["empty"]] == ["insider_activity"]


def test_the_words_for_each_signal_follow_the_scoring_code():
    """What a signal measures and how it is scaled are written once, beside the line of factors.py they describe."""
    from terminal.qsf import config
    src = (ROOT / "terminal" / "qsf" / "factors.py").read_text(encoding="utf-8")
    counted = {n for p in config.PROFILES.values() for d in p["domains"].values() for n in d}
    assert counted <= set(A.FACTOR_INFO) and counted <= set(A.FACTOR_KO)          # every signal a score counts can be explained
    for name, (what, scale, line) in A.FACTOR_INFO.items():
        assert line in src, name
        assert "니다" in what and scale and "−" not in scale, name
    f = factor("valuation", "FUNDAMENTAL", 15, 0.58, raw={"pe": 27.72, "pb": 2.52, "fcf_yield": 0.0343})
    assert A.figures(f, {"price": 100.0}, "KR") == "PER 27.7배, PBR 2.52배, 잉여현금흐름 수익률 3.4%"
    assert A.figures(factor("leverage", "RISK", 4, 0.5, raw={"debt_equity": None}), {}, "KR") == "부채/자본 자료 없음"      # a missing figure is said, never shown as 0
    assert A.figures(factor("liquidity", "RISK", 5, 1.0, raw={"adv_value": 2.35e9}), {}, "US") == "20일 평균 거래대금 23.5억 달러"
    assert A.figures(factor("balance_sheet", "FUNDAMENTAL", 3, 0.3, raw={"equity_assets": 0.076}), {}, "KR") == "자기자본/자산 7.6%"       # a bank is read by its own measure


def test_particles_follow_the_last_sound_and_a_price_that_hardly_moves_is_said():
    assert [A.josa(w, "은는") for w in ("삼성전자", "KB금융", "AAPL", "TECH", "Apple Inc.")] == ["삼성전자는", "KB금융은", "AAPL은", "TECH는", "Apple Inc.는"]
    assert A.josa("현대로템", "이가") == "현대로템이" and A.josa("서울", "으로로") == "서울로" and A.josa("삼성", "으로로") == "삼성으로" and A.josa("123456", "은는") == "123456은"
    still = {"factors": [factor("atr_risk", "RISK", 5, 1.0, raw={"atr_pct": 0.0018, "hist_vol": 0.43})]}
    assert "0.2%로 거의 움직이지 않습니다" in A.pinned(still) and "공시를 먼저 확인" in A.pinned(still)
    assert A.pinned({"factors": [factor("atr_risk", "RISK", 5, 0.8, raw={"atr_pct": 0.017})]}) is None and A.pinned({"factors": []}) is None


def test_an_analysts_note_lays_the_stock_out_from_view_to_what_would_change_it(term):
    note = A.answer(term, "삼성전자 분석해 줘", "US")
    assert note["status"] == "REAL" and note["intent"] == "ANALYZE" and note["title"] == "삼성전자(005930) 분석 노트" and A.answer(term, "삼성전자", "KR")["intent"] == "ANALYZE"
    assert note["summary"].startswith("삼성전자(기술 업종): 프로그램이 읽는 것은 스윙 53.9점('보유·관찰', 판단 '관찰', 3종목 중 1위, 업종 등급 A(업종 7종목 중 상위 15%))") and "장기 64.2점" in note["summary"]
    titles = [s["title"] for s in note["sections"]]
    assert titles == ["핵심 세 줄", "지난 기록 이후 달라진 것 (장기 점수)", "밸류에이션과 업종 안에서의 위치 (기술 7종목)", "실적과 이익의 질", "재무 건전성", "가격과 수급", "무엇과 같이 움직였나 (노출)", "촉매와 일정", "위험", "시나리오",
                      "견해가 바뀌는 조건", "이 노트의 한계"]      # a part with nothing stored is left out
    by_title = {s["title"]: s["lines"] for s in note["sections"]}
    assert by_title["지난 기록 이후 달라진 것 (장기 점수)"] == ["비교할 지난 기록이 아직 없습니다(1주 전 기록부터 비교합니다)."] and "60거래일" in by_title["무엇과 같이 움직였나 (노출)"][0]
    assert by_title["핵심 세 줄"] == ["점수: 장기 64.2점('보유·관찰'), 스윙 53.9점('보유·관찰').", "달라진 것: 비교할 지난 기록이 아직 없습니다.", "먼저 볼 위험: 걸린 차단 조건과 회피 표시가 없습니다. 안전하다는 뜻은 아닙니다."]
    by = {s["title"]: s["lines"] for s in note["sections"]}
    value = by["밸류에이션과 업종 안에서의 위치 (기술 7종목)"]
    assert value[0] == "PER 27.7배: 업종 중앙값 25.0배보다 높습니다. 7종목 중 좋은 쪽에서 5위(업종보다 못한 쪽)." and value[1] == "ROE 10.4%: 업종 중앙값 10.4%와 같습니다. 7종목 중 좋은 쪽에서 4위."
    assert value[-1].startswith("최근 한 달 주가 -14.6%: 업종 중앙값 -14.6%") or value[-1].startswith("최근 한 달 주가 -14.6%: 업종 중앙값 -15.0%")
    assert any(x.startswith("다음 실적 발표 2027-01-27(44거래일 뒤, 과거 발표일로 추정)") for x in by["촉매와 일정"]) and "거시 일정: FOMC 금리 결정 2026-11-23(2일 뒤)." in by["촉매와 일정"]
    assert any("시장 상태 25/100(나쁨)" in x for x in by["위험"]) and any(x.startswith("스윙 계획의 손절 158,079원, 목표 208,941원, 손익비 0.96") for x in by["시나리오"])
    assert by["이 노트의 한계"] == A.NOTE_LIMITS and "컨센서스" in by["이 노트의 한계"][0]
    for word in ("사세요", "매수하세요", "파세요", "매도하세요", "추천합니다", "목표주가"):
        assert word not in json.dumps(note, ensure_ascii=False), word
    bare = A.answer(term, "AAPL 어때?", "KR")                                       # no sector data for this one: the note says so and still stands
    assert bare["intent"] == "ANALYZE" and "같은 업종의 스캔 종목이 모자라 비교하지 못했습니다." in flat(bare) and "업종 정보 없음" in bare["summary"]


def test_ratios_are_read_beside_the_sector_best_side_first():
    rows = [{"ticker": "ME", "ratios": {"pe": -3.0, "debt_equity": 0.2, "roe": 0.30}}] + [{"ticker": f"P{k}", "ratios": {"pe": 10.0 + k, "debt_equity": 0.5 + 0.1 * k, "roe": 0.05 + 0.01 * k}} for k in range(5)]
    got = A.sector_lines({"status": "REAL", "peers": rows}, "ME")
    assert got[0] == "PER: 적자라 계산되지 않습니다(업종 중앙값 12.0배)." and got[1].startswith("ROE 30.0%: 업종 중앙값 7.5%보다 높습니다. 6종목 중 좋은 쪽에서 1위(업종보다 나은 쪽)")
    assert got[2].startswith("부채/자본 0.20배: 업종 중앙값 0.65배보다 낮습니다. 6종목 중 좋은 쪽에서 1위(업종보다 나은 쪽)")
    assert A.sector_lines({"status": "REAL", "peers": rows[:3]}, "ME") == [] and A.sector_lines({"status": "UNAVAILABLE"}, "ME") == [] and A.sector_lines({"status": "REAL", "peers": rows}, "NOPE") == []


def test_the_days_list_opens_with_the_market_and_names_a_macro_date_within_three_days(term):
    got = A.context_items(term.overview("KR"), term.econ_calendar("KR"), "KR")
    assert kinds(got) == ["MARKET_MOVE", "MACRO_DATE"] and got[0]["text"].startswith("한국 지수: 코스피 4,869.96(전일 대비 -3.10%, 한 달 -12.3%, 2026-11-20). 코스닥 700.00(전일 대비 -2.00%, 2026-11-20).")
    assert "FOMC 금리 결정 2026-11-23(2일 뒤)" in got[1]["text"] and A.context_items({}, {"items": [{"name": "x", "date": "2026-12-20", "days_away": 20}]}, "US") == []
    assert {"MARKET_MOVE", "MACRO_DATE"} <= set(kinds(A.briefing(term, "KR")["items"]))


def test_stock_answers_come_from_the_stored_scan(term):
    buy = A.answer(term, "AAPL 사도 돼?", "KR")
    table = buy["sections"][0]["lines"]
    assert buy["intent"] == "BUY_CHECK" and len(table) == 7 and table[0].startswith("○ 점수 구간: 스윙 71.5점") and table[1].startswith("○ 진입 판단: '지금 진입 가능 구간'") and table[5].startswith("✕ 시장 상태")
    assert "7개 중 6개가 걸림 없이 통과" in buy["summary"] and "걸린 것은 시장 상태입니다" in buy["summary"] and "살지 말지에 대한 답이 아닙니다" in buy["summary"]
    for word in ("사세요", "매수하세요", "파세요", "매도하세요", "추천합니다"):
        assert word not in json.dumps(buy, ensure_ascii=False)
    kr = A.answer(term, "삼성전자 사도 돼?", "KR")
    assert kr["sections"][0]["lines"][4].startswith("○ 회피 표시: 없음") and any("자사주 취득 공시" in x for x in kr["sections"][1]["lines"])       # a buyback is a note, not a mark against
    assert "'유효한 진입 근거 없음'" in kr["sections"][0]["lines"][1] and "지금 손익비는 0.96입니다" in kr["sections"][0]["lines"][1]
    risk = A.answer(term, "LG에너지솔루션 위험해?", "KR")
    by = {s["title"]: s["lines"] for s in risk["sections"]}
    assert "차단 조건 1건, 회피 표시 2건" in risk["summary"] and "횡령·배임" in by["차단 조건"][0] and "고위험 표시" in by["회피 표시"][0] and "자금 조달 공시" in by["회피 표시"][1]
    assert any(x.startswith("변동 폭 안정성 10/100(배점 5)") for x in by["위험 요인의 실제 수치"])
    calm = A.answer(term, "AAPL 위험해?", "KR")
    assert "안전하다는 뜻은 아닙니다" in calm["summary"]
    stop = A.answer(term, "005930 손절 어디?", "KR")
    assert "손절선은 158,079원(지금보다 -13.7%), 목표는 208,941원(지금보다 +14.1%)" in stop["summary"] and "0.96" in flat(stop) and "주문이 아닙니다" in flat(stop)
    long_stop = A.answer(term, "삼성전자 장기 손절 어디?", "KR")
    assert "가격으로 정한 손절선이 없습니다" in long_stop["summary"] and long_stop["title"].endswith("장기 보유의 기준")
    earn = A.answer(term, "삼성전자 실적 언제?", "KR")
    assert "2027-01-27(44거래일 뒤)" in earn["summary"] and "추정했습니다" in flat(earn) and "발표 5거래일 전부터 새 진입을 막습니다" in flat(earn) and "지금은 그 밖입니다" in flat(earn)
    rank = A.answer(term, "TECH 몇 등이야?", "KR")
    assert "4종목 중 1위(상위 25%)" in rank["summary"] and "근거는 아직 확인되지 않았습니다" in flat(rank) and "매수 후보 구간(70점 이상)에 든 종목은 2개" in flat(rank)
    low = A.answer(term, "IT 몇 등이야?", "KR")
    assert "4종목 중 4위(하위 1%)" in low["summary"]
    sell = A.answer(term, "삼성전자 팔아야 해?", "KR")
    assert sell["intent"] == "SELL_CHECK" and sell["summary"].startswith("삼성전자는 보유 기록이 없어") and sell["tab"] == "portfolio"
    held = A.answer(FakeTerminal(term.base, held=["005930"]), "삼성전자 팔아야 해?", "KR")
    assert "'비중 축소 검토'" in held["summary"] and "주문은 직접 정합니다" in flat(held)
    gone = A.answer(term, "ZZZZ 사도 돼?", "KR")
    assert gone["status"] == "UNKNOWN_STOCK" and gone["ticker"] == "ZZZZ" and gone["tab"] == "stock" and "'ZZZZ'는 스캔 대상" in gone["summary"]
    assert A.answer(term, "123456 손절", "KR")["status"] == "UNKNOWN_STOCK" and A.answer(term, "비트코인 전망", "KR")["status"] == "UNKNOWN"


def test_plain_answers_and_what_it_does_not_know(term):
    market = A.answer(term, "시장 상태 어때?", "KR")
    assert market["intent"] == "MARKET" and market["summary"].startswith("한국 시장 상태 25/100(나쁨)") and "지수 추세: 0/100" in flat(market) and "순위를 바꾸지 못합니다" in flat(market)
    by = {s["title"]: s["lines"] for s in market["sections"]}
    assert market["title"] == "한국 시장 노트(2026-11-20)" and by["지수"][0] == "코스피 4,869.96(전일 대비 -3.10%, 한 달 -12.3%, 2026-11-20)."
    assert "대표 지수는 200일 평균보다 -25.4%, 50일 평균보다 -20.3%입니다." in by["얼마나 불안한가"] and any("200일 평균 위에 있는 종목은 16%" in x for x in by["얼마나 불안한가"])
    assert by["업종"] == ["한 달 동안 가장 약한 업종: 기술 -18.3%, 에너지 -10.4%, 금융 -6.0%.", "가장 강한 업종: 필수소비재 +0.5%, 유틸리티 -0.4%, 금융 -6.0%."]
    assert "스윙 점수의 중간값은 40.0점이고, 3종목 가운데 매수 후보 구간(70점 이상)은 0개입니다." in by["점수로 본 시장"] and by["다가오는 일정"] == ["FOMC 금리 결정 2026-11-23(2일 뒤)."]
    assert "왜 움직였는지(뉴스의 뜻)는 판단하지 않습니다" in flat(market)
    assert "왕복 비용을 0.53%로 계산합니다" in A.answer(term, "수수료는 얼마로 계산해?", "KR")["summary"]
    top = A.answer(term, "오늘 상위 종목은?", "US")
    assert top["summary"].startswith("미국 스윙 점수 1위는 Bio-Techne(TECH) 76.4점") and "무작위로 고른 3종목과 구분되지 않았습니다" in flat(top) and top["follow"] == ["TECH 점수 왜 이래?", "TECH 사도 돼?"]
    assert "과거 구간으로 시험한 적이 없고" in flat(A.answer(term, "오늘 상위 종목은?", "KR"))
    for typed in ("뭘 물어볼 수 있어?", "help", "도움말", "?", "명령어 뭐 있어"):
        got = A.answer(term, typed, "KR")
        assert got["status"] == "REAL" and got["intent"] == "HELP" and got["examples"] == A.EXAMPLES and "22가지" in got["title"], typed
        assert [s["title"] for s in got["sections"]] == ["종목 없이 묻는 것 12가지", "종목을 넣어 묻는 것 10가지", "쓰는 법"] and "'help'" in got["lines"][-1]
    trust = A.answer(term, "이 점수 믿어도 돼?", "KR")
    assert trust["intent"] == "TRUST" and "아직 확인되지 않았습니다" in trust["summary"] and "살 종목을 고르는 힘은 확인되지 않았습니다." in flat(trust)
    today = A.answer(term, "오늘 뭐 해야 해?", "KR")
    assert today["intent"] == "TODAY" and today["tab"] == "today" and today["summary"] == "오늘 따로 챙길 것이 없습니다." and [s["title"] for s in today["sections"]] == ["참고"]
    hold = A.answer(term, "내 보유 종목 괜찮아?", "KR")
    assert hold["summary"] == "한국 계좌에 기록된 보유 종목이 없습니다." and [s["title"] for s in hold["sections"]] == ["할 수 있는 것"]
    job = A.answer(term, "오늘 수집 됐어?", "KR")
    assert "1단계 중 1단계가 끝났습니다. 실패한 단계는 없습니다." in job["summary"]
    unknown = A.answer(term, "비트코인 전망", "KR")
    assert unknown["status"] == "UNKNOWN" and unknown["examples"] == A.EXAMPLES and "알아듣지 못했습니다" in unknown["title"] and unknown["lines"] == [unknown["summary"]]
    assert A.answer(term, "   ", "KR")["status"] == "UNKNOWN" and A.answer(term, "HELP 삼성전자", "KR")["intent"] != "HELP" and len(A.answer(term, "가" * 500 + " 시장", "KR")["question"]) <= 200
    broken = FakeTerminal(term.base)
    broken.market_state = lambda market="US": (_ for _ in ()).throw(OSError("x"))
    lost = A.answer(broken, "시장 상태 어때?", "KR")
    assert lost["status"] == "UNAVAILABLE" and "OSError" in lost["summary"] and lost["follow"] == ["오늘 수집 됐어?"]


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
    assert 'class="asst-sum">${esc(a.summary)}' in js and "a.sections.map((s) => `<h4>${esc(s.title)}</h4>" in js and "이어서 물어보기" in js and "esc(a.basis)" in js      # every text goes through esc
    assert 'RENDER.today ? "today" : "overview"' in (server.STATIC / "app.js").read_text(encoding="utf-8")
    cmd = (server.STATIC / "command.js").read_text(encoding="utf-8")
    assert "askAssistant(q)" in cmd and 'today: ["오늘", "비서"' in cmd and 'askAssistant("help")' in cmd and '"도움말"' in cmd
    auto = (ROOT / "terminal" / "automation.py").read_text(encoding="utf-8")
    assert "self._notes(st), self._brief())" in auto and "assistant.daily_lines" in auto


def test_a_stock_is_not_its_own_sector_median_when_the_count_is_even():
    rows = [{"ticker": f"P{k}", "ratios": {"roe": 0.10 + 0.01 * k}} for k in range(8)]       # eight peers: the fifth used to be called the median
    line = A.sector_lines({"status": "REAL", "peers": rows}, "P4")[0]
    assert "업종 중앙값 13.5%보다 높습니다" in line and "와 같습니다" not in line
    assert A._middle([1.0, 2.0, 3.0]) == 2.0 and A._middle([1.0, 2.0, 3.0, 4.0]) == 2.5


def test_a_korean_macro_date_is_not_listed_under_the_us_market():
    items = [{"name": "한국은행 금통위", "country": "KR", "days_away": 1, "date": "2026-11-26"}, {"name": "미국 고용보고서", "country": "US", "days_away": 2, "date": "2026-12-04"}]
    assert [e["country"] for e in A.macro_dates(items, "US")] == ["US"] and [e["country"] for e in A.macro_dates(items, "KR")] == ["KR", "US"]
    us = [i["text"] for i in A.context_items({}, {"items": items}, "US") if i["kind"] == "MACRO_DATE"]
    assert len(us) == 1 and "고용보고서" in us[0]


def test_the_candidate_count_says_how_many_are_in_the_buy_band():
    by = {"SWING": {"all": 9, "buy": 1}, "LONG": {"all": 313, "buy": 70}}
    text = A.plan_items({"status": "NO_ACCOUNT", "candidates": 322, "candidates_by": by}, "US")[0]["text"]
    assert "322건" in text and "스윙 9건 중 1건" in text and "장기 313건 중 70건" in text and "관망 구간(55~70점)" in text
    assert A.candidate_split(None) == "" and A.candidate_split({"SWING": {"all": 0, "buy": 0}}) == ""


def test_the_days_list_names_an_ex_dividend_date_and_the_note_shows_the_stored_expectations(term):
    term.qsf.dividends = [{"ticker": "AAPL", "name": "Apple Inc.", "date": "2026-11-24", "days_away": 3, "held": False, "watched": True},
                          {"ticker": "A", "name": "Agilent", "date": "2026-12-20", "days_away": 29, "held": True, "watched": False}]
    items = [i for i in A.briefing(term, "US")["items"] if i["kind"] == "EX_DIVIDEND"]
    assert len(items) == 1 and items[0]["level"] == "INFO" and items[0]["ticker"] == "AAPL" and "배당락일 2026-11-24(3일 뒤)" in items[0]["text"]      # only within five days
    term.qsf.stored_info = lambda ticker, market: {"targetMeanPrice": 200000.0, "numberOfAnalystOpinions": 35}
    note = A.answer(term, "삼성전자 분석해 줘", "KR")
    by = {s["title"]: s["lines"] for s in note["sections"]}
    assert by["시장의 기대 (야후 집계, 참고)"][0].startswith("목표주가: 증권사 35곳 평균 200,000원(지금 가격 대비 ") and "공식 자료가 아닙니다" in by["시장의 기대 (야후 집계, 참고)"][-1]
    assert "야후가 모은 지금 값만" in by["이 노트의 한계"][0]


def test_example_questions_name_a_stock_of_the_market_on_screen(term):
    """The US screen listed its examples with 삼성전자 (user report 2026-11-22)."""
    us, kr = A.answer(term, "help", "US"), A.answer(term, "help", "KR")
    assert not any("삼성전자" in q for q in us["examples"]) and "AAPL 분석해 줘" in us["examples"] and "AAPL 점수 왜 낮아?" in us["examples"]
    assert "삼성전자 분석해 줘" in kr["examples"] and not any("AAPL" in q for q in kr["examples"]) and kr["examples"] == A.EXAMPLES
    by = {s["title"]: s["lines"] for s in us["sections"]}
    assert by["종목을 넣어 묻는 것 10가지"] == A.stock_examples("US") and all(q.startswith("AAPL ") for q in by["종목을 넣어 묻는 것 10가지"]) and by["쓰는 법"][0].startswith("종목은 'AAPL' 자리에")
    assert {s["title"]: s["lines"] for s in kr["sections"]}["쓰는 법"][0].startswith("종목은 '삼성전자' 자리에")
    assert len(A.examples_for("US")) == len(A.examples_for("KR")) == 22 and A.examples_for("US")[:12] == A.examples_for("KR")[:12]      # the questions without a stock are the same
    assert not any("삼성전자" in q for q in A.answer(term, "", "US")["examples"]) and not any("삼성전자" in q for q in A.answer(term, "무슨 말인지 모를 문장", "US")["examples"])
    for q in A.stock_examples("US"):                        # every US example is itself a question the assistant answers about AAPL
        got = A.answer(term, q, "US")
        assert got["status"] == "REAL" and got["ticker"] == "AAPL", q
    page = (Path(A.__file__).parent / "static" / "assistant.js").read_text(encoding="utf-8")
    assert 'isKR() ? "삼성전자" : "AAPL"' in page


def test_the_five_views_answer_a_stock_and_give_the_team_list(term, monkeypatch):
    """User request 2026-11-22: five well-known approaches as a team, one or two lines each, and a team list."""
    from terminal import five_views as fv
    assert A.read_question("삼성전자 다섯 관점은?", True) == "FIVE" and A.read_question("버핏이라면 삼성전자 어때", True) == "FIVE" and A.read_question("다섯 관점 팀 목록은?", False) == "TEAM"
    assert A.read_question("삼성전자 분석해 줘", True) == "ANALYZE" and A.read_question("오늘 상위 종목은?", False) == "TOP"          # the other questions are read as before
    good = {"price": 100.0, "domains": {"REGIME": {"score_100": 60.0}}, "factors": [
        {"factor": "valuation", "raw": {"pe": 12.0, "pb": 1.2}}, {"factor": "business_quality", "raw": {"roe": 0.2, "op_margin": 0.25, "gross_margin": 0.5, "roe_years_positive": 1.0}},
        {"factor": "growth_quality", "raw": {"eps_cagr3": 0.15, "rev_growth": 0.08}}, {"factor": "free_cash_flow", "raw": {"fcf_margin": 0.12, "fcf_years_positive": 1.0}},
        {"factor": "balance_dilution", "raw": {"debt_equity": 0.3, "share_change": -0.01}}, {"factor": "financial_resilience", "raw": {"current_ratio": 2.5}},
        {"factor": "capital_allocation", "raw": {"returns_capital": True}}, {"factor": "long_trend", "raw": {"ma200": 90.0, "ma200_slope": 0.05}},
        {"factor": "relative_strength", "raw": {"percentile": 0.8}}, {"factor": "momentum_persistence", "raw": {"ret_12_1": 0.2}}, {"factor": "downside_drawdown", "raw": {"max_drawdown_252": -0.15}},
        {"factor": "material_events", "raw": {"negative": 0}}, {"factor": "governance", "raw": {"issues": []}}]}
    monkeypatch.setattr(A, "five_opinions", lambda terminal, stock: fv.opinions(good, None))
    got = A.answer(term, "삼성전자 다섯 관점은?", "KR")
    assert got["status"] == "REAL" and got["intent"] == "FIVE" and got["title"] == "삼성전자(005930) 다섯 관점" and got["summary"].startswith("다섯 관점 가운데 5개가 '기준에 맞음'")
    by = {s["title"]: s["lines"] for s in got["sections"]}
    assert len(by["다섯 관점"]) == 5 and by["다섯 관점"][0].startswith("버핏식(좋은 사업을 적정한 값에): 기준 7개 중 7개 충족, 기준에 맞음. 맞는 것: ROE 20.0%")
    assert "실존 투자자의 실제 의견이 아닙니다" in by["이 답의 한계"][0] and got["follow"][0] == "삼성전자 분석해 줘"
    note = A.answer(term, "삼성전자 분석해 줘", "KR")
    five = {s["title"]: s["lines"] for s in note["sections"]}["다섯 관점 (참고)"]
    assert len(five) == 7 and five[5].startswith("다섯 관점 가운데 5개") and five[6] == fv.NOTE
    team = A.answer(term, "다섯 관점 팀 목록은?", "KR")                                     # the stored snapshots of the scratch terminal carry no figures: an honest empty list
    assert team["status"] == "REAL" and team["intent"] == "TEAM" and team["title"] == "다섯 관점 팀 목록(한국)" and "목록을 억지로 채우지 않습니다" in team["summary"]
    items = [i for i in A.briefing(term, "KR")["items"] if i["kind"] == "FIVE_TEAM"]
    assert len(items) == 1 and items[0]["level"] == "INFO" and "기준에 맞음'으로 본 종목이 없습니다" in items[0]["text"]
