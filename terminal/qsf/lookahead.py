"""Look-ahead audit: a value computed for a day must not move when everything after that day is replaced.

Each audited function is called twice on the same day: once on the prices as they are, once on a copy whose later rows are wiped
(and once more with those rows multiplied).  Any difference means the function read the future.  A function that is supposed to
read the future (an outcome) is run through the same check as a control: if the audit does not catch it, the audit itself is
broken.  The second part reads the forward records: hash chains, and how many were written before the next open.

Read-only on every record.  Writes one view file, data/qsf/lookahead_audit.json.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

VIEW = Path("data") / "qsf" / "lookahead_audit.json"
WINDOW_WEEKDAYS = 400           # price rows read back: enough for the longest window (253) on every sampled day
SAMPLE_BACK, SAMPLE_GAP, SAMPLE_STEP = 82, 22, 6        # sampled days: from 82 rows before the end to 22 before it, every sixth
MODES = ("WIPED", "MULTIPLIED")
UNIVERSE = 300
ENGINE_STOCKS, ENGINE_HISTORY = 12, 320          # the score engine is run on this many of the most traded stocks, on this many rows back


def poison(d: Dict[str, Any], i: int, mode: str) -> Dict[str, Any]:
    """A copy in which every row after ``i`` of every day-by-stock array is unusable (WIPED) or wrong (MULTIPLIED)."""
    n = len(d["dates"]) if "dates" in d else None
    out = dict(d)
    for k, v in d.items():
        if isinstance(v, np.ndarray) and v.ndim >= 1 and v.dtype.kind in "fiu" and (n is None or v.shape[0] == n) and k != "dates":
            a = v.astype(float, copy=True)
            if mode == "WIPED":
                a[i + 1:] = np.nan
            else:
                a[i + 1:] = a[i + 1:] * 3.7 + 11.0
            out[k] = a
    return out


def same(a: Any, b: Any) -> bool:
    """Equal, with a missing value equal to a missing value."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        x, y = np.asarray(a), np.asarray(b)
        if x.shape != y.shape:
            return False
        if x.dtype.kind in "fc" or y.dtype.kind in "fc":
            return bool(np.array_equal(x.astype(float), y.astype(float), equal_nan=True))
        return bool(np.array_equal(x, y))
    if isinstance(a, float) and isinstance(b, float) and a != a and b != b:
        return True
    return a == b


def _filled(x: Any) -> bool:
    """The result says something: a function that returns nothing on every sampled day would pass any check."""
    if isinstance(x, dict):
        return any(_filled(v) for v in x.values())
    if isinstance(x, (list, tuple)):
        return any(_filled(v) for v in x)
    if isinstance(x, np.ndarray):
        return bool(np.any(x)) if x.dtype.kind == "b" else bool(np.isfinite(x.astype(float)).any())
    return x is not None and x == x


def check(fn: Callable[[Dict[str, Any], int], Any], d: Dict[str, Any], rows: Sequence[int]) -> Dict[str, Any]:
    """``moved``: sampled days on which the result changed with the later rows.  ``filled``: days on which it said anything."""
    moved, filled = [], 0
    for i in rows:
        base = fn(d, i)
        filled += _filled(base)
        if not all(same(base, fn(poison(d, i, mode), i)) for mode in MODES):
            moved.append(int(i))
    return {"days": len(rows), "filled": int(filled), "moved": moved}


def sample_rows(n: int) -> List[int]:
    return [i for i in range(n - SAMPLE_BACK, n - SAMPLE_GAP, SAMPLE_STEP) if i > 0]


# ---------------------------------------------------------------------- what is audited
def functions(d: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The functions that turn past prices into something recorded or shown, each as ``fn(d, i)``; ``control`` marks the outcome."""
    from terminal.qsf import kr_method, kr_risk_grade, regime_weights
    close = d["close"].astype(float)
    value = d["value"].astype(float)[-120:]
    traded = np.where(np.isfinite(value), value, 0.0).sum(axis=0)           # a fixed set of columns, chosen once and used for both calls
    cols = np.sort(np.argsort(-traded)[:UNIVERSE])

    def index_state(z: Dict[str, Any], i: int) -> Optional[str]:
        """The state of an equal-weight index of the universe, built from the same (possibly wiped) prices."""
        c = z["close"].astype(float)[:, cols]
        with np.errstate(invalid="ignore", divide="ignore"):
            move = c[1:] / c[:-1] - 1
        have = np.isfinite(move)
        r = np.where(have.any(axis=1), np.where(have, move, 0.0).sum(axis=1) / np.maximum(have.sum(axis=1), 1), 0.0)
        return regime_weights.state(100.0 * np.concatenate([[1.0], np.cumprod(1 + r)]), i)
    def engine_scores(z: Dict[str, Any], i: int) -> Dict[str, Any]:
        """The live score engine itself (both strategies; the price factors, the gates and the levels) on each day's bars.  Added
        after the audit of 2026-11-22: the engine and everything it calls had not been among the audited functions."""
        from terminal.qsf import engine
        i0 = max(0, i - ENGINE_HISTORY + 1)
        adj = z.get("adj_close", z["close"])

        def bars(j: int) -> List[Dict[str, Any]]:
            rows = []
            for n in range(i0, i + 1):
                c = float(z["close"][n, j])
                if c == c and c > 0:
                    rows.append({"date": str(z["dates"][n]), "open": float(z["open"][n, j]), "high": float(z["high"][n, j]), "low": float(z["low"][n, j]), "close": c,
                                 "adj_close": float(adj[n, j]), "volume": float(z["volume"][n, j])})
            return rows
        bench = bars(int(cols[0]))
        out: Dict[str, Any] = {}
        for j in cols[1:ENGINE_STOCKS + 1]:
            b = bars(int(j))
            if len(b) < 60 or b[-1]["date"] != str(z["dates"][i]):
                continue
            base = {"market": "KR", "ticker": str(z["symbols"][j]), "bars": b, "bench": bench, "bench_name": "점검용 지수", "events": None, "regime": None, "earnings": None, "fund": None,
                    "expected_session": str(z["dates"][i])}
            res = [engine.score(dict(base), s) for s in ("SWING", "LONG_TERM")]
            out[str(z["symbols"][j])] = [[r["score"], r["coverage"], [g["code"] for g in r["gates"]], [f["normalized"] for f in r["factors"]]] for r in res]
        return out
    return [
        {"id": "engine.score", "label": "점수 엔진(스윙·장기 점수, 요인 값, 위험 게이트)", "fn": engine_scores},
        {"id": "kr_method.signals", "label": "독자 매매법의 진입 신호 7종", "fn": lambda z, i: kr_method.signals(z, i, cols)},
        {"id": "kr_method.atr", "label": "독자 매매법의 ATR(손절·목표 폭)", "fn": lambda z, i: kr_method.atr(z, i, cols)},
        {"id": "kr_risk_grade.inputs", "label": "위험 등급의 입력 4종", "fn": kr_risk_grade.inputs},
        {"id": "regime_weights.state", "label": "시장 상태(상승·안정 / 상승·불안 / 하락)", "fn": index_state},
        {"id": "kr_risk_grade.targets", "label": "대조: 20거래일 뒤 결과(미래를 읽는 것이 맞음)", "fn": kr_risk_grade.targets, "control": True},
    ] if close.shape[0] else []


def audit_functions(d: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = sample_rows(d["close"].shape[0])
    out = []
    for f in functions(d):
        got = check(f["fn"], d, rows)
        control = bool(f.get("control"))
        ok = (len(got["moved"]) == got["days"] and got["days"] > 0) if control else (not got["moved"] and got["filled"] > 0)
        out.append({"id": f["id"], "label": f["label"], "control": control, **got, "moved": len(got["moved"]), "moved_rows": got["moved"][:5], "ok": ok})
    return out


# ---------------------------------------------------------------------- the forward records
def audit_records(base: Path) -> List[Dict[str, Any]]:
    """Per store: the hash chain, and how many sessions were written before the next open (a later record is flagged, not hidden)."""
    from terminal import automation
    from terminal.qsf import kr_forward as kf
    out = []
    for name in automation.FORWARD_STORES:
        store = Path("research_data") / name
        rows = kf.read_index(base, store)
        if not rows:
            continue
        v = kf.verify(base, store)
        out.append({"store": name, "sessions": len(rows), "first": rows[0]["session"], "last": rows[-1]["session"], "chain": v["status"], "bad": v["bad"][:5],
                    "before_next_open": sum(1 for r in rows if r.get("before_next_open")), "late": sum(1 for r in rows if r.get("late"))})
    return out


def _walk_forward(base: Path) -> Optional[Dict[str, Any]]:
    from terminal.qsf import regime_weights
    try:
        doc = json.loads((Path(base) / regime_weights.REPORT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {m: {"leak_free": v.get("leak_free"), "folds": v.get("folds"), "first_train": v.get("first_train"), "horizon": doc.get("horizon")} for m, v in doc["markets"].items()}


def run(base: Path, prices: Optional[Dict[str, Any]] = None, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> Dict[str, Any]:
    """The audit on the newest price rows on file.  ``prices`` replaces the Korean price files (tests)."""
    at = now()
    if prices is None:
        from terminal.qsf import kr_method
        last = (at + timedelta(hours=9)).date()
        first = last - timedelta(days=int(WINDOW_WEEKDAYS * 7 / 5) + 10)
        prices = kr_method._prices(Path(base), first.isoformat(), last.isoformat())
    dates = [str(x) for x in prices["dates"]]
    fns = audit_functions(prices) if len(dates) > SAMPLE_BACK else []
    records = audit_records(Path(base))
    checked = [f for f in fns if not f["control"]]
    control = next((f for f in fns if f["control"]), None)
    problems = [f["id"] for f in checked if not f["ok"]] + ([control["id"]] if control and not control["ok"] else []) + [r["store"] for r in records if r["chain"] != "OK"]
    status = "NO_PRICES" if not fns else "OK" if not problems else "PROBLEM"
    doc = {"status": status, "checked_at": at.isoformat(), "prices_to": dates[-1] if dates else None, "sampled_days": len(sample_rows(len(dates))), "modes": list(MODES),
           "functions": checked, "control": control, "records": records, "walk_forward": _walk_forward(Path(base)), "problems": problems,
           "note": "점검 대상은 과거 가격으로 기록·화면 값을 만드는 함수입니다. 라이브 스캔은 그날까지 받은 자료만 읽으므로 미래 자료가 없습니다. 재무 자료의 공시일 기준은 따로 점검했습니다(2026-11-11 입력 점검)."}
    path = Path(base) / VIEW
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return doc


def status(base: Path) -> Dict[str, Any]:
    try:
        return json.loads((Path(base) / VIEW).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "NO_RECORD"}
