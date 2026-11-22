"""System test A: the daily scan and the one-ticker evaluation, on the same stored inputs and the same code.

Every provider call raises, so only stored copies are read; the scan is a dry run (record=False, publish=False) and nothing is
written.  The scan's cards are captured as they are made and compared, factor by factor, with QSF.evaluate of the same stocks.
No return is computed.  Run from the repository root:  .venv/bin/python reports/maturity_assessment_2026_11_22/evidence/chief/test_a_consistency.py
"""
import json, random, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from utils import runtime_config
runtime_config.load_local_env(REPO / ".env")
from terminal.services import Terminal
from terminal.qsf.service import QSF
from terminal.qsf.ledger import Ledger


class Offline:
    SEC_ARCHIVE = "https://offline/{cik}/{acc}/{doc}"
    ciks = {}

    def sec_cik(self, t):
        if t not in self.ciks:
            raise OSError("offline")
        return self.ciks[t]

    def __getattr__(self, name):
        def call(*a, **k):
            raise OSError("offline")
        return call


led = Ledger(REPO)
last = [r for r in led._live_rows() if r["market"] == "US"][-1]
Offline.ciks = {s["ticker"]: s["cik"] for s in led._load(last) if s.get("cik")}
KEYS = ("score", "band", "band_label", "action", "actionability", "coverage", "input_coverage", "confidence", "entry_status", "data_date", "price", "model_version")
out = {}
random.seed(20261122)
for market in ("US", "KR"):
    q = QSF(REPO, src=Offline(), terminal=Terminal(REPO))
    seen = {}
    make = q.card

    def keep(ctx, strategy, position=None, _make=make, _seen=seen):
        c = _make(ctx, strategy, position)
        _seen[(c["ticker"], strategy)] = c
        return c
    q.card = keep
    res = q.scan(market, record=False, publish=False, **({} if market == "US" else {"side_files": False}))
    q.card = make
    tickers = sorted({t for t, _ in seen})
    rank = {s: {t: n for n, (t, _) in enumerate(sorted(((t, c["score"]) for (t, st), c in seen.items() if st == s and c["score"] is not None), key=lambda x: -x[1]), 1)} for s in ("SWING", "LONG_TERM")}
    sample = random.sample(tickers, 15)
    rows = []
    for t in sample:
        d = q.evaluate(t, market)
        for s, direct in (d.get("cards") or {}).items():
            scan = seen.get((t, s))
            if scan is None:
                rows.append({"ticker": t, "strategy": s, "problem": "not in scan"})
                continue
            fa, fb = {f["factor"]: f for f in scan["factors"]}, {f["factor"]: f for f in direct["factors"]}
            diff = []
            for name in sorted(set(fa) | set(fb)):
                a, b = fa.get(name) or {}, fb.get(name) or {}
                na, nb = a.get("normalized"), b.get("normalized")
                if a.get("status") != b.get("status") or (na is None) != (nb is None) or (na is not None and abs(na - nb) > 1e-9) or a.get("raw") != b.get("raw"):
                    diff.append({"factor": name, "scan": [a.get("status"), na], "direct": [b.get("status"), nb], "raw_same": a.get("raw") == b.get("raw")})
            rows.append({"ticker": t, "strategy": s, "rank_in_scan": rank[s].get(t), **{f"scan_{k}": scan.get(k) for k in KEYS}, **{f"direct_{k}": direct.get(k) for k in KEYS},
                         "score_diff": None if scan["score"] is None or direct["score"] is None else direct["score"] - scan["score"],
                         "same_words": all(scan.get(k) == direct.get(k) for k in ("band", "band_label", "action", "actionability", "confidence", "entry_status")),
                         "gates_scan": [g["code"] for g in scan["gates"]], "gates_direct": [g["code"] for g in direct["gates"]], "factor_differences": diff, "rank_basis": d.get("rank_basis")})
    out[market] = {"session": res.get("session"), "scan_status": res.get("status"), "scanned": len(tickers), "sample": sample, "rows": rows}
    same = sum(1 for r in rows if r.get("score_diff") is not None and abs(r["score_diff"]) < 0.005)
    print(market, res.get("session"), "pairs", len(rows), "identical score", same, "max |diff|", max((abs(r["score_diff"]) for r in rows if r.get("score_diff") is not None), default=None),
          "words differ", sum(1 for r in rows if r.get("same_words") is False), "cards with factor differences", sum(1 for r in rows if r.get("factor_differences")), flush=True)
(Path(__file__).parent / "test_a_consistency.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
