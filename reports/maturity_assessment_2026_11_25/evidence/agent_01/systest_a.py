"""Agent 01 cross review, System Test A: evaluate replies saved by other agents (2026-11-25 02:29-02:30 KST, commit 73c7886)
against the same ticker's 2026-11-23 ledger snapshot (daily scan, QSF-1.5.2).  No new requests.  Labels, scores, factor values;
no returns."""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf.ledger import Ledger
EV = Path(__file__).resolve().parents[1]
FILES = [("agent_01/big/eval_KR_005930.json", "KR"), ("agent_08/big/eval_t_005930_market_KR.json", "KR"), ("agent_07/big/eval_005380.json", "KR"),
         ("agent_02/big/eval_KR_105560.json", "KR"), ("agent_02/big/eval_KR_011200.json", "KR"),
         ("agent_07/big/eval_TECH.json", "US"), ("agent_08/big/eval_t_TECH_market_US.json", "US"), ("agent_07/big/eval_GILD.json", "US"),
         ("agent_08/big/eval_t_INCY_market_US.json", "US"), ("agent_02/big/eval_US_EOG.json", "US")]
led = Ledger(REPO)
live = led._live_rows()

def flat(x, pre=""):
    out = {}
    if isinstance(x, dict):
        for k, v in x.items():
            out.update(flat(v, f"{pre}{k}."))
    elif isinstance(x, (int, float)) and not isinstance(x, bool):
        out[pre[:-1]] = float(x)
    return out

for market in ("KR", "US"):
    snaps = led._load([r for r in live if r["market"] == market][-1])
    by = {(s["ticker"], s["strategy"]): s for s in snaps}
    for f, m in FILES:
        if m != market:
            continue
        d = json.loads((EV / f).read_text(encoding="utf-8"))
        print(f"== {f}  status {d.get('status')} rank_basis {d.get('rank_basis')} deals {[x.get('form') for x in d.get('deals') or []][:3]}")
        for strat, c in (d.get("cards") or {}).items():
            s = by.get((d["ticker"], strat)) or {}
            def row(x):
                cs = x.get("conservative_score")
                return (x.get("model_version"), x.get("data_date"), None if x.get("score") is None else round(x["score"], 4), None if cs is None else round(cs, 3),
                        x.get("band"), x.get("action"), x.get("actionability"), x.get("confidence"), x.get("entry_status"), x.get("band_held_back"), x.get("deal_held"))
            print(f"  {strat:9s} card  ", row(c))
            print(f"  {'':9s} record", row(s))
            lf = {x["factor"]: x for x in c.get("factors") or []}
            rf = {x["factor"]: x for x in s.get("factors") or []}
            for k in sorted(set(lf) | set(rf)):
                a, b = rf.get(k) or {}, lf.get(k) or {}
                na, nb = a.get("normalized"), b.get("normalized")
                stat = (a.get("status"), b.get("status"))
                rawd = {kk: (flat(a.get("raw")).get(kk), v) for kk, v in flat(b.get("raw")).items() if flat(a.get("raw")).get(kk) is None or abs(flat(a.get("raw"))[kk] - v) > 1e-9 * max(1, abs(v))}
                if (na is None) != (nb is None) or (na is not None and abs(na - nb) > 1e-9) or stat[0] != stat[1] or rawd:
                    w = b.get("weight") if b.get("scored", True) is not False else 0
                    print(f"     {k:24s} w={w} status {stat} norm {None if na is None else round(na, 5)} -> {None if nb is None else round(nb, 5)} raw " +
                          ", ".join(f"{kk} {None if v0 is None else round(v0, 5)}->{round(v1, 5)}" for kk, (v0, v1) in list(rawd.items())[:4]))
            print(f"     why card  : {(c.get('why_summary') or '')[:150]}")
            print(f"     entry card: {((c.get('entry') or {}).get('reason') or '')[:110]}")
    del snaps
