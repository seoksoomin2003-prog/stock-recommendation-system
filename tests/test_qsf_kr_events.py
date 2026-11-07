"""Korean filing events: first filings only, usable the day after receipt, no tie broken by code, the key not written, one run.  No network."""
import gzip
import io
import json
import zipfile
from datetime import date, timedelta

import numpy as np
import pytest

from terminal.qsf import config, research_kr as kr, research_kr_events as ke

KEY = "not-a-real-key-123"


@pytest.mark.parametrize("title,kind", [
    ("주요사항보고서(유상증자결정)", "financing"),
    ("주요사항보고서(전환사채권발행결정)", "financing"),
    ("주요사항보고서(신주인수권부사채권발행결정)", "financing"),
    ("주요사항보고서(유무상증자결정)", "financing"),
    ("주요사항보고서(자기주식취득결정)", "buyback"),
    ("주요사항보고서(자기주식취득신탁계약체결결정)", "buyback"),
    ("주요사항보고서 (유상증자결정)  ", "financing"),
    ("[기재정정]주요사항보고서(유상증자결정)", None),
    ("[첨부정정]주요사항보고서(전환사채권발행결정)", None),
    ("[연장결정]주요사항보고서(자기주식취득신탁계약체결결정)", None),
    ("주요사항보고서(자기주식취득신탁계약해지결정)", None),
    ("주요사항보고서(자기주식처분결정)", None),
    ("주요사항보고서(무상증자결정)", None),
    ("주요사항보고서(교환사채권발행결정)", None),
    ("주요사항보고서(유상증자결정)(종속회사의주요경영사항)", None),
    ("주요사항보고서(상각형조건부자본증권발행결정)", None),
    ("", None),
    (None, None),
])
def test_only_a_first_filing_of_the_named_decisions_counts(title, kind):
    assert ke.classify(title) == kind


def test_quarters_stay_within_three_months_and_stop_at_today():
    got = ke.quarters(2025, date(2026, 11, 8))
    assert got[0] == ("2025Q1", "20250101", "20250331") and got[-1] == ("2026Q4", "20261001", "20261108") and len(got) == 8
    assert ke.quarters(2026, date(2026, 1, 5)) == [("2026Q1", "20260101", "20260105")]


def test_a_filing_is_not_usable_on_its_receipt_day():
    days = ["2020-03-10"]
    assert not ke.seen_within(days, "2019-03-10", "2020-03-10")
    assert ke.seen_within(days, "2019-03-10", "2020-03-11")
    assert ke.seen_within(days, "2020-03-10", "2020-03-11")          # the first day of the window counts
    assert not ke.seen_within(days, "2020-03-11", "2020-03-20")      # out of the window
    assert not ke.seen_within([], "2019-01-01", "2020-01-01")


def corp_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("CORPCODE.xml", "<result><list><corp_code>C1</corp_code><stock_code>000010</stock_code></list><list><corp_code>C2</corp_code><stock_code> </stock_code></list></result>".encode())
    return buf.getvalue()


class Reply:
    def __init__(self, body=None, content=b""):
        self.body, self.content = body, content

    def json(self):
        return self.body


def fake_get(pages, log=None):
    def get(url, params=None, timeout=None):
        if log is not None:
            log.append((url, dict(params)))
        if "corpCode" in url:
            return Reply(content=corp_zip())
        return Reply(pages(params))
    return get


def full(params):
    return {"status": "000", "total_page": 2, "list": [{"rcept_no": f"2026{params['page_no']:02d}01000001", "corp_code": "C1", "stock_code": "000010", "report_nm": "주요사항보고서(유상증자결정)", "flr_nm": "secret person"}]}


def test_download_walks_pages_keeps_only_needed_fields_and_never_writes_the_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENDART_API_KEY", KEY)
    calls = []
    res = ke.download(tmp_path, log=lambda _: None, get=fake_get(full, calls), sleep=lambda _: None, today=date(2016, 2, 1))
    assert res == {"status": "DONE", "calls": 2}
    assert [c[1].get("page_no") for c in calls if "list.json" in c[0]] == [1, 2]
    assert calls[1][1]["pblntf_detail_ty"] == "B001" and calls[1][1]["last_reprt_at"] == "N"
    root = tmp_path / ke.DATA
    with gzip.open(root / "2016Q1.json.gz", "rt", encoding="utf-8") as fh:
        rows = json.load(fh)
    assert rows[0] == ["20260101000001", "C1", "000010", "주요사항보고서(유상증자결정)"]
    for f in root.iterdir():
        data = gzip.open(f, "rb").read() if f.suffix == ".gz" else f.read_bytes()
        assert KEY.encode() not in data and "secret person".encode() not in data
    assert ke.download(tmp_path, log=lambda _: None, get=fake_get(full), sleep=lambda _: None, today=date(2016, 2, 1)) == {"status": "DONE", "calls": 0}


def test_download_without_a_key_does_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)
    assert ke.download(tmp_path) == {"status": "NO_KEY"}
    assert not (tmp_path / ke.DATA).exists()


def test_download_stops_on_the_daily_limit_and_stores_no_partial_quarter(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENDART_API_KEY", KEY)

    def pages(params):
        return full(params) if params["page_no"] == 1 else {"status": "020"}
    res = ke.download(tmp_path, log=lambda _: None, get=fake_get(pages), sleep=lambda _: None, today=date(2016, 2, 1))
    assert res["stopped"] == "DART_020" and not (tmp_path / ke.DATA / "2016Q1.json.gz").exists()


def test_download_error_never_carries_the_address(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENDART_API_KEY", KEY)
    logs = []

    def get(url, params=None, timeout=None):
        if "corpCode" in url:
            return Reply(content=corp_zip())
        raise RuntimeError(f"failed {url}?crtfc_key={params['crtfc_key']}")
    res = ke.download(tmp_path, log=logs.append, get=get, sleep=lambda _: None, today=date(2016, 2, 1))
    assert res["stopped"] == "TOO_MANY_FAILURES" and logs and all(KEY not in x for x in logs)


def test_load_events_sorts_days_finds_blank_codes_and_drops_amendments(tmp_path):
    (tmp_path / "corp.json").write_text(json.dumps({"C9": "000090"}), encoding="utf-8")
    with gzip.open(tmp_path / "2020Q1.json.gz", "wt", encoding="utf-8") as fh:
        json.dump([["20200305000001", "C1", "000010", "주요사항보고서(유상증자결정)"], ["20200105000001", "C1", "000010", "주요사항보고서(전환사채권발행결정)"],
                   ["20200110000001", "C1", "000010", "[기재정정]주요사항보고서(유상증자결정)"], ["20200201000001", "C9", "", "주요사항보고서(자기주식취득결정)"], ["20200201000002", "CX", "", "주요사항보고서(자기주식취득결정)"]], fh)
    got = ke.load_events(tmp_path)
    assert got == {"000010": {"financing": ["2020-01-05", "2020-03-05"]}, "000090": {"buyback": ["2020-02-01"]}}


def small_prices(stocks=40, sessions=400, start=date(2018, 1, 1)):
    days, d = [], start
    while len(days) < sessions:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d += timedelta(days=1)
    syms = [f"{k:05d}0" for k in range(stocks)] + [kr.MARKET]
    shape = (sessions, len(syms))
    base = 100 + np.arange(sessions)[:, None] * (1 + np.arange(len(syms))[None, :] * 0.01)
    z = {"dates": np.array(days), "symbols": np.array(syms), "kospi": np.ones(len(syms), dtype=bool), "close": base.copy(), "adj_close": base.copy(), "open": base.copy(), "cap": base * 1e9,
         "value": np.full(shape, kr.MIN_VALUE * 2.0), "volume": np.full(shape, 1000.0), "watch": np.zeros(shape, dtype=bool)}
    return kr.KrPrices(z)


def test_features_mark_a_true_no_and_leave_ineligible_stocks_empty():
    px = small_prices()
    i = 300
    px.data["volume"][i, 3] = 0                     # not eligible that day
    on, day_before = px.dates[i], px.dates[i - 1]
    events = {px.symbols[0]: {"financing": [day_before]}, px.symbols[1]: {"buyback": [px.dates[i - 252]]}, px.symbols[2]: {"financing": [px.dates[i - 253]], "buyback": [on]}}
    t = ke.build_features(px, [i], events, log=lambda _: None)[0]
    assert t[0].tolist() == [1, 0] and t[1].tolist() == [0, 1]
    assert t[2].tolist() == [0, 0]                  # older than the window, and today's receipt is not usable yet
    assert t[4].tolist() == [0, 0] and np.isnan(t[3]).all() and np.isnan(t[px.col[kr.MARKET]]).all()


def test_nothing_is_built_before_the_reference_start():
    px = small_prices(start=date(2016, 6, 1))
    i = next(k for k, d in enumerate(px.dates) if d >= "2017-06-01")
    assert np.isnan(ke.build_features(px, [i], {}, log=lambda _: None)).all()


def test_score_has_three_tiers_and_keeps_empty_empty():
    t = np.array([[[1, 0], [0, 0], [0, 1], [1, 1], [np.nan, np.nan]]], dtype=np.float32)
    s = ke.score_of(t)[0]
    assert s[:4].tolist() == [0, 50, 100, 50] and np.isnan(s[4])


def test_tiers_are_counted_without_returns():
    px = small_prices()
    rows = [260, 270]
    t = np.full((2, len(px.symbols), 2), np.nan, dtype=np.float32)
    t[:, :40] = 0
    t[:, :4, 0] = 1
    t[:, 36:40, 1] = 1
    got = ke.tier_summary(t, rows, px)
    y = int(px.dates[260][:4])
    assert got[y]["eligible"] == 40 and got[y]["low"] == pytest.approx(0.1) and got[y]["high"] == pytest.approx(0.1) and got[y]["dates_with_empty_top"] == 0


def test_portfolios_use_fixed_sets_and_charge_cost_on_turnover():
    px = small_prices(sessions=380)
    rows = list(range(260, 340, kr.STEP))
    t = np.full((len(rows), len(px.symbols), 2), np.nan, dtype=np.float32)
    t[:, :40] = 0
    t[:, :10, 0] = 1
    t[:, 30:40, 1] = 1
    got = ke._portfolios(t, px, rows, px.dates[260], "2099", 0.0)
    assert got["all_equal"]["mean_holdings"] == 40 and got["no_financing"]["mean_holdings"] == 30 and got["financing"]["mean_holdings"] == 10 and got["buyback_clean"]["mean_holdings"] == 10
    assert got["buyback_clean"]["annual_net"] > got["financing"]["annual_net"]       # later symbols rise faster in this panel
    paid = ke._portfolios(t, px, rows, px.dates[260], "2099", 0.01)
    assert paid["buyback_clean"]["annual_net"] < got["buyback_clean"]["annual_net"]


def money(buy, none, every, market):
    return {"buyback_clean": {"annual_net": buy}, "no_financing": {"annual_net": none}, "all_equal": {"annual_net": every}, "cap_weighted_market": {"annual": market}}


def test_money_conditions_need_both_periods():
    good = money(0.2, 0.1, 0.05, 0.1)
    assert ke.money_conditions({"2022_2023": good, "2024_on": good}) == {"b1_buyback_beats_market": True, "b2_avoiding_financing_helps": True}
    bad = money(0.05, 0.01, 0.05, 0.1)
    assert ke.money_conditions({"2022_2023": good, "2024_on": bad}) == {"b1_buyback_beats_market": False, "b2_avoiding_financing_helps": False}


@pytest.mark.parametrize("v20,v252,b1,b2,want", [
    ("WEAK_POSITIVE_EVIDENCE", "WEAK_POSITIVE_EVIDENCE", True, True, "A_AND_B1"),
    ("WEAK_POSITIVE_EVIDENCE", "WEAK_POSITIVE_EVIDENCE", False, True, "A_AND_B2"),
    ("WEAK_POSITIVE_EVIDENCE", "WEAK_POSITIVE_EVIDENCE", False, False, "A_ONLY"),
    ("WEAK_POSITIVE_EVIDENCE", "NO_EVIDENCE", True, True, "NO_EVIDENCE"),
    ("NO_EVIDENCE", "WEAK_POSITIVE_EVIDENCE", True, True, "NO_EVIDENCE"),
])
def test_reading_is_fixed_in_advance(v20, v252, b1, b2, want):
    primary = {"SWING_20": {"verdict": v20}, "LONG_252": {"verdict": v252}}
    assert ke.reading(primary, {"b1_buyback_beats_market": b1, "b2_avoiding_financing_helps": b2}) == want


def test_a_second_run_is_refused_and_the_report_is_left_alone(tmp_path):
    target = tmp_path / ke.REPORT
    target.parent.mkdir(parents=True)
    target.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError):
        ke.run_once(tmp_path)
    assert target.read_text(encoding="utf-8") == "{}"


def test_the_test_reuses_the_korean_cost_and_horizons():
    assert ke.HORIZONS == {"SWING_20": 20, "LONG_252": 252} and config.round_trip_cost("KR") > 0


def planted_panel(tmp_path, monkeypatch, edge):
    """2018 to 2026 with a known effect: financing stocks lose ``edge`` a session and buyback stocks gain it.  No real data."""
    from terminal.qsf import research_kr_fund as kf
    rng = np.random.default_rng(7)
    sessions, stocks = 2300, 60
    px = small_prices(stocks=stocks, sessions=sessions)
    fin, buy = np.zeros(stocks, dtype=bool), np.zeros(stocks, dtype=bool)
    fin[:12], buy[48:] = True, True
    daily = rng.normal(0.0004, 0.02, (sessions, stocks + 1)) + rng.normal(0, 0.008, (sessions, 1))
    daily[:, :stocks] += edge * (buy.astype(float) - fin.astype(float))
    path = 100 * np.exp(np.cumsum(daily, axis=0))
    px.data["adj_close"], px.data["close"], px.data["open"] = path, path, path
    rows = list(range(260, sessions - 1, kr.STEP))
    tensor = np.full((len(rows), stocks + 1, 2), np.nan, dtype=np.float32)
    tensor[:, :stocks, 0], tensor[:, :stocks, 1] = fin, buy
    (tmp_path / ke.DATA).mkdir(parents=True)
    np.savez_compressed(tmp_path / ke.FEATURES, tensor=tensor)
    fund = rng.normal(size=(len(rows), stocks + 1, len(kf.SIGNALS))).astype(np.float32)
    fund[:, stocks] = np.nan
    (tmp_path / kf.FEATURES).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(tmp_path / kf.FEATURES, tensor=fund)
    top300 = np.ones((len(rows), stocks + 1), dtype=bool)
    monkeypatch.setattr(ke, "_inputs", lambda base: (px, rows, top300))
    return px


def test_the_whole_run_finds_a_planted_effect_and_writes_every_section(tmp_path, monkeypatch):
    planted_panel(tmp_path, monkeypatch, 0.002)
    out = ke.run_once(tmp_path, log=lambda _: None)
    assert out["reading"] == "A_AND_B1" and out["conditions"]["b2_avoiding_financing_helps"]
    primary = out["scores"]["EVENTS"]
    for s, h in ke.HORIZONS.items():
        assert primary[s]["horizon"] == h and primary[s]["ic"] > 0.02 and primary[s]["verdict"] == "WEAK_POSITIVE_EVIDENCE"
        assert primary[s]["tiers"]["100"]["excess"] > 0 > primary[s]["tiers"]["0"]["excess"]
        assert set(primary[s]["subsets"]) == {"kospi", "kosdaq", "top300"}
    assert set(out["scores"]) == {"EVENTS", "FINANCING", "BUYBACK", "FUND_ONLY", "FUND_WITH_EVENTS"}
    assert set(out["money_20d"]) == set(ke.PORTFOLIO_PERIODS) and out["money_20d"]["2022_on"]["buyback_clean"]["mean_holdings"] == 12
    assert json.loads((tmp_path / ke.REPORT).read_text(encoding="utf-8"))["reading"] == "A_AND_B1"
    with pytest.raises(RuntimeError):
        ke.run_once(tmp_path, log=lambda _: None)


def test_the_whole_run_finds_nothing_when_nothing_is_planted(tmp_path, monkeypatch):
    planted_panel(tmp_path, monkeypatch, 0.0)
    out = ke.run_once(tmp_path, log=lambda _: None)
    assert out["reading"] == "NO_EVIDENCE"
