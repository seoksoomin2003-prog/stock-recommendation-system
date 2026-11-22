"""QSF 1.1 offline tests: weights, contributions, coverage, gates, labels, horizons, exits, Form 4 semantics,
point-in-time fundamentals, immutable ledger, no look-ahead, cohort isolation, UI colours, frozen core untouched."""
import ast
import gzip
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from terminal.qsf import config, engine, events, factors, fundamentals, holding, ledger, technicals
from terminal.qsf.service import QSF
from utils import nyse_calendar

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 4, 23, 0, tzinfo=timezone.utc)
SESSION = "2026-11-04"


def sessions(n=320, end=SESSION):
    d, out = date.fromisoformat(end), []
    while len(out) < n:
        if nyse_calendar.is_session(d):
            out.append(d.isoformat())
        d = nyse_calendar.previous_session(d)
    return sorted(out)


def bars(n=320, drift=0.001, end=SESSION, vol=2_000_000.0, base=50.0):
    out, c = [], base
    for k, d in enumerate(sessions(n, end)):
        c *= 1 + drift + (0.004 if k % 2 else -0.004)
        out.append({"date": d, "open": c * 0.999, "high": c * 1.01, "low": c * 0.99, "close": c, "adj_close": c, "volume": vol})
    return out


GOOD_FUND = {"status": "REAL", "source": "SEC", "filed": "2026-02-01", "roe": 0.25, "op_margin": 0.25, "gross_margin": 0.6, "rev_growth": 0.15, "eps_growth": 0.2, "ocf_to_ni": 1.2,
             "fcf_margin": 0.2, "debt_equity": 0.3, "current_ratio": 2.0, "interest_cover": 12, "cash_debt": 1.0, "equity_assets": 0.5, "share_change": -0.01, "pe": 18, "pb": 3, "fcf_yield": 0.05,
             "rev_cagr3": 0.12, "eps_cagr3": 0.15, "roe_years_positive": 1.0, "fcf_years_positive": 1.0, "returns_capital": True, "insider_pct": 0.05, "eps": 5.0}
REGIME_US = {"vix": {"status": "REAL", "value": 15, "percentile": 0.3, "source": "t", "date": SESSION}, "vix_term": {"status": "REAL", "value": 0.9, "source": "t", "date": SESSION},
             "hy_spread": {"status": "REAL", "value": 3, "percentile": 0.3, "n": 780, "source": "t", "date": SESSION}, "index": {"status": "REAL", "symbol": "SPY", "close": 110, "ma50": 105, "ma200": 100, "source": "t", "date": SESSION},
             "breadth": {"status": "REAL", "value": 0.6, "n": 500, "date": SESSION}}
EVENTS = {"status": "REAL", "source": "t", "as_of": SESSION, "severe": [], "negative": [], "positive": [], "governance": [], "window_days": 90, "window_long_days": 365,
          "insider": {"status": "REAL", "open_market_buy": 100.0, "open_market_sell": 0.0, "window_days": 90}}


def ctx(**over):
    b = over.pop("bars", bars())
    c = {"market": "US", "ticker": "TST", "bars": b, "bench": bars(drift=0.0003), "bench_name": "SPY", "regime": REGIME_US, "fund": GOOD_FUND, "events": EVENTS, "earnings": {"date": "2026-12-20", "sessions": 30},
         "price_fresh": True, "expected_session": SESSION}
    c.update(over)
    return c


# ---------------------------------------------------------------------- weights and arithmetic
@pytest.mark.parametrize("pid", list(config.PROFILES))
def test_every_profile_totals_100_and_every_factor_has_a_calculator(pid):
    p = config.PROFILES[pid]
    assert sum(sum(d.values()) for d in p["domains"].values()) + sum(sum(d.values()) for d in p["reference"].values()) == 100      # counted and reference points together
    assert all(f in factors.CALC for part in (p["domains"], p["reference"]) for d in part.values() for f in d)


def test_domain_weights_match_the_specification():
    def tot(pid):
        return {d: sum(v.values()) for d, v in config.PROFILES[pid]["domains"].items()}
    def ref(pid):
        return {d: sum(v.values()) for d, v in config.PROFILES[pid]["reference"].items()}
    # QSF-1.4.0: the regime domain is reference only in every profile (user decision 2026-11-16); it is shown apart as the market state
    assert tot("US_SWING_V2") == {"TECHNICAL": 40, "FUNDAMENTAL": 10, "REGIME": 0, "RISK": 20, "EVENTS": 10} and ref("US_SWING_V2") == {"REGIME": 20}
    # QSF-1.2.0: the Korean swing score keeps the technical domain's 40 points as reference only (user decision 2026-11-11)
    assert tot("KR_SWING_V3") == {"TECHNICAL": 0, "FUNDAMENTAL": 10, "REGIME": 0, "RISK": 20, "EVENTS": 10} and ref("KR_SWING_V3") == {"TECHNICAL": 40, "REGIME": 20}
    assert not {"KR_SWING_V1", "KR_SWING_V2", "US_SWING_V1", "US_LONG_TERM_V1", "KR_LONG_TERM_V1"} & set(config.PROFILES)
    assert config.PROFILES["KR_SWING_V3"]["reference"]["TECHNICAL"] == config.PROFILES["US_SWING_V2"]["domains"]["TECHNICAL"]
    assert tot("US_LONG_TERM_V2") == tot("KR_LONG_TERM_V2") == {"TECHNICAL": 10, "FUNDAMENTAL": 50, "REGIME": 0, "RISK": 20, "EVENTS": 10} and ref("US_LONG_TERM_V2") == ref("KR_LONG_TERM_V2") == {"REGIME": 10}
    assert config.PROFILES["US_SWING_V2"]["reference"]["REGIME"] == config.MARKET_STATE_WEIGHTS["US"] == {"vix_regime": 5, "vix_term": 4, "credit_spread": 4, "index_trend_breadth": 7}
    assert config.PROFILES["KR_SWING_V3"]["reference"]["REGIME"] == config.MARKET_STATE_WEIGHTS["KR"] == {"vkospi_regime": 5, "index_trend": 5, "breadth": 4, "usdkrw_regime": 3, "credit_liquidity": 3}


def test_contributions_reconcile_to_composite_and_are_deterministic():
    a = engine.score(ctx(), "SWING")
    rows = [r for r in a["factors"] if r["contribution"] is not None]
    assert a["score"] == pytest.approx(100 * sum(r["contribution"] for r in rows) / sum(r["weight"] for r in rows))
    assert all(r["contribution"] == pytest.approx(r["weight"] * r["normalized"]) for r in rows)
    assert 0 <= a["score"] <= 100 and a["score"] == engine.score(ctx(), "SWING")["score"]


def test_missing_data_is_excluded_never_zero():
    full = engine.score(ctx(), "LONG_TERM")
    gone = engine.score(ctx(events={"status": "UNAVAILABLE"}, earnings={"sessions": None}), "LONG_TERM")
    st = {r["factor"]: r for r in gone["factors"]}
    assert st["governance"]["status"] == "MISSING" and st["governance"]["contribution"] is None and st["material_events"]["contribution"] is None
    assert gone["coverage"] < full["coverage"]
    assert gone["domains"]["FUNDAMENTAL"]["score_100"] == pytest.approx(full["domains"]["FUNDAMENTAL"]["score_100"])
    assert abs(gone["score"] - full["score"]) < 6    # scoring the missing points as 0 would lower it by several more


def test_low_coverage_gives_insufficient_data_with_diagnostic_score():
    r = engine.score(ctx(fund=None, events=None), "LONG_TERM")
    assert r["actionability"] == "INSUFFICIENT_DATA" and r["action"] == "INSUFFICIENT_DATA" and r["confidence"] == "INSUFFICIENT"
    assert r["diagnostic_only"] and r["score"] is not None and "FUNDAMENTAL" in r["short_domains"]


def test_confidence_never_changes_the_score():
    stale = {**GOOD_FUND, "status": "STALE"}
    a, b = engine.score(ctx(), "SWING"), engine.score(ctx(fund=stale), "SWING")
    assert a["score"] == pytest.approx(b["score"]) and a["confidence"] == "HIGH" and b["confidence"] != "HIGH"


def test_rsi_and_macd_share_one_factor():
    assert "momentum" in config.PROFILES["US_SWING_V2"]["domains"]["TECHNICAL"]
    names = set(config.PROFILES["US_SWING_V2"]["domains"]["TECHNICAL"])
    assert not names & {"rsi", "macd"}


def test_factor_direction_stronger_uptrend_scores_higher():
    up = engine.score(ctx(), "SWING")["domains"]["TECHNICAL"]["score_100"]
    down = engine.score(ctx(bars=bars(drift=-0.002)), "SWING")["domains"]["TECHNICAL"]["score_100"]
    assert up > down


def test_ramp_clips_outliers_and_keeps_raw():
    assert factors.ramp(1e9, 0, 1) == 1.0 and factors.ramp(-1e9, 0, 1) == 0.0 and factors.ramp(None, 0, 1) is None
    assert factors.ramp(float("nan"), 0, 1) is None and factors.ramp(0.0, 2, 0) == 1.0
    r = engine.score(ctx(fund={**GOOD_FUND, "pe": 5000.0}), "LONG_TERM")
    assert next(f for f in r["factors"] if f["factor"] == "valuation")["raw"]["pe"] == 5000.0


def test_financial_company_treatment():
    bank = {**GOOD_FUND, "is_financial": True, "fcf_margin": None, "debt_equity": 9.0, "equity_assets": 0.10}
    r = engine.score(ctx(fund=bank), "LONG_TERM")
    st = {f["factor"]: f["status"] for f in r["factors"]}
    assert st["free_cash_flow"] == "NOT_APPLICABLE" and st["leverage"] == "NOT_APPLICABLE"
    assert r["coverage"] == pytest.approx(1.0)


# ---------------------------------------------------------------------- classification and gates
@pytest.mark.parametrize("score,band", [(80, "STRONG_BUY_CANDIDATE"), (79.99, "BUY_CANDIDATE"), (70, "BUY_CANDIDATE"), (69.99, "HOLD_WATCH"), (55, "HOLD_WATCH"), (54.99, "WEAK_REDUCE"), (40, "WEAK_REDUCE"), (39.99, "SELL_AVOID"), (0, "SELL_AVOID")])
def test_bands(score, band):
    assert engine.classify(score)["band"] == band


def test_held_and_new_candidates_get_different_labels():
    assert engine.action_for(30, held=True) == "SELL" and engine.action_for(30, held=False) == "AVOID"
    assert engine.action_for(50, held=True) == "REDUCE" and engine.action_for(50, held=False) == "AVOID"
    assert engine.action_for(60, held=True) == "HOLD" and engine.action_for(60, held=False) == "WATCH"
    assert engine.action_for(75, held=False) == "BUY" and engine.action_for(75, held=True) == "HOLD"


def test_gate_overrides_buy_but_keeps_score():
    r = engine.score(ctx(price_fresh=False), "SWING")
    assert r["score"] is not None and r["actionability"] == "BLOCKED" and r["action"] != "BUY"
    assert any(g["code"] == "STALE_PRICE" for g in r["gates"])


@pytest.mark.parametrize("over,code", [
    ({"bars": bars(vol=100.0)}, "LOW_LIQUIDITY"), ({"bars": bars(n=120)}, "SHORT_HISTORY"), ({"identity_ok": False}, "INVALID_IDENTITY"),
    ({"events": {**EVENTS, "severe": [{"label": "파산", "date": SESSION}]}}, "SEVERE_EVENT"), ({"fund": {**GOOD_FUND, "basis_conflict": True}}, "INVALID_ACCOUNTING"),
    ({"earnings": {"date": "2026-11-05", "sessions": 1}}, "EARNINGS_IMMINENT"), ({"bars": bars(base=1.0)}, "LOW_PRICE")])
def test_hard_gates(over, code):
    assert code in [g["code"] for g in engine.score(ctx(**over), "SWING")["gates"]]


def test_zero_volume_and_anomaly_gates():
    b = bars()
    b[-1] = {**b[-1], "volume": 0.0}
    assert "NO_TRADING" in [g["code"] for g in engine.score(ctx(bars=b), "SWING")["gates"]]
    b = bars()
    b[-1] = {**b[-1], "close": b[-2]["close"] * 2, "adj_close": b[-2]["close"] * 2}
    assert "DATA_ANOMALY" in [g["code"] for g in engine.score(ctx(bars=b), "SWING")["gates"]]


def test_earnings_gate_does_not_block_long_term():
    r = engine.score(ctx(earnings={"date": "2026-11-05", "sessions": 1}), "LONG_TERM")
    assert "EARNINGS_IMMINENT" not in [g["code"] for g in r["gates"]]


def test_semantic_colours():
    assert engine._color("BUY", 75) == "#16A34A" and engine._color("SELL", 20) == "#DC2626" and engine._color("HOLD", 60) == "#64748B"
    assert engine._color("REDUCE", 50) == "#D97706" and engine._color("AVOID", 50) == "#D97706" and engine._color("AVOID", 30) == "#DC2626"


def test_ui_has_text_labels_and_separate_confidence():
    js = (ROOT / "terminal/static/qsf.js").read_text(encoding="utf-8")
    css = (ROOT / "terminal/static/style.css").read_text(encoding="utf-8")
    assert "esc(c.action_label)" in js and "신뢰도" in js and "데이터 반영률" in js
    for colour in ("#16A34A", "#DC2626", "#64748B", "#D97706"):
        assert colour in css


# ---------------------------------------------------------------------- holding and entry
def run(strategy="SWING", **over):
    c = ctx(**over)
    r = engine.score(c, strategy)
    return r, c


def test_swing_horizon_stays_in_policy_with_review_dates():
    r, c = run()
    p = holding.swing_plan(r, c, date(2026, 11, 5))
    assert 5 <= p["expected_sessions"] <= 20 and p["why"]
    assert p["first_review"] == holding.add_sessions(date(2026, 11, 5), 5, holding.next_session_us).isoformat()
    assert p["time_stop_review"] == holding.add_sessions(date(2026, 11, 5), 30, holding.next_session_us).isoformat()
    assert "자동 매도하지 않" in p["time_stop_note"]


def test_review_dates_skip_market_holidays():
    d = holding.add_sessions(date(2026, 11, 25), 1, holding.next_session_us)
    assert d == date(2026, 11, 27)     # Thanksgiving 2026-11-26 is closed


def test_adaptive_horizon_shortens_for_earnings_and_volatility():
    r, c = run(earnings={"date": "2026-11-12", "sessions": 6})
    p = holding.swing_plan(r, c, date(2026, 11, 5))
    assert p["expected_sessions"] <= 5 and any("실적" in w for w in p["why"])


def test_missing_target_is_not_invented():
    r, c = run()
    r = {**r, "levels": {"status": "UNAVAILABLE", "reason": "x"}}
    p = holding.swing_plan(r, c, date(2026, 11, 5))
    assert p["target"] is None and p["stop"] is None and any("기본값" in w for w in p["why"])


def test_long_term_quarterly_review_and_no_forced_exit():
    r, c = run("LONG_TERM")
    p = holding.long_plan(r, c, date(2026, 11, 5))
    assert p["first_review"] == "2027-02-05" and p["range_months"][1] <= 36 and "매도하지 않습니다" in p["review_note"]


def test_long_term_scenarios_need_positive_eps():
    r, c = run("LONG_TERM")
    assert holding.long_plan(r, c, date(2026, 11, 5))["scenarios"]["status"] == "REAL"
    r2, c2 = run("LONG_TERM", fund={**GOOD_FUND, "eps": -1.0})
    assert holding.long_plan(r2, c2, date(2026, 11, 5))["scenarios"]["status"] == "UNAVAILABLE"


@pytest.mark.parametrize("over,want", [({"earnings": {"date": "2026-11-11", "sessions": 5}}, "WAIT_FOR_EARNINGS"), ({"price_fresh": False}, "NO_VALID_ENTRY_SETUP"), ({"fund": None, "events": None, "regime": {}, "bars": bars(n=60)}, "NO_VALID_ENTRY_SETUP")])
def test_entry_status(over, want):
    r, c = run(**over)
    assert holding.entry_status(r, c)["status"] == want


def test_long_term_overvalued_entry():
    r, c = run("LONG_TERM", fund={**GOOD_FUND, "pe": 90.0, "pb": 30.0, "fcf_yield": 0.002})
    assert holding.entry_status(r, c)["status"] == "OVERVALUED_AT_CURRENT_PRICE"


def test_kr_session_step_skips_weekend():
    assert holding.next_session_kr(date(2026, 11, 6)) == date(2026, 11, 9)


# ---------------------------------------------------------------------- exits
def test_swing_stop_breach_exit_warns_about_gap():
    r, c = run()
    e = holding.evaluate_exit(r, c, {"stop": r["price"] * 1.01, "opened": "2026-11-01"}, date(2026, 11, 5))
    assert e["action"] == "EXIT" and "불리" in e["reason"]


def test_swing_target_and_time_stop():
    r, c = run()
    assert holding.evaluate_exit(r, c, {"target": r["price"] * 0.9, "opened": "2026-11-01"}, date(2026, 11, 5))["action"] == "PARTIAL_TAKE_PROFIT"
    assert holding.evaluate_exit(r, c, {"opened": "2026-08-01"}, date(2026, 11, 5))["action"] == "TIME_STOP_REVIEW"


def test_long_term_price_drop_alone_does_not_exit_but_thesis_does():
    r, c = run("LONG_TERM", bars=bars(drift=-0.002))
    assert holding.evaluate_exit(r, c, {"opened": "2020-01-01"}, date(2026, 11, 5))["action"] not in ("EXIT", "THESIS_INVALIDATED")
    # The one price rule: a stop the user set on a long-term holding.
    e = holding.evaluate_exit(r, c, {"stop": 99999.0, "opened": "2020-01-01"}, date(2026, 11, 5))
    assert e["action"] == "EXIT" and "직접 정한 손절가" in e["reason"]
    r2, c2 = run("LONG_TERM", fund={**GOOD_FUND, "share_change": 0.2})
    assert holding.evaluate_exit(r2, c2, {"opened": "2024-01-01"}, date(2026, 11, 5))["action"] == "THESIS_INVALIDATED"


# ---------------------------------------------------------------------- events
FORM4 = """<ownershipDocument><nonDerivativeTable>
<nonDerivativeTransaction><transactionAmounts><transactionShares><value>100</value></transactionShares><transactionPricePerShare><value>10</value></transactionPricePerShare></transactionAmounts><transactionCoding><transactionCode>P</transactionCode></transactionCoding></nonDerivativeTransaction>
<nonDerivativeTransaction><transactionAmounts><transactionShares><value>50</value></transactionShares><transactionPricePerShare><value>10</value></transactionPricePerShare></transactionAmounts><transactionCoding><transactionCode>S</transactionCode></transactionCoding></nonDerivativeTransaction>
<nonDerivativeTransaction><transactionAmounts><transactionShares><value>9000</value></transactionShares><transactionPricePerShare><value>0</value></transactionPricePerShare></transactionAmounts><transactionCoding><transactionCode>A</transactionCode></transactionCoding></nonDerivativeTransaction>
<nonDerivativeTransaction><transactionAmounts><transactionShares><value>9000</value></transactionShares><transactionPricePerShare><value>10</value></transactionPricePerShare></transactionAmounts><transactionCoding><transactionCode>F</transactionCode></transactionCoding></nonDerivativeTransaction>
<nonDerivativeTransaction><transactionAmounts><transactionShares><value>9000</value></transactionShares><transactionPricePerShare><value>10</value></transactionPricePerShare></transactionAmounts><transactionCoding><transactionCode>M</transactionCode></transactionCoding></nonDerivativeTransaction>
</nonDerivativeTable></ownershipDocument>"""


def test_form4_counts_only_open_market_codes():
    assert events.parse_form4(FORM4) == {"buy": 1000.0, "sell": 500.0, "excluded": 3}
    assert events.raw_form4_doc("xslF345X05/wk-form4.xml") == "wk-form4.xml"


def test_8k_classification_respects_date_and_meaning():
    f = [{"form": "8-K", "date": "2026-10-20", "items": "2.02,9.01"}, {"form": "8-K", "date": "2026-10-21", "items": "2.06"}, {"form": "8-K", "date": "2026-09-01", "items": "1.03"},
         {"form": "NT 10-Q", "date": "2026-08-01", "items": ""}, {"form": "8-K", "date": "2026-12-01", "items": "1.03"}, {"form": "8-K", "date": "2024-01-01", "items": "3.01"}]
    e = events.classify_us(f, SESSION)
    assert [x["label"] for x in e["negative"]] == [events.NEGATIVE_8K["2.06"]] and len(e["severe"]) == 1 and e["severe"][0]["date"] == "2026-09-01"
    assert len(e["governance"]) == 1


def test_kr_disclosures_are_classified_by_korean_rules():
    rep = [{"report_nm": "주요사항보고서(유상증자결정)", "rcept_dt": "20261020"}, {"report_nm": "주요사항보고서(자기주식취득결정)", "rcept_dt": "20261001"},
           {"report_nm": "임원ㆍ주요주주특정증권등소유상황보고서", "rcept_dt": "20261010"}, {"report_nm": "횡령ㆍ배임혐의발생", "rcept_dt": "20261015"}]
    e = events.classify_kr(rep, SESSION)
    assert [x["label"] for x in e["negative"]] == ["유상증자"] and [x["label"] for x in e["positive"]] == ["자사주 취득"]
    assert len(e["severe"]) == 1 and e["insider"]["status"] == "UNAVAILABLE"


# ---------------------------------------------------------------------- fundamentals
def facts():
    def row(end, val, filed, start=None):
        r = {"end": end, "val": val, "form": "10-K", "filed": filed}
        if start:
            r["start"] = start
        return r
    return {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [row("2024-12-31", 100.0, "2025-02-01", "2024-01-01"), row("2025-12-31", 120.0, "2026-02-01", "2025-01-01"), {"end": "2025-03-31", "val": 30.0, "form": "10-Q", "filed": "2025-05-01", "start": "2025-01-01"}]}},
        "NetIncomeLoss": {"units": {"USD": [row("2024-12-31", 10.0, "2025-02-01", "2024-01-01"), row("2025-12-31", 12.0, "2026-02-01", "2025-01-01"), row("2025-12-31", 15.0, "2026-06-01", "2025-01-01")]}},
        "StockholdersEquity": {"units": {"USD": [row("2024-12-31", 50.0, "2025-02-01"), row("2025-12-31", 60.0, "2026-02-01")]}},
    }}}


def test_us_fundamentals_ignore_quarterly_rows_and_are_point_in_time():
    a = fundamentals.extract_us(facts())
    assert len(a["revenue"]) == 2
    before = fundamentals.metrics(a, 10.0, "2025-06-01")
    assert before["fiscal_end"] == "2024-12-31" and before["roe"] == pytest.approx(10 / 50)
    orig = fundamentals.metrics(a, 10.0, "2026-03-01")
    assert orig["roe"] == pytest.approx(12 / 60) and orig["rev_growth"] == pytest.approx(0.2)
    restated = fundamentals.metrics(a, 10.0, "2026-07-01")
    assert restated["roe"] == pytest.approx(15 / 60)      # a later refiling only applies from its filing date


def test_fundamentals_missing_stay_none_and_old_data_is_stale():
    a = fundamentals.extract_us(facts())
    m = fundamentals.metrics(a, 10.0, "2026-03-01")
    assert m["fcf_margin"] is None and m["debt_equity"] is None
    assert fundamentals.metrics(a, 10.0, "2028-01-01")["status"] == "STALE"
    assert fundamentals.metrics({}, 10.0, "2026-03-01")["status"] == "UNAVAILABLE"


def test_item_301_voluntary_transfer_is_not_severe_but_a_real_notice_is():
    head = "<p>Item 3.01. Notice of Delisting or Failure to Satisfy a Continued Listing Rule or Standard; Transfer of Listing.</p>"
    move = head + "<p>The Board authorized the Company to voluntarily withdraw the listing of its common stock from the NYSE and transfer the listing to Nasdaq.</p>"
    notice = head + "<p>The Company received a notice from Nasdaq that it does not comply with the minimum bid price requirement.</p>"
    assert events.is_listing_transfer(move) is True and events.is_listing_transfer(notice) is False and events.is_listing_transfer("<p>unrelated</p>") is False
    f = [{"form": "8-K", "date": "2026-10-20", "items": "3.01,9.01", "accession": "A", "doc": "x.htm"}]
    assert events.classify_us(f, SESSION, ["A"])["severe"] == []
    assert events.classify_us(f, SESSION)["severe"][0]["date"] == "2026-10-20"      # unread text stays severe
    assert events.listing_item_targets(f, SESSION) == f


def test_kr_severe_rules_for_transfers_subsidiaries_and_age():
    def rep(name, d="20261014"):
        return {"report_nm": name, "rcept_dt": d}
    assert events.classify_kr([rep("상장폐지결정 (코스닥시장 이전상장)")], SESSION)["severe"] == []
    e = events.classify_kr([rep("상장폐지승인을위한의안상정결정")], SESSION)
    assert e["severe"] == [] and e["governance"][0]["label"] == "상장폐지 안건 상정"
    e = events.classify_kr([rep("횡령ㆍ배임사실확인(자회사의 주요경영사항)")], SESSION)
    assert e["severe"] == [] and e["negative"][0]["label"] == "자회사 횡령·배임"
    assert [x["label"] for x in events.classify_kr([rep("횡령ㆍ배임혐의발생")], SESSION)["severe"]] == ["횡령·배임"]
    assert events.classify_kr([rep("횡령ㆍ배임혐의발생", "20251201")], SESSION)["severe"] == []      # older than 180 days


def test_kr_basis_never_mixed():
    def r(y, v, basis):
        return {"status": "REAL", "value": v, "period_end": f"{y}-12-31", "receipt_date": f"{y + 1}-03-20", "basis": basis}
    out = fundamentals.extract_kr({2023: {"revenue": r(2023, 50.0, "SEPARATE"), "net_income_parent": r(2023, 5.0, "SEPARATE")},
                                   2024: {"revenue": r(2024, 100.0, "CONSOLIDATED"), "net_income_parent": r(2024, 10.0, "CONSOLIDATED")}})
    m = fundamentals.metrics(out, 100.0, "2025-06-01")
    assert m["basis"] == "CONSOLIDATED" and m["basis_changed"] is True and m["basis_conflict"] is False
    assert m["rev_growth"] is None and m["net_margin"] == 0.1      # growth is not computed across the change
    assert "INVALID_ACCOUNTING" in [g["code"] for g in engine.score(ctx(fund={**GOOD_FUND, "basis_conflict": True}), "LONG_TERM")["gates"]]


def test_financial_sic():
    assert fundamentals.is_financial_sic("6021") and not fundamentals.is_financial_sic("7372") and not fundamentals.is_financial_sic("6798") and not fundamentals.is_financial_sic(None)


# ---------------------------------------------------------------------- no look-ahead
def test_indicators_ignore_future_bars():
    b = bars()
    a = technicals.compute(b[:-10])
    shocked = b[:-10] + [{**x, "close": x["close"] * 3, "adj_close": x["close"] * 3} for x in b[-10:]]
    assert a == technicals.compute(shocked[:-10])


def test_costs_lower_reward_risk_and_kr_tax_is_included():
    t = technicals.compute(bars())
    us, kr = technicals.levels(t, "US"), technicals.levels(t, "KR")
    assert kr["reward_risk"] < us["reward_risk"] and config.COSTS["KR"]["sell_tax_bps"] == 20.0
    assert config.round_trip_cost("KR") == pytest.approx((2 * 16.5 + 20) / 1e4)


def test_costs_are_the_brokers_published_fees_and_the_assumed_part_is_kept_apart():
    """QSF-1.3.2: Toss Securities' schedule (read 2026-11-12).  Spread and slippage stay labelled assumptions; currency exchange stays out."""
    us, kr = config.COSTS["US"], config.COSTS["KR"]
    assert us["commission_bps"] == 10.0 and us["sell_fee_bps"] == pytest.approx(0.206) and us["sell_tax_bps"] == 0.0
    assert kr["commission_bps"] == 1.5 and kr["sell_tax_bps"] == 20.0 and kr["sell_fee_bps"] == 0.0
    assert config.round_trip_cost("US") == pytest.approx((2 * (10 + 10) + 0.206) / 1e4) and config.fees_only("US") == pytest.approx(20.206 / 1e4)
    assert config.fees_only("KR") == pytest.approx(23 / 1e4) and config.round_trip_cost("KR") - config.fees_only("KR") == pytest.approx(30 / 1e4)
    assert all("가정" in c["basis"] and "토스증권" in c["basis"] for c in (us, kr)) and "환전" in us["basis"]
    assert config.FX_BPS == {"regular": 5.0, "off_hours": 50.0} and config.MODEL_VERSION == "QSF-1.5.0"


# ---------------------------------------------------------------------- ledger
def card(ticker="AAA", strategy="SWING", score_ctx=None, market="US"):
    c = engine.score(score_ctx or ctx(), strategy)
    return {**c, "ticker": ticker, "benchmark": "SPY", "entry_status": "ENTRY_NOW", "entry_session": "2026-11-05", "holding": {"x": 1}, "recorded_at": NOW.isoformat(), "provenance": {"price_date": SESSION}, "market": market}


def test_ledger_is_immutable_deduplicated_and_verifiable(tmp_path):
    lg = ledger.Ledger(tmp_path)
    assert lg.append(SESSION, "US", [card()])["recorded"] == 1
    first = lg.snapshots()[0]["score"]
    assert lg.append(SESSION, "US", [card(score_ctx=ctx(fund=None))])["recorded"] == 0     # the original is kept
    assert lg.snapshots()[0]["score"] == first and lg.verify()["status"] == "OK"
    assert lg.append("2026-11-05", "US", [card()])["recorded"] == 1
    assert len(lg.snapshots()) == 2
    shard = next(lg.dir.glob("*.gz"))
    shard.write_bytes(gzip.compress(b"{}\n"))
    assert lg.verify()["status"] == "BROKEN"


def test_ledger_detects_index_edit_and_refuses_to_append(tmp_path):
    lg = ledger.Ledger(tmp_path)
    lg.append(SESSION, "US", [card()])
    lg.index.write_text(lg.index.read_text().replace('"records": 1', '"records": 2'))
    assert lg.read_index()["status"] == "BROKEN"
    with pytest.raises(RuntimeError):
        lg.append("2026-11-05", "US", [card()])


def test_snapshot_holds_required_fields(tmp_path):
    s = ledger.snapshot(card())
    for k in ("market", "ticker", "strategy", "model_version", "spec_version", "score", "domains", "factors", "coverage", "confidence", "action", "entry_status", "holding", "target", "stop", "gates", "benchmark", "recorded_at", "provenance"):
        assert k in s
    assert {"raw", "normalized", "contribution", "source", "as_of", "status"} <= set(s["factors"][0])


def test_stability_separates_new_information_from_data_changes(tmp_path):
    prev = ledger.snapshot(card())
    cur = ledger.snapshot(card(score_ctx=ctx(bars=bars(drift=-0.002))))
    st = ledger.stability(prev, cur)
    assert st["cause"] == "NEW_INFORMATION" and st["delta"] < 0
    cur2 = ledger.snapshot(card(score_ctx=ctx(fund=None)))
    assert ledger.stability(prev, cur2)["cause"] == "DATA_QUALITY_OR_PROVIDER"
    assert ledger.stability(None, cur)["status"] == "NO_PREVIOUS"
    assert ledger.stability({**prev, "model_version": "OLD"}, cur)["cause"] == "MODEL_CHANGE"


def test_outcome_enters_next_open_nets_costs_and_never_peeks():
    b = bars(40, drift=0.01)
    sig = b[10]["date"]
    o = ledger.outcome(b, b, sig, 5, 0.01)
    assert o["entry_date"] == b[11]["date"] and o["exit_date"] == b[15]["date"]
    assert o["gross"] == pytest.approx(b[15]["close"] / b[11]["open"] - 1) and o["net"] == pytest.approx(o["gross"] - 0.01)
    assert o["relative_net"] == pytest.approx(-0.01)
    assert ledger.outcome(b, b, b[-3]["date"], 5, 0.01) is None      # not matured
    broken = [dict(x) for x in b]
    broken[15]["adj_close"] = None
    assert ledger.outcome(broken, b, sig, 5, 0.01) is None           # missing stays missing


def test_snapshot_enters_only_on_its_recorded_entry_session():
    b = bars(40, drift=0.01)
    o = ledger.outcome(b, b, b[10]["date"], 5, 0.0, entry_session=b[13]["date"])
    assert o["entry_date"] == b[13]["date"] and o["exit_date"] == b[17]["date"]


def test_voided_shard_stays_on_disk_but_is_not_read(tmp_path):
    lg = ledger.Ledger(tmp_path)
    name = lg.append(SESSION, "US", [card()])["file"]
    lg.void_shard(name, "stale calendar")
    v = lg.verify()
    assert lg.snapshots() == [] and (lg.dir / name).exists() and v["status"] == "OK" and v["shards"] == 1 and v["voided"] == 1
    assert lg.append(SESSION, "US", [card()])["recorded"] == 1 and len(lg.snapshots()) == 1
    assert lg.append("2026-11-05", "US", [card()])["recorded"] == 1 and lg.verify()["status"] == "OK"


def test_validate_keeps_cohorts_separate_and_withholds_verdict(tmp_path):
    b = bars(60)
    us = {**ledger.snapshot(card()), "data_date": b[10]["date"], "entry_session": b[11]["date"], "score": 75.0}
    other = {**us, "market": "KR", "ticker": "005930"}
    long_t = {**us, "strategy": "LONG_TERM"}
    rep = ledger.validate([us, other, long_t], "US", "SWING", lambda t: b, b)
    assert rep["snapshots"] == 1
    row = rep["horizons"]["5"]
    assert row["buckets"]["70-80"]["n"] == 1 and row["independent_samples"] < 12 and "보류" in row["verdict"]


def test_validate_says_which_model_versions_it_mixes():
    b = bars(60)
    one = {**ledger.snapshot(card()), "data_date": b[10]["date"], "entry_session": b[11]["date"], "score": 75.0, "model_version": "QSF-1.1.1"}
    two = {**one, "ticker": "MSFT", "model_version": "QSF-1.1.7"}
    three = {**one, "ticker": "NVDA", "model_version": "QSF-1.1.7"}
    gone = {**one, "ticker": "X", "strategy": "LONG_TERM", "model_version": "QSF-0.9"}
    assert ledger.validate([one, two, three, gone], "US", "SWING", lambda t: b, b)["model_versions"] == {"QSF-1.1.1": 1, "QSF-1.1.7": 2}


def test_correlation_diagnostics_need_enough_history():
    s = ledger.snapshot(card())
    assert ledger.factor_correlations([s])["status"] == "INSUFFICIENT"


# ---------------------------------------------------------------------- service, isolation
class FakeSrc:
    SEC_ARCHIVE = "https://x/{cik}/{acc}/{doc}"
    calls = []

    def yahoo_history(self, symbols, period="2y"):
        self.calls.append(tuple(symbols))
        extra = {"^VIX": bars(drift=0.0, base=15.0), "^VIX3M": bars(drift=0.0, base=17.0), "SPY": bars(drift=0.0005), "^KS11": bars(drift=0.0005), "^KQ11": bars(), "KRW=X": bars(drift=0.0)}
        return {s: extra.get(s, bars()) for s in symbols}

    def fred_series(self, sid, start):
        return [[d, 3.0] for d in sessions(400)]

    def sec_cik(self, t):
        return "0000000001"

    def sec_companyfacts(self, cik):
        return facts()

    def sec_submissions(self, cik):
        return {"name": "Test Co", "sic": "7372", "filings": {"recent": {"form": ["4", "8-K"], "filingDate": ["2026-10-01", "2026-10-02"], "items": ["", "2.02"], "accessionNumber": ["1-1", "1-2"], "primaryDocument": ["xsl/f.xml", "d.htm"]}}}

    def sec_text(self, url):
        return FORM4

    def yahoo_info(self, t):
        return {"longName": "Test Co", "sharesOutstanding": 10.0}

    def yahoo_earnings_dates(self, t):
        return ["2026-12-15"]


class FakeLab:
    def panel(self):
        return None

    def universe(self):
        return {"tickers": [f"T{k}" for k in range(25)]}


class FakeTerm:
    lab = FakeLab()

    def _latest_scan(self):
        return {"run_id": "r1", "recommendations": [{"ticker": "TOP", "recommendation_rank": 1, "alpha": 9.9}]}

    def _book(self, market="US"):
        return [], {"status": "OK"}, {"positions": {"HELD": {"avg": 10.0, "opened": "2026-10-01", "qty": 1.0}}, "plans": {"HELD": {"stop": 1.0, "target": 1000.0}}}

    def watchlist(self):
        return ["T0", "^VIX"]


def service(tmp_path, **kw):
    return QSF(tmp_path, src=FakeSrc(), now=lambda: NOW, terminal=FakeTerm(), **kw)


def test_evaluate_end_to_end_with_p6_kept_separate(tmp_path):
    d = service(tmp_path).evaluate("TOP")
    assert d["status"] == "REAL" and set(d["cards"]) == {"SWING", "LONG_TERM"}
    c = d["cards"]["SWING"]
    assert c["profile"] == "US_SWING_V2" and c["price"] > 0 and c["holding"]["entry_date"] == "2026-11-05" and c["why_summary"]
    assert d["p6_reference"]["in_top5"] and d["p6_reference"]["rank"] == 1
    assert "alpha" not in json.dumps([f["factor"] for f in c["factors"]])
    assert c["data_date"] == SESSION and "STALE_PRICE" not in [g["code"] for g in c["gates"]]


def test_held_position_gets_exit_block(tmp_path):
    c = service(tmp_path).evaluate("HELD")["cards"]["SWING"]
    assert c["held"] and c["exit"]["action"] and c["action"] in ("HOLD", "REDUCE", "SELL")


def test_intraday_bar_after_session_is_dropped(tmp_path):
    class Src(FakeSrc):
        def yahoo_history(self, symbols, period="2y"):
            out = super().yahoo_history(symbols, period)
            return {s: v + [{**v[-1], "date": "2026-11-05", "close": 9999.0, "adj_close": 9999.0}] for s, v in out.items()}
    c = QSF(tmp_path, src=Src(), now=lambda: NOW, terminal=FakeTerm()).evaluate("AAA")["cards"]["SWING"]
    assert c["data_date"] == SESSION and c["price"] < 9999


def test_scan_records_and_refuses_partial_data(tmp_path):
    q = service(tmp_path)
    res = q.scan("US", tickers=[f"T{k}" for k in range(25)])
    assert res["status"] == "REAL" and res["scored"] == 50 and res["ledger"]["recorded"] == 50 and q.latest("US")["session"] == SESSION
    assert q.ledger.verify()["status"] == "OK"

    class Late(FakeSrc):
        def yahoo_history(self, symbols, period="2y"):
            return {s: bars(end="2026-11-03") for s in symbols}
    q2 = QSF(tmp_path / "b", src=Late(), now=lambda: NOW, terminal=FakeTerm())
    r2 = q2.scan("US", tickers=[f"T{k}" for k in range(25)])
    assert r2["status"] == "DATA_NOT_READY" and not q2.ledger.read_index()["rows"]
    assert r2["reason"] == "NOT_PUBLISHED" and r2["download"]["failed"] == 0 and r2["last_dates"] == {"2026-11-03": 25}


def test_a_cut_download_is_not_called_unpublished(tmp_path):
    class Cut(FakeSrc):
        def yahoo_history(self, symbols, period="2y"):
            if "SPY" in symbols or len(symbols) > 3:          # the scan's price chunks; context series still answer
                raise ConnectionError("asleep")
            return super().yahoo_history(symbols, period)
    q = QSF(tmp_path, src=Cut(), now=lambda: NOW, terminal=FakeTerm())
    r = q.scan("US", tickers=[f"T{k}" for k in range(25)])
    assert r["status"] == "DATA_NOT_READY" and r["reason"] == "DOWNLOAD_FAILED" and not q.ledger.read_index()["rows"]
    assert r["download"] == {"chunks": 1, "failed": 1, "kinds": {"ConnectionError": 1}} and r["no_bars"] == 25

    class Empty(FakeSrc):
        def yahoo_history(self, symbols, period="2y"):
            return {} if len(symbols) > 3 else super().yahoo_history(symbols, period)
    r = QSF(tmp_path / "e", src=Empty(), now=lambda: NOW, terminal=FakeTerm()).scan("US", tickers=[f"T{k}" for k in range(25)])
    assert r["reason"] == "DOWNLOAD_FAILED" and r["download"]["kinds"] == {"EMPTY_REPLY": 1}


def test_kr_uses_no_us_indicators_and_missing_key_is_not_zero(tmp_path):
    import pandas as pd
    master = pd.DataFrame([{"canonical_ticker": "005930", "yahoo_symbol": "005930.KS", "company_name": "삼성전자", "market": "KOSPI", "industry_class": "NON_FINANCIAL"}])

    class NoKey:
        configured = False
    src = FakeSrc()
    FakeSrc.calls = []
    q = QSF(tmp_path, src=src, now=lambda: NOW, terminal=FakeTerm(), dart=NoKey(), kr_master=master)
    d = q.evaluate("005930", "KR")
    used = {s for call in FakeSrc.calls for s in call}
    assert not used & {"^VIX", "^VIX3M", "SPY"} and d["p6_reference"] is None
    c = d["cards"]["LONG_TERM"]
    assert c["actionability"] == "INSUFFICIENT_DATA" and c["profile"] == "KR_LONG_TERM_V2"
    regime = {f["factor"]: f for f in d["cards"]["SWING"]["factors"] if f["domain"] == "REGIME"}
    assert regime["vkospi_regime"]["status"] == "MISSING" and "VKOSPI" in regime["vkospi_regime"]["reason"]
    assert regime["credit_liquidity"]["status"] == "MISSING" and regime["index_trend"]["status"] == "REAL"
    assert q.evaluate("999999", "KR")["status"] == "UNAVAILABLE"


def test_kr_session_survives_a_gap_in_the_index_series(tmp_path):
    import pandas as pd
    master = pd.DataFrame([{"canonical_ticker": "005930", "yahoo_symbol": "005930.KS", "company_name": "삼성전자", "market": "KOSPI", "industry_class": "NON_FINANCIAL"}])

    class Gap(FakeSrc):
        def yahoo_history(self, symbols, period="2y"):
            out = super().yahoo_history(symbols, period)
            if "^KS11" in out:
                out["^KS11"] = [r for r in out["^KS11"] if r["date"] != SESSION]
            return out

    class NoKey:
        configured = False
    q = QSF(tmp_path, src=Gap(), now=lambda: datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc), terminal=FakeTerm(), dart=NoKey(), kr_master=master)
    assert q.regime("KR")["session"] == SESSION
    assert q.evaluate("005930", "KR")["cards"]["SWING"]["data_date"] == SESSION


def test_partial_price_reply_is_not_reused_and_chunks_do_not_share_a_cache_entry(tmp_path):
    calls = []

    class Flaky(FakeSrc):
        def yahoo_history(self, symbols, period="2y"):
            calls.append(list(symbols))
            full = super().yahoo_history(symbols, period)
            return {k: [r for r in v if r["date"] < SESSION] for k, v in full.items()} if len(calls) == 1 else full
    q = QSF(tmp_path, src=Flaky(), now=lambda: datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc), terminal=FakeTerm())
    assert all(r[-1]["date"] < SESSION for r in q._session_bars(["AAA"], SESSION).values())
    assert all(r[-1]["date"] == SESSION for r in q._session_bars(["AAA"], SESSION).values())
    n = len(calls)
    q._session_bars(["AAA"], SESSION)
    assert len(calls) == n
    q._session_bars(["AAA", "BBB"], SESSION)
    assert len(calls) == n + 1


def test_us_path_reads_no_korean_data(tmp_path):
    FakeSrc.calls = []
    service(tmp_path).evaluate("AAA")
    used = {s for call in FakeSrc.calls for s in call}
    assert not used & {"^KS11", "^KQ11", "KRW=X"}


def test_evaluation_never_writes_to_the_ledger(tmp_path):
    q = service(tmp_path)
    q.evaluate("AAA")
    assert not q.ledger.read_index()["rows"]


# ---------------------------------------------------------------------- separation from the frozen model
def test_qsf_imports_nothing_from_the_frozen_core():
    frozen = {"core", "alpha_engine", "pipeline"}
    for p in (ROOT / "terminal" / "qsf").glob("*.py"):
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any(m.split(".")[0] in frozen for m in mods), f"{p.name} imports {mods}"


def test_lab_row_with_partial_prices_is_not_recordable():
    import numpy as np
    from terminal.lab import panel as pm
    tick = [f"T{k}" for k in range(9)] + ["SPY"]
    data = {f: np.ones((2, 10)) for f in ("open", "close", "adj_close", "volume")}
    data["close"][1, 3:] = np.nan
    p = pm.Panel(["2026-11-03", "2026-11-04"], tick, data, {})
    assert pm.row_complete(p, 0) and not pm.row_complete(p, 1)


def test_void_session_keeps_lines_and_allows_rerecord(tmp_path):
    from terminal.lab.service import GENESIS, Lab, LabError, _hash
    lab = Lab(tmp_path, now=lambda: NOW)
    lab.dir.mkdir(parents=True)
    r = {"type": "SIGNAL", "model": "BASE_SPY", "signal_session": SESSION, "seq": 1, "prev_hash": GENESIS}
    r["hash"] = _hash(r)
    lab.ledger_file.write_text(json.dumps(r, sort_keys=True) + "\n", encoding="utf-8")
    lab.void_session(SESSION, "partial data")
    recs, integ = lab.read_ledger()
    assert recs == [] and integ["status"] == "OK" and len(lab.ledger_file.read_text().splitlines()) == 2
    with pytest.raises(LabError):
        lab.void_session("2020-01-01", "none")


def test_validation_loads_each_ticker_once_and_shortcuts_change_nothing():
    b = bars(60, drift=0.004)
    calls = []

    def loader(t):
        calls.append(t)
        return b
    snaps = [{"market": "US", "strategy": "SWING", "ticker": t, "data_date": b[n]["date"], "score": 40.0 + n, "actionability": "OK", "entry_session": b[n + 1]["date"] if n % 2 else None} for t in ("AAA", "BBB") for n in (5, 10, 20, 58)]
    out = ledger.validate(snaps, "US", "SWING", loader, b)
    assert sorted(calls) == ["AAA", "BBB"] and out["snapshots"] == 8
    days, by_date = [x["date"] for x in b], {x["date"]: x for x in b}
    for n in (0, 5, 20, 58, 59):
        for entry in (None, b[n]["date"], "1900-01-01", "2999-01-01"):
            assert ledger.outcome(b, b, b[n]["date"], 5, 0.01, entry, days, by_date) == ledger.outcome(b, b, b[n]["date"], 5, 0.01, entry)


def test_bars_out_of_order_still_get_the_plain_answer():
    b = bars(40, drift=0.004)
    mixed = b[:10] + b[12:] + b[10:12]
    snap = [{"market": "US", "strategy": "SWING", "ticker": "AAA", "data_date": b[8]["date"], "score": 75.0, "actionability": "OK"}]
    h = config.SWING_HORIZONS[0]
    want = ledger.outcome(mixed, b, b[8]["date"], h, config.round_trip_cost("US"))
    got = ledger.validate(snap, "US", "SWING", lambda t: mixed, b)["horizons"][str(h)]["buckets"][ledger.bucket_of(75.0)]
    assert want is not None and got["n"] == 1 and got["mean_net"] == pytest.approx(want["net"])


def test_score_uses_the_technicals_it_is_given(monkeypatch):
    c = ctx()
    c["tech"] = technicals.compute(c["bars"], c.get("bench"))
    want = engine.score(c, "SWING")
    monkeypatch.setattr(technicals, "compute", lambda *a, **k: pytest.fail("계산을 반복했습니다"))
    assert engine.score(c, "SWING")["score"] == want["score"]


def test_a_bar_without_a_date_does_not_take_down_the_report():
    b = bars(40, drift=0.004)
    broken = b + [{**b[-1], "date": None}, {k: v for k, v in b[-1].items() if k != "date"}]
    snap = [{"market": "US", "strategy": "SWING", "ticker": "AAA", "data_date": b[8]["date"], "score": 75.0, "actionability": "OK"}]
    h = config.SWING_HORIZONS[0]
    got = ledger.validate(snap, "US", "SWING", lambda t: broken, b)["horizons"][str(h)]["buckets"][ledger.bucket_of(75.0)]
    assert got["n"] == 1 and got["mean_net"] == pytest.approx(ledger.outcome(b, b, b[8]["date"], h, config.round_trip_cost("US"))["net"])


def test_a_stock_yahoo_left_out_is_asked_again_and_the_chunk_is_kept_only_when_whole(tmp_path):
    """2026-11-18: Yahoo dropped CSCO from one chunk at 09:23; the 90%-whole chunk was kept for the day and CSCO missed the record."""
    calls = []
    names = [f"S{i:02d}" for i in range(20)]

    class Drops(FakeSrc):
        def __init__(self, drop_times):
            super().__init__()
            self.drop_times = drop_times

        def yahoo_history(self, symbols, period="2y"):
            calls.append(list(symbols))
            out = {s: super(Drops, self).yahoo_history(["AAA"], period)["AAA"] for s in symbols}
            if self.drop_times > 0 and "S07" in out:
                self.drop_times -= 1
                del out["S07"]
            return out

    q = QSF(tmp_path, src=Drops(1), now=lambda: datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc), terminal=FakeTerm())
    got = q._session_bars(names, SESSION)
    assert calls == [names, ["S07"]] and set(got) == set(names)
    q._session_bars(names, SESSION)
    assert len(calls) == 2                                   # whole, so kept for the day

    calls.clear()
    q2 = QSF(tmp_path / "b", src=Drops(5), now=lambda: datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc), terminal=FakeTerm())
    got = q2._session_bars(names, SESSION)
    assert calls == [names, ["S07"]] and "S07" not in got and len(got) == 19
    q2._session_bars(names, SESSION)
    assert calls[2] == names                                 # still short: not kept, the next slot downloads the chunk again
