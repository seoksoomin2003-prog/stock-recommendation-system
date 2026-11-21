"""Coin market data for a machine that does not have the horizon_bot_beta predictor: the exchange's public market data, read directly.

Used only when the predictor's files are absent (terminal/coin_bridge.py decides).  It asks Binance's documented public futures
endpoints for the thirty most traded USDT perpetuals: four-hour bars and funding rates.  No key, no account, no order.  One refresh
is about sixty requests, made at most once per four-hour close and only when someone opens the coin screen; the reply is kept on disk.

Checked 2026-11-21: the host's robots.txt names search-engine crawlers only; the exchange publishes a limit of 2,400 request weight
a minute (a refresh uses about 350); its data terms allow personal use and restrict commercial redistribution.  If the exchange
refuses, nothing is retried harder: the last stored reply is shown as old, or the screen says the data could not be read.
"""
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

HOST = "https://fapi.binance.com"
BAR_MS = 4 * 3600 * 1000
COINS = 30
BARS = 1500                     # 250 days of four-hour bars: enough for a 200-day average
FUNDING_ROWS = 100
MIN_LISTED_DAYS = 180           # a coin listed for less than half a year is left out, as the predictor does
PAUSE_S = 0.15
RETRY_AFTER_S = 600             # after a failed refresh, the next try waits this long
SKIP_BASES = {"USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "BTCDOM", "DEFI"}
CACHE = Path("data") / "terminal" / "cache" / "coin_public.json"
UA = {"User-Agent": "quant-terminal (personal use)"}
_LOCK = threading.Lock()
_FAILED: Dict[str, Tuple[int, str]] = {}          # cache path -> (when the last refresh failed, the failure's type name)


def latest_close(now_ms: int) -> int:
    return now_ms // BAR_MS * BAR_MS


def pick(info: Dict[str, Any], tickers: List[Dict[str, Any]], now_ms: int, count: int = COINS) -> List[str]:
    """The most traded USDT perpetuals on coins, by the last day's turnover: no index contract, no stablecoin, no new listing."""
    ok = set()
    for s in info.get("symbols") or []:
        if s.get("contractType") != "PERPETUAL" or s.get("quoteAsset") != "USDT" or s.get("status") != "TRADING":
            continue
        if s.get("underlyingType") not in (None, "COIN") or s.get("baseAsset") in SKIP_BASES:
            continue
        if s.get("onboardDate") and now_ms - int(s["onboardDate"]) < MIN_LISTED_DAYS * 86400000:
            continue
        ok.add(s["symbol"])
    ranked = sorted((t for t in tickers if t.get("symbol") in ok), key=lambda t: -float(t.get("quoteVolume") or 0))
    return [t["symbol"] for t in ranked[:count]]


def fetch(get: Callable[[str, Dict[str, Any]], Any], now_ms: int, sleep: Callable[[float], None] = time.sleep) -> Dict[str, Any]:
    """One refresh.  ``get(path, params)`` returns the parsed reply or raises."""
    close = latest_close(now_ms)
    symbols = pick(get("/fapi/v1/exchangeInfo", {}), get("/fapi/v1/ticker/24hr", {}), now_ms)
    if len(symbols) < 10:
        raise ValueError("TOO_FEW_SYMBOLS")
    bars: Dict[str, List[List[float]]] = {}
    funding: Dict[str, List[List[float]]] = {}
    for s in symbols:
        sleep(PAUSE_S)
        rows = get("/fapi/v1/klines", {"symbol": s, "interval": "4h", "limit": BARS})
        bars[s] = [[int(r[0])] + [float(v) for v in r[1:6]] for r in rows if int(r[0]) + BAR_MS <= close]      # closed bars only
        sleep(PAUSE_S)
        funding[s] = [[int(r["fundingTime"]), float(r["fundingRate"])] for r in get("/fapi/v1/fundingRate", {"symbol": s, "limit": FUNDING_ROWS})]
    return {"close_ms": close, "fetched_ms": now_ms, "symbols": symbols, "bars": bars, "funding": funding}


def _http_get(path: str, params: Dict[str, Any]) -> Any:
    import requests
    r = requests.get(HOST + path, params=params, headers=UA, timeout=20)
    r.raise_for_status()
    return r.json()


def _read(path: Path) -> Optional[Dict[str, Any]]:
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) and got.get("close_ms") and got.get("bars") else None


def load(base: Path, now_ms: Optional[int] = None, get: Optional[Callable[[str, Dict[str, Any]], Any]] = None, sleep: Callable[[float], None] = time.sleep) -> Dict[str, Any]:
    """The stored reply when it covers the newest close, otherwise one refresh.  A failed refresh falls back to the stored reply
    (the caller marks it old) and nothing is asked again for ``RETRY_AFTER_S``.  ``error`` names the failure type, never a URL."""
    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    path = Path(base) / CACHE
    with _LOCK:                                   # two screens opening at once make one refresh
        have = _read(path)
        if have and int(have["close_ms"]) >= latest_close(now_ms):
            return {**have, "arrays": _arrays(have)}
        failed = _FAILED.get(str(path))
        if not (failed and 0 <= now_ms - failed[0] < RETRY_AFTER_S * 1000):
            try:
                got = fetch(get or _http_get, now_ms, sleep)
            except Exception as exc:
                failed = _FAILED[str(path)] = (now_ms, type(exc).__name__)
            else:
                _FAILED.pop(str(path), None)
                _write(path, got)
                return {**got, "arrays": _arrays(got)}
        return {**have, "arrays": _arrays(have), "error": failed[1]} if have else {"error": failed[1]}


def _write(path: Path, doc: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({k: v for k, v in doc.items() if k != "arrays"}), encoding="utf-8")
    tmp.replace(path)


def _arrays(doc: Dict[str, Any]) -> Dict[str, Dict[str, np.ndarray]]:
    return {"bars": {s: np.array(v, dtype=float).reshape(-1, 6) for s, v in doc["bars"].items()},
            "funding": {s: np.array(v, dtype=float).reshape(-1, 2) for s, v in (doc.get("funding") or {}).items()}}
