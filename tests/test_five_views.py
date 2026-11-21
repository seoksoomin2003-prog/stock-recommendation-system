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
    assert loss["GRAHAM"]["checks"][0]["met"] is False and loss["LYNCH"]["checks"][0] == {"ask": "PEG(PER ÷ 이익 성장률) 1 이하", "met": False, "shown": "PEG 계산 안 됨"}      # a loss is not cheap
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
    assert [r["session"] for r in rows] == ["2026-11-23", "2026-11-24"] and rows[0]["rules"] == "FV-1" and rows[0]["picked"][0] == {"ticker": "G0", "agree": 5, "agree_names": [v[1] for v in fv.VIEWS], "mean_share": 1.0, "weight": 0.1}


from tests.test_terminal_1 import _loopback_only, live  # noqa: E402,F401  (fixtures: a local server on 127.0.0.1 only)


def test_the_team_list_has_a_route_and_the_score_tab_shows_both(live):
    import urllib.request
    from pathlib import Path
    url, _ = live
    with urllib.request.urlopen(f"{url}/api/five/team?market=KR", timeout=5) as r:
        got = json.loads(r.read())
    assert got["status"] == "UNAVAILABLE" and got["picked"] == [] and got["lines"] == [] and got["agree_needed"] == fv.AGREE      # no scan in the scratch terminal: an empty list, not an error
    page = (Path(fv.__file__).parent / "static" / "qsf.js").read_text(encoding="utf-8")
    assert "${qsfFiveHtml(d.five_views)}" in page and "/api/five/team?market=" in page and '<div id="qsffive"></div>' in page
    assert "rank: () => { qsfRank(); qsfFive(); qsfCap(); qsfChanges(); }" in page
    service = (Path(fv.__file__).parent / "qsf" / "service.py").read_text(encoding="utf-8")
    assert '"five_views": five' in service and "never fails the evaluation" in service
