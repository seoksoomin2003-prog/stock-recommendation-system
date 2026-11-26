"""Domain weights that follow the market state: a challenger kept apart from the live score.  Rules: reports/QSF_REGIME_WEIGHTS_PROTOCOL.md.

The market is put in one of three states from its index alone.  For each state the weights of the technical, fundamental and risk
domains lean toward the domains that ranked stocks well in that state before.  The past test walks forward: the weights used on a
day come only from days whose 20-session outcome had already ended (``walkforward``).  It runs once per market on stored scores.
The table fitted on every past day is then frozen and written down every session beside the live score.  Nothing here reads into or
changes the live score, the QSF ledger or P6-11B.
"""
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from terminal.qsf import config, kr_forward as kf, validate, walkforward
from terminal.qsf.ledger import Ledger
from utils import durable
from terminal.qsf import ledger as ledger_mod

PROTOCOL = "reports/QSF_REGIME_WEIGHTS_PROTOCOL.md"
REPORT = Path("reports") / "qsf" / "QSF_REGIME_WEIGHTS.json"
FOLDERS = {"KR": Path("research_data") / "regime_weights_kr", "US": Path("research_data") / "regime_weights_us"}
FORWARD_REPORTS = {m: Path("reports") / "qsf" / f"QSF_REGIME_WEIGHTS_FORWARD_{m}.json" for m in ("KR", "US")}
FIRST = "2026-11-12"            # the first session written down; the table is frozen before its outcome exists
STATES = ("UP_CALM", "UP_ROUGH", "DOWN")
STATE_LABELS = {"UP_CALM": "상승·안정", "UP_ROUGH": "상승·불안", "DOWN": "하락"}
DOMAINS = ("TECHNICAL", "FUNDAMENTAL", "RISK")
STRATEGY = "SWING"
TREND_N = 200                   # sessions of the average the index is compared with
VOL_N = 20                      # sessions of daily moves in one volatility reading
VOL_REF_N, VOL_REF_MIN = 400, 252       # earlier readings the current one is compared with: at most, at least
H = 20                          # the swing outcome: next open to the 20th close
MIN_TRAIN = 24                  # past days with a finished outcome before a day is tested (about two years)
MIN_STATE = 12                  # past days in the same state before that state's weights are fitted; fewer keeps the fixed weights
SHRINK = 0.5                    # half the fixed weights, half the fitted ones
MIN_T = 2.24                    # two markets are tested
MIN_STOCKS = 30
MIN_ROWS = 200                  # a recorded session with fewer scored stocks is a partial day
READ_AT = 240                   # matured sessions at the single forward reading
COUNTED = ("REAL", "STALE")
LIMITS = ["과거 점수에는 시장 국면 영역과 이벤트·지배구조 영역이 없습니다. 세 영역(기술·재무·위험)만으로 비교했습니다.",
          "이미 여러 번 쓴 구간입니다. 영역별 과거 성적(예: 한국 기술 영역 음수)을 아는 상태에서 설계했으므로 독립된 새 증거가 아닙니다.",
          "미국 표본은 지수에서 빠진 종목 일부가 없어 결과가 부풀려질 수 있습니다.",
          "한국의 국면은 과거 시험과 매일 기록 모두 KRX 자료로 만든 코스피 시가총액 지수로 정합니다(공식 코스피 지수와 조금 다를 수 있습니다).",
          "평가일이 21거래일 간격이라 한국은 약 60개, 미국은 약 120개의 시험일뿐입니다. 작은 효과는 잡지 못합니다."]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def static_weights(market: str) -> np.ndarray:
    """The live swing points of the three domains, as shares.  Korea's technical domain is reference only, so its share is zero."""
    p = config.profile_for(market, STRATEGY)["domains"]
    w = np.array([float(sum((p.get(k) or {}).values())) for k in DOMAINS])
    return w / w.sum()


# ---------------------------------------------------------------------- the market state
def state(closes: np.ndarray, i: int) -> Optional[str]:
    """The state at the close of row ``i``.  Reads nothing after ``i``.  None: too little history, or a gap in the trend window."""
    if i + 1 < max(TREND_N, VOL_N + 1 + VOL_REF_MIN) or i >= len(closes):
        return None
    trend = np.asarray(closes[i - TREND_N + 1:i + 1], dtype=float)
    if not (np.isfinite(trend).all() and (trend > 0).all()):
        return None
    past = np.asarray(closes[max(0, i - VOL_REF_N - VOL_N):i + 1], dtype=float)
    past = past[np.isfinite(past) & (past > 0)]
    if len(past) < VOL_N + 1 + VOL_REF_MIN:
        return None
    vol = np.lib.stride_tricks.sliding_window_view(np.diff(np.log(past)), VOL_N).std(axis=-1)
    if trend[-1] <= trend.mean():
        return "DOWN"
    return "UP_CALM" if vol[-1] <= float(np.median(vol[:-1])) else "UP_ROUGH"


# ---------------------------------------------------------------------- one day
def composite(dom: np.ndarray, w: np.ndarray) -> np.ndarray:
    """The weighted mean of the domain scores a stock has.  A stock missing a domain is scored on the rest; NaN when no weight is left."""
    have = np.isfinite(dom) & (w > 0)
    total = (have * w).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(have, dom, 0.0) @ w / total
    out[total <= 0] = np.nan
    return out


def _ic(score: np.ndarray, ret: np.ndarray) -> Optional[float]:
    ok = np.isfinite(score) & np.isfinite(ret)
    if ok.sum() < MIN_STOCKS or score[ok].std() == 0 or ret[ok].std() == 0:
        return None
    return float(np.corrcoef(validate.rank(score[ok]), validate.rank(ret[ok]))[0, 1])


def domain_ics(dom: np.ndarray, ret: np.ndarray) -> np.ndarray:
    return np.array([np.nan if (x := _ic(dom[:, k], ret)) is None else x for k in range(len(DOMAINS))])


def fitted(ics: Sequence[np.ndarray], static: np.ndarray) -> Tuple[np.ndarray, str]:
    """Weights from the domains' mean rank correlations on the given past days.  A domain that ranked the wrong way gets no fitted
    weight, never a negative one.  Too few days, or no domain above zero, keeps the fixed weights."""
    if len(ics) < MIN_STATE:
        return static, "STATIC_TOO_FEW"
    stack = np.vstack(ics)
    have = np.isfinite(stack)
    mean = np.where(have.any(axis=0), np.where(have, stack, 0.0).sum(axis=0) / np.maximum(have.sum(axis=0), 1), 0.0)       # a domain never read counts as zero
    raw = np.clip(mean, 0.0, None)
    if raw.sum() <= 0:
        return static, "STATIC_NO_POSITIVE"
    return SHRINK * static + (1 - SHRINK) * raw / raw.sum(), "FITTED"


def _spread(score: np.ndarray, ret: np.ndarray, cost: float) -> Optional[float]:
    ok = np.isfinite(score) & np.isfinite(ret)
    if ok.sum() < MIN_STOCKS:
        return None
    q = validate.rank(score[ok]) / (ok.sum() - 1)
    r = ret[ok]
    return float(r[q >= 0.8].mean() - r[q <= 0.2].mean() - cost)


# ---------------------------------------------------------------------- the walk-forward test
def evaluate(days: List[Dict[str, Any]], market: str, detail: bool = False) -> Dict[str, Any]:
    """``days``: in date order, each with ``row``, ``date``, ``state``, ``dom`` (stocks x domains) and ``ret`` (20-session outcome,
    NaN when unknown).  Days without a state or without an outcome are left out before the walk.  ``detail`` adds each test day."""
    static, cost = static_weights(market), config.round_trip_cost(market)
    days = [d for d in days if d["state"] in STATES and int(np.isfinite(d["ret"]).sum()) >= MIN_STOCKS]
    rows = [d["row"] for d in days]
    ics = [domain_ics(d["dom"], d["ret"]) for d in days]

    def apply(train: List[int], k: int) -> Dict[str, Any]:
        d = days[k]
        w_state, how = fitted([ics[j] for j in train if days[j]["state"] == d["state"]], static)
        w_all, _ = fitted([ics[j] for j in train], static)
        out: Dict[str, Any] = {"date": d["date"], "state": d["state"], "how": how, "weights": w_state.tolist()}
        for name, w in (("static", static), ("dynamic", w_state), ("control", w_all)):
            s = composite(d["dom"], w)
            out[name] = {"ic": _ic(s, d["ret"]), "spread_net": _spread(s, d["ret"], cost)}
        return out
    got, log = walkforward.walk(rows, H, MIN_TRAIN, lambda train: train, apply)
    tested = [got[k] for k in sorted(got) if all(got[k][n]["ic"] is not None for n in ("static", "dynamic", "control"))]
    final = {s: dict(zip(("weights", "how"), fitted([ics[j] for j in range(len(days)) if days[j]["state"] == s], static))) for s in STATES}
    out = {"market": market, "days": len(days), "first": days[0]["date"] if days else None, "last": days[-1]["date"] if days else None, "cost_round_trip": cost,
           "static": dict(zip(DOMAINS, static.tolist())), "leak_free": walkforward.leak_free(log, H), "folds": len(log), "first_train": log[0]["train"] if log else None,
           "final_table": {s: {"how": v["how"], "weights": dict(zip(DOMAINS, np.asarray(v["weights"]).tolist())), "days": sum(1 for d in days if d["state"] == s)} for s, v in final.items()},
           **summarize(tested)}
    if detail:
        out["rows"] = tested
    return out


def _mean(x: Sequence[Optional[float]]) -> Optional[float]:
    v = [a for a in x if a is not None]
    return float(np.mean(v)) if v else None


def summarize(tested: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(tested) < 2 * MIN_STATE:
        return {"status": "TOO_FEW_TEST_DAYS", "tested": len(tested), "verdict": "NOT_TESTED", "conditions": []}
    diff = [r["dynamic"]["ic"] - r["static"]["ic"] for r in tested]
    over = [r["dynamic"]["ic"] - r["control"]["ic"] for r in tested]
    mid = len(tested) // 2
    t = validate.newey_west_t(diff, 1)
    spread = {n: _mean([r[n]["spread_net"] for r in tested]) for n in ("static", "dynamic", "control")}
    ic = {n: float(np.mean([r[n]["ic"] for r in tested])) for n in ("static", "dynamic", "control")}
    early, late = float(np.mean(diff[:mid])), float(np.mean(diff[mid:]))
    conditions = [
        {"id": "DIFF_T", "label": "국면 가중치의 순위 상관이 고정 가중치보다 높음", "need": f"평균 차이 > 0, t ≥ {MIN_T}", "value": {"diff": float(np.mean(diff)), "t": t},
         "passed": bool(np.mean(diff) > 0 and t is not None and t >= MIN_T)},
        {"id": "BOTH_HALVES", "label": "전반·후반 모두 높음", "need": "두 구간 모두 차이 > 0", "value": {"early": early, "late": late}, "passed": bool(early > 0 and late > 0)},
        {"id": "OVER_CONTROL", "label": "국면을 나누지 않은 다시 가중보다 높음", "need": "평균 차이 > 0", "value": {"diff": float(np.mean(over))}, "passed": bool(np.mean(over) > 0)},
        {"id": "SPREAD", "label": "상위 20% − 하위 20% 순수익이 고정 가중치 이상", "need": "국면 ≥ 고정", "value": {"dynamic": spread["dynamic"], "static": spread["static"]},
         "passed": bool(spread["dynamic"] is not None and spread["static"] is not None and spread["dynamic"] >= spread["static"])}]
    by_state = {}
    for s in STATES:
        g = [r for r in tested if r["state"] == s]
        by_state[s] = {"days": len(g), "fitted_share": float(np.mean([r["how"] == "FITTED" for r in g])) if g else None,
                       "ic": {n: _mean([r[n]["ic"] for r in g]) for n in ("static", "dynamic", "control")},
                       "mean_weights": dict(zip(DOMAINS, np.mean([r["weights"] for r in g], axis=0).tolist())) if g else None}
    return {"status": "REAL", "tested": len(tested), "test_first": tested[0]["date"], "test_last": tested[-1]["date"], "split": tested[mid]["date"],
            "ic": ic, "ic_diff": float(np.mean(diff)), "ic_diff_t": t, "ic_diff_positive_share": float(np.mean([x > 0 for x in diff])), "ic_over_control": float(np.mean(over)),
            "spread_net": spread, "fitted_share": float(np.mean([r["how"] == "FITTED" for r in tested])), "by_state": by_state, "conditions": conditions,
            "verdict": "REGIME_WEIGHTS_SUPPORTED" if all(c["passed"] for c in conditions) else "NOT_SUPPORTED"}


# ---------------------------------------------------------------------- stored scores of the two markets
def _days(records: List[Dict[str, Any]], dates: Sequence[str], col: Dict[str, int], forward: Callable[[int, int], np.ndarray], index: np.ndarray) -> List[Dict[str, Any]]:
    by_i: Dict[int, List[Dict[str, Any]]] = {}
    for r in records:
        by_i.setdefault(int(r["i"]), []).append(r)
    out = []
    for i in sorted(by_i):
        g = [r for r in by_i[i] if r["t"] in col]
        fwd = forward(i, H)
        dom = np.array([[np.nan if r.get(f"{STRATEGY}|{k}") is None else float(r[f"{STRATEGY}|{k}"]) for k in DOMAINS] for r in g], dtype=float).reshape(len(g), len(DOMAINS))
        ret = np.array([fwd[col[r["t"]]] for r in g], dtype=float)
        out.append({"row": i, "date": dates[i], "state": state(index, i), "dom": dom, "ret": ret})
    return out


def kr_days(base: Path) -> List[Dict[str, Any]]:
    from terminal.qsf import research_kr_live as live
    px = live.load_panel(base)
    with gzip.open(live._scores_path(base, "cap"), "rt", encoding="utf-8") as fh:
        stored = json.load(fh)
    return _days(stored["records"], px.dates, px.col, lambda i, h: px.forward(i, h), px.data["close"][:, px.col[live.BOARD_INDEX["KOSPI"]]].astype(float))


def us_days(base: Path) -> List[Dict[str, Any]]:
    from terminal.qsf import validate_open
    root = Path(base) / "data" / "qsf" / "research"
    px = validate_open.OpenPrices(root / "prices15y_open.npz", validate_open.load_universe(Path(base)))
    with gzip.open(root / "scores_corrected_open.json.gz", "rt", encoding="utf-8") as fh:
        stored = json.load(fh)
    return _days(stored["records"], px.dates, px.col, lambda i, h: px.forward(i, h), px.data["adj_close"][:, px.col["SPY"]].astype(float))


def run_once(base: Path, log=print, loaders: Optional[Dict[str, Callable[[Path], List[Dict[str, Any]]]]] = None) -> Dict[str, Any]:
    """The single run.  A second call returns the stored report and computes nothing."""
    path = Path(base) / REPORT
    if path.exists():
        return {**json.loads(path.read_text(encoding="utf-8")), "status": "ALREADY_RUN"}
    loaders = loaders or {"KR": kr_days, "US": us_days}
    markets = {}
    for market, load in loaders.items():
        log(f"{market}: reading stored scores")
        markets[market] = evaluate(load(Path(base)), market)
        log(f"{market}: {markets[market].get('verdict')} ({markets[market].get('tested')} test days)")
    doc = {"status": "REAL", "protocol": PROTOCOL, "run_at": _utcnow().isoformat(), "horizon": H, "strategy": STRATEGY, "domains": list(DOMAINS), "states": list(STATES),
           "settings": {"trend_n": TREND_N, "vol_n": VOL_N, "vol_ref_n": VOL_REF_N, "min_train": MIN_TRAIN, "min_state": MIN_STATE, "shrink": SHRINK, "min_t": MIN_T},
           "markets": markets, "limits": LIMITS}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


def table(base: Path) -> Optional[Dict[str, Dict[str, Any]]]:
    """The frozen table of the single run, by market and state; None before the run."""
    try:
        doc = json.loads((Path(base) / REPORT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {m: v["final_table"] for m, v in doc["markets"].items() if v.get("final_table")}


# ---------------------------------------------------------------------- the daily record
class NotReady(Exception):
    """A session that cannot be written yet and is asked again at the next run."""


def index_state(bars: Sequence[Dict[str, Any]], session: str) -> str:
    """The state at ``session`` from index bars; the last bar must be that session, so a day the index has not published waits."""
    rows = [b for b in bars if b.get("date") and b["date"] <= session and (b.get("adj_close") or b.get("close"))]
    if not rows or rows[-1]["date"] != session:
        raise NotReady("INDEX_NOT_AT_SESSION")
    s = state(np.array([float(b.get("adj_close") or b["close"]) for b in rows]), len(rows) - 1)
    if s is None:
        raise NotReady("INDEX_HISTORY_SHORT")
    return s


KR_INDEX_WEEKDAYS = 460         # weekdays of KRX files read back for the Korean index: the trend and volatility windows with room for holidays


def kospi_index(z: Dict[str, Any]) -> List[Dict[str, Any]]:
    """A capitalisation-weighted KOSPI index on the previous day's weights, from KRX price arrays: the construction the past test
    used (``research_kr_live.add_index``).  One bar per day on file."""
    a, cap, member = z["adj_close"].astype(float), z["cap"].astype(float), np.asarray(z["kospi"], dtype=bool)
    level, out = 1000.0, []
    for i, day in enumerate(z["dates"]):
        if i:
            prev, cur, w = a[i - 1], a[i], cap[i - 1]
            ok = member & np.isfinite(prev) & np.isfinite(cur) & np.isfinite(w) & (w > 0) & (prev > 0)
            if ok.any():
                level *= 1 + float(np.sum(w[ok] * (cur[ok] / prev[ok] - 1)) / np.sum(w[ok]))
        out.append({"date": str(day), "close": level})
    return out


def kr_index_bars(base: Path, now: Callable[[], datetime] = _utcnow) -> List[Dict[str, Any]]:
    """The Korean index bars up to the newest KRX day on file.  A session KRX has not published is simply not in them yet."""
    from datetime import timedelta
    from terminal.qsf import kr_method
    last = (now() + timedelta(hours=9)).date()
    first = last - timedelta(days=int(KR_INDEX_WEEKDAYS * 7 / 5) + 10)
    return kospi_index(kr_method._prices(Path(base), first.isoformat(), last.isoformat()))


def _snapshot_scores(s: Dict[str, Any]) -> np.ndarray:
    d = s.get("domains") or {}
    return np.array([float(d[k]["score_100"]) if d.get(k) and d[k].get("score_100") is not None and (d[k].get("coverage") or 0) > 0 else np.nan for k in DOMAINS])


def score_session(snaps: List[Dict[str, Any]], session: str, market: str, st: str, weights: Dict[str, Any]) -> Dict[str, Any]:
    """The three-domain composite of every stock scored on ``session`` under the state's frozen weights and under the fixed ones."""
    fresh = sorted((s for s in snaps if s.get("strategy") == STRATEGY and s.get("data_date") == session and s.get("score") is not None), key=lambda s: s["ticker"])
    if len(fresh) < MIN_ROWS:
        raise NotReady("TOO_FEW_STOCKS")
    dom = np.vstack([_snapshot_scores(s) for s in fresh])
    w = np.array([float(weights["weights"][k]) for k in DOMAINS])
    dyn, fixed = composite(dom, w), composite(dom, static_weights(market))
    rows = [{"ticker": s["ticker"], "score": None if not np.isfinite(dyn[n]) else round(float(dyn[n]), 3), "static": None if not np.isfinite(fixed[n]) else round(float(fixed[n]), 3),
             "live": round(float(s["score"]), 3), "entry_session": s.get("entry_session"), "actionability": s.get("actionability")} for n, s in enumerate(fresh)]
    return {"session": session, "market": market, "protocol": PROTOCOL, "state": st, "how": weights["how"], "weights": {k: float(weights["weights"][k]) for k in DOMAINS},
            "model_versions": sorted({str(s.get("model_version")) for s in fresh}), "rows": rows}


def _session_snaps(led: Ledger, market: str, session: str) -> List[Dict[str, Any]]:
    return ledger_mod.session_snaps(led, market, session)


def record(base: Path, market: str, index_bars: Callable[[], Sequence[Dict[str, Any]]], now: Callable[[], datetime] = _utcnow, first: str = FIRST) -> Dict[str, Any]:
    """OK: every ledger session of ``market`` from ``first`` is written.  WAITING: the newest one cannot be written yet."""
    tab = (table(base) or {}).get(market)
    if not tab:
        return {"status": "NO_TABLE", "market": market}
    led = Ledger(Path(base))
    if led.verify()["status"] != "OK":
        return {"status": "FAILED", "reason": "LEDGER_BROKEN"}
    at, folder = now(), FOLDERS[market]
    sessions = sorted({r["session"] for r in led._live_rows() if r["market"] == market and r["session"] >= first})
    done = {r["session"] for r in kf.read_index(base, folder)}
    todo = [d for d in sessions if d not in done]
    wrote, waiting = [], None
    bars = list(index_bars()) if todo else []
    for day in todo:
        def scorer(b: Path, d: str) -> Dict[str, Any]:
            st = index_state(bars, d)
            return score_session(_session_snaps(led, market, d), d, market, st, tab[st])
        try:
            if kf.write_record(base, day, at, day != sessions[-1], store=folder, scorer=scorer):
                wrote.append(day)
        except NotReady as exc:
            waiting = {"session": day, "reason": str(exc)}
            if day == sessions[-1]:
                break
    return {"status": "WAITING" if waiting and waiting["session"] == sessions[-1] else "OK", "market": market, "written": wrote, "waiting": waiting,
            "last": max(done | set(wrote), default=None), "sessions": len(done) + len(wrote)}


# ---------------------------------------------------------------------- the single forward reading
def measure_forward(docs: List[Dict[str, Any]], px: Any) -> List[Dict[str, Any]]:
    """One row per recorded session whose 20-session outcome has ended: the rank correlation of the three scores written that day."""
    out = []
    for doc in docs:
        entries = {r["entry_session"] for r in doc["rows"] if r.get("entry_session")}
        if len(entries) != 1 or next(iter(entries)) not in px.dates:
            continue
        i = px.dates.index(next(iter(entries))) - 1          # forward() enters at the open of day i + 1
        if i < 0 or i + H >= len(px.dates):
            continue
        fwd = px.forward(i, H)
        ret = np.array([fwd[px.col[r["ticker"]]] if r["ticker"] in px.col else np.nan for r in doc["rows"]], dtype=float)
        col = lambda key: np.array([np.nan if r.get(key) is None else r[key] for r in doc["rows"]], dtype=float)      # noqa: E731
        dyn, fixed, live = _ic(col("score"), ret), _ic(col("static"), ret), _ic(col("live"), ret)
        if dyn is None or fixed is None:
            continue
        out.append({"session": doc["session"], "state": doc["state"], "ic_dynamic": dyn, "ic_static": fixed, "ic_live": live, "late": bool(doc.get("late"))})
    return out


def evaluate_forward_once(base: Path, market: str, px: Any, log=print) -> Dict[str, Any]:
    """The protocol's one reading of the daily record, at ``READ_AT`` matured sessions.  Figures only: the past test did not
    support the rule, so no verdict is attached.  Refused before the count is reached and after a report exists."""
    base = Path(base)
    target = base / FORWARD_REPORTS[market]
    if target.exists():
        raise RuntimeError("이미 읽었습니다. 규칙상 다시 읽지 않습니다.")
    if kf.verify(base, FOLDERS[market])["status"] != "OK":
        raise RuntimeError("기록 검증에 실패해 읽지 않습니다.")
    docs = [kf._read_day(base / FOLDERS[market], r["session"]) for r in kf.read_index(base, FOLDERS[market])]
    days = measure_forward(docs, px)
    if len(days) < READ_AT:
        raise RuntimeError(f"보유가 끝난 기록일이 {len(days)}개입니다. {READ_AT}개가 되기 전에는 읽지 않습니다.")
    days = days[:READ_AT]
    diff = [d["ic_dynamic"] - d["ic_static"] for d in days]
    mid = len(days) // 2
    past = ((json.loads((base / REPORT).read_text(encoding="utf-8")).get("markets") or {}).get(market) or {}).get("verdict") if (base / REPORT).exists() else None
    res = {"status": "REAL", "protocol": PROTOCOL, "market": market, "horizon": H, "records": len(docs), "days": len(days), "first": days[0]["session"], "last": days[-1]["session"],
           "ic": {"dynamic": float(np.mean([d["ic_dynamic"] for d in days])), "static": float(np.mean([d["ic_static"] for d in days])),
                  "live": _mean([d["ic_live"] for d in days])},
           "ic_diff": float(np.mean(diff)), "ic_diff_t": validate.newey_west_t(diff, H), "early": float(np.mean(diff[:mid])), "late": float(np.mean(diff[mid:])),
           "by_state": {s: {"days": sum(1 for d in days if d["state"] == s), "ic_diff": _mean([x for x, d in zip(diff, days) if d["state"] == s])} for s in STATES},
           "late_share": float(np.mean([d["late"] for d in days])), "past_verdict": past, "reading": "FIGURES_ONLY",
           "note": "과거 걸어가기 검증이 기준에 못 미쳤으므로 판정 없이 수치만 적습니다. 240거래일의 겹치는 표본으로는 작은 차이를 가릴 수 없습니다."}
    target.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(target, json.dumps(res, ensure_ascii=False, indent=1))
    return res


def status(base: Path) -> Dict[str, Any]:
    """What the screen shows: the past test's reading with its numbers, the frozen table, and how far the daily record has come."""
    try:
        doc = json.loads((Path(base) / REPORT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "NO_RECORD", "protocol": PROTOCOL}
    out: Dict[str, Any] = {"status": "REAL", "protocol": PROTOCOL, "run_at": doc.get("run_at"), "horizon": doc["horizon"], "settings": doc["settings"], "limits": doc["limits"],
                           "state_labels": STATE_LABELS, "domains": list(DOMAINS), "read_at": READ_AT, "markets": {}}
    for market, m in doc["markets"].items():
        index = kf.read_index(base, FOLDERS[market])
        last = None
        if index:
            try:
                d = kf._read_day(Path(base) / FOLDERS[market], index[-1]["session"])
                last = {"session": d["session"], "state": d["state"], "how": d["how"], "weights": d["weights"]}
            except (OSError, ValueError, KeyError):
                last = None
        keep = ("verdict", "status", "tested", "test_first", "test_last", "ic", "ic_diff", "ic_diff_t", "ic_diff_positive_share", "ic_over_control", "spread_net", "fitted_share",
                "conditions", "by_state", "final_table", "static", "days", "first", "last", "leak_free", "folds", "cost_round_trip")
        out["markets"][market] = {**{k: m.get(k) for k in keep}, "record": {"sessions": len(index), "first": index[0]["session"] if index else None,
                                                                           "last": index[-1]["session"] if index else None, "today": last, "start": FIRST}}
    return out
