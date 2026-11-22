"""Read only.  Regime factor values of each recorded session (no price, no return): the live 20-point state against the
12-point signal the one historical test used (US: VIX 5 + index trend and breadth 7; KR: index trend 5 + breadth 4)."""
import json, sys
from pathlib import Path
repo = Path(sys.argv[1])
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
from terminal.qsf import engine, config
led = Ledger(repo)
out = {}
TESTED = {"US": {"vix_regime": 5, "index_trend_breadth": 7}, "KR": {"index_trend": 5, "breadth": 4}}
for market in ("US", "KR"):
    rows = [r for r in led._live_rows() if r["market"] == market]
    seen = {}
    for r in rows:
        if r["session"] in seen:
            continue
        snaps = led._load(r)
        s = next((x for x in snaps if x.get("strategy") == "SWING" and x.get("data_date") == r["session"] and any(f.get("domain") == "REGIME" for f in x.get("factors") or [])), None)
        del snaps
        if s is None:
            continue
        st = engine.market_state(s["factors"], market)
        f = {p["factor"]: p for p in st["factors"]}
        w = c = 0.0
        for fid, wt in TESTED[market].items():
            if f.get(fid) and f[fid]["normalized"] is not None:
                w += wt; c += wt * f[fid]["normalized"]
        seen[r["session"]] = {"model": s.get("model_version"), "live": None if st["score_100"] is None else round(st["score_100"], 1), "state": st["state"], "coverage": st["coverage"],
                              "tested_signal": round(100 * c / w, 1) if w else None,
                              "factors": {k: (None if v["normalized"] is None else round(v["normalized"], 3)) for k, v in f.items()},
                              "status": {k: v["status"] for k, v in f.items()}, "as_of": {k: v["as_of"] for k, v in f.items()},
                              "raw": {k: v["raw"] for k, v in f.items()}}
    out[market] = seen
(Path(__file__).parent / "state_history.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
for m, d in out.items():
    print(m)
    for sess, v in sorted(d.items()):
        raw = v["raw"]
        extra = ""
        if m == "US":
            extra = f"vix={((raw.get('vix_regime') or {}).get('vix') or 0):.1f} term={((raw.get('vix_term') or {}).get('vix_vix3m') or 0):.2f} hy_pct={((raw.get('credit_spread') or {}).get('percentile') or 0):.2f} hy={((raw.get('credit_spread') or {}).get('spread') or 0):.2f}"
        else:
            extra = f"idx_asof={v['as_of'].get('index_trend')} fx_asof={v['as_of'].get('usdkrw_regime')} breadth={((raw.get('breadth') or {}).get('breadth') or 0):.2f}"
        print(f"  {sess} {v['model']} live={v['live']} {v['state']} cov={v['coverage']} tested={v['tested_signal']} {extra} f={v['factors']}")
