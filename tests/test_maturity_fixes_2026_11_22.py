"""Fixes after the maturity assessment of 2026-11-22 (reports/maturity_assessment_2026_11_22) and the user's eight decisions."""
from terminal.qsf import config, engine, holding, ledger as lg
from terminal.qsf import service as qsf_service
from tests.test_qsf import GOOD_FUND, bars, ctx

NO_VALUATION = {k: v for k, v in GOOD_FUND.items() if k not in ("pe", "pb", "fcf_yield")}
WEAK = {**NO_VALUATION, "roe": 0.08, "op_margin": 0.06, "gross_margin": 0.3, "rev_growth": 0.02, "eps_growth": 0.02, "rev_cagr3": 0.02, "eps_cagr3": 0.02}


# ---------------------------------------------------------------------- QSF-1.5.1: a missing factor does not give a buy label
def test_a_buy_label_reached_only_through_a_missing_factor_is_not_given():
    full = engine.score(ctx(), "LONG_TERM")
    assert full["conservative_score"] == full["score"] and not full["band_held_back"]                # nothing missing: nothing changes
    r = engine.score(ctx(fund=WEAK), "LONG_TERM")
    assert [f["factor"] for f in r["factors"] if f["status"] == "MISSING" and f.get("scored") is not False] == ["valuation"]
    assert r["score"] >= 70 > r["conservative_score"]                                                # the score itself is the one of QSF-1.5.0
    assert r["band"] == "HOLD_WATCH" and r["band_held_back"] and r["action"] == "WATCH" and "중간값으로 보면" in r["band_label"]
    assert r["actionability"] == "ACTIONABLE"                                                        # the label only: not a gate


def test_the_conservative_reading_puts_the_missing_weight_at_the_middle():
    r = engine.score(ctx(fund=WEAK), "LONG_TERM")
    miss = sum(f["weight"] for f in r["factors"] if f["status"] == "MISSING" and f.get("scored") is not False)
    have = sum(f["weight"] for f in r["factors"] if f["status"] != "MISSING" and f.get("scored") is not False and f.get("contribution") is not None)
    got = sum(f["contribution"] for f in r["factors"] if f.get("scored") is not False and f.get("contribution") is not None)
    assert abs(r["conservative_score"] - 100 * (got + config.MISSING_NEUTRAL * miss) / (have + miss)) < 1e-6 and config.MISSING_NEUTRAL == 0.5


def test_a_strong_label_steps_down_and_a_recorded_band_still_buffers():
    strong = engine.score(ctx(fund={**NO_VALUATION, "roe": 0.12, "op_margin": 0.1, "rev_growth": 0.05, "eps_growth": 0.05}), "LONG_TERM")
    assert strong["score"] >= 80 > strong["conservative_score"] >= 70 and strong["band"] == "BUY_CANDIDATE" and strong["band_held_back"] and strong["action"] == "BUY"
    kept = engine.score({**ctx(fund=WEAK), "prev_band": "BUY_CANDIDATE"}, "LONG_TERM")              # recorded in the band: the buffer reads the conservative score
    assert config.BUY_BAND_EXIT <= kept["conservative_score"] < 70 and kept["band"] == "BUY_CANDIDATE" and kept["band_kept"] and not kept["band_held_back"]


def test_the_card_says_which_factors_made_the_difference():
    card = {"actionability": "ACTIONABLE", "score": 73.3, "band_label": "보유·관찰 · 빠진 요인을 중간값으로 보면 69.5점", "band_held_back": True, "missing": ["밸류에이션"],
            "top_positive": [], "top_negative": [], "action": "WATCH", "holding": {}, "entry": {"reason": ""}}
    assert "자료가 없는 요인(밸류에이션)" in qsf_service._why(card) and "자료가 없는 요인" not in qsf_service._why({**card, "band_held_back": False})


# ---------------------------------------------------------------------- the long entry rule's hole
def test_a_poor_valuation_stops_long_entry_whatever_the_quality():
    poor = {**GOOD_FUND, "pe": 90, "pb": 25, "fcf_yield": 0.001, "roe": 0.03, "op_margin": 0.02, "gross_margin": 0.1, "roe_years_positive": 0.3}
    c = ctx(fund=poor)
    e = holding.entry_status(engine.score(c, "LONG_TERM"), c)
    assert e["status"] == "OVERVALUED_AT_CURRENT_PRICE" and "사업 품질 점수도" in e["reason"]       # until 2026-11-22: "the valuation does not block entry"
    c = ctx(fund={**GOOD_FUND, "pe": 90, "pb": 25, "fcf_yield": 0.001})
    e = holding.entry_status(engine.score(c, "LONG_TERM"), c)
    assert e["status"] == "OVERVALUED_AT_CURRENT_PRICE" and e["reason"].startswith("사업 품질은 좋지만")
    c = ctx()
    assert holding.entry_status(engine.score(c, "LONG_TERM"), c)["status"] != "OVERVALUED_AT_CURRENT_PRICE"


# ---------------------------------------------------------------------- price history: holes and impossible rows
def test_a_hole_of_more_than_ten_weekdays_blocks_the_card():
    b = bars()
    r = engine.score(ctx(bars=b[:-80] + b[-67:]), "SWING")                                           # 13 sessions missing
    assert r["tech"]["max_gap_weekdays"] > config.MAX_HISTORY_GAP == 10
    assert any(g["code"] == "DATA_ANOMALY" and "비어 있어" in g["text"] for g in r["gates"]) and r["actionability"] == "BLOCKED"
    r = engine.score(ctx(bars=b[:-80] + b[-72:]), "SWING")                                           # 8 missing: a long holiday is not a defect
    assert r["tech"]["max_gap_weekdays"] <= 10 and not any(g["code"] == "DATA_ANOMALY" for g in r["gates"])


def test_a_row_that_cannot_be_a_price_blocks_the_card():
    b = [dict(x) for x in bars()]
    b[-30]["high"] = b[-30]["low"] * 0.9
    r = engine.score(ctx(bars=b), "SWING")
    assert r["tech"]["bad_rows"] == 1 and any(g["code"] == "DATA_ANOMALY" for g in r["gates"]) and engine.score(ctx(), "SWING")["tech"]["bad_rows"] == 0


def test_the_ledger_names_its_last_sessions(tmp_path):
    led = lg.Ledger(tmp_path)
    card = engine.score(ctx(), "SWING")
    for day in ("2026-11-02", "2026-11-03", "2026-11-04"):
        led.append(day, "US", [{**card, "ticker": "AAA", "strategy": "SWING"}])
    assert led.recent_sessions("US", "2026-11-04", 5) == ["2026-11-02", "2026-11-03"] and led.recent_sessions("US", "2026-11-05", 2) == ["2026-11-03", "2026-11-04"]
    assert led.recent_sessions("KR", "2026-11-05", 5) == []


# ---------------------------------------------------------------------- the readings (user decision "모두 고침")
def test_korean_swing_comparisons_read_the_days_top_fifth():
    import numpy as np

    from terminal.qsf import fund_period as fp, score_split as ss
    score, able, ret = np.array([10, 20, 30, 40, 50, 60, 65, 66, 67, 68.0]), np.ones(10, dtype=bool), np.linspace(-0.05, 0.04, 10)
    by_band, top = ss._band(score, able, ret, 0.001), ss._band(score, able, ret, 0.001, top=True)
    assert by_band == {"names": 0, "ret": 0.0}                                                       # no Korean swing score has reached 70: the band never differs
    assert top["names"] == 2 and abs(top["ret"] - (ret[-2:].mean() - 0.001)) < 1e-12
    assert ss._band(score[:4], able[:4], ret[:4], 0.0, top=True)["names"] == 0                       # under five stocks: no fifth to speak of
    able[-1] = False
    assert ss._band(score, able, ret, 0.0, top=True)["names"] == 2 and ss.TOP_FIFTH == (("KR", "SWING"),) and fp.TOP_FIFTH is ss.TOP_FIFTH
    s = {"days": 240, "difference": {"mean": 0.001, "t": 1.0, "t_bar": 4.8, "days_with_difference": 200}, "trailing": {"mean": 0.0, "empty_share": 0.0}, "annual": {"mean": 0.0, "empty_share": 0.0}}
    assert "상위 20%" in fp.reasons(s, "NOT_DISTINGUISHED", top=True)[0] and "점수 70 이상" in fp.reasons(s, "NOT_DISTINGUISHED")[0]


def test_the_two_market_reference_uses_the_markets_own_bar(tmp_path):
    import json

    from terminal.qsf import live_forward as lf
    for market, t in (("US", 2.4), ("KR", 2.4)):
        p = lf.report_path(tmp_path, market, "SWING")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"primary": {"t": t, "t_bar": 3.33}}), encoding="utf-8")
    got = lf._pooled(tmp_path, "SWING")
    assert got["t_bar"] == 3.33 and got["combined"] > 3.33 and got["engine_level_reference"] is True
    lf.report_path(tmp_path, "KR", "SWING").write_text(json.dumps({"primary": {"t": 2.0, "t_bar": 3.33}}), encoding="utf-8")
    assert lf._pooled(tmp_path, "SWING")["engine_level_reference"] is False                           # 3.11: over the table's 2.24, under the bar


def test_the_top_three_and_own_method_verdicts_take_their_bar_from_the_design():
    import inspect

    from terminal.qsf import calibrate, kr_method, top_picks
    assert calibrate.plain_bar(top_picks.MIN_T, 12) > top_picks.MIN_T
    assert "calibrate.plain_bar(MIN_T, len(spaced))" in inspect.getsource(top_picks) and "t >= row[\"t_bar\"]" in inspect.getsource(top_picks)
    assert "calibrate.bar(VERDICT_T" in inspect.getsource(kr_method.evaluate) if hasattr(kr_method, "evaluate") else "calibrate.bar(VERDICT_T" in inspect.getsource(kr_method)
