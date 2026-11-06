"""Independent test of one hypothesis on dates no earlier check used.  Criteria: reports/QSF_OOS_TEST_PROTOCOL.md.

Research only: it never touches the ledger or the live score.  Scoring sees no returns, so the test window could be fixed from data
coverage alone.  The return test runs once: a second run is refused, so the window and criteria cannot be retried after the result.
"""
import bisect
import csv
import gzip
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Set

import numpy as np

from terminal.qsf import open_prices, validate, validate_open, validate_pit

UNIVERSE = Path("reports") / "qsf" / "QSF_OOS_UNIVERSE.json"
REPORT = Path("reports") / "qsf" / "QSF_OOS_TEST.json"
SCORE_FIRST, SCORE_LAST = "2010-01-01", "2013-12-31"
HYPOTHESIS = ("LONG_TERM", "A", 252)
STRICT_FIRST, STRICT_LAST = "2011-03-01", "2012-12-31"
SECTOR_STAMPS = ["2013-01-01", "2013-07-01", "2014-01-01", "2014-07-01", "2015-01-01"]


def load_old(base: Path) -> Dict[str, Dict[str, Any]]:
    return json.loads((base / UNIVERSE).read_text(encoding="utf-8"))


def old_members(previous: Callable[[str], List[str]], keys: List[str], snaps: List[Set[str]], old: Dict[str, Dict[str, Any]]) -> Callable[[str], List[str]]:
    """Older names by the ticker they carried then.  A ticker now used by another company keeps its own column under an alias."""
    def members(day: str) -> List[str]:
        out = list(previous(day))
        if not out or day < keys[0] or day > open_prices.SOURCE_END:
            return out
        snap = snaps[bisect.bisect_right(keys, day) - 1]
        return out + [a for a, v in old.items() if v["ticker"] in snap and a not in out]
    return members


def prepare(base: Path, log=print) -> Dict[str, Any]:
    root = base / "data" / "qsf" / "research"
    u, old = validate_open.load_universe(base), load_old(base)
    tickers = set(u) | {v["ticker"] for v in old.values()}
    files = open_prices.read_archives(root / "open" / "pystock" / "repo.tar.gz", tickers)
    series = {t: open_prices.build_series([b[t] for b in files if t in b]) for t in u}
    series.update({a: open_prices.build_series([b[v["ticker"]] for b in files if v["ticker"] in b]) for a, v in old.items()})
    m = validate_open.merge_open(root / "prices_2008.npz", series, root / "prices_oos.npz")
    (root / "prices_oos_open.splits.json").write_text(json.dumps({t: s["splits"] for t, s in series.items() if s["splits"]}), encoding="utf-8")
    t0 = time.time()
    f = validate.download_facts({a: v["cik"] for a, v in old.items()}, root / "facts_oos", progress=lambda a, b: a % 10 == 0 and log(f"facts {a}/{b} {time.time() - t0:.0f}s"))
    by_ticker = validate_pit.fetch_sectors({v["ticker"] for v in old.values()}, stamps=SECTOR_STAMPS, log=log)
    sectors = {a: by_ticker[v["ticker"]] for a, v in old.items() if v["ticker"] in by_ticker}
    (root / "survivorship" / "sectors_oos.json").write_text(json.dumps(sectors, ensure_ascii=False, indent=0), encoding="utf-8")
    return {"merged": len(m["added"]), "facts": f, "sectors": len(sectors), "no_sector": [a for a in old if a not in sectors], "stopped": {t: s["stopped"] for t, s in series.items() if s["stopped"]}}


def _load(base: Path):
    root = base / "data" / "qsf" / "research"
    names = {**validate_open.load_universe(base), **load_old(base)}
    return root, names, validate_open.OpenPrices(root / "prices_oos.npz", names)


def score(base: Path, log=print) -> Dict[str, Any]:
    """Scores and how many were usable per date.  No return is computed here."""
    from terminal.lab.backtest import members_at
    u0 = validate._universe(base)
    root, names, px = _load(base)
    surv = root / "survivorship"
    with (surv / "hist_updated.csv").open(newline="", encoding="utf-8") as fh:
        keys, snaps = validate_pit.load_history(list(csv.reader(fh)))
    added = {str(k).upper().replace(".", "-"): v for k, v in json.loads((base / "data" / "lab" / "membership.json").read_text(encoding="utf-8"))["added"].items()}
    splits: Dict[str, Any] = {}
    for f in ("prices_2008.splits.json", "prices_oos_open.splits.json"):
        splits.update(json.loads((root / f).read_text(encoding="utf-8")))
    facts = {**validate_pit._facts(root / "facts"), **validate_pit._facts(root / "facts_recovered"), **validate_pit._facts(root / "facts_open"), **validate_pit._facts(root / "facts_oos")}
    sectors = {**u0["sectors"]}
    for f in ("sectors.json", "sectors_open.json", "sectors_oos.json"):
        sectors.update(json.loads((surv / f).read_text(encoding="utf-8")))
    previous = validate_open.open_members(validate_pit.members_fn(lambda day: members_at(u0["tickers"], added, day), keys, snaps), keys, snaps, validate_open.load_universe(base))
    members = old_members(previous, keys, snaps, load_old(base))
    t0 = time.time()
    recs = validate.score_dates(px, members, facts, sectors, splits, progress=lambda n, m, d, k: log(f"{n}/{m} {d} {k} stocks {time.time() - t0:.0f}s"), first=SCORE_FIRST, last=SCORE_LAST)
    with gzip.open(root / "scores_oos.json.gz", "wt", encoding="utf-8") as fh:
        json.dump({"dates": px.dates, "records": recs}, fh)
    return coverage(recs, px.dates, keys, snaps)


def coverage(recs: List[Dict[str, Any]], dates: List[str], keys: List[str], snaps: List[Set[str]]) -> Dict[str, Any]:
    key = "|".join(HYPOTHESIS[:2])
    by: Dict[int, List[Dict]] = {}
    for r in recs:
        by.setdefault(r["i"], []).append(r)
    return {dates[i]: {"members": len(snaps[bisect.bisect_right(keys, dates[i]) - 1]), "scored": len(g), "usable": sum(1 for r in g if r.get(key) is not None)} for i, g in sorted(by.items())}


def in_window(recs: List[Dict[str, Any]], dates: List[str], first: str, last: str) -> List[Dict[str, Any]]:
    return [r for r in recs if first <= dates[r["i"]] <= last]


def test_once(base: Path, log=print) -> Dict[str, Any]:
    out = base / REPORT
    if out.exists():
        raise RuntimeError("독립 시험은 한 번만 실행합니다. 이미 결과가 있습니다.")
    root, _, px = _load(base)
    with gzip.open(root / "scores_oos.json.gz", "rt", encoding="utf-8") as fh:
        d = json.load(fh)
    strategy, variant, h = HYPOTHESIS
    strict = validate.analyze(px, in_window(d["records"], d["dates"], STRICT_FIRST, STRICT_LAST))
    extended = validate.analyze(px, in_window(d["records"], d["dates"], STRICT_FIRST, SCORE_LAST))
    name = f"{strategy}|{variant}|{h}"
    primary = {"hypothesis": name, **strict["tables"][name], **validate.verdict(strict["tables"][name])}
    result = {"status": "REAL", "protocol": "reports/QSF_OOS_TEST_PROTOCOL.md", "primary": primary, "strict": {"tables": strict["tables"], "buckets": strict["buckets"]},
              "extended_reference": {"tables": extended["tables"], "buckets": extended["buckets"]}}
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result
