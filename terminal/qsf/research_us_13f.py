"""Pre-registered test of the change in 13F breadth of ownership.  Rules: reports/QSF_US_13F_PROTOCOL.md.

A quarter's signal is built only from filings received by the deadline (report date + 45 days) and is used from the trading day
after it.  Holders are counted among filers that reported both quarters.  Securities are tied to tickers by price alone.  The
test runs once and a second run is refused.  Nothing here changes the live score, the QSF ledger or P6-11B.

The SEC files are downloaded data: they are read as text inside the zip, never extracted and never executed.  Security numbers
(CUSIPs) stay in research_data/sec13f/work and never enter a report.
"""
import csv
import io
import json
import warnings
import zipfile
from array import array
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np

PROTOCOL = "reports/QSF_US_13F_PROTOCOL.md"
REPORT = Path("reports") / "qsf" / "QSF_US_13F.json"
PREPARED = Path("reports") / "qsf" / "QSF_US_13F_PREPARE.json"
DATA = Path("research_data") / "sec13f"
RAW, WORK = DATA / "raw", DATA / "work"
REDUCED, CODES, SCAN, LINKS, BREADTH, FEATURES = WORK / "reduced", WORK / "cusips.json", WORK / "scan.npz", WORK / "links.json", WORK / "breadth.npz", WORK / "features.npz"
FIRST_PERIOD = "2013-06-30"          # the first report date the data sets hold in full
DEADLINE_DAYS = 45
UNIT_CHANGE = "2023-01-03"           # values were in thousands of dollars in filings received before this day
MIN_HOLDERS = 50
TOLERANCE, TOLERANCE_FALLBACK = 0.005, 0.02
MIN_MATCH_QUARTERS, MIN_MATCH_SHARE = 4, 0.9
FILL_MIN, FILL_MIN_YEAR = 0.90, 0.80
MIN_SAMPLE = 30                      # an evaluation day needs this many stocks (validate.per_date)
HORIZONS = {"SWING_20": 20, "QUARTER_63": 63}
REFERENCE_HORIZONS = {"LONG_252": 252}
NW_LAG = 13                          # the signal stands for a quarter, about thirteen evaluation days
FRESH_SESSIONS = 20
MONEY_PERIODS = {"2013_2019": ("2013-11-15", "2020-01-01"), "2020_on": ("2020-01-01", "9999-12-31")}
SIGNALS = ("breadth_chg", "breadth_rel", "breadth_level")
QUARTER_ENDS = ("03-31", "06-30", "09-30", "12-31")
MONTHS = {m: n for n, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1)}


# ---------------------------------------------------------------------- reading one data set
def iso(text: str) -> Optional[str]:
    """`31-JUL-2026` (the data sets' form) or an ISO date; anything else is no date."""
    t = text.strip().upper()
    try:
        if len(t) == 10 and t[4] == "-":
            return date.fromisoformat(t).isoformat()
        d, m, y = t.split("-")
        return date(int(y), MONTHS[m], int(d)).isoformat()
    except (ValueError, KeyError):
        return None


def kind_of(submission_type: str, amendment_type: str) -> Optional[str]:
    """O original, R restatement, N new holdings, X an amendment of a kind the protocol does not use; None is not a holdings report."""
    t = submission_type.strip().upper()
    if t == "13F-HR":
        return "O"
    if t == "13F-HR/A":
        return {"RESTATEMENT": "R", "NEW HOLDINGS": "N"}.get(amendment_type.strip().upper(), "X")
    return None


def _table(z: zipfile.ZipFile, name: str, stats: Counter) -> Iterator[Tuple[List[str], Dict[str, int]]]:
    member = next((m for m in z.namelist() if m.rsplit("/", 1)[-1].upper() == name), None)
    if member is None:
        raise KeyError(name)
    with z.open(member) as fh:
        it = csv.reader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline=""), delimiter="\t", quoting=csv.QUOTE_NONE)
        head = [h.strip().upper() for h in next(it)]
        ix = {h: j for j, h in enumerate(head)}
        for r in it:
            if len(r) == len(head):
                yield r, ix
            else:
                stats[f"bad_width_{name}"] += 1


def read_zip(path: Path, codes: Dict[str, int]) -> Dict[str, Any]:
    """Filings and the rows that count as a holding.  `codes` numbers each security and grows as new ones appear."""
    csv.field_size_limit(1 << 24)
    stats: Counter = Counter()
    with zipfile.ZipFile(path) as z:
        amend = {r[ix["ACCESSION_NUMBER"]]: r[ix["AMENDMENTTYPE"]] for r, ix in _table(z, "COVERPAGE.TSV", stats)}
        where: Dict[str, int] = {}
        acc, filed, kind, cik, period = [], [], [], [], []
        for r, ix in _table(z, "SUBMISSION.TSV", stats):
            a = r[ix["ACCESSION_NUMBER"]]
            k = kind_of(r[ix["SUBMISSIONTYPE"]], amend.get(a, ""))
            if k is None:
                stats["not_a_holdings_report"] += 1
                continue
            f, p = iso(r[ix["FILING_DATE"]]), iso(r[ix["PERIODOFREPORT"]])
            try:
                c = int(r[ix["CIK"]])
            except ValueError:
                c = -1
            if f is None or p is None or c < 0 or a in where:
                stats["unreadable_filing"] += 1
                continue
            if p[5:] not in QUARTER_ENDS or p < FIRST_PERIOD:
                stats["other_report_date"] += 1
                continue
            where[a] = len(acc)
            acc.append(a); filed.append(f); kind.append(k); cik.append(c); period.append(p)      # noqa: E702
            stats[f"kind_{k}"] += 1
        row_filing, row_code, row_ratio = array("i"), array("i"), array("f")
        for r, ix in _table(z, "INFOTABLE.TSV", stats):
            stats["rows"] += 1
            n = where.get(r[ix["ACCESSION_NUMBER"]])
            if n is None:
                stats["rows_of_unused_filings"] += 1
                continue
            if r[ix["PUTCALL"]].strip():
                stats["option_rows"] += 1
                continue
            if r[ix["SSHPRNAMTTYPE"]].strip().upper() != "SH":
                stats["principal_rows"] += 1
                continue
            try:
                value, shares = float(r[ix["VALUE"]]), float(r[ix["SSHPRNAMT"]])
            except ValueError:
                stats["unreadable_rows"] += 1
                continue
            code = r[ix["CUSIP"]].strip().upper()
            if not (value > 0 and shares > 0) or len(code) != 9:
                stats["zero_or_misnumbered_rows"] += 1
                continue
            row_filing.append(n)
            row_code.append(codes.setdefault(code, len(codes)))
            row_ratio.append(value / shares * (1000.0 if filed[n] < UNIT_CHANGE else 1.0))
            stats["holding_rows"] += 1
    return {"acc": np.array(acc, dtype=str), "filed": np.array(filed, dtype=str), "kind": np.array(kind, dtype=str), "cik": np.array(cik, dtype=np.int64),
            "period": np.array(period, dtype=str), "row_filing": np.frombuffer(row_filing, dtype=np.int32).copy() if len(row_filing) else np.zeros(0, np.int32),
            "row_code": np.frombuffer(row_code, dtype=np.int32).copy() if len(row_code) else np.zeros(0, np.int32),
            "row_ratio": np.frombuffer(row_ratio, dtype=np.float32).copy() if len(row_ratio) else np.zeros(0, np.float32), "stats": dict(stats)}


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def reduce_all(base: Path, log=print) -> Dict[str, Any]:
    """Each zip once: its filings and holding rows as arrays.  A zip already reduced is not read again."""
    base = Path(base)
    out = base / REDUCED
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    codes: Dict[str, int] = {c: n for n, c in enumerate(json.loads((base / CODES).read_text(encoding="utf-8")))} if (base / CODES).exists() else {}
    done = 0
    for z in sorted((base / RAW).glob("*_form13f.zip")):
        if z.name in index:
            continue
        d = read_zip(z, codes)
        stats = d.pop("stats")
        tmp = out / (z.name + ".tmp.npz")
        np.savez_compressed(tmp, **d)
        tmp.replace(out / (z.name + ".npz"))
        _write_json(base / CODES, sorted(codes, key=codes.get))          # numbers first, then the index that points at them
        days = sorted(d["filed"].tolist())
        index[z.name] = {"first": days[0] if days else None, "last": days[-1] if days else None, "filings": int(len(d["acc"])), "stats": stats}
        _write_json(index_path, index)
        done += 1
        log(f"{z.name} filings {len(d['acc'])} rows {stats.get('holding_rows', 0)}")
    return {"status": "REDUCED", "new": done, "files": len(index), "securities": len(codes)}


# ---------------------------------------------------------------------- quarters
def period_ends(last: str, first: str = FIRST_PERIOD) -> List[str]:
    out, y, m = [], int(first[:4]), int(first[5:7])
    while True:
        d = date(y, m, 30 if m in (6, 9) else 31).isoformat()
        if d > last:
            return out
        out.append(d)
        y, m = (y + 1, 3) if m == 12 else (y, m + 3)


def deadline(period: str) -> str:
    return (date.fromisoformat(period) + timedelta(days=DEADLINE_DAYS)).isoformat()


def cutoff(period: str, dates: Sequence[str]) -> Optional[str]:
    """The filing deadline, moved to the next trading day when the market is closed; None beyond the price history."""
    k = bisect_left(dates, deadline(period))
    return dates[k] if k < len(dates) else None


class Store:
    """The reduced data sets, read a few at a time so the whole history never sits in memory."""
    def __init__(self, base: Path, keep: int = 4):
        self.root = Path(base) / REDUCED
        self.index = json.loads((self.root / "index.json").read_text(encoding="utf-8"))
        self.keep, self._cache = keep, {}

    def _one(self, name: str) -> Dict[str, np.ndarray]:
        if name not in self._cache:
            while len(self._cache) >= self.keep:
                self._cache.pop(next(iter(self._cache)))
            with np.load(self.root / (name + ".npz")) as z:
                self._cache[name] = {k: z[k] for k in z.files}
        return self._cache[name]

    def window(self, first: str, last: str) -> Dict[str, np.ndarray]:
        """Every filing of the data sets whose filing dates reach into [first, last], as one set of arrays."""
        names = sorted(n for n, v in self.index.items() if v["first"] and v["first"] <= last and v["last"] >= first)
        parts = [self._one(n) for n in names]
        if not parts:
            return {"acc": np.zeros(0, str), "filed": np.zeros(0, str), "kind": np.zeros(0, str), "cik": np.zeros(0, np.int64), "period": np.zeros(0, str),
                    "row_filing": np.zeros(0, np.int32), "row_code": np.zeros(0, np.int32), "row_ratio": np.zeros(0, np.float32)}
        shift = np.cumsum([0] + [len(p["acc"]) for p in parts[:-1]])
        out = {k: np.concatenate([p[k] for p in parts]) for k in ("acc", "filed", "kind", "cik", "period", "row_code", "row_ratio")}
        out["row_filing"] = np.concatenate([p["row_filing"] + s for p, s in zip(parts, shift)])
        return out


def chosen(w: Dict[str, np.ndarray], period: str, by: str) -> Dict[int, int]:
    """{filing position: filer} of the filings that make up each filer's holdings for `period` as known on `by`: the newest of the
    original and its restatements, plus every new-holdings amendment received after it.  A filer with no such base has none."""
    idx = np.flatnonzero((w["period"] == period) & (w["filed"] <= by) & (w["kind"] != "X"))
    per: Dict[int, List[int]] = {}
    for i in idx:
        per.setdefault(int(w["cik"][i]), []).append(int(i))
    out: Dict[int, int] = {}
    for c, rows in per.items():
        rows.sort(key=lambda i: (str(w["filed"][i]), str(w["acc"][i])))
        base = next((i for i in reversed(rows) if w["kind"][i] in ("O", "R")), None)
        if base is None:
            continue
        out[base] = c
        for i in rows[rows.index(base) + 1:]:
            if w["kind"][i] == "N":
                out[i] = c
    return out


def _held(w: Dict[str, np.ndarray], picked: Dict[int, int]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(filer, security, value/shares) of every holding row of the picked filings."""
    filer = np.full(len(w["acc"]), -1, dtype=np.int64)
    for i, c in picked.items():
        filer[i] = c
    f = filer[w["row_filing"]] if len(w["row_filing"]) else np.zeros(0, np.int64)
    m = f >= 0
    return f[m], w["row_code"][m].astype(np.int64), w["row_ratio"][m]


def _pairs(a: np.ndarray, b: np.ndarray, width: int) -> Tuple[np.ndarray, np.ndarray]:
    """Distinct (a, b) pairs; `b` must stay below `width`."""
    key = np.unique(a * width + b)
    return key // width, key % width


def _median_by(code: np.ndarray, value: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(codes, median of the values, how many values) per code."""
    if not len(code):
        return np.zeros(0, np.int64), np.zeros(0), np.zeros(0, np.int64)
    order = np.lexsort((value, code))
    c, v = code[order], value[order].astype(float)
    start = np.flatnonzero(np.r_[True, c[1:] != c[:-1]])
    end = np.r_[start[1:], len(c)]
    return c[start], (v[(start + end - 1) // 2] + v[(start + end) // 2]) / 2, end - start


def scan(base: Path, dates: Sequence[str], log=print) -> Dict[str, Any]:
    """Per report date, as known on its cut-off: how many filers hold each security and the price their filings imply."""
    store = Store(base)
    n_codes = len(json.loads((Path(base) / CODES).read_text(encoding="utf-8")))
    periods = [p for p in period_ends(dates[-1]) if cutoff(p, dates)]
    out: Dict[str, Any] = {"periods": np.array(periods, dtype=str), "cutoffs": np.array([cutoff(p, dates) for p in periods], dtype=str)}
    quarters = []
    for k, p in enumerate(periods):
        w = store.window(p, str(out["cutoffs"][k]))
        picked = chosen(w, p, str(out["cutoffs"][k]))
        filer, code, ratio = _held(w, picked)
        _, pc = _pairs(filer, code, n_codes)
        holders = np.bincount(pc, minlength=n_codes)
        codes, price, _ = _median_by(code, ratio)
        keep = holders[codes] >= MIN_HOLDERS
        out[f"code_{k}"], out[f"price_{k}"], out[f"holders_{k}"] = codes[keep].astype(np.int32), price[keep], holders[codes][keep].astype(np.int32)
        kinds = Counter(str(w["kind"][i]) for i in picked)
        unused = int(((w["period"] == p) & (w["filed"] <= str(out["cutoffs"][k])) & (w["kind"] == "X")).sum())
        late = int(((w["period"] == p) & (w["filed"] > str(out["cutoffs"][k]))).sum())
        quarters.append({"period": p, "cutoff": str(out["cutoffs"][k]), "filers": len(set(picked.values())), "originals": kinds["O"], "restatements": kinds["R"],
                         "new_holdings": kinds["N"], "amendments_of_other_kinds": unused, "late_in_loaded_files": late, "securities_50_holders": int(keep.sum())})
        log(f"scan {p} filers {quarters[-1]['filers']} securities {quarters[-1]['securities_50_holders']}")
    np.savez_compressed(Path(base) / SCAN, **out)
    return {"quarters": quarters}


# ---------------------------------------------------------------------- tying securities to tickers
def quoted_close(px: Any, splits: Dict[str, Any], period: str) -> np.ndarray:
    """The close actually quoted on the report date (the session before it when the market was closed): the stored close is
    restated for later splits, so those are put back."""
    from terminal.qsf import pit
    i = bisect_right(px.dates, period) - 1
    out = np.full(len(px.symbols), np.nan)
    if i < 0:
        return out
    c = px.data["close"][i].astype(float)
    for j, s in enumerate(px.symbols):
        if np.isfinite(c[j]) and c[j] > 0:
            out[j] = c[j] * pit.Splits(splits.get(s) or []).factor(px.dates[i])
    return out


def link(scan_file: Dict[str, np.ndarray], closes: Sequence[np.ndarray], tolerance: float) -> Tuple[Dict[int, int], Dict[str, Any]]:
    """{security: ticker position}.  A security is tied to a ticker when the price its filings imply sits within `tolerance` of the
    ticker's quoted close in at least MIN_MATCH_QUARTERS quarters and in MIN_MATCH_SHARE of the quarters both have a value; the
    closest ticker wins when several qualify.  No name and no later return is read."""
    seen_code: Dict[int, int] = {}
    seen_sym = [0] * len(closes[0])
    gaps: Dict[Tuple[int, int], List[float]] = {}
    for k, a in enumerate(closes):
        ok = np.flatnonzero(np.isfinite(a))
        for j in ok:
            seen_sym[j] |= 1 << k
        order = ok[np.argsort(a[ok])]
        sa = a[order]
        codes, price = scan_file[f"code_{k}"], scan_file[f"price_{k}"]
        lo, hi = np.searchsorted(sa, price / (1 + tolerance), "left"), np.searchsorted(sa, price / (1 - tolerance), "right")
        for c, p, x, y in zip(codes, price, lo, hi):
            seen_code[int(c)] = seen_code.get(int(c), 0) | (1 << k)
            for t in range(x, y):
                g = abs(p / sa[t] - 1)
                if g <= tolerance:
                    gaps.setdefault((int(c), int(order[t])), []).append(float(g))
    best: Dict[int, Tuple[float, int]] = {}
    for (c, j), g in gaps.items():
        both = bin(seen_code[c] & seen_sym[j]).count("1")
        if len(g) >= MIN_MATCH_QUARTERS and len(g) >= MIN_MATCH_SHARE * both:
            cand = (float(np.median(g)), j)
            if c not in best or cand < best[c]:
                best[c] = cand
    links = {c: j for c, (_, j) in best.items()}
    per = Counter(links.values())
    return links, {"tolerance": tolerance, "securities_tied": len(links), "tickers_tied": len(per), "tickers_with_several_securities": sum(1 for v in per.values() if v > 1)}


def count(base: Path, scan_file: Dict[str, np.ndarray], links: Dict[int, int], n_symbols: int, min_holders: int = MIN_HOLDERS, log=print) -> Dict[str, Any]:
    """Per quarter and ticker: holders now and a quarter earlier among the filers that reported both, as known on the cut-off."""
    store = Store(base)
    n_codes = len(json.loads((Path(base) / CODES).read_text(encoding="utf-8")))
    to_sym = np.full(n_codes, -1, dtype=np.int64)
    for c, j in links.items():
        to_sym[c] = j
    periods, cutoffs = [str(x) for x in scan_file["periods"]], [str(x) for x in scan_file["cutoffs"]]
    now, prev = (np.full((len(periods), n_symbols), -1, dtype=np.int32) for _ in range(2))
    common = np.zeros(len(periods), dtype=np.int32)
    several = np.zeros(len(periods), dtype=np.int32)
    for k in range(1, len(periods)):
        w = store.window(periods[k - 1], cutoffs[k])
        sides = []
        for p in (periods[k], periods[k - 1]):
            filer, code, _ = _held(w, chosen(w, p, cutoffs[k]))
            sides.append((filer, code))
        both = np.intersect1d(np.unique(sides[0][0]), np.unique(sides[1][0]))
        common[k] = len(both)
        for side, target in zip(sides, (now, prev)):
            filer, code = side
            sym = to_sym[code]
            m = (sym >= 0) & np.isin(filer, both)
            if target is now:
                _, s2 = _pairs(code[m], sym[m], n_symbols)
                several[k] = int((np.bincount(s2, minlength=n_symbols) > 1).sum())
            _, s = _pairs(filer[m], sym[m], n_symbols)
            target[k] = np.bincount(s, minlength=n_symbols)
        log(f"count {periods[k]} common filers {common[k]}")
    return {"periods": np.array(periods, dtype=str), "cutoffs": np.array(cutoffs, dtype=str), "now": now, "prev": prev, "common": common, "several": several,
            "min_holders": np.array(min_holders)}


def quarter_on(day: str, cutoffs: Sequence[str], periods: Sequence[str]) -> Optional[int]:
    """The quarter whose value is in use on `day`: the newest cut-off strictly before it, until the next one has passed."""
    k = bisect_left(cutoffs, day) - 1
    if k < 1:
        return None
    if k == len(cutoffs) - 1:
        y, m = int(periods[k][:4]), int(periods[k][5:7])
        nxt = deadline(date(y + (m == 12), 3 if m == 12 else m + 3, 30 if m in (3, 6) else 31).isoformat())      # the calendar deadline stands in for the next cut-off, which can only be the same day or later
        if day > nxt:
            return None
    return k


def values(b: Dict[str, np.ndarray], k: int) -> np.ndarray:
    """[tickers, 3]: change over the common filers, change over the earlier count, level.  Empty unless both counts reach the floor."""
    now, prev, n = b["now"][k].astype(float), b["prev"][k].astype(float), float(b["common"][k])
    floor = int(b["min_holders"])
    out = np.full((len(now), len(SIGNALS)), np.nan, dtype=np.float32)
    ok = (now >= floor) & (prev >= floor) & (n > 0)
    out[ok, 0] = (now[ok] - prev[ok]) / n
    out[ok, 1] = (now[ok] - prev[ok]) / prev[ok]
    out[ok, 2] = now[ok] / n
    return out


def features(px: Any, rows: Sequence[int], members: Callable[[str], List[str]], b: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """The signal on every evaluation day for the stocks of the sample, and how much of the sample has a value."""
    from terminal.qsf import research_swing as rs
    cutoffs, periods = [str(x) for x in b["cutoffs"]], [str(x) for x in b["periods"]]
    tensor = np.full((len(rows), len(px.symbols), len(SIGNALS)), np.nan, dtype=np.float32)
    quarter = np.full(len(rows), -1, dtype=np.int32)
    age = np.full(len(rows), -1, dtype=np.int32)
    sample = np.zeros(len(rows), dtype=np.int32)
    for n, i in enumerate(rows):
        day = px.dates[i]
        k = quarter_on(day, cutoffs, periods)
        if k is None:
            continue
        keep = rs.eligible(px.data, i, sorted({px.col[t] for t in members(day) if t in px.col}))
        quarter[n], sample[n] = k, len(keep)
        age[n] = i - bisect_left(px.dates, cutoffs[k])
        tensor[n, keep] = values(b, k)[keep]
    return {"rows": np.array(list(rows)), "tensor": tensor, "quarter": quarter, "age": age, "sample": sample}


def fill(f: Dict[str, np.ndarray], dates: Sequence[str]) -> Dict[str, Any]:
    """Share of the sample that has a value, per evaluation day.  A day whose sample is under MIN_SAMPLE stocks cannot be evaluated
    and has no ratio: the sample's membership history ends before the price history does, and 0 of 0 is not 0%."""
    used = np.flatnonzero((f["quarter"] >= 0) & (f["sample"] >= MIN_SAMPLE))
    have = np.isfinite(f["tensor"][used, :, 0]).sum(axis=1)
    share = have / np.maximum(1, f["sample"][used])
    years: Dict[str, List[float]] = {}
    for n, s in zip(used, share):
        years.setdefault(dates[int(f["rows"][n])][:4], []).append(float(s))
    by_year = {y: float(np.mean(v)) for y, v in sorted(years.items())}
    overall = float(np.mean(share)) if len(share) else 0.0
    return {"overall": overall, "by_year": by_year, "days": int(len(used)), "days_without_a_sample": int(((f["quarter"] >= 0) & (f["sample"] < MIN_SAMPLE)).sum()), "mean_sample": float(np.mean(f["sample"][used])) if len(used) else 0.0,
            "mean_with_value": float(np.mean(have)) if len(used) else 0.0, "passes": bool(overall >= FILL_MIN and by_year and min(by_year.values()) >= FILL_MIN_YEAR)}


# ---------------------------------------------------------------------- runs
def _load(base: Path):
    from terminal.qsf import research_ensemble as en, research_swing as rs
    root, px, rows, swing, insider = en._inputs(base)
    return root, px, rows, swing, insider, rs._members(base, root), rs._sectors(base, root), en._splits(root)


def _controls(base: Path, root: Path, px: Any, rows: Sequence[int], swing: np.ndarray, insider: np.ndarray, sectors: Dict[str, Optional[str]]) -> Dict[str, np.ndarray]:
    """The nine existing themes a new signal must add to, and size (20-session mean traded value, a stand-in for market value)."""
    from terminal.qsf import research_ensemble as en, research_swing as rs
    with np.load(root / en.FUND_FILE) as z:
        fund = z["tensor"]
    themes = en.theme_scores(en.signal_ranks(fund, swing, insider, px.symbols, sectors))
    themes.pop("insider")
    d = px.data
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)          # a stock with no bar in the window has no mean
        traded = np.stack([np.nanmean(d["close"][max(0, i - 19):i + 1] * d["volume"][max(0, i - 19):i + 1], axis=0) for i in rows]).astype(np.float32)
    size = rs.rank_tensor(np.where(np.isfinite(traded) & (traded > 0), traded, np.nan)[:, :, None], ("size",), {"size": True})[:, :, 0]
    return {**themes, "size": size}


def prepare(base: Path, log=print) -> Dict[str, Any]:
    """Everything up to the signal, and how complete it is.  No return is computed."""
    from terminal.qsf import research_ensemble as en, research_swing as rs
    base = Path(base)
    if (base / REPORT).exists():
        raise RuntimeError("이미 시험을 실행했습니다. 준비 단계를 다시 돌리지 않습니다.")
    root, px, rows, swing, insider, members, sectors, splits = _load(base)
    scanned = scan(base, px.dates, log=log)
    with np.load(base / SCAN) as z:
        sf = {k: z[k] for k in z.files}
    closes = [quoted_close(px, splits, str(p)) for p in sf["periods"]]
    tried = []
    for tol in (TOLERANCE, TOLERANCE_FALLBACK):
        links, how = link(sf, closes, tol)
        b = count(base, sf, links, len(px.symbols), log=log)
        f = features(px, rows, members, b)
        ratio = fill(f, px.dates)
        tried.append({**how, "fill": ratio})
        if ratio["overall"] >= FILL_MIN:
            break
    _write_json(base / LINKS, {str(c): px.symbols[j] for c, j in links.items()})
    np.savez_compressed(base / BREADTH, **b)
    np.savez_compressed(base / FEATURES, **f)
    used = [n for n in range(len(rows)) if f["quarter"][n] >= 0 and f["sample"][n] >= MIN_SAMPLE]
    chg = f["tensor"][used, :, 0]
    pct = [float(x) for x in np.nanpercentile(chg, [5, 25, 50, 75, 95])]
    score = rs.rank_tensor(f["tensor"], SIGNALS, {s: True for s in SIGNALS})
    controls = _controls(base, root, px, rows, swing, insider, sectors)
    corr = en.theme_correlation({**controls, "breadth": score[:, :, 0], "breadth_rel": score[:, :, 1], "breadth_level": score[:, :, 2]}, used)
    quarters = scanned["quarters"]
    for k, q in enumerate(quarters):
        q.update(common_filers=int(b["common"][k]), tickers_with_several_securities=int(b["several"][k]))
    out = {"status": "PREPARED_OK" if ratio["passes"] else "DATA_INSUFFICIENT", "protocol": PROTOCOL, "tolerance_used": tried[-1]["tolerance"], "link_attempts": tried,
           "fill": ratio, "quarters": quarters, "changes": int(len(quarters) - 1), "value_percentiles_5_25_50_75_95": pct,
           "share_exactly_zero": float(np.mean(chg[np.isfinite(chg)] == 0)), "correlation_with_breadth": {k: corr["breadth"][k] for k in corr["breadth"]},
           "correlation_rel_with_breadth": corr["breadth_rel"]["breadth"], "first_day": px.dates[rows[used[0]]], "last_day": px.dates[rows[used[-1]]], "note": "수익률은 계산하지 않았습니다."}
    (base / PREPARED).parent.mkdir(parents=True, exist_ok=True)
    (base / PREPARED).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def evaluate(score: np.ndarray, px: Any, rows: Sequence[int], picks: Sequence[int], h: int, groups: np.ndarray, cost: float, quarter: np.ndarray) -> Dict[str, Any]:
    """The protocol's reading of one score at one horizon.  `t` uses the quarter-long lag; the usual lag is kept beside it."""
    from terminal.qsf import validate
    daily = []
    spy = px.data["adj_close"][:, px.col["SPY"]]
    for n in picks:
        i = rows[n]
        r, s = px.forward(i, h), score[n].astype(float)
        day = validate.per_date(s, r, cost, groups)
        if not day:
            continue
        ok = np.isfinite(s) & np.isfinite(r)
        e = r[ok] - r[ok].mean()
        q = validate.rank(s[ok]) / (ok.sum() - 1)
        day.update(date=px.dates[i], top_excess=float(e[q >= 0.8].mean()), quarter=int(quarter[n]), above=bool(spy[i] > np.nanmean(spy[max(0, i - 199):i + 1])))
        daily.append(day)
    out = validate.summarize(daily, h)
    used = [d for d in daily if d.get("ic") is not None]
    if not used:
        return out
    ics = [d["ic"] for d in used]
    per_quarter: Dict[int, List[float]] = {}
    for d in used:
        per_quarter.setdefault(d["quarter"], []).append(d["ic"])
    qm = np.array([np.mean(v) for _, v in sorted(per_quarter.items())])
    out.update(t_usual_lag=out["t"], t=validate.newey_west_t(ics, NW_LAG), lag=NW_LAG, top_excess=float(np.mean([d["top_excess"] for d in daily])),
               mean_stocks=float(np.mean([d["n"] for d in daily])),
               quarters={"n": int(len(qm)), "mean_ic": float(qm.mean()), "t_simple": float(qm.mean() / (qm.std(ddof=1) / np.sqrt(len(qm)))) if len(qm) > 2 and qm.std(ddof=1) > 0 else None},
               ic_spy_above_200d={"ic": float(np.mean([d["ic"] for d in used if d["above"]])) if any(d["above"] for d in used) else None, "dates": sum(d["above"] for d in used)},
               ic_spy_below_200d={"ic": float(np.mean([d["ic"] for d in used if not d["above"]])) if any(not d["above"] for d in used) else None, "dates": sum(not d["above"] for d in used)})
    return out


def portfolios(score: np.ndarray, px: Any, rows: Sequence[int], first: str, last: str, cost: float, h: int = 20) -> Dict[str, Any]:
    """Equal-weight holdings by the evaluation's own rank rule, rebalanced every 20 sessions, cost on what is replaced."""
    from terminal.qsf import research_kr as kr, research_swing as rs, validate
    ns = [n for n, i in enumerate(rows) if first <= px.dates[i] < last and i + h < len(px.dates) and np.isfinite(score[n]).any()][::h // rs.STEP]
    if not ns:
        return {"periods": 0}
    ret = np.stack([px.forward(rows[n], h) for n in ns])
    sets: Dict[str, List[np.ndarray]] = {"all_equal": [], "no_bottom": [], "bottom": [], "top": []}
    for n in ns:
        s = score[n].astype(float)
        ok = np.isfinite(s)
        q = np.full(s.shape, np.nan)
        q[ok] = validate.rank(s[ok]) / max(1, ok.sum() - 1)
        with np.errstate(invalid="ignore"):
            sets["all_equal"].append(ok)
            sets["no_bottom"].append(q > 0.2)
            sets["bottom"].append(q <= 0.2)
            sets["top"].append(q >= 0.8)
    out: Dict[str, Any] = {"periods": len(ns), "first": px.dates[rows[ns[0]]], "last": px.dates[rows[ns[-1]]]}
    for name, p in sets.items():
        out[name] = {"annual_net": kr.annual_growth(kr.rebalance_path(p, ret, cost), h, 252), "mean_holdings": float(np.mean([x.sum() for x in p]))}
    out["spy"] = {"annual": kr.annual_growth([float(v) for v in ret[:, px.col["SPY"]]], h, 252)}
    return out


def money_conditions(money: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
    """B1: the top fifth beats SPY in both periods.  B2: leaving out the bottom fifth beats holding the whole sample in both."""
    def gt(a, b):
        return a is not None and b is not None and a > b
    return {"b1_top_beats_market": all(m.get("periods") and gt(m["top"]["annual_net"], m["spy"]["annual"]) for m in money.values()),
            "b2_avoiding_bottom_helps": all(m.get("periods") and gt(m["no_bottom"]["annual_net"], m["all_equal"]["annual_net"]) for m in money.values())}


def condition_c(partial: Dict[str, Any]) -> bool:
    from terminal.qsf import validate
    ic, t = partial.get("ic"), partial.get("t")
    return ic is not None and t is not None and ic >= validate.MIN_IC and t >= validate.MIN_T


def reading(primary: Dict[str, Any], independent: bool, conditions: Dict[str, bool]) -> str:
    """The protocol's reading of one horizon, fixed before the run."""
    if primary.get("verdict") != "WEAK_POSITIVE_EVIDENCE":
        return "NO_EVIDENCE"
    if not independent:
        return "A_NOT_INDEPENDENT"
    if conditions["b1_top_beats_market"]:
        return "A_C_AND_B1"
    return "A_C_AND_B2" if conditions["b2_avoiding_bottom_helps"] else "A_C_ONLY"


def run_once(base: Path, log=print) -> Dict[str, Any]:
    from terminal.qsf import config, research_kr_sue as sue, research_swing as rs
    from terminal.qsf.research_score import test_verdict
    base = Path(base)
    target = base / REPORT
    if target.exists():
        raise RuntimeError("이미 시험을 실행했습니다. 프로토콜상 다시 실행할 수 없습니다.")
    prepared = json.loads((base / PREPARED).read_text(encoding="utf-8"))
    if prepared["status"] != "PREPARED_OK":
        out: Dict[str, Any] = {"status": "DATA_INSUFFICIENT", "protocol": PROTOCOL, "fill": prepared["fill"], "reason": "채움 비율이 미리 정한 기준에 못 미쳐 시험하지 않았습니다."}
        target.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        return out
    root, px, rows, swing, insider, _, sectors, _ = _load(base)
    with np.load(base / FEATURES) as z:
        f = {k: z[k] for k in z.files}
    if [int(i) for i in f["rows"]] != list(rows):
        raise ValueError("ROWS_DIFFER")
    ranks = rs.rank_tensor(f["tensor"], SIGNALS, {s: True for s in SIGNALS}) * 100
    primary = ranks[:, :, 0]
    controls = _controls(base, root, px, rows, swing, insider, sectors)
    left = sue.residual(primary, controls)
    fresh_rows = (f["age"] >= 0) & (f["age"] <= FRESH_SESSIONS)
    scores = {"BREADTH": primary, "BREADTH_RESIDUAL": left, "BREADTH_REL": ranks[:, :, 1], "BREADTH_LEVEL": ranks[:, :, 2],
              "BREADTH_FRESH": np.where(fresh_rows[:, None], primary, np.nan), "BREADTH_OLDER": np.where(~fresh_rows[:, None], primary, np.nan)}
    cost = config.round_trip_cost("US")
    groups = np.array([sectors.get(s) or "?" for s in px.symbols])
    out = {"status": "TESTED", "protocol": PROTOCOL, "cost": cost, "lag": NW_LAG, "tolerance_used": prepared["tolerance_used"], "fill": prepared["fill"], "scores": {}}
    for name, score in scores.items():
        res: Dict[str, Any] = {}
        for label, h in {**HORIZONS, **REFERENCE_HORIZONS}.items():
            picks = [n for n, i in enumerate(rows) if f["quarter"][n] >= 0 and i + h < len(px.dates)]
            r = evaluate(score, px, rows, picks, h, groups, cost, f["quarter"])
            res[label] = {"horizon": h, **r, **test_verdict(r)}
            log(f"{name} {label} done")
        out["scores"][name] = res
    money = {k: portfolios(primary, px, rows, a, b, cost) for k, (a, b) in MONEY_PERIODS.items()}
    conditions = money_conditions(money)
    out["money_20d"], out["conditions"], out["controls"], out["readings"], out["partial"] = money, dict(conditions), list(controls), {}, {}
    for label in HORIZONS:
        partial = {k: out["scores"]["BREADTH_RESIDUAL"][label].get(k) for k in ("ic", "t", "dates", "mean_stocks")}
        independent = condition_c(partial)
        out["partial"][label] = {**partial, "c_independent": independent}
        out["readings"][label] = reading(out["scores"]["BREADTH"][label], independent, conditions)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return out
