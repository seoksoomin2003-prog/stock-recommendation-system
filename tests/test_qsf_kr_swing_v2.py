"""QSF-1.2.0: the Korean swing score without the technical domain, the reference rows, and the record of the former formula.  All offline."""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from terminal.qsf import config, engine, factors, kr_forward as kf, kr_swing_challenger as sc, kr_swing_prior as sp, ledger, track_record as tr

NOW = datetime(2026, 11, 11, 22, 30, tzinfo=timezone.utc)
TECH = ("trend_structure", "relative_strength", "momentum", "breakout_volume", "volatility_structure")


def bars(n=320, drift=0.001):
    out, px = [], 10000.0
    for i in range(n):
        px *= 1 + drift + 0.01 * np.sin(i / 7.0)
        out.append({"date": f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}" if i < 336 else f"d{i}", "open": px * 0.995, "high": px * 1.01, "low": px * 0.985, "close": px, "adj_close": px, "volume": 500000.0})
    return out


def ctx(market="KR"):
    return {"market": market, "ticker": "000001", "bars": bars(), "fund": None, "regime": {}, "events": None, "earnings": {}, "price_fresh": True}


def fixed_tech(monkeypatch, value):
    for fid in TECH:
        monkeypatch.setitem(factors.CALC, fid, lambda c, v=value: factors.obs(v, {}, "고정값", "시험", "2026-11-10"))


def test_only_the_korean_swing_profile_changed():
    ids = {(p["market"], p["strategy"]): p["id"] for p in config.PROFILES.values()}
    assert ids == {("US", "SWING"): "US_SWING_V1", ("US", "LONG_TERM"): "US_LONG_TERM_V1", ("KR", "SWING"): "KR_SWING_V2", ("KR", "LONG_TERM"): "KR_LONG_TERM_V1"}
    kr, us = config.profile_for("KR", "SWING"), config.profile_for("US", "SWING")
    assert kr["domains"]["TECHNICAL"] == {} and kr["reference"]["TECHNICAL"] == us["domains"]["TECHNICAL"] and sum(us["domains"]["TECHNICAL"].values()) == 40
    assert {d: kr["domains"][d] for d in ("FUNDAMENTAL", "RISK", "EVENTS")} == {d: us["domains"][d] for d in ("FUNDAMENTAL", "RISK", "EVENTS")}
    assert all(not p["reference"] for k, p in config.PROFILES.items() if k != "KR_SWING_V2")
    assert sum(sum(v.values()) for v in config.profile_for("KR", "LONG_TERM")["domains"].values()) == 100 and config.MODEL_VERSION == "QSF-1.3.2"


def test_the_technical_value_cannot_move_the_korean_swing_score(monkeypatch):
    fixed_tech(monkeypatch, 1.0)
    high = engine.score(ctx(), "SWING")
    fixed_tech(monkeypatch, 0.0)
    low = engine.score(ctx(), "SWING")
    assert high["profile"] == "KR_SWING_V2" and high["score"] is not None and high["score"] == low["score"] and high["coverage"] == low["coverage"]
    scored = [r for r in high["factors"] if r.get("scored") is not False and r["contribution"] is not None]
    assert high["score"] == pytest.approx(100 * sum(r["contribution"] for r in scored) / sum(r["weight"] for r in scored)) and all(r["domain"] != "TECHNICAL" for r in scored)
    fixed_tech(monkeypatch, 1.0)
    us_high = engine.score(ctx("US"), "SWING")["score"]
    fixed_tech(monkeypatch, 0.0)
    assert us_high > engine.score(ctx("US"), "SWING")["score"]                       # the US swing score still counts it


def test_reference_rows_are_kept_with_their_values_and_no_weight(monkeypatch):
    fixed_tech(monkeypatch, 0.75)
    res = engine.score(ctx(), "SWING")
    ref = [r for r in res["factors"] if r["domain"] == "TECHNICAL"]
    assert [r["factor"] for r in ref] == list(TECH) and all(r["scored"] is False and r["weight"] == 0 and r["contribution"] is None and r["normalized"] == 0.75 for r in ref)
    assert sum(r["reference_weight"] for r in ref) == 40
    d = res["domains"]["TECHNICAL"]
    assert d["reference"] is True and d["max_points"] == 0 and d["points"] == 0 and d["score_100"] == pytest.approx(75.0) and d["coverage"] == 1.0
    assert "TECHNICAL" not in res["short_domains"] and not set(TECH) & set(res["missing"])
    assert all(x["factor"] not in TECH for x in res["top_positive"] + res["top_negative"])


def test_a_missing_reference_factor_is_empty_and_costs_no_coverage(monkeypatch):
    fixed_tech(monkeypatch, 0.5)
    with_tech = engine.score(ctx(), "SWING")
    for fid in TECH:
        monkeypatch.setitem(factors.CALC, fid, lambda c: factors.missing("없음"))
    without = engine.score(ctx(), "SWING")
    ref = [r for r in without["factors"] if r["domain"] == "TECHNICAL"]
    assert all(r["normalized"] is None and r["status"] == "MISSING" for r in ref) and without["domains"]["TECHNICAL"]["score_100"] is None
    assert without["score"] == with_tech["score"] and without["coverage"] == with_tech["coverage"] and without["actionability"] == with_tech["actionability"]


def test_the_us_swing_score_still_needs_its_technical_domain(monkeypatch):
    for fid in TECH:
        monkeypatch.setitem(factors.CALC, fid, lambda c: factors.missing("없음"))
    assert "TECHNICAL" in engine.score(ctx("US"), "SWING")["short_domains"]


def test_the_former_formula_is_recovered_from_the_rows(monkeypatch):
    fixed_tech(monkeypatch, 0.9)
    new = engine.score(ctx(), "SWING")
    us = config.profile_for("US", "SWING")
    former = {"id": "KR_SWING_V1", "market": "KR", "strategy": "SWING", "reference": {},
              "domains": {**{d: dict(v) for d, v in config.profile_for("KR", "SWING")["domains"].items()}, "TECHNICAL": dict(us["domains"]["TECHNICAL"])}}
    monkeypatch.setitem(config._LIVE, ("KR", "SWING"), former)
    old = engine.score(ctx(), "SWING")
    assert old["profile"] == "KR_SWING_V1" and old["score"] != new["score"]
    assert engine.prior_formula_score(new["factors"]) == pytest.approx(old["score"])
    assert engine.prior_formula_score(old["factors"]) == pytest.approx(old["score"]) and engine.prior_formula_score([]) is None


def test_the_ledger_keeps_the_reference_mark_and_the_challenger_equals_the_live_score(monkeypatch):
    fixed_tech(monkeypatch, 0.2)
    res = engine.score(ctx(), "SWING")
    snap = ledger.snapshot({**res, "ticker": "000001"})
    ref = [f for f in snap["factors"] if f["domain"] == "TECHNICAL"]
    assert all(f["scored"] is False and f["reference_weight"] > 0 and f["weight"] == 0 for f in ref) and all("scored" not in f for f in snap["factors"] if f["domain"] != "TECHNICAL")
    assert snap["domains"]["TECHNICAL"]["reference"] is True and "reference" not in snap["domains"]["RISK"] and snap["profile"] == "KR_SWING_V2"
    assert sc.challenger_score(snap["factors"]) == pytest.approx(res["score"])       # the former challenger is now the live score
    assert engine.prior_formula_score(snap["factors"]) == pytest.approx(engine.prior_formula_score(res["factors"]))
    us = ledger.snapshot({**engine.score(ctx("US"), "SWING"), "ticker": "AAA"})
    assert all("scored" not in f and "reference_weight" not in f for f in us["factors"]) and all("reference" not in v for v in us["domains"].values())


# ---------------------------------------------------------------------- the record of the former formula
def frow(domain, weight, normalized, scored=True):
    if scored:
        return {"factor": f"{domain}_{weight}", "domain": domain, "weight": weight, "status": "REAL", "normalized": normalized, "contribution": weight * normalized}
    return {"factor": f"{domain}_{weight}", "domain": domain, "weight": 0, "reference_weight": weight, "scored": False, "status": "REAL", "normalized": normalized, "contribution": None}


def snap(ticker, session, tech, risk, new=True, strategy="SWING", entry_status="ENTRY_NOW"):
    rows = [frow("TECHNICAL", 40, tech, scored=not new), frow("RISK", 20, risk), frow("FUNDAMENTAL", 10, 0.5)]
    live = 100 * (20 * risk + 5) / 30 if new else 100 * (40 * tech + 20 * risk + 5) / 70
    return {"market": "KR", "ticker": ticker, "strategy": strategy, "model_version": "QSF-1.2.0" if new else "QSF-1.1.9", "score": live, "data_date": session, "entry_session": "2026-11-12",
            "entry_status": entry_status, "actionability": "ACTIONABLE", "factors": rows}


def test_a_session_holds_both_scores_and_a_session_of_the_former_composition_is_refused():
    snaps = [snap(f"{k:06d}", "2026-11-11", tech=1.0, risk=k / 300) for k in range(250)] + [snap("999990", "2026-11-10", 0.5, 0.5), snap("999980", "2026-11-11", 0.5, 0.5, strategy="LONG_TERM")]
    doc = sp.score_session(snaps, "2026-11-11")
    r = doc["rows"][150]
    assert len(doc["rows"]) == 250 and doc["model_versions"] == ["QSF-1.2.0"] and r["entry_status"] == "ENTRY_NOW" and r["entry_session"] == "2026-11-12"
    assert r["live"] == pytest.approx(100 * (20 * 0.5 + 5) / 30, abs=1e-3) and r["prior"] == pytest.approx(100 * (40 * 1.0 + 20 * 0.5 + 5) / 70, abs=1e-3)
    with pytest.raises(ValueError, match="TOO_FEW_STOCKS"):
        sp.score_session(snaps[:100], "2026-11-11")
    with pytest.raises(ValueError, match="FORMER_COMPOSITION"):
        sp.score_session([snap(f"{k:06d}", "2026-11-10", 1.0, 0.5, new=False) for k in range(250)], "2026-11-10")


class FakeLedger:
    rows = [{"market": "KR", "session": "2026-11-10"}, {"market": "KR", "session": "2026-11-11"}, {"market": "KR", "session": "2026-11-12"}, {"market": "KR", "session": "2026-11-13"}, {"market": "US", "session": "2026-11-11"}]

    def __init__(self, root):
        pass

    def verify(self):
        return {"status": "OK"}

    def _live_rows(self):
        return self.rows

    def _load(self, r):
        if r["session"] == "2026-11-11":                        # recorded before the change went live
            return [snap(f"{k:06d}", r["session"], 0.5, k / 300, new=False) for k in range(250)]
        return [snap(f"{k:06d}", r["session"], 0.5, k / 300) for k in range(250 if r["session"] == "2026-11-12" else 50)]


def test_record_is_written_once_and_skips_what_the_former_composition_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(sp, "Ledger", FakeLedger)
    res = sp.record(tmp_path, now=lambda: NOW)
    assert res["status"] == "WAITING" and res["written"] == ["2026-11-12"] and res["partial"] == ["2026-11-13"] and res["former_composition"] == ["2026-11-11"]
    idx = kf.read_index(tmp_path, sp.FOLDER)
    assert len(idx) == 1 and idx[0]["stocks"] == 250 and kf.verify(tmp_path, sp.FOLDER)["status"] == "OK" and not (tmp_path / sc.FOLDER).exists()
    before = (tmp_path / sp.FOLDER / "2026-11-12.json.gz").read_bytes()
    assert sp.record(tmp_path, now=lambda: NOW)["written"] == [] and (tmp_path / sp.FOLDER / "2026-11-12.json.gz").read_bytes() == before
    assert sp.status(tmp_path) == {"records": 1, "first": "2026-11-12", "last": "2026-11-12", "late": 1, "samples_needed": 12, "horizon": 20, "evaluated": False}


class FakePanel:
    def __init__(self, n=400, names=60):
        self.dates = [f"d{i:04d}" for i in range(n)]
        self.col = {f"{k:06d}": k for k in range(names)}
        self.names = names

    def forward(self, i, h, cost=0.0):
        rng = np.random.default_rng(i)
        return np.linspace(-0.05, 0.05, self.names) + rng.normal(0, 0.01, self.names) - cost        # the higher the code, the better the return


def docs(n, names=60, live_knows=True, prior_knows=False):
    out = []
    for d in range(n):
        noise = np.random.default_rng(1000 + d).random((2, names)) * 100
        rows = [{"ticker": f"{k:06d}", "live": float(40 + k if live_knows else noise[0, k]), "prior": float(k if prior_knows else noise[1, k]), "entry_session": f"d{d + 1:04d}",
                 "entry_status": "ENTRY_NOW" if k >= 45 else "WAIT_FOR_PULLBACK"} for k in range(names)]
        out.append({"session": f"d{d:04d}", "rows": rows, "late": False})
    return out


def test_days_measure_both_scores_and_the_entry_reading():
    got = sp.measure_days(docs(40), FakePanel(n=50))
    assert len(got) == 30 and got[0]["entry"] == "d0001" and got[0]["ic_live"] > 0.9 and abs(got[0]["ic_prior"]) < 0.5
    assert got[0]["entry_gap"] > 0                                                    # watched stocks are codes 15 and up; the ready ones are the best of them
    thin = docs(40)
    for doc in thin:
        for r in doc["rows"]:
            r["entry_status"] = "ENTRY_NOW" if r["ticker"] >= "000058" else "WAIT_FOR_PULLBACK"
    assert sp.measure_days(thin, FakePanel(n=50))[0]["entry_gap"] is None             # two ready stocks are not a group


def test_the_verdict_tells_the_two_scores_apart_only_with_a_clear_lead():
    px = FakePanel()
    assert sp.verdict(sp.measure_days(docs(300), px)[::sp.HORIZON])["verdict"] == "DECISION_SUPPORTED"
    back = sp.verdict(sp.measure_days(docs(300, live_knows=False, prior_knows=True), px)[::sp.HORIZON])
    assert back["verdict"] == "PRIOR_BETTER" and back["difference"]["mean"] < 0 and back["samples"] >= sp.MIN_SAMPLES
    same = [{"ic_live": 0.1 + 0.01 * (k % 3), "ic_prior": 0.1 + 0.01 * ((k + 1) % 3)} for k in range(12)]
    assert sp.verdict(same)["verdict"] == "NOT_DISTINGUISHED"
    assert sp.verdict([{"ic_live": 0.1, "ic_prior": 0.1}] * 12)["verdict"] == "NOT_DISTINGUISHED"       # no spread at all: no t-value, no verdict


def test_evaluation_is_refused_before_twelve_samples_and_runs_once(tmp_path, monkeypatch):
    monkeypatch.setattr(sp, "Ledger", FakeLedger)
    monkeypatch.setattr(FakeLedger, "rows", [{"market": "KR", "session": "2026-11-12"}])
    sp.record(tmp_path, now=lambda: NOW)
    with pytest.raises(RuntimeError, match="12개"):
        sp.evaluate_once(tmp_path, panel=FakePanel())
    (tmp_path / sp.REPORT).parent.mkdir(parents=True)
    (tmp_path / sp.REPORT).write_text(json.dumps({}))
    with pytest.raises(RuntimeError, match="한 번만"):
        sp.evaluate_once(tmp_path, panel=FakePanel())


def test_the_protocol_is_written_and_the_record_is_backed_up_and_wired_into_the_daily_step():
    root = Path(__file__).resolve().parents[1]
    text = (root / sp.PROTOCOL).read_text(encoding="utf-8")
    assert "DECISION_SUPPORTED" in text and "PRIOR_BETTER" in text and "NOT_DISTINGUISHED" in text and "12개" in text
    from terminal import automation
    assert "kr_swing_prior" in automation.FORWARD_STORES and any("kr_swing_prior/index.jsonl" in g for g in automation.BACKUP_GLOBS)
    app = (root / "app.py").read_text(encoding="utf-8")
    assert 'res["swing_prior"] = kr_swing_prior.record(PROJECT_ROOT)' in app and '"kr-swing-prior-evaluate"' in app
