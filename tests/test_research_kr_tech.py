"""The earlier-window confirmation run of the Korean technical domain: which days count, the readings, and the single run.  All offline."""
import gzip
import json

import numpy as np
import pytest

from terminal.qsf import research_kr_live as rl, research_kr_tech as rt


class Panel:
    def __init__(self, dates, symbols, sign):
        self.dates, self.symbols, self.col, self.sign = dates, symbols, {s: n for n, s in enumerate(symbols)}, sign

    def forward(self, i, h, cost=0.0):
        rng = np.random.default_rng(i)
        base = np.linspace(-0.03, 0.03, len(self.symbols)) * self.sign(i)
        return base + 0.01 * rng.standard_normal(len(self.symbols)) - cost


def dates(n):
    out, y, m, d = [], 2012, 1, 1
    from datetime import date, timedelta
    day = date(2011, 6, 1)
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


DATES = dates(2100)                                       # mid 2011 to mid 2019
SYMS = [f"S{k:03d}" for k in range(60)]


def records(rows, tech_dir=1.0):
    """Technical ranks with the column order times ``tech_dir``; risk ranks with it always."""
    out = []
    for i in rows:
        for k, s in enumerate(SYMS):
            out.append({"i": i, "t": s, "SWING|TECHNICAL": 50 + tech_dir * (k - 30), "SWING|RISK": 20 + k, "SWING|RAW": 50 + (tech_dir * 2 + 1) * (k - 30) / 3,
                        "LONG_TERM|TECHNICAL": 50.0 + k, "factors": {"trend_structure": k / 60}})
    return out


def test_only_days_whose_return_ends_before_the_replay_are_used(monkeypatch):
    px = Panel(DATES, SYMS, lambda i: 1)
    monkeypatch.setattr(rl, "eval_rows", lambda p, first: list(range(next(i for i, d in enumerate(p.dates) if d >= first), len(p.dates), 21)))
    rows = rt.eval_days(px)
    assert px.dates[rows[0]] >= rt.FIRST and all(px.dates[i + rt.H] <= rt.LAST_EXIT for i in rows) and px.dates[rows[-1] + 21 + rt.H] > rt.LAST_EXIT
    assert len(rt.eval_days(px, rt.LONG_H)) < len(rows)


def test_the_readings_are_the_protocols():
    s = lambda mean, t, early, late: {"mean": mean, "t": t, "early": early, "late": late}      # noqa: E731
    assert rt.primary_reading(s(-0.03, -2.4, -0.02, -0.04)) == "NEGATIVE_AGAIN" and rt.primary_reading(s(-0.03, -1.9, -0.02, -0.04)) == "NOT_CONFIRMED"
    assert rt.primary_reading(s(-0.03, -2.4, 0.01, -0.07)) == "NOT_CONFIRMED" and rt.primary_reading(s(0.03, 2.4, 0.02, 0.04)) == "OPPOSITE"
    assert rt.primary_reading({"dates": 2, "status": "UNAVAILABLE"}) == "NOT_CONFIRMED"
    assert rt.secondary_reading(s(0.02, 2.1, 0.01, 0.03)) == "DROPPING_HELPED_AGAIN" and rt.secondary_reading(s(0.02, 2.1, -0.01, 0.05)) == "NOT_CONFIRMED"


def test_a_technical_score_against_the_returns_reads_negative_and_dropping_it_helps():
    px = Panel(DATES, SYMS, lambda i: 1)
    rows = list(range(300, 1900, 21))
    res = rt.evaluate(px, records(rows, tech_dir=-1.0))
    assert res["technical"]["reading"] == "NEGATIVE_AGAIN" and res["technical"]["mean"] < -0.5 and res["technical"]["bottom_fifth_excess"] > res["technical"]["top_fifth_excess"]
    assert res["risk_minus_composite"]["reading"] == "DROPPING_HELPED_AGAIN" and res["risk"]["mean"] > 0.5
    assert res["technical_factors"]["trend_structure"]["mean"] > 0 and set(res["technical_other_horizons"]) == {"5", "10"}


def test_a_technical_score_that_works_in_one_half_only_is_not_confirmed():
    px = Panel(DATES, SYMS, lambda i: 1 if i < 1100 else -1)
    res = rt.evaluate(px, records(list(range(300, 1900, 21)), tech_dir=-1.0))
    assert res["technical"]["reading"] == "NOT_CONFIRMED" and res["technical"]["early"] < 0 < res["technical"]["late"]


def test_the_run_is_written_once(tmp_path, monkeypatch):
    px = Panel(DATES, SYMS, lambda i: 1)
    rows = list(range(300, 1900, 21))
    (tmp_path / rl.DATA).mkdir(parents=True)
    with pytest.raises(RuntimeError, match="prepare"):
        rt.run_once(tmp_path)
    with gzip.open(tmp_path / rl.DATA / rt.SCORES, "wt", encoding="utf-8") as fh:
        json.dump({"rows": rows, "first": DATES[rows[0]], "last": DATES[rows[-1]], "records": records(rows)}, fh)
    monkeypatch.setattr(rl, "load_panel", lambda base: px)
    res = rt.run_once(tmp_path, log=lambda *_: None)
    assert res["technical"]["reading"] == "OPPOSITE" and json.loads((tmp_path / rt.REPORT).read_text(encoding="utf-8"))["days"] == len(rows)
    with pytest.raises(RuntimeError, match="한 번만"):
        rt.run_once(tmp_path)
