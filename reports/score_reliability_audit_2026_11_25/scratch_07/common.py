"""AGENT 7 scratch helpers.  Reads only the compact ledger copy (build_data.py) and terminal.qsf.config.  No return anywhere."""
import pickle, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, ".")
from terminal.qsf import config

HERE = Path("reports/score_reliability_audit_2026_11_25/scratch_07")
DATA = pickle.load(open(HERE / "ledger_compact.pkl", "rb"))
FIRST = {"US": "2026-11-09", "KR": "2026-11-11"}      # US: after the input corrections (the challenger's first day); KR: the market-value universe
OK = ("REAL", "STALE")
PROFILES = [("US", "SWING"), ("US", "LONG_TERM"), ("KR", "SWING"), ("KR", "LONG_TERM")]
FIN = {"US": "Financials", "KR": "금융"}


def sessions(market):
    return sorted({k[1] for k in DATA if k[0] == market and k[1] >= FIRST[market]})


def weights(market, strategy):
    """{factor: (weight, domain)} of the factors the live profile counts (QSF-1.6.0)."""
    p = config.profile_for(market, strategy)
    return {f: (float(w), d) for d, fs in p["domains"].items() for f, w in fs.items()}


def frame(market, session, strategy, judged_only=True):
    """tickers, X (stocks x scored factors, NaN = no value), stored scores, sectors, weights, domains, factor names."""
    slot = DATA[(market, session, strategy)]
    wd = weights(market, strategy)
    names = list(wd)
    tick = sorted(t for t, r in slot["rows"].items() if r["score"] is not None and (not judged_only or r["act"] != "INSUFFICIENT_DATA"))
    X = np.full((len(tick), len(names)), np.nan)
    for i, t in enumerate(tick):
        fac = slot["rows"][t]["fac"]
        for j, f in enumerate(names):
            v = fac.get(f)
            if v and v["st"] in OK and v["n"] is not None:
                X[i, j] = float(v["n"])
    never = config.NEVER_AVAILABLE.get((market, strategy), ())
    miss = np.array([[(slot["rows"][t]["fac"].get(f) or {}).get("st") == "MISSING" and f not in never for f in names] for t in tick], dtype=bool)
    stored = np.array([slot["rows"][t]["score"] for t in tick], dtype=float)
    sec = [slot["rows"][t]["sector"] for t in tick]
    w = np.array([wd[f][0] for f in names])
    dom = [wd[f][1] for f in names]
    return {"tick": tick, "X": X, "stored": stored, "sec": sec, "w": w, "dom": dom, "names": names, "miss": miss, "slot": slot, "versions": slot["model_versions"]}


def wmean(Z, w):
    """100 * sum(w z) / sum(w of the factors with a value): the live aggregation; a missing factor leaves both sums."""
    have = np.isfinite(Z)
    W = (have * w).sum(axis=1)
    C = np.nansum(Z * w, axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(W > 0, 100 * C / W, np.nan)


def rank(v):
    """average ranks 0..n-1 (ties shared)."""
    v = np.asarray(v, dtype=float)
    order = np.argsort(v, kind="mergesort")
    r = np.empty(len(v))
    r[order] = np.arange(len(v))
    for val in np.unique(v):
        m = v == val
        if m.sum() > 1:
            r[m] = r[m].mean()
    return r


def pct_col(col):
    out = np.full(len(col), np.nan)
    ok = np.isfinite(col)
    if ok.sum() >= 2:
        out[ok] = rank(col[ok]) / (ok.sum() - 1)
    return out


def spearman(a, b):
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 5:
        return np.nan
    ra, rb = rank(a[ok]), rank(b[ok])
    if ra.std() == 0 or rb.std() == 0:
        return np.nan
    return float(np.corrcoef(ra, rb)[0, 1])


def top_set(score, tick, share=0.2):
    ok = np.flatnonzero(np.isfinite(score))
    n = max(1, len(ok) // int(round(1 / share)))
    idx = ok[np.argsort(-score[ok], kind="mergesort")[:n]]
    return {tick[i] for i in idx}
