"""The first screen is computed before anyone opens it.

After a restart the day's list took five to eight seconds to appear: its first request rebuilt the top-stock report and read
the ledger.  A daemon thread now does that once when the server starts, and again whenever a newer scan appears on disk (the
daily job runs in another process).  Nothing is fetched from the network: the briefing reads stored records only.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Sequence

log = logging.getLogger(__name__)
EVERY_S = 300
MARKETS = ("US", "KR")


def warm_once(terminal: Any, seen: Dict[str, Optional[str]], markets: Sequence[str] = MARKETS) -> Dict[str, str]:
    """Compute the day's list of each market whose newest scan has not been warmed yet.  A failure is logged and tried again
    at the next turn; it never reaches a user request."""
    from terminal import assistant
    done: Dict[str, str] = {}
    for market in markets:
        try:
            got = terminal.qsf.latest(market)
            stamp = got.get("generated_at") or got.get("session")
            if stamp is None or seen.get(market) == stamp:
                continue
            assistant.briefing(terminal, market)
            seen[market] = stamp
            done[market] = stamp
        except Exception as exc:
            log.warning("warm-up of %s failed: %s", market, type(exc).__name__)
    return done


def start(terminal: Any, every: float = EVERY_S, sleep: Callable[[float], None] = time.sleep, turns: Optional[int] = None) -> threading.Thread:
    """``turns``: stop after this many rounds (tests); None runs for the life of the server."""
    seen: Dict[str, Optional[str]] = {}

    def loop() -> None:
        n = 0
        while turns is None or n < turns:
            warm_once(terminal, seen)
            n += 1
            sleep(every)

    thread = threading.Thread(target=loop, name="warm", daemon=True)
    thread.start()
    return thread
