"""Shared helpers for the audit simulations.  Synthetic random data only; nothing of the repository is read or imported."""
import math
import numpy as np

def newey_west_t_repo(x, lag):
    """VERBATIM copy of terminal/qsf/validate.py:207-216 (newey_west_t)."""
    a = np.asarray(x, dtype=float)
    n = len(a)
    if n < 3:
        return None
    e = a - a.mean()
    var = float((e * e).sum() / n)
    for k in range(1, min(lag, n - 1) + 1):
        var += 2 * (1 - k / (lag + 1)) * float((e[k:] * e[:-k]).sum() / n)
    return float(a.mean() / math.sqrt(var / n)) if var > 0 else None

def nw_t(A, lag, kernel="bartlett"):
    """Vectorised over rows of A (S x n).  bartlett = the repo's weights; 'uniform' = Hansen-Hodrick (weights 1 up to lag)."""
    A = np.asarray(A, dtype=float)
    n = A.shape[1]
    m = A.mean(axis=1, keepdims=True)
    e = A - m
    var = (e * e).sum(axis=1) / n
    for k in range(1, min(lag, n - 1) + 1):
        w = (1 - k / (lag + 1)) if kernel == "bartlett" else 1.0
        var = var + 2 * w * (e[:, k:] * e[:, :-k]).sum(axis=1) / n
    out = np.full(A.shape[0], np.nan)
    ok = var > 0
    out[ok] = m[ok, 0] / np.sqrt(var[ok] / n)
    return out

def plain_t(A):
    A = np.asarray(A, dtype=float)
    n = A.shape[1]
    return A.mean(axis=1) / (A.std(axis=1, ddof=1) / math.sqrt(n))

def ranks(x):
    """Ordinal ranks along the last axis (continuous data: no ties)."""
    return np.argsort(np.argsort(x, axis=-1), axis=-1).astype(float)

def rowcorr(a, b):
    a = a - a.mean(axis=-1, keepdims=True)
    b = b - b.mean(axis=-1, keepdims=True)
    return (a * b).sum(axis=-1) / np.sqrt((a * a).sum(axis=-1) * (b * b).sum(axis=-1))

def selfcheck():
    rng = np.random.default_rng(1)
    for n, lag in ((240, 20), (77, 12), (22, 12), (240, 5), (12, 1)):
        A = rng.standard_normal((5, n)).cumsum(axis=1) * 0.1 + rng.standard_normal((5, n))
        v = nw_t(A, lag)
        for i in range(5):
            assert abs(v[i] - newey_west_t_repo(A[i], lag)) < 1e-9, (n, lag)
    return True
