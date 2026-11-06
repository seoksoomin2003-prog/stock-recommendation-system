"""Pre-registered rerun that adds names found in the open pystock-data archive.  Criteria: reports/QSF_OPEN_VALIDATION_PROTOCOL.md.

Research only: it never touches the ledger or the live score, and takes no parameters to search.  Derived prices stay in
data/qsf/research/ (git-ignored); the report goes to reports/qsf/QSF_OPEN_VALIDATION.json.
"""
import csv
import gzip
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set

import numpy as np

from terminal.qsf import open_prices, validate, validate_pit

UNIVERSE = Path("reports") / "qsf" / "QSF_OPEN_UNIVERSE.json"
SAME_COMPANY = {"KORS": "CPRI", "CTL": "LUMN", "LB": "BBWI"}       # one company under two tickers: the Yahoo series wins when both are listed
LIMITS = ["pystock 종목의 가격은 2017-03-31까지만 있어, 그 뒤 구간의 빈 종목은 그대로입니다.", "2017년 이후의 파산·인수 종목은 대부분 빠져 생존 편향이 해결된 것이 아닙니다.",
          "표본 대부분이 이전 검증과 겹쳐 독립된 새 증거가 아닙니다.", "섹터는 현재 또는 마지막 확인 분류를 과거에도 적용했습니다.",
          "시장 국면과 이벤트·지배구조 영역은 시점 기준 이력이 없어 빠졌습니다.", "지수 구성 이력은 공식 S&P 자료가 아닙니다.", "장기 252거래일의 독립 표본은 약 12개뿐입니다."]


def load_universe(base: Path) -> Dict[str, Dict[str, Any]]:
    return json.loads((base / UNIVERSE).read_text(encoding="utf-8"))


class OpenPrices(validate.Prices):
    """Forward returns for archive names: nothing past the archive's end, and an exit before it is valued at its last close."""

    def __init__(self, path: Path, open_names: Iterable[str]):
        super().__init__(path)
        self.open_cols = [self.col[t] for t in open_names if t in self.col]
        self.early_only = False

    def forward(self, i: int, h: int, cost: float = 0.0) -> np.ndarray:
        out = super().forward(i, h, cost)
        if i + h >= len(self.dates):
            return out
        ended = self.dates[i + h] > open_prices.SOURCE_END
        if ended and self.early_only:
            return np.full(len(self.symbols), np.nan)
        d = self.data
        for j in self.open_cols:
            if ended:
                out[j] = np.nan
            elif out[j] != out[j] and d["close"][i + 1, j] == d["close"][i + 1, j] and d["open"][i + 1, j] == d["open"][i + 1, j]:
                path = d["adj_close"][i + 1:i + h + 1, j]
                seen = path[np.isfinite(path)]
                if len(seen):
                    out[j] = seen[-1] / (d["open"][i + 1, j] * d["adj_close"][i + 1, j] / d["close"][i + 1, j]) - 1 - cost
        return out


def open_members(previous: Callable[[str], List[str]], keys: List[str], snaps: List[Set[str]], names: Iterable[str]) -> Callable[[str], List[str]]:
    """Archive names are added while the latest snapshot lists them, up to the archive's end, one ticker per company."""
    import bisect
    rec = list(names)

    def members(day: str) -> List[str]:
        out = list(previous(day))
        if not out or day > open_prices.SOURCE_END:
            return out
        snap = snaps[bisect.bisect_right(keys, day) - 1]
        return out + [t for t in rec if t in snap and SAME_COMPANY.get(t) not in snap]
    return members


def merge_open(base_path: Path, series: Dict[str, Dict[str, Any]], out_path: Path) -> Dict[str, Any]:
    """Archive columns on the existing date axis.  A date the axis lacks is dropped; a missing day stays empty."""
    a = np.load(base_path, allow_pickle=False)
    dates = [str(d) for d in a["dates"]]
    pos = {d: i for i, d in enumerate(dates)}
    have = {str(s) for s in a["symbols"]}
    names = [t for t in sorted(series) if t not in have and series[t]["rows"]]
    extra = {f: np.full((len(dates), len(names)), np.nan) for f in validate.FIELDS}
    for j, t in enumerate(names):
        for r in series[t]["rows"]:
            i = pos.get(r["date"])
            if i is None:
                continue
            for f in validate.FIELDS:
                if r.get(f) is not None:
                    extra[f][i, j] = r[f]
    tmp = out_path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, dates=a["dates"], symbols=np.array([str(s) for s in a["symbols"]] + names), **{f: np.concatenate([a[f], extra[f]], axis=1) for f in validate.FIELDS})
    tmp.replace(out_path)
    return {"added": names}


def prepare(base: Path, log=print) -> Dict[str, Any]:
    root = base / "data" / "qsf" / "research"
    u = load_universe(base)
    files = open_prices.read_archives(root / "open" / "pystock" / "repo.tar.gz", u)
    series = {t: open_prices.build_series([b[t] for b in files if t in b]) for t in u}
    m = merge_open(root / "prices15y_pit.npz", series, root / "prices15y_open.npz")
    (root / "prices_open.splits.json").write_text(json.dumps({t: s["splits"] for t, s in series.items() if s["splits"]}), encoding="utf-8")
    t0 = time.time()
    f = validate.download_facts({t: v["cik"] for t, v in u.items()}, root / "facts_open", progress=lambda a, b: a % 25 == 0 and log(f"facts {a}/{b} {time.time() - t0:.0f}s"))
    sectors = validate_pit.fetch_sectors(u, log=log)
    (root / "survivorship" / "sectors_open.json").write_text(json.dumps(sectors, ensure_ascii=False, indent=0), encoding="utf-8")
    return {"merged": len(m["added"]), "missing": [t for t in u if t not in m["added"]], "facts": f, "sectors": len(sectors), "no_sector": [t for t in u if t not in sectors],
            "gaps": sum(s["gaps"] for s in series.values()), "stopped": {t: s["stopped"] for t, s in series.items() if s["stopped"]}}


def run(base: Path, log=print) -> Dict[str, Any]:
    from terminal.lab.backtest import members_at
    u0 = validate._universe(base)
    names = load_universe(base)
    root = base / "data" / "qsf" / "research"
    surv = root / "survivorship"
    with (surv / "hist_updated.csv").open(newline="", encoding="utf-8") as fh:
        keys, snaps = validate_pit.load_history(list(csv.reader(fh)))
    added = json.loads((base / "data" / "lab" / "membership.json").read_text(encoding="utf-8"))["added"]
    added = {str(k).upper().replace(".", "-"): v for k, v in added.items()}
    px = OpenPrices(root / "prices15y_open.npz", names)
    splits: Dict[str, Any] = {}
    for f in ("prices15y.splits.json", "prices_recovered.splits.json", "prices_open.splits.json"):
        splits.update(json.loads((root / f).read_text(encoding="utf-8")))
    facts = {**validate_pit._facts(root / "facts"), **validate_pit._facts(root / "facts_recovered"), **validate_pit._facts(root / "facts_open")}
    sectors = {**u0["sectors"], **json.loads((surv / "sectors.json").read_text(encoding="utf-8")), **json.loads((surv / "sectors_open.json").read_text(encoding="utf-8"))}
    previous = validate_pit.members_fn(lambda day: members_at(u0["tickers"], added, day), keys, snaps)
    t0 = time.time()
    recs = validate.score_dates(px, open_members(previous, keys, snaps, names), facts, sectors, splits, progress=lambda n, m, d, k: log(f"{n}/{m} {d} {k} stocks {time.time() - t0:.0f}s"))
    for r in recs:
        r["open"] = r["t"] in names
        r["recovered"] = r["t"] in validate_pit.RECOVERED or r["open"]
    with gzip.open(root / "scores_open.json.gz", "wt", encoding="utf-8") as fh:
        json.dump({"dates": px.dates, "records": recs}, fh)
    result = validate.analyze(px, recs)
    without = [r for r in recs if not r["open"]]
    previous_only = validate.analyze(px, without)
    px.early_only = True
    early_all, early_without = validate.analyze(px, recs), validate.analyze(px, without)
    px.early_only = False
    keep = lambda a: {"primary": a["primary"], "tables": a["tables"]}      # noqa: E731
    result.update(status="REAL", model="QSF-1.2 candidate, open-archive rerun (research only)", protocol="reports/QSF_OPEN_VALIDATION_PROTOCOL.md", limitations=LIMITS,
                  evaluations=len(recs), open_evaluations=sum(1 for r in recs if r["open"]), open_names=len({r["t"] for r in recs if r["open"]}), recovered_evaluations=sum(1 for r in recs if r["t"] in validate_pit.RECOVERED),
                  price_last=px.dates[-1], source_end=open_prices.SOURCE_END, coverage=validate_pit.coverage(recs, px.dates, keys, snaps), without_open_names=keep(previous_only),
                  early_panel={"with_open_names": keep(early_all), "without_open_names": keep(early_without)})
    (base / "reports" / "qsf" / "QSF_OPEN_VALIDATION.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result
