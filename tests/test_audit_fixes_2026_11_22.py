"""The fixes of the audit of 2026-11-22 that needed no decision (reports/audit_2026_11_22_master/REMEDIATION_ROADMAP.md, order 1,
2-ga, 3, 5, 6, 14, 15, 17, 19, 21, 22, 24, 25).  The score itself is unchanged by every one of them."""
import inspect
import json
from argparse import Namespace
from datetime import date

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
