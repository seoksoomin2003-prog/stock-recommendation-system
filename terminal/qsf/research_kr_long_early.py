"""One confirmation run of the live Korean long score on dates before the live replay.  Rules: reports/QSF_KR_LONG_EARLY_PROTOCOL.md.

The replay's own code (``research_kr_live``) on evaluation days from 2016-04 whose returns end before the replay's first day.
``download`` and ``prepare`` read no return; ``run_once`` reads returns once and refuses a second run.
"""
import gzip
import json
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from terminal.qsf import research_kr_live as rl, validate

PROTOCOL = "reports/QSF_KR_LONG_EARLY_PROTOCOL.md"
REPORT = Path("reports") / "qsf" / "QSF_KR_LONG_EARLY.json"
SCORES = "scores_long_early.json.gz"
FIRST, BEFORE, LAST_EXIT = "2016-04-01", "2019-04-01", "2019-03-29"
PRIMARY = ("LONG_TERM", 252)
OTHERS = (("LONG_TERM", 63), ("LONG_TERM", 126), ("SWING", 20))


def eval_days(px: Any) -> List[int]:
    return [i for i in rl.eval_rows(px, FIRST) if px.dates[i] < BEFORE]


def ended(px: Any, by_i: Dict[int, List[Dict[str, Any]]], h: int) -> Dict[int, List[Dict[str, Any]]]:
    """Only the days whose h-session return has ended by LAST_EXIT."""
    return {i: g for i, g in by_i.items() if i + h < len(px.dates) and px.dates[i + h] <= LAST_EXIT}


def download(base: Path, log=print) -> Dict[str, Any]:
    px = rl.ensure_panel(Path(base), log)
    return rl.download(Path(base), log, rows=eval_days(px))


def prepare(base: Path, log=print) -> Dict[str, Any]:
    """Scores for every evaluation day, with what was filed by then.  Reads no return."""
    base = Path(base)
    px = rl.load_panel(base)
    st = rl._statements(base)
    rows = eval_days(px)
    recs: List[Dict[str, Any]] = []
    t0 = time.time()
    for n, i in enumerate(rows, 1):
        day = rl.score_day(px, i, st)
        recs.extend(day)
        if n % 5 == 0 or n == len(rows):
            log(f"scores {n}/{len(rows)} {px.dates[i]} {len(day)} stocks {time.time() - t0:.0f}s")
    with gzip.open(base / rl.DATA / SCORES, "wt", encoding="utf-8") as fh:
        json.dump({"rows": rows, "first": px.dates[rows[0]], "last": px.dates[rows[-1]], "records": recs}, fh)
    by_year: Dict[str, List[bool]] = {}
    for r in recs:
        by_year.setdefault(px.dates[r["i"]][:4], []).append(r.get("fund_status") in ("REAL", "STALE"))
    return {"status": "REAL", "days": len(rows), "first": px.dates[rows[0]], "last": px.dates[rows[-1]], "records": len(recs),
            "scored_share": {s: float(np.mean([s in r for r in recs])) for s in rl.HORIZONS}, "fund_real_share_by_year": {y: round(float(np.mean(v)), 3) for y, v in sorted(by_year.items())}}


def word(a: bool, b: bool) -> str:
    return "CONFIRMED_RANK_AND_MONEY" if a and b else "CONFIRMED_RANK_ONLY" if a else "NOT_CONFIRMED"


def evaluate(px: Any, recs: List[Dict[str, Any]]) -> Dict[str, Any]:
    view = rl._View(px)
    by_i: Dict[int, List[Dict[str, Any]]] = {}
    for r in recs:
        by_i.setdefault(r["i"], []).append(r)

    def block(key: str, h: int) -> Dict[str, Any]:
        t = rl.tables(view, ended(px, by_i, h), key, h)
        return {**t, "condition_a": validate.verdict(t) if t.get("dates") else {"verdict": "NO_EVIDENCE", "checks": {}}}
    money = {s: rl.money(view, ended(px, by_i, rl.STEP), s) for s in rl.HORIZONS}
    key, h = PRIMARY
    main = block(key, h)
    a = main["condition_a"]["verdict"] == "WEAK_POSITIVE_EVIDENCE"
    others = {f"{k}|{x}": block(k, x) for k, x in OTHERS}
    domains = {f"{k}|{d}|{x}": rl.tables(view, ended(px, by_i, x), f"{k}|{d}", x) for k, x in (PRIMARY, ("LONG_TERM", 63), ("SWING", 20)) for d in rl.DOMAINS}
    return {"primary": {"strategy": key, "horizon": h, **main, "condition_b": money[key]["passed"], "reading": word(a, money[key]["passed"])},
            "others": others, "money": money, "domains": domains}


def run_once(base: Path, log=print) -> Dict[str, Any]:
    base = Path(base)
    out = base / REPORT
    if out.exists():
        raise RuntimeError("이 시험은 한 번만 실행합니다. 이미 결과가 있습니다.")
    path = base / rl.DATA / SCORES
    if not path.exists():
        raise RuntimeError("먼저 kr-long-early-prepare 를 실행하세요.")
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        stored = json.load(fh)
    px = rl.load_panel(base)
    res = {"status": "REAL", "protocol": PROTOCOL, "first": stored["first"], "last": stored["last"], "days": len(stored["rows"]), "last_exit": LAST_EXIT, **evaluate(px, stored["records"])}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    log(f"long score 2016-2019: {res['primary']['reading']}")
    return res
