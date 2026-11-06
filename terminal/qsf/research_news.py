"""Pre-registered historical news research.  Rules: reports/QSF_NEWS_RESEARCH_PROTOCOL.md.

Only headlines dated up to the evaluation date count.  Development sees only returns that end before TEST_FIRST; the test runs once
and a second run is refused.  Authors and article text in the source file are never extracted.  Nothing here changes the live score,
the QSF ledger, the headline record in data/news or P6-11B.
"""
import bisect
import collections
import csv
import gzip
import hashlib
import json
import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np

from terminal.qsf import config, research_swing as rs, validate

PROTOCOL = "reports/QSF_NEWS_RESEARCH_PROTOCOL.md"
FOLDER = Path("research_data") / "fnspid"      # not under data/: the test guard copies that folder, twice
SOURCE = "All_external.csv"
EXTRACT = "news_rows.json.gz"
FEATURES = "news_features.npz"
DEV_REPORT = Path("reports") / "qsf" / "QSF_NEWS_DEV.json"
TEST_REPORT = Path("reports") / "qsf" / "QSF_NEWS_TEST.json"

READ_FROM = "2010-01-01"
VALUES_FROM = "2010-04-01"
SOURCE_END = "2020-05-31"
DEV_END = "2017-01-01"            # development returns end before this date
TEST_FIRST = "2017-01-03"
ROUNDUP_TICKERS = 4               # the same title on this many sample tickers in one day is a roundup
HORIZONS = rs.HORIZONS
FACTORS = ("news_tone_7", "news_tone_30", "news_neg_share_30", "news_abnormal_7", "news_count_91")
GOOD_HIGH = {"news_tone_7": True, "news_tone_30": True, "news_neg_share_30": False, "news_abnormal_7": False, "news_count_91": False}

POSITIVE = frozenset("beat beats tops surge surges soar soars jump jumps rally rallies gain gains rise rises upgrade upgrades upgraded raises raised record strong growth outperform bullish buy boost boosts".split())
NEGATIVE = frozenset("miss misses fall falls drop drops plunge plunges slump slumps tumble tumbles sink sinks downgrade downgrades downgraded cut cuts lowers lowered weak loss losses lawsuit probe investigation recall bearish sell warning warns fraud bankruptcy decline declines".split())


def tone(title: str) -> int:
    words = re.findall(r"[a-z]+", title.lower())
    pos, neg = sum(w in POSITIVE for w in words), sum(w in NEGATIVE for w in words)
    return (pos > neg) - (neg > pos)


def _key(day: str, title: str) -> str:
    return hashlib.sha256(f"{day}|{title.strip().lower()}".encode()).hexdigest()[:16]


def extract(rows: Iterable[Tuple[str, str, str]], wanted: Set[str], read_from: str = READ_FROM, end: str = SOURCE_END) -> Dict[str, Any]:
    """``rows``: (date text, title, ticker).  Returns per ticker a date-sorted list of [day, tone], without roundups or repeats."""
    tickers_of: Dict[str, Set[str]] = collections.defaultdict(set)
    kept: Dict[Tuple[str, str], Tuple[str, str, int]] = {}
    read = 0
    for date_text, title, ticker in rows:
        ticker, day = (ticker or "").strip().upper(), (date_text or "")[:10]
        if ticker not in wanted or not title or not title.strip() or not (read_from <= day <= end):
            continue
        read += 1
        key = _key(day, title)
        tickers_of[key].add(ticker)
        kept[(key, ticker)] = (ticker, day, tone(title))
    out: Dict[str, List[List[Any]]] = collections.defaultdict(list)
    roundup = 0
    for (key, _), (ticker, day, t) in kept.items():
        if len(tickers_of[key]) >= ROUNDUP_TICKERS:
            roundup += 1
            continue
        out[ticker].append([day, t])
    for v in out.values():
        v.sort(key=lambda r: r[0])
    return {"articles": dict(out), "read": read, "unique": len(kept), "roundup_removed": roundup}


def _since(day: str, days: int) -> str:
    return (datetime.strptime(day, "%Y-%m-%d").date() - timedelta(days=days - 1)).isoformat()


def factors_at(rows: List[List[Any]], day: str) -> Dict[str, float]:
    """Rows sorted by date.  An empty window has no tone, but a true count of zero.  Before the first article nothing is known."""
    nan = float("nan")
    filed = [r[0] for r in rows]
    if not filed or filed[0] > day:
        return {f: nan for f in FACTORS}
    end = bisect.bisect_right(filed, day)

    def start(n: int) -> int:
        return bisect.bisect_left(filed, _since(day, n))
    w7, w30, w91 = rows[start(7):end], rows[start(30):end], rows[start(91):end]
    prior = len(w91) - len(w7)
    mean = lambda w: float(np.mean([r[1] for r in w])) if w else nan     # noqa: E731
    return {"news_tone_7": mean(w7), "news_tone_30": mean(w30), "news_neg_share_30": sum(r[1] < 0 for r in w30) / len(w30) if w30 else nan,
            "news_abnormal_7": math.log1p(len(w7)) - math.log1p(prior / 12), "news_count_91": math.log1p(len(w91))}


def build_features(px: validate.Prices, members, articles: Dict[str, List[List[Any]]], progress=None) -> Dict[str, Any]:
    d = px.data
    rows = list(range(rs.HISTORY, len(px.dates) - 1, rs.STEP))
    tensor = np.full((len(rows), len(px.symbols), len(FACTORS)), np.nan, dtype=np.float32)
    counts = []
    for n, i in enumerate(rows):
        day = px.dates[i]
        if day < VALUES_FROM or day > SOURCE_END:      # outside the data: unknown, not "no news"
            continue
        keep = rs.eligible(d, i, sorted({px.col[t] for t in members(day) if t in px.col}))
        linked = 0
        for j in keep:
            got = articles.get(px.symbols[j])
            if not got or got[0][0] > day:
                continue
            linked += 1
            f = factors_at(got, day)
            for k, name in enumerate(FACTORS):
                tensor[n, j, k] = f[name]
        counts.append({"date": day, "eligible": len(keep), "linked": linked})
        if progress:
            progress(n + 1, len(rows), day)
    return {"rows": rows, "tensor": tensor, "counts": counts}


def dev_rows(px: validate.Prices, rows: List[int], h: int) -> List[int]:
    return [n for n, i in enumerate(rows) if px.dates[i] >= VALUES_FROM and i + h < len(px.dates) and px.dates[i + h] < DEV_END]


def test_rows(px: validate.Prices, rows: List[int], h: int) -> List[int]:
    return [n for n, i in enumerate(rows) if TEST_FIRST <= px.dates[i] <= SOURCE_END and i + h < len(px.dates)]


def evaluate(ranks: np.ndarray, px: validate.Prices, rows: List[int], picks: List[int], h: int, chosen: Sequence[str], sectors: Dict[str, Optional[str]]) -> Dict[str, Any]:
    cost = config.round_trip_cost("US")
    daily, sc, rt, be, ex, above, below = [], [], [], [], [], [], []
    spy = px.col["SPY"]
    groups = np.array([sectors.get(s) or "?" for s in px.symbols])
    a = px.data["adj_close"][:, spy]
    for n in picks:
        i = rows[n]
        r = px.forward(i, h)
        s = rs.composite(ranks[n], list(chosen), FACTORS)
        day = validate.per_date(s, r, cost, groups)
        if not day:
            continue
        ok = np.isfinite(s) & np.isfinite(r)
        e = r[ok] - r[ok].mean()
        q = validate.rank(s[ok]) / (ok.sum() - 1)
        day.update(date=px.dates[i], top_excess=float(e[q >= 0.8].mean()), n=int(ok.sum()))
        daily.append(day)
        if day.get("ic") is not None:
            (above if a[i] > np.nanmean(a[i - 199:i + 1]) else below).append(day["ic"])
        sc.append(s[ok]); rt.append(r[ok]); ex.append(e); be.append(np.full(int(ok.sum()), r[spy]))     # noqa: E702
    out = validate.summarize(daily, h)
    if daily:
        out["t"] = validate.newey_west_t([d["ic"] for d in daily if d.get("ic") is not None], rs.lag_of(h))
        out["top_excess"] = float(np.mean([d["top_excess"] for d in daily]))
        out["buy_excess"], out["buy_dates"] = out["top_excess"], len(daily)      # condition 5 reads the top fifth, as in the earnings test
        out["mean_stocks"] = float(np.mean([d["n"] for d in daily]))
        out["buckets"] = validate.bucket_table(*(np.concatenate(x) for x in (sc, rt, be, ex)), cost)
        out["ic_spy_above_200d"] = {"ic": float(np.mean(above)) if above else None, "dates": len(above)}
        out["ic_spy_below_200d"] = {"ic": float(np.mean(below)) if below else None, "dates": len(below)}
    return out


# ---------------------------------------------------------------------- runs
def _csv_rows(path: Path) -> Iterable[Tuple[str, str, str]]:
    csv.field_size_limit(10 ** 9)
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        r = csv.reader(fh)
        head = next(r)
        ix = {c: i for i, c in enumerate(head)}
        for row in r:
            if len(row) == len(head):
                yield row[ix["Date"]], row[ix["Article_title"]], row[ix["Stock_symbol"]]


def prepare(base: Path) -> Dict[str, Any]:
    _, _, px = rs._load(base)
    res = extract(_csv_rows(base / FOLDER / SOURCE), set(px.symbols))
    with gzip.open(base / FOLDER / EXTRACT, "wt", encoding="utf-8") as fh:
        json.dump(res["articles"], fh)
    return {"status": "PREPARED", "tickers": len(res["articles"]), "read": res["read"], "unique": res["unique"], "roundup_removed": res["roundup_removed"], "kept": sum(len(v) for v in res["articles"].values())}


def develop(base: Path, log=print) -> Dict[str, Any]:
    root, _, px = rs._load(base)
    with gzip.open(base / FOLDER / EXTRACT, "rt", encoding="utf-8") as fh:
        articles = json.load(fh)
    b = build_features(px, rs._members(base, root), articles, progress=lambda n, m, d: n % 100 == 0 and log(f"{n}/{m} {d}"))
    np.savez_compressed(base / FOLDER / FEATURES, rows=np.array(b["rows"]), tensor=b["tensor"])
    ranks = rs.rank_tensor(b["tensor"], FACTORS, GOOD_HIGH)
    res = {}
    for s, h in HORIZONS.items():
        picks = dev_rows(px, b["rows"], h)
        if any(px.dates[b["rows"][n] + h] >= DEV_END for n in picks):
            raise ValueError("TEST_DATA_IN_DEVELOPMENT")
        res[s] = rs.select(ranks, px, b["rows"], picks, h, FACTORS)
    active = [c for c in b["counts"] if c["eligible"]]
    out = {"status": "DEVELOPED", "protocol": PROTOCOL, "strategies": res, "factors": list(FACTORS), "mean_eligible": float(np.mean([c["eligible"] for c in active])), "mean_linked": float(np.mean([c["linked"] for c in active]))}
    (base / DEV_REPORT).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def test_once(base: Path) -> Dict[str, Any]:
    target = base / TEST_REPORT
    if target.exists():
        raise RuntimeError("이미 시험을 실행했습니다. 프로토콜상 다시 실행할 수 없습니다.")
    root, _, px = rs._load(base)
    dev = json.loads((base / DEV_REPORT).read_text(encoding="utf-8"))
    sectors = rs._sectors(base, root)
    z = np.load(base / FOLDER / FEATURES)
    rows = [int(i) for i in z["rows"]]
    ranks = rs.rank_tensor(z["tensor"], FACTORS, GOOD_HIGH)
    out: Dict[str, Any] = {"status": "TESTED", "protocol": PROTOCOL, "strategies": {}}
    for s, h in HORIZONS.items():
        chosen = dev["strategies"][s]["chosen"]
        if not chosen:
            out["strategies"][s] = {"status": "NO_MODEL", "chosen": [], "horizon": h, "reason": "개발 구간에서 채택된 요인이 없어 시험하지 않았습니다."}
            continue
        picks = test_rows(px, rows, h)
        res = evaluate(ranks, px, rows, picks, h, chosen, sectors)
        each = {}
        for f in FACTORS:
            k = FACTORS.index(f)
            ics = [v for v in (rs._ic(ranks[n, :, k].astype(float), px.forward(rows[n], h)) for n in picks) if v is not None]
            each[f] = {"ic": float(np.mean(ics)) if ics else None, "t": validate.newey_west_t(ics, rs.lag_of(h)), "dates": len(ics)}
        out["strategies"][s] = {"status": "TESTED", "chosen": chosen, "horizon": h, **res, **validate.verdict(res), "each_factor": each}
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
