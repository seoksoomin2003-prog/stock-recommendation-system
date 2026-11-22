"""The own trading method challenger for Korea (KR-M1).  Rules: reports/QSF_KR_METHOD_PROTOCOL.md.

Three layers: stocks carrying an avoid mark are dropped, the top fifth of the rest by the live swing score is the pool, and a chart
signal on a pool stock is an entry at the next open with one shared exit rule (stop, target, ten sessions).  Seven chart entries and
two baselines are followed side by side.  The selection run on the past names at most two primaries and runs once; the daily record
is written once and holds no return.  Nothing here changes the live score, places an order, or is investment advice.
"""
import gzip
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set

from terminal.qsf import calibrate
import numpy as np

from terminal.qsf import config, kr_avoid_marks, kr_forward as kf, kr_risk_grade, krx_history as kh, research_kr as kr, validate
from terminal.qsf.ledger import Ledger

PROTOCOL = "reports/QSF_KR_METHOD_PROTOCOL.md"
FOLDER = Path("research_data") / "kr_method"
SELECTION = Path("reports") / "qsf" / "QSF_KR_METHOD_SELECTION.json"
STATUS = Path("data") / "qsf" / "kr_method_status.json"          # rebuilt after each record: a view, not a record
FIRST = "2026-11-11"
METHODS = ("R1", "R2", "R3", "T1", "T2", "T3", "T4")
BASELINES = ("B0", "B00")
NAMES = {"R1": "눌림목", "R2": "과매도 반등", "R3": "밴드 하단 복귀", "T1": "신고가 돌파", "T2": "수축 후 돌파", "T3": "정배열 시작", "T4": "상대강도 지속",
         "B0": "기준선(신호 없이 후보군)", "B00": "기준선 2(거르기 없이 대상 전부)"}
FAMILY = {"R1": "되돌림", "R2": "되돌림", "R3": "되돌림", "T1": "추세", "T2": "추세", "T3": "추세", "T4": "추세"}
HOLD, STOP_ATR, TARGET_ATR, ATR_N = 10, 2.0, 3.0, 14
POOL_SHARE = 0.2
NEED_BARS = 253                     # the longest look-back: the close 252 sessions ago
MIN_ROWS = 200                      # fewer scored stocks than this is a partial day
MIN_TRADES, SELECT_T, MAX_PRIMARY = 300, 2.45, 2
VERDICT_T = 2.0
READ_AT = (120, 240)
WEIGHT_FUND, WEIGHT_RISK = 10.0, 20.0          # the live Korean swing weights of the two domains the past scores hold
WINDOW = kf.WINDOW                  # weekdays of KRX files read back for one day's signals
BLOCKED = "EARNINGS_IMMINENT"


class NotReady(Exception):
    """The day cannot be recorded yet: its marks, its prices or enough of its live scores are missing."""


# ---------------------------------------------------------------------- signals
def _closes(d: Dict[str, np.ndarray], i: int, cols: np.ndarray) -> np.ndarray:
    return d["close"][i - NEED_BARS + 1:i + 1][:, cols].astype(float)


def _ma(c: np.ndarray, n: int, back: int = 0) -> np.ndarray:
    """Mean of the ``n`` closes ending ``back`` sessions ago; a missing close makes it missing."""
    end = len(c) - back
    return c[end - n:end].mean(axis=0)


def _sd(c: np.ndarray, n: int, back: int = 0) -> np.ndarray:
    end = len(c) - back
    return c[end - n:end].std(axis=0)


def _rsi2(c: np.ndarray) -> np.ndarray:
    """Wilder's RSI with period 2, warmed up over the last 30 changes."""
    ch = np.diff(c[-31:], axis=0)
    gain, loss = np.maximum(ch, 0), np.maximum(-ch, 0)
    ag, al = gain[:2].mean(axis=0), loss[:2].mean(axis=0)
    for t in range(2, len(ch)):
        ag, al = (ag + gain[t]) / 2, (al + loss[t]) / 2
    with np.errstate(invalid="ignore", divide="ignore"):
        rsi = 100 - 100 / (1 + ag / al)
    rsi = np.where((al == 0) & (ag > 0), 100.0, rsi)
    return np.where((al == 0) & (ag == 0), 50.0, rsi)


def atr(d: Dict[str, np.ndarray], i: int, cols: np.ndarray) -> np.ndarray:
    """Mean true range of the 14 sessions ending at row ``i`` (at least 10 of them traded)."""
    if i < ATR_N:
        return np.full(len(cols), np.nan)
    h, lo = d["high"][i - ATR_N + 1:i + 1][:, cols].astype(float), d["low"][i - ATR_N + 1:i + 1][:, cols].astype(float)
    pc = d["close"][i - ATR_N:i][:, cols].astype(float)
    with np.errstate(invalid="ignore"):
        tr = np.fmax(h - lo, np.fmax(np.abs(h - pc), np.abs(lo - pc)))
    tr = np.where(np.isfinite(h) & np.isfinite(lo) & np.isfinite(pc), tr, np.nan)
    have = np.isfinite(tr).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(have >= 10, np.nansum(np.where(np.isfinite(tr), tr, 0.0), axis=0) / np.where(have > 0, have, np.nan), np.nan)


def signals(d: Dict[str, np.ndarray], i: int, cols: np.ndarray) -> Dict[str, np.ndarray]:
    """The seven entry signals at the close of row ``i`` for the universe columns ``cols``.  Reads nothing after ``i``.
    A missing bar inside a rule's window means no signal."""
    k = len(cols)
    out = {m: np.zeros(k, dtype=bool) for m in METHODS}
    if i < NEED_BARS - 1 or not k:
        return out
    c = _closes(d, i, cols)
    c0, c1 = c[-1], c[-2]
    with np.errstate(invalid="ignore", divide="ignore"):
        out["R1"] = (c0 > _ma(c, 60)) & (c0 > _ma(c, 5)) & np.all([c[-1 - b] <= _ma(c, 5, b) for b in (1, 2, 3)], axis=0)
        out["R2"] = (_rsi2(c) < 10) & (c0 > _ma(c, 200))
        low_prev, low_now = _ma(c, 20, 1) - 2 * _sd(c, 20, 1), _ma(c, 20) - 2 * _sd(c, 20)
        out["R3"] = (c1 < low_prev) & (c0 >= low_now)
        high = d["high"][i - 20:i][:, cols].astype(float)
        vol = d["volume"][i - 20:i + 1][:, cols].astype(float)
        out["T1"] = (c0 > high.max(axis=0)) & (vol[-1] >= 1.5 * vol[:-1].mean(axis=0))
        win = np.lib.stride_tricks.sliding_window_view(c[-140:-1], 20, axis=0)          # the 120 windows ending at rows i-120 .. i-1
        width = 4 * win.std(axis=-1) / win.mean(axis=-1)
        tight = np.isfinite(width).all(axis=0) & ((width <= width[-1]).mean(axis=0) <= 0.2)
        out["T2"] = tight & (c0 > _ma(c, 20) + 2 * _sd(c, 20))
        lined = lambda b: (_ma(c, 5, b) > _ma(c, 20, b)) & (_ma(c, 20, b) > _ma(c, 60, b))      # noqa: E731
        out["T3"] = lined(0) & ~lined(1) & np.isfinite(_ma(c, 60, 1)) & np.isfinite(_ma(c, 5, 1))
        mom = c[-22] / c[0] - 1
        strong = np.zeros(k, dtype=bool)
        have = np.isfinite(mom)
        if have.sum() >= 2:
            strong[have] = validate.rank(mom[have]) / (have.sum() - 1) >= 0.8
        out["T4"] = strong & (c1 <= _ma(c, 20, 1)) & (c0 > _ma(c, 20))
    return out


# ---------------------------------------------------------------------- one trade
def simulate(o: np.ndarray, h: np.ndarray, lo: np.ndarray, c: np.ndarray, s: int, atr_value: float, cost: float) -> Optional[Dict[str, Any]]:
    """Follow one signal of row ``s`` on one stock's arrays.  None: no trade (no open on the entry day, or no ATR).
    ``open`` is True while the ten sessions have not ended and neither level was touched."""
    e = s + 1
    if e >= len(o) or not (np.isfinite(o[e]) and o[e] > 0) or atr_value is None or not np.isfinite(atr_value) or atr_value <= 0:
        return None
    entry = float(o[e])
    stop, target = entry - STOP_ATR * atr_value, entry + TARGET_ATR * atr_value
    last_close, last_row = None, None

    def done(row: int, price: float, reason: str) -> Dict[str, Any]:
        gross = price / entry - 1
        return {"signal": s, "entry_row": e, "exit_row": row, "entry": entry, "exit": float(price), "reason": reason, "gross": gross, "net": gross - cost, "days": row - e + 1, "open": False}
    for row in range(e, min(e + HOLD, len(o))):
        if np.isfinite(c[row]):
            last_close, last_row = float(c[row]), row
        if row > e and np.isfinite(o[row]):
            if o[row] <= stop:
                return done(row, float(o[row]), "STOP")
            if o[row] >= target:
                return done(row, float(o[row]), "TARGET")
        if np.isfinite(lo[row]) and lo[row] <= stop:
            return done(row, stop, "STOP")
        if np.isfinite(h[row]) and h[row] >= target:
            return done(row, target, "TARGET")
    if e + HOLD - 1 < len(o):                               # the tenth session is on file
        if last_close is None:
            return None
        return done(e + HOLD - 1, last_close, "TIME" if last_row == e + HOLD - 1 else "GONE")
    return {"signal": s, "entry_row": e, "entry": entry, "stop": stop, "target": target, "open": True, "last": last_close, "days": len(o) - e,
            "gross": None if last_close is None else last_close / entry - 1}


class Book:
    """One method's trades over time: a stock it still holds takes no new signal."""

    def __init__(self, d: Dict[str, np.ndarray], cost: float):
        self.d, self.cost = d, cost
        self.busy: Dict[int, int] = {}        # column -> the row its position leaves (a very large row while open)
        self.trades: List[Dict[str, Any]] = []

    def take(self, j: int, s: int, atr_value: float, block: int, scale: float = 1.0) -> Optional[Dict[str, Any]]:
        if s < self.busy.get(j, -1):
            return None
        d = self.d
        t = simulate(d["open"][:, j], d["high"][:, j], d["low"][:, j], d["close"][:, j], s, atr_value * scale, self.cost)
        if t is None:
            return None
        t.update({"col": j, "block": block})
        self.busy[j] = t.get("exit_row", 10 ** 9)
        self.trades.append(t)
        return t


# ---------------------------------------------------------------------- reading trades
def stats(trades: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    done = [t for t in trades if not t.get("open")]
    if not done:
        return {"trades": 0}
    net = np.array([t["net"] for t in done])
    win, loss = net[net > 0], net[net <= 0]
    reasons = {r: float(np.mean([t["reason"] == r for t in done])) for r in ("STOP", "TARGET", "TIME", "GONE")}
    return {"trades": len(done), "mean_net": float(net.mean()), "median_net": float(np.median(net)), "win_rate": float((net > 0).mean()),
            "avg_win": float(win.mean()) if len(win) else None, "avg_loss": float(loss.mean()) if len(loss) else None,
            "payoff": float(win.mean() / -loss.mean()) if len(win) and len(loss) and loss.mean() < 0 else None,
            "mean_days": float(np.mean([t["days"] for t in done])), "exits": reasons}


def by_block(trades: Sequence[Dict[str, Any]]) -> Dict[int, float]:
    out: Dict[int, List[float]] = {}
    for t in trades:
        if not t.get("open"):
            out.setdefault(t["block"], []).append(t["net"])
    return {b: float(np.mean(v)) for b, v in out.items()}


def compare(trades: Sequence[Dict[str, Any]], base: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Block by block: the method's mean net return minus the baseline's.  A block without a trade on either side is left out."""
    a, b = by_block(trades), by_block(base)
    blocks = sorted(set(a) & set(b))
    diff = [a[x] - b[x] for x in blocks]
    half = len(diff) // 2
    mean = lambda v: float(np.mean(v)) if len(v) else None          # noqa: E731
    return {"blocks": len(diff), "mean_diff": mean(diff), "t": validate.newey_west_t(diff, 1), "early": mean(diff[:half]), "late": mean(diff[half:])}


def drawdown(trades: Sequence[Dict[str, Any]], blocks: int) -> Optional[float]:
    """Largest fall of the path that puts the same money into every block's trades, equally weighted.  A block without a trade earns nothing."""
    got = by_block(trades)
    if not got:
        return None
    level, peak, worst = 1.0, 1.0, 0.0
    for b in range(blocks):
        level *= 1 + got.get(b, 0.0)
        peak = max(peak, level)
        worst = min(worst, level / peak - 1)
    return worst


def reading(name: str, trades: Sequence[Dict[str, Any]], base: Sequence[Dict[str, Any]], blocks: int) -> Dict[str, Any]:
    s, b = stats(trades), stats(base)
    out = {"method": name, "name": NAMES[name], **s, "max_drawdown": drawdown(trades, blocks)}
    if name != "B0":
        out["vs_b0"] = compare(trades, base)
        out["mean_net_minus_b0"] = None if not s["trades"] or not b["trades"] else s["mean_net"] - b["mean_net"]
    return out


def select(readings: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """The protocol's four conditions, then at most two primaries by mean net return."""
    checks = {}
    for m in METHODS:
        r = readings[m]
        v = r.get("vs_b0") or {}
        gt = lambda x, y: x is not None and x > y          # noqa: E731
        checks[m] = {"trades": r["trades"] >= MIN_TRADES, "above_b0": gt(r.get("mean_net_minus_b0"), 0),
                     "t": v.get("t") is not None and v["t"] >= calibrate.bar(SELECT_T, v.get("blocks") or 0, 1, 1, 1), "both_halves": gt(v.get("early"), 0) and gt(v.get("late"), 0)}
    passed = sorted((m for m in METHODS if all(checks[m].values())), key=lambda m: -readings[m]["mean_net"])
    return {"checks": checks, "passed": passed, "primary": passed[:MAX_PRIMARY], "verdict": "PRIMARY_NAMED" if passed else "NO_PRIMARY"}


# ---------------------------------------------------------------------- pool
def pool_of(scores: Dict[str, Optional[float]], marked: Set[str], blocked: Set[str]) -> List[str]:
    """Top fifth (rounded up) by score of the stocks that carry no mark, are not blocked and have a score.  Ties go to the lower code."""
    left = sorted(((c, s) for c, s in scores.items() if s is not None and c not in marked and c not in blocked), key=lambda x: (-x[1], x[0]))
    return [c for c, _ in left[:math.ceil(len(left) * POOL_SHARE)]] if left else []


# ---------------------------------------------------------------------- the selection run on the past
def _past_marks(base: Path) -> Dict[str, Any]:
    """The three marks on the stored 5-session grid of the earlier tests: the lowest fifth of the low risk theme and of the financial
    score among every stock that has one, and a financing decision in the last 252 sessions."""
    from terminal.qsf import research_ensemble as en, research_kr_events as re_, research_kr_fund as rf
    px = kr._load(Path(base))
    with np.load(Path(base) / kr.FEATURES) as z:
        rows, price = [int(i) for i in z["rows"]], z["tensor"]
    with np.load(Path(base) / rf.FEATURES) as z:
        fund = z["tensor"]
    with np.load(Path(base) / re_.FEATURES) as z:
        events = z["tensor"]
    low = kr.theme_ranks(price)["low_risk"]
    fin = en.combine(rf.theme_ranks(fund), kf.FUND_GROUPS)

    def bottom(x: np.ndarray) -> np.ndarray:
        out = np.zeros(x.shape, dtype=bool)
        for n in range(x.shape[0]):
            m = np.isfinite(x[n])
            if m.sum() >= 30:
                out[n, m] = validate.rank(x[n, m]) / (m.sum() - 1) <= 0.2
        return out
    return {"dates": [px.dates[i] for i in rows], "symbols": px.symbols, "high_risk": bottom(low), "weak_fund": bottom(fin),
            "financing": events[:, :, re_.SIGNALS.index("financing")] == 1}


def marked_on(marks: Dict[str, Any], day: str) -> Set[str]:
    """Codes carrying any mark on the newest grid day not after ``day``."""
    n = int(np.searchsorted(marks["dates"], day, side="right")) - 1
    if n < 0:
        return set()
    any_ = marks["high_risk"][n] | marks["weak_fund"][n] | marks["financing"][n]
    return {marks["symbols"][j] for j in np.flatnonzero(any_)}


def past_score(rec: Dict[str, Any]) -> Optional[float]:
    f, r = rec.get("SWING|FUNDAMENTAL"), rec.get("SWING|RISK")
    return None if f is None or r is None else (WEIGHT_FUND * f + WEIGHT_RISK * r) / (WEIGHT_FUND + WEIGHT_RISK)


def run_selection(d: Dict[str, np.ndarray], col: Dict[str, int], dates: Sequence[str], eval_rows: Sequence[int], by_row: Dict[int, List[Dict[str, Any]]],
                  marked: Callable[[str], Set[str]], cost: float, log=lambda m: None) -> Dict[str, Any]:
    """Every method and both baselines over the stored evaluation days.  A trade whose ten sessions run past the data is not opened."""
    books = {m: Book(d, cost) for m in METHODS + BASELINES}
    last_signal = len(dates) - 1 - HOLD                  # the last row whose ten sessions are all on file
    block = 0
    pools = []
    for n, e in enumerate(eval_rows):
        recs = [r for r in by_row.get(e, []) if r["t"] in col]
        uni = [r["t"] for r in recs]
        cols = np.array([col[t] for t in uni], dtype=int)
        pool = set(pool_of({r["t"]: past_score(r) for r in recs}, marked(dates[e]), set()))
        pools.append({"date": dates[e], "universe": len(uni), "pool": len(pool)})
        end = eval_rows[n + 1] if n + 1 < len(eval_rows) else min(e + 21, len(dates))
        for start, stop in ((e, min(e + HOLD, end)), (min(e + HOLD, end), end)):
            for s in range(start, min(stop, last_signal + 1)):
                a = atr(d, s, cols)
                if s == start:
                    for k, t in enumerate(uni):
                        books["B00"].take(int(cols[k]), s, float(a[k]), block)
                        if t in pool:
                            books["B0"].take(int(cols[k]), s, float(a[k]), block)
                sig = signals(d, s, cols)
                for m in METHODS:
                    for k in np.flatnonzero(sig[m]):
                        if uni[k] in pool:
                            books[m].take(int(cols[k]), s, float(a[k]), block)
            block += 1
        if n % 10 == 0:
            log(f"{n}/{len(eval_rows)} {dates[e]}")
    readings = {m: reading(m, books[m].trades, books["B0"].trades, block) for m in METHODS + BASELINES}
    for m in METHODS + BASELINES:
        years: Dict[str, List[float]] = {}
        for t in books[m].trades:
            years.setdefault(dates[t["entry_row"]][:4], []).append(t["net"])
        readings[m]["by_year"] = {y: {"trades": len(v), "mean_net": float(np.mean(v))} for y, v in sorted(years.items())}
    return {"blocks": block, "first": dates[eval_rows[0]], "last_signal": dates[last_signal], "pools": pools, "readings": readings, **select(readings)}


def select_once(base: Path, log=print) -> Dict[str, Any]:
    """The one selection run.  A stored result is returned as it is."""
    from terminal.qsf import research_kr_live as rl
    path = Path(base) / SELECTION
    if path.exists():
        return {**json.loads(path.read_text(encoding="utf-8")), "status": "ALREADY_RUN"}
    px = rl.load_panel(Path(base))
    with gzip.open(rl._scores_path(Path(base), "cap"), "rt", encoding="utf-8") as fh:
        stored = json.load(fh)
    if list(stored["dates"]) != px.dates[:len(stored["dates"])]:
        raise ValueError("the stored scores were made on another panel")
    by_row: Dict[int, List[Dict[str, Any]]] = {}
    for r in stored["records"]:
        by_row.setdefault(int(r["i"]), []).append(r)
    marks = _past_marks(Path(base))
    cost = config.round_trip_cost("KR")
    res = run_selection(px.data, px.col, px.dates, [int(i) for i in stored["rows"]], by_row, lambda day: marked_on(marks, day), cost, log)
    doc = {"status": "REAL", "protocol": PROTOCOL, "ran_at": datetime.now(timezone.utc).isoformat(), "cost_round_trip": cost, "hold": HOLD, "stop_atr": STOP_ATR,
           "target_atr": TARGET_ATR, "min_trades": MIN_TRADES, "select_t": SELECT_T,
           "note": "선발용 수치입니다. 9개 중 고른 결과이고 이미 본 구간이라 실제보다 좋게 나옵니다. 근거가 아닙니다.", **res}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return doc


def primaries(base: Path) -> List[str]:
    try:
        return list(json.loads((Path(base) / SELECTION).read_text(encoding="utf-8")).get("primary") or [])
    except (OSError, ValueError):
        return []


# ---------------------------------------------------------------------- the daily record
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _prices(base: Path, first: str, last: str) -> Dict[str, np.ndarray]:
    return kr.build_prices(Path(base) / kr.DATA, log=lambda m: None, days=list(kh.weekdays(first, last)))


def _back(day: str, weekdays: int) -> str:
    return (date.fromisoformat(day) - timedelta(days=weekdays * 7 // 5 + 7)).isoformat()


def live_rows(led: Ledger, session: str) -> List[Dict[str, Any]]:
    """The Korean swing snapshots of one session, as the screen showed them."""
    out = []
    for r in led._live_rows():
        if r["market"] == "KR" and r["session"] == session:
            out += [s for s in led._load(r) if s.get("strategy") == "SWING"]
    return out


def build_doc(session: str, snaps: List[Dict[str, Any]], marks: Dict[str, Set[str]], z: Dict[str, np.ndarray], order: int, grades: Optional[Dict[str, Dict[str, Any]]]) -> Dict[str, Any]:
    """What the method saw at the close of ``session``.  No return is read and none is stored."""
    i = len(z["dates"]) - 1
    if i < 0 or str(z["dates"][i]) != session:
        raise NotReady("NO_PRICES_FOR_DAY")
    col = {str(s): j for j, s in enumerate(z["symbols"])}
    snaps = sorted((s for s in snaps if s["ticker"] in col), key=lambda s: s["ticker"])
    scores = {s["ticker"]: (float(s["score"]) if s.get("score") is not None and s.get("actionability") != "INSUFFICIENT_DATA" and s.get("data_date") == session else None) for s in snaps}
    if sum(v is not None for v in scores.values()) < MIN_ROWS:
        raise NotReady("TOO_FEW_SCORES")
    blocked = {s["ticker"] for s in snaps if any((g.get("code") if isinstance(g, dict) else g) == BLOCKED for g in (s.get("gates") or []))}
    marked = {c for c in scores if c in marks["known"] and c in marks["any"]}
    pool = set(pool_of(scores, marked, blocked))
    codes = [s["ticker"] for s in snaps]
    cols = np.array([col[c] for c in codes], dtype=int)
    sig, a = signals(z, i, cols), atr(z, i, cols)
    rows = []
    for k, c in enumerate(codes):
        close = float(z["close"][i, cols[k]])
        row = {"code": c, "score": None if scores[c] is None else round(scores[c], 3), "marks": [m for m in kr_avoid_marks.MARKS if c in marks[m]] if c in marks["known"] else None,
               "blocked": c in blocked, "pool": c in pool, "signals": [m for m in METHODS if sig[m][k]], "close": close if np.isfinite(close) else None,
               "atr": float(a[k]) if np.isfinite(a[k]) else None}
        if grades is not None and c in grades:
            row["risk"] = grades[c]
        rows.append(row)
    return {"session": session, "protocol": PROTOCOL, "order": order, "baseline_entry": order % HOLD == 0, "model_versions": sorted({s.get("model_version") for s in snaps if s.get("model_version")}),
            "universe": len(rows), "pool": len(pool), "signals": {m: [r["code"] for r in rows if r["pool"] and m in r["signals"]] for m in METHODS}, "rows": rows}


def score_day(base: Path, day: str) -> Dict[str, Any]:
    """The scorer ``kr_forward.write_record`` calls: everything is read as of ``day``."""
    base = Path(base)
    marks = kr_avoid_marks.marks_of(base, day)
    if marks is None:
        raise NotReady("MARKS_NOT_RECORDED")
    snaps = live_rows(Ledger(base), day)
    z = _prices(base, _back(day, WINDOW), day)
    i = len(z["dates"]) - 1
    grades = kr_risk_grade.day_grades(z, i) if i >= 0 and kr_risk_grade.supported(base) else None
    return build_doc(day, snaps, marks, z, len(kf.read_index(base, FOLDER)), grades)


def record(base: Path, now: Callable[[], datetime] = _utcnow, first: str = FIRST) -> Dict[str, Any]:
    """Write every live Korean session from ``first`` on that is not recorded yet, oldest first.  A day whose marks or prices are not
    there yet stops the run, so the record keeps the order of the sessions."""
    base = Path(base)
    led = Ledger(base)
    sessions = sorted({r["session"] for r in led._live_rows() if r["market"] == "KR" and r["session"] >= first})
    done = {r["session"] for r in kf.read_index(base, FOLDER)}
    at = now()
    wrote, waiting, partial = [], None, []
    for n, day in enumerate(sessions):
        if day in done:
            continue
        try:
            if kf.write_record(base, day, at, n < len(sessions) - 1, store=FOLDER, scorer=score_day):
                wrote.append(day)
        except NotReady as e:
            if str(e) == "TOO_FEW_SCORES":          # a partial live day: it is asked again every run and never holds the later days back
                partial.append(day)
                continue
            waiting = {"session": day, "reason": str(e)}
            break
    last = max(done | set(wrote), default=None)
    return {"status": "WAITING" if waiting else "OK", "written": wrote, "last": last, "waiting": waiting, "partial_days": partial, "sessions": len(done) + len(wrote)}


# ---------------------------------------------------------------------- following the record
def follow(docs: List[Dict[str, Any]], z: Dict[str, np.ndarray], cost: float) -> Dict[str, Any]:
    """Every recorded signal followed on the prices on file.  ``docs`` are in record order.  The ATR of a record is on that day's price
    basis, so it is rescaled by the close of the same day on this build."""
    dates = [str(x) for x in z["dates"]]
    row_of = {day: n for n, day in enumerate(dates)}
    col = {str(s): j for j, s in enumerate(z["symbols"])}
    books = {m: Book(z, cost) for m in METHODS + BASELINES}
    for doc in docs:
        s = row_of.get(doc["session"])
        if s is None:
            continue
        block = doc["order"] // HOLD
        for r in doc["rows"]:
            j = col.get(r["code"])
            if j is None or r.get("atr") is None or not r.get("close"):
                continue
            now = float(z["close"][s, j])
            scale = now / r["close"] if np.isfinite(now) else float("nan")
            if doc["baseline_entry"]:
                books["B00"].take(j, s, r["atr"], block, scale)
                if r["pool"]:
                    books["B0"].take(j, s, r["atr"], block, scale)
            if r["pool"]:
                for m in r["signals"]:
                    books[m].take(j, s, r["atr"], block, scale)
    symbols = [str(s) for s in z["symbols"]]
    for b in books.values():
        for t in b.trades:
            t["code"], t["signal_day"] = symbols[t["col"]], dates[t["signal"]]
            t["entry_day"] = dates[t["entry_row"]]
            if not t.get("open"):
                t["exit_day"] = dates[t["exit_row"]]
    return {m: b.trades for m, b in books.items()}


def matured(docs: List[Dict[str, Any]], dates: Sequence[str]) -> List[str]:
    """Recorded sessions whose ten holding sessions have all ended on the calendar ``dates``."""
    where = {d: n for n, d in enumerate(dates)}
    return [d["session"] for d in docs if d["session"] in where and where[d["session"]] + HOLD < len(dates)]


def _docs(base: Path) -> List[Dict[str, Any]]:
    folder = Path(base) / FOLDER
    return [kf._read_day(folder, r["session"]) for r in kf.read_index(base, FOLDER)]


def progress(base: Path) -> Dict[str, Any]:
    """The running view for the screen: counts and what the followed trades did so far.  Not a verdict and not a record."""
    base = Path(base)
    docs = _docs(base)
    out: Dict[str, Any] = {"status": "NO_RECORD", "protocol": PROTOCOL, "first": FIRST, "primary": primaries(base), "read_at": list(READ_AT), "names": NAMES, "family": FAMILY}
    if not docs:
        return out
    last = docs[-1]
    z = _prices(base, _back(docs[0]["session"], 30), kf.read_index(base)[-1]["session"] if kf.read_index(base) else last["session"])
    dates = [str(x) for x in z["dates"]]
    trades = follow(docs, z, config.round_trip_cost("KR"))
    blocks = last["order"] // HOLD + 1
    methods = {}
    for m in METHODS + BASELINES:
        r = reading(m, trades[m], trades["B0"], blocks)
        r["open"] = [{"code": t["code"], "entry_day": t["entry_day"], "entry": t["entry"], "days": t["days"], "gross": t["gross"]} for t in trades[m] if t.get("open")][:50]
        r["open_count"] = sum(1 for t in trades[m] if t.get("open"))
        r["signals_recorded"] = sum(len(d["signals"].get(m, [])) for d in docs) if m in METHODS else None
        r["today"] = last["signals"].get(m, []) if m in METHODS else None
        methods[m] = r
    out.update({"status": "REAL", "sessions": len(docs), "matured": len(matured(docs, dates)), "last": last["session"], "prices_to": dates[-1] if dates else None,
                "universe": last["universe"], "pool": last["pool"], "pool_codes": [r["code"] for r in last["rows"] if r["pool"]], "methods": methods,
                "note": "판정 전 참고입니다. 판정은 보유가 끝난 신호일 120개와 240개에서 한 번씩만 합니다." if out["primary"] else
                        "판정 전 참고입니다. 선발에서 주력이 정해지지 않아 판정은 없고, 보유가 끝난 신호일 120개와 240개에서 수치만 한 번씩 보고합니다."})
    return out


def write_status(base: Path) -> Dict[str, Any]:
    """Rebuild the view file the screen reads.  It can be thrown away and rebuilt: the record is the source."""
    doc = {**progress(base), "built_at": _utcnow().isoformat()}
    p = Path(base) / STATUS
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)
    return doc


def status(base: Path) -> Dict[str, Any]:
    try:
        return json.loads((Path(base) / STATUS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "NO_RECORD", "protocol": PROTOCOL, "first": FIRST, "primary": primaries(base), "read_at": list(READ_AT), "names": NAMES, "family": FAMILY}


def risk_view(base: Path) -> Dict[str, Any]:
    """The risk grade of the newest recorded session with the stored test's numbers next to it.  ``top_fifth`` is the reading that
    was tested: the riskiest fifth inside the day's universe."""
    base = Path(base)
    out: Dict[str, Any] = {"status": "UNAVAILABLE", "protocol": kr_risk_grade.PROTOCOL, "rows": {}}
    if not kr_risk_grade.supported(base):
        return out
    index = kf.read_index(base, FOLDER)
    if not index:
        return {**out, "status": "NO_RECORD"}
    doc = kf._read_day(base / FOLDER, index[-1]["session"])
    got = [(r["code"], r["risk"]) for r in doc["rows"] if r.get("risk") and r["risk"].get("score") is not None]
    if len(got) < 30:
        return {**out, "status": "NO_RECORD"}
    q = validate.rank(np.array([v["score"] for _, v in got], dtype=float)) / (len(got) - 1)
    test = json.loads((base / kr_risk_grade.REPORT).read_text(encoding="utf-8"))["primary"]
    return {"status": "REAL", "protocol": kr_risk_grade.PROTOCOL, "session": doc["session"], "names": kr_risk_grade.GRADE_NAMES,
            "rows": {c: {**v, "top_fifth": bool(x >= 0.8)} for (c, v), x in zip(got, q)},
            "test": {"pair_win": test["pair_win"], "loss_top": test["big_loss"]["top"], "loss_all": test["big_loss"]["all"],
                     "drawdown_top": test["drawdown"]["top"], "drawdown_bottom": test["drawdown"]["bottom"], "first": test["first"], "last": test["last"]}}


# ---------------------------------------------------------------------- the two readings of the record
def forward_report(base: Path, n: int) -> Path:
    return Path(base) / "reports" / "qsf" / f"QSF_KR_METHOD_FORWARD_{n}.json"


def evaluate_once(base: Path, n: int, log=print) -> Dict[str, Any]:
    """The reading at ``n`` matured signal days (120 or 240), once.  Only the first ``n`` matured days are used."""
    if n not in READ_AT:
        raise ValueError(f"readings are fixed at {READ_AT}")
    base = Path(base)
    path = forward_report(base, n)
    if path.exists():
        return {**json.loads(path.read_text(encoding="utf-8")), "status": "ALREADY_RUN"}
    docs = _docs(base)
    if not docs:
        return {"status": "NOT_READY", "matured": 0, "needed": n}
    price_days = kf.read_index(base)
    z = _prices(base, _back(docs[0]["session"], 30), price_days[-1]["session"] if price_days else docs[-1]["session"])
    dates = [str(x) for x in z["dates"]]
    ready = matured(docs, dates)
    if len(ready) < n:
        return {"status": "NOT_READY", "matured": len(ready), "needed": n}
    used = [d for d in docs if d["session"] in set(ready[:n])]
    trades = follow(used, z, config.round_trip_cost("KR"))
    trades = {m: [t for t in v if not t.get("open")] for m, v in trades.items()}
    blocks = used[-1]["order"] // HOLD + 1
    readings = {m: reading(m, trades[m], trades["B0"], blocks) for m in METHODS + BASELINES}
    prim = primaries(base)
    verdicts = {}
    for m in prim:
        r, v = readings[m], readings[m].get("vs_b0") or {}
        ok = r["trades"] > 0 and r["mean_net"] > 0 and (r.get("mean_net_minus_b0") or 0) > 0 and v.get("t") is not None and v["t"] >= calibrate.bar(VERDICT_T, v.get("blocks") or 0, 1, 1, 1)
        verdicts[m] = "METHOD_SUPPORTED" if ok else "NOT_DISTINGUISHED"
    versions: Dict[str, int] = {}
    for d in used:
        for v in d.get("model_versions") or []:
            versions[v] = versions.get(v, 0) + 1
    doc = {"status": "REAL", "protocol": PROTOCOL, "ran_at": _utcnow().isoformat(), "signal_days": n, "first": used[0]["session"], "last": used[-1]["session"],
           "primary": prim, "verdict": verdicts if prim else "NO_PRIMARY", "readings": readings, "model_version_days": versions, "cost_round_trip": config.round_trip_cost("KR")}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return doc
