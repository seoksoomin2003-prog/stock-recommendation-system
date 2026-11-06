"""Pre-registered short selling research.  Rules: reports/QSF_SHORT_RESEARCH_PROTOCOL.md.

Short interest counts only from 16 calendar days after its settlement date, the conservative end of FINRA's publication calendar.
Development sees only returns that end before TEST_START; the test runs once and a second run is refused.  Nothing here changes the
live score, the QSF ledger or P6-11B.
"""
import bisect
import gzip
import json
import time
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from terminal.qsf import pit, research_ensemble as en, research_swing as rs, validate, validate_corrected as vc
from terminal.qsf.research_score import dev_rows, test_rows, test_verdict
from terminal.sources import GENERIC_UA

PROTOCOL = "reports/QSF_SHORT_RESEARCH_PROTOCOL.md"
DEV_REPORT = Path("reports") / "qsf" / "QSF_SHORT_DEV.json"
TEST_REPORT = Path("reports") / "qsf" / "QSF_SHORT_TEST.json"
FEATURES = Path("research_data") / "short" / "short_features.npz"
SI_URL = "https://cdn.finra.org/equity/otcmarket/biweekly/shrt{}.csv"
SV_URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{}.txt"
SI_FIRST, SV_FIRST, DEV_START = "2017-12-01", "2018-08-01", "2018-01-01"
PUBLISH_LAG_DAYS, MAX_AGE_DAYS, CHANGE_BACK = 16, 45, 6
FACTORS = ("si_dtc", "si_ratio", "si_chg_3m", "sv_ratio_20", "sv_abn_5")
GOOD_HIGH = {f: False for f in FACTORS}
HORIZONS = {"SWING_10": 10, "SWING_20": 20}


def norm(symbol: str) -> str:
    return symbol.upper().replace("-", "").replace(".", "").replace("/", "")


def usable_from(settlement: str) -> str:
    return (date.fromisoformat(settlement) + timedelta(days=PUBLISH_LAG_DAYS)).isoformat()


def latest_usable(settlements: Sequence[str], day: str) -> Optional[int]:
    """Index of the newest settlement already published on `day`, unless it has grown too old."""
    n = bisect.bisect_right([usable_from(s) for s in settlements], day) - 1
    if n < 0 or (date.fromisoformat(day) - date.fromisoformat(settlements[n])).days > MAX_AGE_DAYS:
        return None
    return n


def _num(x: str) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def parse_si(text: str, wanted: Dict[str, str]) -> Dict[str, List[Optional[float]]]:
    lines = text.replace('"', "").splitlines()
    if not lines:
        return {}
    col = {k: n for n, k in enumerate(lines[0].split("|"))}
    out = {}
    for line in lines[1:]:
        p = line.split("|")
        if len(p) < len(col) or p[col["symbolCode"]] not in wanted:
            continue
        out[wanted[p[col["symbolCode"]]]] = [_num(p[col["currentShortPositionQuantity"]]), _num(p[col["averageDailyVolumeQuantity"]])]
    return out


def parse_sv(text: str, wanted: Dict[str, str]) -> Dict[str, List[Optional[float]]]:
    lines = text.splitlines()
    if not lines:
        return {}
    col = {k: n for n, k in enumerate(lines[0].split("|"))}
    out = {}
    for line in lines[1:]:
        p = line.split("|")
        if len(p) < len(col) or p[col["Symbol"]] not in wanted:
            continue
        out[wanted[p[col["Symbol"]]]] = [_num(p[col["ShortVolume"]]), _num(p[col["TotalVolume"]])]
    return out


def settlement_candidates(first: str, last: str) -> List[List[str]]:
    """The 15th and the month's end, each with the earlier weekdays that replace it on a holiday."""
    out = []
    y, m = int(first[:4]), int(first[5:7])
    while f"{y}-{m:02d}" <= last[:7]:
        for d in (15, monthrange(y, m)[1]):
            c, tries = date(y, m, d), []
            while len(tries) < 4:
                if c.weekday() < 5:
                    tries.append(c.isoformat())
                c -= timedelta(days=1)
            if first <= tries[0] <= last:
                out.append(tries)
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


class Refused(RuntimeError):
    pass


def _fetch(get, url: str) -> Optional[str]:
    r = get(url, headers={"User-Agent": GENERIC_UA}, timeout=60)
    if r.status_code == 200:
        return r.content.decode("utf-8", "replace")
    if r.status_code in (429, 503):
        raise Refused(str(r.status_code))
    return None      # the CDN answers 403 for a date without a file, so a missing day is expected


def _save(path: Path, rows: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(rows, fh)
    tmp.replace(path)


def download(root: Path, symbols: Sequence[str], days: Sequence[str], get, sleep=time.sleep, log=print) -> Dict[str, Any]:
    """Keeps only the sample's rows.  A file already kept is not asked again."""
    wanted = {norm(s): s for s in symbols}
    last = max(days)
    si = sv = misses = 0
    for tries in settlement_candidates(SI_FIRST, last):
        if any((root / f"si_{d}.json.gz").exists() for d in tries):
            continue
        for d in tries:
            text = _fetch(get, SI_URL.format(d.replace("-", "")))
            sleep(0.3)
            if text:
                _save(root / f"si_{d}.json.gz", parse_si(text, wanted))
                si += 1
                break
    for d in days:
        if d < SV_FIRST or (root / f"sv_{d}.json.gz").exists():
            continue
        text = _fetch(get, SV_URL.format(d.replace("-", "")))
        sleep(0.3)
        if not text:
            misses += 1
            log(f"sv missing {d}")
            if misses >= 25:
                raise Refused("TOO_MANY_MISSING")
            continue
        misses = 0
        _save(root / f"sv_{d}.json.gz", parse_sv(text, wanted))
        sv += 1
        if sv % 200 == 0:
            log(f"sv {d} {sv}")
    return {"status": "DOWNLOADED", "short_interest_files": si, "short_volume_files": sv}


def _read(path: Path) -> Dict[str, List[Optional[float]]]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def si_series(root: Path, symbols: Sequence[str], shares_at: Callable[[str, str], Optional[float]]) -> Tuple[List[str], np.ndarray, np.ndarray]:
    """Days to cover and short share per settlement.  Shares are read as of each settlement, so a later split cannot leak."""
    files = sorted(root.glob("si_*.json.gz"))
    days = [f.name[3:13] for f in files]
    dtc, ratio = (np.full((len(days), len(symbols)), np.nan, dtype=np.float32) for _ in range(2))
    col = {s: j for j, s in enumerate(symbols)}
    for n, f in enumerate(files):
        for s, (cur, adv) in _read(f).items():
            j = col.get(s)
            if j is None or cur is None:
                continue
            if adv:
                dtc[n, j] = cur / adv
            sh = shares_at(s, days[n])
            if sh:
                ratio[n, j] = cur / sh
    return days, dtc, ratio


def sv_matrix(root: Path, dates: Sequence[str], symbols: Sequence[str]) -> np.ndarray:
    """Short share of volume by trading day; a day with no volume stays empty."""
    col = {s: j for j, s in enumerate(symbols)}
    out = np.full((len(dates), len(symbols)), np.nan, dtype=np.float32)
    for i, d in enumerate(dates):
        f = root / f"sv_{d}.json.gz"
        if not f.exists():
            continue
        for s, (short, total) in _read(f).items():
            j = col.get(s)
            if j is not None and short is not None and total:
                out[i, j] = short / total
    return out


def _window_mean(m: np.ndarray, i: int, n: int, need: int) -> np.ndarray:
    x = m[max(0, i - n + 1):i + 1]
    have = np.isfinite(x).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        v = np.nansum(x, axis=0) / np.where(have > 0, have, np.nan)
    v[have < need] = np.nan
    return v


def features_at(day: str, i: int, keep: Sequence[int], settlements: Sequence[str], dtc: np.ndarray, ratio: np.ndarray, sv: np.ndarray) -> np.ndarray:
    out = np.full((sv.shape[1], len(FACTORS)), np.nan, dtype=np.float32)
    keep = list(keep)
    s = latest_usable(settlements, day)
    if s is not None:
        out[keep, 0] = dtc[s, keep]
        out[keep, 1] = ratio[s, keep]
        if s >= CHANGE_BACK:
            out[keep, 2] = ratio[s, keep] - ratio[s - CHANGE_BACK, keep]
    m20, m5, m60 = _window_mean(sv, i, 20, 15), _window_mean(sv, i, 5, 4), _window_mean(sv, i, 60, 45)
    out[keep, 3] = m20[keep]
    out[keep, 4] = (m5 - m60)[keep]
    return out


# ---------------------------------------------------------------------- runs
def fetch_all(base: Path, log=print) -> Dict[str, Any]:
    import requests
    _, _, px = rs._load(base)
    return download(base / "research_data" / "short", px.symbols, [d for d in px.dates if d >= SI_FIRST], requests.get, log=log)


def _shares_fn(facts: Dict[str, Dict], splits: Dict[str, List]) -> Callable[[str, str], Optional[float]]:
    objs: Dict[str, pit.Splits] = {}

    def at(t: str, day: str) -> Optional[float]:
        if t not in facts:
            return None
        o = objs.setdefault(t, pit.Splits(splits.get(t) or []))
        series = vc.ttm_view(facts[t]["full"], day, o).get("shares_avg") or []
        if not series:
            return None
        last = series[-1]
        v = last.get("val") if isinstance(last, dict) else last
        return float(v) if v else None
    return at


def develop(base: Path, log=print) -> Dict[str, Any]:
    root, _, px, rows, _, _ = _inputs(base)
    data = base / "research_data" / "short"
    t0 = time.time()
    settlements, dtc, ratio = si_series(data, px.symbols, _shares_fn(vc.load_facts(root), en._splits(root)))
    log(f"settlements {len(settlements)} {time.time() - t0:.0f}s")
    sv = sv_matrix(data, px.dates, px.symbols)
    members = rs._members(base, root)
    tensor = np.full((len(rows), len(px.symbols), len(FACTORS)), np.nan, dtype=np.float32)
    for n, i in enumerate(rows):
        day = px.dates[i]
        if day < DEV_START:
            continue
        tensor[n] = features_at(day, i, rs.eligible(px.data, i, sorted({px.col[t] for t in members(day) if t in px.col})), settlements, dtc, ratio, sv)
    np.savez_compressed(base / FEATURES, rows=np.array(rows), tensor=tensor)
    ranks = rs.rank_tensor(tensor, FACTORS, GOOD_HIGH)
    res = {}
    for s, h in HORIZONS.items():
        picks = [n for n in dev_rows(px, rows, h) if px.dates[rows[n]] >= DEV_START]
        res[s] = rs.select(ranks, px, rows, picks, h, FACTORS)
    picks = [n for n, i in enumerate(rows) if px.dates[i] >= DEV_START]
    out = {"status": "DEVELOPED", "protocol": PROTOCOL, "strategies": res, "settlements": [settlements[0], settlements[-1], len(settlements)],
           "mean_stocks_with_value": {f: float(np.mean(np.isfinite(tensor[picks, :, k]).sum(axis=1))) for k, f in enumerate(FACTORS)}}
    (base / DEV_REPORT).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def _inputs(base: Path):
    root, names, px = rs._load(base)
    z = np.load(root / "swing_features_corrected.npz")
    return root, names, px, [int(i) for i in z["rows"]], z["tensor"], None


def test_once(base: Path) -> Dict[str, Any]:
    target = base / TEST_REPORT
    if target.exists():
        raise RuntimeError("이미 시험을 실행했습니다. 프로토콜상 다시 실행할 수 없습니다.")
    root, _, px = rs._load(base)
    dev = json.loads((base / DEV_REPORT).read_text(encoding="utf-8"))
    z = np.load(base / FEATURES)
    rows = [int(i) for i in z["rows"]]
    ranks = rs.rank_tensor(z["tensor"], FACTORS, GOOD_HIGH)
    sectors = rs._sectors(base, root)
    out: Dict[str, Any] = {"status": "TESTED", "protocol": PROTOCOL, "strategies": {}}
    for s, h in HORIZONS.items():
        chosen = dev["strategies"][s]["chosen"]
        picks = test_rows(px, rows, h)
        each = {}
        for k, f in enumerate(FACTORS):
            ics = [v for v in (rs._ic(ranks[n, :, k].astype(float), px.forward(rows[n], h)) for n in picks) if v is not None]
            each[f] = {"ic": float(np.mean(ics)) if ics else None, "t": validate.newey_west_t(ics, rs.lag_of(h)), "dates": len(ics)}
        if not chosen:
            out["strategies"][s] = {"status": "NO_MODEL", "chosen": [], "horizon": h, "reference_each_signal": each, "reason": "개발 구간에서 채택된 신호가 없어 합성 점수를 시험하지 않았습니다."}
            continue
        score = np.stack([rs.composite(ranks[n], chosen, FACTORS) for n in range(len(rows))])
        res = en.evaluate(score, px, rows, picks, h, sectors)
        out["strategies"][s] = {"status": "TESTED", "chosen": chosen, "horizon": h, **res, **test_verdict(res), "reference_each_signal": each}
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
