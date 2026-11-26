"""The former formula, written down every session beside the split score.  Rules: reports/QSF_SCORE_SPLIT_PROTOCOL.md.

On 2026-11-16 the regime domain left all four live scores (QSF-1.4.0) and became the market state, shown apart.  Its factors are
still computed and stored in the ledger as reference rows, so the former composite can be worked out from the ledger alone.  The
ledger is only read.  A record is written once and chained by hash.  No return is computed while the record grows, and the single
reading is refused until 240 recorded sessions have a finished 20-session outcome.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from terminal.qsf import calibrate
import numpy as np

from terminal.qsf import config, engine, kr_forward as kf, validate
from terminal.qsf.ledger import Ledger
from utils import durable
from terminal.qsf import ledger as ledger_mod

PROTOCOL = "reports/QSF_SCORE_SPLIT_PROTOCOL.md"
FOLDERS = {"KR": Path("research_data") / "score_split_kr", "US": Path("research_data") / "score_split_us"}
REPORTS = {m: Path("reports") / "qsf" / f"QSF_SCORE_SPLIT_{m}.json" for m in ("KR", "US")}
FIRST = "2026-11-16"            # the earliest session QSF-1.4.0 can have recorded
COUNTED_AGAIN = ("REGIME",)     # the former formula: the live one with the regime domain counting again
MIN_ROWS = 200                  # fewer swing scores than this is a partial day, not a day
HORIZONS = {"SWING": 20, "LONG_TERM": 63}
BAND = 70.0                     # the buy band
READ_AT = 240                   # matured swing sessions at the single reading
MIN_T = 2.0
MIN_STOCKS = 30


class NotReady(Exception):
    """A session that cannot be written (yet): a partial day, or one recorded before the split."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_split(snap: Dict[str, Any]) -> bool:
    return any(f.get("scored") is False and f.get("domain") == "REGIME" for f in snap.get("factors") or [])


def score_session(snaps: List[Dict[str, Any]], session: str, market: str) -> Dict[str, Any]:
    fresh = sorted((s for s in snaps if s.get("data_date") == session and s.get("score") is not None and s.get("strategy") in HORIZONS), key=lambda s: (s["ticker"], s["strategy"]))
    if fresh and not any(is_split(s) for s in fresh):
        raise NotReady("FORMER_COMPOSITION")
    fresh = [s for s in fresh if is_split(s)]
    if sum(1 for s in fresh if s["strategy"] == "SWING") < MIN_ROWS:
        raise NotReady("TOO_FEW_STOCKS")
    rows = []
    for s in fresh:
        p = engine.formula_score(s.get("factors") or [], COUNTED_AGAIN)
        rows.append({"ticker": s["ticker"], "strategy": s["strategy"], "live": round(float(s["score"]), 3), "with_regime": None if p is None else round(p, 3),
                     "entry_session": s.get("entry_session"), "actionability": s.get("actionability")})
    state = engine.market_state(next(s for s in fresh if s["strategy"] == "SWING")["factors"], market)
    return {"session": session, "market": market, "protocol": PROTOCOL, "model_versions": sorted({str(s.get("model_version")) for s in fresh}),
            "market_state": {k: state[k] for k in ("score_100", "state", "size_factor", "coverage")}, "rows": rows}


def _session_snaps(led: Ledger, market: str, session: str) -> List[Dict[str, Any]]:
    return ledger_mod.session_snaps(led, market, session)


def record(base: Path, market: str, now: Callable[[], datetime] = _utcnow, first: str = FIRST) -> Dict[str, Any]:
    """OK: every ledger session of the split composition is written.  WAITING: a session in the ledger is still partial."""
    at, folder = now(), FOLDERS[market]
    led = Ledger(Path(base))
    if led.verify()["status"] != "OK":
        return {"status": "FAILED", "reason": "LEDGER_BROKEN"}
    sessions = sorted({r["session"] for r in led._live_rows() if r["market"] == market and r["session"] >= first})
    done = {r["session"] for r in kf.read_index(base, folder)}
    wrote: List[str] = []
    partial: List[str] = []
    former: List[str] = []
    for day in sessions:
        if day in done:
            continue
        try:
            if kf.write_record(base, day, at, day != sessions[-1], store=folder, scorer=lambda b, d: score_session(_session_snaps(led, market, d), d, market)):
                wrote.append(day)
        except NotReady as exc:
            (former if str(exc) == "FORMER_COMPOSITION" else partial).append(day)
    return {"status": "WAITING" if partial else "OK", "market": market, "written": wrote, "partial": partial, "former_composition": former,
            "last": max(done | set(wrote), default=None), "sessions": len(done) + len(wrote)}


def status(base: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {"protocol": PROTOCOL, "read_at": READ_AT, "first": FIRST, "markets": {}}
    for market, folder in FOLDERS.items():
        rows = kf.read_index(base, folder)
        out["markets"][market] = {"records": len(rows), "first": rows[0]["session"] if rows else None, "last": rows[-1]["session"] if rows else None,
                                  "late": sum(1 for r in rows if r.get("late")), "evaluated": (Path(base) / REPORTS[market]).exists()}
    return out


# ---------------------------------------------------------------------- the single reading
def _ic(score: np.ndarray, ret: np.ndarray) -> Optional[float]:
    ok = np.isfinite(score) & np.isfinite(ret)
    if ok.sum() < MIN_STOCKS or np.ptp(score[ok]) == 0 or np.ptp(ret[ok]) == 0:
        return None
    return float(np.corrcoef(validate.rank(score[ok]), validate.rank(ret[ok]))[0, 1])


TOP_FIFTH = (("KR", "SWING"),)          # read on the day's top fifth instead of the band (user decision 2026-11-22): the band is empty there


def _band(score: np.ndarray, able: np.ndarray, ret: np.ndarray, cost: float, top: bool = False) -> Dict[str, Any]:
    """Equal weight in every actionable stock at or over the band, net of a round trip; nothing held (0) when there is none.
    ``top``: the day's top fifth of the actionable stocks by this score, for a market and strategy whose scores never reach the band."""
    ok = np.isfinite(score) & able & np.isfinite(ret)
    if top:
        pick = ok & (score >= np.quantile(score[ok], 0.8)) if ok.sum() >= 5 else np.zeros_like(ok)
    else:
        pick = ok & (score >= BAND)
    return {"names": int(pick.sum()), "ret": float(ret[pick].mean() - cost) if pick.any() else 0.0}


def measure(docs: List[Dict[str, Any]], px: Any, market: str, strategy: str = "SWING") -> List[Dict[str, Any]]:
    """One row per recorded session whose outcome of the strategy's horizon has ended."""
    h, cost, out = HORIZONS[strategy], config.round_trip_cost(market), []
    for doc in docs:
        rows = [r for r in doc["rows"] if r["strategy"] == strategy]
        entries = {r["entry_session"] for r in rows if r.get("entry_session")}
        if len(entries) != 1 or next(iter(entries)) not in px.dates:
            continue
        i = px.dates.index(next(iter(entries))) - 1          # forward() enters at the open of day i + 1
        if i < 0 or i + h >= len(px.dates):
            continue
        fwd = px.forward(i, h)
        ret = np.array([fwd[px.col[r["ticker"]]] if r["ticker"] in px.col else np.nan for r in rows], dtype=float)
        col = lambda key: np.array([np.nan if r.get(key) is None else r[key] for r in rows], dtype=float)      # noqa: E731
        able = np.array([r.get("actionability") == "ACTIONABLE" for r in rows], dtype=bool)
        top = (market, strategy) in TOP_FIFTH
        live, prior = _band(col("live"), able, ret, cost, top), _band(col("with_regime"), able, ret, cost, top)
        out.append({"session": doc["session"], "state": (doc.get("market_state") or {}).get("state"), "live": live, "with_regime": prior, "diff": live["ret"] - prior["ret"],
                    "ic_live": _ic(col("live"), ret), "ic_with_regime": _ic(col("with_regime"), ret), "late": bool(doc.get("late"))})
    return out


def _mean(x) -> Optional[float]:
    v = [float(a) for a in x if a is not None]
    return float(np.mean(v)) if v else None


def summarize(days: List[Dict[str, Any]], lag: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {"days": len(days)}
    for k in ("live", "with_regime"):
        r = np.array([d[k]["ret"] for d in days], dtype=float)
        worst = np.sort(r)[:max(1, len(r) // 10)]
        out[k] = {"mean": float(r.mean()), "sd": float(r.std(ddof=1)) if len(r) > 1 else None, "worst_tenth": float(worst.mean()),
                  "empty_share": float(np.mean([d[k]["names"] == 0 for d in days])), "mean_names": float(np.mean([d[k]["names"] for d in days])), "ic": _mean(d[f"ic_{k}"] for d in days)}
    diff = [d["diff"] for d in days]
    out["difference"] = {"mean": float(np.mean(diff)), "t": validate.newey_west_t(diff, lag)}
    out["difference"]["t_bar"] = calibrate.bar(MIN_T, len(diff), lag, 1, lag)          # the bar for this sample's own design (2026-11-22)
    out["by_state"] = {s: {"days": sum(1 for d in days if d["state"] == s), "live": _mean(d["live"]["ret"] for d in days if d["state"] == s),
                           "with_regime": _mean(d["with_regime"]["ret"] for d in days if d["state"] == s)} for s in ("FAVOURABLE", "ADVERSE")}
    return out


def verdict(diff: Dict[str, Any]) -> str:
    m, t = diff["mean"], diff["t"]
    bar = diff.get("t_bar") or MIN_T
    return "SPLIT_BETTER" if t is not None and m > 0 and t >= bar else "WITH_REGIME_BETTER" if t is not None and m < 0 and t <= -bar else "NOT_DISTINGUISHED"


def evaluate_once(base: Path, market: str, px: Any, log=print) -> Dict[str, Any]:
    """The protocol's one reading, at ``READ_AT`` matured swing sessions.  Refused before the count is reached and after a report exists."""
    base = Path(base)
    target = base / REPORTS[market]
    if target.exists():
        raise RuntimeError("이미 읽었습니다. 규칙상 다시 읽지 않습니다.")
    if kf.verify(base, FOLDERS[market])["status"] != "OK":
        raise RuntimeError("기록 검증에 실패해 읽지 않습니다.")
    docs = [kf._read_day(base / FOLDERS[market], r["session"]) for r in kf.read_index(base, FOLDERS[market])]
    swing = measure(docs, px, market, "SWING")
    if len(swing) < READ_AT:
        raise RuntimeError(f"보유가 끝난 기록일이 {len(swing)}개입니다. {READ_AT}개가 되기 전에는 읽지 않습니다.")
    swing = swing[:READ_AT]
    last = swing[-1]["session"]
    long_days = [d for d in measure(docs, px, market, "LONG_TERM") if d["session"] <= last]
    s = summarize(swing, HORIZONS["SWING"])
    top = (market, "SWING") in TOP_FIFTH
    res = {"status": "REAL", "protocol": PROTOCOL, "market": market, "records": len(docs), "first": swing[0]["session"], "last": last, "band": BAND,
           "selection": "TOP_FIFTH" if top else "BAND",          # Korea: no swing score has reached 70 (amendment 2026-11-22)
           "verdict": verdict(s["difference"]), "swing": s, "long": {**summarize(long_days, HORIZONS["LONG_TERM"]), "reading": "FIGURES_ONLY"} if long_days else {"days": 0},
           "late_share": float(np.mean([d["late"] for d in swing])),
           "note": "NOT_DISTINGUISHED는 '차이 없음'이 아니라 '아직 모름'입니다. 두 점수는 종목 순위가 거의 같고, 차이는 "
                   + ("그날 상위 20%에 드는 종목이 서로 다른 데서 나옵니다(한국 스윙 점수는 70에 닿은 적이 없어 상위 20%로 읽습니다)." if top else "어느 날에 몇 종목이 70을 넘는가에서 나옵니다.")}
    target.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(target, json.dumps(res, ensure_ascii=False, indent=1))
    return res
