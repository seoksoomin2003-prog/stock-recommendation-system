"""QSF-1.4.0: the regime domain out of every score, the market state shown apart, the size rule of an adverse US day, and the record
of the former formula (reports/QSF_SCORE_SPLIT_PROTOCOL.md).  All offline, made-up data."""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from terminal import automation
from terminal.qsf import config, engine, factors, kr_forward as kf, ledger, order_plan as op, paper_book as pb, score_split as ss

NOW = datetime(2026, 11, 17, 22, 30, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]
REGIME = {"US": ("vix_regime", "vix_term", "credit_spread", "index_trend_breadth"), "KR": ("vkospi_regime", "index_trend", "breadth", "usdkrw_regime", "credit_liquidity")}


def bars(n=320, drift=0.001):
    out, px = [], 10000.0
    for i in range(n):
        px *= 1 + drift + 0.01 * np.sin(i / 7.0)
        out.append({"date": f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": px * 0.995, "high": px * 1.01, "low": px * 0.985, "close": px, "adj_close": px, "volume": 500000.0})
    return out


def ctx(market="US"):
    return {"market": market, "ticker": "AAA", "bars": bars(), "fund": None, "regime": {}, "events": None, "earnings": {}, "price_fresh": True}


def fixed_regime(monkeypatch, market, value, missing=()):
    for fid in REGIME[market]:
        monkeypatch.setitem(factors.CALC, fid, (lambda c: factors.missing("없음")) if fid in missing else (lambda c, v=value: factors.obs(v, {}, "고정값", "시험", "2026-11-16")))


# ---------------------------------------------------------------------- the score and the market state
@pytest.mark.parametrize("market,strategy", [("US", "SWING"), ("US", "LONG_TERM"), ("KR", "SWING"), ("KR", "LONG_TERM")])
def test_the_regime_value_cannot_move_any_score(monkeypatch, market, strategy):
    fixed_regime(monkeypatch, market, 1.0)
    high = engine.score(ctx(market), strategy)
    fixed_regime(monkeypatch, market, 0.0)
    low = engine.score(ctx(market), strategy)
    assert high["score"] is not None and high["score"] == low["score"] and high["coverage"] == low["coverage"] and high["band"] == low["band"]
    assert high["market_state"]["score_100"] == pytest.approx(100.0) and low["market_state"]["score_100"] == pytest.approx(0.0)
    rows = [r for r in high["factors"] if r["domain"] == "REGIME"]
    assert [r["factor"] for r in rows] == list(REGIME[market]) and all(r["scored"] is False and r["weight"] == 0 and r["contribution"] is None for r in rows)
    d = high["domains"]["REGIME"]
    assert d["reference"] is True and d["max_points"] == 0 and d["points"] == 0 and d["score_100"] == pytest.approx(100.0)
    assert all(x["factor"] not in REGIME[market] for x in high["top_positive"] + high["top_negative"]) and high["model_version"] == "QSF-1.4.1"


def test_one_market_state_for_both_cards_and_from_the_ledger(monkeypatch):
    for fid, v in zip(REGIME["US"], (0.2, 0.9, 0.4, 0.8)):
        monkeypatch.setitem(factors.CALC, fid, lambda c, v=v: factors.obs(v, {}, "고정값", "시험", "2026-11-16"))
    swing, long_ = engine.score(ctx(), "SWING"), engine.score(ctx(), "LONG_TERM")
    want = 100 * (5 * 0.2 + 4 * 0.9 + 4 * 0.4 + 7 * 0.8) / 20                    # the swing weights, whichever card it is read from
    assert swing["market_state"]["score_100"] == pytest.approx(want) == pytest.approx(long_["market_state"]["score_100"])
    assert swing["domains"]["REGIME"]["score_100"] == pytest.approx(want) and long_["domains"]["REGIME"]["score_100"] != pytest.approx(want)   # the long card's own reference reading uses its former weights
    snap = ledger.snapshot({**long_, "ticker": "AAA"})
    assert engine.market_state(snap["factors"], "US")["score_100"] == pytest.approx(want)
    ms = swing["market_state"]
    assert ms["state"] == "FAVOURABLE" and ms["label"] == "좋음" and ms["size_factor"] == 1.0 and ms["mid"] == 50.0 and len(ms["factors"]) == 4 and "위험 표시" in ms["note"]


def test_an_adverse_day_halves_the_size_in_the_us_only_and_missing_is_not_zero(monkeypatch):
    fixed_regime(monkeypatch, "US", 0.3)
    us = engine.score(ctx(), "SWING")["market_state"]
    assert us["state"] == "ADVERSE" and us["label"] == "나쁨" and us["size_factor"] == 0.5 and us["score_100"] == pytest.approx(30.0)
    fixed_regime(monkeypatch, "KR", 0.3, missing=("vkospi_regime", "credit_liquidity"))
    kr = engine.score(ctx("KR"), "SWING")["market_state"]
    assert kr["state"] == "ADVERSE" and kr["size_factor"] == 1.0 and kr["score_100"] == pytest.approx(30.0) and kr["coverage"] == pytest.approx(12 / 20)
    assert [f["normalized"] for f in kr["factors"]] == [None, 0.3, 0.3, 0.3, None] and "구분되지 않았습니다" in kr["note"]
    fixed_regime(monkeypatch, "US", 0.5)
    assert engine.score(ctx(), "SWING")["market_state"]["state"] == "FAVOURABLE"       # the middle itself is not adverse
    fixed_regime(monkeypatch, "US", 0.5, missing=REGIME["US"])
    none = engine.score(ctx(), "SWING")["market_state"]
    assert none["score_100"] is None and none["state"] is None and none["size_factor"] == 1.0 and none["label"] == "자료 없음"
    assert config.ADVERSE_SIZE_FACTOR == {"US": 0.5} and config.MARKET_STATE_MID == 50.0


def test_the_former_formula_is_recovered_from_the_rows(monkeypatch):
    for market, strategy in (("US", "SWING"), ("US", "LONG_TERM"), ("KR", "SWING"), ("KR", "LONG_TERM")):
        fixed_regime(monkeypatch, market, 0.9)
        new = engine.score(ctx(market), strategy)
        live = config.profile_for(market, strategy)
        former = {"id": "FORMER", "market": market, "strategy": strategy, "reference": {k: v for k, v in live["reference"].items() if k != "REGIME"},
                  "domains": {**{d: dict(v) for d, v in live["domains"].items()}, "REGIME": dict(live["reference"]["REGIME"])}}
        monkeypatch.setitem(config._LIVE, (market, strategy), former)
        old = engine.score(ctx(market), strategy)
        monkeypatch.setitem(config._LIVE, (market, strategy), live)
        assert old["score"] != new["score"] and engine.formula_score(new["factors"], ss.COUNTED_AGAIN) == pytest.approx(old["score"])
        assert engine.formula_score(ledger.snapshot({**new, "ticker": "AAA"})["factors"], ss.COUNTED_AGAIN) == pytest.approx(old["score"])
    kr = engine.score(ctx("KR"), "SWING")
    assert engine.prior_formula_score(kr["factors"]) != pytest.approx(engine.formula_score(kr["factors"], ss.COUNTED_AGAIN))     # the 2026-11-11 formula also counted the technical domain
    assert engine.formula_score([], ss.COUNTED_AGAIN) is None


# ---------------------------------------------------------------------- the order plan
def cand(ticker, style="SWING", score=60.0, close=100.0, atr=2.0, adv=1e10):
    return {"ticker": ticker, "name": ticker, "sector": None, "style": style, "score": score, "close": close, "atr": atr, "stop": close - (2 if style == "SWING" else 5) * atr,
            "target": None, "adv_value": adv, "session": "2026-11-16"}


def account(equity=100_000.0):
    return {"equity": equity, "cash": equity, "positions": {}}


def state(market, value):
    rows = [{"factor": f, "domain": "REGIME", "status": "REAL", "normalized": value} for f in REGIME[market]]
    return engine.market_state(rows, market)


def test_an_adverse_us_day_makes_every_new_order_at_most_half(monkeypatch):
    usual = op.build([cand("A"), cand("W", atr=6.0)], account(), "US")
    half = op.build([cand("A"), cand("W", atr=6.0)], account(), "US", state=state("US", 0.3))
    a, w = usual["orders"]
    ha, hw = half["orders"]
    # US swing: 1% risk and 10% weight.  A: 4 stop distance -> 250 by risk, 100 by weight.  W: 12 stop distance -> 83 by risk.
    assert (a["shares"], a["binding"], w["shares"], w["binding"]) == (100, "WEIGHT", 83, "RISK")
    assert (ha["shares"], ha["binding"], hw["shares"], hw["binding"]) == (50, "WEIGHT", 41, "RISK")
    assert usual["size_factor"] == 1.0 and usual["market_state"] is None and half["size_factor"] == 0.5 and half["market_state"]["state"] == "ADVERSE"
    assert op.build([cand("A")], account(), "US", state=state("US", 0.8))["orders"][0]["shares"] == 100
    long_usual, long_half = (op.build([cand("L", "LONG")], account(), "US", state=s)["orders"][0] for s in (None, state("US", 0.1)))
    assert long_half["shares"] * 2 == long_usual["shares"] and long_usual["binding"] == long_half["binding"]


def test_korea_shows_the_state_and_changes_no_size():
    usual = op.build([cand("A", close=10_000.0, atr=200.0)], account(10_000_000.0), "KR")
    adverse = op.build([cand("A", close=10_000.0, atr=200.0)], account(10_000_000.0), "KR", state=state("KR", 0.1))
    assert adverse["orders"][0]["shares"] == usual["orders"][0]["shares"] == 100 and adverse["size_factor"] == 1.0 and adverse["market_state"]["state"] == "ADVERSE"


def lsnap(ticker, strategy, session, regime, split=True, score=60.0, market="US"):
    """A ledger snapshot: one scored row and the market's regime rows, as reference rows when written by QSF-1.4.0."""
    weights = config.MARKET_STATE_WEIGHTS[market] if strategy == "SWING" else {k: w / 2 for k, w in config.MARKET_STATE_WEIGHTS[market].items()}
    rows = [{"factor": "risk", "domain": "RISK", "weight": 20, "status": "REAL", "normalized": score / 100, "contribution": 20 * score / 100}]
    for fid, w in weights.items():
        rows.append({"factor": fid, "domain": "REGIME", "weight": 0, "reference_weight": w, "scored": False, "status": "REAL", "normalized": regime, "contribution": None} if split
                    else {"factor": fid, "domain": "REGIME", "weight": w, "status": "REAL", "normalized": regime, "contribution": w * regime})
    total = sum(weights.values())
    live = score if split else 100 * (20 * score / 100 + total * regime) / (20 + total)
    return {"market": market, "ticker": ticker, "strategy": strategy, "model_version": "QSF-1.4.0" if split else "QSF-1.3.2", "score": live, "data_date": session,
            "entry_session": "2026-11-18", "entry_status": "ENTRY_NOW", "actionability": "ACTIONABLE", "price": 100.0, "stop": 96.0, "target": 106.0, "factors": rows}


def test_the_plan_reads_the_state_of_its_own_session():
    snaps = [lsnap("OLD", "SWING", "2026-11-13", 0.9), lsnap("L", "LONG_TERM", "2026-11-16", 0.2), lsnap("S", "SWING", "2026-11-16", 0.2)]
    got = op.market_state(snaps, "US", "2026-11-16")
    assert got["score_100"] == pytest.approx(20.0) and got["state"] == "ADVERSE" and got["size_factor"] == 0.5 and got["session"] == "2026-11-16"
    assert op.market_state(snaps[:2], "US", "2026-11-16")["score_100"] == pytest.approx(20.0)        # only a long card that day: the same reading
    assert op.market_state(snaps, "US", "2026-11-14") is None
    old = op.market_state([lsnap("S", "SWING", "2026-11-13", 0.2, split=False)], "US", "2026-11-13")   # a session recorded before the split still has its regime rows
    assert old["score_100"] == pytest.approx(20.0)


# ---------------------------------------------------------------------- the record of the former formula
def test_a_session_holds_both_scores_and_one_recorded_before_the_split_is_refused():
    day = "2026-11-17"
    snaps = [lsnap(f"T{k:03d}", "SWING", day, 0.25, score=40 + k / 10) for k in range(250)] + [lsnap(f"T{k:03d}", "LONG_TERM", day, 0.25, score=50.0) for k in range(100)] + [lsnap("STALE", "SWING", "2026-11-16", 0.9)]
    doc = ss.score_session(snaps, day, "US")
    assert len(doc["rows"]) == 350 and doc["model_versions"] == ["QSF-1.4.0"] and doc["market_state"] == {"score_100": pytest.approx(25.0), "state": "ADVERSE", "size_factor": 0.5, "coverage": 1.0}
    r = next(x for x in doc["rows"] if x["ticker"] == "T100" and x["strategy"] == "SWING")
    assert r["live"] == pytest.approx(50.0) and r["with_regime"] == pytest.approx(100 * (20 * 0.5 + 20 * 0.25) / 40, abs=1e-3) and r["entry_session"] == "2026-11-18" and r["actionability"] == "ACTIONABLE"
    lg = next(x for x in doc["rows"] if x["ticker"] == "T050" and x["strategy"] == "LONG_TERM")
    assert lg["with_regime"] == pytest.approx(100 * (20 * 0.5 + 10 * 0.25) / 30, abs=1e-3)
    with pytest.raises(ss.NotReady, match="TOO_FEW_STOCKS"):
        ss.score_session(snaps[:100], day, "US")
    with pytest.raises(ss.NotReady, match="FORMER_COMPOSITION"):
        ss.score_session([lsnap(f"T{k:03d}", "SWING", day, 0.25, split=False) for k in range(250)], day, "US")


class FakeLedger:
    rows = [{"market": "US", "session": "2026-11-13"}, {"market": "US", "session": "2026-11-16"}, {"market": "US", "session": "2026-11-17"}, {"market": "US", "session": "2026-11-18"}, {"market": "KR", "session": "2026-11-17"}]

    def __init__(self, root):
        pass

    def verify(self):
        return {"status": "OK"}

    def _live_rows(self):
        return self.rows

    def _load(self, r):
        if r["session"] == "2026-11-16":                        # recorded before the change went live
            return [lsnap(f"T{k:03d}", "SWING", r["session"], 0.5, split=False) for k in range(250)]
        return [lsnap(f"T{k:03d}", "SWING", r["session"], 0.5, market=r["market"]) for k in range(250 if r["session"] == "2026-11-17" else 50)]


def test_record_is_written_once_and_skips_what_was_recorded_before_the_split(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "Ledger", FakeLedger)
    res = ss.record(tmp_path, "US", now=lambda: NOW)
    assert res["status"] == "WAITING" and res["written"] == ["2026-11-17"] and res["partial"] == ["2026-11-18"] and res["former_composition"] == ["2026-11-16"] and res["sessions"] == 1
    idx = kf.read_index(tmp_path, ss.FOLDERS["US"])
    assert len(idx) == 1 and idx[0]["stocks"] == 250 and kf.verify(tmp_path, ss.FOLDERS["US"])["status"] == "OK" and not (tmp_path / ss.FOLDERS["KR"]).exists()
    before = (tmp_path / ss.FOLDERS["US"] / "2026-11-17.json.gz").read_bytes()
    assert ss.record(tmp_path, "US", now=lambda: NOW)["written"] == [] and (tmp_path / ss.FOLDERS["US"] / "2026-11-17.json.gz").read_bytes() == before
    assert ss.record(tmp_path, "KR", now=lambda: NOW)["written"] == ["2026-11-17"]
    st = ss.status(tmp_path)
    assert st["markets"]["US"] == {"records": 1, "first": "2026-11-17", "last": "2026-11-17", "late": 1, "evaluated": False} and st["read_at"] == 240

    class Broken(FakeLedger):
        def verify(self):
            return {"status": "BROKEN"}
    monkeypatch.setattr(ss, "Ledger", Broken)
    assert ss.record(tmp_path, "US", now=lambda: NOW) == {"status": "FAILED", "reason": "LEDGER_BROKEN"}


class Panel:
    """Prices where a stock's 20-session return is its number over a thousand, and the 63-session one twice that."""
    def __init__(self, n_days, tickers):
        self.dates = [f"D{k:04d}" for k in range(n_days)]
        self.col = {t: j for j, t in enumerate(tickers)}

    def forward(self, i, h):
        return np.array([(1 if h == 20 else 2) * int(t[1:]) / 1000 for t in self.col], dtype=float)


def docs_for(n, tickers, with_regime_shift=-10.0, state="ADVERSE", every=1):
    """``every``: the former formula sits lower only on every such day; on the others the two bands are the same."""
    out = []
    for k in range(n):
        shift = with_regime_shift if k % every == 0 else 0.0
        rows = [{"ticker": t, "strategy": s, "live": 60.0 + int(t[1:]) / 2, "with_regime": 60.0 + int(t[1:]) / 2 + shift, "entry_session": f"D{k + 1:04d}", "actionability": "ACTIONABLE" if int(t[1:]) % 2 == 0 else "BLOCKED"}
                for t in tickers for s in ("SWING", "LONG_TERM")]
        out.append({"session": f"S{k:04d}", "market": "US", "market_state": {"state": state}, "rows": rows, "late": False})
    return out


def test_the_reading_holds_the_buy_band_of_each_formula():
    tickers = [f"T{k:03d}" for k in range(40)]
    px = Panel(400, tickers)
    days = ss.measure(docs_for(3, tickers), px, "US")
    cost = config.round_trip_cost("US")
    live = [int(t[1:]) / 1000 for t in tickers if 60 + int(t[1:]) / 2 >= 70 and int(t[1:]) % 2 == 0]      # T020..T038, even ones
    assert len(days) == 3 and days[0]["live"] == {"names": 10, "ret": pytest.approx(np.mean(live) - cost)} and days[0]["with_regime"] == {"names": 0, "ret": 0.0}
    assert days[0]["diff"] == pytest.approx(np.mean(live) - cost) and days[0]["state"] == "ADVERSE" and days[0]["ic_live"] == pytest.approx(1.0) == pytest.approx(days[0]["ic_with_regime"])
    s = ss.summarize(days, 20)
    assert s["with_regime"]["empty_share"] == 1.0 and s["live"]["empty_share"] == 0.0 and s["live"]["mean_names"] == 10 and s["by_state"]["ADVERSE"]["days"] == 3 and s["by_state"]["FAVOURABLE"]["days"] == 0
    assert ss.measure(docs_for(3, tickers), Panel(15, tickers), "US") == []                              # the outcome has not ended
    assert ss.measure(docs_for(3, tickers), Panel(400, tickers), "US", "LONG_TERM")[0]["live"]["ret"] == pytest.approx(2 * np.mean(live) - cost)
    assert ss.verdict({"mean": 0.01, "t": 2.5}) == "SPLIT_BETTER" and ss.verdict({"mean": -0.01, "t": -2.5}) == "WITH_REGIME_BETTER"
    assert ss.verdict({"mean": 0.01, "t": 1.9}) == ss.verdict({"mean": -0.01, "t": -1.0}) == ss.verdict({"mean": 0.01, "t": None}) == "NOT_DISTINGUISHED"


def test_the_one_reading_waits_for_240_days_and_runs_once(tmp_path, monkeypatch):
    tickers = [f"T{k:03d}" for k in range(40)]
    store = {}
    monkeypatch.setattr(ss.kf, "verify", lambda base, folder: {"status": "OK"})
    monkeypatch.setattr(ss.kf, "read_index", lambda base, folder: [{"session": d["session"]} for d in store["docs"]])
    monkeypatch.setattr(ss.kf, "_read_day", lambda folder, day: next(d for d in store["docs"] if d["session"] == day))
    store["docs"] = docs_for(100, tickers)
    with pytest.raises(RuntimeError, match="100개"):
        ss.evaluate_once(tmp_path, "US", Panel(500, tickers), log=lambda *_: None)
    assert not (tmp_path / ss.REPORTS["US"]).exists()
    store["docs"] = docs_for(250, tickers, every=2)
    res = ss.evaluate_once(tmp_path, "US", Panel(500, tickers), log=lambda *_: None)
    assert res["swing"]["days"] == 240 and res["last"] == "S0239" and res["long"]["reading"] == "FIGURES_ONLY" and res["long"]["days"] == 240
    assert res["verdict"] == "SPLIT_BETTER" and res["swing"]["difference"]["mean"] > 0 and res["swing"]["with_regime"]["empty_share"] == 0.5     # the former band was empty every other day
    assert json.loads((tmp_path / ss.REPORTS["US"]).read_text(encoding="utf-8"))["swing"]["live"]["mean_names"] == 10
    with pytest.raises(RuntimeError, match="다시 읽지 않습니다"):
        ss.evaluate_once(tmp_path, "US", Panel(500, tickers), log=lambda *_: None)
    monkeypatch.setattr(ss.kf, "verify", lambda base, folder: {"status": "BROKEN"})
    with pytest.raises(RuntimeError, match="검증"):
        ss.evaluate_once(tmp_path, "KR", Panel(500, tickers), log=lambda *_: None)


# ---------------------------------------------------------------------- wiring
def test_the_daily_job_the_backup_the_routes_and_the_page_know_the_split():
    assert {"score_split_kr", "score_split_us"} <= set(automation.FORWARD_STORES) and sum("score_split_" in g for g in automation.BACKUP_GLOBS) == 2
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'score_split.record(PROJECT_ROOT, "KR")' in app and 'score_split.record(PROJECT_ROOT, "US")' in app and '"score-split-evaluate": _qsf_score_split' in app
    assert '("GET", "/api/qsf/market-state")' in (ROOT / "terminal" / "server.py").read_text(encoding="utf-8")
    js = (ROOT / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")
    assert "function qsfMarketState(ms)" in js and 'filter(([k]) => k !== "REGIME")' in js and "${qsfMarketState(c.market_state)}" in js and "/api/qsf/market-state?market=" in js
    assert config.VALIDATION_NOTICE in js and "시장 상태" in config.VALIDATION_NOTICE
    assert pb.VERSION == "PB-2" and "PB-2" in (ROOT / "reports" / "PAPER_BOOK_RULES.md").read_text(encoding="utf-8")
    assert (ROOT / ss.PROTOCOL).exists() and "QSF-1.4.0" in (ROOT / ss.PROTOCOL).read_text(encoding="utf-8")


def test_a_held_position_still_reads_a_severe_market(monkeypatch):
    from terminal.qsf import holding
    src = (ROOT / "terminal" / "qsf" / "holding.py").read_text(encoding="utf-8")
    assert 'res["domains"]["REGIME"]["score_100"] or 100) < 25' in src                                  # the reference domain still carries its reading
    fixed_regime(monkeypatch, "US", 0.1)
    assert engine.score(ctx(), "SWING")["domains"]["REGIME"]["score_100"] == pytest.approx(10.0) and hasattr(holding, "entry_status")
