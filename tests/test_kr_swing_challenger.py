"""Korean swing challenger: the score, the write-once record from the ledger, and the one evaluation's rule.  All offline."""
import json
from datetime import datetime, timezone

import numpy as np
import pytest

from terminal.qsf import kr_forward as kf
from terminal.qsf import kr_swing_challenger as sc

NOW = datetime(2026, 11, 10, 22, 30, tzinfo=timezone.utc)


def factor(domain, weight, normalized, status="REAL"):
    return {"factor": f"{domain}_{weight}", "domain": domain, "weight": weight, "status": status, "normalized": normalized, "contribution": None if normalized is None else weight * normalized}


def snap(ticker, session, tech, risk, fund, score=50.0, strategy="SWING", entry="2026-11-11"):
    return {"market": "KR", "ticker": ticker, "strategy": strategy, "model_version": "QSF-1.1.8", "score": score, "data_date": session, "entry_session": entry, "actionability": "ACTIONABLE",
            "factors": [factor("TECHNICAL", 40, tech), factor("RISK", 20, risk), factor("FUNDAMENTAL", 10, fund), factor("EVENTS", 10, None, "MISSING"), factor("REGIME", 20, 0.5, "STALE")]}


def test_the_challenger_is_the_live_composite_without_the_technical_domain():
    s = snap("000010", "2026-11-09", tech=1.0, risk=0.5, fund=1.0)
    assert sc.challenger_score(s["factors"]) == pytest.approx(100 * (20 * 0.5 + 10 * 1.0 + 20 * 0.5) / 50)       # the missing events factor carries no weight
    assert sc.challenger_score([factor("TECHNICAL", 40, 1.0)]) is None and sc.challenger_score([]) is None
    low_tech = snap("000020", "2026-11-09", tech=0.0, risk=0.5, fund=1.0)
    assert sc.challenger_score(low_tech["factors"]) == sc.challenger_score(s["factors"])                       # the technical value cannot move it


def test_a_session_keeps_only_fresh_swing_rows_and_refuses_a_partial_day():
    snaps = [snap(f"{k:06d}", "2026-11-09", 0.5, k / 300, 0.5) for k in range(250)] + [snap("999990", "2026-11-06", 0.5, 0.5, 0.5), snap("999980", "2026-11-09", 0.5, 0.5, 0.5, strategy="LONG_TERM")]
    doc = sc.score_session(snaps, "2026-11-09")
    assert len(doc["rows"]) == 250 and doc["dropped_domain"] == "TECHNICAL" and doc["rows"][0]["entry_session"] == "2026-11-11" and doc["rows"][0]["live"] == 50.0
    assert doc["rows"][249]["score"] > doc["rows"][0]["score"]
    with pytest.raises(ValueError, match="TOO_FEW_STOCKS"):
        sc.score_session(snaps[:100], "2026-11-09")


class FakeLedger:
    rows = [{"market": "KR", "session": "2026-11-06"}, {"market": "KR", "session": "2026-11-09"}, {"market": "KR", "session": "2026-11-10"}, {"market": "US", "session": "2026-11-09"}]

    def __init__(self, root):
        pass

    def verify(self):
        return {"status": "OK"}

    def _live_rows(self):
        return self.rows

    def _load(self, r):
        n = 250 if r["session"] != "2026-11-10" else 50
        return [snap(f"{k:06d}", r["session"], 0.5, k / 300, 0.5) for k in range(n)]


def test_record_is_written_once_from_the_first_session_and_waits_for_a_partial_day(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "Ledger", FakeLedger)
    res = sc.record(tmp_path, now=lambda: NOW)
    assert res["status"] == "WAITING" and res["written"] == ["2026-11-09"] and res["partial"] == ["2026-11-10"]         # 11-06 is before the first session
    idx = kf.read_index(tmp_path, sc.FOLDER)
    assert len(idx) == 1 and idx[0]["stocks"] == 250 and idx[0]["late"] is True and kf.verify(tmp_path, sc.FOLDER)["status"] == "OK"
    before = (tmp_path / sc.FOLDER / "2026-11-09.json.gz").read_bytes()
    assert sc.record(tmp_path, now=lambda: NOW)["written"] == [] and (tmp_path / sc.FOLDER / "2026-11-09.json.gz").read_bytes() == before
    assert sc.status(tmp_path)["records"] == 1 and sc.status(tmp_path)["evaluated"] is False


class FakePanel:
    def __init__(self, n=400, names=60):
        self.dates = [f"d{i:04d}" for i in range(n)]
        self.col = {f"{k:06d}": k for k in range(names)}
        self.names = names

    def forward(self, i, h, cost=0.0):
        rng = np.random.default_rng(i)
        return np.linspace(-0.05, 0.05, self.names) + rng.normal(0, 0.01, self.names) - cost        # the higher the code, the better the return


def docs(n, names=60, challenger_knows=True):
    out = []
    for d in range(n):
        noise = np.random.default_rng(1000 + d).random((2, names))                         # a score that knows nothing, different every day
        rows = [{"ticker": f"{k:06d}", "score": float(k if challenger_knows else noise[0, k]), "live": float(noise[1, k]), "entry_session": f"d{d + 1:04d}"} for k in range(names)]
        out.append({"session": f"d{d:04d}", "rows": rows, "late": False})
    return out


def test_days_are_measured_from_the_ledgers_entry_session_and_only_when_the_hold_has_ended():
    px = FakePanel(n=50)
    got = sc.measure_days(docs(40), px)
    assert len(got) == 30 and got[0]["entry"] == "d0001" and got[0]["ic_challenger"] > 0.9 and abs(got[0]["ic_live"]) < 0.5      # the last holds are still open
    assert got[0]["fifths_challenger"]["top"] > 0 > got[0]["fifths_challenger"]["bottom"]


def test_verdict_needs_the_challengers_own_evidence_and_a_lead_over_the_live_score():
    px = FakePanel()
    better = sc.verdict(sc.measure_days(docs(300), px)[::sc.HORIZON])
    assert better["samples"] >= sc.MIN_SAMPLES and better["verdict"] == "CHALLENGER_BETTER" and better["difference"]["mean"] > 0
    same = [{"ic_challenger": 0.1 + 0.01 * (k % 3), "ic_live": 0.1 + 0.01 * ((k + 1) % 3)} for k in range(12)]
    assert sc.verdict(same)["verdict"] == "CHALLENGER_HAS_EVIDENCE"
    none = sc.verdict(sc.measure_days(docs(300, challenger_knows=False), px)[::sc.HORIZON])
    assert none["verdict"] == "NO_EVIDENCE"


def test_evaluation_is_refused_before_twelve_samples_and_runs_once(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "Ledger", FakeLedger)
    monkeypatch.setattr(FakeLedger, "rows", [{"market": "KR", "session": "2026-11-09"}])
    sc.record(tmp_path, now=lambda: NOW)
    with pytest.raises(RuntimeError, match="12개"):
        sc.evaluate_once(tmp_path, panel=FakePanel())
    (tmp_path / sc.REPORT).parent.mkdir(parents=True)
    (tmp_path / sc.REPORT).write_text(json.dumps({}))
    with pytest.raises(RuntimeError, match="한 번만"):
        sc.evaluate_once(tmp_path, panel=FakePanel())
