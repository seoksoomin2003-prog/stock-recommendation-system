"""Five investor engines, the unified committee and six portfolios (user specification 2026-11-22, rules IC-1)."""
import json
from pathlib import Path

from terminal.committee import council, figures as fg, investors as iv, portfolios as pf, record, service
from tests import committee_cases as cc
from tests.test_terminal_1 import _loopback_only, live  # noqa: F401  (fixtures: a local server on 127.0.0.1 only)

CTX = {"sector_rs": {"산업재": 0.6, "기술": 0.6, "필수소비재": 0.5}}


def run(case=None, held=None, **over):
    f = cc.figures(**{**(case or {}), **over})
    ops = iv.evaluate(f, held, CTX)
    return f, {o["investor"]: o for o in ops}, council.decide(f, ops, bool((held or {}).get("COMMITTEE")))


def recs(by):
    return [by[k]["recommendation"] for k in iv.ORDER]


def test_every_engine_returns_the_same_shape_and_says_what_would_change_its_mind():
    f, by, _ = run()
    assert list(by) == ["BUFFETT", "MUNGER", "GRAHAM", "LYNCH", "DRUCKENMILLER"] and [by[k]["name"] for k in iv.ORDER] == ["버핏식", "멍거식", "그레이엄식", "린치식", "드러켄밀러식"]
    for o in by.values():
        assert {"investor", "philosophy", "question", "ticker", "as_of", "score", "confidence", "coverage", "recommendation", "recommendation_ko", "horizon", "valuation", "expected_return", "downside_risk",
                "positives", "negatives", "opinion", "thesis", "conditions", "suggested_weight", "action", "components", "missing", "evidence", "rules"} <= set(o)
        assert set(o["conditions"]) == {"buy", "hold", "add", "reduce", "sell", "invalidation"} and all(o["conditions"].values()) and o["rules"] == "IC-1"
        assert 0 <= o["score"] <= 100 and 0 <= o["confidence"] <= 100 and o["recommendation"] in iv.REC_KO and o["as_of"] == "2026-11-20" and o["ticker"] == "GOOD"
        assert o["expected_return"]["basis"] and o["downside_risk"]["basis"] and len(o["opinion"]) > 30
    assert recs(by) == ["STRONG_BUY", "HOLD", "WAIT", "STRONG_BUY", "STRONG_BUY"]                     # the same stock, five different conclusions
    assert "보수적 적정 PER" in by["BUFFETT"]["opinion"] and "45 아래로 떨어지면" in by["BUFFETT"]["opinion"]         # why, the evidence, and what would change it
    assert by["GRAHAM"]["margin_of_safety"] < 0 and "안전마진이 25% 이상이 되면" in by["GRAHAM"]["opinion"] and by["LYNCH"]["category"] == "STALWART"
    assert by["BUFFETT"]["suggested_weight"] > 0 and by["GRAHAM"]["suggested_weight"] == 0 and by["MUNGER"]["loss_risk"]["score"] == 0.0
    assert not any(w in " ".join(o["opinion"] for o in by.values()) for w in ("사세요", "파세요", "추천합니다"))        # rule results, never advice
    assert "실존 투자자의 실제 의견이 아닙니다" in iv.NOTE and "주문을 내지 않습니다" in iv.NOTE


def test_scenario_a_an_excellent_company_at_a_very_dear_price():
    _f, by, c = run(cc.A_EXCELLENT_BUT_DEAR)
    assert recs(by) == ["WAIT", "WAIT", "WAIT", "HOLD", "STRONG_BUY"]
    assert by["BUFFETT"]["business_ok"] and by["MUNGER"]["exceptional"] and by["BUFFETT"]["margin_of_safety"] < 0             # the business is liked, the price is not
    assert by["GRAHAM"]["margin_of_safety"] < by["BUFFETT"]["margin_of_safety"] and by["GRAHAM"]["components"]["가격과 안전마진"] == 0.0      # Graham is the strictest on price
    assert by["LYNCH"]["category"] == "FAST_GROWER" and by["LYNCH"]["peg"] > 1.3 and by["DRUCKENMILLER"]["trend_ok"]
    assert c["decision"] == council.CONDITIONAL_BUY and c["buyers"] == ["드러켄밀러식"] and "다수결이 아닙니다" in c["reasons"][0] and c["horizon"] == "전술적(몇 주~몇 달)"
    assert {d["kind"] for d in c["disagreements"]} == {"MARKET"} and c["scores"]["quality"] > 90 and c["scores"]["valuation"] < 10


def test_scenario_b_a_sound_mature_company_far_under_its_value():
    _f, by, c = run(cc.B_SOUND_AND_CHEAP)
    assert recs(by) == ["AVOID", "AVOID", "STRONG_BUY", "BUY", "HOLD"] and by["GRAHAM"]["margin_of_safety"] > 0.40 and not by["GRAHAM"]["value_trap"]
    assert by["LYNCH"]["category"] == "ASSET_PLAY" and by["BUFFETT"]["margin_of_safety"] > 0 and not by["BUFFETT"]["business_ok"]          # cheap is not enough for the owner of businesses
    assert c["decision"] == council.CONDITIONAL_BUY and c["buyers"] == ["그레이엄식", "린치식"] and {d["kind"] for d in c["disagreements"]} == {"FUNDAMENTAL", "MARKET"}


def test_scenario_c_a_small_fast_grower():
    _f, by, c = run(cc.C_FAST_SMALL)
    assert recs(by) == ["WAIT", "AVOID", "WAIT", "STRONG_BUY", "STRONG_BUY"] and by["LYNCH"]["category"] == "FAST_GROWER" and by["LYNCH"]["peg"] < 1.0
    assert "PEG" in by["LYNCH"]["opinion"] and not by["MUNGER"]["exceptional"] and by["GRAHAM"]["sound"]
    assert c["decision"] == council.CONDITIONAL_BUY and c["horizon"] == "장기 관점과 추세 관점이 함께 봄"


def test_scenario_d_druckenmiller_turns_first_when_momentum_breaks():
    _f, good, _ = run()
    _f, by, c = run(cc.D_QUALITY_LOSING_MOMENTUM)
    assert recs(by) == ["STRONG_BUY", "HOLD", "WAIT", "STRONG_BUY", "AVOID"]
    assert [by[k]["recommendation"] for k in ("BUFFETT", "MUNGER", "GRAHAM", "LYNCH")] == [good[k]["recommendation"] for k in ("BUFFETT", "MUNGER", "GRAHAM", "LYNCH")]      # the long-term views do not move on price
    assert "200일선 아래" in by["DRUCKENMILLER"]["opinion"] and by["DRUCKENMILLER"]["negatives"][0].startswith("가격이 200일선 아래")
    held = run(cc.D_QUALITY_LOSING_MOMENTUM, held={"DRUCKENMILLER": True, "BUFFETT": True})[1]
    assert held["DRUCKENMILLER"]["recommendation"] == "SELL" and held["BUFFETT"]["recommendation"] == "STRONG_BUY" and "가격이 내렸다는 이유만으로는 팔지 않습니다" in held["BUFFETT"]["conditions"]["hold"]
    assert c["decision"] == council.CONDITIONAL_BUY and any(d["kind"] == "MARKET" and d["investor"] == "드러켄밀러식" for d in c["disagreements"])


def test_scenario_e_a_cheap_company_with_too_much_debt_and_falling_cash_flow():
    _f, by, c = run(cc.E_CHEAP_LEVERED)
    assert recs(by) == ["AVOID", "AVOID", "AVOID", "AVOID", "AVOID"]
    assert by["GRAHAM"]["value_trap"] and by["GRAHAM"]["margin_of_safety"] > 0.5 and "가치 함정" in by["GRAHAM"]["opinion"] and by["GRAHAM"]["negatives"][0] == "가치 함정 가능성"
    assert by["MUNGER"]["loss_risk"]["score"] >= 50 and by["LYNCH"]["story_broken"] and "숫자로 확인되지 않습니다" in by["LYNCH"]["opinion"]
    assert c["decision"] == "AVOID" and {r["name"] for r in c["material_risks"]} >= {"과도한 부채", "이익의 질", "영구 손실 위험", "가치 함정 가능성"}
    assert any(r["level"] == council.CRITICAL for r in c["material_risks"]) and c["scores"]["confidence"] <= council.CONFIDENCE_CAP_RISK and "위험 하나가 다수 의견보다 무겁습니다" in c["reasons"][0]


def test_scenario_f_munger_separates_the_business_from_the_price():
    _f, by, c = run(cc.F_MOAT_FULL_PRICE)
    assert recs(by) == ["WAIT", "BUY", "WAIT", "HOLD", "STRONG_BUY"]
    assert by["MUNGER"]["exceptional"] and by["MUNGER"]["fair_pe"] > by["BUFFETT"]["fair_pe"] > 15 > 0 and by["BUFFETT"]["business_ok"] and by["GRAHAM"]["margin_of_safety"] < -1
    assert c["decision"] == council.CONDITIONAL_BUY and {d["kind"] for d in c["disagreements"]} == {"PHILOSOPHICAL", "FUNDAMENTAL"}


def test_missing_and_not_applicable_figures_are_said_and_never_read_as_zero():
    f, by, c = run(pe=None, pb=None, roe=None, eps_cagr3=None, rev_cagr3=None, ma200=None, rs=None, trailing_pe=None, forward_pe=None)
    assert f["pe"] is None and f["_status"]["pe"] == fg.MISSING and recs(by) == [iv.NO_DATA] * 5 and all(o["score"] is None and o["suggested_weight"] == 0 for o in by.values())
    assert c["decision"] == iv.NO_DATA and c["valid"] == 0 and "결정하지 않습니다" in c["reasons"][0]
    bank = cc.figures(sector="금융")
    assert bank["kind"] == "FINANCIAL" and bank["op_margin"] is None and bank["_status"]["current_ratio"] == fg.NOT_APPLICABLE and bank["roic"] == bank["roe"]
    plain = cc.figures()
    assert iv.buffett(bank)["confidence"] < iv.buffett(plain)["confidence"] and iv.buffett(bank)["recommendation"] != iv.NO_DATA      # fewer figures: a view, but a less sure one
    gone = cc.figures(debt_equity=99.0, roe=None, pb=None)
    assert gone["no_equity"] and gone["debt_equity"] is None and iv.buffett(gone)["recommendation"] == iv.NO_DATA and "자본이 0 이하" in iv.buffett(gone)["opinion"]
    assert cc.figures(dividend_yield=9.45)["dividend_yield"] is None and cc.figures(dividend_yield=9.45)["_status"]["dividend_yield"] == fg.INVALID and cc.figures()["dividend_yield"] == 0.015
    assert fg.blend([("a", 1, None, fg.MISSING), ("b", 1, 0.5, fg.CONFIRMED)]) == {"score": 50.0, "coverage": 0.5, "sure": 0.5, "missing": ["a"], "not_applicable": []}
    na = fg.blend([("a", 2, None, fg.NOT_APPLICABLE), ("b", 2, 1.0, fg.CONFIRMED)])
    assert (na["coverage"], na["sure"], na["not_applicable"]) == (1.0, 2 / 3, ["a"])                # the data is complete; the judgement rests on less
    assert '"debt_equity": 99.0 if (eq is not None and eq <= 0 and debt)' in (Path(fg.__file__).parent.parent / "qsf" / "fundamentals.py").read_text(encoding="utf-8") and fg.NO_EQUITY == 99.0


def test_graham_has_two_profiles_and_sector_methods_and_lynch_six_kinds():
    assert set(iv.GRAHAM_PROFILES) == {"DEFENSIVE", "ENTERPRISING"} and iv.GRAHAM_PROFILES["ENTERPRISING"]["current"] < iv.GRAHAM_PROFILES["DEFENSIVE"]["current"]
    f = cc.figures(pe=11.0, pb=1.6, current_ratio=1.6, sector="산업재")
    assert iv.graham(f)["recommendation"] != iv.graham(f, False, {"graham_profile": "ENTERPRISING"})["recommendation"] or iv.graham(f)["profile"] == "방어적 투자자"
    assert iv.graham(f)["profile"] == "방어적 투자자" and iv.graham(f, False, {"graham_profile": "ENTERPRISING"})["profile"] == "적극적 투자자"
    assert "그레이엄 수" in iv.graham_value(cc.figures(), iv.GRAHAM_PROFILES["DEFENSIVE"])["method"] and "PBR 없이" in iv.graham_value(cc.figures(sector="기술"), iv.GRAHAM_PROFILES["DEFENSIVE"])["method"]
    assert "부동산" in iv.graham_value(cc.figures(sector="부동산"), iv.GRAHAM_PROFILES["DEFENSIVE"])["method"] and iv.graham_value(cc.figures(pe=-3.0), iv.GRAHAM_PROFILES["DEFENSIVE"])["loss"]
    kinds = {iv.lynch_kind(cc.figures(**kw)) for kw in (dict(eps_cagr3=0.02), dict(eps_cagr3=0.10), dict(eps_cagr3=0.25), dict(sector="에너지"), dict(pe=-4.0), dict(pb=0.8, eps_cagr3=0.02))}
    assert kinds == {iv.SLOW, iv.STALWART, iv.FAST, iv.CYCLICAL, iv.TURNAROUND, iv.ASSET} and len(iv.KIND_KO) == 6 and iv.lynch_kind(cc.figures(eps_cagr3=None, rev_cagr3=None)) is None
    cheap_peg = iv.lynch(cc.figures(pe=9.0, eps_cagr3=0.2, debt_equity=3.0))
    assert cheap_peg["peg"] < 1 and cheap_peg["recommendation"] == "HOLD" and "부채가 과합니다" in cheap_peg["opinion"]          # a PEG under 1 is not a buy by itself
    assert iv.lynch(cc.figures(sector="에너지", pe=5.0))["opinion"].count("정점") == 1                                         # a cyclical's low multiple is not read as cheap


def test_druckenmiller_reads_the_regime_and_steps_down_in_a_risk_off_market():
    calm = iv.druckenmiller(cc.figures(), False, CTX)
    storm = iv.druckenmiller(cc.figures(state=15.0, credit_pct=0.92, vix_pct=0.99, breadth=0.2, index_close=90.0), False, CTX)
    assert [r["regime"] for r in calm["regimes"]] == ["RISK_ON"] and {r["regime"] for r in storm["regimes"]} == {"RISK_OFF", "LIQUIDITY_CONTRACTION", "RECESSION_RISK"}
    assert all(0 <= r["confidence"] <= 100 for r in storm["regimes"]) and storm["regimes_not_told"] == ["물가 상승·둔화 국면", "성장률과 정책 금리 국면"]
    assert calm["recommendation"] == "STRONG_BUY" and storm["recommendation"] == "WAIT" and storm["suggested_weight"] == 0 < calm["suggested_weight"] and storm["risk_off"]      # the stock's trend is the same
    assert storm["trend_ok"] and "현금도 포지션입니다" in storm["opinion"]
    assert iv.regimes(cc.figures(state=None, credit_pct=None, breadth=None, index_close=None)) == []


def test_the_committee_does_not_average_and_one_risk_outweighs_a_majority():
    _f, by, c = run()
    assert c["decision"] == "BUY" and c["buyers"] == ["버핏식", "린치식", "드러켄밀러식"] and set(c["scores"]) == set(council.SCORE_KO) and len(c["scores"]) == 9
    assert [m["investor"] for m in c["minority"]] == ["멍거식", "그레이엄식"] and "따르지 않은 의견" in c["reasons"][-1] and c["strongest_for"]["investor"] in c["buyers"]
    _f, _by, marked = run(marks=["자금 조달 공시"])                                      # three views still say buy; the avoid mark decides
    assert len(marked["buyers"]) == 3 and marked["decision"] == "AVOID" and marked["material_risks"][0]["level"] == council.CRITICAL and marked["strongest_against"]["text"].startswith("회피 표시")
    _f, _by, deal = run(deals=[{"form": "DEFM14A"}])
    assert deal["decision"] == council.CONDITIONAL_BUY and any(r["name"] == "인수·합병 절차" for r in deal["material_risks"])
    _f, _by, thin = run(gross_margin=None, fcf_margin=None, fcf_years=None, cash_debt=None, interest_cover=None, current_ratio=None, insider_pct=None, share_change=None, returns_capital=None,
                        ocf_to_ni=None, fcf_yield=None, rev_cagr3=None, market_cap=None, dividend_yield=None, reward_risk=None, atr_pct=None, earnings_sessions=None, events_positive=None)
    assert thin["scores"]["data"] < 100 and thin["scores"]["confidence"] <= 100
    assert council.decide(cc.figures(), [])["decision"] == iv.NO_DATA
    held = run(cc.E_CHEAP_LEVERED, held={"COMMITTEE": True})[2]
    assert held["decision"] == "SELL" and held["held"]


def book(cases):
    out = {}
    for case in cases:
        f = cc.figures(**case)
        out[f["ticker"]] = service.judge(f, None, CTX)
    return out


def test_six_portfolios_are_built_six_different_ways():
    cases = [dict(ticker=f"Q{k}", sector=f"S{k % 5}") for k in range(8)] + [dict(cc.B_SOUND_AND_CHEAP, ticker=f"V{k}", sector=f"T{k % 6}") for k in range(9)] + \
            [dict(cc.C_FAST_SMALL, ticker=f"G{k}", sector=f"U{k % 4}") for k in range(6)] + [dict(cc.E_CHEAP_LEVERED, ticker="BAD"), dict(cc.F_MOAT_FULL_PRICE, ticker="MOAT")]
    b = book(cases)
    ports = pf.build(b, None, 60.0)
    assert list(ports) == ["BUFFETT", "MUNGER", "GRAHAM", "LYNCH", "DRUCKENMILLER", "COMMITTEE"] and all(p["rules"] == "IC-1" for p in ports.values())
    held = {k: {r["ticker"] for r in p["holdings"]} for k, p in ports.items()}
    assert held["BUFFETT"] == {f"Q{k}" for k in range(8)} and held["GRAHAM"] == {f"V{k}" for k in range(9)} and held["MUNGER"] == {"MOAT"}          # each takes what its own engine buys
    assert all(r["weight"] == 0.05 for r in ports["GRAHAM"]["holdings"]) and ports["GRAHAM"]["cash"] == 0.55 and "나머지는 현금" in ports["GRAHAM"]["cash_reasons"][0]
    assert ports["MUNGER"]["count"] == 1 and ports["MUNGER"]["cash"] > 0.8 and ports["MUNGER"]["largest"] <= pf.SPEC["MUNGER"]["cap"]          # no stock bought to fill a place
    assert len({r["category"] for r in ports["LYNCH"]["holdings"]}) >= 2 and max(sum(1 for r in ports["LYNCH"]["holdings"] if r["category"] == k) for k in ("고성장주", "자산주", "대형 우량주")) <= 4
    assert "BAD" not in set().union(*held.values()) and ports["COMMITTEE"]["count"] <= 15 and all(r["weight"] <= 0.10 + 1e-9 for r in ports["COMMITTEE"]["holdings"])
    assert held["COMMITTEE"] != held["BUFFETT"] and not held["COMMITTEE"] <= (held["BUFFETT"] & held["GRAHAM"] & held["LYNCH"])          # not the intersection
    assert all(abs(p["invested"] + p["cash"] - 1.0) < 1e-6 and max(p["sectors"].values(), default=0) <= 1 for p in ports.values())
    one = ports["BUFFETT"]["holdings"][0]
    assert {"ticker", "name", "weight", "score", "confidence", "recommendation", "expected_return", "downside_risk", "thesis", "entry", "exit", "sizing", "as_of", "status"} <= set(one) and one["status"] == "새로 편입"
    storm = pf.build(b, None, 20.0)                                                         # the market's regime sets how much is invested
    assert storm["DRUCKENMILLER"]["invested"] <= 0.4 + 1e-9 and storm["COMMITTEE"]["invested"] <= 0.6 + 1e-9 and storm["GRAHAM"]["invested"] == ports["GRAHAM"]["invested"]
    assert "시장 국면 때문에" in storm["COMMITTEE"]["cash_reasons"][0] and pf.exposure(None, pf.D_EXPOSURE) == 1.0
    over = pf.overlap(ports)
    assert len(over) == 15 and all(o["count"] == len(o["shared"]) for o in over)
    assert pf.build({}, None, 60.0)["BUFFETT"]["count"] == 0 and "매수 조건을 채운 종목이 없습니다" in pf.build({}, None, 60.0)["BUFFETT"]["cash_reasons"][0]


def test_a_held_stock_is_kept_until_its_engine_says_sell_and_twins_are_one_holding():
    b = book([dict(ticker="KEEP"), dict(cc.A_EXCELLENT_BUT_DEAR, ticker="WAITS"), dict(cc.E_CHEAP_LEVERED, ticker="GONE")])
    for t, e in b.items():                                                               # judged again as held stocks
        b[t] = service.judge(e["figures"], {k: True for k in pf.ORDER}, CTX)
    prev = {"KEEP": 0.10, "WAITS": 0.07, "GONE": 0.06, "LEFT": 0.05}
    p = pf.investor_portfolio("BUFFETT", b, prev, 60.0)
    rows = {r["ticker"]: r for r in p["holdings"]}
    assert set(rows) == {"KEEP", "WAITS"} and rows["WAITS"]["status"] == "보유 유지" and rows["WAITS"]["recommendation"] == "WAIT"          # held and merely dear: kept
    assert rows["WAITS"]["weight"] == 0.07 and rows["KEEP"]["weight"] == 0.10 and b["KEEP"]["opinions"]["BUFFETT"]["suggested_weight"] != 0.10          # a small change is not a trade
    assert [x["ticker"] for x in p["exits"]] == ["GONE", "LEFT"] and "이번 스캔 기록에 없는 종목" in p["exits"][1]["why"] and p["turnover"] > 0
    same = [0.01, -0.02, 0.015, 0.0, -0.01] * 20
    b2 = book([dict(ticker="A1", sector="X1"), dict(ticker="A2", sector="X2"), dict(ticker="A3", sector="X3")])
    series = {"A1": same, "A2": same, "A3": [0.02, 0.01, -0.03, 0.0, 0.01] * 20}
    twins = pf.build(b2, None, 60.0, lambda t: series.get(t))
    assert [r["ticker"] for r in twins["BUFFETT"]["holdings"]] == ["A1", "A3"] and twins["COMMITTEE"]["moves_together"] == [{"ticker": "A2", "with": "A1", "correlation": 1.0}]
    assert pf.correlation([0.1] * 10, [0.1] * 10) is None and pf.correlation(None, same) is None


def test_the_record_is_one_line_a_session_and_paper_results_never_look_back(tmp_path):
    b = book([dict(ticker="AAA1"), dict(cc.B_SOUND_AND_CHEAP, ticker="BBB1")])
    ports = pf.build(b, None, 60.0)
    assert record.append(tmp_path, "US", "2026-11-23", b, ports)["status"] == "OK" and record.append(tmp_path, "US", "2026-11-23", b, ports)["status"] == "ALREADY"
    rows = record.read(tmp_path, "US")
    assert len(rows) == 1 and rows[0]["rules"] == "IC-1" and rows[0]["order"] == list(iv.ORDER) + ["COMMITTEE"] and rows[0]["stocks"]["AAA1"] == "SHWSSB" and len(rows[0]["scores"]["AAA1"]) == 6
    assert record.held(rows[0])["BUFFETT"] == {"AAA1": ports["BUFFETT"]["holdings"][0]["weight"]} and record.before(rows, "2026-11-23") is None and record.before(rows, "2026-11-24") == rows[0]
    (tmp_path / "research_data" / "committee_us" / "2026-11.jsonl").open("a").write("{broken\n")            # a torn line is left out, never repaired
    assert len(record.read(tmp_path, "US")) == 1 and record.read(tmp_path, "KR") == []
    days = [f"2026-12-{d:02d}" for d in range(1, 8)]
    lines = [{"session": d, "portfolios": {"X": {"cash": 0.5, "holdings": {"UP": 0.5} if i < 4 else {"DN": 0.5}}}} for i, d in enumerate(days)]
    price = lambda t, s: {"UP": 100.0 * 1.01 ** days.index(s), "DN": 100.0 * 0.99 ** days.index(s)}[t]      # noqa: E731
    out = record.performance(lines, price, lambda s: 100.0 * 1.005 ** days.index(s), 0.002)
    x = out["portfolios"]["X"]
    # weights recorded on day i earn from day i+1 to i+2: five days, never the day they were made on
    assert out["status"] == "OK" and out["kind"] == "PAPER" and x["days"] == 5 and x["benchmark_days"] == 5 and abs(x["benchmark_return"] - (1.005 ** 5 - 1)) < 1e-4
    assert abs(x["total_return"] - ((1 + 0.005 - 0.001) * 1.005 ** 3 * (1 - 0.005 - 0.002) - 1)) < 1e-4 and x["positions_closed"] == 1 and x["average_holding_sessions"] == 4.0
    assert "60거래일부터" in x["ratios"] and "sharpe" not in x and "cagr" not in x and x["unpriced"] == []
    # 2026-11-23: a recorded weight that stays at 0.5 while its price moves is a small trade back to 0.5 every day (weights follow prices now)
    assert 0.003 < x["cost_total"] < 0.00305
    assert record.performance(lines[:2], price, lambda s: None, 0.002)["status"] == "TOO_SHORT"
    jump = record.performance(lines[:4], lambda t, s: 100.0 if s != days[3] else 300.0, lambda s: None, 0.0)["portfolios"]["X"]
    assert jump["price_breaks"] and jump["total_return"] == 0.0                              # a 200% day is a break in the series, not a gain
    long_days = [f"D{i:03d}" for i in range(70)]
    many = [{"session": d, "portfolios": {"X": {"cash": 0.0, "holdings": {"UP": 1.0}}}} for d in long_days]
    full = record.performance(many, lambda t, s: 100.0 * (1.01 if long_days.index(s) % 2 else 1.0) * 1.001 ** long_days.index(s), lambda s: 100.0 * 1.0005 ** long_days.index(s), 0.0)["portfolios"]["X"]
    assert full["days"] == 68 and {"cagr", "volatility", "sharpe", "sortino", "calmar", "beta", "alpha"} <= set(full)


def test_the_screens_ask_for_portfolios_only_through_a_button(live):
    import urllib.request
    url, _ = live
    def get(path):
        with urllib.request.urlopen(f"{url}{path}", timeout=5) as r:
            return json.loads(r.read())
    assert get("/api/committee/stock?t=005930&market=KR")["status"] in ("OK", "NO_VIEW") and get("/api/committee/portfolios?market=KR")["status"] in ("OK", "NO_SCAN")
    assert get("/api/committee/dashboard?market=US")["status"] in ("OK", "NO_SCAN") and get("/api/committee/compare?market=US")["status"] in ("OK", "NO_SCAN")
    perf = get("/api/committee/performance?market=US")
    assert perf["status"] == "TOO_SHORT" and perf["kind"] == "PAPER" and "백테스트" in perf["not_this"] and get("/api/committee/place?t=AAPL&market=US")["status"] in ("OK", "NO_SCAN")
    static = Path(service.__file__).parent.parent / "static"
    js, html, qsf = (static / "committee.js").read_text(encoding="utf-8"), (static / "index.html").read_text(encoding="utf-8"), (static / "qsf.js").read_text(encoding="utf-8")
    assert '<button data-tab="committee" data-group="score">투자위원회</button>' in html and 'id="tab-committee"' in html and html.index("qsf.js") < html.index("committee.js")
    assert "${icCardHtml(d.committee, d.ticker, d.market)}" in qsf and "RENDER.committee = renderCommittee" in js
    # the two requests that make portfolios are each sent from one place, a button's handler; opening the tab draws the button only
    uses = {name: sum(f.read_text(encoding="utf-8").count(name) for f in static.glob("*.js")) for name in ("/api/committee/portfolios", "/api/committee/place")}
    assert uses == {"/api/committee/portfolios": 1, "/api/committee/place": 1}
    get_ports = js[js.index("async function icPortsGet()"):js.index("function icPorts()")]
    assert "/api/committee/portfolios" in get_ports and "icPortsGet()" not in js[js.index("function renderCommittee()"):js.index("function icOpenRows")]
    assert js.count('$("#icportsget").onclick = () => icPortsGet();') == 2 and 'e.target.closest(".ic-place"); if (b) icPlace(b);' in js and "여섯 포트폴리오 받아보기</button>" in js
    for name in ("warm.py", "today.py"):                                                    # nor does the server make them ahead of time
        assert "committee" not in (Path(service.__file__).parent.parent / name).read_text(encoding="utf-8")
    app = (Path(service.__file__).parent.parent.parent / "app.py").read_text(encoding="utf-8")
    assert app.count('_committee_record(res, "') == 2 and "committee_service.daily_record" in app                # the daily job writes the record; no screen reads a portfolio from it unasked
    from terminal import automation
    assert "research_data/committee_kr/*.jsonl" in automation.BACKUP_GLOBS and "research_data/committee_us/*.jsonl" in automation.BACKUP_GLOBS


def test_graham_shows_the_enterprising_verdict_beside_the_defensive_one_and_changes_nothing():
    """User decision 2026-11-22: both profiles on the card for comparison; the portfolio and the record use the defensive one alone."""
    f = cc.figures(pe=9.0, pb=1.0, current_ratio=1.6, eps_cagr3=0.02)             # cheap, and its current ratio is between the two profiles' bars
    one = iv.graham(f)
    assert one["profile"] == "방어적 투자자" and one["other_profile"]["profile"] == "적극적 투자자" and set(one["other_profile"]) == {"profile", "recommendation", "recommendation_ko", "score", "opinion", "buy", "same"}
    assert one["other_profile"]["recommendation"] == iv.graham(f, False, {"graham_profile": "ENTERPRISING"})["recommendation"] and "other_profile" not in iv.graham(f, False, {"graham_profile": "ENTERPRISING"})
    assert one["other_profile"]["same"] == (one["recommendation"] == one["other_profile"]["recommendation"])
    b = book([dict(ticker="X1", pe=9.0, pb=1.0, current_ratio=1.6, eps_cagr3=0.02)])
    assert b["X1"]["opinions"]["GRAHAM"]["recommendation"] == one["recommendation"]                      # what the portfolio and the record read
    assert "other_profile" in service.CARD_KEYS and "alt.profile" in (Path(service.__file__).parent.parent / "static" / "committee.js").read_text(encoding="utf-8")


def test_a_financial_is_judged_among_the_sessions_financials_and_never_more_easily_than_before():
    """User decision 2026-11-22: on the 2026-11-20 record the committee's most attractive US stocks were mostly insurers."""
    banks = {f"B{k}": cc.figures(ticker=f"B{k}", sector="금융", roe=0.06 + 0.02 * k) for k in range(10)}          # 6% .. 24%
    ctx = service.context(banks)
    peers = ctx["financial_roe"]
    assert (peers["n"], round(peers["median"], 6), round(peers["top"], 6)) == (10, 0.15, 0.24) and iv.fin_band(ctx, 0.08, 0.16)[:2] == (peers["median"], peers["top"]) and iv.fin_band(None, 0.08, 0.16) == (0.08, 0.16, None)
    mid, top = banks["B5"], banks["B9"]                                                     # 16% and 24%
    assert iv.buffett(mid, False, None)["components"]["사업의 질"] == 100.0 and iv.buffett(mid, False, ctx)["components"]["사업의 질"] < 15       # an ordinary financial is ordinary among financials
    assert iv.buffett(top, False, ctx)["components"]["사업의 질"] == 100.0 and "금융업 10종목의 중앙값 15.0%, 상위 10% 24.0%" in iv.buffett(mid, False, ctx)["opinion"]
    assert iv.munger(mid, False, ctx)["components"]["사업의 탁월함"] < iv.munger(mid, False, None)["components"]["사업의 탁월함"]
    low = service.context({f"L{k}": cc.figures(ticker=f"L{k}", sector="금융", roe=0.02 + 0.01 * k) for k in range(10)})      # the best of a poor lot: 11%
    assert iv.fin_band(low, 0.08, 0.16)[:2] == (0.08, 0.16) and iv.buffett(cc.figures(sector="금융", roe=0.11), False, low)["components"]["사업의 질"] < 40
    assert iv.fin_band(service.context({"A": cc.figures(sector="금융")}), 0.08, 0.16)[2] is None and service.context({})["financial_roe"] is None      # too few to compare
    plain = cc.figures()
    assert iv.buffett(plain, False, ctx)["score"] == iv.buffett(plain, False, None)["score"]             # nothing changes for a company that is not a financial


def test_the_paper_record_is_read_once_at_240_days_by_the_written_rule(tmp_path):
    """User decision 2026-11-22; reports/IC1_PAPER_READING_PROTOCOL.md was committed before the first record line."""
    import random
    from terminal.committee import reading
    from terminal.qsf import readings
    folder = tmp_path / "research_data" / "committee_us"
    folder.mkdir(parents=True)
    days = [f"D{i:04d}" for i in range(260)]
    held = {"BUFFETT": "UP", "MUNGER": "FLAT", "GRAHAM": "DOWN"}
    ports = {k: {"cash": 0.0 if k in held else 1.0, "holdings": {held[k]: 1.0} if k in held else {}} for k in pf.ORDER}
    def write(n):
        (folder / "2027-01.jsonl").write_text("".join(json.dumps({"session": d, "rules": "IC-1", "portfolios": ports}) + "\n" for d in days[:n]), encoding="utf-8")
    rng = random.Random(7)
    index, level = {}, 100.0
    for d in days:
        level *= 1.0 + rng.gauss(0.0003, 0.008)
        index[d] = level
    drift = {"UP": 0.004, "FLAT": 0.0, "DOWN": -0.004}
    px = {t: {} for t in drift}
    for t, extra in drift.items():
        own, noise = 100.0, random.Random(t)
        for i, d in enumerate(days):
            own = own if i == 0 else own * (index[d] / index[days[i - 1]]) * (1.0 + extra + noise.gauss(0, 0.004))
            px[t][d] = own
    price, bench = (lambda t, s: px[t].get(s)), (lambda s: index.get(s))
    write(241)
    try:
        reading.evaluate_once(tmp_path, "US", price, bench, 0.0)
        raise AssertionError("read before 240 paper days")
    except RuntimeError as exc:
        assert "241거래일" in str(exc) and not (tmp_path / reading.REPORTS["US"]).exists()
    write(260)
    res = reading.evaluate_once(tmp_path, "US", price, bench, 0.0)
    got = {k: v["verdict"] for k, v in res["portfolios"].items()}
    assert res["days"] == 240 and res["records"] == 242 and res["last"] == days[241] and res["bar"] == 3.0 and res["kind"] == "PAPER"            # the first 242 records only
    assert got == {"BUFFETT": "BETTER", "MUNGER": "NOT_DISTINGUISHED", "GRAHAM": "WORSE", "LYNCH": "NOT_DISTINGUISHED", "DRUCKENMILLER": "NOT_DISTINGUISHED", "COMMITTEE": "NOT_DISTINGUISHED"}
    assert res["verdict"] == "PAPER_BETTER" and res["portfolios"]["BUFFETT"]["t"] >= 3.0 and res["portfolios"]["LYNCH"]["average_invested"] == 0.0 and len(res["reasons"]) == 7
    assert "daily" not in res["portfolios"]["BUFFETT"] and json.loads((tmp_path / reading.REPORTS["US"]).read_text(encoding="utf-8"))["verdict"] == "PAPER_BETTER"
    try:
        reading.evaluate_once(tmp_path, "US", price, bench, 0.0)
        raise AssertionError("read twice")
    except RuntimeError as exc:
        assert "이미 읽었습니다" in str(exc)
    assert reading.judge(2.99) == "NOT_DISTINGUISHED" and reading.judge(-3.0) == "WORSE" and reading.judge(None) == "NOT_DISTINGUISHED"
    # the daily job finds it by itself: two entries in the list of readings, counted on the committee's own record
    by = {e["key"]: e for e in readings.REGISTRY}
    e = by["committee_paper_us"]
    assert e["argv"] == ["--market", "US", "qsf", "committee-evaluate"] and e["report"] == reading.REPORTS["US"].name and (e["need"], e["horizon"]) == (reading.READ_AT, 2)
    assert readings.records(tmp_path, e) == 260 and readings.due(tmp_path, e) and readings.records(tmp_path, by["committee_paper_kr"]) == 0 and not readings.due(tmp_path, by["committee_paper_kr"])
    assert readings.verdict(e, res) == "PAPER_BETTER" and "지수보다 나았다고 볼 만한 것" in readings.meaning("PAPER_BETTER") and "자동으로 바뀌지 않습니다" in e["after"]
    assert "버핏식 포트폴리오: 지수보다 나음" in readings.text(e, res)
    protocol = (Path(reading.__file__).parent.parent.parent / reading.PROTOCOL).read_text(encoding="utf-8")
    assert "t ≥ 3.0이면" in protocol and "시차 5" in protocol and "240개" in protocol and "아무것도 자동으로 바뀌지 않는다" in protocol
    app = (Path(reading.__file__).parent.parent.parent / "app.py").read_text(encoding="utf-8")
    assert '"committee-evaluate": _qsf_committee' in app and '"committee-evaluate"' in app[app.index("QSF_ACTIONS = ["):app.index("def ", app.index("QSF_ACTIONS = ["))]
