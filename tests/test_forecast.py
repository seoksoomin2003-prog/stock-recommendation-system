"""The forecast layer FC-1 (reports/QSF_FORECAST_PROTOCOL.md): ranges, the one historical check, the daily record and its reading."""
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from terminal.qsf import forecast as fc, kr_forward as kf

ROOT = Path(__file__).resolve().parents[1]


def walk(days=700, stocks=80, vol=0.02, seed=0, tails=False):
    """Adjusted closes of independent random walks; ``tails`` draws fat-tailed days of the same variance."""
    rng = np.random.default_rng(seed)
    r = rng.standard_t(3, size=(days, stocks)) / math.sqrt(3) * vol if tails else rng.normal(0, vol, size=(days, stocks))
    return 100 * np.exp(np.cumsum(r, axis=0))


def test_the_variance_starts_as_the_mean_square_of_twenty_returns_and_skips_days_without_one():
    r = np.full((30, 2), 0.01)
    r[5, 1] = np.nan
    r[25, 0] = 0.05
    sig, cnt = fc.ewma_vol(r, 0.94)
    assert np.isnan(sig[18, 0]) and sig[19, 0] == pytest.approx(0.01) and cnt[19, 0] == 20
    assert np.isnan(sig[19, 1]) and sig[20, 1] == pytest.approx(0.01) and cnt[29, 1] == 29          # the gap delays the start by a day
    assert sig[25, 0] == pytest.approx(math.sqrt(0.94 * 1e-4 + 0.06 * 25e-4))
    assert sig[26, 0] == pytest.approx(math.sqrt(0.94 * (0.94 * 1e-4 + 0.06 * 25e-4) + 0.06 * 1e-4))


def test_a_forecast_reads_nothing_after_its_day_and_nothing_before_its_window():
    adj = walk(days=620)
    cols = np.arange(adj.shape[1])
    i = 560
    a = fc.day_forecast(adj, i, cols)
    later = adj.copy()
    later[i + 1:] *= 7.0
    later[:i - fc.WINDOW + 1] = np.nan
    b = fc.day_forecast(later, i, cols)
    for h in fc.HORIZONS:
        assert np.array_equal(a["vol"][h], b["vol"][h], equal_nan=True) and a["k"][h] == b["k"][h]
    moved = adj.copy()
    moved[i] *= 1.5                                         # the day itself is read
    assert not np.array_equal(a["vol"][5], fc.day_forecast(moved, i, cols)["vol"][5], equal_nan=True)


def test_the_width_comes_from_past_moves_and_a_small_pool_falls_back_to_the_normal_values():
    f = fc.day_forecast(walk(), 650, np.arange(80))
    for h in fc.HORIZONS:
        assert f["k"][h]["source"] == "EMPIRICAL" and f["k"][h]["pool"] >= fc.MIN_POOL
        assert f["k"][h][80] == pytest.approx(1.2816, abs=0.12) and f["k"][h][50] == pytest.approx(0.6745, abs=0.08)
        assert np.all(f["vol"][h] > 0) and np.median(f["vol"][h]) == pytest.approx(0.02 * math.sqrt(h), rel=0.15)
    fat = fc.day_forecast(walk(tails=True), 650, np.arange(80))
    assert fat["k"][5][50] < f["k"][5][50]                 # fat tails: the middle half is narrower than the normal curve says
    few = fc.day_forecast(walk(stocks=20), 650, np.arange(20))
    assert few["k"][20]["source"] == "NORMAL" and few["k"][20][80] == 1.2816 and few["k"][20]["pool"] < fc.MIN_POOL


def test_a_stock_with_too_little_history_or_no_close_gets_no_forecast_rather_than_a_zero():
    adj = walk(days=600, stocks=60)
    adj[:520, 0] = np.nan                                   # listed 80 sessions ago
    adj[599, 1] = np.nan                                    # no close on the day
    f = fc.day_forecast(adj, 599, np.arange(60))
    assert np.isnan(f["vol"][5][0]) and np.isnan(f["vol"][20][1]) and np.isfinite(f["vol"][5][2:]).all()


def test_the_outcome_ends_at_the_last_close_of_a_stock_that_stopped_trading():
    adj = np.full((30, 3), 100.0)
    adj[11:, 0] = 110.0
    adj[11:13, 1], adj[13:, 1] = 90.0, np.nan              # gone after two sessions
    adj[11:, 2] = np.nan                                    # no close at all inside the horizon
    move = fc.outcome(adj, 10, np.arange(3), 5)
    assert move[0] == pytest.approx(math.log(1.1)) and move[1] == pytest.approx(math.log(0.9)) and np.isnan(move[2])
    c = fc.cover(move, np.array([0.2, 0.05, 0.1]), 1.0)
    assert c == {"n": 2, "inside": 0.5, "above": 0.0, "below": 0.5}
    assert fc.cover(np.array([np.nan]), np.array([0.1]), 1.0) is None


def test_a_world_of_steady_random_walks_is_calibrated_and_the_check_starts_with_a_full_window():
    adj = walk(days=760, stocks=90, seed=3)
    dates = [f"D{n:04d}" for n in range(760)]
    assert fc.check_rows(760)[0] == fc.WINDOW - 1 and fc.check_rows(760)[-1] + fc.TEST_END_ROOM < 760 and fc.check_rows(480) == []
    got = fc.evaluate(adj, dates, lambda i: np.arange(90))
    assert got["verdict"] == "RANGE_CALIBRATED" and got["failed"] == [] and got["days"] == len(fc.check_rows(760))
    for h in ("5", "20"):
        x = got["horizons"][h]
        assert 0.75 <= x["cover80"]["all"] <= 0.85 and 0.45 <= x["cover50"]["all"] <= 0.55 and x["pass80"] and x["pass50"]
        assert x["above80"] + x["below80"] == pytest.approx(1 - x["cover80"]["all"]) and len(x["by_vol"]) == 3 and x["uncounted"] == 0
    assert fc.evaluate(adj, dates, lambda i: np.arange(10))["verdict"] == "RANGE_NOT_CALIBRATED"          # too few stocks: no day, no pass


def day(n, c80, c50):
    one = {"n": 100, "uncounted": 0, "cover80": c80, "above80": (1 - c80) / 2, "below80": (1 - c80) / 2, "cover50": c50, "normal80": c80, "normal50": c50, "k80": 1.3, "k50": 0.7,
           "source": "EMPIRICAL", "half_width": 0.1, "by_vol": [c80, c80, c80]}
    return {"date": f"{2020 + n // 4}-01-0{n % 4 + 1}", "stocks": 100, "5": dict(one), "20": dict(one)}


def test_one_half_outside_its_band_fails_and_is_named_with_its_value():
    good = fc.summarize([day(n, 0.80, 0.50) for n in range(8)])
    assert good["verdict"] == "RANGE_CALIBRATED"
    bad = fc.summarize([day(n, 0.80 if n < 4 else 0.70, 0.50) for n in range(8)])
    assert bad["verdict"] == "RANGE_NOT_CALIBRATED"
    assert {(f["horizon"], f["level"], f["part"]) for f in bad["failed"]} == {(5, 80, "late"), (20, 80, "late")} and bad["failed"][0]["value"] == pytest.approx(0.70)
    assert bad["horizons"]["5"]["cover80"]["all"] == pytest.approx(0.75) and bad["horizons"]["5"]["worst_year"]["year"] == "2021"
    edge = fc.summarize([day(n, 0.85, 0.45) for n in range(8)])
    assert edge["verdict"] == "RANGE_CALIBRATED"            # the band's ends are inside
    assert fc.summarize([])["verdict"] == "RANGE_NOT_CALIBRATED"


def test_the_check_is_written_once_and_a_second_call_computes_nothing(tmp_path):
    adj = walk(days=560, stocks=60, seed=5)
    calls = []

    def loaders(base):
        calls.append(1)
        return {"KR": (adj, [f"D{n:04d}" for n in range(560)], lambda i: np.arange(60))}
    doc = fc.run_once(tmp_path, log=lambda m: None, loaders=loaders)
    assert doc["status"] == "REAL" and doc["version"] == "FC-1" and doc["markets"]["KR"]["days"] > 0 and doc["settings"]["lambda"] == {"5": 0.94, "20": 0.97}
    again = fc.run_once(tmp_path, log=lambda m: None, loaders=loaders)
    assert again["status"] == "ALREADY_RUN" and len(calls) == 1 and again["markets"] == doc["markets"]
    assert fc.check_result(tmp_path)["status"] == "REAL" and fc.check_result(tmp_path / "nowhere") is None


def test_the_us_universe_asks_for_a_close_on_the_day_and_enough_closes_in_the_window():
    adj = np.full((600, 3), 50.0)
    adj[:400, 1] = np.nan                                   # 200 closes in the window
    adj[599, 2] = np.nan
    assert list(fc.us_universe(adj)(599)) == [0] and list(fc.us_universe(adj)(450)) == [0, 2]


def test_no_evidence_reads_as_zero_and_fifty_percent_and_the_assumed_value_stays_small():
    z = fc.z_scores(np.array([40.0, 50.0, 60.0, np.nan, 500.0]))
    assert np.isnan(z[3]) and z[4] <= fc.Z_CAP and z[0] < z[1] < z[2]
    assert np.isnan(fc.z_scores(np.array([50.0, 50.0, 50.0]))).all()
    none = fc.direction(2.0, 0.08, 0.0)
    assert none == {"p": 0.5, "alpha": 0.0}
    some = fc.direction(2.0, 0.08, fc.IC_ASSUMED)
    assert some["alpha"] == pytest.approx(0.03 * 0.08 * 2.0) and 0.52 < some["p"] < 0.53
    assert fc.direction(-2.0, None, fc.IC_ASSUMED)["alpha"] is None and fc.direction(-2.0, 0.08, fc.IC_ASSUMED)["p"] == pytest.approx(1 - some["p"])
    assert set(fc.IC_EVIDENCE.values()) == {0.0} and len(fc.IC_EVIDENCE) == 4


def sessions(last, n):
    days, d = [], date.fromisoformat(last)
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d -= timedelta(days=1)
    return days[::-1]


def world(last="2026-11-20", n=560, stocks=240, seed=7):
    """Bars by ticker up to ``last`` and a loader over them."""
    days, adj = sessions(last, n), walk(days=n, stocks=stocks, seed=seed)
    bars = {f"T{k:03d}": [{"date": d, "close": float(adj[j, k]) * 2, "adj_close": float(adj[j, k])} for j, d in enumerate(days)] for k in range(stocks)}
    return days, adj, bars


def snaps(session, n=240, market="US", price=None):
    out = []
    for k in range(n):
        for strategy in ("SWING", "LONG_TERM"):
            if strategy == "LONG_TERM" and k == 1:
                continue
            out.append({"ticker": f"T{k:03d}", "strategy": strategy, "score": 30.0 + k / 5 if strategy == "SWING" else 80.0 - k / 5, "data_date": session, "market": market,
                        "model_version": "QSF-1.3.2", "price": 10.0 + k if price is None else price})
    return out


def test_a_day_is_written_from_the_scans_prices_up_to_the_session_and_missing_history_stays_missing():
    days, adj, bars = world()
    session = days[-6]
    bars["T005"] = bars["T005"][-70:]                       # too short a history
    doc = fc.build_doc(session, "US", snaps(session), lambda t: bars.get(t) or [])
    assert doc["session"] == session and doc["version"] == "FC-1" and len(doc["rows"]) == 240 and doc["forecast"] == 239 and doc["sessions_read"] == 555
    assert doc["k"]["5"]["source"] == "EMPIRICAL" and doc["ic_evidence"] == {"SWING": 0.0, "LONG_TERM": 0.0} and doc["ic_assumed"] == 0.03
    rows = {r["ticker"]: r for r in doc["rows"]}
    assert rows["T005"]["vol"] == {"5": None, "20": None} and rows["T005"]["swing"]["omega"] is None and rows["T005"]["swing"]["alpha"] is None
    assert rows["T001"]["long"] is None and rows["T001"]["swing"]["p"] == 0.5 and rows["T001"]["swing"]["alpha"] == 0.0
    assert rows["T239"]["swing"]["z"] > 0 > rows["T239"]["long"]["z"] and rows["T239"]["swing"]["p_assumed"] > 0.5 > rows["T239"]["long"]["p_assumed"]
    assert rows["T239"]["swing"]["alpha_assumed"] > 0 and rows["T010"]["close"] == 20.0
    later = {t: [dict(b, adj_close=b["adj_close"] * 3) if b["date"] > session else b for b in v] for t, v in bars.items()}
    assert fc.build_doc(session, "US", snaps(session), lambda t: later.get(t) or [])["rows"] == doc["rows"]         # nothing after the session is read
    one = fc.stock_range(rows["T010"], doc)
    lo, hi = one["ranges"]["20"]["p80"]
    assert lo < 20.0 < hi and lo * hi == pytest.approx(400.0) and one["ranges"]["20"]["p50"][1] < hi and fc.stock_range(rows["T005"], doc)["ranges"]["5"] is None
    with pytest.raises(fc.NotReady, match="TOO_FEW_STOCKS"):
        fc.build_doc(session, "US", snaps(session, n=100), lambda t: bars.get(t) or [])
    with pytest.raises(fc.NotReady, match="PRICES_NOT_AT_SESSION"):
        fc.build_doc("2026-11-23", "US", snaps("2026-11-23"), lambda t: bars.get(t) or [])


class FakeLedger:
    days = []

    def __init__(self, base):
        pass

    def verify(self):
        return {"status": "OK"}

    def _live_rows(self):
        return [{"market": "US", "session": d} for d in self.days] + [{"market": "KR", "session": "2026-11-20"}]

    def _load(self, row):
        return snaps(row["session"], n=100 if row["session"] == "2026-11-17" else 240)


def test_the_record_starts_at_the_first_day_is_written_once_and_waits_for_prices(tmp_path, monkeypatch):
    monkeypatch.setattr(fc, "Ledger", FakeLedger)
    days, adj, bars = world(last="2026-11-19")
    loader = lambda t: bars.get(t) or []        # noqa: E731
    FakeLedger.days = ["2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18"]
    at = datetime(2026, 11, 19, 0, 0, tzinfo=timezone.utc)
    got = fc.record(tmp_path, "US", loader, now=lambda: at)
    assert got["status"] == "OK" and got["written"] == ["2026-11-13", "2026-11-16", "2026-11-18"] and got["waiting"] == {"session": "2026-11-17", "reason": "TOO_FEW_STOCKS"}
    again = fc.record(tmp_path, "US", loader, now=lambda: at)
    assert again["written"] == [] and again["sessions"] == 3
    FakeLedger.days = FakeLedger.days + ["2026-11-20"]
    late = fc.record(tmp_path, "US", loader, now=lambda: at)                # the prices have not reached the newest session
    assert late["status"] == "WAITING" and late["waiting"] == {"session": "2026-11-20", "reason": "PRICES_NOT_AT_SESSION"} and late["written"] == []
    idx = kf.read_index(tmp_path, fc.FOLDERS["US"])
    assert [r["session"] for r in idx] == ["2026-11-13", "2026-11-16", "2026-11-18"] and kf.verify(tmp_path, fc.FOLDERS["US"])["status"] == "OK"
    assert kf._read_day(tmp_path / fc.FOLDERS["US"], "2026-11-13")["late"] is True and not (tmp_path / fc.FOLDERS["KR"]).exists()
    view = fc.write_status(tmp_path, {"US": loader, "KR": loader})
    us = view["markets"]["US"]
    assert us["record"] == {"sessions": 3, "first": "2026-11-13", "last": "2026-11-18"} and us["today"]["session"] == "2026-11-18" and us["test"] is None
    assert us["today"]["half_width"]["20"]["p80_median"] > us["today"]["half_width"]["5"]["p80_median"] > us["today"]["half_width"]["5"]["p50_median"] > 0
    assert us["followed"]["ranges"]["5"]["matured"] == 0 and us["followed"]["ranges"]["5"]["reading"] is None
    assert view["markets"]["KR"]["record"]["sessions"] == 0 and "today" not in view["markets"]["KR"]
    assert fc.status(tmp_path)["markets"]["US"]["record"]["sessions"] == 3 and fc.status(tmp_path / "nowhere")["status"] == "NO_RECORD"


def test_ended_days_are_scored_against_their_own_range_and_the_reading_waits_for_240(monkeypatch):
    days, adj, bars = world(last="2026-11-20", n=560, stocks=240, seed=11)
    loader = lambda t: bars.get(t) or []        # noqa: E731
    tickers = sorted(bars)
    docs = [fc.build_doc(d, "US", snaps(d), loader) for d in days[-40:-30]]
    m, dates = fc.matrix(tickers, loader, first=docs[0]["session"])
    got = fc.follow(docs, m, dates, {t: j for j, t in enumerate(tickers)})
    assert dates[0] == docs[0]["session"] and got["ranges"]["5"]["matured"] == 10 and got["ranges"]["20"]["matured"] == 10
    assert 0.6 < got["ranges"]["20"]["cover80"] < 0.95 and 0.3 < got["ranges"]["5"]["cover50"] < 0.7 and got["ranges"]["5"]["reading"] is None
    assert got["ranges"]["5"]["stock_days"] == 2400 and got["ranges"]["5"]["uncounted"] == 0
    swing = got["direction"]["SWING"]
    assert swing["matured"] == 10 and swing["horizon"] == 20 and 0.3 < swing["high"] < 0.7 and swing["brier_half"] == pytest.approx(0.25, abs=0.001)
    assert got["direction"]["LONG_TERM"]["matured"] == 0                     # 63 sessions have not passed
    newest = fc.follow([fc.build_doc(days[-3], "US", snaps(days[-3]), loader)], m, dates, {t: j for j, t in enumerate(tickers)})
    assert newest["ranges"]["5"]["matured"] == 0 and newest["ranges"]["5"]["cover80"] is None
    monkeypatch.setattr(fc, "READ_AT", 8)
    read = fc.follow(docs, m, dates, {t: j for j, t in enumerate(tickers)})["ranges"]["20"]["reading"]
    assert read["days"] == 8 and read["first"] == docs[0]["session"] and read["last"] == docs[7]["session"] and read["verdict"] in ("RANGE_CALIBRATED", "RANGE_NOT_CALIBRATED")


def test_a_date_few_stocks_traded_on_is_not_a_session():
    bars = {f"T{k}": [{"date": "2026-11-12", "close": 10.0}, {"date": "2026-11-13", "close": 11.0, "adj_close": 5.5}] for k in range(10)}
    bars["T0"].append({"date": "2026-11-14", "close": 12.0})
    m, dates = fc.matrix(sorted(bars), lambda t: bars[t])
    assert dates == ["2026-11-12", "2026-11-13"] and m[1, 0] == 5.5 and m[0, 0] == 10.0
    assert fc.matrix(sorted(bars), lambda t: bars[t], last="2026-11-12")[1] == ["2026-11-12"]


def test_the_layer_is_recorded_in_both_daily_steps_backed_up_and_changes_no_score():
    from terminal import automation
    assert {"forecast_kr", "forecast_us"} <= set(automation.FORWARD_STORES) and sum("forecast_" in g for g in automation.BACKUP_GLOBS) == 2
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert app.count('_forecast_record("KR")') == 1 and app.count('_forecast_record("US")') == 1
    assert app.index('_paper_book_record("KR")') < app.index('_forecast_record("KR")') < app.index("lookahead.run(PROJECT_ROOT")
    src = (ROOT / "terminal" / "qsf" / "forecast.py").read_text(encoding="utf-8")
    assert "engine" not in src and "import config" not in src and "from terminal.qsf import config" not in src
    protocol = (ROOT / fc.PROTOCOL).read_text(encoding="utf-8")
    for text in ("480거래일", "0.94", "0.97", "20,000개", "1.2816", "0.6745", "75% 이상 85% 이하", "45% 이상 55% 이하", "2026-11-13", "0.03", "240개"):
        assert text in protocol
