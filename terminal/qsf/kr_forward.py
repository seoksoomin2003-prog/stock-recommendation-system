"""The Korean price score, written down every session and kept apart from the live score.  Rules: reports/QSF_KR_FORWARD_PROTOCOL.md.

A record is written once and chained by hash, so a later edit shows.  No return is computed while the record grows: the status reads
dates only, and the single evaluation is refused until enough sessions have matured.  Nothing here reads or changes the live score,
the QSF ledger or P6-11B.
"""
import fcntl
import gzip
import hashlib
import json
import os
from datetime import date, datetime, time as clock, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from terminal.qsf import config, krx_history as kh, research_ensemble as en, research_kr as kr, research_swing as rs, validate
from terminal.qsf.research_score import test_verdict

PROTOCOL = "reports/QSF_KR_FORWARD_PROTOCOL.md"
FOLDER = Path("research_data") / "krx_forward"
REPORT = Path("reports") / "qsf" / "QSF_KR_FORWARD.json"
FUND_FOLDER = Path("research_data") / "krx_forward_fund"
FUND_REPORT = Path("reports") / "qsf" / "QSF_KR_FORWARD_FUND.json"
DART_FORWARD = Path("research_data") / "dart" / "forward"
FUND_GROUPS = [["profitability", "value"], ["safety"], ["investment"], ["earnings_change"]]     # settled by the financial test
DART_YEARS_BACK = 4        # four quarters and the year before them, for the newest report
FIRST = "2026-11-06"       # the Korean test's data ends on 2026-11-05
GROUPS = [["momentum"], ["reversal"], ["low_risk"]]     # settled by the test, not worked out again
WINDOW = 420               # weekdays read back: more than the longest signal and the history condition need
WAIT_DAYS = 7              # an empty answer this recent may be a day not yet published
MIN_STOCKS = 30
HORIZON, STEP = 20, 5
MIN_INDEPENDENT = config.MIN_INDEPENDENT
KST = timezone(timedelta(hours=9))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def previous_weekday(day: date) -> date:
    d = day - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def next_open(session: str) -> datetime:
    """09:00 KST on the next weekday.  A holiday makes this earlier than the true open, so the flag can only understate."""
    d = date.fromisoformat(session) + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return datetime.combine(d, clock(9), KST)


def _rows_of(root: Path, day: str) -> Dict[str, List[Any]]:
    """Both boards with rows, or nothing: half a day is not a day."""
    out: Dict[str, List[Any]] = {}
    for board in kh.BOARDS:
        p = kh.path_of(root, board, day)
        if not p.exists():
            return {}
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            rows = json.load(fh)
        if not rows:
            return {}
        out[board] = rows
    return out


def available(root: Path, first: str, last: str) -> List[str]:
    return [d for d in kh.weekdays(first, last) if _rows_of(root, d)]


def score_day(root: Path, day: str) -> Dict[str, Any]:
    """Reads the files up to ``day`` and no later."""
    back = (date.fromisoformat(day) - timedelta(days=WINDOW * 7 // 5 + 7)).isoformat()
    days = list(kh.weekdays(back, day))[-WINDOW:]
    z = kr.build_prices(root, log=lambda m: None, days=days)
    i = len(z["dates"]) - 1
    if i < 0 or str(z["dates"][i]) != day:
        raise ValueError("NO_PRICES_FOR_DAY")
    m = list(z["symbols"]).index(kr.MARKET)
    ok = kr.eligible(z, i)
    f = rs.price_features(z, i, m)
    tensor = np.full((1, len(z["symbols"]), len(kr.SIGNALS)), np.nan, dtype=np.float32)
    for k, s in enumerate(kr.SIGNALS):
        tensor[0, ok, k] = f[s][ok]
    themes = kr.theme_ranks(tensor)
    final = en.combine(themes, GROUPS)[0]
    names = {r[kr.F["ISU_CD"]]: r[kr.F["ISU_NM"]] for rows in _rows_of(root, day).values() for r in rows}

    def val(x: Any) -> Optional[float]:
        v = float(x)
        return round(v, 3) if np.isfinite(v) else None
    rows = []
    for j in np.flatnonzero(ok):
        code = str(z["symbols"][j])
        rows.append({"code": code, "name": names.get(code), "board": "KOSPI" if z["kospi"][j] else "KOSDAQ", "score": val(final[j]),
                     **{t: val(themes[t][0, j] * 100) for t in kr.THEMES}, "cap": val(z["cap"][i, j]), "value": val(z["value"][i, j])})
    if sum(1 for r in rows if r["score"] is not None) < MIN_STOCKS:
        raise ValueError("TOO_FEW_SCORES")
    return {"session": day, "protocol": PROTOCOL, "groups": GROUPS, "rows": rows}


def score_fund_day(base: Path, day: str) -> Dict[str, Any]:
    """The financial score of ``day``: prices up to that day, and only figures received before it."""
    from terminal.qsf import research_kr_fund as rf
    root = Path(base) / kr.DATA
    back = (date.fromisoformat(day) - timedelta(days=WINDOW * 7 // 5 + 7)).isoformat()
    z = kr.build_prices(root, log=lambda m: None, days=list(kh.weekdays(back, day))[-WINDOW:])
    i = len(z["dates"]) - 1
    if i < 0 or str(z["dates"][i]) != day:
        raise ValueError("NO_PRICES_FOR_DAY")
    px = kr.KrPrices(z)
    tensor = rf.build_features(px, [i], rf.load_reports(Path(base) / DART_FORWARD), log=lambda m: None)
    themes = rf.theme_ranks(tensor)
    final = en.combine(themes, FUND_GROUPS)[0]
    names = {r[kr.F["ISU_CD"]]: r[kr.F["ISU_NM"]] for rows in _rows_of(root, day).values() for r in rows}

    def val(x: Any) -> Optional[float]:
        v = float(x)
        return round(v, 3) if np.isfinite(v) else None
    rows = []
    for j in np.flatnonzero(kr.eligible(z, i)):
        code = str(z["symbols"][j])
        rows.append({"code": code, "name": names.get(code), "board": "KOSPI" if z["kospi"][j] else "KOSDAQ", "score": val(final[j]),
                     **{f"theme_{t}": val(themes[t][0, j] * 100) for t in rf.THEMES}, "cap": val(z["cap"][i, j]), "traded": val(z["value"][i, j])})
    if sum(1 for r in rows if r["score"] is not None) < MIN_STOCKS:
        raise ValueError("TOO_FEW_SCORES")
    return {"session": day, "protocol": PROTOCOL, "groups": FUND_GROUPS, "rows": rows}


def refresh_dart(base: Path, key: str, get: Callable[..., Any], today: date, log=print, sleep=None) -> Dict[str, Any]:
    """This year's reports and last year's annual report are asked again, since new ones arrive.  Earlier years are asked once."""
    from terminal.qsf import dart_history as dh
    r = get(dh.BASE + "corpCode.xml", params={"crtfc_key": key}, timeout=120)
    corp = dh.parse_corp_list(r.content)
    root = Path(base) / kr.DATA
    stocks = set()
    for day in reversed(list(kh.weekdays((today - timedelta(days=14)).isoformat(), today.isoformat()))):
        rows = _rows_of(root, day)
        if rows:
            stocks = {x[kr.F["ISU_CD"]] for v in rows.values() for x in v if kr.common_stock(x[kr.F["ISU_CD"]], x[kr.F["ISU_NM"]], x[kr.F["SECT_TP_NM"]])}
            break
    codes = [corp[s] for s in stocks if s in corp]
    if not codes:
        return {"status": "STOPPED", "stopped": "NO_COMPANIES"}
    extra = {"sleep": sleep} if sleep else {}
    return dh.download(Path(base) / DART_FORWARD, key, get, codes, range(today.year - DART_YEARS_BACK, today.year + 1), log=log,
                       refresh=lambda y, rep: y == today.year or (y == today.year - 1 and rep == "FY"), **extra)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _index_rows(p: Path) -> Tuple[List[Dict[str, Any]], bool]:
    """(rows, torn).  A last line that cannot be parsed is an append cut short (full disk, power loss): it is left out, so the
    rows before it stay readable, and the caller is told.  An unreadable line anywhere else is not hidden."""
    if not p.exists():
        return [], False
    lines = [x for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    rows = []
    for n, line in enumerate(lines):
        try:
            rows.append(json.loads(line))
        except ValueError:
            if n == len(lines) - 1:
                return rows, True
            raise
    return rows, False


def read_index(base: Path, folder: Path = FOLDER) -> List[Dict[str, Any]]:
    return _index_rows(Path(base) / folder / "index.jsonl")[0]


def index_torn(base: Path, folder: Path = FOLDER) -> bool:
    return _index_rows(Path(base) / folder / "index.jsonl")[1]


def _append_index(folder: Path, day: str, recorded_at: str, late: bool, before_open: bool, stocks: int) -> None:
    rows = read_index(folder, Path("."))
    sha = _sha(folder / f"{day}.json.gz")
    chain = hashlib.sha256(((rows[-1]["chain"] if rows else "") + sha).encode()).hexdigest()
    with open(folder / "index.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"session": day, "recorded_at": recorded_at, "late": late, "before_next_open": before_open, "stocks": stocks, "sha256": sha, "chain": chain}) + "\n")
        fh.flush()
        os.fsync(fh.fileno())                       # the line is on the disk before the record counts as written


def _read_day(folder: Path, day: str) -> Dict[str, Any]:
    with gzip.open(folder / f"{day}.json.gz", "rt", encoding="utf-8") as fh:
        return json.load(fh)


def write_record(base: Path, day: str, at: datetime, late: bool, store: Path = FOLDER, scorer: Optional[Callable[[Path, str], Dict[str, Any]]] = None) -> bool:
    """Write-once.  A file left without its index line by a crash gets the line it was written with."""
    folder = Path(base) / store
    folder.mkdir(parents=True, exist_ok=True)
    # One writer at a time: a record command run by hand beside the daily job once could pass the "not written yet" check twice,
    # write the day twice and break the chain.
    with open(folder / "write.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rows, torn = _index_rows(folder / "index.jsonl")
        if torn:                                    # appending after a cut line would weld two lines into one for good
            raise RuntimeError(f"INDEX_TORN: {store}/index.jsonl ends in a cut line; it must be repaired before any new record")
        if day in {r["session"] for r in rows}:
            return False
        p = folder / f"{day}.json.gz"
        if not p.exists():
            scored = scorer(base, day) if scorer else score_fund_day(base, day) if store == FUND_FOLDER else score_day(Path(base) / kr.DATA, day)
            doc = {**scored, "recorded_at": at.isoformat(), "late": late, "before_next_open": at < next_open(day)}
            tmp = p.with_suffix(".tmp")
            with gzip.open(tmp, "wt", encoding="utf-8") as fh:
                json.dump(doc, fh, ensure_ascii=False)
            tmp.replace(p)
        doc = _read_day(folder, day)
        _append_index(folder, day, doc["recorded_at"], doc["late"], doc["before_next_open"], len(doc["rows"]))
        return True


def _record_fund(base: Path, have: List[str], at: datetime, key: Optional[str], get: Callable[..., Any], first: str, log, sleep) -> Dict[str, Any]:
    """The financial score of the days not yet written.  A failure here leaves the price record alone."""
    done = {r["session"] for r in read_index(base, FUND_FOLDER)}
    days = [d for d in have if d >= first]
    pending = [d for d in days if d not in done]
    if not pending:
        return {"status": "OK", "written": []}
    if not key:
        return {"status": "FAILED", "reason": "NO_DART_KEY", "written": []}
    try:
        got = refresh_dart(base, key, get, at.astimezone(KST).date(), log, sleep)
        if got.get("stopped"):
            return {"status": "FAILED", "reason": got["stopped"], "written": []}
        wrote = [d for d in pending if write_record(base, d, at, d != days[-1], FUND_FOLDER)]
    except Exception as exc:                # the type only: a message could carry the key
        return {"status": "FAILED", "reason": type(exc).__name__, "written": []}
    return {"status": "OK", "written": wrote}


def record(base: Path, key: Optional[str] = None, get: Optional[Callable[..., Any]] = None, now: Callable[[], datetime] = _utcnow, first: str = FIRST, log=print, sleep=None,
           dart_key: Optional[str] = None, dart_get: Optional[Callable[..., Any]] = None, events_get: Optional[Callable[..., Any]] = None) -> Dict[str, Any]:
    """OK: caught up to the previous weekday.  WAITING: that day is not published yet, or was a holiday; asked again at the next slot.
    A caller passing its own ``get`` without ``dart_get`` or ``events_get`` records the price score only."""
    live_run = get is None
    at = now()
    today = at.astimezone(KST).date()
    end = previous_weekday(today).isoformat()
    key = key if key is not None else os.environ.get("KRX_API_KEY")
    if not key:
        return {"status": "NO_KEY"}
    if get is None:
        import requests
        get = requests.get
    root = Path(base) / kr.DATA
    extra = {"sleep": sleep} if sleep else {}
    got = kh.download(root, key, get, first, end, keep_empty_before=(today - timedelta(days=WAIT_DAYS)).isoformat(), log=log, **extra)
    have = available(root, first, end)
    done = {r["session"] for r in read_index(base)}
    wrote = []
    for n, day in enumerate(have):
        if day not in done and write_record(base, day, at, n < len(have) - 1):
            wrote.append(day)
    cross_check(base)
    last = max(done | set(wrote), default=None)
    fund: Dict[str, Any] = {"status": "SKIPPED"}
    if live_run or dart_get:
        fund = _record_fund(base, have, at, dart_key if dart_key is not None else os.environ.get("OPENDART_API_KEY"), dart_get or get, first, log, sleep)
    events: Dict[str, Any] = {"status": "SKIPPED"}
    if live_run or events_get:
        from terminal.qsf import kr_events_forward
        events = kr_events_forward.record(base, have, at, dart_key if dart_key is not None else os.environ.get("OPENDART_API_KEY"), events_get or get, first, log, sleep)
    status = "FAILED" if got.get("stopped") or fund["status"] == "FAILED" or events["status"] == "FAILED" else "OK" if last and last >= end else "WAITING"
    return {"status": status, "written": wrote, "last": last, "expected": end, "stopped": got.get("stopped"), "calls": got.get("calls"), "fund": fund, "events": events}


def cross_check(base: Path, tolerance: float = 0.001) -> Optional[Dict[str, Any]]:
    """Live Korean prices come from Yahoo.  Against the KRX close of the same day, any gap means a live score read a wrong price.
    Nothing is corrected here and no score moves.  One line per session."""
    try:
        live = json.loads((Path(base) / "data" / "qsf" / "latest_KR.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    day = live.get("session")
    boards = _rows_of(Path(base) / kr.DATA, day) if day else {}
    if not boards:
        return None
    file = Path(base) / FOLDER / "price_checks.jsonl"
    if file.exists() and any(json.loads(x).get("session") == day for x in file.read_text(encoding="utf-8").splitlines() if x.strip()):
        return None
    close = {r[kr.F["ISU_CD"]]: kr.num(r[kr.F["TDD_CLSPRC"]]) for rows in boards.values() for r in rows}
    seen, gaps, absent, stale = set(), [], 0, 0
    for r in live.get("rows") or []:
        t = r.get("ticker")
        if t in seen:
            continue
        seen.add(t)
        if r.get("data_date") != day:
            stale += 1
            continue
        c, price = close.get(t), r.get("price")
        if not c or not price:
            absent += 1
        elif abs(price / c - 1) > tolerance:
            gaps.append({"ticker": t, "live": price, "krx": c})
    out = {"session": day, "checked": len(seen), "gaps": len(gaps), "absent": absent, "stale": stale, "examples": gaps[:10]}
    file.parent.mkdir(parents=True, exist_ok=True)
    with open(file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(out, ensure_ascii=False) + "\n")
    return out


def last_check(base: Path) -> Optional[Dict[str, Any]]:
    file = Path(base) / FOLDER / "price_checks.jsonl"
    if not file.exists():
        return None
    lines = [x for x in file.read_text(encoding="utf-8").splitlines() if x.strip()]
    return json.loads(lines[-1]) if lines else None


def verify(base: Path, store: Path = FOLDER) -> Dict[str, Any]:
    folder, chain, bad = Path(base) / store, "", []
    rows, torn = _index_rows(folder / "index.jsonl")
    for r in rows:
        p = folder / f"{r['session']}.json.gz"
        chain = hashlib.sha256((chain + r["sha256"]).encode()).hexdigest()
        if not p.exists() or _sha(p) != r["sha256"] or chain != r["chain"]:
            bad.append(r["session"])
    return {"status": "OK" if not bad and not torn else "BROKEN", "sessions": len(rows), "bad": bad, **({"torn_index": True} if torn else {})}


def status(base: Path, calendar: Optional[Sequence[str]], store: Path = FOLDER) -> Dict[str, Any]:
    """Dates and counts only.  ``calendar`` None means the Korean sessions could not be established."""
    rows, check = read_index(base, store), verify(base, store)
    sessions = [r["session"] for r in rows]
    cal = list(calendar) if calendar is not None else None
    matured = sum(1 for s in sessions if sum(1 for d in cal if d > s) >= HORIZON) if cal is not None else 0
    need = MIN_INDEPENDENT * HORIZON
    return {"sessions": len(sessions), "first": sessions[0] if sessions else None, "last": sessions[-1] if sessions else None, "late": sum(1 for r in rows if r["late"]),
            "before_next_open": sum(1 for r in rows if r["before_next_open"]), "stocks": rows[-1]["stocks"] if rows else None, "integrity": check["status"], "price_check": last_check(base),
            "behind_sessions": sum(1 for d in cal if d > sessions[-1]) if cal is not None and sessions else None, "horizon": HORIZON, "matured": matured, "needed": need,
            "independent": matured / HORIZON, "target": MIN_INDEPENDENT, "ready": matured >= need, "remaining_sessions": max(0, need - len(sessions)) + HORIZON if len(sessions) < need else max(0, need - matured)}


def high_risk(base: Path) -> Dict[str, Any]:
    """Stocks in the riskiest fifth of the low risk theme on the newest record.  For display: it feeds no score and is not a tested rule."""
    rows = read_index(base)
    if not rows:
        return {"session": None, "codes": [], "ranked": []}
    day = rows[-1]["session"]
    doc = _read_day(Path(base) / FOLDER, day)
    values = [(r["code"], r["low_risk"]) for r in doc["rows"] if r.get("low_risk") is not None]
    if len(values) < MIN_STOCKS:
        return {"session": day, "codes": [], "ranked": []}
    ranks = validate.rank(np.array([v for _, v in values], dtype=float)) / (len(values) - 1)
    # ``ranked`` is every code that was placed: a code outside it has an unknown risk, not a low one
    return {"session": day, "codes": sorted(c for (c, _), q in zip(values, ranks) if q <= 0.2), "ranked": sorted(c for c, _ in values)}


# ---------------------------------------------------------------------- the one evaluation
def _bottom_excess(values: np.ndarray, ret: np.ndarray) -> Optional[float]:
    ok = np.isfinite(values) & np.isfinite(ret)
    if ok.sum() < MIN_STOCKS:
        return None
    q = validate.rank(values[ok]) / (ok.sum() - 1)
    e = ret[ok] - ret[ok].mean()
    return float(e[q <= 0.2].mean())


def _half(x: Sequence[float]) -> List[List[float]]:
    return [list(x[:len(x) // 2]), list(x[len(x) // 2:])]


def _top_vs_market(score: np.ndarray, px: kr.KrPrices, rows: List[int], picks: List[int], cost: float) -> Dict[str, Any]:
    ns = picks[::HORIZON // STEP]
    ret = np.stack([px.forward(rows[n], HORIZON) for n in ns])
    tops = []
    for n in ns:
        out = np.zeros(score.shape[1], dtype=bool)
        idx = np.flatnonzero(np.isfinite(score[n]))
        out[idx[np.argsort(-score[n][idx])[:max(1, len(idx) // 5)]]] = True
        tops.append(out)
    path = kr.rebalance_path(tops, ret, cost)
    market = [float(v) for v in ret[:, px.col[kr.MARKET]]]
    a, b = _half(path), _half(market)
    parts = [{"top_fifth": kr.annual_growth(a[k], HORIZON), "market": kr.annual_growth(b[k], HORIZON)} for k in (0, 1)]
    beats = all(p["top_fifth"] is not None and p["market"] is not None and p["top_fifth"] > p["market"] for p in parts)
    return {"periods": len(ns), "top_fifth": kr.annual_growth(path, HORIZON), "market": kr.annual_growth(market, HORIZON), "early": parts[0], "late": parts[1], "beats_market_in_both_halves": beats}


def evaluate_once(base: Path, log=print, store: Path = FOLDER) -> Dict[str, Any]:
    """The price record asks whether the riskiest fifth loses; the financial record asks it of its own lowest fifth."""
    fund = store == FUND_FOLDER
    target = Path(base) / (FUND_REPORT if fund else REPORT)
    if target.exists():
        raise RuntimeError("이미 평가했습니다. 규칙상 다시 평가할 수 없습니다.")
    if verify(base, store)["status"] != "OK":
        raise RuntimeError("기록 검증에 실패해 평가하지 않습니다.")
    index = read_index(base, store)
    if not index:
        raise RuntimeError("기록이 없습니다.")
    root, folder = Path(base) / kr.DATA, Path(base) / store
    days = list(kh.weekdays(index[0]["session"], previous_weekday(date.today()).isoformat()))
    px = kr.KrPrices(kr.build_prices(root, log=log, days=days))
    place = {d: n for n, d in enumerate(px.dates)}
    known = [r["session"] for r in index if r["session"] in place]
    matured = [d for d in known if place[d] + HORIZON < len(px.dates)]
    need = MIN_INDEPENDENT * HORIZON
    if len(matured) < need:
        raise RuntimeError(f"아직 평가할 수 없습니다. 만기 거래일 {len(matured)}개, 기준 {need}개입니다.")
    chosen = matured[::STEP]
    rows = [place[d] for d in chosen]
    score, low = np.full((len(rows), len(px.symbols)), np.nan), np.full((len(rows), len(px.symbols)), np.nan)
    for n, d in enumerate(chosen):
        for r in _read_day(folder, d)["rows"]:
            j = px.col.get(r["code"])
            if j is not None:
                score[n, j] = np.nan if r["score"] is None else r["score"]
                worst = r["score"] if fund else r["low_risk"]
                low[n, j] = np.nan if worst is None else worst
    picks = list(range(len(rows)))
    cost = config.round_trip_cost("KR")
    test = en.evaluate(score, px, rows, picks, HORIZON, {}, cost)
    for regime in ("ic_spy_above_200d", "ic_spy_below_200d"):      # prices start at the first record, too short for a 200-day average
        test.pop(regime, None)
    later_ic = [v for v in (rs._ic(score[n], px.forward(rows[n] + 1, HORIZON)) for n in picks) if v is not None]
    bottom = [v for v in (_bottom_excess(low[n], px.forward(rows[n], HORIZON)) for n in picks) if v is not None]
    a, b = _half(bottom)
    late = sum(1 for r in index if r["late"])
    out = {"status": "EVALUATED", "protocol": PROTOCOL, "horizon": HORIZON, "dates": len(rows), "first": chosen[0], "last": chosen[-1], "cost": cost, **test, **test_verdict(test),
           "top_vs_market": _top_vs_market(score, px, rows, picks, cost),
           "score_bottom_fifth" if fund else "low_risk_bottom_fifth": {"excess": float(np.mean(bottom)), "early": float(np.mean(a)), "late": float(np.mean(b)), "supports_exclusion": bool(np.mean(a) < 0 and np.mean(b) < 0 and np.mean(bottom) <= -0.005)},
           "one_day_later_entry_ic": float(np.mean(later_ic)) if later_ic else None, "late_share": late / len(index), "before_next_open_share": sum(1 for r in index if r["before_next_open"]) / len(index)}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return out
