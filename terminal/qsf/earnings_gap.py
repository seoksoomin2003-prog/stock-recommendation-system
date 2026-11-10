"""US stocks without a next earnings date: counted once on or after ``DUE`` and told to the user.  Read only.

Background: reports/DECISIONS_FOR_USER.md, "미국 다음 실적 발표일 빈칸".  On 2026-11-08, 265 of 503 US stocks had only past dates in
Yahoo's calendar, so their earnings-schedule factor was blank and the pre-earnings swing entry block could not trigger for them.
Filling the blanks would change about half of the US scores, which is the user's decision.  This module only counts what the QSF
ledger already holds and words the message.  It changes no score and no record.
"""
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

from terminal.qsf.ledger import Ledger

DUE = date(2026, 12, 15)                 # before the late-January earnings season, as promised in the decision list
BASELINE = {"day": "2026-11-08", "stocks": 503, "blank": 265}
FACTOR = "earnings_calendar"
STRATEGY = "SWING"                       # the strategy whose score carries the factor and whose entry block needs the date
COUNTED = ("REAL", "STALE")
MANY = 0.20                              # a reference line for the wording only; nothing is decided by it
NOTES = Path("reports") / "DECISIONS_FOR_USER.md"
ANCHOR = "**미국 다음 실적 발표일 빈칸:**"
MARK = "자동 재집계 (기준 거래일"


def has_date(snap: Dict[str, Any]) -> bool:
    return any(f.get("factor") == FACTOR and f.get("status") in COUNTED for f in snap.get("factors") or [])


def count(base: Path) -> Optional[Dict[str, Any]]:
    """The newest US ledger session.  None when the ledger holds no US session, so the caller asks again at a later run."""
    led = Ledger(Path(base))
    rows = [r for r in led._live_rows() if r["market"] == "US"]
    if not rows:
        return None
    session = max(r["session"] for r in rows)
    snaps = [s for r in rows if r["session"] == session for s in led._load(r) if s.get("strategy") == STRATEGY]
    if not snaps:
        return None
    blank = sum(1 for s in snaps if not has_date(s))
    return {"session": session, "stocks": len(snaps), "blank": blank, "share": round(blank / len(snaps), 4)}


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%"


def text(res: Dict[str, Any]) -> str:
    many = res["share"] >= MANY
    reading = ("아직 많이 비어 있습니다. 빈칸 종목은 실적 직전 스윙 진입 차단이 걸리지 않습니다. 1월 말 실적 시즌 전에 채울지 정해 주세요." if many
               else "대부분 채워졌습니다. 남은 종목만 실적 직전 스윙 진입 차단이 걸리지 않습니다.")
    return "\n".join([
        f"📅 미국 실적 발표일 빈칸 재집계 (기준 거래일 {res['session']})", "",
        f"{res['stocks']}종목 중 {res['blank']}종목({_pct(res['blank'], res['stocks'])})에 다음 실적 발표일이 없습니다.",
        f"{BASELINE['day']}에는 {BASELINE['stocks']}종목 중 {BASELINE['blank']}종목({_pct(BASELINE['blank'], BASELINE['stocks'])})이었습니다.",
        reading + f" (많고 적음의 기준 {MANY:.0%}는 참고용입니다.)", "",
        "세기만 했고 점수와 기록은 바꾸지 않았습니다. 빈칸을 채우면 미국 점수가 바뀌어 새 모델 버전이 됩니다. reports/DECISIONS_FOR_USER.md 의 해당 항목에서 정해 주세요."])


def short(res: Dict[str, Any]) -> str:
    return f"{res['stocks']}종목 중 {res['blank']}종목에 다음 실적 발표일이 없습니다 ({BASELINE['day']}: {BASELINE['blank']}종목)."


def write_note(base: Path, res: Dict[str, Any]) -> bool:
    """One line under the item in the decision list.  False when the item is not there; a line already written is left alone."""
    path = Path(base) / NOTES
    if not path.exists():
        return False
    lines = path.read_text(encoding="utf-8").split("\n")
    if any(MARK in x for x in lines):
        return True
    at = next((k for k, x in enumerate(lines) if ANCHOR in x), None)
    if at is None:
        return False
    lines.insert(at + 1, f"   - **{MARK} {res['session']}):** {res['stocks']}종목 중 {res['blank']}종목({_pct(res['blank'], res['stocks'])})에 다음 실적 발표일이 없습니다. "
                         f"{BASELINE['day']}에는 {BASELINE['stocks']}종목 중 {BASELINE['blank']}종목이었습니다. 세기만 했고 점수는 바꾸지 않았습니다.")
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(path)
    return True
