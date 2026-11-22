"""The look-ahead audit: it catches a function that reads a later row, passes the ones that do not, and reads the record chains."""
import gzip
import json
from datetime import date, datetime, timedelta, timezone

import numpy as np

from terminal.qsf import kr_forward as kf, lookahead as la


def world(days=420, stocks=320, seed=4):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(0.0003 + 0.02 * rng.standard_normal((days, stocks)), axis=0))
    close[:60, :5] = np.nan                                             # some stocks start late
    d, out = date(2025, 1, 1), []
    while len(out) < days:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return {"dates": np.array(out), "symbols": np.array([f"{j:05d}0" for j in range(stocks)]), "close": close, "open": np.vstack([close[:1], close[:-1]]),
            "high": close * 1.01, "low": close * 0.99, "volume": rng.uniform(1e4, 1e6, (days, stocks)), "value": rng.uniform(1e8, 1e11, (days, stocks)),
            "cap": np.full((days, stocks), 1e11), "watch": np.zeros((days, stocks), dtype=bool)}


def test_poison_changes_only_the_rows_after_the_day_and_leaves_the_original_alone():
    d = world(days=120, stocks=10)
    before = d["close"].copy()
    wiped, mult = la.poison(d, 50, "WIPED"), la.poison(d, 50, "MULTIPLIED")
    assert np.array_equal(d["close"], before, equal_nan=True) and np.array_equal(wiped["close"][:51], before[:51], equal_nan=True) and np.isnan(wiped["close"][51:]).all()
    assert np.array_equal(mult["volume"][:51], d["volume"][:51]) and not np.array_equal(mult["volume"][51:], d["volume"][51:])
    assert wiped["dates"] is d["dates"] and wiped["watch"] is d["watch"] and wiped["symbols"] is d["symbols"]


def test_same_treats_missing_as_equal_to_missing_and_sees_any_other_difference():
    a = {"x": np.array([1.0, np.nan]), "y": [np.array([True, False]), 3, None], "z": float("nan")}
    assert la.same(a, {"x": np.array([1.0, np.nan]), "y": [np.array([True, False]), 3, None], "z": float("nan")})
    assert not la.same(a, {**a, "x": np.array([1.0, 2.0])}) and not la.same(a, {**a, "y": [np.array([True, True]), 3, None]})
    assert not la.same({"x": 1}, {"y": 1}) and not la.same(np.zeros(2), np.zeros(3)) and la.same("UP", "UP") and not la.same("UP", None)


def test_a_function_that_reads_the_next_row_is_caught_and_one_that_does_not_passes():
    d = world(days=150, stocks=12)
    rows = [100, 110, 120]
    clean = la.check(lambda z, i: z["close"][i - 20:i + 1].mean(axis=0), d, rows)
    peek = la.check(lambda z, i: z["close"][i - 20:i + 2].mean(axis=0), d, rows)
    assert clean == {"days": 3, "filled": 3, "moved": []} and peek["moved"] == rows
    subtle = la.check(lambda z, i: (z["close"] > np.nanmedian(z["close"], axis=0))[i], d, rows)            # a threshold fitted on the whole history
    assert subtle["moved"]
    silent = la.check(lambda z, i: np.full(12, np.nan), d, rows)
    assert silent["moved"] == [] and silent["filled"] == 0


def test_the_audited_functions_read_nothing_after_their_day_and_the_control_is_caught():
    got = {f["id"]: f for f in la.audit_functions(world())}
    assert set(got) == {"engine.score", "kr_method.signals", "kr_method.atr", "kr_risk_grade.inputs", "regime_weights.state", "kr_risk_grade.targets"}
    for name in ("engine.score", "kr_method.signals", "kr_method.atr", "kr_risk_grade.inputs", "regime_weights.state"):          # the score engine since the audit of 2026-11-22
        assert got[name]["ok"] and got[name]["moved"] == 0 and got[name]["filled"] > 0 and got[name]["days"] == 10 and not got[name]["control"], name
    control = got["kr_risk_grade.targets"]
    assert control["control"] and control["ok"] and control["moved"] == control["days"] == 10


def store(base, name, sessions, tamper=False):
    at = datetime(2026, 11, 20, tzinfo=timezone.utc)
    for n, day in enumerate(sessions):
        kf.write_record(base, day, at, n == 0, store=("research_data/" + name), scorer=lambda b, d: {"session": d, "rows": [{"ticker": "A"}]})
    if tamper:
        with gzip.open(base / "research_data" / name / f"{sessions[0]}.json.gz", "wt", encoding="utf-8") as fh:
            json.dump({"session": sessions[0], "rows": [], "recorded_at": "x", "late": False, "before_next_open": True}, fh)


def test_the_run_writes_one_view_file_and_a_broken_chain_or_a_missed_control_is_a_problem(tmp_path, monkeypatch):
    from pathlib import Path
    store(tmp_path, "kr_method", ["2026-11-11", "2026-11-12"])
    at = datetime(2026, 11, 13, 1, tzinfo=timezone.utc)
    doc = la.run(tmp_path, prices=world(), now=lambda: at)
    assert doc["status"] == "OK" and doc["problems"] == [] and doc["sampled_days"] == 10 and doc["control"]["ok"] and len(doc["functions"]) == 5
    assert doc["records"] == [{"store": "kr_method", "sessions": 2, "first": "2026-11-11", "last": "2026-11-12", "chain": "OK", "bad": [], "before_next_open": 0, "late": 1}]
    assert la.status(tmp_path) == json.loads((tmp_path / la.VIEW).read_text()) and doc["walk_forward"] is None and la.status(tmp_path / "x")["status"] == "NO_RECORD"
    store(tmp_path, "kr_swing_prior", ["2026-11-11", "2026-11-12"], tamper=True)
    bad = la.run(tmp_path, prices=world(), now=lambda: at)
    assert bad["status"] == "PROBLEM" and bad["problems"] == ["kr_swing_prior"] and [r["chain"] for r in bad["records"]] == ["BROKEN", "OK"]
    monkeypatch.setattr(la, "functions", lambda d: [{"id": "peek", "label": "x", "fn": lambda z, i: z["close"][i + 1]},
                                                    {"id": "blind_control", "label": "y", "fn": lambda z, i: z["close"][i], "control": True}])
    worse = la.run(tmp_path / "other", prices=world(), now=lambda: at)
    assert worse["status"] == "PROBLEM" and worse["problems"] == ["peek", "blind_control"]
    assert la.run(tmp_path / "short", prices=world(days=50), now=lambda: at)["status"] == "NO_PRICES"
    assert not list(Path(tmp_path).rglob("*.tmp"))
