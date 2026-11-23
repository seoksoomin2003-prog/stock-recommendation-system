"""The chart-analysis tab (CHART-1, 2026-11-23): classic indicators and signals, reference only and never part of a score."""
import json
import math
import re
from pathlib import Path

import pytest

from terminal import chart_analysis as ca
from terminal import server
from terminal.services import Terminal
from tests.test_terminal_1 import AFTER, bars, fake_src

ROOT = Path(__file__).resolve().parents[1]


def rows_from(closes, vols=None, opens=None):
    out = []
    for i, c in enumerate(closes):
        o = opens[i] if opens else c
        out.append({"date": f"2026-01-{i + 1:03d}", "open": o, "high": max(o, c) + 1, "low": min(o, c) - 1, "close": c,
                    "volume": (vols[i] if vols else 1000.0)})
    return out


def test_sma_and_ema_use_the_chart_conventions():
    assert ca.sma([1, 2, 3, 4, None, 6], 3) == [None, None, 2.0, 3.0, None, None]             # a missing value is never read as 0
    assert ca.ema([1.0, 2.0, 3.0, 4.0, 5.0], 3) == [None, None, 2.0, 3.0, 4.0]                  # seeded with the first simple average
    assert ca.ema([1.0, None, 2.0, 3.0, 4.0], 2) == [None, None, None, 2.5, 3.5]                # a gap restarts it from a new seed


def test_rsi_is_wilders_smoothing():
    closes = [10.0, 11.0, 10.0, 12.0, 11.0, 13.0]
    got = ca.rsi_wilder(closes, 3)
    g, lo = (1 + 0 + 2) / 3, (0 + 1 + 0) / 3                                                   # first averages: simple means of three changes
    assert got[:3] == [None, None, None] and got[3] == pytest.approx(100 - 100 / (1 + g / lo))
    g, lo = (g * 2 + 0) / 3, (lo * 2 + 1) / 3                                                   # then (prev * (n - 1) + x) / n
    assert got[4] == pytest.approx(100 - 100 / (1 + g / lo))
    g, lo = (g * 2 + 2) / 3, (lo * 2 + 0) / 3
    assert got[5] == pytest.approx(100 - 100 / (1 + g / lo))
    assert ca.rsi_wilder([1.0, 2.0, 3.0, 4.0], 3)[3] == 100.0 and ca.rsi_wilder([1.0, 2.0], 14) == [None, None]


def test_macd_bollinger_and_obv():
    closes = [100.0 + math.sin(i / 3) * 5 + i * 0.2 for i in range(80)]
    m = ca.macd(closes)
    fast, slow = ca.ema(closes, 12), ca.ema(closes, 26)
    assert m["macd"][24] is None and m["macd"][25] == pytest.approx(fast[25] - slow[25])
    assert m["signal"][32] is None and m["signal"][33] == pytest.approx(sum(m["macd"][25:34]) / 9)
    assert m["hist"][-1] == pytest.approx(m["macd"][-1] - m["signal"][-1])
    bb = ca.bollinger([float(i) for i in range(1, 21)])
    sd = math.sqrt((20 ** 2 - 1) / 12)                                                          # population deviation of 1..20
    assert bb["mid"][-1] == 10.5 and bb["upper"][-1] == pytest.approx(10.5 + 2 * sd) and bb["lower"][-1] == pytest.approx(10.5 - 2 * sd) and bb["upper"][18] is None
    assert ca.obv([10.0, 11.0, 11.0, 10.0, 12.0], [5.0, 7.0, 9.0, None, 4.0]) == [0.0, 7.0, 7.0, None, 11.0]


def test_signals_mark_the_day_a_condition_starts():
    closes = [100.0] * 70 + [100.0 - i for i in range(1, 31)] + [70.0 + 2 * i for i in range(1, 61)]
    vols = [1000.0] * len(closes)
    vols[120] = 5000.0
    out = ca.analyse(rows_from(closes, vols), "KR", 1000, [20, 60])
    kinds = [s["kind"] for s in out["signals"]]
    assert kinds.count("DEAD_CROSS") == 1 and kinds.count("GOLDEN_CROSS") == 1
    assert [s["i"] for s in out["signals"] if s["kind"] == "DEAD_CROSS"] < [s["i"] for s in out["signals"] if s["kind"] == "GOLDEN_CROSS"]
    assert kinds.count("RSI_OVERSOLD") == 1 and kinds.count("RSI_OVERBOUGHT") == 1                # entering the zone, not every day in it
    spike = [s for s in out["signals"] if s["kind"] == "VOLUME_SPIKE"]
    assert [s["i"] for s in spike] == [120] and spike[0]["side"] == "up"                         # the close rose from the day before
    g = next(s for s in out["signals"] if s["kind"] == "GOLDEN_CROSS")
    assert out["bars"][g["i"]]["ma"]["20"] > out["bars"][g["i"]]["ma"]["60"] and out["bars"][g["i"] - 1]["ma"]["20"] <= out["bars"][g["i"] - 1]["ma"]["60"]
    assert all(set(s) >= {"date", "kind", "side", "label", "text", "close"} for s in out["signals"])


def test_the_range_is_cut_after_the_whole_history_is_computed():
    closes = [100.0 + i for i in range(300)]
    out = ca.analyse(rows_from(closes), "US", 63, [20, 50, 200])
    assert len(out["bars"]) == 63 and out["bars"][0]["ma"]["200"] is not None                   # the first bar of the range is not warming up
    assert out["bars"][-1]["ma"]["20"] == pytest.approx(sum(closes[-20:]) / 20) and out["cross_pair"] == [50, 200]
    assert all(0 <= s["i"] < 63 for s in out["signals"])


def test_missing_values_stay_missing():
    rows = rows_from([100.0 + i for i in range(40)])
    for r in rows[-5:]:
        r["volume"] = None
        r["high"] = None
    rows.append({"date": "2026-02-30", "close": None})
    out = ca.analyse(rows, "US", 252, [20])
    last = out["bars"][-1]
    assert len(out["bars"]) == 40 and last["volume"] is None and last["obv"] is None and last["high"] is None and last["vol_avg"] is None
    assert "VOLUME_SPIKE" not in {s["kind"] for s in out["signals"]}
    assert any(line["name"] == "거래량" and "자료가 없어" in line["text"] for line in out["lines"])
    assert ca.analyse([{"date": "2026-01-01", "close": 1.0}], "US", 63, [20])["status"] == "UNAVAILABLE"
    assert "NaN" not in json.dumps(out)


def test_moving_average_choices_and_defaults_by_market():
    assert ca.ma_periods("", "KR") == [5, 20, 60, 120] and ca.ma_periods("", "US") == [20, 50, 200]
    assert ca.ma_periods("200,7,20,abc,20", "US") == [20, 200] and ca.ma_periods("x", "KR") == [5, 20, 60, 120]
    assert ca.ma_periods("5,10,20,50,60,120,200", "US") == [5, 10, 20, 50, 60]                  # at most MA_MAX
    s = ca.settings()
    assert s["rsi"]["method"] == "WILDER" and s["ma_default"]["KR"] == [5, 20, 60, 120] and set(s["ranges"]) == set(ca.RANGES) and "검증" in s["caveat"]


def test_the_lines_say_what_the_custom_reads_and_that_it_is_untested():
    closes = [100.0 + i for i in range(260)]
    out = ca.analyse(rows_from(closes), "KR", 252, [5, 20, 60, 120])
    text = {line["name"]: line["text"] for line in out["lines"]}
    assert set(text) == {"이동평균", "RSI", "MACD", "볼린저밴드", "거래량"}
    assert "정배열" in text["이동평균"] and "4/4개 위" in text["이동평균"] and "와일더" in text["RSI"] and "점수 카드" in text["RSI"]
    assert "IC 음수" in ca.CAVEAT and "매매 지시가 아닙니다" in ca.CAVEAT


def test_the_service_answers_stocks_and_indices(tmp_path):
    t = Terminal(tmp_path, src=fake_src(yahoo_history=lambda s, p: {s[0]: bars(300)}), now=lambda: AFTER)
    d = t.chart_analysis("aapl", "1y", "")
    assert d["ticker"] == "AAPL" and d["market"] == "US" and d["status"] == "REAL" and len(d["bars"]) == 252 and d["ma"] == [20, 50, 200]
    assert d["short_history"] is False and d["intraday"] is False and d["settings"]["rsi"]["method"] == "WILDER"
    k = t.chart_analysis("^KS11", "3mo", "5,20")
    assert k["market"] == "KR" and k["name"] == "코스피" and k["ma"] == [5, 20] and len(k["bars"]) == 63
    assert t.chart_analysis("AAPL", "10y")["short_history"] is True                              # 300 bars for a ten-year view
    with pytest.raises(ValueError):
        t.chart_analysis("AAPL", "2y")
    empty = Terminal(tmp_path / "e", src=fake_src(yahoo_history=lambda s, p: {}), now=lambda: AFTER)
    assert empty.chart_analysis("ZZZZ")["status"] == "UNAVAILABLE"


def test_a_korean_stock_uses_the_krx_copy_inside_its_window(tmp_path, monkeypatch):
    from terminal.qsf import kr_bars
    seen = []

    def rebuild(code, rows, pan):
        seen.append((code, pan))
        return [{**r, "close": r["close"] * 2} for r in rows], {"source": "KRX+YAHOO", "krx_last": "2026-11-03", "tail_days": 1}
    monkeypatch.setattr(kr_bars, "panel", lambda base, today: "PANEL")
    monkeypatch.setattr(kr_bars, "rebuild", rebuild)
    t = Terminal(tmp_path, src=fake_src(yahoo_history=lambda s, p: {s[0]: bars(300)}), now=lambda: AFTER)
    t._sym = lambda code: code + ".KS"                                    # the listed-company master is not asked in a test
    d = t.chart_analysis("005930", "1y")
    assert seen == [("005930", "PANEL")] and d["bars"][-1]["close"] == 2 * 399.0 and "한국 거래소 일별 시세" in d["source"] and "1일은 Yahoo" in d["source"]
    long_ = t.chart_analysis("005930", "5y")
    assert len(seen) == 1 and "3년 이상은 Yahoo" in long_["source"] and long_["bars"][-1]["close"] == 399.0          # outside the copy's window
    t.chart_analysis("^KS11", "1y")
    assert len(seen) == 1                                                                                          # an index keeps Yahoo
    monkeypatch.setattr(kr_bars, "rebuild", lambda code, rows, pan: (rows, {"source": "YAHOO", "reason": "KRX 일별 자료에 없는 종목"}))
    assert "KRX 일별 자료에 없는 종목" in t.chart_analysis("005930", "3mo")["source"]
    monkeypatch.setattr(kr_bars, "panel", lambda base, today: (_ for _ in ()).throw(OSError("/secret/path")))
    broken = t.chart_analysis("005930", "6mo")
    assert broken["status"] == "REAL" and "OSError" in broken["source"] and "secret" not in broken["source"]


def test_compare_adds_the_moving_correlation(tmp_path):
    t = Terminal(tmp_path, src=fake_src(yahoo_history=lambda s, p: {s[0]: bars(300, start=100.0 + 7 * len(s[0]))}), now=lambda: AFTER)
    d = t.compare("AAPL,MSFT,NVDA", "1y")
    assert d["rolling_base"] == "AAPL" and d["rolling_window"] == 60 and [r["ticker"] for r in d["rolling"]] == ["MSFT", "NVDA"]
    pts = d["rolling"][0]["points"]
    assert len(pts) == len(d["dates"]) and pts[59] is None and pts[60] is not None and -1.0001 <= pts[-1] <= 1.0001
    assert t.compare("AAPL,MSFT", "3mo")["rolling_window"] == 20 and t.compare("AAPL", "1y")["rolling"] == []


def test_the_route_is_a_read_and_the_score_never_imports_it(tmp_path):
    assert ("GET", "/api/chart/analysis") in server.routes(object())
    t = Terminal(tmp_path, src=fake_src(yahoo_history=lambda s, p: {s[0]: bars(300)}), now=lambda: AFTER)
    body = json.dumps(server.routes(t)[("GET", "/api/chart/analysis")]({"t": "AAPL", "range": "6mo", "ma": "20"}, None))
    assert "NaN" not in body and json.loads(body)["ma"] == [20]
    for p in (ROOT / "terminal" / "qsf").rglob("*.py"):
        assert "chart_analysis" not in p.read_text(encoding="utf-8"), p.name                     # reference only: never part of a score
    for p in (ROOT / "terminal" / "committee").rglob("*.py"):
        assert "chart_analysis" not in p.read_text(encoding="utf-8"), p.name


def test_the_page_has_the_chart_group_and_draws_from_the_servers_settings():
    html = (ROOT / "terminal" / "static" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "terminal" / "static" / "chart.js").read_text(encoding="utf-8")
    assert '<button type="button" data-group="chart">차트</button>' in html and '<button data-tab="chart" data-group="chart">차트분석</button>' in html
    assert '<button data-tab="compare" data-group="chart">비교</button>' in html and html.index("compare.js") < html.index("chart.js") < html.index("command.js")
    assert "RENDER.chart = renderChart;" in js and "errKo(e)" in js and not re.findall(r"\be\.message\b", js)
    assert "s.ma_choices" in js and "s.caveat" in js and "box.onpointermove" in js                    # numbers come from the server; a finger drag works
    assert 'const CHA_ON_PRICE = new Set(["GOLDEN_CROSS", "DEAD_CROSS", "BB_UPPER", "BB_LOWER"]);' in js                       # other signals sit on their own pane
    css = (ROOT / "terminal" / "static" / "style.css").read_text(encoding="utf-8")
    assert all(css.count(f"--ma{n}:") == 2 for n in ca.MA_CHOICES)                                  # light and dark (one dark block since UI batch 5)
    assert "chartWith(c.ticker)" in (ROOT / "terminal" / "static" / "app.js").read_text(encoding="utf-8")
