"""Every one-time reading, made by the program itself.  Guide: reports/RUNBOOK.md.

Each forward record has one reading fixed by its protocol.  Until 2026-11-16 a reading was made by typing its command, so a reading
nobody typed would never have been made.  This module lists them all: the command that makes it, the report it writes, the record it
waits for and how many sessions that record needs.  The daily job (``automation.Daily._readings``) runs a reading's own command on the
day its record is long enough, tells the verdict once, and never runs a reading again once its report exists: the one-reading rule
of every protocol is kept by the report file, as before.

Nothing here changes a score, a universe or a rule.  Every protocol in this list says the verdict is reported and the user decides;
the two comparison books that do apply their own decision (turnover and rank rules) have their own modules and are only shown here.
"""
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from terminal.qsf import kr_forward as kf

GUIDE = "reports/RUNBOOK.md"
GIVE_UP = 15                    # attempts without a report after which the user is told once; later attempts come a week apart
RETRY_DAYS = 7
REPORTS = Path("reports") / "qsf"
STORES = Path("research_data")
LEDGER_FIRST = "2026-11-09"     # live_forward.FIRST: the first ledger session the live verdicts read
NO_CHANGE = "이 결과로 점수·스캔 대상·규칙이 자동으로 바뀌지는 않습니다."


def _e(key: str, label: str, argv: List[str], report: str, protocol: str, need: int, horizon: int, store: Optional[str] = None, ledger: Optional[str] = None,
       verdict: tuple = ("verdict",), after: str = NO_CHANGE) -> Dict[str, Any]:
    return {"key": key, "label": label, "argv": argv, "report": report, "protocol": f"reports/{protocol}", "need": need, "horizon": horizon, "store": store, "ledger": ledger,
            "verdict": verdict, "after": after}


def _per_market(key: str, label: str, action: str, report: str, protocol: str, need: int, horizon: int, store: Optional[str] = None, ledger: bool = False, **kw) -> List[Dict[str, Any]]:
    return [_e(f"{key}_{m.lower()}", f"{label}({ko})", ["--market", m, "qsf", action], report.format(m=m), protocol, need, horizon,
               store=store.format(m=m.lower()) if store else None, ledger=m if ledger else None, **kw) for m, ko in (("KR", "한국"), ("US", "미국"))]


# need: sessions whose outcome must have ended; horizon: sessions an outcome takes.  A record of need + horizon sessions is long enough.
REGISTRY: List[Dict[str, Any]] = [
    *_per_market("live_swing", "실전 점수 판정 · 스윙", "live-forward-evaluate-swing", "QSF_LIVE_FORWARD_{m}_SWING.json", "QSF_LIVE_FORWARD_PROTOCOL.md", 240, 20, ledger=True),
    *_per_market("live_long", "실전 점수 판정 · 장기", "live-forward-evaluate-long", "QSF_LIVE_FORWARD_{m}_LONG_TERM.json", "QSF_LIVE_FORWARD_PROTOCOL.md", 756, 63, ledger=True),
    _e("kr_avoid_marks", "한국 회피 표시 판정", ["qsf", "kr-avoid-marks-evaluate"], "QSF_KR_AVOID_MARKS.json", "QSF_KR_AVOID_MARKS_PROTOCOL.md", 240, 20, ledger="KR",
       after="AVOID_RULE_SUPPORTED가 나와도 매수 후보에서 자동으로 빼지 않습니다. 화면의 회피 표시를 보고 직접 판단합니다."),
    *_per_market("score_split", "점수 분리 비교", "score-split-evaluate", "QSF_SCORE_SPLIT_{m}.json", "QSF_SCORE_SPLIT_PROTOCOL.md", 240, 20, store="score_split_{m}",
                 after="WITH_REGIME_BETTER가 나와도 점수를 자동으로 되돌리지 않습니다."),
    *_per_market("regime_weights", "국면 가중치 기록 읽기", "regime-weights-evaluate", "QSF_REGIME_WEIGHTS_FORWARD_{m}.json", "QSF_REGIME_WEIGHTS_PROTOCOL.md", 240, 20,
                 store="regime_weights_{m}", verdict=("reading",), after="판정 없이 수치만 적는 읽기입니다. 아무것도 바뀌지 않습니다."),
    _e("us_challenger_swing", "미국 도전자 점수 · 스윙", ["qsf", "us-challenger-evaluate-swing"], "QSF_US_CHALLENGER_SWING.json", "QSF_US_CHALLENGER_PROTOCOL.md", 240, 20,
       store="us_challenger", verdict=("supports_challenger",)),
    _e("us_challenger_long", "미국 도전자 점수 · 장기", ["qsf", "us-challenger-evaluate-long"], "QSF_US_CHALLENGER_LONG.json", "QSF_US_CHALLENGER_PROTOCOL.md", 756, 63,
       store="us_challenger", verdict=("supports_challenger",)),
    _e("kr_forward", "한국 가격 점수", ["qsf", "kr-forward-evaluate"], "QSF_KR_FORWARD.json", "QSF_KR_FORWARD_PROTOCOL.md", 240, 20, store="krx_forward"),
    _e("kr_forward_fund", "한국 재무 점수", ["qsf", "kr-forward-evaluate-fund"], "QSF_KR_FORWARD_FUND.json", "QSF_KR_FORWARD_PROTOCOL.md", 240, 20, store="krx_forward_fund"),
    _e("kr_forward_events", "한국 공시 이벤트", ["qsf", "kr-forward-evaluate-events"], "QSF_KR_FORWARD_EVENTS.json", "QSF_KR_EVENTS_FORWARD_PROTOCOL.md", 240, 20,
       store="krx_forward_events", verdict=("reading",)),
    _e("kr_cap_universe", "한국 시가총액 대상", ["qsf", "kr-cap-universe-evaluate"], "QSF_KR_CAP_UNIVERSE.json", "QSF_KR_CAP_UNIVERSE_PROTOCOL.md", 240, 20, store="kr_cap_universe",
       verdict=("universe", "reading")),
    _e("kr_traded_universe", "한국 이전 스캔 대상(거래대금)", ["qsf", "kr-traded-universe-evaluate"], "QSF_KR_TRADED_UNIVERSE.json", "QSF_KR_TRADED_UNIVERSE_PROTOCOL.md", 240, 20,
       store="kr_traded_universe", verdict=("universe", "reading"), after="FORMER_BETTER가 나와도 스캔 대상을 자동으로 되돌리지 않습니다."),
    _e("kr_swing_challenger", "한국 스윙 도전자", ["qsf", "kr-swing-challenger-evaluate"], "QSF_KR_SWING_CHALLENGER.json", "QSF_KR_SWING_CHALLENGER_PROTOCOL.md", 240, 20,
       store="kr_swing_challenger"),
    _e("kr_swing_prior", "한국 이전 스윙 공식", ["qsf", "kr-swing-prior-evaluate"], "QSF_KR_SWING_PRIOR.json", "QSF_KR_SWING_PRIOR_PROTOCOL.md", 240, 20, store="kr_swing_prior",
       after="PRIOR_BETTER가 나와도 점수 공식을 자동으로 되돌리지 않습니다."),
    _e("kr_method_120", "한국 독자 매매법 · 120일 읽기", ["qsf", "kr-method-evaluate-120"], "QSF_KR_METHOD_FORWARD_120.json", "QSF_KR_METHOD_PROTOCOL.md", 120, 10, store="kr_method",
       after="METHOD_SUPPORTED가 나와도 매매 보조 화면의 진입 규칙은 자동으로 바뀌지 않습니다."),
    _e("kr_method_240", "한국 독자 매매법 · 240일 읽기", ["qsf", "kr-method-evaluate-240"], "QSF_KR_METHOD_FORWARD_240.json", "QSF_KR_METHOD_PROTOCOL.md", 240, 10, store="kr_method",
       after="METHOD_SUPPORTED가 나와도 매매 보조 화면의 진입 규칙은 자동으로 바뀌지 않습니다."),
]

VERDICT_KO = {
    "WEAK_POSITIVE_EVIDENCE": "약한 근거가 있습니다(순위 조건과 수익 조건을 모두 채움)",
    "RANK_ONLY": "순위 근거만 있습니다(상위 종목의 수익 조건은 채우지 못함)",
    "NO_EVIDENCE": "근거를 찾지 못했습니다. 효과가 없다는 뜻이 아니라 확인되지 않았다는 뜻입니다",
    "NOT_DISTINGUISHED": "구분되지 않았습니다. 차이가 없다는 뜻이 아니라 아직 모른다는 뜻입니다",
    "SAME_DIRECTION_NOT_SIGNIFICANT": "같은 방향이지만 통계로 구분되지 않았습니다",
    "NOT_SUPPORTED": "지지되지 않았습니다",
    "UNIVERSE_BETTER": "시가총액 대상 쪽이 나았습니다",
    "SWITCH_SUPPORTED": "스캔 대상을 바꾼 결정이 지지됐습니다",
    "FORMER_BETTER": "이전 스캔 대상 쪽이 나았습니다",
    "CHALLENGER_BETTER": "도전자 공식이 지금 공식보다 나았습니다",
    "CHALLENGER_HAS_EVIDENCE": "도전자 공식에 근거가 있지만 지금 공식보다 낫다고 구분되지는 않았습니다",
    "DECISION_SUPPORTED": "2026-11-11에 공식을 바꾼 결정이 지지됐습니다",
    "PRIOR_BETTER": "이전 공식 쪽이 나았습니다",
    "SPLIT_BETTER": "시장 국면을 뺀 지금 점수 쪽이 나았습니다",
    "WITH_REGIME_BETTER": "시장 국면을 넣은 이전 점수 쪽이 나았습니다",
    "AVOID_RULE_SUPPORTED": "회피 표시가 붙은 종목을 빼는 규칙이 지지됐습니다",
    "MARKS_FLAG_LOSERS_BUT_SCORE_KNOWS": "회피 표시가 부진한 종목을 가리키지만 점수가 이미 반영하고 있습니다",
    "METHOD_SUPPORTED": "매매법이 지지됐습니다",
    "NO_PRIMARY": "미리 고른 주 매매법이 없어 판정하지 않고 수치만 적었습니다",
    "FIGURES_ONLY": "판정 없이 수치만 적었습니다",
    "True": "도전자 점수가 지지됐습니다",
    "False": "도전자 점수가 지지되지 않았습니다",
}


def report_path(base: Path, e: Dict[str, Any]) -> Path:
    return Path(base) / REPORTS / e["report"]


def report(base: Path, e: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The reading's stored report.  None: not read yet (or the file cannot be parsed, which is treated as not read and tried again)."""
    p = report_path(base, e)
    if not p.exists():
        return None
    try:
        got = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


def records(base: Path, e: Dict[str, Any]) -> Optional[int]:
    """Sessions the reading's record has so far: its own store's index, or the live ledger's sessions of its market."""
    if e.get("store"):
        return len(kf.read_index(Path(base), STORES / e["store"]))
    if e.get("ledger"):
        from terminal.qsf.ledger import Ledger
        return len({r["session"] for r in Ledger(Path(base))._live_rows() if r["market"] == e["ledger"] and r["session"] >= LEDGER_FIRST})
    return None


def wanted(e: Dict[str, Any]) -> int:
    return e["need"] + e["horizon"]


def due(base: Path, e: Dict[str, Any]) -> bool:
    """Long enough to be worth asking the reading's own command, which alone decides whether it reads."""
    n = records(base, e)
    return n is not None and n >= wanted(e)


def verdict(e: Dict[str, Any], rep: Dict[str, Any]) -> str:
    got: Any = rep
    for k in e["verdict"]:
        got = got.get(k) if isinstance(got, dict) else None
    if isinstance(got, dict):                       # kr_method: {method: verdict}
        return ", ".join(f"{k}: {v}" for k, v in sorted(got.items())) or "?"
    return "?" if got is None else str(got)


def meaning(code: str) -> str:
    if ": " in code:                                # several verdicts in one report (kr_method: one per method)
        return "; ".join(f"{k}: {VERDICT_KO.get(v, v)}" for k, v in (part.split(": ", 1) for part in code.split(", ")))
    return VERDICT_KO.get(code, "뜻은 규칙 문서에 있습니다")


def text(e: Dict[str, Any], rep: Dict[str, Any]) -> str:
    """The notice sent once when a reading has been made."""
    code = verdict(e, rep)
    lines = [f"[판정 · {e['label']}] {code}", meaning(code) + ".", e["after"],
             f"수치: {REPORTS / e['report']} · 규칙: {e['protocol']} · 터미널 점수 탭의 '판정 일정'에서도 볼 수 있습니다."]
    return "\n".join(lines)


def stuck_text(e: Dict[str, Any], tries: int) -> str:
    return (f"[판정 · {e['label']}] 기록은 충분한데 {tries}번 읽지 못했습니다. 매일 작업 기록(data/automation/logs/의 그날 파일, 'READING' 부분)에 이유가 있습니다. "
            f"이제 일주일에 한 번 다시 시도합니다. 안내: {GUIDE}")


def _eta(left: int, today: date) -> str:
    return (today + timedelta(days=round(left * 7 / 5))).isoformat()[:7]


def status(base: Path, today: date, tried: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """What the screen shows: every reading, how far its record is, when it is expected, and the verdict once read."""
    from terminal.qsf import rank_book, turnover_book
    base, rows = Path(base), []
    for e in REGISTRY:
        rep, n = report(base, e), records(base, e)
        row = {"key": e["key"], "label": e["label"], "protocol": e["protocol"], "records": n, "wanted": wanted(e), "after": e["after"], "applies_itself": False,
               "attempts": ((tried or {}).get(e["key"]) or {}).get("failed", 0)}
        if rep is not None:
            code = verdict(e, rep)
            row.update(state="READ", verdict=code, meaning=meaning(code), report=str(REPORTS / e["report"]))
        else:
            left = None if n is None else max(wanted(e) - n, 0)
            row.update(state="DUE" if left == 0 else "WAITING", left=left, expected=None if left is None else _eta(left, today))
        rows.append(row)
    for book, label in ((turnover_book, "회전율 규칙 비교"), (rank_book, "순위 규칙 비교")):
        for m, ko in (("KR", "한국"), ("US", "미국")):
            s = book.status(base, m)
            row = {"key": f"{book.VERSION}_{m}", "label": f"{label}({ko})", "protocol": book.PROTOCOL, "records": s["records"], "wanted": s["read_at"], "applies_itself": True,
                   "after": "적용으로 정해지면 프로그램이 스스로 규칙을 바꿉니다. .env로 뒤집을 수 있습니다.", "attempts": 0}
            if s["status"] == "DECIDED":
                row.update(state="READ", verdict=s["decision"]["decision"], meaning="규칙 적용" if s["decision"]["decision"] == "ADOPT" else "기존 규칙 유지", report=str(book.REPORTS[m]))
            else:
                row.update(state="DUE" if s["left"] == 0 else "WAITING", left=s["left"], expected=_eta(s["left"], today))
            rows.append(row)
    return {"status": "REAL", "guide": GUIDE, "readings": rows, "read": sum(1 for r in rows if r["state"] == "READ"), "total": len(rows),
            "note": "판정은 때가 되면 매일 작업이 스스로 읽고 텔레그램으로 알립니다. 사람이 할 일은 없습니다. 예상 시점은 기록이 하루도 빠지지 않는다고 본 어림입니다."}
