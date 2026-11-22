"""Offline dry scan of both markets with the code of the current directory; dumps score, band, judgement and confidence per stock."""
import json, sys
import mk
from terminal.qsf.service import QSF

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

out = {}
from terminal.qsf.ledger import Ledger
led = Ledger(mk.REAL)
last = [r for r in led._live_rows() if r["market"] == "US"][-1]
Offline.ciks = {s["ticker"]: s["cik"] for s in led._load(last) if s.get("cik")}
print("ciks", len(Offline.ciks), flush=True)
for market in ("US", "KR"):
    q = QSF(mk.REAL, src=Offline(), terminal=mk.terminal())
    res = q.scan(market, record=False, publish=False, **({} if market == "US" else {"side_files": False}))
    out[market] = {"session": res.get("session"), "rows": {f"{r['ticker']}|{r['strategy']}": {k: r.get(k) for k in ("score", "band", "band_label", "action", "actionability", "confidence", "coverage", "entry_status", "gates", "band_held_back", "conservative_score", "band_kept", "missing")} | {"gap": (r.get("tech") or {}).get("max_gap_weekdays"), "bad_rows": (r.get("tech") or {}).get("bad_rows")} | {"dom": r.get("domains")} for r in res.get("rows") or []}}
    print(market, res.get("status"), res.get("session"), len(out[market]["rows"]), flush=True)
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False)
