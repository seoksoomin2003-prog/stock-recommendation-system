"""The Korean bundle challenger record (reports/QSF_KR_CHALLENGER_PROTOCOL.md): fixed bundles, written once, no early reading, four verdict words.  No network."""
import gzip
import json
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from terminal.qsf import config, kr_challenger as kc, kr_forward as kf, readings as rd

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 20, 1, tzinfo=timezone.utc)
PROFILE = {"SWING": "KR_SWING_V3", "LONG_TERM": "KR_LONG_TERM_V2"}


def counted(strategy):
    return [n for d in config.PROFILES[PROFILE[strategy]]["domains"].values() for n in d]


def reference(strategy):
    return [n for d in config.PROFILES[PROFILE[strategy]]["reference"].values() for n in d]


def snap(ticker, strategy, session, seed, score=60.0, drop=(), entry="2026-11-20", act="ACTIONABLE"):
    rng = np.random.default_rng(seed)
    factors = [{"factor": n, "normalized": None if n in drop else float(rng.random())} for n in counted(strategy) + reference(strategy)]
    return {"market": "KR", "ticker": ticker, "strategy": strategy, "data_date": session, "score": score, "model_version": "QSF-1.4.1", "actionability": act, "entry_session": entry, "factors": factors}


def day_snaps(session, n=220):
    return [snap(f"{i:06d}", s, session, zlib.crc32(f"{i}{s}{session}".encode())) for i in range(n) for s in ("SWING", "LONG_TERM")]


# ---------------------------------------------------------------------- the score
def test_bundles_hold_only_signals_the_live_korean_score_counts():
    for strategy, bundles in kc.BUNDLES.items():
        names = [n for b in bundles for n in b]
        assert len(names) == len(set(names)) and set(names) <= set(counted(strategy)) and not set(names) & set(reference(strategy)), strategy
    assert len(kc.BUNDLES["SWING"]) == 9 and len(kc.BUNDLES["LONG_TERM"]) == 5
    assert "insider_activity" not in sum(kc.BUNDLES["SWING"], []) and "trend_structure" not in sum(kc.BUNDLES["SWING"], [])       # empty in Korea; reference only since QSF-1.2.0
    assert not {"governance", "insider_ownership", "capital_allocation"} & set(sum(kc.BUNDLES["LONG_TERM"], []))
    assert ["atr_risk", "drawdown_gap"] in kc.BUNDLES["SWING"] and "valuation" in kc.BUNDLES["LONG_TERM"][0]


def test_every_bundle_weighs_the_same_whatever_its_size():
    def row(t, big, small):
        s = {"ticker": t, "score": 50.0, "factors": []}
        for b in kc.BUNDLES["LONG_TERM"]:
            s["factors"] += [{"factor": n, "normalized": big if len(b) > 1 else small} for n in b]
        return s
    got = {r["ticker"]: r for r in kc.score_strategy([row("A", 1.0, 0.0), row("B", 0.0, 1.0)], "LONG_TERM")}
    assert got["A"]["score"] == pytest.approx(60.0) and got["B"]["score"] == pytest.approx(40.0)      # three bundles of several signals, two of one: 3/5 and 2/5
    assert got["A"]["bundles"] == [100.0, 100.0, 100.0, 0.0, 0.0] and got["A"]["strategy"] == "LONG_TERM"


def test_an_empty_value_stays_empty_and_too_few_bundles_give_no_score():
    names = [n for b in kc.BUNDLES["SWING"] for n in b]
    full = [{"ticker": f"T{k}", "score": 50.0, "factors": [{"factor": n, "normalized": k / 10} for n in names]} for k in range(10)]
    full[0]["factors"] = [f if f["factor"] != "atr_risk" else {"factor": "atr_risk", "normalized": None} for f in full[0]["factors"]]
    full[1]["factors"] = [f if f["factor"] in ("liquidity", "risk_reward", "profitability", "balance_sheet", "material_disclosures", "earnings_calendar") else {"factor": f["factor"], "normalized": None}
                          for f in full[1]["factors"]]
    full[2]["factors"] = [f if f["factor"] in ("liquidity", "risk_reward", "profitability") else {"factor": f["factor"], "normalized": None} for f in full[2]["factors"]]
    got = kc.score_strategy(full, "SWING")
    assert got[0]["score"] is not None and got[0]["bundles"][5] is not None      # half of the two-signal bundle is enough
    assert got[1]["score"] is None and got[1]["bundles"][5] is None              # six of nine bundles is under 70%
    assert got[2]["score"] is None and got[9]["score"] == pytest.approx(100.0)


def test_a_session_holds_both_strategies_and_refuses_a_partial_day():
    snaps = day_snaps("2026-11-18") + [snap("999990", "SWING", "2026-11-17", 1), snap("999980", "SWING", "2026-11-18", 2, score=None)]
    doc = kc.score_session(snaps, "2026-11-18")
    assert len(doc["rows"]) == 440 and {r["strategy"] for r in doc["rows"]} == {"SWING", "LONG_TERM"} and doc["model_versions"] == ["QSF-1.4.1"]
    assert doc["bundles"] == kc.BUNDLES and doc["rows"][0]["entry_session"] == "2026-11-20" and not {"999990", "999980"} & {r["ticker"] for r in doc["rows"]}
    assert all(0 <= r["score"] <= 100 and len(r["bundles"]) == (9 if r["strategy"] == "SWING" else 5) for r in doc["rows"])
    with pytest.raises(ValueError, match="TOO_FEW_STOCKS"):
        kc.score_session(day_snaps("2026-11-18", n=150), "2026-11-18")


# ---------------------------------------------------------------------- the record
class FakeLedger:
    rows = [{"market": "KR", "session": "2026-11-17"}, {"market": "KR", "session": "2026-11-18"}, {"market": "KR", "session": "2026-11-19"}, {"market": "KR", "session": "2026-11-20"},
            {"market": "US", "session": "2026-11-18"}]
    state = "OK"

    def __init__(self, root):
        pass

    def verify(self):
        return {"status": self.state}

    def _live_rows(self):
        return self.rows

    def _load(self, r):
        return day_snaps(r["session"], n=50 if r["session"] == "2026-11-20" else 220)


def test_record_starts_at_the_first_session_is_written_once_and_waits_for_a_partial_day(tmp_path, monkeypatch):
    monkeypatch.setattr(kc, "Ledger", FakeLedger)
    res = kc.record(tmp_path, now=lambda: NOW)
    assert res == {"status": "WAITING", "written": ["2026-11-18", "2026-11-19"], "partial": ["2026-11-20"], "last": "2026-11-19", "sessions_in_ledger": 3}
    idx = kf.read_index(tmp_path, kc.FOLDER)
    assert [r["session"] for r in idx] == ["2026-11-18", "2026-11-19"] and idx[0]["stocks"] == 440 and [r["late"] for r in idx] == [True, True]
    assert kf.verify(tmp_path, kc.FOLDER)["status"] == "OK" and not (tmp_path / kc.FOLDER / "2026-11-17.json.gz").exists()
    before = (tmp_path / kc.FOLDER / "2026-11-18.json.gz").read_bytes()
    assert kc.record(tmp_path, now=lambda: NOW)["written"] == [] and (tmp_path / kc.FOLDER / "2026-11-18.json.gz").read_bytes() == before
    st = kc.status(tmp_path)
    assert st["records"] == 2 and st["first"] == "2026-11-18" and st["needed"] == {"SWING": 240, "LONG_TERM": 756} and st["evaluated"] == {"SWING": False, "LONG_TERM": False}
    with gzip.open(tmp_path / kc.FOLDER / "2026-11-18.json.gz", "wt", encoding="utf-8") as fh:
        json.dump({"edited": True}, fh)
    assert kf.verify(tmp_path, kc.FOLDER)["status"] != "OK"


def test_the_newest_ledger_session_is_not_late_and_a_broken_ledger_records_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(kc, "Ledger", FakeLedger)
    monkeypatch.setattr(FakeLedger, "rows", [{"market": "KR", "session": "2026-11-18"}])
    assert kc.record(tmp_path, now=lambda: NOW)["status"] == "OK" and kf.read_index(tmp_path, kc.FOLDER)[0]["late"] is False
    monkeypatch.setattr(FakeLedger, "state", "BROKEN")
    assert kc.record(tmp_path / "other", now=lambda: NOW) == {"status": "FAILED", "reason": "LEDGER_BROKEN"} and not (tmp_path / "other" / kc.FOLDER).exists()


# ---------------------------------------------------------------------- the one reading
class FakePanel:
    """Closes that drift by the stock's number; the open of a day is the close before it.  The last column is the KOSPI index."""

    def __init__(self, n, tickers, drift=lambda k: 0.0002 * k, seed=3):
        rng = np.random.default_rng(seed)
        self.dates = [f"d{i:04d}" for i in range(n)]
        self.symbols = list(tickers) + [kc.INDEX]
        self.col = {s: j for j, s in enumerate(self.symbols)}
        step = rng.normal(0, 0.01, (n, len(self.symbols))) + np.array([drift(k) for k in range(len(tickers))] + [0.0])
        self.data = {"close": 100 * np.cumprod(1 + step, axis=0)}

    def forward(self, i, h, cost=0.0):
        c = self.data["close"]
        out = np.full(len(self.symbols), np.nan) if i + h >= len(self.dates) else c[i + h] / c[i] - 1 - cost
        out[-1] = np.nan
        return out


def write_records(base, days, tickers, challenger, live, entry=lambda d: f"d{d + 1:04d}", act=lambda k: "ACTIONABLE"):
    folder = base / kc.FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    for d in days:
        rows = [{"strategy": s, "ticker": t, "score": challenger(k, d), "bundles": [], "live": live(k, d), "actionability": act(k), "entry_session": entry(d)}
                for s in ("SWING", "LONG_TERM") for k, t in enumerate(tickers)]
        doc = {"session": f"d{d:04d}", "rows": rows, "recorded_at": NOW.isoformat(), "late": d % 10 == 0, "before_next_open": True}
        with gzip.open(folder / f"d{d:04d}.json.gz", "wt", encoding="utf-8") as fh:
            json.dump(doc, fh)
        kf._append_index(folder, f"d{d:04d}", doc["recorded_at"], doc["late"], True, len(rows))


TICKERS = [f"{k:06d}" for k in range(60)]
KNOWS = lambda k, d: float(k)                                                    # noqa: E731
NOISE = lambda k, d: float((k * 7 + zlib.crc32(str(d).encode())) % 60)           # noqa: E731


def test_the_reading_is_refused_until_enough_sessions_matured(tmp_path):
    write_records(tmp_path, range(239), TICKERS, KNOWS, NOISE)
    with pytest.raises(RuntimeError, match="만기 거래일 239개, 기준 240개"):
        kc.evaluate_once(tmp_path, "SWING", panel=FakePanel(290, TICKERS))
    with pytest.raises(RuntimeError, match="기준 756개"):
        kc.evaluate_once(tmp_path, "LONG_TERM", panel=FakePanel(400, TICKERS))
    assert not (tmp_path / kc.REPORTS["SWING"]).exists() and not (tmp_path / kc.REPORTS["LONG_TERM"]).exists()


def test_a_record_whose_hold_has_not_ended_does_not_count(tmp_path):
    write_records(tmp_path, range(260), TICKERS, KNOWS, NOISE)
    with pytest.raises(RuntimeError, match="만기 거래일 230개"):                 # 250 dates: records 0..229 have their 20th close
        kc.evaluate_once(tmp_path, "SWING", panel=FakePanel(250, TICKERS))


def test_the_reading_runs_once_uses_the_first_240_matured_records_and_names_the_better_score(tmp_path):
    write_records(tmp_path, range(270), TICKERS, KNOWS, NOISE)
    res = kc.evaluate_once(tmp_path, "SWING", panel=FakePanel(300, TICKERS))
    assert res["status"] == "EVALUATED" and res["horizon"] == 20 and res["records_used"] == 240 and res["dates"] == 48 and res["first"] == "d0000" and res["last"] == "d0235"
    assert res["verdict"] == "CHALLENGER_BETTER" and res["challenger"]["verdict"] == "WEAK_POSITIVE_EVIDENCE" and res["challenger"]["ic"] > res["live"]["ic"]
    assert res["paired_ic"]["mean"] > 0 and res["paired_ic"]["t"] >= 2.0 and res["cost"] == config.round_trip_cost("KR") and res["late_share"] == pytest.approx(24 / 240)
    assert set(res["challenger"]["top_fifth_path"]) >= {"top_fifth", "kospi", "sample_average", "early", "late", "beats_kospi_in_both_halves"}
    assert res["challenger"]["top_fifth_path"]["top_fifth"] > res["challenger"]["top_fifth_path"]["sample_average"] and res["samples_a_horizon_apart"]["samples"] == 12
    assert "ic_spy_above_200d" not in res["challenger"] and res["one_day_later_entry_ic"] > 0
    why = res["reasons"]
    assert len(why) == 4 and why[0].startswith("잰 것: d0000~d0235 기록 중 48일") and "도전자: 평균 IC +" in why[1] and "5개 조건을 모두 채웠습니다" in why[1]
    assert why[2].startswith("라이브: 평균 IC") and "IC 차이(도전자 − 라이브): 평균 +" in why[3]
    assert json.loads((tmp_path / kc.REPORTS["SWING"]).read_text(encoding="utf-8"))["verdict"] == "CHALLENGER_BETTER"
    with pytest.raises(RuntimeError, match="이미 평가"):
        kc.evaluate_once(tmp_path, "SWING", panel=FakePanel(300, TICKERS))


def test_the_reading_says_so_when_the_live_score_ranked_better(tmp_path):
    write_records(tmp_path, range(260), TICKERS, NOISE, KNOWS)
    res = kc.evaluate_once(tmp_path, "SWING", panel=FakePanel(290, TICKERS))
    assert res["verdict"] == "LIVE_BETTER" and res["paired_ic"]["mean"] < 0 and res["paired_ic"]["t"] <= -2.0 and "걸린 조건: " in res["reasons"][1]


def test_equal_scores_are_never_called_better(tmp_path):
    write_records(tmp_path, range(260), TICKERS, KNOWS, KNOWS)
    res = kc.evaluate_once(tmp_path, "SWING", panel=FakePanel(290, TICKERS))
    assert res["paired_ic"]["mean"] == pytest.approx(0.0) and res["verdict"] == "CHALLENGER_HAS_EVIDENCE"


def test_stocks_without_enough_data_and_days_with_mixed_entry_sessions_are_left_out(tmp_path):
    write_records(tmp_path, range(270), TICKERS, KNOWS, NOISE, act=lambda k: "INSUFFICIENT_DATA" if k < 10 else "ACTIONABLE",
                  entry=lambda d: None if d == 3 else f"d{d + 1:04d}")
    res = kc.evaluate_once(tmp_path, "SWING", panel=FakePanel(300, TICKERS))
    assert res["challenger"]["mean_stocks"] == pytest.approx(50.0) and res["first"] == "d0000" and res["last"] == "d0236" and res["records_used"] == 240


def test_the_four_verdict_words():
    better = {"supports_challenger": True, "mean": 0.03, "t": 2.5, "early": 0.02, "late": 0.04}
    worse = {"supports_challenger": False, "mean": -0.03, "t": -2.5, "early": -0.02, "late": -0.04}
    flat = {"supports_challenger": False, "mean": 0.01, "t": 0.8, "early": 0.02, "late": -0.01}
    assert kc.verdict(True, better) == "CHALLENGER_BETTER" and kc.verdict(False, better) == "NO_EVIDENCE"        # a lead without the challenger's own evidence is not a verdict
    assert kc.verdict(True, worse) == "LIVE_BETTER" and kc.verdict(False, worse) == "LIVE_BETTER"
    assert kc.verdict(True, flat) == "CHALLENGER_HAS_EVIDENCE" and kc.verdict(False, flat) == "NO_EVIDENCE"
    assert kc.verdict(False, {**worse, "t": -1.9}) == "NO_EVIDENCE" and kc.verdict(False, {**worse, "late": 0.01}) == "NO_EVIDENCE"
    assert kc.verdict(False, {"supports_challenger": False, "mean": None, "t": None, "early": None, "late": None}) == "NO_EVIDENCE"


# ---------------------------------------------------------------------- wiring
def test_the_rules_are_written_and_the_record_is_wired_backed_up_watched_and_read_by_itself():
    text = (ROOT / kc.PROTOCOL).read_text(encoding="utf-8")
    for word in ("CHALLENGER_BETTER", "LIVE_BETTER", "CHALLENGER_HAS_EVIDENCE", "NO_EVIDENCE", "2026-11-18", "research_data/kr_challenger/", "자동으로 바꾸지 않는다"):
        assert word in text, word
    for strategy, bundles in kc.BUNDLES.items():                                 # the code's bundles are the document's
        for b in bundles:
            assert ", ".join(f"`{n}`" for n in b) in text, b
    from terminal import automation, store_watch
    assert "kr_challenger" in automation.FORWARD_STORES and any("kr_challenger/index.jsonl" in g for g in automation.BACKUP_GLOBS)
    assert store_watch.LABELS["kr_challenger"] == "한국 묶음 도전자 점수" and store_watch.market_of("kr_challenger") == "KR"
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'res["bundle_challenger"] = kr_challenger.record(PROJECT_ROOT)' in app and '"kr-challenger-evaluate-swing"' in app and '"kr-challenger-evaluate-long"' in app
    by = {e["key"]: e for e in rd.REGISTRY}
    for key, strategy in (("kr_challenger_swing", "SWING"), ("kr_challenger_long", "LONG_TERM")):
        e = by[key]
        assert e["report"] == kc.REPORTS[strategy].name and e["store"] == kc.FOLDER.name and e["horizon"] == kc.HORIZONS[strategy] and e["need"] == 12 * kc.HORIZONS[strategy]
        assert e["protocol"] == kc.PROTOCOL and "자동으로 바뀌지 않습니다" in e["after"]
    assert "kr_challenger:" in (ROOT / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")


def test_the_notice_and_the_screen_carry_the_reasons(tmp_path):
    e = {x["key"]: x for x in rd.REGISTRY}["kr_challenger_swing"]
    rep = {"verdict": "LIVE_BETTER", "reasons": ["잰 것: 가~나.", "IC 차이(도전자 − 라이브): 평균 -0.030."]}
    text = rd.text(e, rep)
    assert "[판정 · 한국 묶음 도전자 점수 · 스윙] LIVE_BETTER" in text and "지금 공식(사람이 정한 배점)이 도전자 공식보다 나았습니다." in text
    assert "잰 것: 가~나." in text and "평균 -0.030." in text and "자동으로 바뀌지 않습니다" in text
    assert rd.why({"verdict": "X"}) == [] and rd.why({"reasons": "한 줄"}) == []
    (tmp_path / rd.REPORTS).mkdir(parents=True)
    (tmp_path / rd.REPORTS / e["report"]).write_text(json.dumps(rep), encoding="utf-8")
    from datetime import date
    row = {r["key"]: r for r in rd.status(tmp_path, date(2027, 12, 20))["readings"]}["kr_challenger_swing"]
    assert row["state"] == "READ" and row["verdict"] == "LIVE_BETTER" and row["reasons"] == rep["reasons"]
