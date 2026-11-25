"""Three displays chosen by the user on 2026-11-25 after the reliability debate: each sale beside the same money in the index
fund, the shape of the top fifth by score, and ranges and risk before the score cards.  None reads a return of the forward
record, and none changes a score, a plan or a rule."""
from pathlib import Path

import pytest

from terminal import analyst_extra as ax, journal_yardstick as jy

ROOT = Path(__file__).resolve().parents[1]


def fund(prices, start_day=1):
    return [{"date": f"2026-12-{start_day + k:02d}", "close": p} for k, p in enumerate(prices)]


def sale(ticker, opened, date, avg, price, qty=10.0, fee=0.0):
    return {"date": date, "ticker": ticker, "qty": qty, "price": price, "avg_cost": avg, "pnl": (price - avg) * qty - fee, "return_pct": (price / avg - 1) * 100,
            "opened": opened, "style": "SWING", "hold_days": 3}


def test_each_sale_stands_beside_the_same_money_in_the_index_fund():
    bars = fund([100.0, 102.0, 101.0, 110.0, 99.0])                    # 12-01 .. 12-05
    marked = jy.mark([sale("AAA", "2026-12-01", "2026-12-04", 50.0, 60.0), sale("BBB", "2026-12-02", "2026-12-05", 20.0, 21.0)], bars)
    a, b = marked
    assert a["index_return_pct"] == pytest.approx(10.0) and a["vs_index_pct"] == pytest.approx(10.0) and a["index_pnl"] == pytest.approx(50.0) and a["vs_index_pnl"] == pytest.approx(50.0)
    assert b["index_return_pct"] == pytest.approx((99 / 102 - 1) * 100) and b["vs_index_pnl"] == pytest.approx(10.0 - 200.0 * (99 / 102 - 1))
    s = jy.summary(marked, "SPY")
    assert s["fund"] == "SPY" and s["count"] == 2 and s["compared"] == 2 and s["ahead"] == 2 and s["small_sample"] is True and s["vs_index_pnl"] == pytest.approx(a["vs_index_pnl"] + b["vs_index_pnl"])
    assert "통계 판정이 아닙니다" in s["note"] and "우연" in s["note"] and "배당" in s["note"]


def test_a_sale_the_fund_has_no_price_for_is_left_empty_never_zero():
    bars = fund([100.0, 101.0], start_day=3)                           # the fund's first bar is 12-03
    early, late, weekend = jy.mark([sale("AAA", "2026-12-01", "2026-12-04", 10.0, 11.0), sale("BBB", "2026-12-03", "2026-12-09", 10.0, 11.0),
                                    sale("CCC", "2026-12-03", "2026-12-04", 10.0, 9.0)], bars)
    assert early["vs_index_pnl"] is None and early["index_return_pct"] is None           # opened before the fund's first bar
    assert late["vs_index_pnl"] is None                                                    # sold after its last bar: not carried forward
    assert weekend["index_return_pct"] == pytest.approx(1.0) and weekend["vs_index_pct"] == pytest.approx(-11.0)
    s = jy.summary([early, late, weekend], "KODEX 200")
    assert s["count"] == 3 and s["compared"] == 1 and s["ahead"] == 0 and jy.summary([early], "x")["vs_index_pnl"] is None and jy.mark([sale("A", "2026-12-01", "2026-12-02", 1.0, 1.0)], [])[0]["index_pnl"] is None
    src = (ROOT / "terminal" / "services.py").read_text(encoding="utf-8")
    assert 'marked = jy.mark(state["closed"], hist.get(bench) or [])' in src and '"yardstick": {**jy.summary(marked, bench_name), "trades": marked[::-1][:50]}' in src
    js = (ROOT / "terminal" / "static" / "portfolio.js").read_text(encoding="utf-8")
    assert "function pfYardstick(y)" in js and 'yard.innerHTML = pfYardstick(d.yardstick);' in js and '<div id="eq-yard"></div>' in js


def snap(k, n=50, strategy="SWING", **more):
    """Stock k of n: the higher the score, the calmer and the nearer its high."""
    return {"ticker": f"T{k:02d}", "strategy": strategy, "score": 30.0 + k, "actionability": "ACTIONABLE",
            "factors": [{"factor": "atr_risk", "raw": {"hist_vol": 0.60 - 0.008 * k}}, {"factor": "breakout_volume", "raw": {"dist_high": -0.30 + 0.006 * k}}], **more}


def test_the_top_fifth_is_described_by_its_shape_from_recorded_factor_values():
    snaps = [snap(k) for k in range(50)] + [snap(5, strategy="LONG_TERM"), {**snap(49), "score": None}, snap(48, actionability="INSUFFICIENT_DATA")]
    t = ax.tilt(snaps)
    assert t["n"] == 50 and t["top_n"] == 10 and t["vol_top"] == pytest.approx(0.60 - 0.008 * 44.5) and t["vol_all"] == pytest.approx(0.60 - 0.008 * 24.5)
    assert t["near_high_top"] == pytest.approx(0.8) and t["near_high_all"] == pytest.approx(8 / 50)       # k >= 42: within five percent of the high
    line = ax.tilt_line(t)
    assert line.startswith("스윙 점수 상위 5분의 1(10종목)의 모양: 최근 변동성(연 환산)의 중앙값 24%(스캔 전체 40%), 52주 고점에서 5% 안에 있는 종목 80%(전체 16%).")
    assert "'더 오를 종목'이 아니라" in line and "근거는 아직 확인되지 않았습니다" in line and "덜 흔들렸" not in line
    assert ax.tilt(snaps[:20]) is None and ax.tilt_line(None) is None                                     # too few scored stocks: nothing is said
    bare = [{**snap(k), "factors": []} for k in range(50)]
    assert ax.tilt_line(ax.tilt(bare)) is None                                                            # no recorded values: no line, never a zero
    src = (ROOT / "terminal" / "assistant.py").read_text(encoding="utf-8")
    assert 'part("mix", tilt)' in src and "ax.tilt_line(ax.tilt(_snaps(terminal, market, session)))" in src


def test_ranges_and_risk_come_before_the_score_cards():
    qsf = (ROOT / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")
    first, cards = qsf.index('qsfFold("range-first"'), qsf.index('<div class="qsf-cards">${Object.values(d.cards)')
    assert first < cards and "방향이 아니라 흔들림의 크기였습니다" in qsf and "회피 표시는 판정 전 참고입니다" in qsf
    assert qsf.count('id="qsffc"') == 1 and 'qsfFold("range",' not in qsf
    asst = (ROOT / "terminal" / "static" / "assistant.js").read_text(encoding="utf-8")
    assert "점수 순서는 수익 순서가 아닙니다. 종목을 누르면 가격 범위와 위험이 점수 카드보다 먼저 나옵니다." in asst
