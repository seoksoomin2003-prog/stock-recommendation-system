"""Change report: who entered and left the buy band, what moved, a model change said out loud, the ledger left alone.  No network."""
import gzip
import json

import pytest

from terminal.qsf import changes as ch, ledger as lg


def row(t, score, action="WATCH", strategy="SWING", tech=50.0, fund=50.0, **extra):
    return {"ticker": t, "name": f"{t} Inc", "strategy": strategy, "score": score, "action": action, "action_label": action, "domains": {"TECHNICAL": tech, "FUNDAMENTAL": fund}, "gates": [], **extra}


def old(t, score, action="WATCH", strategy="SWING", tech=50.0, fund=50.0, version="M1"):
    return {"ticker": t, "strategy": strategy, "score": score, "action": action, "model_version": version, "domains": {"TECHNICAL": {"score_100": tech}, "FUNDAMENTAL": {"score_100": fund}}}


def test_entered_and_left_the_buy_band_sorted_by_score():
    got = ch.compare([row("A", 72, "BUY"), row("B", 80, "BUY"), row("C", 60), row("D", 75, "BUY")], [old("A", 60), old("B", 69), old("C", 71, "BUY"), old("D", 74, "BUY")], "SWING")
    assert [m["ticker"] for m in got["entered_buy"]] == ["B", "A"] and [m["ticker"] for m in got["left_buy"]] == ["C"] and got["compared"] == 4


def test_movers_and_the_domain_that_moved_most():
    got = ch.compare([row("UP", 70, tech=80.0), row("DN", 40, fund=20.0), row("SAME", 55), row("LITTLE", 56, fund=50.5)], [old("UP", 60), old("DN", 50), old("SAME", 55), old("LITTLE", 55)], "SWING")
    assert [m["ticker"] for m in got["up"]] == ["UP", "LITTLE"] and [m["ticker"] for m in got["down"]] == ["DN"]
    assert got["up"][0]["reason"] == {"domain": "TECHNICAL", "change": 30.0} and got["down"][0]["reason"] == {"domain": "FUNDAMENTAL", "change": -30.0}
    assert got["up"][1]["reason"] is None and got["up"][0]["delta"] == 10.0


def test_a_missing_score_never_makes_a_move():
    got = ch.compare([row("A", None), row("B", 50)], [old("A", 60), old("B", None)], "SWING")
    assert got["up"] == [] and got["down"] == [] and got["compared"] == 2


def test_only_the_asked_strategy_and_new_or_gone_names():
    got = ch.compare([row("A", 70), row("NEW", 70), row("L", 90, strategy="LONG_TERM")], [old("A", 60), old("GONE", 60), old("L", 10, strategy="LONG_TERM")], "SWING")
    assert got["new_in_scan"] == ["NEW"] and got["gone_from_scan"] == ["GONE"] and got["compared"] == 1 and "L" not in [m["ticker"] for m in got["up"]]


class FakeLedger:
    def __init__(self, rows, status="OK"):
        self.rows, self.status = rows, status

    def read_index(self):
        return {"status": self.status, "rows": []}

    def session_before(self, market, session):
        return "2026-11-05" if self.rows else None

    def of_session(self, market, session, strategy):
        return [r for r in self.rows if r["strategy"] == strategy]


LATEST = {"status": "REAL", "session": "2026-11-06", "model_version": "M1", "rows": [row("A", 70, "BUY")]}


def test_a_model_change_is_said_out_loud():
    assert ch.report(LATEST, FakeLedger([old("A", 60)]), "US", "SWING")["model_changed"] is False
    got = ch.report(LATEST, FakeLedger([old("A", 60, version="M0")]), "US", "SWING")
    assert got["model_changed"] is True and got["previous_model_versions"] == ["M0"] and got["previous_session"] == "2026-11-05"


def test_no_previous_a_broken_ledger_and_no_scan_are_not_empty_successes():
    assert ch.report(LATEST, FakeLedger([]), "US", "SWING")["status"] == "NO_PREVIOUS"
    assert ch.report(LATEST, FakeLedger([old("A", 60)], status="CHAIN_BROKEN"), "US", "SWING")["status"] == "UNAVAILABLE"
    assert ch.report({"status": "UNAVAILABLE", "reason": "x"}, FakeLedger([]), "US", "SWING") == {"status": "UNAVAILABLE", "reason": "x"}


def snap(t, session, strategy="SWING", market="US", score=50.0):
    return {"ticker": t, "strategy": strategy, "market": market, "score": score, "data_date": session}


def write_shards(tmp_path, shards):
    led = lg.Ledger(tmp_path)
    led.dir.mkdir(parents=True)
    rows = []
    for n, (session, market, items) in enumerate(shards, 1):
        name = f"{session}_{market}_{n:06d}.jsonl.gz"
        with gzip.open(led.dir / name, "wt", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(it) + "\n")
        rows.append({"file": name, "session": session, "market": market})
    led._live_rows = lambda: rows
    return led


def test_ledger_reads_the_session_before_for_that_market_only(tmp_path):
    led = write_shards(tmp_path, [("2026-11-04", "US", [snap("A", "2026-11-04")]), ("2026-11-05", "US", [snap("B", "2026-11-03"), snap("B", "2026-11-03", strategy="LONG_TERM")]), ("2026-11-05", "KR", [snap("K", "2026-11-05", market="KR")]), ("2026-11-06", "US", [snap("C", "2026-11-06")])])
    assert led.session_before("US", "2026-11-06") == "2026-11-05" and led.session_before("US", "2026-11-04") is None and led.session_before("KR", "2026-11-05") is None
    assert [s["ticker"] for s in led.of_session("US", "2026-11-05", "SWING")] == ["B"]      # a stale price date does not drop it


def test_bad_strategy_refused():
    from terminal.server import routes

    class Qsf:
        ledger = FakeLedger([])

        def latest(self, market):
            return LATEST

    class T:
        qsf = Qsf()
    fn = routes(T())[("GET", "/api/qsf/changes")]
    with pytest.raises(ValueError):
        fn({"strategy": "DAY"}, {})
    assert fn({}, {})["status"] == "NO_PREVIOUS"
