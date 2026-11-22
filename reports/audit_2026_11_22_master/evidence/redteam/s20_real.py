"""Read-only survey of the newest recorded session: scores and factor values only.  No price path, no return."""
from common import *
from pathlib import Path
from collections import Counter
from terminal.qsf.ledger import Ledger
from terminal.cache import FileCache
from terminal.committee import figures as fg, investors as iv, council
from terminal.committee import service as cs
from terminal import analyst_extra as ax

led = Ledger(Path(REPO))
cache = FileCache(Path(REPO) / "data" / "qsf" / "cache")
rows = led._live_rows()
for market in ("US", "KR"):
    last = max(r["session"] for r in rows if r["market"] == market)
    snaps = [s for r in rows if r["market"] == market and r["session"] == last for s in led._load(r)]
    snaps = [s for s in snaps if s.get("data_date") == last]
    print(f"\n================ {market} session {last}: {len(snaps)} snapshots, model {Counter(s.get('model_version') for s in snaps).most_common(2)}")
    for strat in ("SWING", "LONG_TERM"):
        ss = [s for s in snaps if s["strategy"] == strat]
        buy = [s for s in ss if s.get("action") == "BUY"]
        raw_buy = [s for s in ss if (s.get("score") or 0) >= 70]
        print(f" {strat}: n={len(ss)} | score>=70: {len(raw_buy)} | action BUY (actionable): {len(buy)} by confidence {dict(Counter(s['confidence'] for s in buy))} | min coverage among BUY: {min((s['coverage'] for s in buy), default=None)}"
              f" | BUY with entry ENTRY_NOW: {sum(1 for s in buy if s.get('entry_status') == 'ENTRY_NOW')} | all-confidence {dict(Counter(s['confidence'] for s in ss))}")
        # hidden gaps: sub-fields that were None inside factors the card counts as REAL
        def gaps(s):
            tot = miss = 0
            for f in s["factors"]:
                if f.get("status") in ("REAL", "STALE") and f.get("scored", True) is not False and f["domain"] in ("FUNDAMENTAL",) and isinstance(f.get("raw"), dict):
                    for k, v in f["raw"].items():
                        tot += 1; miss += v is None
            return miss, tot
        g = [(gaps(s), s) for s in buy]
        thin = [(m, t, s["ticker"], s["confidence"], round(s["coverage"], 2), round(s["score"], 1)) for (m, t), s in g if t and m / t >= 0.25]
        print(f"   BUY cards whose counted fundamental factors had >=25% of their raw sub-fields empty: {len(thin)} of {len(buy)}; examples (missing, of, ticker, confidence, coverage, score): {sorted(thin, reverse=True)[:6]}")
    lt = {s["ticker"]: s for s in snaps if s["strategy"] == "LONG_TERM"}
    sw = {s["ticker"]: s for s in snaps if s["strategy"] == "SWING"}
    def raw(s, fac, key):
        return next(((f.get("raw") or {}).get(key) for f in s["factors"] if f["factor"] == fac), None)
    de = {t: raw(s, "leverage", "debt_equity") for t, s in lt.items()}
    roe = {t: raw(s, "business_quality", "roe") for t, s in lt.items()}
    pe = {t: raw(s, "valuation", "pe") for t, s in lt.items()}
    epsg = {t: raw(s, "earnings_revenue_quality", "eps_growth") for t, s in sw.items()}
    eps3 = {t: raw(s, "growth_quality", "eps_cagr3") for t, s in lt.items()}
    print(f" LONG cards: debt_equity == 99.0 (no-equity mark): {sum(1 for v in de.values() if v == 99.0)} | D/E > 99: {sum(1 for v in de.values() if v is not None and v > 99)} | D/E < 0 or -0.0: {sum(1 for v in de.values() if v is not None and (v < 0 or (v == 0 and math.copysign(1, v) < 0)))}"
          f" | ROE > 100%: {sum(1 for v in roe.values() if v is not None and v > 1)} (max {max((v for v in roe.values() if v is not None), default=None)}) | ROE None: {sum(1 for v in roe.values() if v is None)}")
    loss = [t for t, v in pe.items() if v is not None and v <= 0]
    print(f" loss-makers (PER<=0): {len(loss)}; of them latest EPS growth is None: {sum(1 for t in loss if epsg.get(t) is None)}; 3y EPS growth None: {sum(1 for t in loss if eps3.get(t) is None)}")
    gq = [(t, next((f['normalized'] for f in lt[t]['factors'] if f['factor'] == 'growth_quality'), None)) for t in loss]
    print(f"   loss-makers with growth_quality >= 0.7: {[(t, round(v, 2)) for t, v in gq if v is not None and v >= 0.7][:12]}")
    if market != "US":
        continue
    # committee on the same snapshots, as terminal/committee/service.py builds it (marks and merger filings left out: they only add risks)
    figs = {}
    for t in sorted(set(lt) | set(sw)):
        if t in cs.BENCHMARKS:
            continue
        info = (cache.read(f"info:{t}") or {}).get("data") or {}
        sector = ax.SECTOR_KO.get(info.get("sector"), info.get("sector"))
        f = fg.read(lt.get(t), sw.get(t), info, sector)
        f["name"] = t
        figs[t] = (f, info)
    ctx_ = cs.context({t: f for t, (f, _i) in figs.items()})
    book = {t: cs.judge(f, None, ctx_) for t, (f, _i) in figs.items()}
    print(" committee decisions:", dict(Counter(e["committee"]["decision"] for e in book.values())))
    for k in iv.ORDER:
        print(f"   {k}: {dict(Counter(e['opinions'][k]['recommendation'] for e in book.values()))}")
    cross = Counter()
    for t, e in book.items():
        q = lt.get(t)
        if q is None:
            continue
        qa = "QSF_LONG_BUY+ENTRY_NOW" if q.get("action") == "BUY" and q.get("entry_status") == "ENTRY_NOW" else "QSF_LONG_BUY(other entry)" if q.get("action") == "BUY" else "QSF_LONG_" + str(q.get("action"))
        cross[(qa, e["committee"]["decision"])] += 1
    print(" QSF long action x committee decision:")
    for (a, d), n in sorted(cross.items(), key=lambda kv: (kv[0][0], -kv[1])):
        print(f"    {a:28s} {d:18s} {n}")
    ex = [(t, round(lt[t]["score"], 1), [r["name"] for r in e["committee"]["material_risks"]][:3]) for t, e in book.items() if t in lt and lt[t].get("action") == "BUY" and e["committee"]["decision"] in ("AVOID", "SELL")]
    print(" examples QSF long BUY & committee AVOID:", ex[:8])
    ex2 = [(t, round(lt[t]["score"], 1)) for t, e in book.items() if t in lt and lt[t].get("action") == "AVOID" and e["committee"]["decision"] in ("BUY", "STRONG_BUY", "CONDITIONAL_BUY")]
    print(" examples QSF long AVOID & committee buy-side:", ex2[:8])
    exs = [(t, round(sw[t]["score"], 1)) for t, e in book.items() if t in sw and sw[t].get("action") == "BUY" and e["committee"]["decision"] in ("AVOID", "SELL")]
    print(" examples QSF swing BUY & committee AVOID:", exs[:8])
    # Yahoo 'Financial Services' that the score treats as an ordinary company
    mism = [t for t, (f, i) in figs.items() if f["kind"] == "FINANCIAL" and t in lt and any(x["factor"] == "leverage" and x.get("status") == "REAL" for x in lt[t]["factors"])]
    print(f" committee kind FINANCIAL but QSF scored as non-financial (leverage factor REAL): {len(mism)} -> {mism[:25]}")
    for t in mism[:3]:
        e = book[t]
        print(f"    {t}: committee confidence {e['committee']['scores']['confidence']}, data {e['committee']['scores']['data']}, decision {e['committee']['decision']}; " + "; ".join(f"{k[:3]} {o['recommendation']} conf {o['confidence']} cov {o['coverage']}" for k, o in e["opinions"].items()))
    fins = [e for t, e in book.items() if figs[t][0]["kind"] == "FINANCIAL"]
    conf = sorted(e["committee"]["scores"]["confidence"] for e in fins if e["committee"]["scores"]["confidence"] is not None)
    print(f" financial-sector stocks: {len(fins)}; committee confidence min/median/max: {conf[0] if conf else None}/{conf[len(conf)//2] if conf else None}/{conf[-1] if conf else None}; decisions {dict(Counter(e['committee']['decision'] for e in fins))}")
    dy = [(t, i.get("dividendYield")) for t, (f, i) in figs.items() if i.get("dividendYield") is not None]
    vals = sorted(v for _t, v in dy)
    print(f" stored Yahoo dividendYield: n={len(vals)}, median {vals[len(vals)//2]}, max {vals[-1]}, over 8.0: {[(t, v) for t, v in dy if v > 8][:8]}; KO={dict(dy).get('KO')} JNJ={dict(dy).get('JNJ')} T={dict(dy).get('T')}")
    deals = 0
