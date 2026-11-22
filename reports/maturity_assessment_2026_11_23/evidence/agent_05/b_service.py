"""AGENT 5 (2026-11-23) scratch: SYSTEM TEST B at the service level, plus the three data-carrying additions of 2026-11-22/23
(Korean price label, coin quotes, portfolio drift moves).  A QSF / Terminal on a temporary folder OUTSIDE the repository with
fake providers (tests/test_qsf.py, tests/test_kr_terminal.py).  No provider request.  The only file written inside the
repository is this script's own output beside it."""
import json
import shutil
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from utils import runtime_config                              # noqa: E402
runtime_config.load_local_env(REPO / ".env")                  # the brief's rule 7; nothing of it is printed

import numpy as np                                            # noqa: E402
import pandas as pd                                           # noqa: E402

from terminal import coin_source, services, sources          # noqa: E402
from terminal.committee import portfolios, service as csvc   # noqa: E402
from terminal.qsf import kr_bars, service as qsvc            # noqa: E402
from terminal.qsf.service import QSF                          # noqa: E402
from tests import test_kr_terminal as tk                      # noqa: E402
from tests.test_qsf import NOW, FakeSrc, FakeTerm, bars     # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="agent05_1123_"))
assert REPO not in TMP.parents and TMP != REPO
OUT = {}
n = [0]


def folder():
    n[0] += 1
    p = TMP / f"case{n[0]}"
    p.mkdir()
    return p


def brief(c):
    return {"score": None if c["score"] is None else round(c["score"], 2), "conservative": None if c.get("conservative_score") is None else round(c["conservative_score"], 2),
            "band_label": c["band_label"], "action": c["action"], "actionability": c["actionability"], "coverage": round(c["coverage"], 3),
            "input_coverage": round(c["input_coverage"], 3), "confidence": c["confidence"], "gates": [g["code"] for g in c["gates"]], "missing": c["missing"], "partial": c["partial"], "stale": c["stale"],
            "data_date": c["data_date"], "provenance_price": c["provenance"].get("price"), "provenance_stale": c["provenance"].get("stale"),
            "market_state": {k: c["market_state"].get(k) for k in ("state", "coverage")}, "why": c.get("why_summary")}


def both(d):
    if d.get("status") != "REAL":
        return {"status": d.get("status"), "reason": d.get("reason")}
    return {s: brief(c) for s, c in d["cards"].items()}


def age_cache(base: Path, days: float, only: str = ""):
    for p in (base / "data" / "qsf" / "cache").glob("*.json"):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if only and not str(rec.get("key", "")).startswith(only):
            continue
        rec["stored_at"] -= days * 86400
        p.write_text(json.dumps(rec), encoding="utf-8")


class Down(FakeSrc):
    def __init__(self, *dead):
        self.dead = set(dead)

    def __getattribute__(self, name):
        if name not in ("dead", "__class__") and name in object.__getattribute__(self, "dead"):
            def boom(*a, **k):
                raise TimeoutError("synthetic timeout")
            return boom
        return object.__getattribute__(self, name)


def q(base=None, src=None, now=NOW):
    return QSF(base or folder(), src=src or FakeSrc(), now=lambda: now, terminal=FakeTerm())


# ------------------------------------------------------------------ provider failures
OUT["S0_all_sources_answer"] = both(q().evaluate("AAA"))
OUT["S1_price_timeout_no_copy"] = both(q(src=Down("yahoo_history")).evaluate("AAA"))
base = folder()
q(base).evaluate("AAA")
age_cache(base, 2.0)
OUT["S2_all_sources_down_2_days_later"] = both(q(base, Down("yahoo_history", "sec_companyfacts", "sec_submissions", "yahoo_info", "fred_series", "yahoo_earnings_dates", "sec_text"), NOW + timedelta(days=2)).evaluate("AAA"))
OUT["S3_statements_timeout_no_copy"] = both(q(src=Down("sec_companyfacts")).evaluate("AAA"))
for days in (30.0, 400.0):
    base = folder()
    q(base).evaluate("AAA")
    age_cache(base, days, "annual4")
    OUT[f"S4_statements_timeout_{int(days)}_day_old_copy"] = both(q(base, Down("sec_companyfacts")).evaluate("AAA"))
for days in (30.0, 400.0):
    base = folder()
    q(base).evaluate("AAA")
    age_cache(base, days, "info:")
    OUT[f"S5_company_record_{int(days)}_days_old_request_fails"] = both(q(base, Down("yahoo_info")).evaluate("AAA"))["LONG_TERM"]


# ------------------------------------------------------------------ partial replies in a scan
def scan_missing(k):
    class Partial(FakeSrc):
        def yahoo_history(self, symbols, period="2y"):
            out = super().yahoo_history(symbols, period)
            return {s: v for s, v in out.items() if s not in {f"T{i}" for i in range(k)}}
    r = q(src=Partial()).scan("US", tickers=[f"T{i}" for i in range(25)])
    return {x: r.get(x) for x in ("status", "reason", "tickers", "asked", "at_session", "scored", "errors", "no_bars", "download")} | {"recorded": bool(r.get("ledger"))}


OUT["S7_scan_2_of_25_without_bars"] = scan_missing(2)
OUT["S7_scan_4_of_25_without_bars"] = scan_missing(4)


class TwoLate(FakeSrc):
    def yahoo_history(self, symbols, period="2y"):
        out = super().yahoo_history(symbols, period)
        return {s: (bars(end="2026-11-03") if s in ("T0", "T1") else v) for s, v in out.items()}


r = q(src=TwoLate()).scan("US", tickers=[f"T{i}" for i in range(25)])
OUT["S7b_scan_2_of_25_one_session_behind"] = {"status": r["status"], "scored": r.get("scored"), "late_rows": [{k: x[k] for k in ("ticker", "strategy", "action", "actionability", "gates", "data_date")} for x in r["rows"] if x["ticker"] in ("T0", "T1")]}


class HoleInOne(FakeSrc):
    """A whole-universe scan where one stock's history has a 40-session hole and another a doubled last row."""
    def yahoo_history(self, symbols, period="2y"):
        out = super().yahoo_history(symbols, period)
        b = bars()
        if "T3" in out:
            out["T3"] = b[:200] + b[240:]
        if "T4" in out:
            out["T4"] = b + [dict(b[-1])]
        return out


r = q(src=HoleInOne()).scan("US")
OUT["S7c_whole_scan_one_stock_with_hole_one_doubled"] = {"status": r["status"], "scored": r.get("scored"), "recorded": bool(r.get("ledger")),
                                                         "rows": [{k: x[k] for k in ("ticker", "strategy", "score", "action", "actionability", "gates")} for x in r["rows"] if x["ticker"] in ("T3", "T4")],
                                                         "summary_mentions_gated": any(k in r for k in ("gated", "data_anomaly", "anomalies"))}

qq = q(src=Down("sec_companyfacts"))
r = qq.scan("US")
OUT["S8_whole_scan_statements_down"] = {x: r.get(x) for x in ("status", "reason", "fundamentals")} | {"recorded": bool(r.get("ledger")), "ledger_rows": len(qq.ledger.read_index()["rows"])}
qq = q(src=Down("sec_companyfacts"))
r = qq.scan("US", tickers=[f"T{i}" for i in range(25)])
OUT["S8b_named_scan_statements_down"] = {x: r.get(x) for x in ("status", "reason", "fundamentals")} | {"recorded": bool(r.get("ledger")), "ledger_rows": len(qq.ledger.read_index()["rows"])}
base = folder()
q(base).scan("US", record=False)
age_cache(base, 400.0, "annual4")
qq = q(base, Down("sec_companyfacts"))
r = qq.scan("US")
OUT["S8c_whole_scan_statements_down_400_day_copies"] = {x: r.get(x) for x in ("status", "reason", "fundamentals", "stale_inputs")} | {"recorded": bool(r.get("ledger")),
    "first_row": {k: r["rows"][0].get(k) for k in ("ticker", "strategy", "action", "actionability", "confidence")} if r.get("rows") else None}


# ------------------------------------------------------------------ the source layer
def fake_download(symbols, period, interval="1d"):
    idx = pd.to_datetime(["2026-10-28", "2026-10-29", "2026-10-30", "2026-10-30", "2026-11-02", "2026-11-03", "2026-11-04"])
    close = [10.0, np.nan, 0.0, 10.2, -5.0, 10.4, 10.5]
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Adj Close": close, "Volume": [1e6] * 7}, index=idx)


got = sources.yahoo_history(["AAA"], "1mo", download=fake_download)["AAA"]
OUT["S9_source_filter"] = {"rows_in": 7, "rows_out": len(got), "dates_out": [r["date"] for r in got], "dropped_count_returned": False}

# ------------------------------------------------------------------ the Korean price-source label
days = [x["date"] for x in bars()[-300:]]
kb = [{**x, **{k: x[k] * 1000 for k in ("open", "high", "low", "close", "adj_close")}} for x in bars()[-300:]]


def pan_through(k):
    """A KRX panel of one stock holding the first ``k`` of the 300 days (KRX has published through days[k-1])."""
    data = np.full((6, k, 1), np.nan)
    raw = np.array([x["close"] for x in kb[:k]])
    rate = np.zeros(k)
    rate[1:] = (raw[1:] / raw[:-1] - 1) * 100
    for f in (kr_bars.OPEN, kr_bars.HIGH, kr_bars.LOW, kr_bars.CLOSE):
        data[f, :, 0] = raw
    data[kr_bars.RATE, :, 0] = rate
    data[kr_bars.VOLUME, :, 0] = 1e6
    return {"dates": days[:k], "codes": {"000001": 0}, "data": data}


def label_case(pan, yahoo, session, code="000001"):
    """What service._krx_bars + context() do, without the provider: rebuild, remember the info, cut at the session, label."""
    out, info = kr_bars.rebuild(code, yahoo, pan)
    used = qsvc._clean(out, session)
    return {"label": qsvc.price_label("KR", info), "info": {k: info.get(k) for k in ("source", "krx_last", "tail_days", "tail_skipped", "reason")}, "last_bar_used": used[-1]["date"] if used else None,
            "session": session, "bars_used_after_krx_last": sum(1 for x in used if info.get("krx_last") and x["date"] > info["krx_last"])}


OUT["LABEL_a_krx_at_session"] = label_case(pan_through(300), kb, days[-1])
OUT["LABEL_b_krx_two_days_behind"] = label_case(pan_through(298), kb, days[-1])
# during Korean market hours: KRX has yesterday, Yahoo also carries today's unfinished bar, the session is yesterday
OUT["LABEL_c_yahoo_has_an_unfinished_day_past_the_session"] = label_case(pan_through(299), kb, days[-2])
OUT["LABEL_d_stock_not_in_krx"] = label_case(pan_through(300), kb, days[-1], code="999999")
OUT["LABEL_e_yahoo_without_the_last_krx_day"] = label_case(pan_through(298), [x for x in kb if x["date"] != days[297]], days[-1])
# the label when the info of the bars is not known to this QSF (a context handed prefetched bars by a caller that did not rebuild them)
OUT["LABEL_f_info_unknown"] = qsvc.price_label("KR", None)
# a QSF whose panel read fails: every stock is labelled Yahoo with the reason
qk = q()
orig = kr_bars.panel
kr_bars.panel = lambda *a, **k: (_ for _ in ()).throw(OSError("synthetic"))
try:
    b2, summ = qk._krx_bars({"000001": kb})
    OUT["LABEL_g_panel_unreadable"] = {"label": qsvc.price_label("KR", qk._kr_bar_infos.get("000001")), "summary": summ, "bars_are_yahoo": b2["000001"] is kb}
    kr_bars.panel = lambda *a, **k: pan_through(300)
    b3, summ = qk._krx_bars({"000001": kb})
    OUT["LABEL_h_after_the_panel_is_back_the_label_follows"] = {"label": qsvc.price_label("KR", qk._kr_bar_infos.get("000001")), "summary": summ}
    kr_bars.panel = lambda *a, **k: None
    b4, summ = qk._krx_bars({"000001": kb})
    OUT["LABEL_i_no_snapshot_at_all"] = {"label": qsvc.price_label("KR", qk._kr_bar_infos.get("000001")), "summary": summ}
finally:
    kr_bars.panel = orig
# a KRX day missing from the files (not in the panel's dates): what the chained series does with it
full = pan_through(300)
keep = [i for i in range(300) if i != 250]
holed = {"dates": [days[i] for i in keep], "codes": full["codes"], "data": full["data"][:, keep, :]}
a, ia = kr_bars.rebuild("000001", kb, full)
h, ih = kr_bars.rebuild("000001", kb, holed)
OUT["KRX_one_day_file_missing"] = {"rows": [len(a), len(h)], "source": ih["source"], "close_240_rows_back_full_vs_holed": [round(a[59]["close"], 2), round(h[59]["close"], 2)],
                                   "ratio": round(h[59]["close"] / a[59]["close"], 5), "true_move_on_the_missing_day": round(kb[250]["close"] / kb[249]["close"], 5),
                                   "note": "the missing day's move is lost from every earlier price: the rate of the next day is chained onto the day before the hole"}

# ------------------------------------------------------------------ coin quotes
step = 4 * 3600 * 1000


def cbars(*closes, end_ms=None):
    end_ms = end_ms or int(tk.NOW.timestamp() * 1000) // step * step
    k = len(closes)
    return np.array([[end_ms - (k - i) * step, c, c, c, c, 1.0] for i, c in enumerate(closes)], dtype=float)


def coin_case(prices, fx=1400.0, error=None, ask=("BTC", "SHIB"), end_ms=None):
    t = services.Terminal(folder(), src=tk.FakeSrc({"KRW=X": fx} if fx else {}), now=lambda: tk.NOW)
    doc = {"arrays": {"bars": {s: cbars(*v, end_ms=end_ms) for s, v in prices.items()}}, **({"error": error} if error else {})}
    orig_load = coin_source.load
    coin_source.load = lambda base, *a, **k: doc
    try:
        got = t._coin_quotes(list(ask))
    finally:
        coin_source.load = orig_load
    return {"items": {c: {k: (round(v, 8) if isinstance(v, float) else v) for k, v in it.items()} for c, it in got["items"].items()}, "covered": got["covered"], "error": got["error"], "fx_status": got["fx"].get("status"), "fx_date": got["fx"].get("date")}


P = {"BTCUSDT": [90_000.0] * 6 + [100_000.0], "1000SHIBUSDT": [0.02] * 7}
OUT["COIN_a_ordinary"] = coin_case(P)
OUT["COIN_b_no_rate"] = coin_case(P, fx=None)
OUT["COIN_c_refresh_failed_reply_three_days_old"] = coin_case(P, error="TimeoutError", end_ms=(int(tk.NOW.timestamp() * 1000) // step * step) - 18 * step)
OUT["COIN_d_no_reply_at_all"] = coin_case({}, error="TimeoutError")
# contracts quoted per million and per thousand with other prefixes (Binance lists 1000000MOGUSDT, 1MBABYDOGEUSDT, 1000PEPEUSDT)
OUT["COIN_e_other_unit_prefixes"] = coin_case({"1000PEPEUSDT": [0.01] * 7, "1000000MOGUSDT": [0.9] * 7, "1MBABYDOGEUSDT": [0.0015] * 7}, ask=("PEPE", "MOG", "000MOG", "BABYDOGE", "1MBABYDOGE"))
OUT["COIN_f_zero_or_nan_close"] = coin_case({"BTCUSDT": [90_000.0] * 6 + [0.0], "ETHUSDT": [3000.0] * 6 + [float("nan")]}, ask=("BTC", "ETH"))
OUT["COIN_g_fewer_than_seven_bars"] = coin_case({"BTCUSDT": [100_000.0] * 3}, ask=("BTC",))


# ------------------------------------------------------------------ drift moves of the six portfolios
class Loader:
    def __init__(self, table):
        self.table = table

    def _loader(self, market):
        return lambda t: self.table.get(t)


class T:
    def __init__(self, table):
        self.qsf = Loader(table)


def mk(pairs, adj=None):
    return [{"date": d, "close": c, "adj_close": (adj or {}).get(d, c)} for d, c in pairs]


table = {
    "PLAIN": mk([("2026-11-19", 100.0), ("2026-11-20", 110.0)]),
    # a 2-for-1 split between the two sessions, the series already on today's basis (what an adjusted download gives)
    "SPLIT_ADJUSTED": mk([("2026-11-19", 50.0), ("2026-11-20", 55.0)]),
    # the same split, but the stored series was NOT put on today's basis (an archive bar kept from before the split)
    "SPLIT_NOT_ADJUSTED": mk([("2026-11-19", 100.0), ("2026-11-20", 55.0)]),
    "NO_BAR_ON_SINCE": mk([("2026-11-18", 100.0), ("2026-11-20", 120.0)]),
    "NO_NEWER_BAR": mk([("2026-11-18", 100.0), ("2026-11-19", 120.0)]),
    "EMPTY": [],
    # adj_close missing on the old bar only: the move mixes an adjusted price with a raw one
    "MIXED_BASIS": [{"date": "2026-11-19", "close": 100.0, "adj_close": None}, {"date": "2026-11-20", "close": 100.0, "adj_close": 97.0}],
    "EX_DIVIDEND": mk([("2026-11-19", 100.0), ("2026-11-20", 98.0)], adj={"2026-11-19": 98.0, "2026-11-20": 98.0}),
}
mv = csvc._moves(T(table), "US", "2026-11-19")
OUT["MOVES"] = {k: (None if mv(k) is None else round(mv(k), 4)) for k in list(table) + ["UNKNOWN_TICKER"]}
OUT["MOVES_none_without_an_earlier_record"] = csvc._moves(T(table), "US", None)
prev = {"PLAIN": 0.2, "NO_BAR_ON_SINCE": 0.2, "SPLIT_NOT_ADJUSTED": 0.2}
OUT["DRIFT_weights"] = {"before": prev, "after": portfolios.drift(prev, mv), "note": "an unknown move leaves the weight as it was, silently; an unadjusted split halves it"}

Path(__file__).with_name("b_service_output.json").write_text(json.dumps(OUT, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
for k, v in OUT.items():
    print(k, json.dumps(v, ensure_ascii=False, default=str)[:1400])
shutil.rmtree(TMP, ignore_errors=True)
