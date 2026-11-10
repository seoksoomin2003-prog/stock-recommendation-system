"""The live score's one forward verdict: which rows count, the daily statistics, the split of score and universe, the refusals.  All offline."""
import json
from datetime import date, timedelta

import numpy as np
import pytest

from terminal.qsf import live_forward as lf


def calendar(n, start=date(2026, 11, 9)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


CAL = calendar(400)
N = 40                                                     # stocks a day


def bars_of(k, strength, bad_from=None):
    """Stock k drifts with its rank: a higher k earns more each day when ``strength`` is positive."""
    px, out = 100.0, []
    for n, d in enumerate(CAL):
        drift = strength * (k - N / 2) / N * (-1 if bad_from is not None and n >= bad_from else 1)
        wobble = 0.004 * np.sin(0.7 * n + k)
        o = px
        px = px * (1 + drift + wobble)
        out.append({"date": d, "open": o, "high": max(o, px), "low": min(o, px), "close": px, "adj_close": px, "volume": 1000})
    return out


def flat_bench(n=len(CAL)):
    """The index's bars are the market calendar: it ends at the last finished session."""
    return [{"date": d, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "adj_close": 100.0, "volume": 1} for d in CAL[:n]]


def snap(k, session, entry, strategy="SWING", score=None, **more):
    return {"market": "US", "ticker": f"T{k:02d}", "strategy": strategy, "score": 35 + k if score is None else score, "actionability": "ACTIONABLE", "data_date": session,
            "entry_session": entry, "model_version": "QSF-1.1.8", **more}


class FakeLedger:
    days = 300
    broken = False

    def __init__(self, root):
        pass

    def verify(self):
        return {"status": "BROKEN" if self.broken else "OK"}

    def _live_rows(self):
        return [{"market": "US", "session": d} for d in CAL[:self.days]] + [{"market": "US", "session": "2026-11-06"}, {"market": "KR", "session": CAL[0]}]

    def _load(self, r):
        if r["market"] != "US":
            return [snap(k, r["session"], r["session"]) for k in range(N)]
        i = CAL.index(r["session"]) if r["session"] in CAL else 0
        rows = [snap(k, r["session"], CAL[i + 1]) for k in range(N)]
        rows += [snap(90, "2026-11-01", CAL[i + 1]), snap(91, r["session"], CAL[i + 1], actionability="INSUFFICIENT_DATA"), snap(92, r["session"], CAL[i + 1], strategy="LONG_TERM")]
        return rows + [{**snap(93, r["session"], CAL[i + 1]), "score": None}]


@pytest.fixture
def led(monkeypatch):
    monkeypatch.setattr(lf, "Ledger", FakeLedger)
    monkeypatch.setattr(FakeLedger, "days", 300)
    monkeypatch.setattr(FakeLedger, "broken", False)
    return FakeLedger


def loader(strength=0.001, bad_from=None):
    books = {f"T{k:02d}": bars_of(k, strength, bad_from) for k in range(N)}
    return lambda t: books.get(t) or []


def test_only_fresh_scored_rows_from_the_first_session_count(led):
    rows = lf.session_rows(FakeLedger("x"), "US", "SWING")
    assert list(rows)[0] == lf.FIRST and "2026-11-06" not in rows and len(rows) == 300
    assert {s["ticker"] for s in rows[CAL[0]]} == {f"T{k:02d}" for k in range(N)}        # stale, unscored, insufficient and long rows are out


def test_the_status_counts_sessions_and_reads_no_price(led):
    st = lf.status("x", {"US": CAL, "KR": CAL[:5]})
    c = st["cohorts"]["US_SWING"]
    assert c == {"horizon": 20, "recorded": 300, "matured": 300, "needed": 240, "ready": True, "evaluated": False}
    assert st["cohorts"]["KR_SWING"]["matured"] == 0 and st["cohorts"]["US_LONG_TERM"]["needed"] == 756


def test_a_day_splits_the_buy_band_into_score_and_universe(led):
    rows = lf.session_rows(FakeLedger("x"), "US", "SWING")
    px = lf.Prices(loader(), flat_bench())
    d = lf.day_stats(CAL[0], rows[CAL[0]], px, 20, 0.002)
    assert d["n"] == N and d["ic"] > 0.5 and d["buy_n"] == 5 and d["index"] == pytest.approx(0.0, abs=1e-12)
    assert d["buy_net"] > d["universe_net"] and d["universe_effect"] == pytest.approx(d["universe_net"] - d["index"])
    assert lf.day_stats(CAL[-10], [snap(k, CAL[-10], CAL[-9]) for k in range(N)], px, 20, 0.002) is None                   # the hold has not ended: never a zero


def test_a_score_that_ranks_and_beats_the_index_passes_and_is_written_once(led, tmp_path):
    res = lf.evaluate_once(tmp_path, "US", "SWING", loader(), flat_bench(), log=lambda *_: None)
    assert res["verdict"] == "WEAK_POSITIVE_EVIDENCE" and res["sessions_used"] == 240 and res["last"] == CAL[239] and all(res["condition_a"].values()) and res["condition_b"]
    p = res["primary"]
    assert p["lag"] == 20 and p["dates"] == 240 and p["all"]["score_effect"] > 0 and p["separate_samples"]["samples"] == 12
    assert set(res["other_horizons"]) == {"5", "10"} and res["by_version"] == {"QSF-1.1.8": {"dates": 240, "ic": pytest.approx(p["ic"])}}
    assert json.loads(lf.report_path(tmp_path, "US", "SWING").read_text(encoding="utf-8"))["verdict"] == "WEAK_POSITIVE_EVIDENCE" and "pooled" not in res
    with pytest.raises(RuntimeError, match="한 번만"):
        lf.evaluate_once(tmp_path, "US", "SWING", loader(), flat_bench())


def test_the_sample_is_fixed_whenever_the_evaluation_runs(led, tmp_path, monkeypatch):
    a = lf.evaluate_once(tmp_path / "a", "US", "SWING", loader(), flat_bench(), log=lambda *_: None)
    monkeypatch.setattr(FakeLedger, "days", 360)                                        # run four months later: the same 240 sessions
    b = lf.evaluate_once(tmp_path / "b", "US", "SWING", loader(), flat_bench(), log=lambda *_: None)
    assert a["last"] == b["last"] and a["primary"]["ic"] == b["primary"]["ic"]


def test_a_score_that_works_in_one_half_only_is_no_evidence(led, tmp_path):
    res = lf.evaluate_once(tmp_path, "US", "SWING", loader(bad_from=130), flat_bench(), log=lambda *_: None)
    assert res["verdict"] == "NO_EVIDENCE" and res["condition_a"]["ic_both_halves"] is False


def test_ranking_without_beating_the_index_is_rank_only(led, tmp_path):
    rising = [{**b, "open": 100 * 1.004 ** n, "close": 100 * 1.004 ** (n + 1), "adj_close": 100 * 1.004 ** (n + 1)} for n, b in enumerate(flat_bench())]
    res = lf.evaluate_once(tmp_path, "US", "SWING", loader(), rising, log=lambda *_: None)
    assert res["verdict"] == "RANK_ONLY" and res["condition_b"] is False and res["primary"]["all"]["universe_effect"] < 0 and res["primary"]["all"]["score_effect"] > 0


def test_it_refuses_before_the_sample_is_full_and_on_a_broken_ledger(led, tmp_path, monkeypatch):
    monkeypatch.setattr(FakeLedger, "days", 259)                                         # 239 matured sessions
    with pytest.raises(RuntimeError, match="만기 거래일 239개"):
        lf.evaluate_once(tmp_path, "US", "SWING", loader(), flat_bench(259))
    with pytest.raises(RuntimeError, match="756"):
        lf.evaluate_once(tmp_path, "US", "LONG_TERM", loader(), flat_bench())
    monkeypatch.setattr(FakeLedger, "broken", True)
    with pytest.raises(RuntimeError, match="원장 검증"):
        lf.evaluate_once(tmp_path, "US", "SWING", loader(), flat_bench())
    assert not lf.report_path(tmp_path, "US", "SWING").exists()


def test_two_markets_are_combined_only_as_a_reference(tmp_path):
    for market, t in (("US", 1.8), ("KR", 2.0)):
        p = lf.report_path(tmp_path, market, "SWING")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"primary": {"t": t}}), encoding="utf-8")
    got = lf._pooled(tmp_path, "SWING")
    assert got["combined"] == pytest.approx(3.8 / 2 ** 0.5) and got["engine_level_reference"] is True
    assert lf._pooled(tmp_path, "LONG_TERM") is None
