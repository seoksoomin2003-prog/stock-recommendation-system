"""Offline dry scan with the worktree's code; captures what engine.score itself returns (gap, bad rows, conservative score)."""
import json, sys
import mk
from terminal.qsf import engine
from terminal.qsf import service as svc
from terminal.qsf.service import QSF
from terminal.qsf.ledger import Ledger

class Offline:
    SEC_ARCHIVE = "https://offline/{cik}/{acc}/{doc}"
    ciks = {}
    def sec_cik(self, t):
        got = self.ciks.get(t)
        if not got:
            raise OSError("offline measurement")
        return got
    def __getattr__(self, name):
        def call(*a, **k):
            raise OSError("offline measurement")
        return call

seen, calls = {}, {}
real_card = QSF.card
def card(self, ctx, strategy, position=None):
    r = real_card(self, ctx, strategy, position)
    key = (ctx["market"], ctx["ticker"], strategy)
    calls[key] = calls.get(key, 0) + 1
    t = r.get("tech") or {}
    seen.setdefault(key, {"gap": t.get("max_gap_weekdays"), "bad": t.get("bad_rows"), "score": r.get("score"), "cons": r.get("conservative_score"), "held_back": r.get("band_held_back"),
                          "act": r.get("actionability"), "band": r.get("band"), "label": r.get("band_label"), "action": r.get("action"), "entry": r.get("entry_status"), "why": r.get("why_summary"),
                          "missing": [f["factor"] for f in r["factors"] if f["status"] == "MISSING" and f.get("scored") is not False]})
    return r
QSF.card = card
led = Ledger(mk.REAL)
last = [r for r in led._live_rows() if r["market"] == "US"][-1]
Offline.ciks = {s["ticker"]: s["cik"] for s in led._load(last) if s.get("cik")}
for market in ("US", "KR"):
    q = QSF(mk.REAL, src=Offline(), terminal=mk.terminal())
    q.scan(market, record=False, publish=False, **({} if market == "US" else {"side_files": False}))
json.dump({"|".join(k): v for k, v in seen.items()}, open(sys.argv[1], "w"), ensure_ascii=False)
import collections
for market in ("US", "KR"):
    for st in ("SWING", "LONG_TERM"):
        rows = {k[1]: v for k, v in seen.items() if k[0] == market and k[2] == st}
        gaps = collections.Counter(v["gap"] for v in rows.values())
        lower = [k for k, v in rows.items() if v["cons"] is not None and v["score"] is not None and v["cons"] < v["score"] - 1e-9]
        lower_act = [k for k in lower if rows[k]["act"] == "ACTIONABLE"]
        near = sorted(((round(rows[k]["score"], 1), round(rows[k]["cons"], 1), k, rows[k]["missing"]) for k in lower_act), reverse=True)[:5]
        print(market, st, len(rows), "gap counts", sorted(gaps.items(), key=lambda x: (x[0] is None, x[0]))[-6:], "bad rows", sum(1 for v in rows.values() if v["bad"]),
              "| a scored factor missing", len(lower), "actionable", len(lower_act), "held back", [(k, round(v["score"], 1), round(v["cons"], 1), v["band"], v["action"], v["missing"]) for k, v in rows.items() if v["held_back"]], "calls per card", collections.Counter(calls.values()))
