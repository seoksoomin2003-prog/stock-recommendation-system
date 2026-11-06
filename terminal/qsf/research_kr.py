"""Pre-registered Korean price signal test.  Rules: reports/QSF_KR_RESEARCH_PROTOCOL.md.

Prices come from whole-market KRX snapshots, so the universe on a day is what traded that day, delisted names included.  A stock that
disappears after entry is closed at its last traded price, which keeps a delisting's fall in the returns.  The evaluation runs once and
a second run is refused.  Nothing here changes the live score, the QSF ledger or P6-11B.
"""
import gzip
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from terminal.qsf import config, krx_history as kh, research_ensemble as en, research_swing as rs, validate
from terminal.qsf.research_score import test_verdict

PROTOCOL = "reports/QSF_KR_RESEARCH_PROTOCOL.md"
REPORT = Path("reports") / "qsf" / "QSF_KR.json"
DATA = Path("research_data") / "krx"
PRICES = DATA / "prices.npz"
FEATURES = DATA / "features.npz"
START, TEST_START = "2011-01-01", "2022-01-01"
HORIZONS = {"SWING_20": 20, "LONG_252": 252}
THEMES: Dict[str, Sequence[str]] = {
    "momentum": ("mom_12_1", "mom_6_1", "resid_mom_12_1", "high_52w"),
    "reversal": ("rev_1m", "rev_resid_1m"),
    "low_risk": ("vol_252", "ivol_21", "max_21"),
}
SIGNALS = tuple(s for v in THEMES.values() for s in v)
MIN_VALUE = config.GATES["KR"]["min_adv_value"]
HISTORY, MIN_BARS, STEP = 320, 200, 5
CODE = re.compile(r"^\d{5}0$")
F = {name: n for n, name in enumerate(kh.FIELDS)}
MARKET = "MKT"
JUMP = 30.0        # percent, the widest daily price limit
ABSURD = 1000.0    # percent in a day


def num(x: Any) -> Optional[float]:
    """KRX writes numbers as text with commas and '-' for nothing."""
    try:
        v = float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def common_stock(code: Optional[str], name: Optional[str], section: Optional[str]) -> bool:
    return bool(code and CODE.match(code)) and "스팩" not in (name or "") and "SPAC" not in (section or "")


def watch_listed(section: Optional[str]) -> bool:
    return "관리종목" in (section or "") or "투자주의환기" in (section or "")


def next_level(level: Optional[float], close: float, chg: Optional[float], cap: Optional[float], shares: Optional[float], seen: Optional[Any], i: int) -> float:
    """The change KRX reports.  One exception: back from a halt with a jump above the widest daily limit and at least a fifth fewer
    shares, the change compares with a price from before a consolidation, so the change in market value is used.  More shares do not
    trigger it: a debt swap during a halt multiplies market value without any gain for a holder."""
    if level is None:
        return close
    if chg is not None and chg > ABSURD:       # a placeholder quote of 1 won during a halt, not a price anyone traded
        return level
    if seen is not None and chg is not None and chg > JUMP:
        last, traded, cap_before, shares_before = seen
        if (last != i - 1 or not traded) and cap_before and cap and shares_before and shares and shares <= 0.8 * shares_before:
            return level * cap / cap_before
    return level * (1 + chg / 100) if chg is not None else level


def build_prices(root: Path, log=print) -> Dict[str, Any]:
    """Arrays by day and stock.  Each adjusted price is built only from changes up to that day."""
    days = sorted({p.name[:10] for b in kh.BOARDS for p in (root / b).glob("*.json.gz")})
    snap: List[Dict[str, List[Any]]] = []
    kept, boards = [], {}
    for day in days:
        rows: Dict[str, List[Any]] = {}
        for board in kh.BOARDS:
            p = kh.path_of(root, board, day)
            if not p.exists():
                continue
            with gzip.open(p, "rt", encoding="utf-8") as fh:
                for r in json.load(fh):
                    if common_stock(r[F["ISU_CD"]], r[F["ISU_NM"]], r[F["SECT_TP_NM"]]):
                        rows[r[F["ISU_CD"]]] = r
                        boards[r[F["ISU_CD"]]] = board
        if rows:
            kept.append(day)
            snap.append(rows)
    symbols = sorted({c for s in snap for c in s}) + [MARKET]
    col = {c: j for j, c in enumerate(symbols)}
    D, S = len(kept), len(symbols)
    log(f"days {D} stocks {S}")
    out = {x: np.full((D, S), np.nan, dtype=np.float32) for x in ("open", "high", "low", "close", "adj_close", "volume", "value", "cap")}
    watch = np.zeros((D, S), dtype=bool)
    level: Dict[str, float] = {}
    seen: Dict[str, Any] = {}      # code -> (last day index, traded that day, market cap, listed shares)
    for i, rows in enumerate(snap):
        for c, r in rows.items():
            j = col[c]
            close = num(r[F["TDD_CLSPRC"]])
            if not close:
                continue
            cap = num(r[F["MKTCAP"]])
            shares = num(r[F["LIST_SHRS"]])
            level[c] = next_level(level.get(c), close, num(r[F["FLUC_RT"]]), cap, shares, seen.get(c), i)
            seen[c] = (i, bool(num(r[F["ACC_TRDVOL"]])), cap, shares)
            k = level[c] / close
            out["close"][i, j], out["adj_close"][i, j] = level[c], level[c]
            for field, name in (("open", "TDD_OPNPRC"), ("high", "TDD_HGPRC"), ("low", "TDD_LWPRC")):
                v = num(r[F[name]])
                if v:
                    out[field][i, j] = v * k
            for field, name in (("volume", "ACC_TRDVOL"), ("value", "ACC_TRDVAL"), ("cap", "MKTCAP")):
                v = num(r[F[name]])
                if v is not None:
                    out[field][i, j] = v
            watch[i, j] = watch_listed(r[F["SECT_TP_NM"]])
    add_market(out, col[MARKET])
    return {"dates": np.array(kept), "symbols": np.array(symbols), "kospi": np.array([boards.get(c) == "KOSPI" for c in symbols]), "watch": watch, **out}


def add_market(d: Dict[str, np.ndarray], m: int) -> None:
    """A capitalisation-weighted index on the previous day's weights.  Its open is the previous close, since only its return matters."""
    a, cap = d["adj_close"].astype(float), d["cap"].astype(float)
    level = 1000.0
    d["adj_close"][0, m] = d["close"][0, m] = d["high"][0, m] = d["low"][0, m] = d["open"][0, m] = level
    d["volume"][0, m] = 1
    for i in range(1, a.shape[0]):
        prev, now, w = a[i - 1], a[i], cap[i - 1]
        ok = np.isfinite(prev) & np.isfinite(now) & np.isfinite(w) & (w > 0) & (prev > 0)
        ok[m] = False
        before = level
        if ok.any():
            level *= 1 + float(np.sum(w[ok] * (now[ok] / prev[ok] - 1)) / np.sum(w[ok]))
        d["open"][i, m], d["adj_close"][i, m], d["close"][i, m] = before, level, level
        d["high"][i, m], d["low"][i, m], d["volume"][i, m] = max(before, level), min(before, level), 1


class KrPrices:
    """Same shape as validate.Prices, but a stock gone before the exit day closes at its last traded price."""

    def __init__(self, z: Dict[str, np.ndarray]):
        self.dates = [str(d) for d in z["dates"]]
        self.symbols = [str(s) for s in z["symbols"]]
        self.col = {s: j for j, s in enumerate(self.symbols)}
        self.col["SPY"] = self.col[MARKET]     # the shared evaluation reads its benchmark under this name
        self.data = z
        self.kospi = z["kospi"]

    def forward(self, i: int, h: int, cost: float = 0.0) -> np.ndarray:
        n = len(self.symbols)
        if i + h >= len(self.dates):
            return np.full(n, np.nan)
        win = self.data["adj_close"][i + 1:i + h + 1].astype(float)
        have = np.isfinite(win)
        last = win.shape[0] - 1 - np.argmax(have[::-1], axis=0)
        exit_ = win[last, np.arange(n)]
        exit_[~have.any(axis=0)] = np.nan
        with np.errstate(invalid="ignore", divide="ignore"):
            return exit_ / self.data["open"][i + 1].astype(float) - 1 - cost


def eligible(d: Dict[str, np.ndarray], i: int) -> np.ndarray:
    lo = max(0, i - HISTORY + 1)
    bars = np.isfinite(d["close"][lo:i + 1]).sum(axis=0)
    v20 = d["value"][max(0, i - 19):i + 1].astype(float)
    have = np.isfinite(v20).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.nansum(v20, axis=0) / np.where(have > 0, have, np.nan)
    ok = np.isfinite(d["close"][i]) & (bars >= MIN_BARS) & (mean >= MIN_VALUE) & (d["volume"][i] > 0) & ~d["watch"][i]
    ok[d["symbols"] == MARKET] = False
    return ok


def build_features(px: KrPrices, log=print) -> Dict[str, Any]:
    first = next(n for n, day in enumerate(px.dates) if day >= START)
    rows = list(range(first, len(px.dates), STEP))
    tensor = np.full((len(rows), len(px.symbols), len(SIGNALS)), np.nan, dtype=np.float32)
    top300 = np.zeros((len(rows), len(px.symbols)), dtype=bool)
    m = px.col[MARKET]
    t0 = time.time()
    for n, i in enumerate(rows):
        ok = eligible(px.data, i)
        f = rs.price_features(px.data, i, m)
        for k, s in enumerate(SIGNALS):
            tensor[n, ok, k] = f[s][ok]
        v = px.data["value"][max(0, i - 19):i + 1].astype(float)
        with np.errstate(invalid="ignore"):
            mean = np.where(ok, np.nanmean(np.where(np.isfinite(v), v, np.nan), axis=0), -1.0)
        top300[n, np.argsort(-mean)[:300]] = True
        top300[n, ~ok] = False
        if n % 200 == 0:
            log(f"{n}/{len(rows)} {px.dates[i]} {time.time() - t0:.0f}s")
    return {"rows": np.array(rows), "tensor": tensor, "top300": top300}


def theme_ranks(tensor: np.ndarray) -> Dict[str, np.ndarray]:
    r = rs.rank_tensor(tensor, SIGNALS, {s: rs.GOOD_HIGH[s] for s in SIGNALS})
    return en.theme_scores({s: r[:, :, k] for k, s in enumerate(SIGNALS)}, THEMES)


def windows(px: KrPrices, rows: Sequence[int], h: int) -> Dict[str, List[int]]:
    early = [n for n, i in enumerate(rows) if px.dates[i] >= START and i + h < len(px.dates) and px.dates[i + h] < TEST_START]
    test = [n for n, i in enumerate(rows) if px.dates[i] >= TEST_START and i + h < len(px.dates)]
    return {"early": early, "test": test}


def _load(base: Path) -> KrPrices:
    with np.load(base / PRICES, allow_pickle=False) as z:
        return KrPrices({k: z[k] for k in z.files})


def download(base: Path, log=print) -> Dict[str, Any]:
    import requests
    key = os.environ.get("KRX_API_KEY")
    if not key:
        return {"status": "NO_KEY"}
    return kh.download(base / DATA, key, requests.get, "2010-01-04", "2026-11-05", log=log)


def prepare(base: Path, log=print) -> Dict[str, Any]:
    """Prices, signals and how alike the themes are.  No forward return is computed."""
    z = build_prices(base / DATA, log)
    np.savez_compressed(base / PRICES, **z)
    px = KrPrices(z)
    f = build_features(px, log)
    np.savez_compressed(base / FEATURES, **f)
    scores = theme_ranks(f["tensor"])
    rows = [int(i) for i in f["rows"]]
    picks = [n for n, i in enumerate(rows) if px.dates[i] < TEST_START]
    corr = en.theme_correlation(scores, picks)
    return {"status": "PREPARED", "days": len(px.dates), "first": px.dates[0], "last": px.dates[-1], "stocks": len(px.symbols) - 1, "correlation": corr, "groups": en.merge_groups(corr),
            "mean_stocks": float(np.mean(np.isfinite(f["tensor"][:, :, 0]).sum(axis=1)))}


def run_once(base: Path, log=print) -> Dict[str, Any]:
    target = base / REPORT
    if target.exists():
        raise RuntimeError("이미 시험을 실행했습니다. 프로토콜상 다시 실행할 수 없습니다.")
    px = _load(base)
    with np.load(base / FEATURES) as z:
        rows, tensor, top300 = [int(i) for i in z["rows"]], z["tensor"], z["top300"]
    scores = theme_ranks(tensor)
    corr = en.theme_correlation(scores, [n for n, i in enumerate(rows) if px.dates[i] < TEST_START])
    groups = en.merge_groups(corr)
    score = en.combine(scores, groups)
    cost = config.round_trip_cost("KR")
    out: Dict[str, Any] = {"status": "TESTED", "protocol": PROTOCOL, "groups": groups, "correlation": corr, "cost": cost, "strategies": {}}
    masks = {"kospi": np.tile(px.kospi, (len(rows), 1)), "kosdaq": np.tile(~px.kospi, (len(rows), 1)), "top300": top300}
    for s, h in HORIZONS.items():
        w = windows(px, rows, h)
        test = en.evaluate(score, px, rows, w["test"], h, {}, cost)
        early = en.evaluate(score, px, rows, w["early"], h, {}, cost)
        themes = {}
        for t, m in scores.items():
            ics = {k: [v for v in (rs._ic(m[n].astype(float), px.forward(rows[n], h)) for n in w[k]) if v is not None] for k in w}
            themes[t] = {k: {"ic": float(np.mean(v)) if v else None, "t": validate.newey_west_t(v, rs.lag_of(h)), "dates": len(v)} for k, v in ics.items()}
        subsets = {}
        for name, mask in masks.items():
            sub = np.where(mask, score, np.nan)
            subsets[name] = {k: {x: en.evaluate(sub, px, rows, w[k], h, {}, cost).get(x) for x in ("ic", "t", "top_excess", "spread_net", "mean_stocks", "dates")} for k in w}
        out["strategies"][s] = {"horizon": h, **test, **test_verdict(test), "earlier_2011_2021": early, "themes": themes, "subsets": subsets}
        log(f"{s} done")
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
