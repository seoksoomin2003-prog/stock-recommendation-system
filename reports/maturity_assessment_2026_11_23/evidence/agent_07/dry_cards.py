"""Agent 7: dry scan on stored copies (every provider call raises; record=False, publish=False), keeping each card as today's code
makes it.  Nothing is written but the output file under big/.  No return is computed."""
import json, sys
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
market = sys.argv[1]
q = QSF(REPO, src=Offline(), terminal=Terminal(REPO))
seen = {}
make = q.card
def keep(ctx, strategy, position=None):
    c = make(ctx, strategy, position)
    d = {k: v for k, v in c.items() if k not in ("tech", "position", "exit")}
    t = c.get("tech") or {}
    d["tech_small"] = {k: t.get(k) for k in ("close", "atr", "atr_pct", "ma20", "ma50", "ma200", "resistance", "support", "breakout", "volume_ratio", "date")}
    d["fund_small"] = {k: (ctx.get("fund") or {}).get(k) for k in ("sector", "industry", "is_financial", "pe", "eps", "rev_growth", "op_margin", "fcf_margin", "roe", "period_basis", "filed")}
    d["earnings"] = ctx.get("earnings")
    seen[c["ticker"] + "|" + strategy] = d
    return c
q.card = keep
res = q.scan(market, record=False, publish=False, **({} if market == "US" else {"side_files": False}))
print(market, res.get("status"), res.get("session"), len(seen), flush=True)
(Path(__file__).parent / "big" / f"cards_{market}.json").write_text(json.dumps(seen, ensure_ascii=False, default=str), encoding="utf-8")
