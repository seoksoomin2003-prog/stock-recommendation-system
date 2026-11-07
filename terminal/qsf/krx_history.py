"""Whole-market daily snapshots from the KRX Open API, kept for research under the git-ignored research_data/.

Every snapshot lists what traded that day, so a company that later delisted is still in it.  The key travels in a header and is
never written anywhere.  A day already stored is not asked again, so a stopped run continues where it ended.  Personal research only:
the KRX terms should be read before anything here is passed to anyone else.
"""
import gzip
import json
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

BASE = "https://data-dbg.krx.co.kr/svc/apis/sto/"
BOARDS = {"KOSPI": "stk_bydd_trd", "KOSDAQ": "ksq_bydd_trd"}
FIELDS = ("ISU_CD", "ISU_NM", "SECT_TP_NM", "TDD_OPNPRC", "TDD_HGPRC", "TDD_LWPRC", "TDD_CLSPRC", "FLUC_RT", "ACC_TRDVOL", "ACC_TRDVAL", "MKTCAP", "LIST_SHRS")
DAILY_CAP = 9500      # one key is reported to allow 10,000 calls a day; the rest stays free
REFUSED = (401, 403, 429, 503)


def weekdays(start: str, end: str) -> Iterable[str]:
    d, last = date.fromisoformat(start), date.fromisoformat(end)
    while d <= last:
        if d.weekday() < 5:
            yield d.isoformat()
        d += timedelta(days=1)


def path_of(root: Path, board: str, day: str) -> Path:
    return root / board / f"{day}.json.gz"


def listed_shares(root: Path, as_of: str, max_age_days: int = 10) -> Dict[str, float]:
    """Stock code to listed shares, from the newest day up to ``as_of`` with both boards.  A snapshot too old is not used."""
    end = date.fromisoformat(as_of)
    for back in range(max_age_days + 1):
        day = (end - timedelta(days=back)).isoformat()
        out: Dict[str, float] = {}
        for board in BOARDS:
            p = path_of(root, board, day)
            if not p.exists():
                out = {}
                break
            with gzip.open(p, "rt", encoding="utf-8") as fh:
                rows = json.load(fh)
            if not rows:
                out = {}
                break
            for r in rows:
                try:
                    out[r[0]] = float(str(r[FIELDS.index("LIST_SHRS")]).replace(",", ""))
                except (TypeError, ValueError):
                    continue
        if out:
            return out
    return {}


def slim(rows: List[Dict[str, Any]]) -> List[List[Any]]:
    return [[r.get(f) for f in FIELDS] for r in rows]


def download(root: Path, key: str, get: Callable[..., Any], start: str, end: str, sleep: Callable[[float], None] = time.sleep, cap: int = DAILY_CAP, pause: float = 0.2, log=print, keep_empty_before: Optional[str] = None) -> Dict[str, Any]:
    """Stops at once on a refusal.  An empty answer is a day without trading and is stored, so it is not asked twice.  From
    ``keep_empty_before`` on, an empty answer may be a day not published yet, so it is left to be asked again."""
    calls = stored = empty = 0
    stopped: Optional[str] = None
    fails = 0
    for day in reversed(list(weekdays(start, end))):        # newest first: a cut-off run still leaves the recent years
        for board, api in BOARDS.items():
            p = path_of(root, board, day)
            if p.exists():
                continue
            if calls >= cap:
                stopped = "DAILY_CAP"
                break
            calls += 1
            try:
                r = get(BASE + api, params={"basDd": day.replace("-", "")}, headers={"AUTH_KEY": key}, timeout=60)
            except Exception as exc:
                fails += 1
                log(f"{day} {board} {type(exc).__name__}")
                if fails >= 10:
                    stopped = "TOO_MANY_FAILURES"
                    break
                sleep(5)
                continue
            if r.status_code in REFUSED:
                stopped = f"REFUSED_{r.status_code}"
                break
            if r.status_code != 200:
                fails += 1
                log(f"{day} {board} HTTP {r.status_code}")
                if fails >= 10:
                    stopped = "TOO_MANY_FAILURES"
                    break
                sleep(5)
                continue
            fails = 0
            rows = slim(r.json().get("OutBlock_1") or [])
            if not rows and keep_empty_before and day >= keep_empty_before:
                sleep(pause)
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            with gzip.open(tmp, "wt", encoding="utf-8") as fh:
                json.dump(rows, fh, ensure_ascii=False)
            tmp.replace(p)
            stored += 1 if rows else 0
            empty += 0 if rows else 1
            if calls % 200 == 0:
                log(f"{day} calls={calls} stored={stored} empty={empty}")
            sleep(pause)
        if stopped:
            break
    return {"status": "STOPPED" if stopped else "DONE", "stopped": stopped, "calls": calls, "stored": stored, "empty": empty}
