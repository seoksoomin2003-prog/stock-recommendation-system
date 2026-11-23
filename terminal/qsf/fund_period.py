"""The score on annual statements and the score on trailing four quarters, written down side by side every session.
Rules: reports/QSF_FUND_PERIOD_PROTOCOL.md.

The live score reads annual statements.  Each card also carries the score the other period's figures give (``fund_period`` in the
ledger snapshot), so this record is made from the ledger alone.  A record is written once and chained by hash.  No return is
computed while the record grows.  One reading per market at 240 matured swing sessions; a TRAILING_BETTER verdict makes that
market's live score read trailing figures from the next scan on, with no one typing anything (``live_period``).
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from terminal.qsf import calibrate
import numpy as np

from terminal.qsf import config, kr_forward as kf, validate
from terminal.qsf.ledger import Ledger
from terminal.qsf.score_split import TOP_FIFTH, _band, _ic, _mean
from utils import durable

PROTOCOL = "reports/QSF_FUND_PERIOD_PROTOCOL.md"
FOLDERS = {"KR": Path("research_data") / "fund_period_kr", "US": Path("research_data") / "fund_period_us"}
REPORTS = {m: Path("reports") / "qsf" / f"QSF_FUND_PERIOD_{m}.json" for m in ("KR", "US")}
FIRST = "2026-11-23"            # the earliest session a card can carry both scores
PERIODS = ("ANNUAL", "TRAILING")
DEFAULT = "ANNUAL"
SWITCH = "QSF_FUND_PERIOD"      # .env: ANNUAL or TRAILING overrides the reading for both markets
MIN_ROWS = 200                  # fewer trailing swing scores than this is a partial day, not a day
HORIZONS = {"SWING": 20, "LONG_TERM": 63}
READ_AT = 240                   # matured swing sessions at the single reading
# User decision 2026-11-22 ("기준 조이기"), made before any record of this store existed.  The difference series is 240 daily
# values of 20-session returns: they overlap, so there are about twelve independent periods.  With no effect at all the
# Newey-West t of such a series reaches 2.0 in 7.7% of cases (a normal test would give 2.3%) and 3.0 in about 2.2%
# (20,000 simulated series each for normal noise, fat-tailed noise and noise absent on half the days: 2.2%, 1.8%, 2.0%).
# A passing reading rewrites the live score's inputs by itself, so the bar is the value that keeps a chance pass under 2.5%.
MIN_T = 3.0
# Two 30-session episodes in an otherwise empty year gave t 2.37.  A verdict now needs a difference on at least half the days.
MIN_DIFF_DAYS = READ_AT // 2
ADOPT = "TRAILING_BETTER"
VERDICT_KO = {"TRAILING_BETTER": "최근 4분기 재무 쪽이 나았습니다", "ANNUAL_BETTER": "연간 재무 쪽이 나았습니다",
              "NOT_DISTINGUISHED": "구분되지 않았습니다. 차이가 없다는 뜻이 아니라 아직 모른다는 뜻입니다"}


class NotReady(Exception):
    """A session that cannot be written (yet): a partial day, or one recorded before cards carried both scores."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------- which period the live score reads
def read_report(base: Path, market: str) -> Optional[Dict[str, Any]]:
    try:
        got = json.loads((Path(base) / REPORTS[market]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) and got.get("verdict") else None


SWITCH_FILE = Path("data") / "qsf" / "fund_period_switch.json"          # the screen's button, one entry per market


def stored_switch(base: Path, market: str) -> Optional[str]:
    try:
        got = (json.loads((Path(base) / SWITCH_FILE).read_text(encoding="utf-8")).get(market) or {}).get("period")
    except (OSError, ValueError, AttributeError):
        return None
    return got if got in PERIODS else None


def live_period(base: Path, market: str) -> str:
    """ANNUAL unless the user switched it: .env first, then the screen's button.  Since 2026-11-23 the reading only reports
    (user decision): its verdict rested on swing results and would have changed the long score's input too, under the same
    model version."""
    forced = os.environ.get(SWITCH, "").strip().upper()
    if forced in PERIODS:
        return forced
    return stored_switch(base, market) or DEFAULT


def set_period(base: Path, market: str, period: str, now: Optional[Any] = None) -> Dict[str, Any]:
    """The screen's button.  Trailing statements can be switched on only after the market's reading exists; back to annual always."""
    from datetime import datetime, timezone
    from utils import durable
    period = str(period or "").upper()
    if market not in REPORTS or period not in PERIODS:
        raise ValueError("BAD_VALUE")
    if period == "TRAILING" and read_report(base, market) is None:
        return {"status": "REFUSED", "market": market, "reason": "240거래일 판정이 나온 뒤에 바꿀 수 있습니다. 그 전에 바꾸면 비교하려는 두 점수 가운데 하나가 실전 점수가 되어 비교가 뜻을 잃습니다."}
    path = Path(base) / SWITCH_FILE
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc = doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        doc = {}
    doc[market] = {"period": period, "at": (now or (lambda: datetime.now(timezone.utc)))().isoformat()}
    path.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(path, json.dumps(doc, ensure_ascii=False, indent=1))
    forced = os.environ.get(SWITCH, "").strip().upper()
    return {"status": "OK", "market": market, "period": period, "live_period": live_period(base, market),
            "note": f".env의 {SWITCH}={forced} 가 이 버튼보다 먼저 읽힙니다." if forced in PERIODS else
                    "다음 스캔부터 이 시장의 점수가 이 재무 기준을 읽습니다. 공식 버전은 그대로이고, 기록의 각 줄에 어느 기준이 실전이었는지 남습니다."}


def card_field(live: str, live_score: Optional[float], live_fund: Dict[str, Any], other_score: Optional[float], other_fund: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """What a card keeps: both scores under their own names, whichever is live."""
    other = "TRAILING" if live == "ANNUAL" else "ANNUAL"
    side = lambda score, fund: {"score": None if score is None else round(float(score), 3), "fiscal_end": (fund or {}).get("fiscal_end"), "filed": (fund or {}).get("filed"),      # noqa: E731
                                "newer_quarter": (fund or {}).get("period_basis") == "TRAILING"}
    return {"live": live, live.lower(): side(live_score, live_fund), other.lower(): side(other_score, other_fund)}


# ---------------------------------------------------------------------- the record
def score_session(snaps: List[Dict[str, Any]], session: str, market: str) -> Dict[str, Any]:
    fresh = sorted((s for s in snaps if s.get("data_date") == session and s.get("score") is not None and s.get("strategy") in HORIZONS), key=lambda s: (s["ticker"], s["strategy"]))
    if fresh and not any(s.get("fund_period") for s in fresh):
        raise NotReady("NO_SECOND_SCORE")
    rows = []
    for s in fresh:
        fp = s.get("fund_period") or {}
        a, t = fp.get("annual") or {}, fp.get("trailing") or {}
        rows.append({"ticker": s["ticker"], "strategy": s["strategy"], "annual": a.get("score"), "trailing": t.get("score"), "annual_end": a.get("fiscal_end"), "trailing_end": t.get("fiscal_end"),
                     "newer_quarter": bool(t.get("newer_quarter")), "entry_session": s.get("entry_session"), "actionability": s.get("actionability")})
    if sum(1 for r in rows if r["strategy"] == "SWING" and r["trailing"] is not None) < MIN_ROWS:
        raise NotReady("TOO_FEW_STOCKS")
    live = {(s.get("fund_period") or {}).get("live") for s in fresh} - {None}
    return {"session": session, "market": market, "protocol": PROTOCOL, "model_versions": sorted({str(s.get("model_version")) for s in fresh}),
            "live_period": sorted(live)[0] if len(live) == 1 else "MIXED", "newer_quarter": sum(1 for r in rows if r["strategy"] == "SWING" and r["newer_quarter"]), "rows": rows}


def _session_snaps(led: Ledger, market: str, session: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in led._live_rows():
        if r["market"] == market and r["session"] == session:
            out += led._load(r)
    return out


def record(base: Path, market: str, now: Callable[[], datetime] = _utcnow, first: str = FIRST) -> Dict[str, Any]:
    """OK: every ledger session whose cards carry both scores is written.  WAITING: a session in the ledger is still partial."""
    at, folder = now(), FOLDERS[market]
    led = Ledger(Path(base))
    if led.verify()["status"] != "OK":
        return {"status": "FAILED", "reason": "LEDGER_BROKEN"}
    sessions = sorted({r["session"] for r in led._live_rows() if r["market"] == market and r["session"] >= first})
    done = {r["session"] for r in kf.read_index(base, folder)}
    wrote: List[str] = []
    partial: List[str] = []
    before: List[str] = []
    for day in sessions:
        if day in done:
            continue
        try:
            if kf.write_record(base, day, at, day != sessions[-1], store=folder, scorer=lambda b, d: score_session(_session_snaps(led, market, d), d, market)):
                wrote.append(day)
        except NotReady as exc:
            (before if str(exc) == "NO_SECOND_SCORE" else partial).append(day)
    return {"status": "WAITING" if partial else "OK", "market": market, "written": wrote, "partial": partial, "without_second_score": before,
            "last": max(done | set(wrote), default=None), "sessions": len(done) + len(wrote)}


def status(base: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {"protocol": PROTOCOL, "read_at": READ_AT, "first": FIRST, "switch": SWITCH, "markets": {}}
    for market, folder in FOLDERS.items():
        rows = kf.read_index(base, folder)
        rep = read_report(base, market)
        out["markets"][market] = {"records": len(rows), "first": rows[0]["session"] if rows else None, "last": rows[-1]["session"] if rows else None,
                                  "late": sum(1 for r in rows if r.get("late")), "evaluated": rep is not None, "verdict": (rep or {}).get("verdict"), "live_period": live_period(base, market),
                                  "switch": stored_switch(base, market), "can_switch": rep is not None and os.environ.get(SWITCH, "").strip().upper() not in PERIODS}
    return out


# ---------------------------------------------------------------------- the single reading
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
        top = (market, strategy) in TOP_FIFTH          # Korea, swing: the day's top fifth (the band of 70 is empty there)
        annual, trailing = _band(col("annual"), able, ret, cost, top), _band(col("trailing"), able, ret, cost, top)
        out.append({"session": doc["session"], "annual": annual, "trailing": trailing, "diff": trailing["ret"] - annual["ret"],
                    "ic_annual": _ic(col("annual"), ret), "ic_trailing": _ic(col("trailing"), ret), "late": bool(doc.get("late"))})
    return out


def summarize(days: List[Dict[str, Any]], lag: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {"days": len(days)}
    for k in ("annual", "trailing"):
        r = np.array([d[k]["ret"] for d in days], dtype=float)
        worst = np.sort(r)[:max(1, len(r) // 10)]
        out[k] = {"mean": float(r.mean()), "sd": float(r.std(ddof=1)) if len(r) > 1 else None, "worst_tenth": float(worst.mean()),
                  "empty_share": float(np.mean([d[k]["names"] == 0 for d in days])), "mean_names": float(np.mean([d[k]["names"] for d in days])), "ic": _mean(d[f"ic_{k}"] for d in days)}
    diff = [d["diff"] for d in days]
    out["difference"] = {"mean": float(np.mean(diff)), "t": validate.newey_west_t(diff, lag), "days_with_difference": int(sum(1 for x in diff if x != 0))}
    out["difference"]["t_bar"] = calibrate.bar(MIN_T, len(diff), lag, 1, lag)          # the bar for this sample's own design (2026-11-22)
    return out


def verdict(diff: Dict[str, Any]) -> str:
    """Both conditions must hold: the two scores picked different stocks on at least ``MIN_DIFF_DAYS`` days, and the mean
    difference stands ``MIN_T`` standard errors from zero.  A reading without the day count (none exists) does not pass."""
    m, t = diff["mean"], diff["t"]
    if t is None or (diff.get("days_with_difference") or 0) < MIN_DIFF_DAYS:
        return "NOT_DISTINGUISHED"
    bar = diff.get("t_bar") or MIN_T
    return "TRAILING_BETTER" if m > 0 and t >= bar else "ANNUAL_BETTER" if m < 0 and t <= -bar else "NOT_DISTINGUISHED"


def reasons(s: Dict[str, Any], code: str, top: bool = False) -> List[str]:
    d, t = s["difference"], s["difference"]["t"]
    what = "그날 실행 가능한 종목 가운데 점수 상위 20%를" if top else "점수 70 이상이고 실행 가능한 종목을"
    return [f"잰 것: {what} 같은 비중으로 20거래일 보유한 수익(비용 차감), {s['days']}거래일.",
            f"하루 평균: 최근 4분기 {s['trailing']['mean'] * 100:+.2f}%, 연간 {s['annual']['mean'] * 100:+.2f}%. 차이 {d['mean'] * 100:+.2f}%p, t {'없음' if t is None else format(t, '+.2f')} (기준: 차이가 양수이고 t {(d.get('t_bar') or MIN_T):g} 이상).",
            f"두 점수가 다른 종목을 고른 날: {d.get('days_with_difference', 0)}일 (기준: {MIN_DIFF_DAYS}일 이상). 기준 t {(d.get('t_bar') or MIN_T):g}은 표의 값 {MIN_T:g}을 이 표본 구조(겹치는 20거래일 수익의 하루 값)에서 우연히 넘는 비율이 표와 같아지도록 모의실험으로 고친 값입니다.",
            f"후보가 없던 날의 비율: 최근 4분기 {s['trailing']['empty_share'] * 100:.0f}%, 연간 {s['annual']['empty_share'] * 100:.0f}%.",
            "최근 4분기 쪽이 나았습니다. 자동으로 바꾸지는 않습니다(2026-11-23 결정). 바꾸려면 순위·카드 탭 '판정 일정'의 재무 기준 칸에서 버튼을 누릅니다." if code == ADOPT else "라이브 점수는 연간 재무 그대로입니다."]


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
    code = verdict(s["difference"])
    top = (market, "SWING") in TOP_FIFTH
    res = {"status": "REAL", "protocol": PROTOCOL, "market": market, "records": len(docs), "first": swing[0]["session"], "last": last, "band": 70.0,
           "selection": "TOP_FIFTH" if top else "BAND",          # Korea: no swing score has reached 70, so the band could never differ (amendment 2026-11-22)
           "verdict": code, "applies": "ANNUAL", "applies_itself": False, "reasons": reasons(s, code, top), "swing": s,
           "long": {**summarize(long_days, HORIZONS["LONG_TERM"]), "reading": "FIGURES_ONLY"} if long_days else {"days": 0},
           "late_share": float(np.mean([d["late"] for d in swing])),
           "note": f"NOT_DISTINGUISHED는 '차이 없음'이 아니라 '아직 모름'입니다. 뒤집으려면 .env에 {SWITCH}=ANNUAL 또는 TRAILING을 적습니다."}
    target.parent.mkdir(parents=True, exist_ok=True)
    durable.write_text(target, json.dumps(res, ensure_ascii=False, indent=1))
    return res
