"""Walk-forward order of work: whatever is fitted for a day reads only days whose outcome was already known on that day.

A day's outcome runs from the next session's open to the close ``horizon`` sessions after the day (``validate.Prices.forward``), so
day ``j`` may teach day ``k`` only when ``rows[j] + horizon <= rows[k]``.  Days nearer than that are purged: their outcome still
overlaps the test day.  Nothing here knows what is being fitted; it only decides who may see what, and keeps a log that can be checked.
"""
from typing import Any, Callable, Dict, List, Sequence, Tuple


def known(rows: Sequence[int], k: int, horizon: int, embargo: int = 0) -> List[int]:
    """Positions before ``k`` whose outcome had fully ended by the close of ``rows[k]`` (``embargo`` more sessions kept apart)."""
    return [j for j in range(k) if rows[j] + horizon + embargo <= rows[k]]


def walk(rows: Sequence[int], horizon: int, min_train: int, fit: Callable[[List[int]], Any], apply: Callable[[Any, int], Any],
         embargo: int = 0) -> Tuple[Dict[int, Any], List[Dict[str, int]]]:
    """``fit(train positions)`` then ``apply(model, test position)`` for every day with at least ``min_train`` usable past days.
    Returns the results by test position and the log of what each test day was allowed to read."""
    if list(rows) != sorted(set(rows)):
        raise ValueError("ROWS_NOT_IN_ORDER")
    out: Dict[int, Any] = {}
    log: List[Dict[str, int]] = []
    for k in range(len(rows)):
        train = known(rows, k, horizon, embargo)
        if len(train) < min_train:
            continue
        out[k] = apply(fit(train), k)
        log.append({"test": int(rows[k]), "train": len(train), "last_train": int(rows[train[-1]]), "gap": int(rows[k] - rows[train[-1]])})
    return out, log


def leak_free(log: Sequence[Dict[str, int]], horizon: int, embargo: int = 0) -> bool:
    """Every test day in the log stands at least a full outcome after the newest day it learned from."""
    return all(r["gap"] >= horizon + embargo and r["last_train"] < r["test"] for r in log)
