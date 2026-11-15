"""Forecast layer FC-2: closes are what count, nothing after the day is read, the table comes from past paths, the check is run once."""
import json

import numpy as np
import pytest

from terminal.qsf import forecast as fc, forecast_touch as ft


def walk(days=700, stocks=60, vol=0.02, seed=3, drift=0.0):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(drift, vol, size=(days, stocks)), axis=0))


def test_the_furthest_close_each_way_is_read_and_a_path_without_a_close_has_none():
    path = np.log(np.array([[101.0, 97.0, 104.0], [np.nan, np.nan, np.nan], [102.0, np.nan, 103.0]]))
    below, above = ft._extremes(path, np.log(np.array([100.0, 100.0, 100.0])))
    assert below[0] == pytest.approx(-np.log(0.97)) and above[0] == pytest.approx(np.log(1.04))
    assert np.isnan(below[1]) and np.isnan(above[1])
    assert below[2] == pytest.approx(-np.log(1.02)) and below[2] < 0            # never closed under the start: a negative distance, so no level below is reached


def test_only_closes_inside_the_horizon_count_and_a_stock_that_stops_trading_is_read_to_its_last_close():
    adj = np.array([[100.0, 100.0, 100.0], [95.0, 101.0, np.nan], [99.0, np.nan, np.nan], [80.0, np.nan, np.nan]])
    below, above = ft.reached(adj, 0, np.arange(3), 2)
    assert below[0] == pytest.approx(-np.log(0.95)) and above[0] == pytest.approx(np.log(0.99))        # the 80 is outside the two sessions
    assert above[1] == pytest.approx(np.log(1.01)) and np.isnan(below[2]) and np.isnan(above[2])
    real, ok = ft.shares(below, np.array([0.05, 0.05, 0.05]))
    assert list(ok) == [True, True, False] and real[0] == 0.5 and real[3] == 0.5 and real[4] == 0.0     # 5.1% down is 1.03 volatilities: reaches 1.0, not 1.5


def test_the_table_reads_nothing_after_the_day():
    adj = walk()
    i, cols = 600, np.arange(60)
    a = ft.day_touch(adj, i, cols)
    later = adj.copy()
    later[i + 1:] *= 3.0
    b = ft.day_touch(later, i, cols)
    assert a["table"] == b["table"] and all(np.array_equal(a["vol"][h], b["vol"][h], equal_nan=True) for h in fc.HORIZONS)
    assert all(np.array_equal(a["vol"][h], fc.day_forecast(adj, i, cols)["vol"][h], equal_nan=True) for h in fc.HORIZONS)       # FC-1's own volatility


def test_the_table_comes_from_past_paths_and_falls_as_the_level_moves_away():
    t = ft.day_touch(walk(), 600, np.arange(60))["table"][20]
    assert t["source"] == "EMPIRICAL" and t["pool"] >= fc.MIN_POOL
    for side in ft.SIDES:
        assert all(a > b for a, b in zip(t[side], t[side][1:]))
        assert all(p < ft.normal_touch(d) for p, d in zip(t[side], ft.GRID))        # closes only: fewer touches than a walk watched all the time
        assert 0.2 < t[side][3] < ft.normal_touch(1.0)


def test_too_few_past_paths_use_the_formula_and_say_so():
    t = ft.day_touch(walk(days=200, stocks=5), 199, np.arange(5))["table"][5]
    assert t["source"] == "NORMAL" and t["pool"] < fc.MIN_POOL and t["down"] == [ft.normal_touch(d) for d in ft.GRID] == t["up"]
    assert ft.normal_touch(0.0) == pytest.approx(1.0) and ft.normal_touch(1.0) == pytest.approx(0.3173, abs=1e-4)


def test_a_steady_random_walk_passes_every_check():
    adj = walk(days=900, seed=11)
    out = ft.evaluate(adj, [f"d{n:04d}" for n in range(900)], lambda i: np.arange(60))
    assert out["verdict"] == "TOUCH_CALIBRATED" and out["failed"] == [] and out["days"] > 60
    cell = out["horizons"]["20"]["down"][3]
    assert cell["distance"] == 1.0 and cell["pass"] and abs(cell["gap"]["all"]) < 0.03 and cell["normal_gap"] < 0 and len(cell["by_vol"]) == 3


def test_a_market_that_turns_wilder_than_its_past_fails_and_the_failures_are_listed():
    adj = walk(days=900, seed=11)
    rng = np.random.default_rng(5)
    for start in range(480, 900, 40):                       # bursts of five sessions, each four times as volatile as the rest
        adj[start + 5:] *= np.exp(np.cumsum(rng.normal(0, 0.08, size=(5, 60)), axis=0))[-1]
        adj[start:start + 5] *= np.exp(np.cumsum(rng.normal(0, 0.08, size=(5, 60)), axis=0))
    out = ft.evaluate(adj, [f"d{n:04d}" for n in range(900)], lambda i: np.arange(60))
    assert out["verdict"] == "TOUCH_NOT_CALIBRATED" and out["failed"]
    f = out["failed"][0]
    assert set(f) == {"horizon", "side", "distance", "part", "gap", "tolerance"} and abs(f["gap"]) > f["tolerance"]


def day(gap, date="2020-01-02"):
    cell = {"n": 100, "forecast": [0.5] * 6, "real": [0.5 + gap] * 6, "by_vol": [[0.5] * 6] * 3}
    return {"date": date, "stocks": 100, "5": {"source": "EMPIRICAL", "down": cell, "up": cell}, "20": {"source": "EMPIRICAL", "down": cell, "up": cell}}


def test_the_allowed_gap_narrows_with_distance_and_each_half_must_hold():
    assert ft.summarize([day(0.04), day(0.04)])["failed"] and ft.summarize([day(0.019), day(0.019)])["verdict"] == "TOUCH_CALIBRATED"
    failed = ft.summarize([day(0.04), day(0.04)])["failed"]
    assert {f["distance"] for f in failed} == {1.5, 2.0} and len(failed) == 2 * 2 * 2 * 3
    halves = ft.summarize([day(0.2), day(-0.2)])                    # the two halves cancel in the average
    assert halves["verdict"] == "TOUCH_NOT_CALIBRATED" and {f["part"] for f in halves["failed"]} == {"early", "late"}
    assert ft.summarize([])["verdict"] == "TOUCH_NOT_CALIBRATED"


def test_the_check_is_stored_and_not_run_again(tmp_path):
    adj = walk(days=560, seed=2)
    loaders = lambda base: {"US": (adj, [f"d{n:04d}" for n in range(560)], lambda i: np.arange(60))}      # noqa: E731
    first = ft.run_once(tmp_path, log=lambda *_: None, loaders=loaders)
    assert first["status"] == "REAL" and first["version"] == "FC-2" and first["settings"]["basis"] == "close"
    again = ft.run_once(tmp_path, log=lambda *_: None, loaders=lambda base: pytest.fail("the check ran twice"))
    assert again["status"] == "ALREADY_RUN" and again["markets"] == json.loads((tmp_path / ft.REPORT).read_text(encoding="utf-8"))["markets"]
    assert ft.check_result(tmp_path)["markets"]["US"]["days"] == first["markets"]["US"]["days"] and ft.check_result(tmp_path / "none") is None


def test_a_stored_table_is_read_between_grid_points_and_not_beyond_them():
    f = ft.day_touch(walk(), 600, np.arange(60))
    doc = ft.table_doc(f)
    assert doc["version"] == "FC-2" and doc["basis"] == "close" and doc["grid"] == list(ft.GRID) and set(doc["horizons"]) == {"5", "20"}
    p = doc["horizons"]["20"]["down"]
    assert ft.at_distance(doc, 20, "down", 1.0) == pytest.approx(p[3]) and ft.at_distance(doc, 20, "down", 1.25) == pytest.approx((p[3] + p[4]) / 2)
    assert ft.at_distance(doc, 20, "down", 0.1) is None and ft.at_distance(doc, 20, "up", 2.5) is None and ft.at_distance(doc, 20, "up", float("nan")) is None and ft.at_distance(doc, 20, "up", None) is None


def test_a_recorded_day_is_scored_from_its_own_table_and_read_once_at_the_fixed_count(monkeypatch):
    adj = walk(days=700, seed=4)
    i, cols = 600, np.arange(60)
    f = ft.day_touch(adj, i, cols)
    rows = [{"ticker": f"S{j}", "vol": {str(h): float(f["vol"][h][j]) for h in fc.HORIZONS}} for j in range(60)]
    doc = {"session": "2026-11-16", "touch": ft.table_doc(f)}
    got = ft.follow_day(doc, adj, i, cols, rows, 20)
    assert got["session"] == "2026-11-16" and got["down"]["n"] == 60 and got["down"]["forecast"] == doc["touch"]["horizons"]["20"]["down"] and len(got["up"]["real"]) == 6
    assert ft.follow_day({"session": "2026-11-13"}, adj, i, cols, rows, 20) is None           # a day recorded before FC-2 has no table
    monkeypatch.setattr(fc, "READ_AT", 3)
    days = [{"session": f"s{n}", "down": {"forecast": [0.5] * 6, "real": [0.5 + g] * 6}, "up": {"forecast": [0.5] * 6, "real": [0.5] * 6}} for n, g in enumerate((0.0, 0.01, 0.0, 0.3))]
    two, four = ft.read(days[:2]), ft.read(days)
    assert two["matured"] == 2 and two["reading"] is None and two["down"][0]["real"] == pytest.approx(0.505)
    assert four["reading"]["days"] == 3 and four["reading"]["last"] == "s2" and four["reading"]["verdict"] == "TOUCH_CALIBRATED"          # the fourth day is not in the reading
    assert four["down"][0]["pass"] is False and ft.read([]) == {"matured": 0, "first": None, "last": None, "read_at": 3, "reading": None}


def test_the_table_rides_in_the_daily_record_from_its_first_day_and_the_earlier_day_is_left_as_written(tmp_path, monkeypatch):
    from terminal.qsf import kr_forward as kf
    from tests.test_forecast import recorded
    recorded(tmp_path, monkeypatch)
    old, new = (kf._read_day(tmp_path / fc.FOLDERS["US"], d) for d in ("2026-11-13", "2026-11-16"))
    assert "touch" not in old and new["touch"]["version"] == "FC-2" and new["touch"]["grid"] == list(ft.GRID) and new["version"] == "FC-1"
    t = new["touch"]["horizons"]["20"]
    assert t["source"] == "EMPIRICAL" and t["pool"] == new["k"]["20"]["pool"] and len(t["down"]) == len(t["up"]) == 6 and 0 < t["down"][5] < t["down"][0] < 1
    assert kf.verify(tmp_path, fc.FOLDERS["US"])["status"] == "OK"


def test_the_status_carries_the_rule_the_stored_check_and_the_running_figures(tmp_path, monkeypatch):
    from tests.test_forecast import recorded
    bars = recorded(tmp_path, monkeypatch)
    (tmp_path / ft.REPORT).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / ft.REPORT).write_text(json.dumps({"markets": {"US": {"verdict": "TOUCH_CALIBRATED", "days": 9, "failed": [], "horizons": {}}}}), encoding="utf-8")
    view = fc.write_status(tmp_path, {"US": lambda t: bars.get(t) or []})
    assert view["touch"]["version"] == "FC-2" and view["touch"]["first"] == "2026-11-16" and view["touch"]["basis"] == "close" and view["touch"]["tolerance"]["2.0"] == 0.02
    us = view["markets"]["US"]
    assert us["touch_test"] == {"verdict": "TOUCH_CALIBRATED", "days": 9, "first": None, "last": None, "mean_stocks": None, "horizons": {}, "failed": []}
    assert us["today"]["touch"]["grid"] == list(ft.GRID) and us["today"]["session"] == "2026-11-16"
    five = us["followed"]["touch"]["5"]
    assert us["followed"]["touch"]["20"]["matured"] == 0 and five["reading"] is None and five["read_at"] == 240
    assert five["matured"] == 0 or (five["first"] == "2026-11-16" and len(five["down"]) == 6)           # the day before FC-2 is never scored for touches


def test_the_fixed_numbers_are_the_protocol_s():
    text = open(ft.PROTOCOL, encoding="utf-8").read()
    assert ft.GRID == (0.25, 0.5, 0.75, 1.0, 1.5, 2.0) and ft.TOLERANCE == {0.25: 0.05, 0.5: 0.05, 0.75: 0.05, 1.0: 0.05, 1.5: 0.03, 2.0: 0.02}
    assert ft.FIRST == "2026-11-16" and ft.CROWDED == 2.0 and str(ft.REPORT) == "reports/qsf/QSF_FORECAST_TOUCH_TEST.json"
    for words in ("0.25, 0.5, 0.75, 1.0, 1.5, 2.0", "| ±5 | ±5 | ±5 | ±5 | ±3 | ±2 |", "2026-11-16", "20,000개 미만", "종가 기준", "240개", "QSF_FORECAST_TOUCH_TEST.json", "예측의 2배"):
        assert words in text, words


def test_the_screen_gets_the_stored_table_the_stocks_volatility_and_the_stored_check(tmp_path, monkeypatch):
    from terminal.qsf import kr_forward as kf
    from tests.test_forecast import recorded
    recorded(tmp_path, monkeypatch)
    doc = kf._read_day(tmp_path / fc.FOLDERS["US"], "2026-11-16")
    row = next(r for r in doc["rows"] if r["ticker"] == "T010")
    got = fc.stock(tmp_path, "US", "T010")
    assert got["ranges"]["20"]["vol"] == row["vol"]["20"] and got["ranges"]["5"]["vol"] == row["vol"]["5"]
    t = got["touch"]
    assert t["version"] == "FC-2" and t["basis"] == "close" and t["first"] == "2026-11-16" and t["grid"] == list(ft.GRID) and t["table"] == doc["touch"]
    assert t["test"] is None and "종가 기준" in t["note"] and t["limits"] == ft.LIMITS and t["tolerance"]["1.5"] == 0.03
    adj = walk(days=560, seed=2)
    ft.run_once(tmp_path, log=lambda *_: None, loaders=lambda base: {"US": (adj, [f"d{n:04d}" for n in range(560)], lambda i: np.arange(60))})
    cells = fc.stock(tmp_path, "US", "T010")["touch"]["test"]["horizons"]["20"]["down"]
    assert [c["distance"] for c in cells] == list(ft.GRID) and set(cells[0]) == {"distance", "forecast", "real", "gap", "tolerance", "pass", "by_vol", "crowded_share", "worst_year"}
    assert len(cells[0]["by_vol"]) == 3 and fc.stock(tmp_path, "KR", "005930")["status"] == "NO_RECORD"


def test_a_day_recorded_before_the_table_shows_no_probability_rather_than_a_made_up_one(tmp_path, monkeypatch):
    from tests.test_forecast import recorded
    bars = recorded(tmp_path, monkeypatch, days_in=("2026-11-13",))
    got = fc.stock(tmp_path, "US", "T010")
    assert got["status"] == "REAL" and got["session"] == "2026-11-13" and got["touch"]["table"] is None and got["touch"]["first"] == "2026-11-16"
    fc.write_status(tmp_path, {"US": lambda t: bars.get(t) or []})
    view = fc.view(tmp_path, "US")
    assert view["touch"]["table"] is None and view["touch"]["grid"] == list(ft.GRID) and view["followed"]["touch"]["20"]["matured"] == 0


def test_the_screen_says_what_the_number_is_and_is_not():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "terminal" / "static" / "forecast.js").read_text(encoding="utf-8")
    for text in ("fcTouchLines(d, levels)", "가까워서 대부분 닿음", "멀어서 표 밖", "이미 기준을 지남", "비워 둔 것이며 0이 아닙니다", "어느 쪽에 먼저 닿는지는 계산하지 않습니다",
                 "점수와 무관합니다", "주문 계획은 이 숫자로 바뀌지 않습니다", "과거 점검 미달", "예측 → 실제", "esc(t.note)"):
        assert text in js, text
    assert "종가 기준" in ft.NOTE and "오를지 내릴지는 말하지 않습니다" in ft.NOTE and "장중" in ft.NOTE
