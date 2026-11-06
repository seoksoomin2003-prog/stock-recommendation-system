"""Pre-registered rerun of the QSF historical check with demoted names that Yahoo still carries.
Criteria: reports/QSF_PIT_VALIDATION_PROTOCOL.md.

Research only: it never touches the ledger or the live score, and takes no parameters to search.  Inputs and scores stay in
data/qsf/research/ (git-ignored); the report goes to reports/qsf/QSF_PIT_VALIDATION.json.
"""
import bisect
import csv
import gzip
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
import requests

from terminal import sources
from terminal.qsf import validate

RECOVERED = tuple("""AAL AAP AIV ALK AMG AMTM AN ATI AYI BBWI BHF BIO BLDR BWA CAG CCEP CE CLF CNX COTY
CPB CPRI CTVA CZR DXC EMN ENPH EPAM ETSY FCPT FLR FLS FMC FOSL GHC GME GNW GT HOG HP
HRB IPGP JEF KMX KSS LKQ LNC LUMN LW M MAC MAT MHK MKTX MOH MTCH MUR NBR NKTR NOV
NWL OGN OI PAYC PBI PENN POOL PRGO PVH R RHI RIG RRC SEDG SIG SLG SLM SOLS TAP TDC
TFX THC TRIP TTD UA UAA UNM URBN VFC VNO VNT WHR WU XRAY ZION""".split())
GICS = {"Industrials": "Industrials", "Financials": "Financials", "Information Technology": "Information Technology", "Health Care": "Health Care",
        "Consumer Discretionary": "Consumer Discretionary", "Consumer Staples": "Consumer Staples", "Utilities": "Utilities", "Real Estate": "Real Estate",
        "Materials": "Materials", "Energy": "Energy", "Communication Services": "Communication Services",
        "Telecommunication Services": "Communication Services", "Telecommunications Services": "Communication Services"}
WIKI_API = "https://en.wikipedia.org/w/api.php"
LIMITS = ["파산·인수된 종목은 무료 가격이 없어 빠졌습니다. 생존 편향이 해결된 것이 아닙니다.", "복구 종목은 아직 상장된 강등 종목뿐이라 표본에 새로운 치우침이 있습니다.",
          "섹터는 현재 또는 마지막 확인 분류를 과거에도 적용했습니다.", "시장 국면과 이벤트·지배구조 영역은 시점 기준 이력이 없어 빠졌습니다.",
          "지수 구성 이력은 공식 S&P 자료가 아닙니다.", "장기 252거래일의 독립 표본은 약 12개뿐입니다.", "표본 대부분이 지난 검증과 겹쳐 독립된 새 증거가 아닙니다."]


# ---------------------------------------------------------------------- membership
def load_history(rows: Iterable[List[str]]) -> Tuple[List[str], List[set]]:
    """Public snapshots ``date, "A,B,C"`` in date order; tickers use the dash form of the rest of the system."""
    parsed = sorted((r[0], {x.strip().upper().replace(".", "-") for x in ",".join(r[1:]).strip('"').split(",") if x.strip()}) for r in rows if r and r[0][:2] in ("19", "20"))
    return [d for d, _ in parsed], [s for _, s in parsed]


def members_fn(base_members: Callable[[str], List[str]], keys: List[str], snaps: List[set], recovered: Iterable[str] = RECOVERED) -> Callable[[str], List[str]]:
    """Existing names by their join date, recovered names only while the latest snapshot on or before ``day`` lists them.
    Nothing is evaluated after the last snapshot, where membership is no longer known."""
    rec = list(recovered)

    def members(day: str) -> List[str]:
        if not keys or day > keys[-1] or day < keys[0]:
            return []
        snap = snaps[bisect.bisect_right(keys, day) - 1]
        return list(base_members(day)) + [t for t in rec if t in snap]
    return members


# ---------------------------------------------------------------------- inputs
def sector_of_row(row: str) -> Optional[str]:
    """GICS sector of one wikitext table row, using the sector names themselves."""
    for cell in re.split(r"\|\||\n\|", row):
        name = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", cell).strip()
        if name in GICS:
            return GICS[name]
    return None


def row_ticker(row: str) -> Optional[str]:
    m = re.search(r"\{\{\s*(?:NYSE|NASDAQ|Nasdaq|NyseSymbol|NasdaqSymbol|BZX|Cboe)[^|}]*\|\s*(?:symbol\s*=\s*)?([A-Za-z.\-]+)\s*\}\}", row)
    return m.group(1).upper().replace(".", "-") if m else None


def fetch_sectors(wanted: Iterable[str], stamps: Optional[List[str]] = None, http=requests, pause: float = 4.0, log=print) -> Dict[str, str]:
    """The sector a ticker last showed in Wikipedia's table.  A failed revision is logged and skipped; a missing sector stays missing."""
    want, out = set(wanted), {}
    for ts in stamps or [f"{y}-{m}-01" for y in range(2014, 2027) for m in ("01", "07")]:
        time.sleep(pause)
        try:
            r = http.get(WIKI_API, params={"action": "query", "prop": "revisions", "titles": "List of S&P 500 companies", "rvlimit": 1, "rvdir": "older", "rvstart": ts + "T00:00:00Z",
                                           "rvprop": "content", "rvslots": "main", "format": "json", "formatversion": 2}, headers={"User-Agent": sources.GENERIC_UA}, timeout=40)
            text = r.json()["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
        except Exception as exc:
            log(f"sector revision {ts}: {type(exc).__name__}")
            continue
        for row in re.split(r"\n\|-", text):
            t, s = row_ticker(row), sector_of_row(row)
            if t in want and s:
                out[t] = s
    return out


def merge_prices(base_path: Path, extra_path: Path, out_path: Path) -> Dict[str, Any]:
    """Recovered columns placed on the existing date axis.  Each series keeps its own adjustment basis; only within-series ratios are used."""
    a, b = np.load(base_path, allow_pickle=False), np.load(extra_path, allow_pickle=False)
    dates = [str(d) for d in a["dates"]]
    pos = {d: i for i, d in enumerate(dates)}
    rows = [(pos[str(d)], k) for k, d in enumerate(b["dates"]) if str(d) in pos]
    to, frm = [r[0] for r in rows], [r[1] for r in rows]
    fresh = [str(s) for s in b["symbols"] if str(s) not in {str(x) for x in a["symbols"]}]
    keep = [j for j, s in enumerate(b["symbols"]) if str(s) in set(fresh)]
    data = {}
    for f in validate.FIELDS:
        extra = np.full((len(dates), len(keep)), np.nan)
        extra[to] = b[f][frm][:, keep]
        data[f] = np.concatenate([a[f], extra], axis=1)
    tmp = out_path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, dates=a["dates"], symbols=np.array([str(s) for s in a["symbols"]] + fresh), **data)
    tmp.replace(out_path)
    return {"added": fresh, "dates": len(dates)}


def prepare(base: Path, log=print) -> Dict[str, Any]:
    root = base / "data" / "qsf" / "research"
    surv = root / "survivorship"
    classified = json.loads((surv / "classified.json").read_text(encoding="utf-8"))
    t0 = time.time()
    p = validate.download_prices(list(RECOVERED), root / "prices_recovered.npz", progress=lambda a, b: log(f"prices {a}/{b} {time.time() - t0:.0f}s"))
    m = merge_prices(root / "prices15y.npz", root / "prices_recovered.npz", root / "prices15y_pit.npz")
    f = validate.download_facts({t: classified[t]["cik"] for t in RECOVERED}, root / "facts_recovered", progress=lambda a, b: a % 25 == 0 and log(f"facts {a}/{b} {time.time() - t0:.0f}s"))
    sectors = fetch_sectors(RECOVERED, log=log)
    (surv / "sectors.json").write_text(json.dumps(sectors, ensure_ascii=False, indent=0), encoding="utf-8")
    return {"prices": p, "merged": len(m["added"]), "facts": f, "sectors": len(sectors), "no_sector": [t for t in RECOVERED if t not in sectors]}


# ---------------------------------------------------------------------- run
def coverage(recs: List[Dict[str, Any]], dates: List[str], keys: List[str], snaps: List[set]) -> Dict[str, Any]:
    """Evaluations per year and the scored share of the listed index, by count (renamed tickers are not mapped, so it is approximate)."""
    by: Dict[int, List[Dict]] = {}
    for r in recs:
        by.setdefault(r["i"], []).append(r)
    years: Dict[str, Dict[str, float]] = {}
    for i, g in by.items():
        y = years.setdefault(dates[i][:4], {"dates": 0, "evaluations": 0, "recovered": 0, "index": 0})
        y["dates"] += 1
        y["evaluations"] += len(g)
        y["recovered"] += sum(1 for r in g if r.get("recovered"))
        y["index"] += len(snaps[bisect.bisect_right(keys, dates[i]) - 1])
    return {k: {**v, "share_of_index": v["evaluations"] / v["index"]} for k, v in sorted(years.items())}


def _facts(folder: Path) -> Dict[str, Dict]:
    out = {}
    for f in sorted(folder.glob("*.json.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            out[f.name[:-8]] = json.load(fh)
    return out


def run(base: Path, log=print) -> Dict[str, Any]:
    from terminal.lab.backtest import members_at
    u = validate._universe(base)
    root = base / "data" / "qsf" / "research"
    surv = root / "survivorship"
    with (surv / "hist_updated.csv").open(newline="", encoding="utf-8") as fh:
        keys, snaps = load_history(list(csv.reader(fh)))
    added = json.loads((base / "data" / "lab" / "membership.json").read_text(encoding="utf-8"))["added"]
    added = {str(k).upper().replace(".", "-"): v for k, v in added.items()}
    px = validate.Prices(root / "prices15y_pit.npz")
    splits = json.loads((root / "prices15y.splits.json").read_text(encoding="utf-8"))
    splits.update(json.loads((root / "prices_recovered.splits.json").read_text(encoding="utf-8")))
    facts = {**_facts(root / "facts"), **_facts(root / "facts_recovered")}
    sectors = {**u["sectors"], **json.loads((surv / "sectors.json").read_text(encoding="utf-8"))}
    members = members_fn(lambda day: members_at(u["tickers"], added, day), keys, snaps)
    t0 = time.time()
    recs = validate.score_dates(px, members, facts, sectors, splits, progress=lambda n, m, d, k: log(f"{n}/{m} {d} {k} stocks {time.time() - t0:.0f}s"))
    rec_set = set(RECOVERED)
    for r in recs:
        r["recovered"] = r["t"] in rec_set
    with gzip.open(root / "scores_pit.json.gz", "wt", encoding="utf-8") as fh:
        json.dump({"dates": px.dates, "records": recs}, fh)
    result = validate.analyze(px, recs)
    base_only = validate.analyze(px, [r for r in recs if not r["recovered"]])
    result.update(status="REAL", model="QSF-1.2 candidate, point-in-time rerun (research only)", protocol="reports/QSF_PIT_VALIDATION_PROTOCOL.md", limitations=LIMITS,
                  evaluations=len(recs), recovered_evaluations=sum(1 for r in recs if r["recovered"]), recovered_names=len({r["t"] for r in recs if r["recovered"]}),
                  price_last=px.dates[-1], last_snapshot=keys[-1], coverage=coverage(recs, px.dates, keys, snaps), existing_names_only={"primary": base_only["primary"], "tables": base_only["tables"]})
    (base / "reports" / "qsf" / "QSF_PIT_VALIDATION.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result
