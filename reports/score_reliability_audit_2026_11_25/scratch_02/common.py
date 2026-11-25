"""Shared read-only helpers for Agent 2's experiments.  Nothing here reads a price path, an outcome or a return."""
import sys, json, gzip, math
from pathlib import Path
import numpy as np
sys.path.insert(0, ".")
from terminal.qsf.ledger import Ledger
from terminal.qsf import config, engine, factors

OUT = Path("reports/score_reliability_audit_2026_11_25/scratch_02")
LED = Ledger(Path("."))
QUAL = ("REAL", "STALE")
_cache = {}


def sessions(market):
    """[(session, model_version)] in order, one per session."""
    seen = {}
    for r in LED._live_rows():
        if r["market"] == market:
            seen[r["session"]] = r["model_version"]
    return sorted(seen.items())


def load(market, session):
    """{strategy: {ticker: snapshot}} of a session.  A stock recorded in two live shards keeps its LAST record (noted in s01)."""
    key = (market, session)
    if key not in _cache:
        out = {"SWING": {}, "LONG_TERM": {}}
        dup = 0
        for r in LED._live_rows():
            if r["market"] == market and r["session"] == session:
                for s in LED._load(r):
                    if s["ticker"] in out[s["strategy"]]:
                        dup += 1
                    out[s["strategy"]][s["ticker"]] = s
        out["_dup"] = dup
        _cache[key] = out
    return _cache[key]


def scored_rows(s):
    return [f for f in s["factors"] if f.get("scored") is not False and f.get("weight")]


def recompute(rows):
    """composite from factor rows, the engine's formula (engine.py:240)."""
    w = c = 0.0
    for f in rows:
        if f.get("status") in QUAL and f.get("normalized") is not None:
            w += f["weight"]; c += f["weight"] * f["normalized"]
    return 100 * c / w if w else None


def matrix(snaps, profile=None):
    """tickers, factor ids, weights (profile's), N[i,f] (nan = no data), A[i,f] (False = NOT_APPLICABLE)."""
    tick = sorted(snaps)
    s0 = snaps[tick[0]]
    prof = profile or config.profile_for(s0["market"], s0["strategy"])
    fids, w, dom = [], [], []
    for d in config.DOMAINS:
        for fid, wt in prof["domains"][d].items():
            fids.append(fid); w.append(float(wt)); dom.append(d)
    N = np.full((len(tick), len(fids)), np.nan)
    A = np.ones((len(tick), len(fids)), bool)
    for i, t in enumerate(tick):
        by = {f["factor"]: f for f in snaps[t]["factors"] if f.get("scored") is not False}
        for j, fid in enumerate(fids):
            f = by.get(fid)
            if f is None:
                continue
            if f.get("status") == "NOT_APPLICABLE":
                A[i, j] = False
            if f.get("status") in QUAL and f.get("normalized") is not None:
                N[i, j] = f["normalized"]
    return tick, fids, np.array(w), dom, N, A


def composite(N, w):
    """vectorised engine formula: missing leaves both sums."""
    have = ~np.isnan(N)
    num = np.nansum(N * w, axis=1)
    den = (have * w).sum(axis=1)
    return np.where(den > 0, 100 * num / np.where(den > 0, den, 1), np.nan)


def rank(x):
    """average ranks, nan stays nan."""
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    ok = ~np.isnan(x)
    v = x[ok]
    order = np.argsort(v, kind="mergesort")
    r = np.empty(len(v)); r[order] = np.arange(1, len(v) + 1)
    # ties: average
    sv = v[order]
    i = 0
    while i < len(sv):
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        if j > i:
            r[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    out[ok] = r
    return out


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = ~np.isnan(a) & ~np.isnan(b)
    if ok.sum() < 3:
        return float("nan")
    ra, rb = rank(a[ok]), rank(b[ok])
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def top_set(score, k):
    """indices of the k highest scores (ties broken by position, as a stable sort would)."""
    s = np.where(np.isnan(score), -np.inf, score)
    return set(np.argsort(-s, kind="mergesort")[:k].tolist())


def us_sectors():
    d = json.load(gzip.open("data/qsf/research/scores_current_us.json.gz"))
    out = {}
    for r in d["records"]:
        if r.get("sector"):
            out[r["t"]] = r["sector"]
    return out


def kr_sectors():
    """code -> broad sector, as terminal/qsf/views.py:_kr_industries reads it (stored master snapshot, no network)."""
    from terminal import kr_sectors as ks
    import pandas as pd
    sdir = Path("data/kr/security_master")
    meta = json.loads((sdir / "LATEST.json").read_text(encoding="utf-8"))
    df = pd.read_csv(sdir / meta["file"], dtype=str, usecols=lambda c: c in ("canonical_ticker", "industry", "company_name"))
    out = {}
    for c, i, n in zip(df["canonical_ticker"], df["industry"], df["company_name"]):
        if isinstance(c, str) and isinstance(i, str) and i.strip():
            sec = ks.broad_sector(c, i, n if isinstance(n, str) else None)
            if sec:
                out[c] = sec
    return out


def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
