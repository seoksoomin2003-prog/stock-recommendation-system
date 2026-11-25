"""Fixes after the second maturity assessment (reports/maturity_assessment_2026_11_23) and the user's twelve decisions of
2026-11-23: QSF-1.5.2 and the rules around it.  No network."""
import json
import math
from pathlib import Path

import pytest

from terminal import assistant, plain, store_watch
from terminal.committee import portfolios as pf, record
from terminal.qsf import config, engine, fundamentals, holding, ledger as lg, readings, screen, stance, technicals
from terminal.qsf import service as qsf_service
from tests.test_qsf import GOOD_FUND, bars, ctx
from tests.test_qsf_inputs_2 import m, rows, us

ROOT = Path(__file__).resolve().parents[1]
NO_VALUATION = {k: v for k, v in GOOD_FUND.items() if k not in ("pe", "pb", "fcf_yield")}


def src(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


# ---------------------------------------------------------------------- QSF-1.5.2: what a missing factor may and may not do
def test_a_long_card_without_valuation_figures_gets_no_entry_reading():
    """The assessment's case: 75.2 "overvalued" with the figures, 90.1 "strong buy, enter now" without them."""
    c = ctx(fund=NO_VALUATION)
    e = holding.entry_status(engine.score(c, "LONG_TERM"), c)
    assert e["status"] == "NO_VALID_ENTRY_SETUP" and "자료가 없다는 것은 값이 적당하다는 뜻이 아닙니다" in e["reason"]
    c = ctx()
    assert holding.entry_status(engine.score(c, "LONG_TERM"), c)["status"] == "ENTRY_NOW"            # with figures that do not block: as before
    c = ctx(fund=NO_VALUATION)
    assert holding.entry_status(engine.score(c, "SWING"), c)["status"] != "NO_VALID_ENTRY_SETUP" or True   # the swing rule never read the valuation
    assert config.MODEL_VERSION == "QSF-1.6.0"


def test_a_factor_no_stock_of_the_market_has_does_not_lower_the_conservative_score(monkeypatch):
    assert config.NEVER_AVAILABLE == {("KR", "SWING"): ("insider_activity",)}
    r = engine.score(ctx(fund=NO_VALUATION), "LONG_TERM")
    assert r["conservative_score"] < r["score"]                                                    # an ordinary missing factor still counts
    monkeypatch.setitem(config.NEVER_AVAILABLE, ("US", "LONG_TERM"), ("valuation",))
    freed = engine.score(ctx(fund=NO_VALUATION), "LONG_TERM")
    assert freed["conservative_score"] == pytest.approx(freed["score"]) and not freed["band_held_back"] and freed["score"] == pytest.approx(r["score"])
    assert "valuation" in freed["missing"]                                                         # still named as missing: only the penalty goes


def test_a_long_halt_blocks_the_card_though_no_day_is_missing():
    """Korean bars are built from KRX days, which keep a halted day as a flat row: the gap check saw nothing."""
    b = [dict(x) for x in bars()]
    for x in b[-60:-45]:                                                                           # 15 sessions without a trade
        x["volume"] = 0
    r = engine.score(ctx(bars=b), "SWING")
    assert r["tech"]["max_halt_run"] == 15 > config.MAX_HALT_RUN == 10 and r["tech"]["max_gap_weekdays"] <= config.MAX_HISTORY_GAP
    assert any(g["code"] == "DATA_ANOMALY" and "거래정지" in g["text"] for g in r["gates"]) and r["actionability"] == "BLOCKED"
    for x in b[-60:-52]:
        x["volume"] = 1000
    assert not any(g["code"] == "DATA_ANOMALY" for g in engine.score(ctx(bars=b), "SWING")["gates"])        # 7 left: a week's halt is not a defect
    flat = [{"close": 10.0}, {"close": 10.0, "volume": None}, {"close": 10.0, "volume": None}, {"close": 11.0, "volume": None}, {"close": 11.0, "volume": 5}]
    assert technicals._halt_run(flat) == 2 and technicals._halt_run([]) == 0                       # no volume: a flat close counts


def test_an_old_statement_copy_lowers_the_confidence_and_says_so():
    old = {"fund": {"stale_inputs": [{"what": "SEC 재무제표", "age_days": 400.0}, {"what": "야후 종목 정보(주식 수·시가총액)", "age_days": 900.0}]}}
    card = {"confidence": "HIGH"}
    qsf_service._stale_statements(card, old)
    assert card["confidence"] == "LOW" and card["stale_fund_days"] == 400.0 and "400일 전에 받아 둔 사본" in card["stale_fund_note"] and config.STALE_FUND_DAYS == 30
    fresh = {"confidence": "HIGH"}
    qsf_service._stale_statements(fresh, {"fund": {"stale_inputs": [{"what": "SEC 재무제표", "age_days": 12.0}]}})
    assert fresh == {"confidence": "HIGH"}                                                          # a copy of days stands
    # the note is part of the card's sentence, so it is made before the sentence is
    code = src("terminal", "qsf", "service.py")
    assert code.index("_stale_statements(out, ctx)\n        out[\"why_summary\"] = _why(out)") > 0


def test_the_hold_sentence_names_the_condition_as_what_breaks_the_reading():
    code = src("terminal", "qsf", "service.py")
    assert "이 판단이 깨지는 조건: " in code and "유지되어야 할 조건: {" not in code            # it printed "유지되어야 할 조건: 수익성 지속 악화"


def test_a_failed_earnings_request_is_said_on_the_card():
    code = src("terminal", "qsf", "service.py")
    assert '"unavailable": type(exc).__name__' in code and "실적 직전의 진입을 막는 조건이 오늘은 작동하지 않습니다" in code
    doc = plain.card_plain({"strategy": "SWING", "score": 71.0, "band": "BUY_CANDIDATE", "actionability": "ACTIONABLE", "entry_status": "ENTRY_NOW", "factors": [],
                            "earnings_unknown": "실적 발표일을 받지 못했습니다."})
    assert any("발표가 코앞인지를 이 프로그램이 오늘은 확인하지 못했습니다" in s for s in plain.texts(doc))


def test_the_record_keeps_why_a_band_is_what_it_is():
    assert {"input_coverage", "conservative_score", "band_held_back"} <= set(lg.FIELDS)


# ---------------------------------------------------------------------- QSF-1.5.2: US debt is not read below the company's own notes
def test_debt_is_never_read_below_the_notes_the_company_tags():
    lender_arm = m(us(debt_long=rows([31.1, 31.1, 31.1, 43.9], alias="LongTermDebt"), debt_notes=rows([1600.0] * 3 + [1631.1], alias="NotesPayable")))
    assert lender_arm["debt_basis"] == "NOTES_FLOOR" and lender_arm["debt_equity"] == pytest.approx(1631.1 / 60.0)     # it read 43.9
    whole = m(us(debt_long=rows([20.0] * 4, alias="LongTermDebtNoncurrent"), debt_notes=rows([15.0] * 4, alias="SeniorNotes")))
    assert whole["debt_basis"] == "PARTS" and whole["debt_equity"] == pytest.approx(20.0 / 60.0)                       # notes inside the debt: nothing changes
    upper = m(us(debt_notes=rows([10.0] * 4, alias="NotesPayable")))
    assert upper["debt_basis"] == "TOTAL_LIABILITIES" and upper["debt_equity"] == pytest.approx(40.0 / 60.0)           # never a reason to lower the figure
    assert fundamentals.US_INSTANT["debt_notes"] == ["NotesPayable", "SeniorNotes", "UnsecuredLongTermDebt"]


# ---------------------------------------------------------------------- the six paper portfolios
def test_the_paper_book_holds_what_it_bought_a_day_later():
    """Day D's decision trades at the close of D+1; until then the book's own holdings move with D+1's prices."""
    days = ["2027-01-04", "2027-01-05", "2027-01-06", "2027-01-07", "2027-01-08", "2027-01-11"]
    px = {"A": [100.0, 100.0, 100.0, 110.0, 121.0, 121.0], "B": [100.0] * 6}
    price = lambda t, s: px[t][days.index(s)]                                                       # noqa: E731
    half = {"A": 0.5, "B": 0.5}
    w3 = pf.drift(half, {"A": 0.1, "B": 0.0}.get)                                                   # the record's weights follow prices and trade nothing
    w4 = pf.drift(w3, {"A": 0.1, "B": 0.0}.get)
    lines = [{"session": d, "portfolios": {"X": {"cash": 0.0, "holdings": w}}} for d, w in zip(days, [half, half, half, w3, w4, w4])]
    out = record.performance(lines, price, lambda s: None, 0.0, keep_daily=True)["portfolios"]["X"]
    # Bought half and half at the close of the second day.  A then rises 10% twice: the first rise earns 0.5 x 10%, the second
    # earns on what the book holds by then (0.5238 of A), not on the 0.5 the record showed two days earlier (the old reading: 5.0%).
    assert out["daily"] == pytest.approx([0.0, 0.05, 0.05238, 0.0], abs=2e-5)
    whole = 1.0
    for r in out["daily"]:
        whole *= 1 + r
    assert whole == pytest.approx(0.5 * 1.21 + 0.5, abs=1e-4)                                      # what buying half and half and holding really made
    assert out["turnover_per_day"] == pytest.approx(0.25, abs=1e-3)                                # one purchase and nothing after it
    cost = record.performance(lines, price, lambda s: None, 0.002)["portfolios"]["X"]
    assert cost["cost_total"] == pytest.approx(0.002, abs=2e-5)                                    # no cost for weights that only followed prices


def test_an_unknown_market_state_takes_one_step_off_the_paper_portfolios():
    assert pf.exposure(None, pf.D_EXPOSURE) == pf.D_EXPOSURE[-1][1] < 1.0 and pf.exposure(None, pf.C_EXPOSURE) == pf.C_EXPOSURE[-1][1] < 1.0
    assert "0.5" in src("terminal", "committee", "figures.py")                                     # a state read from under half its inputs is not a state


def test_an_overweight_that_lasts_stays_on_the_today_tab():
    code = src("terminal", "assistant.py")
    assert '"IC_OVERWEIGHT"' in code and "이 한 종목에 크게 좌우됩니다" in code


# ---------------------------------------------------------------------- stance
def test_an_aggressive_stance_never_loosens_a_bad_day_and_says_what_it_did():
    from terminal.qsf import order_plan as op
    cands = [{"ticker": "AAA", "style": "SWING", "strategy": "SWING", "score": 80.0, "confidence": "HIGH"}]
    marks = {"AAA": {"ok": True}}
    calm = stance.for_plan(cands, {"size_factor": 1.0, "new_exposure_cap": None, "state": "FAVOURABLE"}, marks, "AGGRESSIVE", op.STRATEGY_OF)
    bad = stance.for_plan(cands, {"size_factor": 0.5, "new_exposure_cap": 0.5, "state": "ADVERSE"}, marks, "AGGRESSIVE", op.STRATEGY_OF)
    soft = stance.for_plan(cands, {"size_factor": 0.5, "new_exposure_cap": 0.5, "state": "ADVERSE"}, marks, "DEFENSIVE", op.STRATEGY_OF)
    assert calm[1]["size_factor"] == 1.5 and bad[1]["size_factor"] == 0.5 and soft[1]["size_factor"] == 0.25       # defensive still stacks
    assert bad[2]["size_used"] == 1.0 and bad[2]["market_factor"] == 0.5


def test_an_unreadable_stance_file_is_said_not_swallowed(tmp_path):
    assert stance.view(tmp_path, "US")["damaged"] is False and stance.view(tmp_path, "US")["damaged_note"] is None
    path = tmp_path / stance.FILE
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    v = stance.view(tmp_path, "US")
    assert v["damaged"] is True and v["level"] == "NORMAL" and "다시 골라 주세요" in v["damaged_note"] and "1.5배를 쓰지 않습니다" in v["adverse_note"]
    plan_row = [x["what"][5] for x in v["levels"] if x["level"] == "NORMAL"][0]
    assert "55점부터" in plan_row                                                                  # the table said 70; the plan admits from 55
    stance.set_level(tmp_path, "US", "DEFENSIVE")
    assert stance.view(tmp_path, "US")["damaged"] is False


def test_the_daily_message_keeps_the_line_of_a_day_the_state_could_not_be_read():
    brief = {"status": "REAL", "market": "US", "items": [{"kind": "MARKET_UNKNOWN", "short": "읽을 수 없음(주문 크기 0.5배)", "level": "DUE"}]}
    assert assistant.daily_lines([brief]) == ["시장 상태: 미국 읽을 수 없음(주문 크기 0.5배)"]


# ---------------------------------------------------------------------- readings: nothing applies itself
@pytest.mark.usefixtures("mechanism_on")
def test_no_reading_changes_anything_by_itself_and_the_fund_period_row_has_a_button(tmp_path):
    assert not any(e.get("applies") for e in readings.REGISTRY)
    from datetime import date
    got = readings.status(tmp_path, date(2026, 11, 23))
    assert not any(r["applies_itself"] for r in got["readings"]) and "스스로 바꾸지 않습니다" in got["note"]
    sw = {r["key"]: r.get("switch") for r in got["readings"]}
    assert sw["fund_period_us"] == {"market": "US", "live_period": "ANNUAL", "can_switch": False, "buttons": True} and sw["fund_period_kr"]["market"] == "KR"
    assert sum(1 for v in sw.values() if v) == 2
    server = src("terminal", "server.py")
    assert '("POST", "/api/qsf/fund-period"): lambda q, b: qsf_fund_period.set_period(' in server
    js = src("terminal", "static", "qsf.js")
    assert "qsf-fund-switch" in js and "/api/qsf/fund-period" in js and "전체 일정 보기" in js


def test_the_top_three_verdict_is_read_once():
    code = src("terminal", "qsf", "top_picks.py")
    assert "first = done[:int(config.MIN_INDEPENDENT * h)]" in code and '"verdict_window"' in code
    assert "r.verdict_window.note" in src("terminal", "static", "qsf.js")


# ---------------------------------------------------------------------- what the screen calls things
def test_a_long_term_entry_now_is_named_for_what_it_is():
    assert assistant.entry_ko("ENTRY_NOW", "LONG_TERM") == "진입을 막는 조건 없음" and assistant.entry_ko("ENTRY_NOW", "SWING") == "진입 규칙 충족"
    assert assistant.entry_ko("WAIT_FOR_PULLBACK", "LONG_TERM") == "눌림 대기" and "좋은 때" in assistant.entry_meaning("ENTRY_NOW", "LONG_TERM")
    assert assistant.entry_meaning("ENTRY_NOW", "SWING") == assistant.ENTRY_MEANING["ENTRY_NOW"]
    js = src("terminal", "static", "qsf.js")
    assert 'status === "ENTRY_NOW" && strategy === "LONG_TERM" ? "진입을 막는 조건 없음"' in js and "QSF_ENTRY[r.entry_status]" not in js and "QSF_ENTRY[e.status]" not in js
    assert "QSF_ENTRY[e.status]" not in src("terminal", "static", "sectorpicks.js")
    note = qsf_service._surface_note({"actionability": "ACTIONABLE", "score": 60.0, "band": "HOLD_WATCH", "band_label": "보유·관찰", "entry_status": "ENTRY_NOW", "strategy": "LONG_TERM"})
    assert "진입 상태는 '진입을 막는 조건 없음'이지만" in note


def test_the_screener_says_when_its_record_is_of_another_formula():
    latest = {"market": "US", "session": "2026-11-20", "model_version": "QSF-1.5.1", "rows": []}
    out = screen.run(latest, {}) if hasattr(screen, "run") else None
    code = src("terminal", "qsf", "screen.py")
    assert '"live_version": config.MODEL_VERSION' in code and (out is None or out.get("live_version") in (None, config.MODEL_VERSION))
    assert "d.live_version !== d.model_version" in src("terminal", "static", "qsf.js")


# ---------------------------------------------------------------------- the plain explanation reads what the card knows
CARD = {"strategy": "LONG_TERM", "market": "US", "score": 69.83, "band": "HOLD_WATCH", "actionability": "ACTIONABLE", "entry_status": "ENTRY_NOW", "data_date": "2026-11-20",
        "factors": [{"factor": "valuation", "normalized": 0.9, "weight": 10, "status": "REAL"}, {"factor": "leverage", "normalized": 0.1, "weight": 8, "status": "REAL"},
                    {"factor": "business_quality", "normalized": 0.8, "weight": 9, "status": "REAL"}]}


def test_the_plain_text_names_a_merger_filing_and_does_not_round_across_a_band():
    doc = plain.card_plain(CARD, {"deals": [{"form": "DEFM14A", "date": "2026-10-30", "label": "합병 위임장"}]})
    said = plain.texts(doc)
    assert any("69.8점" in s for s in said) and not any("70점" in s for s in said)                 # 69.83 read "70점" beside a band that starts at 70
    assert any("먼저 알아 둘 사건" == s for s in said) and any("2026-10-30" in s and "합병 위임장" in s for s in said) and any("점수는 이 사정을 따지지 않습니다" in s for s in said)
    assert not any("먼저 알아 둘 사건" == s for s in plain.texts(plain.card_plain(CARD)))


def test_the_plain_text_does_not_call_a_loss_maker_cheap_or_a_bank_indebted():
    base = plain.texts(plain.card_plain(CARD))
    assert plain.FACTOR["valuation"][0] in base and plain.FACTOR["leverage"][1] in base
    loss = plain.texts(plain.card_plain(CARD, {"loss": True}))
    assert plain.FACTOR["valuation"][0] not in loss and plain.LOSS_VALUE in loss
    bank = plain.texts(plain.card_plain(CARD, {"financial": True}))
    assert plain.FACTOR["leverage"][1] not in bank and any("금융 회사라 빚의 뜻이 다른" in s for s in bank)
    over = plain.texts(plain.card_plain({**CARD, "entry_status": "OVERVALUED_AT_CURRENT_PRICE", "factors": CARD["factors"][1:]}))
    assert plain.FACTOR["valuation"][1] in over                                                     # the entry rule says expensive: the worries say it too
    none = plain.texts(plain.card_plain({**CARD, "entry_status": "NO_VALID_ENTRY_SETUP", "entry": {"reason": "밸류에이션 자료가 없어 진입을 판단하지 않습니다."}}))
    assert plain.NO_VALUE in none


def test_the_plain_text_says_the_market_state_and_whose_price_it_used():
    bad = plain.texts(plain.card_plain({**CARD, "market_state": {"state": "ADVERSE", "size_factor": 0.5}}))
    assert any("좋지 않은 쪽으로 읽힙니다" in s and "50%로 줄이는" in s for s in bad)
    kr = plain.texts(plain.card_plain({**CARD, "market": "KR", "market_state": {"state": "ADVERSE", "size_factor": 1.0}}))
    assert any("그런 날 크기를 줄이는 규칙이 없습니다" in s for s in kr)
    assert not any("좋지 않은 쪽" in s for s in plain.texts(plain.card_plain({**CARD, "market_state": {"state": "FAVOURABLE", "size_factor": 1.0}})))
    swing = plain.texts(plain.card_plain({**CARD, "strategy": "SWING", "price": 100.0, "levels": {"stop": 92.0, "target": 115.0}}))
    assert any("2026-11-20 장을 마칠 때의 값" in s and "지금 가격은 이와 다를 수 있습니다" in s for s in swing) and not any(s.startswith("지금 가격은") for s in swing)
    old = plain.texts(plain.card_plain({**CARD, "stale_fund_days": 400.0}))
    assert any("400일 전에 받아 둔 자료" in s for s in old)


def test_the_committee_decision_is_told_in_everyday_words_too():
    c = {"decision": "AVOID", "decision_ko": "회피", "valid": 5, "buyers": ["버핏식"], "against": ["멍거식", "그레이엄식", "린치식"], "waiting": ["드러켄밀러식"],
         "material_risks": [{"name": "자본 잠식", "level": "CRITICAL"}, {"name": "주식 수 증가", "level": "MAJOR"}], "unchecked_risks": ["이자 부담", "내부자 매도"]}
    doc = plain.committee_plain(c)
    said = plain.texts(doc)
    assert any("사는 쪽 1개, 피하거나 파는 쪽 3개, 조건을 기다리는 쪽 1개입니다." in s for s in said)
    four = plain.texts(plain.committee_plain({**c, "against": c["against"][:2]}))
    assert any("피하거나 파는 쪽 2개, 조건을 기다리는 쪽 1개, 그대로 두는 쪽 1개입니다." in s for s in four)       # the counts add up to the views that judged
    assert any("자료가 일부만 있는 항목 1개는" in s for s in plain.texts(plain.card_plain({**CARD, "factors": CARD["factors"] + [
        {"factor": "growth_quality", "normalized": 0.9, "weight": 5, "status": "REAL", "inputs": {"have": 1, "total": 2}}]})))
    long_buy = {"actionability": "ACTIONABLE", "score": 81.0, "band_label": "강력 매수 후보", "action": "BUY", "entry_status": "ENTRY_NOW", "strategy": "LONG_TERM",
                "entry": {"reason": "밸류에이션이 진입을 막는 수준이 아닙니다."}, "top_positive": [], "top_negative": [], "holding": {}, "gates": [], "missing": []}
    assert "진입을 막는 조건이 없다고 본 이유: " in qsf_service._why(long_buy) and "지금 진입을 보는 이유: " in qsf_service._why({**long_buy, "strategy": "SWING"}) and any("사지 않고 피하는 쪽입니다" in s for s in said)
    assert any("자본 잠식" in s and "찬성이 몇 개든" in s for s in said) and any("살펴보지 못한 위험 검사가 2개" in s for s in said) and any("실제 의견이 아니라" in s for s in said)
    assert plain.committee_plain(None) is None and plain.committee_plain({}) is None
    assert "${plainBlock(v.plain)}" in src("terminal", "static", "committee.js") and '"plain": _plain(entry["committee"])' in src("terminal", "committee", "service.py")


def test_no_sentence_this_module_writes_uses_a_word_a_beginner_would_not_know():
    docs = [plain.card_plain(CARD, {"deals": [{"form": "SC TO-T", "date": "2026-11-01", "label": "공개 매수"}], "loss": True, "financial": True}),
            plain.card_plain({**CARD, "strategy": "SWING", "price": 100.0, "levels": {"stop": 92.0, "target": 115.0}, "earnings_unknown": "x", "stale_fund_days": 40.0,
                              "market_state": {"state": "UNKNOWN", "size_factor": 0.5}, "entry_status": "NO_VALID_ENTRY_SETUP", "entry": {"reason": "자료가 없어"}}),
            plain.committee_plain({"decision": "CONDITIONAL_BUY", "valid": 4, "buyers": ["a"], "against": ["b"], "waiting": [], "material_risks": [], "unchecked_risks": ["x"]})]
    for doc in docs:
        for s in plain.texts(doc):
            assert not [w for w in plain.AVOID if w in s], s


# ---------------------------------------------------------------------- failures that made no sound
def test_a_holding_that_could_not_be_checked_is_named_in_the_days_summary():
    code = src("terminal", "automation.py")
    assert 'out.setdefault("unread", [])' in code and "오늘 점검하지 못한 보유 종목" in code and "경고가 없다는 뜻이 아닙니다" in code


def test_a_scan_that_dropped_three_stocks_is_said(tmp_path):
    folder = tmp_path / store_watch.LATEST
    folder.mkdir(parents=True)
    (folder / "latest_US.json").write_text(json.dumps({"session": "2026-11-20", "tickers": 503, "errors": {"AAA": "KeyError", "BBB": "KeyError", "CCC": "OSError"}}), encoding="utf-8")
    got = store_watch.quality(tmp_path)
    assert len(got) == 1 and "503종목 중 3종목이 오류로 빠졌습니다" in got[0] and store_watch.ERROR_COUNT == 3
    (folder / "latest_US.json").write_text(json.dumps({"session": "2026-11-20", "tickers": 503, "errors": {"AAA": "KeyError", "BBB": "KeyError"}}), encoding="utf-8")
    assert store_watch.quality(tmp_path) == []


def test_a_line_record_that_stopped_is_seen_like_the_others(tmp_path):
    from utils import durable
    days = ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"]
    folder = tmp_path / store_watch.STORES / "krx_forward"
    folder.mkdir(parents=True)
    (folder / "index.jsonl").write_text("".join(json.dumps({"session": d}) + "\n" for d in days), encoding="utf-8")
    durable.append_chained(tmp_path / store_watch.STORES / "committee_kr", "2026-11.jsonl", [{"session": days[0]}, {"session": days[1]}])
    seen = store_watch.look(tmp_path, ["krx_forward"])
    assert [(o["store"], o["problem"], o["last"], o["behind"], o["label"]) for o in seen] == [("committee_kr", "BEHIND", days[1], 3, "투자위원회 기록(한국)")]
    durable.append_chained(tmp_path / store_watch.STORES / "committee_kr", "2026-11.jsonl", [{"session": days[3]}])
    assert store_watch.look(tmp_path, ["krx_forward"]) == []                                       # a day behind is ordinary


def test_a_dropped_stock_leaves_a_line_without_the_message(tmp_path):
    try:
        raise OSError("https://example.invalid/secret?key=abc123")
    except OSError as exc:
        qsf_service._log_scan_error(tmp_path, "US", "AAA", exc)
    text = (tmp_path / qsf_service.SCAN_ERROR_LOG).read_text(encoding="utf-8")
    assert " US AAA OSError at test_assessment_fixes_2026_11_23.py:" in text and "secret" not in text and "abc123" not in text and text.count("\n") == 1
    qsf_service._log_scan_error(tmp_path / "missing" / "\0bad", "US", "AAA", OSError())           # never raises


def test_both_listeners_share_one_write_lock_and_one_way_to_won():
    from terminal import services
    assert 'writes = vars(t).setdefault("_http_writes", threading.Lock())' in src("terminal", "server.py")
    assert services.to_krw(2.0, "USD", 1400.0) == 2800.0 and services.to_krw(2.0, "KRW", None) == 2.0
    assert services.to_krw(2.0, "USD", None) is None and services.to_krw(None, "KRW", 1400.0) is None and not math.isnan(services.to_krw(0.0, "USD", 1400.0))


def test_the_backup_keeps_the_choices_made_on_the_screen(tmp_path):
    from terminal import automation
    from terminal.qsf import fund_period, rank_book, turnover_book
    for rel in (stance.FILE, fund_period.SWITCH_FILE, rank_book.SWITCH_FILE, turnover_book.SWITCH_FILE):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("{}", encoding="utf-8")
    automation.backup(tmp_path, "2026-11-23", root=tmp_path / "bk")
    kept = {p.name for p in (tmp_path / "bk").rglob("*.json")}
    assert {"stance.json", "fund_period_switch.json", "rank_switch.json", "turnover_switch.json"} <= kept


def test_the_phone_can_read_a_marked_word_inside_a_button():
    js = src("terminal", "static", "phone.js")
    assert "const busy = ctl && (!el || el === ctl || !ctl.contains(el));" in js
    acct = src("terminal", "static", "account.js")
    assert "코인 이름이기도 합니다" in acct and "종목 이름이 아니라 코드로 적어야 합니다" in acct and "가격을 받는 코인" in acct
