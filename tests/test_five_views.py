"""Five investing approaches as fixed checklists over stored figures (user request 2026-11-22).  No score reads them."""
import json

from terminal import five_views as fv


def factor(name, **raw):
    return {"factor": name, "raw": raw}


def long_snap(pe=12.0, pb=1.2, roe=0.20, op=0.25, gross=0.5, years=1.0, eps3=0.15, rev=0.08, fcf=0.12, fcf_years=1.0, de=0.3, shares=-0.01, cur=2.5, pays=True,
              ma200=90.0, slope=0.05, pct=0.80, ret=0.20, dd=-0.15, negative=0, issues=(), price=100.0, state=60.0):
    return {"price": price, "domains": {"REGIME": {"score_100": state}},
            "factors": [factor("valuation", pe=pe, pb=pb), factor("business_quality", roe=roe, op_margin=op, gross_margin=gross, roe_years_positive=years),
                        factor("growth_quality", eps_cagr3=eps3, rev_growth=rev), factor("free_cash_flow", fcf_margin=fcf, fcf_years_positive=fcf_years),
                        factor("balance_dilution", debt_equity=de, share_change=shares), factor("financial_resilience", current_ratio=cur),
                        factor("capital_allocation", returns_capital=pays), factor("long_trend", ma200=ma200, ma200_slope=slope), factor("relative_strength", percentile=pct),
                        factor("credit_spread", percentile=0.01), factor("momentum_persistence", ret_12_1=ret), factor("downside_drawdown", max_drawdown_252=dd),
                        factor("material_events", negative=negative), factor("governance", issues=list(issues)),
                        factor("insider_ownership", insider={"status": "REAL", "open_market_buy": 5.0, "open_market_sell": 1.0})]}


SWING = {"factors": [factor("earnings_revenue_quality", eps_growth=0.12, rev_growth=0.08)]}


def test_a_stock_that_meets_every_checklist_is_read_by_all_five_views_and_joins_the_team():
    op = fv.opinions(long_snap(), SWING)
    assert [v["key"] for v in op["views"]] == ["BUFFETT", "MUNGER", "GRAHAM", "LYNCH", "DRUCKENMILLER"]
    assert all(v["verdict"] == fv.MEETS and v["met"] == v["known"] == 7 for v in op["views"]) and op["agree"] == 5 and op["in_team"]
    first = op["views"][0]
    assert first["line"] == "버핏식(좋은 사업을 적정한 값에): 기준 7개 중 7개 충족, 기준에 맞음." and first["detail"].startswith("맞는 것: ROE 20.0%, 영업이익률 25.0%")
    out = fv.lines(op)
    assert len(out) == 7 and out[5].startswith("다섯 관점 가운데 5개가 '기준에 맞음'(버핏식, 멍거식, 그레이엄식, 린치식, 드러켄밀러식).") and "실존 투자자의 실제 의견이 아닙니다" in out[6]
    assert "매수" not in " ".join(out) and "매도" not in " ".join(out)                                    # criteria met, never an order to trade
    f = fv.figures(long_snap(), SWING)
    assert f["percentile"] == 0.80                                                                       # the stock's own percentile, not the credit spread's


def test_each_view_fails_on_what_it_cares_about():
    dear = fv.opinions(long_snap(pe=40.0, pb=9.0, eps3=0.15), SWING)
    by = {v["key"]: v for v in dear["views"]}
    assert by["GRAHAM"]["verdict"] == fv.PARTLY and "PER 40.0배(기준: PER 15배 이하)" in by["GRAHAM"]["detail"] and by["LYNCH"]["checks"][0] == {"ask": "PEG(PER ÷ 이익 성장률) 1 이하", "met": False, "shown": "PEG 2.67"}
    assert by["GRAHAM"]["met"] == 5 and by["GRAHAM"]["core_missed"] == ["PER 15배 이하", "PBR 1.5배 이하이거나 PER×PBR 22.5 이하"] and "핵심 기준(PER 15배 이하, PBR 1.5배 이하이거나 PER×PBR 22.5 이하)을 채우지 못해 '맞음'으로 보지 않습니다." in by["GRAHAM"]["line"]
    assert by["LYNCH"]["verdict"] == fv.PARTLY and by["BUFFETT"]["verdict"] == fv.MEETS                  # five of seven boxes do not make a dear stock a Graham stock
    assert by["DRUCKENMILLER"]["verdict"] == fv.MEETS                                                    # price does not enter the trend view
    under = {v["key"]: v for v in fv.opinions(long_snap(ma200=101.0), SWING)["views"]}["DRUCKENMILLER"]
    assert under["met"] == 6 and under["verdict"] == fv.PARTLY and under["core_missed"] == ["가격이 200일선 위"]
    falling = {v["key"]: v for v in fv.opinions(long_snap(ma200=120.0, slope=-0.03, pct=0.2, ret=-0.2, dd=-0.5, state=15.0), SWING)["views"]}
    assert falling["DRUCKENMILLER"]["verdict"] == fv.FAILS and falling["DRUCKENMILLER"]["met"] == 1 and falling["BUFFETT"]["verdict"] == fv.MEETS
    marked = {v["key"]: v for v in fv.opinions(long_snap(), SWING, marks=["자금 조달 공시"])["views"]}
    assert marked["MUNGER"]["checks"][0] == {"ask": "경고 공시와 회피 표시가 없음", "met": False, "shown": "자금 조달 공시"} and marked["MUNGER"]["met"] == 6
    loss = {v["key"]: v for v in fv.opinions(long_snap(pe=-5.0, eps3=-0.1, years=0.5, roe=-0.05), SWING)["views"]}
    assert loss["GRAHAM"]["checks"][0]["met"] is False and loss["LYNCH"]["checks"][0] == {"ask": "PEG(PER ÷ 이익 성장률) 1 이하", "met": False, "shown": "PEG 계산 안 됨(적자이거나 3년 이익이 줄었음)"}      # a loss is not cheap
    est = fv.opinions(long_snap(), SWING, info={"epsCurrentYear": 10.0, "forwardEps": 8.0})["views"][4]
    assert est["checks"][4] == {"ask": "이익이 늘어나는 쪽", "met": False, "shown": "다음 해 예상 이익 -20.0%(야후 집계)"}


def test_a_missing_figure_is_not_counted_and_too_few_figures_give_no_view():
    bank = long_snap(op=None, gross=None, fcf=None, cur=None)
    by = {v["key"]: v for v in fv.opinions(bank, SWING)["views"]}
    assert by["BUFFETT"]["known"] == 5 and by["BUFFETT"]["met"] == 5 and by["GRAHAM"]["known"] == 6 and by["MUNGER"]["known"] == 6      # missing is neither met nor missed
    empty = fv.opinions({"price": 10.0, "factors": []}, None)
    assert all(v["verdict"] == fv.UNKNOWN for v in empty["views"]) and empty["judged"] == 0 and not empty["in_team"] and empty["mean_share"] is None
    assert fv.team_line(empty) == "다섯 관점 모두 자료가 모자라 판단하지 않았습니다." and empty["views"][0]["line"].endswith("판단하지 않았습니다.")
    assert fv.opinions(None, None)["judged"] == 0


def test_a_view_is_not_met_when_its_core_figure_is_missing():
    """Review 2026-11-22 on the real record of 2026-11-20, before the first daily record: 9 US stocks with negative equity met the
    Buffett view with no return on equity at all, and 33 Korean stocks met the Lynch view with no PEG."""
    by = {v["key"]: v for v in fv.opinions(long_snap(roe=None, pb=None, de=99.0), SWING)["views"]}
    assert by["BUFFETT"]["met"] == 5 and by["BUFFETT"]["known"] == 6 and by["BUFFETT"]["verdict"] == fv.PARTLY and by["BUFFETT"]["core_unknown"] == ["ROE 15% 이상"]
    assert by["BUFFETT"]["line"].endswith("일부 맞음. 핵심 기준(ROE 15% 이상)을 확인할 자료가 없어 '맞음'으로 보지 않습니다.") and by["BUFFETT"]["capped"].startswith("핵심 기준(ROE 15% 이상)")
    assert "자본이 0 이하라 부채/자본 계산 안 됨(기준: 부채/자본 0.8배 이하)" in by["BUFFETT"]["detail"] and "99" not in by["BUFFETT"]["detail"]      # the stored 99 is a mark, not a ratio
    assert by["MUNGER"]["verdict"] == fv.PARTLY and by["MUNGER"]["core_unknown"] == ["ROE 15% 이상"]                                   # return on equity is Munger's core too
    assert by["DRUCKENMILLER"]["verdict"] == fv.MEETS and by["DRUCKENMILLER"]["capped"] == ""                                         # its own core figure is there
    no_growth = {v["key"]: v for v in fv.opinions(long_snap(eps3=None), SWING)["views"]}["LYNCH"]
    assert no_growth["checks"][0] == {"ask": "PEG(PER ÷ 이익 성장률) 1 이하", "met": None, "shown": "PEG 자료 없음"} and no_growth["met"] == no_growth["known"] == 5 and no_growth["verdict"] == fv.PARTLY
    both = {v["key"]: v for v in fv.opinions(long_snap(pe=40.0, pb=None), SWING)["views"]}["GRAHAM"]
    assert both["verdict"] == fv.PARTLY and "채우지 못해" in both["capped"] and "확인할 자료가 없어" in both["capped"]                  # one core box missed, the other not known
    from pathlib import Path
    assert '"debt_equity": 99.0 if (eq is not None and eq <= 0 and debt)' in (Path(fv.__file__).parent / "qsf" / "fundamentals.py").read_text(encoding="utf-8") and fv.NO_EQUITY == 99.0


def test_meets_needs_four_criteria_met_and_munger_needs_return_on_equity():
    """User decision 2026-11-22 ("둘 다 적용해"), before the first record.  On the 2026-11-20 record three of four known boxes made
    Allstate (two loss years of five) meet the Buffett view, and Samsung Electronics met the Munger view at a 10.4% return on equity."""
    assert fv.MIN_MET == 4 and fv.CORE["MUNGER"] == (0, 4) and fv.munger({})[4][0] == "ROE 15% 이상" and fv.munger({})[0][0] == "경고 공시와 회피 표시가 없음"
    thin = {v["key"]: v for v in fv.opinions(long_snap(op=None, gross=None, fcf=None, de=None, cur=None, years=0.6), SWING)["views"]}["BUFFETT"]
    assert (thin["met"], thin["known"]) == (3, 4) and thin["verdict"] == fv.PARTLY and thin["capped"] == "충족한 기준이 4개에 못 미쳐 '맞음'으로 보지 않습니다."
    assert thin["line"] == "버핏식(좋은 사업을 적정한 값에): 기준 4개 중 3개 충족, 일부 맞음. 충족한 기준이 4개에 못 미쳐 '맞음'으로 보지 않습니다."
    four = {v["key"]: v for v in fv.opinions(long_snap(op=None, gross=None, fcf=None, de=None, cur=None), SWING)["views"]}["BUFFETT"]
    assert (four["met"], four["known"]) == (4, 4) and four["verdict"] == fv.MEETS and four["capped"] == ""
    plain = {v["key"]: v for v in fv.opinions(long_snap(roe=0.10), SWING)["views"]}
    assert (plain["MUNGER"]["met"], plain["MUNGER"]["known"]) == (6, 7) and plain["MUNGER"]["verdict"] == fv.PARTLY and plain["MUNGER"]["core_missed"] == ["ROE 15% 이상"]
    assert plain["MUNGER"]["capped"] == "핵심 기준(ROE 15% 이상)을 채우지 못해 '맞음'으로 보지 않습니다." and plain["GRAHAM"]["verdict"] == fv.MEETS      # Graham does not ask for it


def test_a_missing_half_of_a_criterion_is_not_read_as_a_low_figure():
    moat = lambda **kw: {v["key"]: v for v in fv.opinions(long_snap(**kw), SWING)["views"]}["MUNGER"]["checks"][5]      # noqa: E731
    assert moat(gross=None, op=0.13) == {"ask": "매출총이익률 40% 이상이거나 영업이익률 20% 이상", "met": None, "shown": "영업이익률 13.0%"}      # Korea: no gross margin on file
    assert moat(gross=None, op=0.25)["met"] is True and moat(gross=0.2, op=None)["met"] is None and moat(gross=0.2, op=0.1)["met"] is False
    assert moat(gross=None, op=None) == {"ask": "매출총이익률 40% 이상이거나 영업이익률 20% 이상", "met": None, "shown": "이익률 자료 없음"}
    cash = lambda **kw: {v["key"]: v for v in fv.opinions(long_snap(**kw), SWING)["views"]}["BUFFETT"]["checks"][4]["met"]      # noqa: E731
    assert cash(fcf=0.1, fcf_years=None) is None and cash(fcf=0.01, fcf_years=None) is False and cash(fcf=0.1, fcf_years=0.5) is False and cash(fcf=0.1, fcf_years=0.8) is True


def test_the_market_state_is_the_one_the_program_shows_and_the_index_fund_is_not_a_stock():
    """The screen's market state is the swing scan's; the long scan scores its own (15 and 14 on 2026-11-20)."""
    swing = {**SWING, "domains": {"REGIME": {"score_100": 15.4}}}
    assert fv.figures(long_snap(state=14.2), swing)["market_state"] == 15.4 and fv.figures(long_snap(state=14.2), SWING)["market_state"] == 14.2
    assert fv.figures(None, swing)["market_state"] == 15.4 and fv.figures({"factors": []}, None)["market_state"] is None
    from terminal import assistant
    from terminal.qsf import config
    assert assistant.BENCHMARKS == frozenset(config.BENCHMARK.values())
    source = (__import__("pathlib").Path(assistant.__file__)).read_text(encoding="utf-8")
    assert "if t not in BENCHMARKS]" in source


def test_the_team_list_needs_a_majority_and_can_be_empty(tmp_path):
    good, dear, weak = long_snap(), long_snap(pe=40.0, pb=9.0), long_snap(pe=40.0, pb=9.0, roe=0.02, op=0.03, gross=0.1, de=3.0, years=0.5, ma200=150.0, slope=-0.1, pct=0.1, ret=-0.3, dd=-0.6, eps3=-0.2, fcf=-0.1)
    stocks = [{"ticker": f"G{k}", "name": f"Good {k}", "long": good, "swing": SWING, "sector": "금융"} for k in range(12)] \
        + [{"ticker": "DEAR", "name": "Dear", "long": dear, "swing": SWING, "sector": "기술"}, {"ticker": "WEAK", "long": weak, "swing": SWING}, {"ticker": "NONE", "long": {"factors": []}}]
    t = fv.team(stocks)
    assert t["judged"] == 14 and t["eligible"] == 13 and len(t["picked"]) == 10 and all(r["agree"] == 5 and r["weight"] == 0.1 for r in t["picked"]) and t["meets_by_view"]["GRAHAM"] == 12
    assert [r["ticker"] for r in t["picked"]] == [f"G{k}" for k in (0, 1, 10, 11, 2, 3, 4, 5, 6, 7)]       # ties by ticker: the list is the same on every run
    out = fv.team_lines(t, "한국")
    assert out[0].startswith("한국 14종목 가운데 13종목이 과반 합의(3개 관점 이상)에 들었고") and "10%씩" in out[0] and any(x.startswith("업종: 금융 10.") for x in out)
    assert any("금융업이 절반 이상입니다" in x for x in out) and out[-2].startswith("주문을 내지 않는 참고 목록") and out[-1] == fv.NOTE
    none = fv.team([{"ticker": "WEAK", "long": weak, "swing": SWING}])
    assert none["picked"] == [] and fv.team_lines(none, "미국")[0].endswith("목록을 억지로 채우지 않습니다.")
    assert fv.record(tmp_path, "US", "2026-11-23", t) == {"status": "OK", "session": "2026-11-23", "picked": 10}
    assert fv.record(tmp_path, "US", "2026-11-23", t)["status"] == "ALREADY" and fv.record(tmp_path, "US", "2026-11-24", none)["picked"] == 0
    rows = [json.loads(x) for x in (tmp_path / "research_data" / "five_views_us" / "2026-11.jsonl").read_text().splitlines()]
    assert rows[0]["views"] == ["BUFFETT", "MUNGER", "GRAHAM", "LYNCH", "DRUCKENMILLER"] and rows[0]["verdicts"]["G0"] == "MMMMM" and rows[0]["verdicts"]["DEAR"] == "MMPPM" and "NONE" not in rows[0]["verdicts"]
    assert len(rows[0]["verdicts"]) == 14 and rows[1]["verdicts"] == {"WEAK": t["verdicts"]["WEAK"]} and set(t["verdicts"]["WEAK"]) <= set("MPFU")      # every judged stock, picked or not
    assert [r["session"] for r in rows] == ["2026-11-23", "2026-11-24"] and rows[0]["rules"] == "FV-1" and rows[0]["picked"][0] == {"ticker": "G0", "agree": 5, "agree_names": [v[1] for v in fv.VIEWS], "mean_share": 1.0, "weight": 0.1}


from tests.test_terminal_1 import _loopback_only, live  # noqa: E402,F401  (fixtures: a local server on 127.0.0.1 only)


def test_the_team_list_has_a_route_and_the_score_tab_shows_both(live):
    import urllib.request
    from pathlib import Path
    url, _ = live
    with urllib.request.urlopen(f"{url}/api/five/team?market=KR", timeout=5) as r:
        got = json.loads(r.read())
    assert "verdicts" not in got
    assert got["status"] == "UNAVAILABLE" and got["picked"] == [] and got["lines"] == [] and got["agree_needed"] == fv.AGREE      # no scan in the scratch terminal: an empty list, not an error
    page = (Path(fv.__file__).parent / "static" / "qsf.js").read_text(encoding="utf-8")
    assert "${qsfFiveHtml(d.five_views)}" in page and "/api/five/team?market=" in page and '<div id="qsffive"></div>' in page
    assert "rank: () => { qsfRank(); qsfFive(); qsfCap(); qsfChanges(); }" in page
    service = (Path(fv.__file__).parent / "qsf" / "service.py").read_text(encoding="utf-8")
    assert '"five_views": five' in service and "never fails the evaluation" in service
