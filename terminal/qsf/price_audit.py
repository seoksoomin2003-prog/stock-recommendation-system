"""Checks the daily price history the scores were computed from.  Read only: nothing is corrected and no score moves.

Korea: the live scan's Yahoo bars (``data/qsf/bars_KR.json.gz``) against the official KRX daily snapshots already kept in
``research_data/krx`` (one file per board and day).  The KRX change rate (``FLUC_RT``) is measured from the exchange's base price,
which already allows for splits and bonus issues, so a Yahoo close-to-close change that differs from it on a day both have is a
wrong price, not an adjustment.  Found on 2026-11-09: whole days missing (2025-09-19 for 289 of 300 stocks), days that repeat the
previous close while the stock moved (2024-10-14, 2024-11-07, 2026-03-27), single bad prints, and history from before a stock's
KOSDAQ listing.

Since QSF-1.1.8 (the user's decision of 2026-11-09) the scan builds the Korean bars from these same KRX snapshots
(``kr_bars``), so for most days the check now confirms the rebuild rather than an independent source.  What it can still flag:
the newest days KRX has not published yet (taken from Yahoo), stocks KRX does not list (Yahoo bars kept), and a rebuild that
went wrong.

United States: no second free daily source is used, so the check is internal: sessions missing against the NYSE calendar,
bars that repeat the previous bar exactly, days with no volume, and high/low that do not contain the open and close.  The last
bar is checked apart: right after the close Yahoo's day bar can still be provisional.

Only the most recent ``WINDOW`` sessions count toward a stock's flag, since those are what the scores read (one-year returns and
volatility).  Results: ``data/qsf/price_audit_{US,KR}.json`` (latest) and one summary line per market and session in
``data/qsf/price_audit_log.jsonl``.
"""
import gzip
import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

WINDOW = 253                 # one year of returns plus its first close
TOLERANCE = 0.005            # KRX rates carry two decimals; Korean prices are whole won, so a real match is near exact
LARGE = 0.05                 # a one-day difference this big is called out on its own
EXAMPLES = 5
FOLDER = Path("data") / "qsf"
KRX = Path("research_data") / "krx"
BOARDS = ("KOSPI", "KOSDAQ")
CODE, CLOSE, CHANGE, VALUE = 0, 6, 7, 9       # positions in a KRX snapshot row (``krx_history.FIELDS``)
SCANBARS = re.compile(r"^scanbars_(\d{4}-\d{2}-\d{2})_[0-9a-f]+_[0-9a-f]+\.json$")

KIND_TEXT = {
    "missing": "KRX에서 거래됐는데 시세가 없는 날",
    "stale": "주가가 움직였는데 전날 종가가 그대로 들어간 날",
    "wrong": "하루 등락률이 KRX와 다른 날",
    "pre_listing": "이 시장 상장 전 거래가 이력에 섞인 날",
    "missing_session": "미국 거래일인데 시세가 없는 날",
    "repeated": "전날과 시가·고가·저가·종가가 똑같은 날",
    "zero_volume": "거래량이 0인 날",
    "bad_range": "고가·저가가 시가·종가를 감싸지 않는 날",
}


def _num(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v


def krx_days(root: Path, first: str) -> Dict[str, Dict[str, List[Any]]]:
    """Every day from ``first`` with both boards on file: {day: {code: row}}.  A day with one board missing is left out."""
    days: Dict[str, Dict[str, List[Any]]] = {}
    files = {b: {p.name[:10]: p for p in (Path(root) / b).glob("*.json.gz") if p.name[:10] >= first} for b in BOARDS}
    for day in sorted(set(files[BOARDS[0]]) & set(files[BOARDS[1]])):
        rows: Dict[str, List[Any]] = {}
        for b in BOARDS:
            with gzip.open(files[b][day], "rt", encoding="utf-8") as fh:
                for r in json.load(fh):
                    rows[str(r[CODE])] = r
        if rows:
            days[day] = rows
    return days


def audit_kr_stock(bars: List[Dict[str, Any]], code: str, krx: Dict[str, Dict[str, List[Any]]], days: List[str]) -> Dict[str, Any]:
    """One stock's Yahoo bars against the KRX days.  ``days``: the KRX days to judge, oldest first."""
    if not days:
        return {"checked": 0, "level": "unknown", "counts": {}, "examples": []}
    by = {b["date"]: b for b in bars if b.get("close")}
    pos = {d: i for i, d in enumerate(days)}
    listed = [d for d in days if code in krx[d]]
    counts: Counter = Counter()
    examples: List[Dict[str, Any]] = []
    worst = 0.0

    def note(kind: str, day: str, **extra: Any) -> None:
        counts[kind] += 1
        if len(examples) < EXAMPLES:
            examples.append({"kind": kind, "date": day, **extra})

    if listed:
        for d in days:
            if d < listed[0] and d in by:
                note("pre_listing", d)
    traded = [d for d in listed if (_num(krx[d][code][VALUE]) or 0) > 0]
    seen = [d for d in days if d in by and code in krx[d]]
    for d in traded:
        if d not in by and d > (seen[0] if seen else d):
            note("missing", d)
    for a, b in zip(seen, seen[1:]):
        if any(d in traded and d not in by for d in days[pos[a] + 1:pos[b]]):
            continue                                  # the gap is already counted as missing days
        rate = _num(krx[b][code][CHANGE])
        if rate is None:
            continue
        mine = by[b]["close"] / by[a]["close"] - 1
        diff = abs(mine - rate / 100)
        if diff <= TOLERANCE:
            continue
        worst = max(worst, diff)
        if mine == 0:
            note("stale", b, krx_pct=round(rate, 2))
        else:
            note("wrong", b, yahoo_pct=round(mine * 100, 2), krx_pct=round(rate, 2))
    level = "ok" if not counts else "bad" if counts["pre_listing"] or worst > LARGE else "warn"
    return {"checked": len(seen), "level": level, "counts": dict(counts), "largest_gap_pct": round(worst * 100, 2) if worst else 0.0, "examples": examples}


def audit_us_stock(bars: List[Dict[str, Any]], sessions: List[str]) -> Dict[str, Any]:
    """One stock's bars against the NYSE sessions to judge (oldest first).  The last bar's range is reported apart."""
    rows = [b for b in bars if b.get("close")]
    if not rows or not sessions:
        return {"checked": 0, "level": "unknown", "counts": {}, "examples": []}
    by = {b["date"]: b for b in rows}
    counts: Counter = Counter()
    examples: List[Dict[str, Any]] = []

    def note(kind: str, day: str) -> None:
        counts[kind] += 1
        if len(examples) < EXAMPLES:
            examples.append({"kind": kind, "date": day})

    start = max(rows[0]["date"], sessions[0])
    judged = [d for d in sessions if d >= start]
    for d in judged:
        if d not in by:
            note("missing_session", d)
    last = rows[-1]["date"]
    prev = None
    for b in rows:
        if b["date"] < start:
            prev = b
            continue
        o, h, lo, c = b.get("open"), b.get("high"), b.get("low"), b["close"]
        if prev is not None and (o, h, lo, c) == (prev.get("open"), prev.get("high"), prev.get("low"), prev["close"]):
            note("repeated", b["date"])
        if not b.get("volume"):
            note("zero_volume", b["date"])
        if b["date"] != last and None not in (o, h, lo) and (h < max(o, c) * (1 - 1e-6) or lo > min(o, c) * (1 + 1e-6)):
            note("bad_range", b["date"])
        prev = b
    b = rows[-1]
    o, h, lo, c = b.get("open"), b.get("high"), b.get("low"), b["close"]
    provisional = bool(None not in (o, h, lo) and (h < max(o, c) * (1 - 1e-6) or lo > min(o, c) * (1 + 1e-6)))
    level = "ok" if not counts else "bad" if counts["missing_session"] or counts["repeated"] else "warn"
    return {"checked": len(judged), "level": level, "counts": dict(counts), "examples": examples, "last_bar_provisional": provisional, "last_date": last}


def _summary(market: str, session: Optional[str], stocks: Dict[str, Dict[str, Any]], source: str, now: datetime) -> Dict[str, Any]:
    kinds: Counter = Counter()
    days: Counter = Counter()
    for s in stocks.values():
        kinds.update(s["counts"])
        for e in s["examples"]:
            days[e["date"]] += 1
    flagged = {t: s for t, s in stocks.items() if s["level"] in ("warn", "bad")}
    return {"status": "REAL", "market": market, "session": session, "at": now.isoformat(timespec="seconds"), "source": source, "window_sessions": WINDOW,
            "checked": len(stocks), "flagged": len(flagged), "bad": sum(1 for s in flagged.values() if s["level"] == "bad"),
            "by_kind": {k: kinds[k] for k in sorted(kinds)}, "kind_text": {k: KIND_TEXT[k] for k in kinds},
            "common_dates": [{"date": d, "stocks": n} for d, n in days.most_common(8) if n >= 3],
            "provisional_last_bars": sum(1 for s in stocks.values() if s.get("last_bar_provisional")),
            "stocks": stocks}


def audit_kr(base: Path, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    try:
        with gzip.open(Path(base) / FOLDER / "bars_KR.json.gz", "rt", encoding="utf-8") as fh:
            bars = json.load(fh)
    except (OSError, ValueError, EOFError):              # EOFError: a gzip cut short
        return {"status": "UNAVAILABLE", "market": "KR", "reason": "한국 스캔 시세가 없습니다."}
    first = min((v[0]["date"] for v in bars.values() if v), default=None)
    krx = krx_days(Path(base) / KRX, first) if first else {}
    if not krx:
        return {"status": "UNAVAILABLE", "market": "KR", "reason": "비교할 KRX 일별 자료가 없습니다."}
    days = sorted(krx)[-WINDOW:]
    session = max((v[-1]["date"] for v in bars.values() if v), default=None)
    stocks = {code: audit_kr_stock(rows, code, krx, days) for code, rows in bars.items()}
    return _summary("KR", session, stocks, f"스캔 입력 일봉(QSF-1.1.8부터 KRX 자료로 재구성, 최근 미공개일은 Yahoo) 대 KRX 일별 시세 {days[0]}~{days[-1]}", now)


def latest_us_bars(base: Path) -> Dict[str, Any]:
    root = Path(base) / FOLDER / "cache"
    by: Dict[str, List[Path]] = {}
    for f in root.iterdir() if root.exists() else []:
        m = SCANBARS.match(f.name)
        if m:
            by.setdefault(m.group(1), []).append(f)
    if not by:
        return {}
    session = max(by)
    bars: Dict[str, Any] = {}
    for f in sorted(by[session]):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        bars.update(doc.get("data", doc) if isinstance(doc, dict) else {})
    return {"session": session, "bars": bars}


def audit_us(base: Path, sessions_between: Callable[[date, date], List[date]], now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    got = latest_us_bars(base)
    if not got.get("bars"):
        return {"status": "UNAVAILABLE", "market": "US", "reason": "미국 스캔 시세가 없습니다."}
    session = got["session"]
    first = min(v[0]["date"] for v in got["bars"].values() if v)
    sessions = [d.isoformat() for d in sessions_between(date.fromisoformat(first), date.fromisoformat(session))][-WINDOW:]
    stocks = {t: audit_us_stock(rows, sessions) for t, rows in got["bars"].items() if isinstance(rows, list)}
    return _summary("US", session, stocks, f"Yahoo 일봉(스캔 입력)의 내부 점검, NYSE 거래일 {sessions[0]}~{sessions[-1]}", now)


def save(base: Path, result: Dict[str, Any]) -> Dict[str, Any]:
    """Writes the latest result and, once per market and session, a summary line.  Returns the summary."""
    folder = Path(base) / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    market = result["market"]
    tmp = folder / f"price_audit_{market}.json.tmp"
    tmp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    tmp.replace(folder / f"price_audit_{market}.json")
    line = {k: result.get(k) for k in ("market", "session", "at", "status", "checked", "flagged", "bad", "by_kind", "provisional_last_bars", "reason")}
    log = folder / "price_audit_log.jsonl"
    seen = set()
    if log.exists():
        for x in log.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(x)
            except ValueError:
                continue
            seen.add((r.get("market"), r.get("session")))
    if result.get("status") == "REAL" and (market, result.get("session")) not in seen:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    return line


def load(base: Path, market: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads((Path(base) / FOLDER / f"price_audit_{market}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def for_stock(base: Path, market: str, ticker: str) -> Optional[Dict[str, Any]]:
    """The latest check of one stock, with words for the screen; None when the stock was not checked."""
    doc = load(base, market)
    if not doc or doc.get("status") != "REAL":
        return None
    s = (doc.get("stocks") or {}).get(ticker)
    if not s:
        return None
    parts = [f"{KIND_TEXT[k]} {n}일" for k, n in sorted(s["counts"].items())]
    return {"session": doc["session"], "source": doc["source"], "level": s["level"], "counts": s["counts"], "examples": s["examples"],
            "last_bar_provisional": bool(s.get("last_bar_provisional")),
            "text": ("최근 1년 시세 이력에서 " + ", ".join(parts) + ".") if parts else "최근 1년 시세 이력에서 문제를 찾지 못했습니다."}


def summary_view(base: Path) -> Dict[str, Any]:
    """Both markets without the per-stock lists, for the record screen."""
    out = {}
    for m in ("US", "KR"):
        doc = load(base, m)
        out[m] = {k: v for k, v in doc.items() if k != "stocks"} if doc else {"status": "UNAVAILABLE"}
    return out


def run(base: Path, sessions_between: Callable[[date, date], List[date]], now: Optional[datetime] = None) -> Dict[str, Any]:
    out = {}
    for market, fn in (("US", lambda: audit_us(base, sessions_between, now)), ("KR", lambda: audit_kr(base, now))):
        res = fn()
        out[market] = save(base, res) if res.get("status") == "REAL" else {k: res.get(k) for k in ("market", "status", "reason")}
    return out
