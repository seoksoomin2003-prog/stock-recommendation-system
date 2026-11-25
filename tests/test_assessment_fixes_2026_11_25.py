"""Third maturity assessment (2026-11-25), the P0 list: outputs that said something false or showed an old price as current.
User decisions of the same day: a card whose buy band was taken back leaves the order plan, and a LOW-confidence card reads
'기다림'.  QSF-1.5.3: no score moves.  No network."""
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from terminal import assistant as A, freshness as fr, plain, price_fill
from terminal.qsf import config, engine, holding, stance
from tests.test_buy_verdict import snap, verdict
from tests.test_qsf import ctx

ROOT = Path(__file__).resolve().parents[1]
SEOUL, NY = ZoneInfo("Asia/Seoul"), ZoneInfo("America/New_York")
PIN = {"form": "DEFM14A", "date": "2026-08-20", "label": "합병 주주총회 위임장", "vol20": 1.6}
DEAL = [{"form": "SC TO-T", "date": "2026-09-01", "label": "제3자의 공개매수 신고"}]


def src(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


# ---------------------------------------------------------------------- 2. a price that stopped is not REAL
def test_a_us_bar_a_session_behind_is_stale_whatever_the_calendar_days():
    now = datetime(2026, 11, 24, 15, 0, tzinfo=SEOUL)                     # the 2026-11-24 reply: bars ended on Friday 11-20
    assert fr.expected("US", now) == date(2026, 11, 23)
    assert fr.behind("2026-11-20", "AAPL", now) and not fr.behind("2026-11-23", "AAPL", now)
    assert not fr.behind("2026-11-20", "AAPL", datetime(2026, 11, 22, 12, 0, tzinfo=NY))        # a weekend: Friday is the newest
    assert fr.kind("005930.KS") == "KR" and fr.kind("^KS200") == "KR" and fr.kind("KRW=X") == "OTHER" and fr.kind("^GSPC") == "US"


def test_korea_forgives_one_weekday_but_not_an_older_bar_in_the_same_reply():
    now = datetime(2026, 11, 25, 2, 0, tzinfo=SEOUL)                       # the live case: KOSPI 11-23 beside KOSPI 200 11-24
    assert fr.expected("KR", now) == date(2026, 11, 24)
    assert not fr.behind("2026-11-23", "^KS11", now)                       # alone, one weekday may be a holiday
    newest = fr.newest([("^KS11", "2026-11-23"), ("^KS200", "2026-11-24"), ("KRW=X", "2026-11-25")])
    assert newest == "2026-11-24" and fr.behind("2026-11-23", "^KS11", now, newest_in_reply=newest)
    assert not fr.behind("2026-11-24", "^KS200", now, newest_in_reply=newest)
    assert fr.behind("2026-11-20", "005930.KS", now)                       # two weekdays missing


def test_the_trade_form_price_names_a_stopped_feed():
    rows = [{"date": "2026-11-19", "close": 10.0}, {"date": "2026-11-20", "close": 11.0}]
    now = datetime(2026, 11, 24, 15, 0, tzinfo=SEOUL)
    got = price_fill.pick(rows, None, date(2026, 11, 24), symbol="AAPL", now=now)
    assert got["status"] == "STALE" and got["close"] == 11.0 and got["exact"] is False
    asked = price_fill.pick(rows, date(2026, 11, 22), date(2026, 11, 24), symbol="AAPL", now=now)       # a Sunday: Friday's close is the right one
    assert asked["status"] == "REAL" and asked["date"] == "2026-11-20"
    assert price_fill.pick(rows, None, date(2026, 11, 24))["status"] == "REAL"                             # without a symbol: the calendar rule as before


def test_the_screens_ask_the_session_rule():
    s = src("terminal", "services.py")
    assert "freshness.behind(last_date, symbol, self.now(), newest_in_reply=newest)" in s and 'self._bar_status(rows[-1]["date"], "REAL", s)' in s
    assert "price_fill.pick(rows, want, today, symbol=sym, now=self.now())" in s
    for path in (ROOT / "terminal" / "qsf").glob("*.py"):
        assert "freshness" not in path.read_text(encoding="utf-8"), path.name                              # the score path keeps its own, stricter rule


# ---------------------------------------------------------------------- 1. the Korean day
def test_the_korean_filing_screen_asks_for_the_korean_day():
    s = src("terminal", "qsf", "service.py")
    body = s[s.index("    def kr_company("):s.index("    def kr_search(")]
    assert 'as_of = self.now().astimezone(ZoneInfo("Asia/Seoul")).date()' in body and "as_of = self.now().date()" not in body


# ---------------------------------------------------------------------- 3. the stance note per market
def test_the_stance_note_says_what_each_market_does():
    us, kr = stance.adverse_note("US"), stance.adverse_note("KR")
    assert "1.5배를 쓰지 않습니다" in us and "0.5배 그대로" in us
    assert "줄이지 않습니다" in kr and "공격적이면 1.5배" in kr and "쓰지 않습니다(그날" not in kr
    assert config.ADVERSE_SIZE_FACTOR.get("KR", 1.0) == 1.0                    # the fact the Korean sentence rests on


# ---------------------------------------------------------------------- 4, 5. merger wording and the pin's follow-through
def _card(**over):
    c = {"actionability": "ACTIONABLE", "score": 76.0, "band": "BUY_CANDIDATE", "strategy": "SWING", "market": "US", "entry_status": "ENTRY_NOW",
         "confidence": "HIGH", "price": 100.0, "data_date": "2026-11-23", "levels": {"stop": 96.0, "target": 106.0}, "factors": []}
    c.update(over)
    return c


def _text(doc):
    return " ".join(line for part in doc["parts"] for line in part["lines"])


def test_a_buyer_is_not_described_as_the_company_being_bought():
    buyer = _text(plain.card_plain(_card(), {"deals": DEAL}))
    assert "사는 쪽 회사가 낼 때도 있습니다" in buyer and "묶여" not in buyer.replace("인수 가격에 묶인 모습은 아닙니다", "") and "깨지면" not in buyer
    target = _text(plain.card_plain(_card(band="HOLD_WATCH", entry_status="NO_VALID_ENTRY_SETUP", deal_pin=PIN), {"deals": DEAL}))
    assert "팔리는 쪽으로 읽힙니다" in target and "거래가 깨지면 크게 떨어질 수 있습니다" in target and "지금 살 자리로 보지 않습니다" in target
    assert "손절 가격은" not in target and "손절 가격은" in buyer                 # a pinned stock has no entry, so no stop or target to plan
    assert "공시 원문 확인" in src("terminal", "committee", "council.py")


def test_what_would_change_and_the_buy_check_know_the_pin():
    c = ctx()
    c["deal_pin"] = PIN
    r = engine.score(c, "SWING")
    said = " ".join(holding.what_would_change(r))
    assert "점수가 올라도 상위 구간을 주지 않습니다" in said and "최상위 구간" not in said
    v = verdict(snap(76.0, entry="NO_VALID_ENTRY_SETUP", deal_pin=PIN))
    assert v["key"] == "NO" and "합병 절차로 가격이 인수 가격 근처에 묶인" in v["why"] and "다시 움직이면" in v["change"]


def test_a_missing_sec_list_is_said_not_read_as_no_deal():
    s = src("terminal", "qsf", "service.py")
    assert 'ctx["deal_unchecked"] = not self.deals_known(ctx["fund"].get("cik"))' in s and 'ctx["deals"], ctx["deal_unchecked"] = [], True' in s
    assert "확인하지 못했습니다" in _text(plain.card_plain(_card(deal_unchecked=True), {}))


# ---------------------------------------------------------------------- 7. a held-back card leaves the order plan
def test_a_card_whose_buy_band_was_taken_back_gets_no_entry_reading():
    c = ctx()
    r = engine.score(c, "LONG_TERM")
    assert holding.entry_status(r, c)["status"] == "ENTRY_NOW"                 # the fixture is a plain long-term entry
    held = {**r, "band_held_back": True, "conservative_score": 66.4}
    e = holding.entry_status(held, c)
    assert e["status"] == "NO_VALID_ENTRY_SETUP" and "66.4점" in e["reason"] and "빠진 자료가 채워질 때까지" in e["reason"]
    assert "빠진 자료가 채워져" in " ".join(holding.what_would_change(held))
    v = verdict(snap(71.0, entry="NO_VALID_ENTRY_SETUP", band_held_back=True, conservative_score=66.4), "AGGRESSIVE")
    assert v["key"] == "WAIT" and v["label"] == "기다림"                       # the plan and '사도 돼?' now say the same
    from terminal.qsf import order_plan
    assert order_plan.ENTRY_READY == "ENTRY_NOW"                              # the plan selects on the entry status, so the card is out


# ---------------------------------------------------------------------- 8. LOW confidence
def test_low_confidence_is_said_and_reads_wait_under_every_stance():
    for level in ("NORMAL", "AGGRESSIVE"):
        v = verdict(snap(80.0, confidence="LOW"), level)
        assert v["key"] == "WAIT" and "믿는 정도가 '낮음'" in v["why"]
    assert verdict(snap(80.0, confidence="MEDIUM"))["key"] == "OK"
    said = _text(plain.card_plain(_card(confidence="LOW"), {}))
    assert "믿는 정도는 '낮음'" in said and "걱정할 점이 없다는 뜻으로 읽으면 안 됩니다" in said
    assert "걱정할 점이 없다는 뜻" not in _text(plain.card_plain(_card(), {}))
    rows = [{"ticker": "X", "strategy": "LONG_TERM", "entry_status": "ENTRY_NOW", "actionability": "ACTIONABLE", "score": 72.0, "confidence": "LOW"}]
    assert A.candidates(rows, {})["styles"]["LONG_TERM"]["rows"][0]["confidence"] == "LOW"
    assert 'r.confidence === "LOW"' in src("terminal", "static", "assistant.js")


# ---------------------------------------------------------------------- 6 and the version label
def test_the_version_and_the_protocol_say_what_changed():
    assert config.RULES_VERSION == "R-2" and (ROOT / "reports" / "QSF_1_5_3_2026_11_25.md").exists()       # the rules of 1.5.3 carry their own label from 1.6.0 on
    doc = src("reports", "QSF_LIVE_FORWARD_PROTOCOL.md")
    assert "## 바로잡음 (2026-11-25" in doc and "차단(BLOCKED)된 종목도 점수가 있으면 표본에 남는다" in doc and "QSF-1.5.3" in doc
    assert 's.get("actionability") != "INSUFFICIENT_DATA"' in src("terminal", "qsf", "live_forward.py")     # the code the correction describes


# ---------------------------------------------------------------------- P1 (2026-11-25): what speaks against a conclusion is said beside it
def test_the_score_gap_between_statement_bases_is_said_where_the_conclusion_is_read():
    from terminal import analyst_extra as ax
    fp = {"live": "ANNUAL", "annual": {"score": 82.5}, "trailing": {"score": 64.8, "newer_quarter": True}}
    line = ax.gap_line(fp, "LONG_TERM")
    assert "연간 재무로 82.5점" in line and "최근 4분기 재무로 64.8점(-17.7점)" in line and "화면의 점수는 연간 기준" in line
    assert ax.gap_line(fp, "SWING") is None and ax.gap_line({**fp, "trailing": {"score": 80.0, "newer_quarter": True}}, "LONG_TERM") is None
    assert ax.gap_line({**fp, "trailing": {"score": 64.8, "newer_quarter": False}}, "LONG_TERM") is None            # no newer quarter: the same statements twice
    said = _text(plain.card_plain(_card(strategy="LONG_TERM", fund_period=fp), {}))
    assert "재무 기준에 따라 장기 점수가 크게 다릅니다" in said
    assert A.decision_cautions(object(), {"fund_period": fp}, "X", "US", "LONG_TERM", "WAIT") == [line]             # no committee call unless the answer is 사도 됨
    js = src("terminal", "static", "assistant.js")
    assert "같이 볼 것: ${esc(c)}" in js and "v.caveat" in js
