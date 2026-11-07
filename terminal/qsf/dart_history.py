"""Main accounts of many Korean companies from OpenDART, kept for research under the git-ignored research_data/.

The company list keeps delisted names, so the set is not limited to survivors.  Each row carries a receipt number whose first eight
digits are the date it became public.  The key travels as a parameter and is never written: errors report the exception type only.
"""
import gzip
import io
import json
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

BASE = "https://opendart.fss.or.kr/api/"
REPORTS = {"Q1": "11013", "H1": "11012", "Q3": "11014", "FY": "11011"}
BATCH = 100           # the endpoint takes at most this many companies in one call
DAILY_CAP = 19000     # the guide states 20,000 a day
FIELDS = ("rcept_no", "corp_code", "stock_code", "fs_div", "sj_div", "account_nm", "thstrm_dt", "thstrm_amount", "thstrm_add_amount")
NO_DATA, LIMIT = "013", "020"
KEY_TROUBLE = {"010", "011", "012", "101", "901"}


def parse_corp_list(zip_bytes: bytes) -> Dict[str, str]:
    """Stock code to DART company code.  Companies without a stock code were never listed."""
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    root = ET.fromstring(z.read(z.namelist()[0]))
    return {s: c.findtext("corp_code") for c in root.iter("list") if (s := (c.findtext("stock_code") or "").strip())}


def batches(codes: Sequence[str], size: int = BATCH) -> Iterable[List[str]]:
    ordered = sorted(set(codes))
    for n in range(0, len(ordered), size):
        yield ordered[n:n + size]


def path_of(root: Path, year: int, report: str, n: int) -> Path:
    return root / f"{year}_{report}" / f"{n:03d}.json.gz"


def slim(rows: List[Dict[str, Any]]) -> List[List[Any]]:
    return [[r.get(f) for f in FIELDS] for r in rows]


def download(root: Path, key: str, get: Callable[..., Any], corp_codes: Sequence[str], years: Sequence[int], sleep: Callable[[float], None] = time.sleep, cap: int = DAILY_CAP, pause: float = 0.3, log=print) -> Dict[str, Any]:
    """A batch already stored is not asked again.  Stops at once on the daily limit or a key problem."""
    groups = list(batches(corp_codes))
    calls = stored = rows_seen = fails = missed = 0
    stopped: Optional[str] = None
    for year in years:
        for report, code in REPORTS.items():
            for n, group in enumerate(groups):
                p = path_of(root, year, report, n)
                if p.exists():
                    continue
                if calls >= cap:
                    return {"status": "STOPPED", "stopped": "DAILY_CAP", "calls": calls, "stored": stored, "rows": rows_seen}
                calls += 1
                try:
                    r = get(BASE + "fnlttMultiAcnt.json", params={"crtfc_key": key, "corp_code": ",".join(group), "bsns_year": year, "reprt_code": code}, timeout=60)
                    body = r.json()
                except Exception as exc:
                    fails += 1
                    missed += 1
                    log(f"{year} {report} {n} {type(exc).__name__}")
                    if fails >= 10:
                        return {"status": "STOPPED", "stopped": "TOO_MANY_FAILURES", "calls": calls, "stored": stored, "rows": rows_seen}
                    sleep(5)
                    continue
                state = str(body.get("status"))
                if state == LIMIT or state in KEY_TROUBLE:
                    stopped = f"DART_{state}"
                    return {"status": "STOPPED", "stopped": stopped, "calls": calls, "stored": stored, "rows": rows_seen}
                if state not in ("000", NO_DATA):
                    fails += 1
                    missed += 1
                    log(f"{year} {report} {n} DART {state}")
                    if fails >= 10:
                        return {"status": "STOPPED", "stopped": "TOO_MANY_FAILURES", "calls": calls, "stored": stored, "rows": rows_seen}
                    sleep(5)
                    continue
                fails = 0
                rows = slim(body.get("list") or [])
                p.parent.mkdir(parents=True, exist_ok=True)
                tmp = p.with_suffix(".tmp")
                with gzip.open(tmp, "wt", encoding="utf-8") as fh:
                    json.dump(rows, fh, ensure_ascii=False)
                tmp.replace(p)
                stored += 1
                rows_seen += len(rows)
                sleep(pause)
            log(f"{year} {report} calls={calls} rows={rows_seen}")
    return {"status": "INCOMPLETE" if missed else "DONE", "stopped": None, "calls": calls, "stored": stored, "rows": rows_seen, "missed": missed}
