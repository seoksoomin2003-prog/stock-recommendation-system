"""One confirmation run of the Korean swing technical domain on dates before the live replay.  Rules: reports/QSF_KR_TECH_EARLY_PROTOCOL.md.

The live scoring code on price data only, the live universe rule, evaluation days from 2012-04 whose 20-session returns end before
the replay's first day.  ``prepare`` stores scores and reads no return; ``run_once`` reads returns once and refuses a second run.
"""
import gzip
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from terminal.qsf import config, engine, research_kr_live as rl, validate

PROTOCOL = "reports/QSF_KR_TECH_EARLY_PROTOCOL.md"
REPORT = Path("reports") / "qsf" / "QSF_KR_TECH_EARLY.json"
SCORES = "scores_tech_early.json.gz"
FIRST, LAST_EXIT = "2012-04-02", "2019-03-29"
H = 20
MIN_T = 2.0
EXTRA_H = (5, 10)
LONG_H = 252
KEYS = {"technical": "SWING|TECHNICAL", "risk": "SWING|RISK", "composite": "SWING|RAW", "long_technical": "LONG_TERM|TECHNICAL"}


class PriceOnly:
    """What ``score_day`` asks of statements, without statements: the fund-vehicle exclusion stays, fundamentals are absent."""

    def __init__(self, klass_of: Dict[str, str]):
        self.klass_of = klass_of

    def not_operating(self, px: Any) -> np.ndarray:
        return np.array([self.klass_of.get(s) in rl.NOT_OPERATING for s in px.symbols])

    def fund(self, code: str, as_of: str, close: float, shares: Optional[float]) -> None:
        return None


def eval_days(px: Any, h: int = H) -> List[int]:
    """Evaluation rows whose h-session return has ended by LAST_EXIT."""
    return [i for i in rl.eval_rows(px, FIRST) if i + h < len(px.dates) and px.dates[i + h] <= LAST_EXIT]


def factor_values(px: Any, i: int, st: PriceOnly) -> Dict[str, Dict[str, float]]:
    """Ticker -> the swing technical factors' normalised values on day ``i`` (reference only)."""
    day = px.dates[i]
    bench = {b: px.bars(px.col[name], i) for b, name in rl.BOARD_INDEX.items()}
    close = px.data["close"]
    ctxs, rets = {}, {}
    for j in rl.universe(px, i, exclude=st.not_operating(px)):
        b = px.bars(j, i)
        if not b or b[-1]["date"] != day:
            continue
        t = px.symbols[j]
        board = "KOSPI" if px.kospi[j] else "KOSDAQ"
        ctxs[t] = {"market": "KR", "bars": b, "bench": bench[board], "bench_name": board, "events": None, "regime": None, "earnings": None, "expected_session": day, "fund": None}
        if i >= 126 and close[i, j] == close[i, j] and close[i - 126, j] == close[i - 126, j] and close[i - 126, j] > 0:
            rets[t] = float(close[i, j] / close[i - 126, j] - 1)
    ordered = sorted(rets.values())
    ranks = {t: float(np.searchsorted(ordered, v, side="right") / len(ordered)) for t, v in rets.items()} if len(ordered) >= 20 else {}
    out: Dict[str, Dict[str, float]] = {}
    for t, ctx in ctxs.items():
        res = engine.score(dict(ctx, rs_rank=ranks.get(t)), "SWING")
        out[t] = {f["factor"]: f["normalized"] for f in res.get("factors") or [] if f.get("domain") == "TECHNICAL" and f.get("normalized") is not None}
    return out


def prepare(base: Path, log=print) -> Dict[str, Any]:
    """Scores for every evaluation day.  Reads no return."""
    base = Path(base)
    px = rl.ensure_panel(base, log)
    st = PriceOnly(rl._statements(base).klass_of)
    rows = eval_days(px)
    recs: List[Dict[str, Any]] = []
    t0 = time.time()
    for n, i in enumerate(rows, 1):
        day = rl.score_day(px, i, st)
        fv = factor_values(px, i, st)
        for r in day:
            r["factors"] = fv.get(r["t"]) or {}
        recs.extend(day)
        if n % 10 == 0 or n == len(rows):
            log(f"scores {n}/{len(rows)} {px.dates[i]} {len(day)} stocks {time.time() - t0:.0f}s")
    with gzip.open(base / rl.DATA / SCORES, "wt", encoding="utf-8") as fh:
        json.dump({"rows": rows, "first": px.dates[rows[0]], "last": px.dates[rows[-1]], "records": recs}, fh)
    per_day = {}
    for r in recs:
        per_day.setdefault(r["i"], []).append(r)
    return {"status": "REAL", "days": len(rows), "first": px.dates[rows[0]], "last": px.dates[rows[-1]], "records": len(recs),
            "mean_universe": float(np.mean([len(g) for g in per_day.values()])),
            "technical_scored_share": float(np.mean([r.get(KEYS["technical"]) is not None for r in recs])), "fund_present": sum(1 for r in recs if r.get("fund_status"))}


def _ic_rows(px: Any, by_i: Dict[int, List[Dict[str, Any]]], get, h: int) -> List[Dict[str, Any]]:
    cost = config.round_trip_cost("KR")
    rows = []
    for i in sorted(by_i):
        if i + h >= len(px.dates) or px.dates[i + h] > LAST_EXIT:
            continue
        fwd = px.forward(i, h, cost)
        g = by_i[i]
        score = np.array([np.nan if get(r) is None else get(r) for r in g], dtype=float)
        ret = np.array([fwd[px.col[r["t"]]] for r in g], dtype=float)
        d = validate.per_date(score, ret, cost)
        if d and d.get("ic") is not None:
            ok = np.isfinite(score) & np.isfinite(ret)
            q = validate.rank(score[ok]) / (ok.sum() - 1)
            ex = ret[ok] - ret[ok].mean()
            d.update(date=px.dates[i], i=i, top_excess=float(ex[q >= 0.8].mean()), bottom_excess=float(ex[q <= 0.2].mean()))
            rows.append(d)
    return rows


def summary(values: List[float], dates: List[str]) -> Dict[str, Any]:
    """Mean, Newey-West t at lag 1 (the days are 21 sessions apart) and the two halves, split at the middle date."""
    if len(values) < 6:
        return {"dates": len(values), "status": "UNAVAILABLE"}
    mid = len(values) // 2
    return {"dates": len(values), "first": dates[0], "last": dates[-1], "split": dates[mid], "mean": float(np.mean(values)), "t": validate.newey_west_t(values, 1),
            "early": float(np.mean(values[:mid])), "late": float(np.mean(values[mid:])), "positive_share": float(np.mean([v > 0 for v in values]))}


def primary_reading(s: Dict[str, Any]) -> str:
    if s.get("t") is None:
        return "NOT_CONFIRMED"
    if s["mean"] < 0 and s["t"] <= -MIN_T and s["early"] < 0 and s["late"] < 0:
        return "NEGATIVE_AGAIN"
    if s["mean"] > 0 and s["t"] >= MIN_T and s["early"] > 0 and s["late"] > 0:
        return "OPPOSITE"
    return "NOT_CONFIRMED"


def secondary_reading(s: Dict[str, Any]) -> str:
    return "DROPPING_HELPED_AGAIN" if s.get("t") is not None and s["mean"] > 0 and s["t"] >= MIN_T and s["early"] > 0 and s["late"] > 0 else "NOT_CONFIRMED"


def evaluate(px: Any, recs: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_i: Dict[int, List[Dict[str, Any]]] = {}
    for r in recs:
        by_i.setdefault(r["i"], []).append(r)
    series = {name: _ic_rows(px, by_i, lambda r, k=key: r.get(k), H) for name, key in KEYS.items() if name != "long_technical"}

    def block(rows):
        s = summary([r["ic"] for r in rows], [r["date"] for r in rows])
        if rows:
            s.update(top_fifth_excess=float(np.mean([r["top_excess"] for r in rows])), bottom_fifth_excess=float(np.mean([r["bottom_excess"] for r in rows])), mean_n=float(np.mean([r["n"] for r in rows])))
        return s
    tech = block(series["technical"])
    both = sorted(set(r["i"] for r in series["risk"]) & set(r["i"] for r in series["composite"]))
    risk_by, comp_by = {r["i"]: r for r in series["risk"]}, {r["i"]: r for r in series["composite"]}
    diff = summary([risk_by[i]["ic"] - comp_by[i]["ic"] for i in both], [risk_by[i]["date"] for i in both])
    names = sorted({k for r in recs for k in (r.get("factors") or {})})
    factors = {n: block(_ic_rows(px, by_i, lambda r, n=n: (r.get("factors") or {}).get(n), H)) for n in names}
    other = {str(h): block(_ic_rows(px, by_i, lambda r: r.get(KEYS["technical"]), h)) for h in EXTRA_H}
    long_rows = _ic_rows(px, by_i, lambda r: r.get(KEYS["long_technical"]), LONG_H)
    return {"horizon": H, "technical": {**tech, "reading": primary_reading(tech)}, "risk": block(series["risk"]), "composite": block(series["composite"]),
            "risk_minus_composite": {**diff, "reading": secondary_reading(diff)}, "technical_factors": factors, "technical_other_horizons": other,
            "long_technical_252": block(long_rows)}


def run_once(base: Path, log=print) -> Dict[str, Any]:
    base = Path(base)
    out = base / REPORT
    if out.exists():
        raise RuntimeError("이 시험은 한 번만 실행합니다. 이미 결과가 있습니다.")
    path = base / rl.DATA / SCORES
    if not path.exists():
        raise RuntimeError("먼저 kr-tech-early-prepare 를 실행하세요.")
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        stored = json.load(fh)
    px = rl.load_panel(base)
    res = {"status": "REAL", "protocol": PROTOCOL, "first": stored["first"], "last": stored["last"], "days": len(stored["rows"]), "last_exit": LAST_EXIT, **evaluate(px, stored["records"])}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"technical: {res['technical']['reading']}, dropping: {res['risk_minus_composite']['reading']}")
    return res
