"""What a t value has to be before it means what its bar says.

Every reading of this program compares a Newey-West t (``validate.newey_west_t``) with a bar such as 2.24, read from the normal
table: "passed by chance 1.25% of the time".  The audit of 2026-11-22 (QNT-01) simulated the readings' own designs on pure noise:
on 240 daily values of overlapping 20-session returns with lag 20 a t of 2.24 or more comes up 5.2% of the time, not 1.25%; the
value that does come up 1.25% of the time is about 3.4.  The estimator's variance is too small on overlapping series this short.

``bar(nominal, n, h, step, lag)`` gives that value for a reading's own design: the t that pure noise reaches as rarely as the
normal table says ``nominal`` is reached.  It is found by simulation on random numbers only (no price, no return, no record is
read), with a fixed seed, so the same design always gets the same bar.  It is never below ``nominal``.

User decision 2026-11-22 ("판정 규칙: 모두 고침").  Readings already written keep their words: this is used by readings that
have not run yet, and each protocol carries a note of the change.
"""
import math
from functools import lru_cache
from typing import Dict

import numpy as np

SIMS, SEED = 100000, 20261122
BLOCK = 4000                    # series simulated at a time: keeps memory small on an 8 GB machine


def tail(nominal: float) -> float:
    """The one-sided chance the normal table gives a t of ``nominal`` or more."""
    return 0.5 * math.erfc(nominal / math.sqrt(2.0))


def t_many(x: np.ndarray, lag: int) -> np.ndarray:
    """``validate.newey_west_t`` for every row of ``x`` at once (the same arithmetic; a row with no variance gives nan)."""
    n = x.shape[1]
    e = x - x.mean(axis=1, keepdims=True)
    var = (e * e).sum(axis=1) / n
    for k in range(1, min(lag, n - 1) + 1):
        var += 2 * (1 - k / (lag + 1)) * (e[:, k:] * e[:, :-k]).sum(axis=1) / n
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(var > 0, x.mean(axis=1) / np.sqrt(var / n), np.nan)


def noise(rng: np.random.Generator, rows: int, n: int, h: int, step: int) -> np.ndarray:
    """``rows`` series of ``n`` values: sums of ``h`` consecutive independent draws, one every ``step`` draws.  With h = 1 the
    values are independent; with h = 20 and step = 1 neighbours share 19 of their 20 draws, as daily 20-session returns do."""
    raw = rng.standard_normal((rows, (n - 1) * step + h))
    if h == 1:
        return raw[:, ::step][:, :n]
    c = np.cumsum(raw, axis=1)
    sums = c[:, h - 1:] - np.concatenate([np.zeros((rows, 1)), c[:, :-h]], axis=1)
    return sums[:, ::step][:, :n]


@lru_cache(maxsize=256)
def quantile(n: int, h: int, step: int, lag: int, level: float, sims: int = SIMS, seed: int = SEED) -> float:
    """The t that noise of this design reaches with one-sided chance ``level``."""
    rng = np.random.default_rng([seed, n, h, step, lag])
    got = np.concatenate([t_many(noise(rng, min(BLOCK, sims - done), n, h, step), lag) for done in range(0, sims, BLOCK)])
    got = got[np.isfinite(got)]
    return float(np.quantile(got, 1.0 - level))


def bar(nominal: float, n: int, h: int = 1, step: int = 1, lag: int = 0) -> float:
    """The bar a reading of ``n`` values uses in place of ``nominal``.  ``h``: sessions each value looks ahead (1: not overlapping).
    ``step``: sessions between values.  ``lag``: the lag its t is computed with."""
    if n < 3:
        return float(nominal)
    return round(max(float(nominal), quantile(int(n), max(1, int(h)), max(1, int(step)), max(0, int(lag)), tail(nominal))), 2)


@lru_cache(maxsize=64)
def plain_quantile(n: int, level: float, sims: int = SIMS, seed: int = SEED) -> float:
    """The same for the plain t of ``n`` separate values (mean over standard error, as kr_swing_challenger._t computes it)."""
    x = np.random.default_rng([seed, n, 0]).standard_normal((sims, n))
    return float(np.quantile(x.mean(axis=1) / (x.std(axis=1, ddof=1) / math.sqrt(n)), 1.0 - level))


def plain_bar(nominal: float, n: int) -> float:
    """The bar for a plain t of ``n`` separate samples: with a dozen samples the normal table's value is passed too often."""
    return float(nominal) if n < 3 else round(max(float(nominal), plain_quantile(int(n), tail(nominal))), 2)


def note(nominal: float, used: float) -> str:
    return (f"기준 t {used:g} (표의 값 {nominal:g}을 이 판정의 표본 구조에서 우연히 넘는 비율이 표와 같아지도록 모의실험으로 고친 값, 2026-11-22)" if used > nominal
            else f"기준 t {nominal:g}")


def describe(nominal: float, n: int, h: int = 1, step: int = 1, lag: int = 0) -> Dict[str, float]:
    used = bar(nominal, n, h, step, lag)
    return {"nominal": float(nominal), "used": used, "one_sided_chance": tail(nominal), "n": int(n), "h": int(h), "step": int(step), "lag": int(lag)}
