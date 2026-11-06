"""Past checks recomputed with the corrected annual figures.  Rules: reports/QSF_CORRECTED_RECHECK_PROTOCOL.md.

Research only: never touches the ledger or the live score, and leaves earlier facts and reports in place.  Only the filings input
changes.  Each recheck runs once; development rechecks never compute a return from the test period.
"""
import csv
import gzip
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

import numpy as np

from terminal import sources
from terminal.qsf import fundamentals, pit, research_score, research_swing, validate, validate_oos, validate_open, validate_pit

FOLDER = "facts_corrected"
PROTOCOL = "reports/QSF_CORRECTED_RECHECK_PROTOCOL.md"
ALIASES = Path("reports") / "qsf" / "QSF_INSIDER_CIK_ALIASES.json"
REPORTS = {k: Path("reports") / "qsf" / f"QSF_CORRECTED_{k}.json" for k in ("OPEN", "OOS", "RESEARCH", "SWING")}


# ---------------------------------------------------------------------- filings
def company_numbers(base: Path) -> Dict[str, str]:
    """Every name used by the earlier checks, with the same precedence those checks gave their folders."""
    root = base / "data" / "qsf" / "research"
    u = validate._universe(base)
    tickers = set(u["tickers"])
    out = {t: c for t, c in u["ciks"].items() if t in tickers}
    classified = json.loads((root / "survivorship" / "classified.json").read_text(encoding="utf-8"))
    out.update({t: classified[t]["cik"] for t in validate_pit.RECOVERED})
    out.update({t: v["cik"] for t, v in validate_open.load_universe(base).items()})
    out.update({t: v["cik"] for t, v in validate_oos.load_old(base).items()})
    return out


def older_numbers(base: Path) -> Dict[str, List[str]]:
    table = json.loads((base / ALIASES).read_text(encoding="utf-8"))
    out = {t: [str(c) for c in v] for t, v in table.items()}
    for t, v in sources.CIK_PREDECESSORS.items():
        out[t] = sorted(set(out.get(t, [])) | set(v))
    return out


def joined_facts(cik: str, older: List[str], fetch: Callable[[str], Dict]) -> Dict[str, Any]:
    """A failed older fetch raises: a thin record is never saved."""
    facts = fetch(cik)
    for c in older:
        if str(int(c)) != str(int(cik)):
            facts = sources.merge_companyfacts(facts, fetch(c))
    return facts


def prepare(base: Path, log=print, fetch=None) -> Dict[str, Any]:
    fetch = fetch or sources.sec_companyfacts
    folder = base / "data" / "qsf" / "research" / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    numbers, older = company_numbers(base), older_numbers(base)
    failed, t0 = [], time.time()
    for n, (t, cik) in enumerate(sorted(numbers.items()), 1):
        f = folder / f"{t}.json.gz"
        if not f.exists():
            try:
                facts = joined_facts(cik, older.get(t, []), fetch)
                tmp = f.with_suffix(".tmp")
                with gzip.open(tmp, "wt", encoding="utf-8") as out:
                    json.dump({"annual": fundamentals.extract_us(facts), "full": pit.extract_full(facts)}, out)
                tmp.replace(f)
            except Exception as exc:
                failed.append((t, type(exc).__name__))
        if n % 50 == 0:
            log(f"facts {n}/{len(numbers)} {time.time() - t0:.0f}s")
    return {"companies": len(numbers), "failed": failed}


def load_facts(root: Path) -> Dict[str, Dict]:
    return validate_pit._facts(root / FOLDER)


# ---------------------------------------------------------------------- the point-in-time reading
def as_of_annual(annual: Dict[str, List[Dict]], as_of: str) -> Dict[str, List[Dict]]:
    """What was on file that day, with series that had stopped by then emptied.  A later filing never decides it."""
    return fundamentals.drop_stale_series({k: [r for r in v if r["filed"] <= as_of] for k, v in annual.items()})


def ttm_view(full: Dict[str, List[Dict]], as_of: str, splits: pit.Splits) -> Dict[str, List[Dict]]:
    return pit.with_ttm_eps(pit.adjust_shares(fundamentals.drop_stale_series(pit.ttm_view(full, as_of)), as_of, splits))


def fund_views(rec: Dict[str, Any], close: float, splits: pit.Splits, as_of: str, is_financial: bool) -> Dict[str, Dict[str, Any]]:
    raw = validate._raw_close(close, splits, as_of)
    a = fundamentals.metrics(pit.adjust_shares(as_of_annual(rec["annual"], as_of), as_of, splits), raw, as_of, is_financial=is_financial, source="SEC 10-K (시점 기준, 수정 읽기)")
    b = fundamentals.metrics(ttm_view(rec["full"], as_of, splits), raw, as_of, is_financial=is_financial, source="SEC 10-K·10-Q TTM (시점 기준, 수정 읽기)")
    return {"A": a, "B": b}


def _guard(base: Path, key: str) -> Path:
    out = base / REPORTS[key]
    if out.exists():
        raise RuntimeError("재계산은 한 번만 실행합니다. 이미 결과가 있습니다.")
    return out


def _write(out: Path, result: Dict[str, Any]) -> Dict[str, Any]:
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def _history(root: Path):
    with (root / "survivorship" / "hist_updated.csv").open(newline="", encoding="utf-8") as fh:
        return validate_pit.load_history(list(csv.reader(fh)))


def _added(base: Path) -> Dict[str, Any]:
    d = json.loads((base / "data" / "lab" / "membership.json").read_text(encoding="utf-8"))["added"]
    return {str(k).upper().replace(".", "-"): v for k, v in d.items()}


# ---------------------------------------------------------------------- rechecks
def run_open(base: Path, log=print) -> Dict[str, Any]:
    from terminal.lab.backtest import members_at
    out = _guard(base, "OPEN")
    root = base / "data" / "qsf" / "research"
    u0, names = validate._universe(base), validate_open.load_universe(base)
    keys, snaps = _history(root)
    added = _added(base)
    px = validate_open.OpenPrices(root / "prices15y_open.npz", names)
    splits: Dict[str, Any] = {}
    for f in ("prices15y.splits.json", "prices_recovered.splits.json", "prices_open.splits.json"):
        splits.update(json.loads((root / f).read_text(encoding="utf-8")))
    sectors = {**u0["sectors"], **json.loads((root / "survivorship" / "sectors.json").read_text(encoding="utf-8")), **json.loads((root / "survivorship" / "sectors_open.json").read_text(encoding="utf-8"))}
    previous = validate_pit.members_fn(lambda day: members_at(u0["tickers"], added, day), keys, snaps)
    t0 = time.time()
    recs = validate.score_dates(px, validate_open.open_members(previous, keys, snaps, names), load_facts(root), sectors, splits, progress=lambda n, m, d, k: log(f"open {n}/{m} {d} {k} {time.time() - t0:.0f}s"), views=fund_views)
    with gzip.open(root / "scores_corrected_open.json.gz", "wt", encoding="utf-8") as fh:
        json.dump({"dates": px.dates, "records": recs}, fh)
    result = validate.analyze(px, recs)
    result.update(status="REAL", protocol=PROTOCOL, evaluations=len(recs), note="같은 표본의 재계산이며 독립된 새 증거가 아닙니다.")
    return _write(out, result)


def run_oos(base: Path, log=print) -> Dict[str, Any]:
    """The earlier hypothesis, window and criteria.  Its original report and one-shot guard stay as they are."""
    from terminal.lab.backtest import members_at
    out = _guard(base, "OOS")
    u0 = validate._universe(base)
    root, _, px = validate_oos._load(base)
    keys, snaps = _history(root)
    added = _added(base)
    splits: Dict[str, Any] = {}
    for f in ("prices_2008.splits.json", "prices_oos_open.splits.json"):
        splits.update(json.loads((root / f).read_text(encoding="utf-8")))
    sectors = dict(u0["sectors"])
    for f in ("sectors.json", "sectors_open.json", "sectors_oos.json"):
        sectors.update(json.loads((root / "survivorship" / f).read_text(encoding="utf-8")))
    previous = validate_open.open_members(validate_pit.members_fn(lambda day: members_at(u0["tickers"], added, day), keys, snaps), keys, snaps, validate_open.load_universe(base))
    members = validate_oos.old_members(previous, keys, snaps, validate_oos.load_old(base))
    t0 = time.time()
    recs = validate.score_dates(px, members, load_facts(root), sectors, splits, progress=lambda n, m, d, k: log(f"oos {n}/{m} {d} {k} {time.time() - t0:.0f}s"), first=validate_oos.SCORE_FIRST, last=validate_oos.SCORE_LAST, views=fund_views)
    with gzip.open(root / "scores_corrected_oos.json.gz", "wt", encoding="utf-8") as fh:
        json.dump({"dates": px.dates, "records": recs}, fh)
    strategy, variant, h = validate_oos.HYPOTHESIS
    name = f"{strategy}|{variant}|{h}"
    strict = validate.analyze(px, validate_oos.in_window(recs, px.dates, validate_oos.STRICT_FIRST, validate_oos.STRICT_LAST))
    return _write(out, {"status": "REAL", "protocol": PROTOCOL, "primary": {"hypothesis": name, **strict["tables"][name], **validate.verdict(strict["tables"][name])}, "tables": strict["tables"],
                        "note": "이미 사용한 구간의 재계산이며 독립 시험이 아닙니다."})


def run_research(base: Path, log=print) -> Dict[str, Any]:
    out = _guard(base, "RESEARCH")
    u, root, px, splits, members = research_score._load(base)
    b = research_score.build_features(px, members, load_facts(root), u["sectors"], splits, progress=lambda n, m, d: n % 20 == 0 and log(f"research {n}/{m} {d}"), view_of=ttm_view)
    np.savez_compressed(root / "features_corrected.npz", rows=np.array(b["rows"]), tensor=b["tensor"])
    ranks = research_score.rank_tensor(b["tensor"], px.symbols, u["sectors"])
    res = {s: research_score.select(ranks, px, b["rows"], research_score.dev_rows(px, b["rows"], h), h) for s, h in research_score.HORIZON.items()}
    return _write(out, {"status": "DEVELOPED", "protocol": PROTOCOL, "strategies": res, "factors": list(research_score.FACTORS), "note": "개발 구간만 계산했습니다. 시험 구간 수익률은 계산하지 않았습니다."})


def run_swing(base: Path, log=print) -> Dict[str, Any]:
    out = _guard(base, "SWING")
    root, _, px = research_swing._load(base)
    facts = load_facts(root)
    t0 = time.time()
    b = research_swing.build_features(px, research_swing._members(base, root), {t: (r.get("full") or {}).get("net_income") or [] for t, r in facts.items()}, research_swing._sectors(base, root),
                                      progress=lambda n, m, d: n % 50 == 0 and log(f"swing {n}/{m} {d} {time.time() - t0:.0f}s"))
    np.savez_compressed(root / "swing_features_corrected.npz", rows=np.array(b["rows"]), tensor=b["tensor"])
    ranks = research_swing.rank_tensor(b["tensor"])
    res = {s: research_swing.select(ranks, px, b["rows"], research_swing.dev_rows(px, b["rows"], h), h) for s, h in research_swing.HORIZONS.items()}
    return _write(out, {"status": "DEVELOPED", "protocol": PROTOCOL, "strategies": res, "factors": list(research_swing.FACTORS), "note": "개발 구간만 계산했습니다. 시험 구간 수익률은 계산하지 않았습니다."})
