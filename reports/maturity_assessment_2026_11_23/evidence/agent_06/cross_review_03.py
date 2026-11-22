"""Agent 06, cross review of Agent 03.  Scores and factor values of ONE session (Agent 03's own offline re-scoring) and random
numbers.  No price, no return, no IC, no forward record."""
import json
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[4]
rng = np.random.default_rng(2306)


def ranks(x):
    o = np.argsort(np.argsort(x, kind="mergesort"), kind="mergesort").astype(float)
    return o


def rho(a, b):
    return float(np.corrcoef(ranks(a), ranks(b))[0, 1])


def score(X, w):
    """100 * sum(w x) / sum(w of present factors); X has nan where a factor is missing."""
    have = np.isfinite(X)
    return 100 * np.nansum(X * w, axis=1) / (have * w).sum(axis=1)


print("A. random numbers: what a +-20% weight shake does to ANY weighted sum (independent uniform factors, 500 stocks)")
for p in (10, 16):
    X = rng.uniform(0, 1, (500, p)); w = rng.choice([2, 3, 5, 10, 15], p).astype(float); s = score(X, w)
    for label, draw in (("+-20%", lambda: rng.uniform(0.8, 1.2, p)), ("+-50%", lambda: rng.uniform(0.5, 1.5, p)), ("x or / 2", lambda: 2.0 ** rng.uniform(-1, 1, p)), ("x or / 4", lambda: 4.0 ** rng.uniform(-1, 1, p))):
        got = [rho(s, score(X, w * draw())) for _ in range(300)]
        print(f"  {p} factors, weights {label:9s}: rank correlation 5% point {np.quantile(got, .05):.3f}, median {np.median(got):.3f}")

print()
print("B. random numbers: effective-number measures when the factors are truly independent (sampling only)")
for n, p in ((504, 16), (300, 16), (300, 10)):
    pr, k1 = [], []
    for _ in range(400):
        X = rng.standard_normal((n, p))
        R = np.corrcoef(np.apply_along_axis(ranks, 0, X), rowvar=False)
        ev = np.linalg.eigvalsh(R)
        pr.append(ev.sum() ** 2 / (ev ** 2).sum()); k1.append((ev > 1).sum())
    print(f"  n={n} p={p}: participation ratio {np.mean(pr):.1f} of {p}; eigenvalues over 1: {np.mean(k1):.1f} (so a count of 'eigenvalues over 1' near {p // 2} means no structure at all)")

print()
print("C. Agent 03's re-scored cards of 2026-11-20 (scores and factor values only)")
path = REPO / "reports/maturity_assessment_2026_11_23/evidence/agent_03/big/cards_151.json"
if not path.exists():
    print("  cards file not found"); raise SystemExit
data = json.loads(path.read_text(encoding="utf-8"))
one = next(iter(data["US"]["cards"].values()))
print("  card keys:", sorted(one.keys())[:40])
fkey = "factors" if "factors" in one else None
print("  factor entry:", (one[fkey][0] if isinstance(one.get(fkey), list) else list(one.get(fkey, {}).items())[:1]) if fkey else None)
for market in ("US", "KR"):
    for strategy in ("SWING", "LONG_TERM"):
        cards = [c for c in data[market]["cards"].values() if c["strategy"] == strategy and c.get("score") is not None]
        rows = [c[fkey] for c in cards]
        if isinstance(rows[0], dict):
            rows = [[dict(v, factor=k) for k, v in r.items()] for r in rows]
        names = sorted({f["factor"] for r in rows for f in r if f.get("scored") is not False})
        W = {f["factor"]: float(f["weight"]) for r in rows for f in r if f.get("scored") is not False}
        D = {f["factor"]: f.get("domain") for r in rows for f in r}
        X = np.full((len(cards), len(names)), np.nan)
        for i, r in enumerate(rows):
            for f in r:
                if f.get("scored") is False or f.get("normalized") is None or f["factor"] not in names:
                    continue
                X[i, names.index(f["factor"])] = float(f["normalized"])
        w = np.array([W[n] for n in names]); s = np.array([c["score"] for c in cards]); re = score(X, w)
        print(f"  {market} {strategy}: {len(cards)} stocks, {len(names)} factors, rebuilt score max gap {np.nanmax(np.abs(re - s)):.4f}")
        top = lambda v, k: set(np.argsort(-v)[:k])          # noqa: E731
        k20 = max(1, len(cards) // 5)
        for dom in sorted({D[n] for n in names}):
            keep = np.array([D[n] != dom for n in names])
            alt = score(X[:, keep], w[keep])
            share = w[~keep].sum() / w.sum()
            print(f"     without {dom:12s} (weight share {share * 100:4.1f}%): rank correlation {rho(re, alt):.3f}, top fifth kept {len(top(re, k20) & top(alt, k20))}/{k20}, top 20 kept {len(top(re, 20) & top(alt, 20))}/20, mean score {np.nanmean(alt) - np.nanmean(re):+.1f}")
        for label, draw in (("+-20%", lambda: rng.uniform(0.8, 1.2, len(w))), ("+-50%", lambda: rng.uniform(0.5, 1.5, len(w))), ("x or / 2", lambda: 2.0 ** rng.uniform(-1, 1, len(w)))):
            got = [(rho(re, a), len(top(re, 20) & top(a, 20))) for a in (score(X, w * draw()) for _ in range(300))]
            print(f"     weights {label:9s}: rank correlation 5% point {np.quantile([g[0] for g in got], .05):.3f}, top 20 kept (5% point) {int(np.quantile([g[1] for g in got], .05))}/20")
