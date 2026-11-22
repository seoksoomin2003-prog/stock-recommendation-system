"""A portfolio around one stock from the five views, made only when asked for (user request 2026-11-22, rules FP-1)."""
import json
from pathlib import Path

from terminal import five_portfolio as fp
from terminal import five_views as fv
from tests.test_five_views import SWING, long_snap
from tests.test_terminal_1 import _loopback_only, live  # noqa: F401  (fixtures: a local server on 127.0.0.1 only)

DEAR = dict(pe=40.0, pb=9.0)                                              # Graham and Lynch do not hold it; the other three do
WEAK = dict(pe=40.0, pb=9.0, roe=0.02, op=0.03, gross=0.1, de=3.0, years=0.5, ma200=150.0, slope=-0.1, pct=0.1, ret=-0.3, dd=-0.6, eps3=-0.2, fcf=-0.1)


def stock(ticker, sector, **kw):
    return {"ticker": ticker, "name": f"{ticker} Co", "sector": sector, "long": long_snap(**kw), "swing": SWING}


def seen(extra=()):
    rows = [stock(f"G{k}", f"S{k}") for k in range(8)] + [stock("DEAR", "기술", **DEAR), stock("WEAK", "소재", **WEAK), {"ticker": "NONE", "long": {"factors": []}}]
    return fv.survey(rows + list(extra))


def test_the_stock_asked_for_is_the_centre_and_the_weights_follow_the_number_of_holding_views():
    p = fp.build(seen(), "DEAR")
    assert p["status"] == "OK" and p["rules"] == "FP-1" and p["seed_in"] and p["seed_agree"] == 3 and p["rows"][0]["ticker"] == "DEAR" and p["rows"][0]["is_seed"]
    # the three holders have one place left, the two that do not hold it have two: 3 + 2 * 2 = 7 stocks beside the one asked for
    assert [v["name"] for v in p["by_view"] if v["holds_seed"]] == ["버핏식", "멍거식", "드러켄밀러식"] and [len(v["added"]) for v in p["by_view"]] == [1, 1, 2, 2, 1] and len(p["rows"]) == 8
    total = 3 + 7 * 5
    assert p["rows"][0]["weight"] == round(3 / total, 4) and all(r["weight"] == round(5 / total, 4) and r["agree"] == 5 for r in p["rows"][1:]) and abs(sum(r["weight"] for r in p["rows"]) - 1) < 0.001
    assert [r["ticker"] for r in p["rows"][1:]] == [f"G{k}" for k in range(7)] and len({r["ticker"] for r in p["rows"]}) == 8      # ties by ticker: the same portfolio on every run
    assert p["lines"][0] == "DEAR Co 중심의 8종목입니다. 다섯 관점 가운데 3개(버핏식, 멍거식, 드러켄밀러식)가 이 종목을 담아 비중은 7.9%입니다."
    assert p["seed_lines"][0].startswith("버핏식: 담음(기준에 맞음, 기준 7개 중 6개 충족). ROE 20.0%") and p["seed_lines"][2].startswith("그레이엄식: 담지 않음(일부 맞음, 기준 7개 중 5개 충족). 핵심 기준(PER 15배 이하")
    assert p["lines"][1].startswith("DEAR Co(DEAR) 7.9%: 3개 관점이 담음(버핏식, 멍거식, 드러켄밀러식).") and "G0 Co(G0) 13.2%: 5개 관점이 담음" in p["lines"][2] and "버핏식이 더함(ROE 20.0%" in p["lines"][2]
    assert p["lines"][-2] == fp.NOTE and p["lines"][-1] == fv.NOTE and "한 업종은 2종목까지만 담습니다." in p["lines"][-3]
    flat = " ".join(p["lines"] + p["seed_lines"])
    assert not any(w in flat for w in ("매수", "매도", "사세요", "파세요", "추천"))                              # held or not held by a checklist, never an order to trade
    assert fp.build(seen(), "DEAR") == p


def test_a_stock_no_view_holds_is_left_out_and_said_so_and_a_stock_without_figures_gets_no_portfolio():
    p = fp.build(seen(), "WEAK")
    assert p["status"] == "OK" and not p["seed_in"] and p["seed_agree"] == 0 and all(not r["is_seed"] for r in p["rows"]) and "WEAK" not in [r["ticker"] for r in p["rows"]]
    assert p["lines"][0] == "WEAK Co: 다섯 관점 가운데 이 종목을 담는 관점이 없어 넣지 않았습니다. 대신 각 관점이 자기 기준으로 고른 9종목입니다."      # each view has both places; Lynch finds one stock left that it holds
    assert all(line.split(": ")[1].startswith("담지 않음") for line in p["seed_lines"]) and "걸리는 것: ROE 2.0%(기준: ROE 15% 이상)" in p["seed_lines"][0]
    assert abs(sum(r["weight"] for r in p["rows"]) - 1) < 0.001
    none = fp.build(seen(), "NONE")
    assert none["status"] == "NO_VIEW" and none["rows"] == [] and "판단할 수 없는 종목을 중심으로 포트폴리오를 만들지 않습니다" in none["reason"] and fp.build(seen(), "ZZZZ")["status"] == "NO_VIEW"
    alone = fp.build(fv.survey([stock("WEAK", "소재", **WEAK)]), "WEAK")
    assert alone["status"] == "EMPTY" and alone["rows"] == [] and alone["lines"][0].endswith("포트폴리오를 만들지 않았습니다.")


def test_one_sector_cannot_fill_the_portfolio_and_the_market_state_is_not_the_first_objection():
    banks = fv.survey([stock(f"B{k}", "금융") for k in range(6)] + [stock("TECH", "기술", **DEAR)])
    p = fp.build(banks, "TECH")
    assert [r["ticker"] for r in p["rows"]] == ["TECH", "B0", "B1"] and sum(v["passed_for_sector"] for v in p["by_view"]) > 0      # two of the six, whoever asks
    assert "그레이엄식: 더한 종목 없음(이 관점의 기준에 맞는 다른 종목 6개, 업종 한도로 넘긴 종목 4개)." in p["lines"]
    assert [(v["held"], v["passed_for_sector"]) for v in p["by_view"]] == [(6, 0), (6, 0), (6, 4), (6, 4), (6, 4)]
    assert fp.SECTOR_CAP == 2 and fp.PER_VIEW == 2
    down = fv.survey([{"ticker": "DOWN", "name": "Down", "sector": "기술", "long": long_snap(ma200=150.0, slope=-0.1, pct=0.1, ret=-0.3, dd=-0.6, state=15.0), "swing": SWING}])["DOWN"]["views"]["DRUCKENMILLER"]
    assert down["verdict"] == fv.FAILS and down["con"][0].startswith("200일선 대비") and not any(fv.MARKET_ASK in c for c in down["con"])      # the stock's own figures first


def test_the_portfolio_is_made_only_when_the_button_asks(live):
    import urllib.request
    url, _ = live
    with urllib.request.urlopen(f"{url}/api/five/portfolio?t=005930&market=KR", timeout=5) as r:
        got = json.loads(r.read())
    assert got["status"] in ("NO_SCAN", "NO_VIEW") and got["rows"] == [] and got["rules"] == "FP-1" and got["note"] == fv.NOTE      # the scratch terminal has no figures: said, not made up
    static = Path(fp.__file__).parent / "static"
    page = (static / "qsf.js").read_text(encoding="utf-8")
    assert 'class="fp-get"' in page and "포트폴리오 받아보기</button>" in page and 'e.target.closest(".fp-get"); if (b) qsfPortfolio(b);' in page
    # the one place that asks the server for a portfolio is the button's handler: no tab, no card and no first screen makes one
    asks = [(f.name, f.read_text(encoding="utf-8").count("/api/five/portfolio")) for f in sorted(static.glob("*.js"))]
    assert [x for x in asks if x[1]] == [("qsf.js", 1)] and page.count("qsfPortfolio(") == 2
    body = page[page.index("async function qsfPortfolio(btn)"):page.index('document.addEventListener("click", (e) => { const b = e.target.closest')]
    assert "/api/five/portfolio?t=" in body and "작성 중…" in body
    for name in ("warm.py", "services.py"):                                                    # nor does the server make one ahead of time
        assert "five_portfolio" not in (Path(fp.__file__).parent / name).read_text(encoding="utf-8")
    assert "five_portfolio" not in (Path(fp.__file__).parent.parent / "app.py").read_text(encoding="utf-8")
