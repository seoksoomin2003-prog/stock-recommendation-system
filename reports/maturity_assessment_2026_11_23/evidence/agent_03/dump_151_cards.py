"""Agent 03: offline dry scan (record=False, publish=False) with today's code (QSF-1.5.1) on the stored copies.

Every provider call raises, so nothing is fetched; nothing is recorded.  Captures per card only what the factor study needs
(scores, bands, factor rows with normalized and raw values, a few context marks).  No return, IC or performance figure is computed.
Output: big/cards_151.json (larger than 60 KB, so it stays out of the repository).
"""
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
FUND_KEYS = ("is_financial", "loss_now", "cash_burn", "market_cap", "sector", "debt_basis", "status", "pe", "pb", "fcf_yield", "roe", "op_margin", "gross_margin",
             "rev_growth", "eps_growth", "rev_cagr3", "eps_cagr3", "ocf_to_ni", "fcf_margin", "fcf_years_positive", "roe_years_positive", "debt_equity",
             "current_ratio", "interest_cover", "cash_debt", "equity_assets", "share_change", "returns_capital", "insider_pct", "cash_flow_note")
out = {}
for market in ("US", "KR"):
    t = Terminal(REPO)
    q = QSF(REPO, src=Offline(), terminal=t)
    seen = {}
    make = q.card

    def keep(ctx, strategy, position=None, _make=make, _seen=seen, _q=q, _market=market):
        c = _make(ctx, strategy, position)
        fund = ctx.get("fund") or {}
        sector = fund.get("sector")
        if _market == "KR":
            try:
                sector = (_q.kr_sector(ctx["ticker"]) or {}).get("sector")
            except Exception:
                sector = None
        tech = c.get("tech") or {}
        _seen[f"{c['ticker']}|{strategy}"] = {
            "ticker": c["ticker"], "name": c.get("name"), "strategy": strategy, "score": c.get("score"), "conservative": c.get("conservative_score"),
            "band": c.get("band"), "band_label": c.get("band_label"), "held_back": c.get("band_held_back"), "action": c.get("action"), "raw_action": c.get("raw_action"),
            "actionability": c.get("actionability"), "confidence": c.get("confidence"), "coverage": c.get("coverage"), "input_coverage": c.get("input_coverage"),
            "gates": [g["code"] for g in c.get("gates") or []], "entry_status": c.get("entry_status"), "price": c.get("price"), "stop": (c.get("levels") or {}).get("stop"),
            "sector": sector, "fund": {k: fund.get(k) for k in FUND_KEYS},
            "tech": {k: tech.get(k) for k in ("atr_pct", "adv_value", "hist_vol", "rsi", "dist_high", "ret_126", "ret_12_1", "resistance", "atr", "close", "ma20", "breakout", "volume_ratio")},
            "earnings": {k: (ctx.get("earnings") or {}).get(k) for k in ("sessions", "basis", "overdue")},
            "rs_rank": ctx.get("rs_rank"),
            "factors": [{k: f.get(k) for k in ("factor", "domain", "weight", "reference_weight", "scored", "status", "normalized", "raw", "inputs")} for f in c["factors"]]}
        return c
    q.card = keep
    res = q.scan(market, record=False, publish=False, **({} if market == "US" else {"side_files": False}))
    q.card = make
    out[market] = {"session": res.get("session"), "status": res.get("status"), "cards": seen}
    print(market, res.get("session"), res.get("status"), len(seen), flush=True)
dst = Path(__file__).parent / "big" / "cards_151.json"
dst.write_text(json.dumps(out, ensure_ascii=False, default=str), encoding="utf-8")
print("written", dst, dst.stat().st_size)
