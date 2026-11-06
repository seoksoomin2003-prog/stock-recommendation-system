"""Pre-registered sentiment and risk test.  Rules: reports/QSF_SENTIMENT_PROTOCOL.md.

A market-wide reading changes no ranking on its own, so it decides the direction of the low risk theme: low risk on calm days, the
opposite on fearful days.  The evaluation runs once and a second run is refused.  Nothing here changes the live score, the QSF ledger
or P6-11B.
"""
import bisect
import csv
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from terminal.qsf import research_ensemble as en, research_swing as rs, validate
from terminal.qsf.research_score import test_verdict
from terminal.sources import GENERIC_UA

PROTOCOL = "reports/QSF_SENTIMENT_PROTOCOL.md"
REPORT = Path("reports") / "qsf" / "QSF_SENTIMENT.json"
VIX_FILE = Path("research_data") / "sentiment" / "VIX_History.csv"
VIX_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
LOOKBACK = 252
THEME = en.THEMES["low_risk"]


def parse_vix(text: str) -> Dict[str, float]:
    """CBOE writes MM/DD/YYYY.  A row that cannot be read is left out, not guessed."""
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        try:
            m, d, y = row["DATE"].split("/")
            v = float(row["CLOSE"])
        except (KeyError, ValueError, AttributeError):
            continue
        if np.isfinite(v) and v > 0:
            out[f"{y}-{int(m):02d}-{int(d):02d}"] = v
    return out


def high_sentiment(vix: Dict[str, float], days: Sequence[str]) -> List[Optional[bool]]:
    """True when VIX closes below the median of the previous 252 closes.  The day itself is not in the median.  None without history."""
    keys = sorted(vix)
    out: List[Optional[bool]] = []
    for day in days:
        n = bisect.bisect_left(keys, day)
        if n >= len(keys) or keys[n] != day or n < LOOKBACK:
            out.append(None)
            continue
        out.append(bool(vix[day] < np.median([vix[k] for k in keys[n - LOOKBACK:n]])))
    return out


def conditional_score(low_risk: np.ndarray, high: Sequence[Optional[bool]]) -> np.ndarray:
    """Low risk on calm days, its opposite on fearful days, empty when the state is unknown."""
    out = np.full(low_risk.shape, np.nan, dtype=float)
    for n, h in enumerate(high):
        if h is not None:
            out[n] = low_risk[n] if h else 1 - low_risk[n]
    return out


def split_ic(low_risk: np.ndarray, high: Sequence[Optional[bool]], px: validate.Prices, rows: List[int], picks: List[int], h: int) -> Dict[str, Any]:
    groups: Dict[bool, List[float]] = {True: [], False: []}
    for n in picks:
        if high[n] is None:
            continue
        v = rs._ic(low_risk[n].astype(float), px.forward(rows[n], h))
        if v is not None:
            groups[high[n]].append(v)
    return {name: {"ic": float(np.mean(groups[k])) if groups[k] else None, "dates": len(groups[k])} for name, k in (("high_sentiment", True), ("low_sentiment", False))}


def run_once(base: Path, log=print) -> Dict[str, Any]:
    target = base / REPORT
    if target.exists():
        raise RuntimeError("이미 시험을 실행했습니다. 프로토콜상 다시 실행할 수 없습니다.")
    root, px, rows, swing, insider = en._inputs(base)
    sectors = rs._sectors(base, root)
    fund = np.load(root / en.FUND_FILE)["tensor"]
    low_risk = en.theme_scores(en.signal_ranks(fund, swing, insider, px.symbols, sectors))["low_risk"]
    high = high_sentiment(parse_vix((base / VIX_FILE).read_text(encoding="utf-8")), [px.dates[i] for i in rows])
    score = conditional_score(low_risk, high) * 100
    out: Dict[str, Any] = {"status": "TESTED", "protocol": PROTOCOL, "strategies": {}}
    for s, h in en.HORIZONS.items():
        w = en.windows(px, rows, h)
        test = en.evaluate(score, px, rows, w["test"], h, sectors)
        early = en.evaluate(score, px, rows, w["early"], h, sectors)
        out["strategies"][s] = {"horizon": h, **test, **test_verdict(test), "earlier_2014_2021": early, "low_risk_by_state": {k: split_ic(low_risk, high, px, rows, w[k], h) for k in w}}
        log(f"{s} done")
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def fetch_vix(base: Path, get=None) -> Dict[str, Any]:
    if get is None:
        import requests
        get = requests.get
    r = get(VIX_URL, headers={"User-Agent": GENERIC_UA}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"VIX_HTTP_{r.status_code}")
    p = base / VIX_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    text = r.content.decode("utf-8")
    p.write_text(text, encoding="utf-8")
    v = parse_vix(text)
    return {"status": "DOWNLOADED", "first": min(v), "last": max(v), "rows": len(v)}
