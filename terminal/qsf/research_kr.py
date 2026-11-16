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
    if seen is not None and chg is not None and chg > JUMP:
        last, traded, cap_before, shares_before = seen
        if (last != i - 1 or not traded) and cap_before and cap and shares_before and shares and shares <= 0.8 * shares_before:
            return level * cap / cap_before
    if chg is not None and chg > ABSURD:       # a placeholder quote of 1 won during a halt, not a price anyone traded
        return level
    return level * (1 + chg / 100) if chg is not None else level


_LAST_BUILD: Dict[str, Any] = {}        # the newest result for a given list of days, and what the day files looked like then


def build_prices(root: Path, log=print, days: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Arrays by day and stock.  Each adjusted price is built only from changes up to that day.  ``days`` limits which days are read.

    One result is kept per process and handed out again, as copies, while the same days are asked for and none of their files has
    changed (size and write time).  The morning's Korean record step built the same arrays several times over, each build reading
    every day file and holding about 800 MB while it ran.  Without ``days`` nothing is kept."""
    if days is None:
        return _build_prices(root, log, None)
    wanted = sorted(days)
    files = []
    for day in wanted:
        for board in kh.BOARDS:
            try:
                st = kh.path_of(root, board, day).stat()
                files.append((st.st_mtime_ns, st.st_size))
            except OSError:
                files.append(None)
    key = (str(Path(root).resolve()), tuple(wanted), tuple(files))
    if _LAST_BUILD.get("key") != key:
        _LAST_BUILD.clear()                               # the old arrays go before the new ones are built
        built = _build_prices(root, log, wanted)
        _LAST_BUILD.update(key=key, value=built)
    else:
        built = _LAST_BUILD["value"]
        log(f"days {len(built['dates'])} stocks {len(built['symbols'])}")
    return {k: v.copy() for k, v in built.items()}


def _build_prices(root: Path, log=print, days: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    days = sorted(days) if days is not None else sorted({p.name[:10] for b in kh.BOARDS for p in (root / b).glob("*.json.gz")})
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


# ---------------------------------------------------------------------- checks after the verdict; they change no verdict
def rebalance_path(picks: Sequence[np.ndarray], returns: np.ndarray, cost: float) -> List[float]:
    """Equal weight in each period, paying the round trip only on the share of holdings replaced."""
    out, held = [], None
    for k, p in enumerate(picks):
        ok = p & np.isfinite(returns[k])
        if not ok.any():
            out.append(float("nan"))
            continue
        turn = 1.0 if held is None else 1 - float((ok & held).sum()) / float(ok.sum())
        out.append(float(returns[k][ok].mean()) - cost * turn)
        held = ok
    return out


def annual_growth(path: Sequence[float], h: int, sessions: int = 248) -> Optional[float]:
    x = [v for v in path if np.isfinite(v)]
    if not x:
        return None
    return float(np.exp(np.sum(np.log1p(x)) * sessions / (h * len(x))) - 1)


def _quintiles(score: np.ndarray, px: KrPrices, rows: List[int], picks: List[int], h: int) -> Dict[str, Any]:
    mean, median, excess = [[] for _ in range(5)], [[] for _ in range(5)], [[] for _ in range(5)]
    for n in picks:
        r, s = px.forward(rows[n], h), score[n].astype(float)
        ok = np.isfinite(r) & np.isfinite(s)
        if ok.sum() < 30:
            continue
        q = np.minimum((validate.rank(s[ok]) / ok.sum() * 5).astype(int), 4)
        avg = r[ok].mean()
        for b in range(5):
            x = r[ok][q == b]
            mean[b].append(x.mean()); median[b].append(np.median(x)); excess[b].append(x.mean() - avg)     # noqa: E702
    return {f"Q{b + 1}": {"mean": float(np.mean(mean[b])), "median": float(np.mean(median[b])), "excess": float(np.mean(excess[b]))} for b in range(5)}


def _ic_mean(score: np.ndarray, px: KrPrices, rows: List[int], picks: List[int], h: int, mask: Optional[np.ndarray] = None) -> Optional[float]:
    v = []
    for n in picks:
        s = score[n].astype(float)
        if mask is not None:
            s = np.where(mask[n], s, np.nan)
        x = rs._ic(s, px.forward(rows[n], h))
        if x is not None:
            v.append(x)
    return float(np.mean(v)) if v else None


def _portfolios(score: np.ndarray, top300: np.ndarray, px: KrPrices, rows: List[int], first: str, last: str, cost: float, h: int = 20) -> Dict[str, Any]:
    every = h // STEP
    ns = [n for n, i in enumerate(rows) if first <= px.dates[i] < last and i + h < len(px.dates)][::every]
    m = px.col[MARKET]
    r = np.stack([px.forward(rows[n], h) for n in ns])
    def top(mask_row: np.ndarray, s: np.ndarray, count: Optional[int] = None) -> np.ndarray:
        ok = mask_row & np.isfinite(s)
        out = np.zeros(s.shape, dtype=bool)
        if ok.sum() < 30:
            return out
        k = count or max(1, int(ok.sum() * 0.2))
        idx = np.flatnonzero(ok)
        out[idx[np.argsort(-s[idx])[:k]]] = True
        return out
    has = [np.isfinite(score[n].astype(float)) for n in ns]
    t300 = [top300[n] for n in ns]
    sets = {"top_fifth_all": [top(has[k], score[n].astype(float)) for k, n in enumerate(ns)],
            "top_fifth_of_300": [top(t300[k], score[n].astype(float)) for k, n in enumerate(ns)],
            "top_30_of_300": [top(t300[k], score[n].astype(float), 30) for k, n in enumerate(ns)],
            "all_equal": has, "top300_equal": t300}
    out = {"periods": len(ns), "first": px.dates[rows[ns[0]]], "last": px.dates[rows[ns[-1]]]}
    for name, p in sets.items():
        path = rebalance_path(p, r, cost)
        out[name] = {"annual_net": annual_growth(path, h), "mean_holdings": float(np.mean([x.sum() for x in p])), "turnover": float(np.mean([1 - (p[k] & p[k - 1]).sum() / max(1, p[k].sum()) for k in range(1, len(p))]))}
    out["cap_weighted_market"] = {"annual": annual_growth([float(v) for v in r[:, m]], h)}
    return out


def diagnose(base: Path, log=print) -> Dict[str, Any]:
    """How large the result is in money, whether the arithmetic holds, and what else could explain it.  Rebuilds prices with the
    corrected order of the two price rules, and reports the verdict on them beside the one-run verdict."""
    prepare(base, log)
    px = _load(base)
    with np.load(base / FEATURES) as z:
        rows, tensor, top300 = [int(i) for i in z["rows"]], z["tensor"], z["top300"]
    scores = theme_ranks(tensor)
    score = en.combine(scores, en.merge_groups(en.theme_correlation(scores, [n for n, i in enumerate(rows) if px.dates[i] < TEST_START])))
    cost = config.round_trip_cost("KR")
    rng = np.random.default_rng(7)
    cap = np.stack([px.data["cap"][i].astype(float) for i in rows])
    out: Dict[str, Any] = {"status": "CHECKED", "note": "결과를 본 뒤의 점검이다. 판정을 바꾸지 않는다.", "strategies": {}}
    for s, h in HORIZONS.items():
        w = windows(px, rows, h)
        res: Dict[str, Any] = {}
        for k, picks in w.items():
            test = en.evaluate(score, px, rows, picks, h, {}, cost)
            sizes = np.full(cap.shape, -1)
            for n in picks:
                ok = np.isfinite(score[n]) & np.isfinite(cap[n])
                if ok.sum() >= 30:
                    sizes[n, ok] = np.minimum((validate.rank(cap[n][ok]) / ok.sum() * 5).astype(int), 4)
            shuffled = score.copy()
            for n in picks:
                ok = np.flatnonzero(np.isfinite(score[n]))
                shuffled[n, ok] = rng.permutation(score[n, ok])
            res[k] = {"corrected_rules": {x: test.get(x) for x in ("ic", "t", "spread_net", "top_excess", "dates")} | {x: {y: test[x].get(y) for y in ("ic", "spread_net")} for x in ("early", "late")} | test_verdict(test),
                      "shuffled_ic": _ic_mean(shuffled, px, rows, picks, h),
                      "score_quintiles": _quintiles(score, px, rows, picks, h),
                      "theme_quintiles": {t: _quintiles(m, px, rows, picks, h) for t, m in scores.items()},
                      "size_quintiles": _quintiles(np.where(sizes >= 0, cap, np.nan), px, rows, picks, h),
                      "ic_inside_size_quintile": {f"cap_Q{b + 1}": _ic_mean(score, px, rows, picks, h, sizes == b) for b in range(5)}}
        res["portfolios_20d"] = None
        out["strategies"][s] = res
    out["portfolios_20d"] = {"2011_2021": _portfolios(score, top300, px, rows, START, TEST_START, cost), "2022_on": _portfolios(score, top300, px, rows, TEST_START, "2099", cost),
                             "2022_2023": _portfolios(score, top300, px, rows, TEST_START, "2024-01-01", cost), "2024_on": _portfolios(score, top300, px, rows, "2024-01-01", "2099", cost)}
    out["raw_quote_check"] = raw_check(base, px, rows)
    (base / "reports" / "qsf" / "QSF_KR_DIAGNOSTICS.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def raw_check(base: Path, px: KrPrices, rows: List[int], h: int = 20) -> Dict[str, Any]:
    """Returns rebuilt from the plain quotes, for stocks whose share count did not change, against the adjusted series."""
    root = base / DATA

    def read(day: str) -> Dict[str, List[Any]]:
        out: Dict[str, List[Any]] = {}
        for b in kh.BOARDS:
            p = kh.path_of(root, b, day)
            if p.exists():
                with gzip.open(p, "rt", encoding="utf-8") as fh:
                    out.update({r[F["ISU_CD"]]: r for r in json.load(fh)})
        return out
    diffs: List[float] = []
    for i in rows[::40]:
        if i + h >= len(px.dates):
            continue
        a, b = read(px.dates[i + 1]), read(px.dates[i + h])
        r = px.forward(i, h)
        for c, x in a.items():
            j = px.col.get(c)
            y = b.get(c)
            if j is None or y is None or not np.isfinite(r[j]) or x[F["LIST_SHRS"]] != y[F["LIST_SHRS"]]:
                continue
            o, e = num(x[F["TDD_OPNPRC"]]), num(y[F["TDD_CLSPRC"]])
            if o and e:
                diffs.append(abs(e / o - 1 - float(r[j])))
    d = np.array(diffs)
    return {"pairs": int(d.size), "median_abs_diff": float(np.median(d)), "p99_abs_diff": float(np.percentile(d, 99)), "share_above_1pct": float((d > 0.01).mean())}
