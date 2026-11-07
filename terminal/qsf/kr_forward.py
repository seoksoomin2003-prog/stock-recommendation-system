"""The Korean price score, written down every session and kept apart from the live score.  Rules: reports/QSF_KR_FORWARD_PROTOCOL.md.

A record is written once and chained by hash, so a later edit shows.  No return is computed while the record grows: the status reads
dates only, and the single evaluation is refused until enough sessions have matured.  Nothing here reads or changes the live score,
the QSF ledger or P6-11B.
"""
import gzip
import hashlib
import json
import os
from datetime import date, datetime, time as clock, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

from terminal.qsf import config, krx_history as kh, research_ensemble as en, research_kr as kr, research_swing as rs, validate
from terminal.qsf.research_score import test_verdict

PROTOCOL = "reports/QSF_KR_FORWARD_PROTOCOL.md"
FOLDER = Path("research_data") / "krx_forward"
REPORT = Path("reports") / "qsf" / "QSF_KR_FORWARD.json"
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


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_index(base: Path) -> List[Dict[str, Any]]:
    p = Path(base) / FOLDER / "index.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _append_index(folder: Path, day: str, recorded_at: str, late: bool, before_open: bool, stocks: int) -> None:
    rows = read_index(folder.parent.parent)
    sha = _sha(folder / f"{day}.json.gz")
    chain = hashlib.sha256(((rows[-1]["chain"] if rows else "") + sha).encode()).hexdigest()
    with open(folder / "index.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"session": day, "recorded_at": recorded_at, "late": late, "before_next_open": before_open, "stocks": stocks, "sha256": sha, "chain": chain}) + "\n")


def _read_day(folder: Path, day: str) -> Dict[str, Any]:
    with gzip.open(folder / f"{day}.json.gz", "rt", encoding="utf-8") as fh:
        return json.load(fh)


def write_record(base: Path, day: str, at: datetime, late: bool) -> bool:
    """Write-once.  A file left without its index line by a crash gets the line it was written with."""
    folder = Path(base) / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    if day in {r["session"] for r in read_index(base)}:
        return False
    p = folder / f"{day}.json.gz"
    if not p.exists():
        doc = {**score_day(Path(base) / kr.DATA, day), "recorded_at": at.isoformat(), "late": late, "before_next_open": at < next_open(day)}
        tmp = p.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False)
        tmp.replace(p)
    doc = _read_day(folder, day)
    _append_index(folder, day, doc["recorded_at"], doc["late"], doc["before_next_open"], len(doc["rows"]))
    return True


def record(base: Path, key: Optional[str] = None, get: Optional[Callable[..., Any]] = None, now: Callable[[], datetime] = _utcnow, first: str = FIRST, log=print, sleep=None) -> Dict[str, Any]:
    """OK: caught up to the previous weekday.  WAITING: that day is not published yet, or was a holiday; asked again at the next slot."""
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
    last = max(done | set(wrote), default=None)
    status = "FAILED" if got.get("stopped") else "OK" if last and last >= end else "WAITING"
    return {"status": status, "written": wrote, "last": last, "expected": end, "stopped": got.get("stopped"), "calls": got.get("calls")}


def verify(base: Path) -> Dict[str, Any]:
    folder, chain, bad = Path(base) / FOLDER, "", []
    rows = read_index(base)
    for r in rows:
        p = folder / f"{r['session']}.json.gz"
        chain = hashlib.sha256((chain + r["sha256"]).encode()).hexdigest()
        if not p.exists() or _sha(p) != r["sha256"] or chain != r["chain"]:
            bad.append(r["session"])
    return {"status": "OK" if not bad else "BROKEN", "sessions": len(rows), "bad": bad}


def status(base: Path, calendar: Optional[Sequence[str]]) -> Dict[str, Any]:
    """Dates and counts only.  ``calendar`` None means the Korean sessions could not be established."""
    rows, check = read_index(base), verify(base)
    sessions = [r["session"] for r in rows]
    cal = list(calendar) if calendar is not None else None
    matured = sum(1 for s in sessions if sum(1 for d in cal if d > s) >= HORIZON) if cal is not None else 0
    need = MIN_INDEPENDENT * HORIZON
    return {"sessions": len(sessions), "first": sessions[0] if sessions else None, "last": sessions[-1] if sessions else None, "late": sum(1 for r in rows if r["late"]),
            "before_next_open": sum(1 for r in rows if r["before_next_open"]), "stocks": rows[-1]["stocks"] if rows else None, "integrity": check["status"],
            "behind_sessions": sum(1 for d in cal if d > sessions[-1]) if cal is not None and sessions else None, "horizon": HORIZON, "matured": matured, "needed": need,
            "independent": matured / HORIZON, "target": MIN_INDEPENDENT, "ready": matured >= need, "remaining_sessions": max(0, need - len(sessions)) + HORIZON if len(sessions) < need else max(0, need - matured)}


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


def evaluate_once(base: Path, log=print) -> Dict[str, Any]:
    target = Path(base) / REPORT
    if target.exists():
        raise RuntimeError("이미 평가했습니다. 규칙상 다시 평가할 수 없습니다.")
    if verify(base)["status"] != "OK":
        raise RuntimeError("기록 검증에 실패해 평가하지 않습니다.")
    index = read_index(base)
    if not index:
        raise RuntimeError("기록이 없습니다.")
    root, folder = Path(base) / kr.DATA, Path(base) / FOLDER
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
                low[n, j] = np.nan if r["low_risk"] is None else r["low_risk"]
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
           "low_risk_bottom_fifth": {"excess": float(np.mean(bottom)), "early": float(np.mean(a)), "late": float(np.mean(b)), "supports_exclusion": bool(np.mean(a) < 0 and np.mean(b) < 0 and np.mean(bottom) <= -0.005)},
           "one_day_later_entry_ic": float(np.mean(later_ic)) if later_ic else None, "late_share": late / len(index), "before_next_open_share": sum(1 for r in index if r["before_next_open"]) / len(index)}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return out
