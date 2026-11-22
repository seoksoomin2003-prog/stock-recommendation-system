"""The fixes of the audit of 2026-11-22 that needed no decision (reports/audit_2026_11_22_master/REMEDIATION_ROADMAP.md, order 1,
2-ga, 3, 5, 6, 14, 15, 17, 19, 21, 22, 24, 25).  The score itself is unchanged by every one of them."""
import inspect
import json
from argparse import Namespace
from datetime import date
from pathlib import Path

import numpy as np
import pytest

import app
from terminal import assistant, store_watch
from terminal.cache import FileCache
from terminal.committee import council, figures as fg, investors as iv, record
from terminal.qsf import engine, factors, holding, order_plan
from terminal.qsf import service as qsf_service
from terminal.qsf.service import QSF
from tests import committee_cases as cc
from tests.test_qsf import GOOD_FUND, bars, ctx
from utils import durable

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------- 1: the worst market state is not "no reading"
def test_a_market_state_of_zero_raises_the_exit_warning():
    c = ctx()
    r = engine.score(c, "SWING")
    for value, hit in ((0.0, True), (24.9, True), (25.0, False), (None, False)):
        r["domains"]["REGIME"]["score_100"] = value
        said = json.dumps(holding.evaluate_exit(r, c, {"opened": "2026-11-01"}, date(2026, 11, 5)), ensure_ascii=False, default=str)
        assert ("REGIME_SEVERE" in said) is hit, value


# ---------------------------------------------------------------------- 2-ga: a factor built from part of its inputs
def test_a_mean_remembers_how_many_inputs_it_had_and_is_still_the_same_number():
    m = factors.mean([0.2, None, 0.6, None])
    assert m == pytest.approx(0.4) and (m.have, m.total) == (2, 4) and factors.mean([None, None]) is None
    whole, part = factors.obs(factors.mean([0.5, 0.5]), {}, "t", "s", None), factors.obs(m, {}, "t", "s", None)
    assert "inputs" not in whole and part["inputs"] == {"have": 2, "total": 4} and type(part["normalized"]) is float


def test_missing_figures_inside_factors_lower_the_confidence_label_and_leave_the_score_alone():
    full = engine.score(ctx(), "LONG_TERM")
    assert full["confidence"] == "HIGH" and full["input_coverage"] == pytest.approx(full["coverage"], abs=0.02)
    thin_fund = {k: v for k, v in GOOD_FUND.items() if k in ("status", "source", "filed", "gross_margin", "pb", "rev_cagr3", "fcf_years_positive", "share_change", "current_ratio", "debt_equity",
                                                               "returns_capital", "insider_pct", "op_margin")}
    thin = engine.score(ctx(fund=thin_fund), "LONG_TERM")
    assert thin["coverage"] >= 0.9 and thin["input_coverage"] < 0.8 and thin["confidence"] in ("MEDIUM", "LOW") and thin["partial"]          # was HIGH on a full coverage figure
    assert thin["actionability"] != "INSUFFICIENT_DATA"                    # the sufficiency rule and the gates read coverage as before
    # the score is the weighted mean it always was: the label changed, not the arithmetic
    again = sum(f["weight"] * f["normalized"] for f in thin["factors"] if f.get("scored", True) is not False and f["normalized"] is not None)
    weight = sum(f["weight"] for f in thin["factors"] if f.get("scored", True) is not False and f["normalized"] is not None)
    assert thin["score"] == pytest.approx(100 * again / weight)


# ---------------------------------------------------------------------- 22: no buy band on a card that cannot be judged
def test_a_card_that_cannot_be_judged_shows_no_band_label_and_keeps_its_band_code():
    r = engine.score(ctx(fund=None, events=None, regime=None), "LONG_TERM")
    assert r["actionability"] == "INSUFFICIENT_DATA" and r["band_label"] == engine.INSUFFICIENT_BAND_LABEL and r["band"] == engine.classify(r["score"])["band"]
    ok = engine.score(ctx(), "LONG_TERM")
    assert ok["band_label"] == engine.classify(ok["score"])["band_label"]


# ---------------------------------------------------------------------- 17: doubled and out-of-order price rows
def test_a_doubled_or_backward_price_row_is_counted_and_blocks_the_card():
    b = bars()
    r = engine.score(ctx(bars=b + [dict(b[-1])]), "SWING")
    assert r["tech"]["row_defects"] == 1 and any(g["code"] == "DATA_ANOMALY" and "겹치거나" in g["text"] for g in r["gates"]) and r["actionability"] == "BLOCKED"
    clean = engine.score(ctx(), "SWING")
    assert clean["tech"]["row_defects"] == 0 and not any("겹치거나" in g["text"] for g in clean["gates"])


# ---------------------------------------------------------------------- 3: the committee reads the score engine's financial flag
def _with_status(snap, status):
    for f in snap["factors"]:
        if f["factor"] in fg.FINANCIAL_FACTORS:
            f["status"] = status
    return snap


def test_a_card_network_under_the_financial_sector_label_is_not_judged_as_a_bank():
    long_, swing, info, _ = cc.snaps(ticker="V")
    as_company = fg.read(_with_status(long_, "REAL"), swing, info, "금융")
    assert as_company["kind"] == "GENERAL" and as_company["op_margin"] is not None and as_company["_status"]["debt_equity"] == fg.CONFIRMED
    long_, swing, info, _ = cc.snaps(ticker="BANK")
    as_bank = fg.read(_with_status(long_, "NOT_APPLICABLE"), swing, info, "산업재")          # the engine's own flag decides, whatever the label
    assert as_bank["kind"] == "FINANCIAL" and as_bank["op_margin"] is None and as_bank["_status"]["debt_equity"] == fg.NOT_APPLICABLE
    assert cc.figures(sector="금융")["kind"] == "FINANCIAL"                 # a record without factor statuses: the label, as before


# ---------------------------------------------------------------------- 5: a missing figure is not a passed safety check
def test_a_buying_verdict_with_an_unread_safety_figure_becomes_waiting_and_says_which():
    cheap = dict(pe=8.0, pb=0.9, trailing_pe=8.0, fcf_yield=0.09)
    weak = iv.graham(cc.figures(**cheap, current_ratio=0.9, debt_equity=1.9, cash_debt=0.05))
    gone = iv.graham(cc.figures(**cheap, current_ratio=None, debt_equity=None, cash_debt=None))
    assert weak["recommendation"] == iv.AVOID and gone["recommendation"] == iv.WAIT and gone["capped_from"] in iv.BUY_SIDE          # was STRONG_BUY
    assert set(gone["unchecked"]) == {"유동비율", "부채/자본"} and "없는 수치를 통과로 치지 않" in gone["opinion"] and gone["suggested_weight"] == 0.0
    trap = iv.graham(cc.figures(**cheap, fcf_margin=None, ocf_to_ni=None))
    assert trap["recommendation"] == iv.WAIT and iv.lynch(cc.figures(debt_equity=None, ocf_to_ni=None))["recommendation"] == iv.WAIT
    whole = iv.graham(cc.figures(**cc.B_SOUND_AND_CHEAP))
    assert whole["recommendation"] in iv.BUY_SIDE and whole["unchecked"] == [] and whole["capped_from"] is None          # nothing missing: as before
    bank = cc.figures(sector="금융", roe=0.2)
    assert not [o for o in iv.evaluate(bank) if "부채/자본" in (o.get("unchecked") or [])]          # not applicable is an answer, not a gap


def test_thin_data_lowers_the_verdict_and_the_committee_does_not_buy_under_its_data_floor():
    f = cc.figures(sector="금융", roe=0.30, pe=9.0, trailing_pe=9.0, forward_pe=8.5, profit_years=1.0, eps_cagr3=None, rev_cagr3=None, share_change=None, returns_capital=None)
    b = iv.buffett(f)
    assert b["confidence"] < iv.STRONG_MIN_CONFIDENCE and b["recommendation"] != iv.STRONG_BUY and (b["capped_from"] == iv.STRONG_BUY or b["recommendation"] not in iv.BUY_SIDE)
    weak = dict(pe=8.0, pb=0.9, trailing_pe=8.0, forward_pe=7.5, fcf_yield=0.09)
    gone = {k: None for k in ("current_ratio", "debt_equity", "cash_debt", "fcf_margin", "ocf_to_ni", "profit_years", "eps_growth", "rev_growth")}
    f = cc.figures(**weak, **gone)
    d = council.decide(f, iv.evaluate(f))
    assert d["decision"] not in iv.BUY_SIDE + (council.CONDITIONAL_BUY,) and set(d["unchecked_risks"]) >= {"과도한 부채", "이익의 질", "사업의 구조적 악화"}
    assert any("확인하지 못한 위험 검사" in w for w in d["reasons"])


# ---------------------------------------------------------------------- 6: the line records are written like the other forward records
def test_a_line_record_is_chained_and_refuses_to_grow_after_a_cut_line(tmp_path):
    folder = tmp_path / "store"
    assert durable.append_chained(folder, "2026-11.jsonl", [{"session": "2026-11-23", "x": 1}]) == 1
    assert durable.append_chained(folder, "2026-11.jsonl", [{"session": "2026-11-24", "x": 2}], skip=lambda: True) == 0          # another writer had it
    assert durable.append_chained(folder, "2026-12.jsonl", [{"session": "2026-12-01", "x": 3}]) == 1
    assert durable.verify_chained(folder) == {"status": "OK", "lines": 2} and durable.verify_chained(tmp_path / "none") == {"status": "EMPTY", "lines": 0}
    with pytest.raises(ValueError):
        durable.append_chained(folder, "2026-11.jsonl", [{"session": "2026-11-25"}])                 # lines go in order only
    text = (folder / "2026-11.jsonl").read_text()
    (folder / "2026-11.jsonl").write_text(text.replace('"x": 1', '"x": 9'))
    assert durable.verify_chained(folder)["status"] == "BROKEN"                                      # a changed line breaks the chain
    (folder / "2026-11.jsonl").write_text(text)
    with open(folder / "2026-12.jsonl", "a") as fh:
        fh.write('{"session": "2026-12-02", "x"')
    with pytest.raises(durable.TornFile):
        durable.append_chained(folder, "2026-12.jsonl", [{"session": "2026-12-03"}])
    assert durable.verify_chained(folder)["status"] == "TORN" and (folder / "2026-12.jsonl").read_text().endswith('"x"')          # and the cut line is not repaired


def test_the_committee_record_is_written_that_way_and_the_watch_says_when_it_is_damaged(tmp_path):
    f = cc.figures()
    entry = {"opinions": {o["investor"]: o for o in iv.evaluate(f)}, "committee": council.decide(f, iv.evaluate(f))}
    ports = {k: {"cash": 1.0, "holdings": [], "count": 0} for k in list(iv.ORDER) + ["COMMITTEE"]}
    assert record.append(tmp_path, "US", "2026-11-23", {"GOOD": entry}, ports)["status"] == "OK"
    assert record.append(tmp_path, "US", "2026-11-23", {"GOOD": entry}, ports)["status"] == "ALREADY"
    folder = tmp_path / "research_data" / "committee_us"
    assert durable.verify_chained(folder) == {"status": "OK", "lines": 1} and record.read(tmp_path, "US")[0]["chain"] and store_watch.look(tmp_path, []) == []
    with open(folder / "2026-11.jsonl", "a") as fh:
        fh.write('{"session": "2026-11-24"')
    with pytest.raises(durable.TornFile):
        record.append(tmp_path, "US", "2026-11-24", {"GOOD": entry}, ports)
    seen = store_watch.look(tmp_path, [])
    assert [(i["store"], i["problem"]) for i in seen] == [("committee_us", "INDEX_TORN")] and "기록 파일 손상" in store_watch.phrase(seen[0])
    assert len(record.read(tmp_path, "US")) == 1                                                    # what was whole is still read


# ---------------------------------------------------------------------- 15: a scan of named stocks is not recorded unless asked
def test_a_scan_of_named_stocks_writes_no_record_unless_record_is_asked(capsys):
    seen = []

    class Q:
        def scan(self, market, tickers=None, record=True, progress=None, publish=True):
            seen.append((tickers, record, publish))
            return {"status": "DATA_NOT_READY", "errors": {}, "rows": []}
    for tickers, dry, rec, want in ((["AAA"], False, False, False), (["AAA"], False, True, True), ([], False, False, True), ([], True, False, False), (["AAA"], True, True, False)):
        app._qsf_scan(Namespace(tickers=tickers, dry_run=dry, record=rec), Q(), "US")
        assert seen[-1][1] is want, (tickers, dry, rec)
    assert "기록하지 않습니다" in capsys.readouterr().out and '"--record"' in inspect.getsource(app)


# ---------------------------------------------------------------------- 19: an old stored company record is said, and past a limit not used
class _Src:
    def yahoo_info(self, ticker):
        raise OSError("no network")


def test_a_stored_company_record_that_stood_in_is_said_and_a_very_old_one_gives_no_share_count(tmp_path):
    info = {"sharesOutstanding": 10.0, "currentPrice": 100.0, "marketCap": 1000.0}
    clock = {"now": 1_800_000_000.0}
    q = QSF.__new__(QSF)
    q.cache, q.src = FileCache(tmp_path, clock=lambda: clock["now"]), _Src()
    q.cache.write("info:XYZ", info)
    assert q._us_info("XYZ", 100.0) == (info, False) and q._info_stale["XYZ"] == []                 # within its keep time: nothing to say
    clock["now"] += 20 * 86400
    got, unknown = q._us_info("XYZ", 100.0)
    assert got == info and unknown is False and q._info_stale["XYZ"][0]["what"].startswith("야후 종목 정보") and q._info_stale["XYZ"][0]["age_days"] == pytest.approx(20, abs=0.1)
    clock["now"] += 40 * 86400
    got, unknown = q._us_info("XYZ", 100.0)
    assert got == info and unknown is True and q._info_stale["XYZ"][0]["age_days"] > qsf_service.INFO_MAX_STALE_DAYS          # the count is not used: unknown, never 400 days old


# ---------------------------------------------------------------------- 14, 21, 25: what the screens say
def test_each_order_row_says_its_band_and_carries_the_merger_mark():
    orders = [{"ticker": "AAA", "score": 82.0}, {"ticker": "BBB", "score": 61.5}, {"ticker": "CCC", "score": 70.0}]
    got = order_plan.annotate(orders, {"BBB": {"form": "DEFM14A", "date": "2026-10-01", "label": "합병 주주총회 위임장"}})
    assert [o["band_label"] for o in orders] == ["강력 매수 후보", "보유·관찰", "매수 후보"] and orders[1]["deal"]["form"] == "DEFM14A" and "deal" not in orders[0]
    assert got["under_buy_band"] == 1 and "1종목은 점수 구간이 매수 후보" in got["note"] and order_plan.annotate([{"ticker": "AAA", "score": 90.0}])["note"] is None


def test_a_card_says_when_its_band_and_its_entry_status_point_different_ways():
    card = {"actionability": "ACTIONABLE", "score": 74.0, "band": "BUY_CANDIDATE", "band_label": "매수 후보", "entry_status": "WAIT_FOR_PULLBACK", "entry": {"reason": "손익비가 낮습니다."}}
    assert "계획에 나오지 않습니다" in qsf_service._surface_note(card)
    assert "계획에 나올 수 있습니다" in qsf_service._surface_note({**card, "score": 60.0, "band": "HOLD_WATCH", "band_label": "보유·관찰", "entry_status": "ENTRY_NOW"})
    assert qsf_service._surface_note({**card, "entry_status": "ENTRY_NOW"}) is None and qsf_service._surface_note({**card, "actionability": "BLOCKED"}) is None
    cards = {"LONG_TERM": {"actionability": "ACTIONABLE", "score": 74.0, "band": "BUY_CANDIDATE", "band_label": "매수 후보"}}
    assert "서로 다른 답" in qsf_service.committee_note(cards, {"committee": {"decision": "AVOID", "decision_ko": "회피"}})
    assert qsf_service.committee_note(cards, {"committee": {"decision": "BUY", "decision_ko": "매수 조건 충족"}}) is None and qsf_service.committee_note(cards, None) is None


# ---------------------------------------------------------------------- 23, 24: wording
def test_the_no_equity_mark_is_not_shown_or_ranked_as_a_ratio():
    rows = [{"ticker": f"T{k}", "ratios": {"debt_equity": v}} for k, v in enumerate([0.2, 0.4, 0.6, 0.8, 1.0, 99.0, 99.0])]
    peers = {"status": "REAL", "peers": rows}
    mine = " ".join(assistant.sector_lines(peers, "T5"))
    assert "계산되지 않습니다" in mine and "99.00" not in mine and "0.60배" in mine                      # the median of the five real ratios
    other = " ".join(assistant.sector_lines(peers, "T0"))
    assert "5종목 중" in other and "99" not in other and assistant._de(99.0).startswith("계산 안 됨") and assistant._de(0.5) == "0.50배"


def test_the_assistant_says_the_risk_grade_told_volatility_and_not_returns():
    src = inspect.getsource(assistant)
    assert "위험 등급이 나쁜 종목은 이후 변동성과 손실 크기가 더 컸습니다(수익을 맞힌 것은 아닙니다)" in src and "위험 등급이 나쁜 종목은 이후 수익이 부진" not in src


# ---------------------------------------------------------------------- decisions of 2026-11-22 on the committee (roadmap 4 and 7)
def _views(recs):
    """The five opinions of the sound base stock, with the recommendations set by hand: the committee's rule is what is tested."""
    f = cc.figures()
    out = []
    for o, rec in zip(iv.evaluate(f), recs):
        out.append({**o, "recommendation": rec, "recommendation_ko": iv.REC_KO[rec], "score": 90.0 if rec == iv.STRONG_BUY else 30.0 if rec == iv.AVOID else 55.0, "confidence": 90})
    return f, out


def test_one_strong_view_does_not_carry_the_committee_against_three_that_say_avoid():
    f, ops = _views([iv.STRONG_BUY, iv.AVOID, iv.AVOID, iv.AVOID, iv.HOLD])
    d = council.decide(f, ops)
    assert d["decision"] == iv.AVOID and "이기지는 못합니다" in d["reasons"][0]                       # was CONDITIONAL_BUY: 17 of 66 US buy-side decisions on 2026-11-20
    f, ops = _views([iv.STRONG_BUY, iv.AVOID, iv.AVOID, iv.HOLD, iv.HOLD])
    assert council.decide(f, ops)["decision"] == council.CONDITIONAL_BUY                           # one or two views can still carry it against two
    f, ops = _views([iv.STRONG_BUY, iv.AVOID, iv.AVOID, iv.AVOID, iv.AVOID])
    assert council.decide(f, ops, held=True)["decision"] in (iv.REDUCE, iv.SELL)


def test_the_paper_record_books_a_crash_and_carries_a_vanished_holding_at_its_last_close():
    days = [f"2026-12-{d:02d}" for d in range(1, 8)]
    lines = [{"session": d, "portfolios": {"X": {"cash": 0.5, "holdings": {"AAA": 0.5}}}} for d in days]
    crash = {days[0]: 100.0, days[1]: 100.0, days[2]: 45.0, days[3]: 45.0, days[4]: 45.0, days[5]: 45.0, days[6]: 45.0}
    x = record.performance(lines, lambda t, s: crash[s], lambda s: None, 0.0)["portfolios"]["X"]
    assert x["total_return"] == pytest.approx(-0.275, abs=1e-6) and x["price_breaks"] == [{"ticker": "AAA", "session": days[2], "move": -0.55, "booked": True}]          # was 0.0
    spike = {**crash, days[2]: 300.0, days[3]: 300.0, days[4]: 300.0, days[5]: 300.0, days[6]: 300.0}
    up = record.performance(lines, lambda t, s: spike[s], lambda s: None, 0.0)["portfolios"]["X"]
    assert up["total_return"] == 0.0 and up["price_breaks"][0]["booked"] is False                  # an unexplained rise of more than half is still not counted
    gone = {days[0]: 100.0, days[1]: 100.0, days[2]: 90.0, days[3]: None, days[4]: None, days[5]: 60.0, days[6]: 60.0}
    g = record.performance(lines, lambda t, s: gone[s], lambda s: None, 0.0)["portfolios"]["X"]
    # 100 -> 90 booked; two days carried at 90 (return 0, and said); back at 60: booked from the last close 90
    assert g["carried_at_last_close"] == {"AAA": days[3]} and g["unpriced"] == [] and g["total_return"] == pytest.approx((1 - 0.05) * (1 + 0.5 * (60 / 90 - 1)) - 1, abs=1e-5)
    never = record.performance(lines, lambda t, s: None, lambda s: None, 0.0)["portfolios"]["X"]
    assert never["unpriced"] == ["AAA"] and never["total_return"] == 0.0 and never["carried_at_last_close"] == {}
    text = (ROOT / "reports" / "IC1_PAPER_READING_PROTOCOL.md").read_text(encoding="utf-8")
    assert "## 수정 이력" in text and "50%를 넘는 하락은 손실로 반영" in text and "마지막 종가로 평가" in text and "세 관점 이상이 회피" in text


# ---------------------------------------------------------------------- decisions of 2026-11-22 on the readings (roadmap 11, 12, 13, 20)
def test_the_t_bar_of_a_reading_is_the_value_noise_of_its_own_design_reaches_as_rarely_as_the_table_says():
    from terminal.qsf import calibrate, validate
    rng = np.random.default_rng(3)
    x = calibrate.noise(rng, 20, 240, 20, 1)
    assert max(abs(calibrate.t_many(x, 20)[i] - validate.newey_west_t(list(x[i]), 20)) for i in range(20)) < 1e-9          # the repo's own t, row by row
    swing, long_ = calibrate.bar(2.24, 240, 20, 1, 20), calibrate.bar(2.24, 756, 63, 1, 63)
    assert 3.2 < swing < 3.5 and 3.2 < long_ < 3.5 and calibrate.bar(2.24, 240, 20, 1, 20) == swing                        # the audit's simulation: about 3.4; and the same every time
    assert 2.0 <= calibrate.bar(2.0, 240, 1, 1, 0) < 2.15 and calibrate.bar(2.0, 2, 20, 1, 20) == 2.0                      # independent values: the table's value nearly holds
    assert 2.15 < calibrate.plain_bar(2.0, 12) < 2.35 and calibrate.plain_bar(2.0, 2) == 2.0 and calibrate.bar(3.0, 240, 20, 1, 20) > 4.5
    assert calibrate.tail(2.24) == pytest.approx(0.01255, abs=2e-4)
    # under the bar, pure noise of that design passes about as often as the table says (a different seed from the one that set the bar)
    noise_t = calibrate.t_many(calibrate.noise(np.random.default_rng(99), 20000, 240, 20, 1), 20)
    assert 0.006 < float((noise_t >= swing).mean()) < 0.02 and float((noise_t >= 2.24).mean()) > 0.04
    base = {"ic": 0.05, "t": 2.6, "early": {"ic": 0.04, "spread_net": 0.01}, "late": {"ic": 0.06, "spread_net": 0.01}, "buy_excess": 0.01, "buy_dates": 20}
    assert validate.verdict(base)["checks"]["t"] is True and validate.verdict({**base, "t_bar": swing})["checks"]["t"] is False          # a past result reads as it did; a new one by its own bar


def _summary(**over):
    part = {"ic": 0.05, "spread_net": 0.01, "buy_minus_index": None, "top_minus_index": 0.004, "top_score_effect": 0.003}
    return {"ic": 0.05, "t": 4.0, "t_bar": 3.33, "early": dict(part), "late": dict(part), "all": dict(part), "buy_excess": None, "buy_dates": 0, **over}


def test_the_korean_swing_verdict_reads_the_top_fifth_where_no_score_reaches_seventy():
    from terminal.qsf import live_forward as lf
    s = _summary()
    by_band, by_top = lf.reading(s), lf.reading(s, top_band=True)
    assert by_band["verdict"] == "NO_EVIDENCE" and by_band["condition_a"]["buy_band"] is False and by_band["band"] == "SCORE_70"          # could never pass: no stock at 70
    assert by_top["verdict"] == "WEAK_POSITIVE_EVIDENCE" and by_top["band"] == "TOP_FIFTH" and by_top["t_bar"] == 3.33
    assert lf.reading(_summary(t=3.0), top_band=True)["verdict"] == "NO_EVIDENCE"                                                          # under its own bar
    worse = _summary()
    worse["late"]["top_minus_index"] = -0.001
    assert lf.reading(worse, top_band=True)["verdict"] == "RANK_ONLY" and lf.TOP_BAND == (("KR", "SWING"),)


def test_a_kosdaq_stock_is_compared_with_the_kosdaq_index():
    from terminal.qsf import ledger, live_forward as lf
    days = [f"2026-12-{d:02d}" for d in range(1, 29)]
    flat = [{"date": d, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "adj_close": 100.0, "volume": 1} for d in days]
    rising = [{**b, "open": 100.0 * 1.01 ** n, "close": 100.0 * 1.01 ** (n + 1), "adj_close": 100.0 * 1.01 ** (n + 1)} for n, b in enumerate(flat)]
    px = lf.Prices(lambda t: rising, flat, {"^KS11": flat, "^KQ11": rising})
    kospi = px.outcome({"ticker": "A", "benchmark": "^KS11", "entry_session": days[1]}, days[0], 5, 0.0)
    kosdaq = px.outcome({"ticker": "A", "benchmark": "^KQ11", "entry_session": days[1]}, days[0], 5, 0.0)
    assert kospi["relative_net"] > 0.04 and abs(kosdaq["relative_net"]) < 1e-9 and kosdaq["net"] == kospi["net"]          # the same stock: ahead of a flat KOSPI, level with its own index
    assert lf.Prices(lambda t: rising, flat).outcome({"ticker": "A", "benchmark": "^KQ11", "entry_session": days[1]}, days[0], 5, 0.0)["relative_net"] > 0.04          # no table: as before
    snaps = [{"market": "KR", "ticker": f"T{k}", "strategy": "SWING", "score": 75.0, "actionability": "ACTIONABLE", "data_date": days[0], "entry_session": days[1], "benchmark": "^KQ11"} for k in range(3)]
    old = ledger.validate(snaps, "KR", "SWING", lambda t: rising, flat)["horizons"]["5"]["buckets"]["70-80"]["mean_relative_net"]
    new = ledger.validate(snaps, "KR", "SWING", lambda t: rising, flat, benches={"^KS11": flat, "^KQ11": rising})["horizons"]["5"]["buckets"]["70-80"]["mean_relative_net"]
    assert old > 0.03 and abs(new + 2 * 0.0) < 0.02 and new < old


def test_the_four_live_verdicts_are_the_main_readings_and_the_rest_say_they_are_reference():
    from terminal.qsf import readings as rd
    by = {e["key"]: e for e in rd.REGISTRY}
    assert sorted(k for k, e in by.items() if e["primary"]) == ["live_long_kr", "live_long_us", "live_swing_kr", "live_swing_us"]
    main, side = rd.text(by["live_swing_us"], {"verdict": "NO_EVIDENCE"}), rd.text(by["fund_period_us"], {"verdict": "NOT_DISTINGUISHED"})
    assert main.startswith("[주된 판정 · ") and rd.REFERENCE_NOTE not in main and side.startswith("[참고 판정 · ") and rd.REFERENCE_NOTE in side


def test_every_protocol_whose_reading_has_not_run_carries_the_amendment():
    names = ("QSF_LIVE_FORWARD", "QSF_KR_AVOID_MARKS", "QSF_SCORE_SPLIT", "QSF_FUND_PERIOD", "QSF_US_CHALLENGER", "QSF_KR_CHALLENGER", "QSF_KR_FORWARD", "QSF_KR_EVENTS_FORWARD",
             "QSF_KR_CAP_UNIVERSE", "QSF_KR_TRADED_UNIVERSE", "QSF_KR_SWING_CHALLENGER", "QSF_KR_SWING_PRIOR", "QSF_KR_METHOD", "QSF_RANK_RULES", "QSF_TURNOVER_RULES")
    for name in names:
        text = (ROOT / "reports" / f"{name}_PROTOCOL.md").read_text(encoding="utf-8")
        assert "## 수정 이력: 2026-11-22, t 기준의 보정 (읽기 전)" in text and "terminal/qsf/calibrate.py" in text, name
    live = (ROOT / "reports" / "QSF_LIVE_FORWARD_PROTOCOL.md").read_text(encoding="utf-8")
    assert "상위 20%" in live and "코스닥 종목은 코스닥" in live and "주된 판정" in live
    turn = (ROOT / "reports" / "QSF_TURNOVER_RULES_PROTOCOL.md").read_text(encoding="utf-8")
    assert "스스로 규칙을 적용하지 않는다" in turn and "QSF_TURNOVER_RULES=on" in turn
