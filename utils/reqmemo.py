"""Results kept for the length of one screen request (2026-11-29, final latency review).

One request for the Today page asked for the newest scan sixteen times, and each time the 630 KB file was parsed and its
thousand rows labelled again (2 to 3 seconds for a page whose inputs had not changed in between).  Inside ``scope()`` a value
asked for under the same key is computed once.  Outside a scope (the daily job, a test, a command) nothing is kept, so nothing
can go stale: the memory lives exactly as long as the request that opened it, on that request's own thread.
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Hashable

_local = threading.local()


class scope:
    """``with scope():`` around the work of one request.  A scope opened inside another shares the outer one's memory."""

    def __enter__(self):
        self.outer = getattr(_local, "memo", None)
        if self.outer is None:
            _local.memo = {}
        return self

    def __exit__(self, *exc):
        if self.outer is None:
            _local.memo = None
        return False


def get(key: Hashable, compute: Callable[[], Any]) -> Any:
    memo = getattr(_local, "memo", None)
    if memo is None:
        return compute()
    if key not in memo:
        memo[key] = compute()
    return memo[key]
