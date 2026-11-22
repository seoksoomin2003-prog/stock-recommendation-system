"""AGENT 5 scratch: SYSTEM TEST B at the service level.  A QSF on a temporary folder with the fake provider of tests/test_qsf.py.
No provider request, nothing written inside the repository (the temporary folder is outside it)."""
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

from terminal import sources                                  # noqa: E402
from terminal.qsf.service import QSF                          # noqa: E402
from tests.test_qsf import NOW, SESSION, FakeSrc, FakeTerm, bars, facts   # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="agent05_"))
assert REPO not in TMP.parents
OUT = {}
n = [0]


def folder():
    n[0] += 1
    p = TMP / f"case{n[0]}"
    p.mkdir()
    return p


def brief(c):
    val = next((f for f in c["factors"] if f["factor"] == "valuation"), {})
    return {"score": None if c["score"] is None else round(c["score"], 2), "band_label": c["band_label"], "action": c["action"], "actionability": c["actionability"], "coverage": round(c["coverage"], 3),
            "input_coverage": round(c["input_coverage"], 3), "confidence": c["confidence"], "gates": [g["code"] for g in c["gates"]], "missing": c["missing"], "partial": c["partial"], "stale": c["stale"],
            "data_date": c["data_date"], "provenance_stale": c["provenance"].get("stale"), "valuation_status": val.get("status"), "valuation_raw": val.get("raw"),
            "market_state": {k: c["market_state"].get(k) for k in ("state", "coverage")}, "regime_dates": c["provenance"].get("regime")}


def both(d):
    if d.get("status") != "REAL":
        return {"status": d.get("status"), "reason": d.get("reason")}
    return {s: brief(c) for s, c in d["cards"].items()}


def age_cache(base: Path, days: float, only: str = ""):
    """Makes the stored copies under ``base`` look ``days`` older (temporary folder only)."""
    for p in (base / "data" / "qsf" / "cache").glob("*.json"):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if only and not str(rec.get("key", "")).startswith(only):
            continue
        rec["stored_at"] -= days * 86400
        p.write_text(json.dumps(rec), encoding="utf-8")


class Down(FakeSrc):
    """Every method named in ``dead`` raises, like a timeout."""
    def __init__(self, *dead):
        self.dead = set(dead)

    def __getattribute__(self, name):
        if name not in ("dead", "__class__") and name in object.__getattribute__(self, "dead"):
            def boom(*a, **k):
                raise TimeoutError("synthetic timeout")
            return boom
        return object.__getattribute__(self, name)


# S0 everything answers
base = folder()
OUT["S0_all_sources_answer"] = both(QSF(base, src=FakeSrc(), now=lambda: NOW, terminal=FakeTerm()).evaluate("AAA"))

# S1 prices time out, nothing stored
OUT["S1_price_timeout_no_copy"] = both(QSF(folder(), src=Down("yahoo_history"), now=lambda: NOW, terminal=FakeTerm()).evaluate("AAA"))

# S2 every provider times out two sessions later; stored copies stand in
base = folder()
QSF(base, src=FakeSrc(), now=lambda: NOW, terminal=FakeTerm()).evaluate("AAA")
age_cache(base, 2.0)
later = NOW + timedelta(days=2)
OUT["S2_all_sources_down_2_days_later_copies_stand_in"] = both(QSF(base, src=Down("yahoo_history", "sec_companyfacts", "sec_submissions", "yahoo_info", "fred_series", "yahoo_earnings_dates", "sec_text"),
                                                                 now=lambda: later, terminal=FakeTerm()).evaluate("AAA"))

# S3 statements time out, nothing stored
OUT["S3_statements_timeout_no_copy"] = both(QSF(folder(), src=Down("sec_companyfacts"), now=lambda: NOW, terminal=FakeTerm()).evaluate("AAA"))

# S4 statements time out, a copy stored 30 days ago stands in (prices are today's)
base = folder()
QSF(base, src=FakeSrc(), now=lambda: NOW, terminal=FakeTerm()).evaluate("AAA")
age_cache(base, 30.0, "annual4")
OUT["S4_statements_timeout_30_day_old_copy"] = both(QSF(base, src=Down("sec_companyfacts"), now=lambda: NOW, terminal=FakeTerm()).evaluate("AAA"))

# S5 the company record: request fails, the copy is 30 days old / 400 days old
for days in (30.0, 400.0):
    base = folder()
    QSF(base, src=FakeSrc(), now=lambda: NOW, terminal=FakeTerm()).evaluate("AAA")
    age_cache(base, days, "info:")
    OUT[f"S5_company_record_{int(days)}_days_old_request_fails"] = both(QSF(base, src=Down("yahoo_info"), now=lambda: NOW, terminal=FakeTerm()).evaluate("AAA"))["LONG_TERM"]


# S6 a split the company record has not caught up with: the record's own price is twice today's close
class SplitInfo(FakeSrc):
    def yahoo_info(self, t):
        return {"longName": "Test Co", "sharesOutstanding": 10.0, "currentPrice": bars()[-1]["close"] * 2}


OUT["S6_share_count_on_another_price_basis"] = both(QSF(folder(), src=SplitInfo(), now=lambda: NOW, terminal=FakeTerm()).evaluate("AAA"))["LONG_TERM"]


# S7 a partial reply in a scan: some of 25 stocks come back without bars
def scan_missing(k, whole=False):
    class Partial(FakeSrc):
        def yahoo_history(self, symbols, period="2y"):
            out = super().yahoo_history(symbols, period)
            return {s: v for s, v in out.items() if s not in {f"T{i}" for i in range(k)}}
    q = QSF(folder(), src=Partial(), now=lambda: NOW, terminal=FakeTerm())
    r = q.scan("US", tickers=None if whole else [f"T{i}" for i in range(25)])
    return {x: r.get(x) for x in ("status", "reason", "tickers", "asked", "at_session", "scored", "errors", "no_bars", "ledger", "fundamentals", "download")}


OUT["S7_scan_2_of_25_without_bars"] = scan_missing(2)
OUT["S7_scan_4_of_25_without_bars"] = scan_missing(4)


# S7b some stocks end a session early (stale last price inside a scan that is otherwise ready)
class TwoLate(FakeSrc):
    def yahoo_history(self, symbols, period="2y"):
        out = super().yahoo_history(symbols, period)
        return {s: (bars(end="2026-11-03") if s in ("T0", "T1") else v) for s, v in out.items()}


q = QSF(folder(), src=TwoLate(), now=lambda: NOW, terminal=FakeTerm())
r = q.scan("US", tickers=[f"T{i}" for i in range(25)])
OUT["S7b_scan_2_of_25_one_session_behind"] = {"status": r["status"], "scored": r.get("scored"), "late_rows": [{k: x[k] for k in ("ticker", "strategy", "score", "action", "actionability", "gates", "data_date")} for x in r["rows"] if x["ticker"] in ("T0", "T1")]}

# S8 whole-universe scan with the statement source down: prices are there, statements are not
q = QSF(folder(), src=Down("sec_companyfacts"), now=lambda: NOW, terminal=FakeTerm())
r = q.scan("US")
OUT["S8_whole_scan_statements_down"] = {x: r.get(x) for x in ("status", "reason", "tickers", "fundamentals", "ledger")} | {"ledger_rows": len(q.ledger.read_index()["rows"])}
# S8b the same with named stocks (the statements-share condition applies to a whole-universe scan only)
q = QSF(folder(), src=Down("sec_companyfacts"), now=lambda: NOW, terminal=FakeTerm())
r = q.scan("US", tickers=[f"T{i}" for i in range(25)])
OUT["S8b_named_scan_statements_down"] = {x: r.get(x) for x in ("status", "reason", "tickers", "fundamentals", "ledger")} | {"ledger_rows": len(q.ledger.read_index()["rows"])}
# S8c whole scan, statements down, but 400-day-old stored statements stand in
base = folder()
QSF(base, src=FakeSrc(), now=lambda: NOW, terminal=FakeTerm()).scan("US", record=False)
age_cache(base, 400.0, "annual4")
q = QSF(base, src=Down("sec_companyfacts"), now=lambda: NOW, terminal=FakeTerm())
r = q.scan("US")
OUT["S8c_whole_scan_statements_down_400_day_copies"] = {x: r.get(x) for x in ("status", "reason", "fundamentals", "stale_inputs", "ledger")} | {
    "first_row": {k: r["rows"][0].get(k) for k in ("ticker", "strategy", "score", "action", "actionability", "confidence")} if r.get("rows") else None}


# S9 the source layer: what terminal.sources.yahoo_history does with invalid rows
def fake_download(symbols, period, interval="1d"):
    idx = pd.to_datetime(["2026-10-28", "2026-10-29", "2026-10-30", "2026-10-30", "2026-11-02", "2026-11-03", "2026-11-04"])
    close = [10.0, np.nan, 0.0, 10.2, -5.0, 10.4, 10.5]
    df = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Adj Close": close, "Volume": [1e6] * 7}, index=idx)
    return df


got = sources.yahoo_history(["AAA"], "1mo", download=fake_download)["AAA"]
OUT["S9_source_filter"] = {"rows_in": 7, "rows_out": len(got), "dates_out": [r["date"] for r in got], "closes_out": [r["close"] for r in got],
                           "note": "NaN, zero and negative closes are dropped without a mark; a doubled date passes"}

# S10 the earnings calendar times out
OUT["S10_earnings_calendar_timeout"] = {s: {k: v for k, v in c.items() if k in ("score", "confidence", "missing", "coverage")} for s, c in both(QSF(folder(), src=Down("yahoo_earnings_dates"), now=lambda: NOW, terminal=FakeTerm()).evaluate("AAA")).items()}

Path(__file__).with_name("test_b_service_output.json").write_text(json.dumps(OUT, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
for k, v in OUT.items():
    print(k, json.dumps(v, ensure_ascii=False, default=str))
shutil.rmtree(TMP, ignore_errors=True)
