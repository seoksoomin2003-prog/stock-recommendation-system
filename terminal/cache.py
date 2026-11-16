"""TTL file cache with honest STALE fallback (TERMINAL-1 §3).

``cached(key, ttl, fetch)`` returns ``{"status", "data", "fetched_at", "age_s", "error"}``:
* fresh cache hit / successful fetch -> REAL
* fetch failed but an older copy exists -> STALE (old data, clearly labelled, never presented as fresh)
* fetch failed and nothing cached -> UNAVAILABLE (data None)
A fetch that returns None or an empty payload counts as a failure (missing is never stored as data).
"""
import hashlib
import json
import os
import threading
import time
import weakref
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional


KEY_WAIT_S = 120            # how long a request waits for another request's fetch of the same key before fetching itself


class _KeyLock:
    __slots__ = ("lock", "__weakref__")

    def __init__(self):
        self.lock = threading.RLock()


class FileCache:
    def __init__(self, root: Path, clock: Callable[[], float] = time.time):
        self.root = Path(root)
        self.clock = clock
        self._key_locks: "weakref.WeakValueDictionary[str, _KeyLock]" = weakref.WeakValueDictionary()   # a lock lives while a request uses it
        self._key_guard = threading.Lock()

    def _path(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)[:80]
        h = hashlib.sha256(key.encode()).hexdigest()[:10]
        return self.root / f"{safe}_{h}.json"

    def read(self, key: str) -> Optional[Dict[str, Any]]:
        p = self._path(key)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def write(self, key: str, data: Any) -> Dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        rec = {"key": key, "stored_at": self.clock(), "data": data}
        p = self._path(key)
        tmp = p.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")     # concurrent requests can write one key
        tmp.write_text(json.dumps(rec, ensure_ascii=False, default=str), encoding="utf-8")
        os.replace(tmp, p)
        return rec

    def cached(self, key: str, ttl_s: float, fetch: Callable[[], Any]) -> Dict[str, Any]:
        now = self.clock()
        old = self.read(key)
        if old is not None and now - old["stored_at"] <= ttl_s:
            return _result("REAL", old, now)
        # One fetch per key at a time.  Two requests that missed the same key each fetched it (a Korean stock tab started the same
        # eight statement requests twice).  The second now waits and reads what the first stored; if the first failed, or the wait
        # runs out, it fetches as before.
        with self._key_guard:
            holder = self._key_locks.get(key)
            if holder is None:
                holder = self._key_locks[key] = _KeyLock()
        got = holder.lock.acquire(timeout=KEY_WAIT_S)
        try:
            return self._fetch_and_store(key, ttl_s, fetch)
        finally:
            if got:
                holder.lock.release()

    def _fetch_and_store(self, key: str, ttl_s: float, fetch: Callable[[], Any]) -> Dict[str, Any]:
        now = self.clock()
        old = self.read(key)
        if old is not None and now - old["stored_at"] <= ttl_s:
            return _result("REAL", old, now)
        err = None
        try:
            data = fetch()
        except Exception as exc:  # provider failure -> fall back, never fabricate
            data, err = None, type(exc).__name__
        if data not in (None, {}, []):
            try:
                return _result("REAL", self.write(key, data), now)
            except OSError:                 # a full disk must not throw away what was just fetched: it is returned, only not kept
                return _result("REAL", {"stored_at": now, "data": data}, now, "NOT_STORED")
        if old is not None:
            return _result("STALE", old, now, err or "EMPTY_RESPONSE")
        return {"status": "UNAVAILABLE", "data": None, "fetched_at": None, "age_s": None,
                "error": err or "EMPTY_RESPONSE"}


def _result(status: str, rec: Dict[str, Any], now: float, error: Optional[str] = None) -> Dict[str, Any]:
    return {"status": status, "data": rec["data"],
            "fetched_at": datetime.fromtimestamp(rec["stored_at"], timezone.utc).isoformat(),
            "age_s": round(now - rec["stored_at"], 1), "error": error}
