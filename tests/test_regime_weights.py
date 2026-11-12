"""Walk-forward order and the regime-weight challenger (reports/QSF_REGIME_WEIGHTS_PROTOCOL.md).  All offline, made-up data."""
import json
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest

from terminal.qsf import config, kr_forward as kf, regime_weights as rw, walkforward as wf


# ---------------------------------------------------------------------- walk-forward
def test_a_day_learns_only_from_days_whose_outcome_had_ended():
    rows = [0, 21, 42, 50, 63, 84]
    assert wf.known(rows, 2, 20) == [0, 1] and wf.known(rows, 3, 20) == [0, 1]         # row 42's outcome ends at 62: not known at row 50
    assert wf.known(rows, 4, 20) == [0, 1, 2] and wf.known(rows, 4, 20, embargo=5) == [0, 1]
    seen = []
    out, log = wf.walk(rows, 20, 2, lambda train: list(train), lambda model, k: seen.append((k, model)) or len(model))
    assert out == {2: 2, 3: 2, 4: 3, 5: 5} and seen[0] == (2, [0, 1]) and wf.leak_free(log, 20)
    assert log[1] == {"test": 50, "train": 2, "last_train": 21, "gap": 29}
    assert not wf.leak_free([{"test": 50, "train": 3, "last_train": 42, "gap": 8}], 20)
    with pytest.raises(ValueError, match="ROWS_NOT_IN_ORDER"):
        wf.walk([0, 42, 21], 20, 1, list, lambda m, k: 0)


def test_the_fit_never_receives_the_test_day_or_a_later_one():
    rows = list(range(0, 21 * 40, 21))

    def fit(train):
        return max(train)
    out, log = wf.walk(rows, 20, 5, fit, lambda newest, k: newest < k)
    assert all(out.values()) and len(out) == 35 and log[0]["train"] == 5


# ---------------------------------------------------------------------- the market state
def index(n=900, drift=0.0005, vol=0.01, seed=0):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(drift + vol * rng.standard_normal(n)))


def test_the_state_reads_trend_and_volatility_and_nothing_after_the_day():
    up = index(drift=0.002, vol=0.004)
    assert rw.state(up, 899) in ("UP_CALM", "UP_ROUGH") and rw.state(up, 100) is None and rw.state(up, 900) is None
    down = np.concatenate([up[:700], up[700] * np.exp(np.cumsum(np.full(200, -0.004)))])
    assert rw.state(down, 899) == "DOWN"
    rough = up.copy()
    rough[880:] = rough[879] * np.exp(np.cumsum(0.002 + 0.03 * np.random.default_rng(3).standard_normal(20)))
    calm = np.concatenate([up[:880], up[879] * np.exp(np.cumsum(np.full(20, 0.002)))])
    if rough[-1] > rough[-200:].mean():
        assert rw.state(rough, 899) == "UP_ROUGH"
    assert rw.state(calm, 899) == "UP_CALM"
    for i in (300, 555, 800):                       # what comes after the day never changes the day
        poisoned = up.copy()
        poisoned[i + 1:] = np.nan
        shocked = up.copy()
        shocked[i + 1:] *= 9.0
        assert rw.state(up, i) == rw.state(poisoned, i) == rw.state(shocked, i)
    gap = up.copy()
    gap[750] = np.nan
    assert rw.state(gap, 800) is None


def test_static_weights_are_the_live_swing_points_and_korea_counts_no_technical():
    assert rw.static_weights("US").tolist() == pytest.approx([40 / 70, 10 / 70, 20 / 70])
    assert rw.static_weights("KR").tolist() == pytest.approx([0.0, 1 / 3, 2 / 3])


def test_the_composite_rescales_over_the_domains_a_stock_has():
    dom = np.array([[60.0, 30.0, 90.0], [60.0, np.nan, 90.0], [np.nan, np.nan, np.nan], [np.nan, 50.0, np.nan]])
    got = rw.composite(dom, np.array([0.5, 0.25, 0.25]))
    assert got[0] == pytest.approx(60.0) and got[1] == pytest.approx((30 + 22.5) / 0.75) and np.isnan(got[2]) and got[3] == pytest.approx(50.0)
    assert np.isnan(rw.composite(dom, np.array([0.0, 1.0, 0.0]))[1])            # the only weighted domain is missing: no score, never a zero


def test_fitted_weights_drop_a_domain_that_ranked_the_wrong_way_and_fall_back_when_unsure():
    static = np.array([0.5, 0.25, 0.25])
    few = [np.array([0.1, 0.1, 0.1])] * (rw.MIN_STATE - 1)
    assert rw.fitted(few, static)[1] == "STATIC_TOO_FEW" and rw.fitted(few, static)[0] is static
    wrong = [np.array([-0.1, -0.02, -0.3])] * rw.MIN_STATE
    assert rw.fitted(wrong, static)[1] == "STATIC_NO_POSITIVE"
    w, how = rw.fitted([np.array([-0.05, 0.02, 0.06])] * rw.MIN_STATE, static)
    assert how == "FITTED" and w.tolist() == pytest.approx([0.25, 0.125 + 0.5 * 0.25, 0.125 + 0.5 * 0.75]) and w.sum() == pytest.approx(1.0) and (w >= 0).all()
    w, how = rw.fitted([np.array([np.nan, 0.02, 0.02])] * rw.MIN_STATE, static)        # a domain with no reading is not rewarded
    assert how == "FITTED" and w[0] == pytest.approx(0.25)


# ---------------------------------------------------------------------- the walk-forward test on a planted world
def planted(days=120, stocks=120, by_state=True, seed=1):
    """Each state has its own domain that predicts the outcome (or, with ``by_state`` False, none does)."""
    rng = np.random.default_rng(seed)
    best = {"UP_CALM": 0, "UP_ROUGH": 1, "DOWN": 2}
    out = []
    for n in range(days):
        st = rw.STATES[(n // 3) % 3]
        dom = rng.uniform(0, 100, (stocks, 3))
        ret = 0.03 * rng.standard_normal(stocks)
        if by_state:
            ret += 0.0012 * (dom[:, best[st]] - 50)
        out.append({"row": 600 + 21 * n, "date": (date(2015, 1, 1) + timedelta(days=30 * n)).isoformat(), "state": st, "dom": dom, "ret": ret})
    return out


def test_a_world_where_each_state_has_its_own_domain_is_supported_and_walks_without_a_leak():
    got = rw.evaluate(planted(), "US")
    assert got["status"] == "REAL" and got["verdict"] == "REGIME_WEIGHTS_SUPPORTED" and got["leak_free"] is True and got["tested"] == 120 - rw.MIN_TRAIN
    assert got["ic"]["dynamic"] > got["ic"]["control"] > 0 and got["ic_diff"] > 0 and got["ic_diff_t"] >= rw.MIN_T and all(c["passed"] for c in got["conditions"])
    assert got["first_train"] == rw.MIN_TRAIN and got["fitted_share"] > 0.7
    table = got["final_table"]
    assert all(v["how"] == "FITTED" and sum(v["weights"].values()) == pytest.approx(1.0) for v in table.values())
    assert max(table["UP_CALM"]["weights"], key=table["UP_CALM"]["weights"].get) == "TECHNICAL" and max(table["DOWN"]["weights"], key=table["DOWN"]["weights"].get) == "RISK"
    assert got["by_state"]["DOWN"]["days"] + got["by_state"]["UP_CALM"]["days"] + got["by_state"]["UP_ROUGH"]["days"] == got["tested"]


def test_a_world_without_any_state_effect_is_not_supported():
    got = rw.evaluate(planted(by_state=False, seed=5), "US")
    assert got["status"] == "REAL" and got["verdict"] == "NOT_SUPPORTED" and any(not c["passed"] for c in got["conditions"])
    assert [c["id"] for c in got["conditions"]] == ["DIFF_T", "BOTH_HALVES", "OVER_CONTROL", "SPREAD"] and all("need" in c and "value" in c for c in got["conditions"])


def test_weights_of_a_test_day_do_not_move_when_its_own_and_later_outcomes_change():
    days = planted(days=90)
    k = 60
    changed = [dict(d, ret=-d["ret"]) if n >= k else d for n, d in enumerate(days)]
    base, again = rw.evaluate(days, "US", detail=True), rw.evaluate(changed, "US", detail=True)
    cut = days[k]["date"]
    before = lambda got: [(r["date"], r["how"], r["weights"]) for r in got["rows"] if r["date"] <= cut]        # noqa: E731
    after = lambda got: [r["weights"] for r in got["rows"] if r["date"] > days[k + 1]["date"]]                # noqa: E731
    assert before(base) == before(again) and len(before(base)) == k + 1 - rw.MIN_TRAIN            # day k itself is weighted from days before it
    assert after(base) != after(again)                                                            # later days do learn from the changed outcomes
    assert [r["static"]["ic"] for r in base["rows"] if r["date"] < cut] == [r["static"]["ic"] for r in again["rows"] if r["date"] < cut]
    assert "rows" not in rw.evaluate(days, "US")


def test_too_few_days_is_not_a_verdict_and_days_without_a_state_or_outcome_are_left_out():
    days = planted(days=rw.MIN_TRAIN + 10)
    got = rw.evaluate(days, "US")
    assert got["verdict"] == "NOT_TESTED" and got["status"] == "TOO_FEW_TEST_DAYS"
    days = planted(days=80)
    days[10]["state"] = None
    days[11]["ret"] = np.full(120, np.nan)
    assert rw.evaluate(days, "US")["days"] == 78


def test_the_run_is_written_once_and_a_second_call_computes_nothing(tmp_path):
    calls = []

    def load(base):
        calls.append(1)
        return planted(days=70)
    first = rw.run_once(tmp_path, log=lambda m: None, loaders={"US": load})
    assert first["status"] == "REAL" and first["markets"]["US"]["verdict"] in ("REGIME_WEIGHTS_SUPPORTED", "NOT_SUPPORTED") and first["settings"]["shrink"] == rw.SHRINK
    again = rw.run_once(tmp_path, log=lambda m: None, loaders={"US": load})
    assert again["status"] == "ALREADY_RUN" and len(calls) == 1 and again["markets"] == json.loads((tmp_path / rw.REPORT).read_text())["markets"]
    assert set(rw.table(tmp_path)["US"]) == set(rw.STATES) and rw.table(tmp_path / "nowhere") is None


# ---------------------------------------------------------------------- the daily record
def snaps(session, n=240, market="US"):
    out = []
    for k in range(n):
        dom = {"TECHNICAL": {"score_100": 20.0 + k / 4, "coverage": 1.0}, "FUNDAMENTAL": {"score_100": 90.0 - k / 4, "coverage": 1.0 if k else 0.0},
               "RISK": {"score_100": 50.0, "coverage": 1.0}, "EVENTS": {"score_100": 10.0, "coverage": 1.0}}
        out.append({"ticker": f"T{k:03d}", "strategy": "SWING", "score": 40.0 + k / 10, "data_date": session, "entry_session": "next", "actionability": "ACTIONABLE",
                    "model_version": config.MODEL_VERSION, "domains": dom, "market": market})
    return out


def bars(last, n=600):
    days, d = [], date.fromisoformat(last)
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d -= timedelta(days=1)
    c = index(n, drift=0.002, vol=0.004)
    return [{"date": day, "close": float(c[k]), "adj_close": float(c[k])} for k, day in enumerate(reversed(days))]


def test_a_session_is_scored_with_the_frozen_weights_of_its_state_and_keeps_the_fixed_and_live_scores():
    weights = {"how": "FITTED", "weights": {"TECHNICAL": 0.2, "FUNDAMENTAL": 0.3, "RISK": 0.5}}
    doc = rw.score_session(snaps("2026-11-12"), "2026-11-12", "US", "DOWN", weights)
    rows = {r["ticker"]: r for r in doc["rows"]}
    assert doc["state"] == "DOWN" and doc["weights"] == weights["weights"] and len(rows) == 240 and doc["model_versions"] == [config.MODEL_VERSION]
    assert rows["T100"]["score"] == pytest.approx(0.2 * 45 + 0.3 * 65 + 0.5 * 50) and rows["T100"]["static"] == pytest.approx((40 * 45 + 10 * 65 + 20 * 50) / 70, abs=1e-3)
    assert rows["T000"]["score"] == pytest.approx((0.2 * 20 + 0.5 * 50) / 0.7, abs=1e-3) and rows["T100"]["live"] == 50.0      # no fundamental reading: scored on the rest
    assert not any("ret" in r or "net" in r for r in doc["rows"])
    with pytest.raises(rw.NotReady, match="TOO_FEW_STOCKS"):
        rw.score_session(snaps("2026-11-12", n=150), "2026-11-12", "US", "DOWN", weights)
    with pytest.raises(rw.NotReady, match="TOO_FEW_STOCKS"):
        rw.score_session(snaps("2026-11-11"), "2026-11-12", "US", "DOWN", weights)


def test_the_state_of_a_session_waits_for_the_index_to_reach_it():
    b = bars("2026-11-12")
    assert rw.index_state(b, "2026-11-12") in rw.STATES and rw.index_state(b + [{"date": "2026-11-13", "close": 1.0}], "2026-11-12") == rw.index_state(b, "2026-11-12")
    with pytest.raises(rw.NotReady, match="INDEX_NOT_AT_SESSION"):
        rw.index_state(b[:-1], "2026-11-12")
    with pytest.raises(rw.NotReady, match="INDEX_HISTORY_SHORT"):
        rw.index_state(b[-150:], "2026-11-12")


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


def test_the_record_is_written_once_per_session_from_the_first_day_and_waits_without_a_table(tmp_path, monkeypatch):
    monkeypatch.setattr(rw, "Ledger", FakeLedger)
    FakeLedger.days = ["2026-11-10", "2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17"]
    at = datetime(2026, 11, 18, 0, 0, tzinfo=timezone.utc)
    assert rw.record(tmp_path, "US", lambda: bars("2026-11-17"), now=lambda: at)["status"] == "NO_TABLE"
    rw.run_once(tmp_path, log=lambda m: None, loaders={"US": lambda base: planted(days=70)})
    got = rw.record(tmp_path, "US", lambda: bars("2026-11-17"), now=lambda: at)
    assert got["status"] == "WAITING" and got["written"] == ["2026-11-12", "2026-11-13", "2026-11-16"] and got["waiting"] == {"session": "2026-11-17", "reason": "TOO_FEW_STOCKS"}
    again = rw.record(tmp_path, "US", lambda: bars("2026-11-17"), now=lambda: at)
    assert again["written"] == [] and again["sessions"] == 3
    FakeLedger.days = FakeLedger.days + ["2026-11-18"]
    late = rw.record(tmp_path, "US", lambda: bars("2026-11-17"), now=lambda: at)              # the index has not reached the newest session
    assert late["status"] == "WAITING" and late["waiting"]["reason"] == "INDEX_NOT_AT_SESSION" and late["written"] == []
    done = rw.record(tmp_path, "US", lambda: bars("2026-11-18"), now=lambda: at)              # the partial older day is passed over
    assert done["status"] == "OK" and done["written"] == ["2026-11-18"]
    idx = kf.read_index(tmp_path, rw.FOLDERS["US"])
    assert [r["session"] for r in idx] == ["2026-11-12", "2026-11-13", "2026-11-16", "2026-11-18"] and kf.verify(tmp_path, rw.FOLDERS["US"])["status"] == "OK"
    doc = kf._read_day(tmp_path / rw.FOLDERS["US"], "2026-11-13")
    assert doc["state"] in rw.STATES and doc["weights"] == rw.table(tmp_path)["US"][doc["state"]]["weights"] and doc["late"] is True
    view = rw.status(tmp_path)
    assert view["status"] == "REAL" and view["markets"]["US"]["record"]["sessions"] == 4 and view["markets"]["US"]["record"]["today"]["session"] == "2026-11-18"
    assert view["markets"]["US"]["conditions"] and rw.status(tmp_path / "nowhere")["status"] == "NO_RECORD"
    assert not (tmp_path / rw.FOLDERS["KR"]).exists()


def test_the_two_stores_are_backed_up_with_the_other_forward_records():
    from terminal import automation
    assert {"regime_weights_kr", "regime_weights_us"} <= set(automation.FORWARD_STORES)
    assert sum("regime_weights_" in g for g in automation.BACKUP_GLOBS) == 2


def test_the_korean_index_is_the_kospi_members_weighted_by_the_previous_days_value():
    z = {"dates": np.array(["2026-11-09", "2026-11-10", "2026-11-11"]), "kospi": np.array([True, True, False, True]),
         "adj_close": np.array([[100.0, 50.0, 10.0, np.nan], [110.0, 50.0, 30.0, 20.0], [110.0, 45.0, 30.0, 22.0]]),
         "cap": np.array([[300.0, 100.0, 999.0, np.nan], [330.0, 100.0, 999.0, 50.0], [330.0, 90.0, 999.0, 55.0]])}
    bars = rw.kospi_index(z)
    assert [b["date"] for b in bars] == ["2026-11-09", "2026-11-10", "2026-11-11"] and bars[0]["close"] == 1000.0
    assert bars[1]["close"] == pytest.approx(1000.0 * (1 + (300 * 0.10 + 100 * 0.0) / 400))                 # the KOSDAQ stock and the one without a previous price are left out
    assert bars[2]["close"] == pytest.approx(bars[1]["close"] * (1 + (330 * 0.0 + 100 * -0.10 + 50 * 0.10) / 480))


class FakePanel:
    """Sessions by index; a stock's 20-session outcome is its number plus the day's shift."""

    def __init__(self, days, tickers, slope):
        self.dates, self.col, self.slope = days, {t: j for j, t in enumerate(tickers)}, slope

    def forward(self, i, h, cost=0.0):
        return self.slope * np.arange(len(self.col), dtype=float) / 1000 + 0.001 * i


def test_the_forward_reading_waits_for_240_matured_sessions_runs_once_and_gives_figures_only(tmp_path, monkeypatch):
    days = []
    d = date(2026, 11, 12)
    while len(days) < 280:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d += timedelta(days=1)
    tickers = [f"T{k:03d}" for k in range(60)]
    at = datetime(2028, 1, 1, tzinfo=timezone.utc)
    rw.run_once(tmp_path, log=lambda m: None, loaders={"US": lambda base: planted(days=70)})

    def write(upto):
        for n, day in enumerate(days[:upto]):
            rows = [{"ticker": t, "score": float(k), "static": float(-k if n % 2 else k), "live": float(k), "entry_session": days[n + 1]} for k, t in enumerate(tickers)]
            kf.write_record(tmp_path, day, at, False, store=rw.FOLDERS["US"], scorer=lambda b, x, rows=rows: {"session": x, "state": rw.STATES[n % 3], "rows": rows})
    write(200)
    px = FakePanel(days, tickers, slope=1.0)
    assert len(rw.measure_forward([kf._read_day(tmp_path / rw.FOLDERS["US"], x) for x in days[:200]], px)) == 200
    with pytest.raises(RuntimeError, match="200개"):
        rw.evaluate_forward_once(tmp_path, "US", px)
    write(259)
    got = rw.evaluate_forward_once(tmp_path, "US", px)
    assert got["days"] == rw.READ_AT == 240 and got["reading"] == "FIGURES_ONLY" and got["records"] == 259 and got["first"] == days[0] and got["last"] == days[239]
    assert got["ic"]["dynamic"] == pytest.approx(1.0) and got["ic"]["static"] == pytest.approx(0.0) and got["ic_diff"] == pytest.approx(1.0) and got["past_verdict"] in ("REGIME_WEIGHTS_SUPPORTED", "NOT_SUPPORTED")
    assert sum(v["days"] for v in got["by_state"].values()) == 240 and got["late_share"] == 0.0
    with pytest.raises(RuntimeError, match="이미 읽었습니다"):
        rw.evaluate_forward_once(tmp_path, "US", px)
