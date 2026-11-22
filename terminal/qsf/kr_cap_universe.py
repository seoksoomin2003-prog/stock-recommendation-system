"""The Korean market-value universe challenger: the live scoring code on another set of stocks, written down every session.
Rules: reports/QSF_KR_CAP_UNIVERSE_PROTOCOL.md.

The live ledger, ranking and side files are never written.  A record is written once and chained by hash.  No return is computed
while the record grows, and the single evaluation is refused until 240 sessions have matured.
"""
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from terminal.qsf import calibrate
import numpy as np

from terminal.qsf import config, kr_forward as kf, krx_history as kh, live_forward as lf, validate
from terminal.qsf.ledger import Ledger
from terminal.qsf.research_kr_live import KRX, NOT_OPERATING, eligible_stock
from utils import durable

PROTOCOL = "reports/QSF_KR_CAP_UNIVERSE_PROTOCOL.md"
FOLDER = Path("research_data") / "kr_cap_universe"
REPORT = Path("reports") / "qsf" / "QSF_KR_CAP_UNIVERSE.json"
FIRST = "2026-11-10"
SIZE, LOOK, WINDOW = 300, 40, 20
MIN_SCORED = 200
HORIZON = 20
NEED = config.MIN_INDEPENDENT * HORIZON
MIN_T = 2.0
F = {name: n for n, name in enumerate(kh.FIELDS)}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _num(v: Any) -> Optional[float]:
    try:
        x = float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def day_rows(root: Path, day: str) -> Optional[Dict[str, Dict[str, Any]]]:
    """Eligible stocks of one day from both boards.  None when a board's file is missing or empty (a holiday, or not published yet)."""
    out: Dict[str, Dict[str, Any]] = {}
    for board in kh.BOARDS:
        p = kh.path_of(root, board, day)
        if not p.exists():
            return None
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            rows = json.load(fh)
        if not rows:
            return None
        for r in rows:
            if eligible_stock(r[F["ISU_CD"]], r[F["ISU_NM"]], r[F["SECT_TP_NM"]]):
                out[r[F["ISU_CD"]]] = {"close": _num(r[F["TDD_CLSPRC"]]), "volume": _num(r[F["ACC_TRDVOL"]]), "cap": _num(r[F["MKTCAP"]])}
    return out


def recent_days(root: Path, session: str, n: int = LOOK) -> List[Dict[str, Dict[str, Any]]]:
    """The newest ``n`` trading days up to the session, newest first.  Holidays (empty files) are not days."""
    names = sorted((p.name[:10] for p in (Path(root) / "KOSPI").glob("*.json.gz") if p.name[:10] <= session), reverse=True)
    out = []
    for day in names:
        rows = day_rows(root, day)
        if rows:
            out.append(rows)
        if len(out) == n:
            break
    return out


def members(root: Path, session: str, klass_of: Dict[str, str], size: int = SIZE) -> List[Dict[str, Any]]:
    """The protocol's rule.  Empty when the session itself has no snapshot."""
    today = day_rows(root, session)
    if not today:
        return []
    days = recent_days(root, session)
    picked = []
    for code, r in today.items():
        if not r["close"] or not r["cap"] or klass_of.get(code) in NOT_OPERATING:
            continue
        traded = sum(1 for d in days if (d.get(code) or {}).get("close") and (d[code].get("volume") or 0) > 0)
        halted = all(not (d.get(code) or {}).get("volume") for d in days[:3])
        if traded >= WINDOW and not halted:
            picked.append((code, r["cap"]))
    picked.sort(key=lambda x: (-x[1], x[0]))
    return [{"code": c, "cap": cap, "rank": n} for n, (c, cap) in enumerate(picked[:size], 1)]


def live_tickers(led: Ledger, session: str) -> List[str]:
    out = set()
    for r in led._live_rows():
        if r["market"] == "KR" and r["session"] == session:
            out |= {s["ticker"] for s in led._load(r) if s.get("strategy") == "SWING" and s.get("score") is not None and s.get("data_date") == session}
    return sorted(out)


def build_doc(session: str, mem: List[Dict[str, Any]], scan: Dict[str, Any], live: List[str], entry: str) -> Dict[str, Any]:
    """Rows scored on the session's own price.  Raises TOO_FEW_STOCKS when the scan did not reach the session for enough of them."""
    by: Dict[str, Dict[str, Any]] = {}
    for r in scan.get("rows") or []:
        if r.get("data_date") == session:
            by.setdefault(r["ticker"], {})[r["strategy"]] = r
    in_live = set(live)
    rows = []
    for m in mem:
        got = by.get(m["code"])
        if not got or "SWING" not in got:
            continue
        sw, lt = got["SWING"], got.get("LONG_TERM") or {}
        rows.append({"ticker": m["code"], "cap_rank": m["rank"], "cap": m["cap"], "in_live": m["code"] in in_live,
                     "swing": None if sw.get("score") is None else round(float(sw["score"]), 3), "long": None if lt.get("score") is None else round(float(lt["score"]), 3),
                     "swing_actionability": sw.get("actionability"), "long_actionability": lt.get("actionability")})
    if len(rows) < MIN_SCORED:
        raise ValueError("TOO_FEW_STOCKS")
    cap = {m["code"] for m in mem}
    return {"session": session, "protocol": PROTOCOL, "size": SIZE, "members": len(mem), "entry_session": entry, "model_version": scan.get("model_version"),
            "live_only": sorted(in_live - cap), "rows": rows}


def record(base: Path, service: Any, now: Callable[[], datetime] = _utcnow, klass_of: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """OK: the session is written or was already.  WAITING: the KRX day or the live record is not there yet, or too few stocks were
    scored on the session's price.  A session the market has moved past is never written afterwards."""
    base = Path(base)
    session = service.regime("KR").get("session")
    if not session or session < FIRST:
        return {"status": "OK", "written": [], "reason": "BEFORE_FIRST"}
    if session in {r["session"] for r in kf.read_index(base, FOLDER)}:
        return {"status": "OK", "written": [], "last": session}
    root = base / KRX
    if not day_rows(root, session):
        return {"status": "WAITING", "reason": "KRX_NOT_PUBLISHED", "session": session}
    live = live_tickers(Ledger(base), session)
    if len(live) < MIN_SCORED:
        return {"status": "WAITING", "reason": "LIVE_NOT_RECORDED", "session": session}
    if klass_of is None:
        from terminal.qsf import research_kr_live
        extra_file = base / research_kr_live.DATA / "industry.json"
        extra = json.loads(extra_file.read_text(encoding="utf-8")) if extra_file.exists() else {}
        klass_of = {**{c: v["class"] for c, v in extra.items()}, **research_kr_live._klass_from_master(base)}
    mem = members(root, session, klass_of)
    if len(mem) < MIN_SCORED:
        return {"status": "WAITING", "reason": "TOO_FEW_MEMBERS", "session": session}
    scan = service.scan("KR", tickers=[m["code"] for m in mem], record=False, side_files=False)
    if scan.get("session") != session:
        return {"status": "WAITING", "reason": "SESSION_MOVED", "session": session}
    try:
        doc = build_doc(session, mem, scan, live, service._entry_date("KR", session).isoformat())
    except ValueError as exc:
        if str(exc) != "TOO_FEW_STOCKS":
            raise
        return {"status": "WAITING", "reason": "TOO_FEW_STOCKS", "session": session}
    wrote = kf.write_record(base, session, now(), False, store=FOLDER, scorer=lambda b, d: doc)
    return {"status": "OK", "written": [session] if wrote else [], "stocks": len(doc["rows"]), "overlap": sum(1 for r in doc["rows"] if r["in_live"])}


def status(base: Path) -> Dict[str, Any]:
    rows = kf.read_index(base, FOLDER)
    return {"records": len(rows), "first": rows[0]["session"] if rows else None, "last": rows[-1]["session"] if rows else None, "needed": NEED, "horizon": HORIZON,
            "evaluated": (Path(base) / REPORT).exists()}


# ---------------------------------------------------------------------- the one evaluation
def measure_day(doc: Dict[str, Any], px: Any, h: int = HORIZON, key: str = "swing") -> Optional[Dict[str, Any]]:
    """One record whose hold has ended, in the shape ``live_forward.summarize`` reads, plus the live universe's return."""
    entry = doc.get("entry_session")
    if entry not in px.dates:
        return None
    i = px.dates.index(entry) - 1                     # forward() enters at the open of day i + 1
    if i < 0 or i + h >= len(px.dates):
        return None
    cost = config.round_trip_cost("KR")
    fwd = px.forward(i, h, cost)
    ret_of = lambda t: fwd[px.col[t]] if t in px.col else np.nan       # noqa: E731
    cap_ret = np.array([ret_of(r["ticker"]) for r in doc["rows"]], dtype=float)
    live_ret = np.array([ret_of(r["ticker"]) for r in doc["rows"] if r["in_live"]] + [ret_of(t) for t in doc.get("live_only") or []], dtype=float)
    ok = [r[key] is not None and r.get(f"{key}_actionability") != "INSUFFICIENT_DATA" for r in doc["rows"]]
    score = np.array([r[key] if good else np.nan for r, good in zip(doc["rows"], ok)], dtype=float)
    d = validate.per_date(score, cap_ret, cost)
    if not d or d.get("ic") is None or np.isfinite(live_ret).sum() < lf.MIN_ROWS:
        return None
    use = np.isfinite(score) & np.isfinite(cap_ret)
    sc, r = score[use], cap_ret[use]
    q = validate.rank(sc) / (len(sc) - 1)
    buy, top = r[sc >= lf.BUY], r[q >= 0.8]
    index = float(px.market_return(i, h))
    d.update(date=doc["session"], universe_net=float(np.nanmean(cap_ret)), live_net=float(np.nanmean(live_ret)), index=index,
             universe_effect=float(np.nanmean(cap_ret)) - index, buy_net=float(buy.mean()) if len(buy) else None, top_net=float(top.mean()) if len(top) else None,
             versions=[str(doc.get("model_version"))], overlap=sum(1 for x in doc["rows"] if x["in_live"]))
    return d


def universe_reading(days: List[Dict[str, Any]], h: int = HORIZON) -> Dict[str, Any]:
    """Question 1: the market-value universe against the live universe, both at equal weight, day by day."""
    diff = [d["universe_net"] - d["live_net"] for d in days]
    mid = len(days) // 2
    early, late = float(np.mean(diff[:mid])), float(np.mean(diff[mid:]))
    t = validate.newey_west_t(diff, h)
    both = early > 0 and late > 0
    bar = calibrate.bar(MIN_T, len(diff), h, 1, h)          # the bar for this sample's own design (2026-11-22)
    return {"mean": float(np.mean(diff)), "t": t, "t_bar": bar, "early": early, "late": late,
            "reading": "UNIVERSE_BETTER" if both and t is not None and t >= bar else "SAME_DIRECTION_NOT_SIGNIFICANT" if both else "NOT_SUPPORTED"}


def evaluate_once(base: Path, log=print, panel: Any = None) -> Dict[str, Any]:
    base = Path(base)
    out = base / REPORT
    if out.exists():
        raise RuntimeError("평가는 한 번만 실행합니다. 이미 결과가 있습니다.")
    if kf.verify(base, FOLDER)["status"] != "OK":
        raise RuntimeError("기록 파일 검증에 실패했습니다.")
    if panel is None:
        from terminal.qsf import research_kr_live
        panel = research_kr_live.ensure_panel(base, log)
    docs = [kf._read_day(base / FOLDER, r["session"]) for r in kf.read_index(base, FOLDER)]
    place = {d: n for n, d in enumerate(panel.dates)}
    ready = [d for d in docs if d.get("entry_session") in place and place[d["entry_session"]] - 1 + HORIZON < len(panel.dates)]
    if len(ready) < NEED:
        raise RuntimeError(f"만기 기록일이 {len(ready)}개입니다. {NEED}개가 되기 전에는 평가하지 않습니다.")
    used = ready[:NEED]
    swing = [d for d in (measure_day(doc, panel) for doc in used) if d]
    long_ = [d for d in (measure_day(doc, panel, key="long") for doc in used) if d]
    if len(swing) < NEED // 2:
        raise RuntimeError(f"수익을 계산할 수 있는 날이 {len(swing)}일뿐입니다.")
    s = lf.summarize(swing, HORIZON)
    res = {"status": "REAL", "protocol": PROTOCOL, "horizon": HORIZON, "records": len(docs), "sessions_used": len(used), "first": used[0]["session"], "last": used[-1]["session"],
           "universe": universe_reading(swing), "swing": {**lf.reading(s), "summary": s},
           "long_reference": lf.summarize(long_, HORIZON) if len(long_) > 2 * HORIZON else None,
           "mean_overlap": float(np.mean([d["overlap"] for d in swing])), "note": lf.NOTE}
    out.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(out, json.dumps(res, ensure_ascii=False, indent=1))
    return res
