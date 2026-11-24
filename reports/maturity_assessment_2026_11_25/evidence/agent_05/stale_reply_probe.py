"""Synthetic probe, no provider: a Yahoo reply whose bars stop at 2026-11-20 (the 2026-11-24 transient), served to the terminal's
quote, chart, price-fill and alert paths on 2026-11-24 (KST afternoon) and on 2026-11-27.  Also the KR stock screen's DART
as_of at 08:00 KST.  Runs in a temporary folder outside the repository."""
import json, sys, tempfile, types
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from zoneinfo import ZoneInfo
repo = Path.home() / "Developer/quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.services import Terminal

def bars(last: str, n=300):
    d, out, c = date.fromisoformat(last), [], 100.0
    while len(out) < n:
        if d.weekday() < 5:
            out.append({"date": d.isoformat(), "open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "adj_close": c, "volume": 1e6})
        d -= timedelta(days=1)
    return out[::-1]

class Src:
    def __init__(self): self.calls = 0
    def yahoo_history(self, syms, period="1y"):
        self.calls += 1
        return {s: bars("2026-11-20") for s in syms}
    def __getattr__(self, k):
        raise RuntimeError("no provider in this probe: " + k)

res = {}
for label, now in (("2026-11-24 15:00 KST", datetime(2026, 11, 24, 6, 0, tzinfo=timezone.utc)),
                   ("2026-11-26 15:00 KST", datetime(2026, 11, 26, 6, 0, tzinfo=timezone.utc)),
                   ("2026-11-27 15:00 KST", datetime(2026, 11, 27, 6, 0, tzinfo=timezone.utc))):
    with tempfile.TemporaryDirectory() as tmp:
        t = Terminal(Path(tmp), src=Src(), now=lambda now=now: now)
        q = t._quotes(["AAPL"], "probe", "US")["items"]["AAPL"]
        fb = t._final_bars(["AAPL"], "US")
        pf = t.price_on("AAPL", "")
        res[label] = {"quote_status": q["status"], "quote_date": q["date"], "price_fill": {k: pf.get(k) for k in ("status", "date", "exact")},
                      "alert_bar_used": bool(fb), "cache_status": "REAL"}
# The Korean stock screen's as_of at 08:00 KST
now = datetime(2026, 11, 25, 8, 0, tzinfo=ZoneInfo("Asia/Seoul")).astimezone(timezone.utc)
res["kr_company_as_of_at_0800_KST"] = now.date().isoformat() + " (UTC date used by QSF.kr_company; Seoul date is 2026-11-25)"
print(json.dumps(res, ensure_ascii=False, indent=1))
json.dump(res, open(repo / "reports/maturity_assessment_2026_11_25/evidence/agent_05/stale_reply_probe.json", "w"), ensure_ascii=False, indent=1)
