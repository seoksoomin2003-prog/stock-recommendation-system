"""Two interrupts of the six portfolios (user request and decisions 2026-11-23): daily judgement stays; a held weight follows
its price; an overweight holding is told and left alone; a stock with fatal damage is in none of the six."""
import pytest

from terminal import assistant, plain
from terminal.committee import figures as fg, investors as iv, portfolios as pf, record, service
from tests import committee_cases as cc
from tests.test_committee import CTX, book


def held_book(cases):
    b = book(cases)
    for t, e in b.items():                                         # judged again as stocks already held
        b[t] = service.judge(e["figures"], {k: True for k in pf.ORDER}, CTX)
    return b


# ---------------------------------------------------------------------- weights follow prices
def test_a_held_weight_follows_its_price_and_cash_is_part_of_the_whole():
    got = pf.drift({"UP": 0.12, "FLAT": 0.10, "DOWN": 0.08}, {"UP": 0.5, "FLAT": 0.0, "DOWN": -0.25}.get)
    whole = 0.70 + 0.18 + 0.10 + 0.06
    assert got == {"UP": round(0.18 / whole, 4), "FLAT": round(0.10 / whole, 4), "DOWN": round(0.06 / whole, 4)}
    assert pf.drift({"A": 0.1}, None) == {"A": 0.1} and pf.drift(None, lambda t: 0.1) == {} and pf.drift({"A": 0.1}, lambda t: None) == {"A": 0.1}      # an unknown move leaves it unmoved
    assert not hasattr(pf, "REBALANCE_STEP") and not hasattr(pf, "_steady")                                    # a held position is no longer pulled to a target


def test_a_grown_holding_is_left_alone_and_the_rule_is_told():
    b = held_book([dict(ticker="KEEP"), dict(cc.A_EXCELLENT_BUT_DEAR, ticker="WAITS")])
    prev = {"KEEP": 0.12, "WAITS": 0.07}
    p = pf.investor_portfolio("BUFFETT", b, prev, 60.0, None, {"KEEP": 0.80, "WAITS": 0.0}.get)
    rows = {r["ticker"]: r for r in p["holdings"]}
    grown = round(0.12 * 1.8 / (0.81 + 0.216 + 0.07), 4)
    assert rows["KEEP"]["weight"] == grown and grown > 0.18 > pf.SPEC["BUFFETT"]["cap"]                      # over the cap and not cut back
    note = p["overweight"][0]
    assert len(p["overweight"]) == 1 and note["ticker"] == "KEEP" and note["new"] is True and note["cap"] == 0.12 and note["line"] == 0.18 and note["to_cash"] == round(grown - 0.12, 4)
    assert "12%로 줄이고" in note["text"] and "현금으로 두는 것입니다" in note["text"] and "알리기만 합니다" in note["text"] and rows["KEEP"]["overweight"] is True
    assert not any(w in note["text"] for w in ("추천합니다", "사세요", "파세요"))                              # a rule's answer, never advice
    assert p["turnover"] == 0.0 and p["fatal"] == []                                                         # nothing was traded: the weights only moved with prices
    again = pf.investor_portfolio("BUFFETT", b, {"KEEP": grown, "WAITS": 0.06}, 60.0, None, lambda t: 0.0)
    assert again["overweight"][0]["new"] is False                                                            # still over the line: shown, but not news
    small = pf.investor_portfolio("BUFFETT", b, prev, 60.0, None, {"KEEP": 0.40, "WAITS": 0.0}.get)
    assert small["overweight"] == [] and "overweight" not in {k for r in small["holdings"] for k in r}        # 16%: over the cap, under one and a half times it
    assert pf.OVERWEIGHT_FACTOR == 1.5


def test_new_positions_take_the_room_that_is_left_and_only_they_are_capped():
    got = pf._fit({"OLD": 0.30, "N1": 0.20, "N2": 0.20}, 0.12, 1.0, {"OLD": 0.30})
    assert got == {"OLD": 0.30, "N1": 0.12, "N2": 0.12}
    tight = pf._fit({"OLD": 0.90, "N1": 0.12, "N2": 0.12}, 0.12, 1.0, {"OLD": 0.90})
    assert tight["OLD"] == 0.90 and tight["N1"] == tight["N2"] == 0.05                                       # what room there is, shared
    storm = pf._fit({"O1": 0.40, "O2": 0.20, "N1": 0.10}, 0.18, 0.40, {"O1": 0.40, "O2": 0.20})              # the regime lowered what may be invested
    assert storm["N1"] == 0.0 and storm["O1"] == pytest.approx(0.2667, abs=1e-4) and storm["O2"] == pytest.approx(0.1333, abs=1e-4)
    assert pf._fit({"N1": 0.3}, 0.12, 1.0) == {"N1": 0.12}


# ---------------------------------------------------------------------- fatal damage
def test_a_severe_filing_or_the_inversion_risk_takes_a_stock_out_of_all_six():
    b = held_book([dict(ticker="KEEP"), dict(ticker="FILED"), dict(cc.E_CHEAP_LEVERED, ticker="RISKY")])
    b["FILED"]["figures"]["severe"] = ["상장폐지 통지 (8-K 3.01)"]
    risk = b["RISKY"]["opinions"]["MUNGER"]["downside_risk"]["value"]
    assert risk >= iv.M_RISK_AVOID == 50.0 and pf.fatal(b["KEEP"]) is None
    assert pf.fatal(b["FILED"]) == "심각 공시: 상장폐지 통지 (8-K 3.01)" and pf.fatal(b["RISKY"]) == f"거꾸로 따져 본 영구 손실 위험 {risk:.0f}/100 (기준 50 이상)"
    prev = {k: {"KEEP": 0.05, "FILED": 0.05, "RISKY": 0.05} for k in pf.ORDER}
    ports = pf.build(b, prev, 60.0)
    for key, p in ports.items():
        held = {r["ticker"] for r in p["holdings"]}
        assert "FILED" not in held and "RISKY" not in held, key                                              # whatever that engine itself says
        assert [n["ticker"] for n in p["fatal"]] == ["FILED", "RISKY"] and all(n["weight"] == 0.05 for n in p["fatal"]), key
        assert sum("치명적 훼손으로 전량 제외" in x["why"] for x in p["exits"]) == 2 and p["cash"] >= 0.10 - 1e-9, key      # what they held stays in cash
    fresh = pf.build(b, None, 60.0)                                                                          # and it is not admitted in the first place
    assert all(r["ticker"] not in ("FILED", "RISKY") for p in fresh.values() for r in p["holdings"]) and all(p["fatal"] == [] for p in fresh.values())
    assert set(pf.interrupts(ports)) == set(pf.ORDER) and pf.interrupts(fresh) == {}


def test_the_severe_filing_is_read_from_the_score_engines_gate():
    snap = {"ticker": "AAA", "market": "US", "data_date": "2026-11-20", "price": 10.0, "factors": [],
            "gates": [{"code": "SEVERE_EVENT", "text": "심각한 공시: 파산·회생 절차 (8-K 1.03)"}, {"code": "LOW_LIQUIDITY", "text": "거래 적음"}]}
    assert fg.read(snap, dict(snap))["severe"] == ["심각한 공시: 파산·회생 절차 (8-K 1.03)"]                   # once, though both snapshots carry it
    assert fg.read({**snap, "gates": []}, None)["severe"] == [] and cc.figures()["severe"] == []


# ---------------------------------------------------------------------- the record, the paper results, the messages
def test_the_record_keeps_the_days_interrupts_and_a_weight_that_only_drifted_costs_nothing():
    b = held_book([dict(ticker="KEEP"), dict(ticker="FILED")])
    b["FILED"]["figures"]["severe"] = ["관리종목"]
    ports = pf.build(b, {k: {"KEEP": 0.12, "FILED": 0.05} for k in pf.ORDER}, 60.0, None, {"KEEP": 0.80, "FILED": 0.0}.get)
    row = record.line("US", "2026-11-24", b, ports)["portfolios"]["BUFFETT"]
    gone = round(0.05 / (0.83 + 0.12 * 1.8 + 0.05), 4)                                                       # its weight after the other holding grew
    assert row["overweight"][0]["ticker"] == "KEEP" and row["overweight"][0]["new"] is True and row["fatal"] == [{"ticker": "FILED", "name": "FILED Co", "weight": gone, "why": "심각 공시: 관리종목"}]
    assert "overweight" not in record.line("US", "2026-11-24", b, pf.build(b, None, 60.0))["portfolios"]["GRAHAM"]
    # paper results: weights that follow the price exactly are not trades
    days = [f"2026-12-{d:02d}" for d in range(1, 8)]
    price = lambda t, s: 100.0 * 1.02 ** days.index(s)      # noqa: E731
    w, lines = 0.5, []
    for d in days:
        lines.append({"session": d, "portfolios": {"X": {"cash": round(1 - w, 6), "holdings": {"UP": w}}}})
        w = w * 1.02 / (1 - w + w * 1.02)
    drifted = record.performance(lines, price, lambda s: None, 0.002)["portfolios"]["X"]
    fixed = record.performance([{"session": d, "portfolios": {"X": {"cash": 0.5, "holdings": {"UP": 0.5}}}} for d in days], price, lambda s: None, 0.002)["portfolios"]["X"]
    assert drifted["cost_total"] == pytest.approx(0.5 * 0.002, abs=1e-6)                                     # the first purchase only
    assert fixed["cost_total"] > drifted["cost_total"] and fixed["turnover_per_day"] > drifted["turnover_per_day"]      # holding a weight still against a rising price is selling


def test_the_today_tab_and_the_daily_message_tell_an_interrupt_once():
    row = {"session": "2026-11-24", "portfolios": {
        "BUFFETT": {"overweight": [{"ticker": "KEEP", "name": "킵", "weight": 0.197, "cap": 0.12, "new": True, "text": "버핏식: 킵의 비중이 19.7%까지 커졌습니다."}],
                    "fatal": [{"ticker": "FILED", "name": "파일드", "weight": 0.05, "why": "심각 공시: 관리종목"}]},
        "GRAHAM": {"fatal": [{"ticker": "FILED", "name": "파일드", "weight": 0.05, "why": "심각 공시: 관리종목"}],
                   "overweight": [{"ticker": "OLD", "name": "올드", "weight": 0.09, "cap": 0.05, "new": False, "text": "그레이엄식: 올드"}]}}}
    items = assistant.committee_items(row, "US", "2026-11-24")
    # an overweight that lasts stays on the Today tab as a reference line (user decision 2026-11-23); only the crossing day is news
    assert [i["kind"] for i in items] == ["IC_INTERRUPT", "IC_INTERRUPT", "IC_OVERWEIGHT"] and [i["ticker"] for i in items] == ["FILED", "KEEP", "OLD"]
    assert items[2]["level"] == "INFO" and items[2]["short"] is None and "이 한 종목에 크게 좌우됩니다" in items[2]["text"] and "이 한 종목에 크게 좌우됩니다" in items[1]["text"]
    assert "버핏식, 그레이엄식 포트폴리오에서 전부 뺐습니다" in items[0]["text"] and "주문이 아닙니다" in items[0]["text"] and items[0]["tab"] == "committee"
    assert items[1]["short"] == "버핏식 KEEP 비중 20%(규칙은 12%로 축소)" and assistant.committee_items(row, "US", "2026-11-25") == [] and assistant.committee_items(None, "US", "2026-11-24") == []
    lines = assistant.daily_lines([{"status": "REAL", "market": "US", "items": items}])
    assert lines == ["가상 포트폴리오 알림: 미국 FILED 전량 제외(버핏식, 그레이엄식), 버핏식 KEEP 비중 20%(규칙은 12%로 축소)"]
    assert assistant.daily_lines([{"status": "REAL", "market": "US", "items": []}]) == [] and "committee" in assistant.PART_KO


def test_the_plain_explanation_tells_the_days_notices_in_everyday_words():
    p = {"key": "BUFFETT", "name": "버핏식 포트폴리오", "holdings": [{"ticker": "KEEP", "name": "킵", "weight": 0.197}], "invested": 0.197, "cash": 0.803, "sectors": {"기술": 0.197},
         "overweight": [{"ticker": "KEEP", "name": "킵", "weight": 0.197, "cap": 0.12}], "fatal": [{"ticker": "FILED", "name": "파일드", "weight": 0.05, "why": "심각 공시: 관리종목"}]}
    doc = plain.portfolio_plain(p)
    notes = next(x["lines"] for x in doc["parts"] if x["h"] == "오늘의 알림")
    assert "킵의 값이 많이 올라 이 바구니의 20%를 차지합니다" in notes[0] and "12%로 줄이고 나머지를 현금으로" in notes[0] and "파일드에 큰 문제가 드러나" in notes[1]
    assert not any(w in " ".join(plain.texts(doc)) for w in plain.AVOID)
    assert "오늘의 알림" not in [x["h"] for x in plain.portfolio_plain({**p, "overweight": [], "fatal": []})["parts"]]


def test_the_price_move_since_the_last_record_is_read_from_todays_own_series():
    class Q:
        def _loader(self, market):
            return {"AAA": [{"date": "2026-11-20", "close": 200.0, "adj_close": 100.0}, {"date": "2026-11-23", "close": 110.0, "adj_close": 110.0}],      # a 2-for-1 split in between
                    "OLD": [{"date": "2026-11-20", "close": 50.0}], "NEW": [{"date": "2026-11-23", "close": 50.0}]}.get

    class T:
        qsf = Q()
    move = service._moves(T(), "US", "2026-11-20")
    assert move("AAA") == pytest.approx(0.10) and move("OLD") is None and move("NEW") is None and move("NONE") is None      # the adjusted series: the split is not a fall
    assert service._moves(T(), "US", None) is None                                                         # no earlier record: nothing to move
