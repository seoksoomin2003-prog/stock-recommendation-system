"""TERMINAL-3 offline tests: challenger rules (no look-ahead, missing != 0), common yardstick outcomes,
prospective ledger (idempotent, no stale panel, entry after record time, hash chain), P6-11B cohort read,
research simulation, API."""
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from terminal.lab import backtest, compare, models
from terminal.lab.panel import Panel
from terminal.lab.service import Lab, LabError
from utils import nyse_calendar

AFTER_CLOSE = datetime(2026, 11, 3, 23, 0, tzinfo=timezone.utc)      # 18:00 ET Tue 2026-11-03
DURING = datetime(2026, 11, 4, 16, 0, tzinfo=timezone.utc)           # 11:00 ET Wed


def sessions(end="2026-11-03", n=320):
    out, d = [], nyse_calendar._as_date(end)
    while len(out) < n:
        if nyse_calendar.is_session(d):
            out.append(d.isoformat())
        d = nyse_calendar.previous_session(d)
    return sorted(out)


def synth(n=320, end="2026-11-03", tickers=None, drift=None):
    """Deterministic panel: ticker k grows at drift[k]/day with small alternating noise; SPY flat-ish."""
    dates = sessions(end, n)
    tickers = tickers or ["AAA", "BBB", "CCC", "DDD", "SPY"]
    drift = drift or {"AAA": 0.002, "BBB": 0.001, "CCC": -0.001, "DDD": 0.0005, "SPY": 0.0003}
    data = {k: np.full((n, len(tickers)), np.nan) for k in ("open", "close", "adj_close", "volume")}
    for j, t in enumerate(tickers):
        noise = np.array([(0.01 if i % 2 else -0.01) * (j + 1) / 4 for i in range(n)])
        close = 50 * np.cumprod(1 + drift[t] + noise)
        data["close"][:, j] = close
        data["open"][:, j] = close * 0.999
        data["adj_close"][:, j] = close
        data["volume"][:, j] = 1e6
    return Panel(dates, tickers, data, {})


# ----------------------------------------------------------------------------- models
def test_momentum_ranks_and_no_lookahead():
    p = synth()
    i = len(p.dates) - 1
    u = ["AAA", "BBB", "CCC", "DDD"]
    picks = [x["ticker"] for x in models.score("MOM_12_1", p, i, u)["picks"]]
    assert picks[0] == "AAA" and picks[-1] == "CCC" and "SPY" not in picks
    k = 300
    before = models.score("MOM_12_1", p, k, u)
    p.data["adj_close"][k + 1:, p.col["CCC"]] *= 100       # future explodes: must not change the past signal
    p.data["close"][k + 1:, p.col["CCC"]] *= 100
    assert models.score("MOM_12_1", p, k, u) == before


def test_lowvol_and_trend():
    p = synth()
    i = len(p.dates) - 1
    u = ["AAA", "BBB", "CCC", "DDD"]
    lv = [x["ticker"] for x in models.score("LOWVOL_252", p, i, u)["picks"]]
    assert lv[0] == "AAA"                                   # smallest noise amplitude (j=0)
    tr = [x["ticker"] for x in models.score("TREND_SWING", p, i, u)["picks"]]
    assert "CCC" not in tr and tr[0] == "AAA"               # downtrend excluded


def test_eligibility_filters_and_missing_data():
    p = synth()
    i = len(p.dates) - 1
    p.data["close"][i, p.col["BBB"]] = 4.0                  # below $5
    p.data["volume"][:, p.col["DDD"]] = 1000.0              # illiquid
    p.data["adj_close"][i - 252, p.col["AAA"]] = np.nan     # missing lookback point
    e = models.eligible(p, i, ["AAA", "BBB", "CCC", "DDD", "ZZZ"])
    assert e == ["AAA", "CCC"]
    picks = [x["ticker"] for x in models.score("MOM_12_1", p, i, ["AAA", "BBB", "CCC", "DDD"])["picks"]]
    assert picks == ["CCC"]                                 # AAA dropped, not scored as 0


def test_baselines():
    p = synth()
    i = len(p.dates) - 1
    assert models.score("BASE_SPY", p, i, [])["picks"][0]["ticker"] == "SPY"
    assert len(models.score("BASE_EW", p, i, ["AAA", "BBB", "CCC", "DDD"])["picks"]) == 4


# ----------------------------------------------------------------------------- yardstick
def test_cohort_outcome_total_return_and_states():
    p = synth()
    e = p.dates[-25]
    j = p.col["AAA"]
    p.data["adj_close"][:, j] = p.data["close"][:, j] * 0.98   # dividend factor 0.98 throughout
    o = compare.cohort_outcome(p, ["AAA"], e, 20)
    ei, xi = p.idx[e], p.idx[e] + 19
    expect = p.data["adj_close"][xi, j] / (p.data["open"][ei, j] * 0.98) - 1
    assert o["status"] == "MATURED" and o["return"] == pytest.approx(expect)
    assert o["exit_session"] == p.dates[xi]
    assert compare.cohort_outcome(p, ["AAA"], e, 60)["status"] == "PENDING"
    assert compare.cohort_outcome(p, ["AAA"], "2026-12-01", 5)["status"] == "PENDING"
    p.data["adj_close"][xi, p.col["BBB"]] = np.nan
    o = compare.cohort_outcome(p, ["AAA", "BBB", "CCC", "DDD", "SPY"], e, 20)
    assert o["status"] == "MATURED" and o["missing"] == ["BBB"] and o["n"] == 4      # 20% missing allowed
    o = compare.cohort_outcome(p, ["AAA", "BBB"], e, 20)
    assert o["status"] == "INCOMPLETE"                                               # 50% missing


def test_aggregate_independent_samples_and_verdict():
    outs = [{"status": "MATURED", "return": 0.02, "bench": 0.01, "excess": 0.01}] * 40 + [{"status": "PENDING"}] * 3
    a = compare.aggregate(outs, 20)
    assert a["matured"] == 40 and a["independent"] == 2.0 and a["verdict"] == "판단 보류"
    assert a["mean_excess"] == pytest.approx(0.01) and a["hit_rate"] == 1.0 and a["pending"] == 3
    assert compare.aggregate(outs[:24], 2)["verdict"] == "관찰 가능"
    assert compare.aggregate([], 5)["mean_excess"] is None


# ----------------------------------------------------------------------------- ledger / service
def make_lab(tmp_path, now, panel=None, universe=("AAA", "BBB", "CCC", "DDD")):
    uf = tmp_path / "data" / "sp500_universe_cache.json"
    uf.parent.mkdir(parents=True, exist_ok=True)
    uf.write_text(json.dumps({"tickers": list(universe), "retrieved_at": "2026-11-03T00:00:00+00:00"}))
    lab = Lab(tmp_path, now=lambda: now)
    if panel is not None:
        panel.save(lab.panel_file)
    return lab


def test_record_idempotent_and_entry_after_close(tmp_path):
    lab = make_lab(tmp_path, AFTER_CLOSE, synth())
    r = lab.record()
    assert r["signal_session"] == "2026-11-03" and r["entry_session"] == "2026-11-04"
    assert sorted(r["recorded"]) == sorted(["MOM_12_1", "LOWVOL_252", "TREND_SWING", "BASE_SPY", "BASE_EW"])
    again = lab.record()
    assert again["recorded"] == [] and len(again["already_recorded"]) == 5
    recs, integ = lab.read_ledger()
    assert integ["status"] == "OK" and len(recs) == 5


def test_record_during_session_enters_next_open(tmp_path):
    lab = make_lab(tmp_path, DURING, synth())
    r = lab.record()
    assert r["signal_session"] == "2026-11-03" and r["entry_session"] == "2026-11-05"


def test_record_refuses_stale_panel_and_missing_panel(tmp_path):
    lab = make_lab(tmp_path, AFTER_CLOSE)
    with pytest.raises(LabError):
        lab.record()
    make_lab(tmp_path, AFTER_CLOSE, synth(end="2026-10-30"))
    lab = Lab(tmp_path, now=lambda: AFTER_CLOSE)
    with pytest.raises(LabError, match="신호일"):
        lab.record()
    assert not lab.ledger_file.exists()


def test_ledger_tamper_detected(tmp_path):
    lab = make_lab(tmp_path, AFTER_CLOSE, synth())
    lab.record()
    lines = lab.ledger_file.read_text().splitlines()
    rec = json.loads(lines[0])
    rec["picks"] = [{"ticker": "ZZZ"}]
    lines[0] = json.dumps(rec, sort_keys=True)
    lab.ledger_file.write_text("\n".join(lines) + "\n")
    assert lab.read_ledger()[1]["status"] == "BROKEN"
    with pytest.raises(LabError):
        lab.record()


def _fetch_from(panel_like):
    """Fake yfinance download returning the synthetic panel (plus a bar for a later date)."""
    def fetch(chunk, period):
        cols = {}
        for t in chunk:
            if t not in panel_like.col:
                continue
            j = panel_like.col[t]
            for f, k in (("Open", "open"), ("Close", "close"), ("Adj Close", "adj_close"), ("Volume", "volume")):
                cols[(f, t)] = panel_like.data[k][:, j]
        df = pd.DataFrame(cols, index=pd.to_datetime(panel_like.dates))
        df.columns = pd.MultiIndex.from_tuples(df.columns)
        return df
    return fetch


def test_refresh_panel_drops_intraday_bar_and_is_cached(tmp_path):
    full = synth(end="2026-11-04", n=321)                   # includes Wednesday's (intraday) bar
    lab = make_lab(tmp_path, DURING)
    lab.fetch = _fetch_from(full)
    r = lab.refresh_panel()
    assert r["status"] == "DOWNLOADED" and r["last"] == "2026-11-03"
    assert lab.refresh_panel()["status"] == "UP_TO_DATE"
    out = lab.update()
    assert out["record"]["entry_session"] == "2026-11-05"


def test_p6_cohorts_first_valid_run_per_session(tmp_path, monkeypatch):
    from pipeline import prospective_ledger as pl
    from pipeline import prospective_tracking as pt

    def obs(oid, run, t, ts, entry="2026-11-04", klass="PORTFOLIO_TOP5"):
        return {"record_type": "OBSERVATION", "observation_id": oid, "observation_class": klass, "run_id": run,
                "ticker": t, "recommendation_timestamp_utc": ts, "signal": {"entry_session": entry}}
    recs = [obs("1", "R1", "AAA", "2026-11-03T15:00"), obs("2", "R1", "BBB", "2026-11-03T15:00"),
            obs("3", "R2", "CCC", "2026-11-03T16:00"), obs("4", "R0", "DDD", "2026-11-03T14:00"),
            obs("5", "R1", "EEE", "2026-11-03T15:00", klass="WATCHLIST_DIAGNOSTIC")]
    monkeypatch.setattr(pl, "read_observations", lambda d: recs)
    monkeypatch.setattr(pt, "_cohorts", lambda o, d: {x["observation_id"]: {"cohort": "PRE_FIX_EXCLUDED" if x["run_id"] == "R0"
                                                                              else "VALID_PROSPECTIVE"} for x in o})
    c = Lab(tmp_path, now=lambda: AFTER_CLOSE).p6_cohorts()
    assert c["cohorts"] == [{"entry_session": "2026-11-04", "tickers": ["AAA", "BBB"], "run_id": "R1",
                             "runs_that_session": 2}]


def test_comparison_shape(tmp_path):
    lab = make_lab(tmp_path, AFTER_CLOSE, synth())
    lab.record()
    c = lab.comparison()
    assert c["order"][0] == "P6-11B" and c["results"]["MOM_12_1"]["cohorts"] == 1
    assert c["results"]["MOM_12_1"]["horizons"]["20"]["pending"] == 1
    assert c["latest"]["BASE_SPY"]["picks"][0]["ticker"] == "SPY"


# ----------------------------------------------------------------------------- research
def test_backtest_runs_and_costs_reduce_returns():
    p = synth(n=520)
    u = ["AAA", "BBB", "CCC", "DDD"]
    s0 = backtest.simulate(p, "MOM_12_1", u, 0.0)
    s1 = backtest.simulate(p, "MOM_12_1", u, 10.0)
    assert s0["status"] == "REAL" and s0["rebalances"] >= 10 and len(s0["nav"]) == len(s0["dates"])
    assert s1["total_return"] <= s0["total_return"]
    b = backtest.benchmark(p)
    assert b["dates"][0] == s0["dates"][0] and b["max_drawdown"] <= 0
    assert backtest.simulate(synth(n=260), "MOM_12_1", u)["status"] == "UNAVAILABLE"


def test_backtest_signal_uses_previous_session_only(monkeypatch):
    p = synth(n=520)
    seen = []
    orig = models.score
    monkeypatch.setattr(models, "score", lambda code, pp, i, u: seen.append(i) or orig(code, pp, i, u))
    rows = backtest.rebalance_rows(p)
    backtest.simulate(p, "TREND_SWING", ["AAA", "BBB", "CCC", "DDD"])
    assert seen == [r - 1 for r in rows]


HTML = ("<table id='constituents'><tr><th>Symbol</th><th>Security</th><th>Date added</th></tr>"
        + "".join(f"<tr><td>{t}</td><td>x</td><td>{d}</td></tr>" for t, d in
                  [("AAA", "1990-01-01"), ("BBB", "2026-01-15"), ("CCC", ""), ("DDD", "2000-05-05")] * 1)
        + "".join(f"<tr><td>Z{i}</td><td>x</td><td>2001-01-01</td></tr>" for i in range(460)) + "</table>")


def test_membership_parse_and_members_at(tmp_path):
    from terminal.lab import membership
    added = membership.parse(HTML)
    assert added["AAA"] == "1990-01-01" and added["CCC"] is None
    u = ["AAA", "BBB", "CCC", "DDD"]
    assert backtest.members_at(u, added, "2025-12-31") == ["AAA", "DDD"]       # BBB not yet, CCC unknown
    assert backtest.members_at(u, added, "2026-01-15") == ["AAA", "BBB", "DDD"]
    assert backtest.members_at(u, None, "2000-01-01") == u
    m = membership.load(tmp_path / "m.json", AFTER_CLOSE, lambda url: HTML)
    assert m["status"] == "REAL" and (tmp_path / "m.json").exists()
    m2 = membership.load(tmp_path / "m.json", AFTER_CLOSE, lambda url: pytest.fail("cached"))
    assert m2["status"] == "REAL"
    def boom(url):
        raise ConnectionError
    assert membership.load(tmp_path / "none.json", AFTER_CLOSE, boom)["status"] == "UNAVAILABLE"


def test_backtest_respects_join_dates():
    p = synth(n=520)
    late = {"AAA": "2099-01-01", "BBB": "1990-01-01", "CCC": "1990-01-01", "DDD": "1990-01-01"}
    s = backtest.simulate(p, "MOM_12_1", ["AAA", "BBB", "CCC", "DDD"], 0.0, late)
    full = backtest.simulate(p, "MOM_12_1", ["AAA", "BBB", "CCC", "DDD"], 0.0, None)
    assert s["members_last"] == 3 and full["members_last"] == 4
    assert s["total_return"] != full["total_return"]


def test_research_cached_by_panel(tmp_path):
    lab = make_lab(tmp_path, AFTER_CLOSE, synth(n=520))
    lab.membership_fetch = lambda url: HTML
    r = lab.research()
    assert r["membership"]["pit"] is True
    assert r["status"] == "REAL" and set(r["models"]) == {"MOM_12_1", "LOWVOL_252", "TREND_SWING", "BASE_EW"}
    assert lab.bt_file.exists() and lab.research()["panel_fingerprint"] == r["panel_fingerprint"]
    assert "생존 편향" in r["limitations"][0]
    nolist = make_lab(tmp_path / "x", AFTER_CLOSE, synth(n=520))
    nolist.membership_fetch = lambda url: (_ for _ in ()).throw(ConnectionError())
    r2 = nolist.research()
    assert r2["membership"]["pit"] is False and "편입일" in r2["limitations"][0]


def test_panel_roundtrip_keeps_missing(tmp_path):
    p = synth(n=30)
    p.data["close"][3, 0] = np.nan
    p.save(tmp_path / "p.json.gz")
    q = Panel.load(tmp_path / "p.json.gz")
    assert np.isnan(q.data["close"][3, 0]) and q.dates == p.dates and q.fingerprint() == p.fingerprint()


def test_static_lab_ui():
    from terminal import server
    text = (server.STATIC / "lab.js").read_text(encoding="utf-8")
    assert "http://" not in text and "https://" not in text
    html = (server.STATIC / "index.html").read_text(encoding="utf-8")
    assert "lab.js" in html and 'data-tab="lab"' in html
