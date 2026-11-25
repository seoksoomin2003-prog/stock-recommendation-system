"""Every one-time reading, made by the program itself.  Guide: reports/RUNBOOK.md.

Each forward record has one reading fixed by its protocol.  Until 2026-11-16 a reading was made by typing its command, so a reading
nobody typed would never have been made.  This module lists them all: the command that makes it, the report it writes, the record it
waits for and how many sessions that record needs.  The daily job (``automation.Daily._readings``) runs a reading's own command on the
day its record is long enough, tells the verdict once, and never runs a reading again once its report exists: the one-reading rule
of every protocol is kept by the report file, as before.

Nothing here changes a score, a universe or a rule.  Every protocol in this list but one says the verdict is reported and the user
decides.  The one (``applies``: the fund-period comparison) names in its protocol what its verdict changes, and the change is made
where the score is computed (``fund_period.live_period`` reads the report this module only tells of).  The two comparison books that
apply their own decision (turnover and rank rules) have their own modules and are only shown here.
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
LEDGER_FIRST = "2026-11-25"     # live_forward.FIRST: the first ledger session the live verdicts read (moved 2026-11-22 and, with QSF-1.6.0, 2026-11-25; user decisions)
PRIMARY_KEYS = ("live_swing_", "live_long_")
KIND_KO = {True: "주된 판정", False: "참고 판정"}
REFERENCE_NOTE = "참고 판정입니다. 판정이 서른 개쯤이라 그중 몇은 우연히 기준을 넘을 수 있으므로, 점수가 통하는지는 실전 점수 판정 넷(미국·한국의 스윙·장기)으로 답합니다."
NO_CHANGE = "이 결과로 점수·스캔 대상·규칙이 자동으로 바뀌지는 않습니다."


def _e(key: str, label: str, argv: List[str], report: str, protocol: str, need: int, horizon: int, store: Optional[str] = None, ledger: Optional[str] = None,
       verdict: tuple = ("verdict",), after: str = NO_CHANGE, applies: bool = False, committee: Optional[str] = None) -> Dict[str, Any]:
    # ``primary``: the four verdicts of the live score.  Thirty readings are scheduled; with that many, some pass by chance
    # (audit 2026-11-22, QNT-04).  The four are the ones the question "does the score work" is answered by; every other
    # reading is reference (user decision 2026-11-22) and is said to be in its notice and on the schedule.
    return {"key": key, "label": label, "argv": argv, "report": report, "protocol": f"reports/{protocol}", "need": need, "horizon": horizon, "store": store, "ledger": ledger,
            "verdict": verdict, "after": after, "applies": applies, "committee": committee, "primary": key.startswith(PRIMARY_KEYS)}


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
    *_per_market("fund_period", "재무 기준 기간 비교", "fund-period-evaluate", "QSF_FUND_PERIOD_{m}.json", "QSF_FUND_PERIOD_PROTOCOL.md", 240, 20, store="fund_period_{m}", applies=False,
                 after="TRAILING_BETTER가 나와도 프로그램이 스스로 바꾸지 않습니다(2026-11-23 결정). 결과를 알리고, 바꾸려면 이 표의 그 줄에 생기는 버튼을 누릅니다. .env의 QSF_FUND_PERIOD가 있으면 그 값이 먼저입니다."),
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
    _e("kr_challenger_swing", "한국 묶음 도전자 점수 · 스윙", ["qsf", "kr-challenger-evaluate-swing"], "QSF_KR_CHALLENGER_SWING.json", "QSF_KR_CHALLENGER_PROTOCOL.md", 240, 20,
       store="kr_challenger", after="CHALLENGER_BETTER가 나와도 점수 공식은 자동으로 바뀌지 않습니다."),
    _e("kr_challenger_long", "한국 묶음 도전자 점수 · 장기", ["qsf", "kr-challenger-evaluate-long"], "QSF_KR_CHALLENGER_LONG.json", "QSF_KR_CHALLENGER_PROTOCOL.md", 756, 63,
       store="kr_challenger", after="CHALLENGER_BETTER가 나와도 점수 공식은 자동으로 바뀌지 않습니다."),
    _e("kr_method_120", "한국 독자 매매법 · 120일 읽기", ["qsf", "kr-method-evaluate-120"], "QSF_KR_METHOD_FORWARD_120.json", "QSF_KR_METHOD_PROTOCOL.md", 120, 10, store="kr_method",
       after="METHOD_SUPPORTED가 나와도 매매 보조 화면의 진입 규칙은 자동으로 바뀌지 않습니다."),
    _e("kr_method_240", "한국 독자 매매법 · 240일 읽기", ["qsf", "kr-method-evaluate-240"], "QSF_KR_METHOD_FORWARD_240.json", "QSF_KR_METHOD_PROTOCOL.md", 240, 10, store="kr_method",
       after="METHOD_SUPPORTED가 나와도 매매 보조 화면의 진입 규칙은 자동으로 바뀌지 않습니다."),
    # the six portfolios of the investment committee (terminal/committee): 240 paper days need 242 recorded sessions
    *[_e(f"committee_paper_{m.lower()}", f"투자위원회 여섯 포트폴리오 가상 성과({ko})", ["--market", m, "qsf", "committee-evaluate"], f"IC1_PAPER_{m}.json", "IC1_PAPER_READING_PROTOCOL.md", 240, 2,
         committee=m, after="PAPER_BETTER가 나와도 엔진·위원회·포트폴리오의 규칙과 점수는 자동으로 바뀌지 않습니다.") for m, ko in (("KR", "한국"), ("US", "미국"))],
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
    "LIVE_BETTER": "지금 공식(사람이 정한 배점)이 도전자 공식보다 나았습니다",
    "DECISION_SUPPORTED": "2026-11-11에 공식을 바꾼 결정이 지지됐습니다",
    "PRIOR_BETTER": "이전 공식 쪽이 나았습니다",
    "SPLIT_BETTER": "시장 국면을 뺀 지금 점수 쪽이 나았습니다",
    "TRAILING_BETTER": "최근 4분기 재무로 계산한 점수 쪽이 나았습니다",
    "ANNUAL_BETTER": "연간 재무로 계산한 점수 쪽이 나았습니다",
    "WITH_REGIME_BETTER": "시장 국면을 넣은 이전 점수 쪽이 나았습니다",
    "AVOID_RULE_SUPPORTED": "회피 표시가 붙은 종목을 빼는 규칙이 지지됐습니다",
    "MARKS_FLAG_LOSERS_BUT_SCORE_KNOWS": "회피 표시가 부진한 종목을 가리키지만 점수가 이미 반영하고 있습니다",
    "METHOD_SUPPORTED": "매매법이 지지됐습니다",
    "NO_PRIMARY": "미리 고른 주 매매법이 없어 판정하지 않고 수치만 적었습니다",
    "PAPER_BETTER": "여섯 가상 포트폴리오 가운데 지수보다 나았다고 볼 만한 것이 있습니다(어느 것인지는 아래 줄에)",
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
    if e.get("committee"):
        from terminal.committee import record
        return len(record.read(Path(base), e["committee"]))
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


def why(rep: Dict[str, Any]) -> List[str]:
    """The report's own lines on what was measured and which condition decided, when it carries them."""
    got = rep.get("reasons") if isinstance(rep, dict) else None
    return [str(x) for x in got] if isinstance(got, list) else []


def text(e: Dict[str, Any], rep: Dict[str, Any]) -> str:
    """The notice sent once when a reading has been made."""
    code = verdict(e, rep)
    lines = [f"[{KIND_KO[bool(e.get('primary'))]} · {e['label']}] {code}", meaning(code) + ".", *why(rep), *([] if e.get("primary") else [REFERENCE_NOTE]), e["after"],
             f"수치: {REPORTS / e['report']} · 규칙: {e['protocol']} · 터미널 순위·카드 탭의 '판정 일정'에서도 볼 수 있습니다."]
    return "\n".join(lines)


def stuck_text(e: Dict[str, Any], tries: int) -> str:
    return (f"[판정 · {e['label']}] 기록은 충분한데 {tries}번 읽지 못했습니다. 매일 작업 기록(data/automation/logs/의 그날 파일, 'READING' 부분)에 이유가 있습니다. "
            f"이제 일주일에 한 번 다시 시도합니다. 안내: {GUIDE}")


def damaged_text(e: Dict[str, Any]) -> str:
    return (f"[판정 · {e['label']}] 결과 파일 reports/qsf/{e['report']} 이 있지만 읽을 수 없습니다(손상). 다시 읽지 않습니다. "
            f"백업 폴더의 reports_qsf/ 안에 같은 이름의 파일이 있으면 그것으로 바꾸세요. 안내: {GUIDE}")


SESSIONS_A_YEAR = 250          # about 252 in New York and 245 in Seoul: weekdays less some ten holidays


def _eta(left: int, today: date) -> str:
    """The month ``left`` sessions from now.  Until 2026-11-22 this counted weekdays only and came out about two weeks early a year."""
    return (today + timedelta(days=round(left * 365 / SESSIONS_A_YEAR))).isoformat()[:7]


def status(base: Path, today: date, tried: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """What the screen shows: every reading, how far its record is, when it is expected, and the verdict once read."""
    from terminal.qsf import rank_book, turnover_book
    base, rows = Path(base), []
    for e in REGISTRY:
        rep, n = report(base, e), records(base, e)
        row = {"key": e["key"], "label": e["label"], "protocol": e["protocol"], "records": n, "wanted": wanted(e), "after": e["after"], "applies_itself": bool(e.get("applies")), "primary": bool(e.get("primary")),
               "attempts": ((tried or {}).get(e["key"]) or {}).get("failed", 0)}
        if rep is not None:
            code = verdict(e, rep)
            row.update(state="READ", verdict=code, meaning=meaning(code), report=str(REPORTS / e["report"]), reasons=why(rep))
        else:
            left = None if n is None else max(wanted(e) - n, 0)
            row.update(state="DUE" if left == 0 else "WAITING", left=left, expected=None if left is None else _eta(left, today))
        if e["key"].startswith("fund_period_"):           # the one reading with a button of its own on this table
            from terminal.qsf import fund_period
            m = e["key"].rsplit("_", 1)[1].upper()
            st = fund_period.status(base)["markets"][m]
            row["switch"] = {"market": m, "live_period": st["live_period"], "can_switch": st["can_switch"]}
        rows.append(row)
    for book, label in ((turnover_book, "회전율 규칙 비교"), (rank_book, "순위 규칙 비교")):
        for m, ko in (("KR", "한국"), ("US", "미국")):
            s = book.status(base, m)
            itself = False                                # both readings report and apply nothing by themselves (user decisions 2026-11-22)
            row = {"key": f"{book.VERSION}_{m}", "label": f"{label}({ko})", "protocol": book.PROTOCOL, "records": s["records"], "wanted": s["read_at"], "applies_itself": itself, "primary": False,
                   "after": "적용으로 정해지면 프로그램이 스스로 규칙을 바꿉니다. .env로 뒤집을 수 있습니다." if itself else
                   "조건을 채워도 프로그램이 스스로 규칙을 바꾸지 않습니다. 결과를 알리고, 쓰려면 순위·카드 탭 가상 장부의 그 규칙 칸에서 '이 규칙 쓰기'를 누릅니다.", "attempts": 0}
            if s["status"] == "DECIDED":
                adopt = s["decision"]["decision"] == "ADOPT"
                row.update(state="READ", verdict=s["decision"]["decision"], meaning=("규칙 적용" if itself else "적용 조건 충족(자동 적용 안 함)") if adopt else "기존 규칙 유지", report=str(book.REPORTS[m]))
            else:
                row.update(state="DUE" if s["left"] == 0 else "WAITING", left=s["left"], expected=_eta(s["left"], today))
            rows.append(row)
    from terminal.qsf import entry_book                     # the entry comparison (EN-1, 2026-11-25): it reports which book did better and changes nothing
    for m, ko in (("KR", "한국"), ("US", "미국")):
        s = entry_book.status(base, m)
        row = {"key": f"{entry_book.VERSION}_{m}", "label": f"진입 규칙 비교({ko})", "protocol": entry_book.PROTOCOL, "records": s["records"], "wanted": s["read_at"], "applies_itself": False,
               "primary": False, "attempts": 0, "after": "결과만 알립니다. 진입 규칙은 스스로 바뀌지 않고, 바꿀지는 결과를 보고 직접 정합니다."}
        if s["status"] == "DECIDED":
            row.update(state="READ", verdict=s["decision"]["decision"], meaning=entry_book.DECISION_KO[s["decision"]["decision"]], report=str(entry_book.REPORTS[m]))
        else:
            row.update(state="DUE" if s["left"] == 0 else "WAITING", left=s["left"], expected=_eta(s["left"], today))
        rows.append(row)
    return {"status": "REAL", "guide": GUIDE, "readings": rows, "read": sum(1 for r in rows if r["state"] == "READ"), "total": len(rows),
            "note": "판정은 때가 되면 매일 작업이 스스로 읽고 텔레그램으로 알립니다. 읽는 데 사람이 할 일은 없고, 어느 판정도 규칙이나 점수를 스스로 바꾸지 않습니다(바꾸려면 버튼). 예상 시점은 기록이 하루도 빠지지 않고 휴장일이 한 해 열흘쯤이라고 본 어림입니다."}
