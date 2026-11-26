"""How far the forward records have come, and whether they are still growing.  Read-only: computes no return and changes no record.

Progress counts sessions of the current QSF version only, since an earlier version read different inputs.  A horizon is ready for
interpretation at the same independence minimum the ledger's own report uses: matured sessions / horizon >= config.MIN_INDEPENDENT.
"""
from datetime import date
from typing import Any, Dict, List, Optional

from terminal import automation, storage
from terminal.qsf import config, kr_events_forward, kr_forward, us_challenger
from utils import nyse_calendar

TRADING_DAYS_PER_YEAR = 252
BASELINE_TARGET = 30
BEHIND_ALERT = 2      # the record of a finished session is written at the next morning's run, so one session behind is normal
PRIMARY = {"SWING": 20, "LONG_TERM": 252}
STEP_LABELS = {"LAB": "도전자 기록", "SCAN": "기준 모델 스캔", "TRACK": "기준 모델 추적", "QSF": "QSF 기록(미국)", "QSF_KR": "QSF 기록(한국)", "NEWS": "뉴스 기록(미국)", "NEWS_KR": "뉴스 기록(한국)", "KR_FORWARD": "한국 결합 점수 기록", "US_CHALLENGER": "미국 도전자 점수 기록", "BACKUP": "백업"}


def horizons() -> Dict[str, List[int]]:
    return {"SWING": list(config.SWING_HORIZONS), "LONG_TERM": [m * 21 for m in config.LONG_HORIZONS_MONTHS]}


def matured_count(recorded: List[str], calendar: List[str], h: int) -> int:
    """A session matures once h sessions followed it: entry at the next open, exit at the h-th close."""
    return sum(1 for s in recorded if sum(1 for d in calendar if d > s) >= h)


def remaining_sessions(recorded: int, matured: int, h: int, minimum: int = config.MIN_INDEPENDENT) -> int:
    """Sessions until the requirement is met if a record is written every session from now on."""
    need = minimum * h
    return max(0, need - recorded) + h if recorded < need else max(0, need - matured)


def missing_sessions(recorded: List[str], calendar: List[str]) -> List[str]:
    """Calendar sessions without a record, counted from the first record.  Before the first record nothing is owed."""
    if not recorded:
        return []
    have, first = set(recorded), min(recorded)
    return [d for d in calendar if d >= first and d not in have]


def progress_rows(recorded: List[str], calendar: List[str]) -> List[Dict[str, Any]]:
    out = []
    for strategy, hs in horizons().items():
        for h in hs:
            done = matured_count(recorded, calendar, h)
            left = remaining_sessions(len(recorded), done, h)
            out.append({"strategy": strategy, "horizon": h, "primary": PRIMARY[strategy] == h, "needed_sessions": config.MIN_INDEPENDENT * h, "matured_sessions": done,
                        "independent": done / h, "target": config.MIN_INDEPENDENT, "ready": done / h >= config.MIN_INDEPENDENT, "remaining_sessions": left,
                        "remaining_years": left / TRADING_DAYS_PER_YEAR})
    return out


def market_record(rows: List[Dict[str, Any]], calendar: Optional[List[str]], current: str = config.MODEL_VERSION) -> Dict[str, Any]:
    """``rows``: live ledger index rows of one market.  ``calendar`` None means the sessions could not be established."""
    sessions = sorted({r["session"] for r in rows})
    now_version = sorted({r["session"] for r in rows if r.get("model_version") == current})
    behind = None
    if calendar is not None:
        behind = sum(1 for d in calendar if d > sessions[-1]) if sessions else None
    return {"sessions": len(sessions), "current_version_sessions": len(now_version), "first": sessions[0] if sessions else None, "last": sessions[-1] if sessions else None,
            "records": sum(int(r.get("records") or 0) for r in rows), "calendar_status": "REAL" if calendar is not None else "UNAVAILABLE", "behind_sessions": behind,
            "missing": missing_sessions(sessions, calendar) if calendar is not None else None, "progress": progress_rows(now_version, calendar or [])}


def baseline_record(capital_configured: bool, status: Optional[Dict[str, Any]], error: Optional[str] = None) -> Dict[str, Any]:
    if status is None:
        return {"status": "UNAVAILABLE", "error": error, "capital_configured": capital_configured, "target": BASELINE_TARGET}
    valid = sorted({r[:8] for r, c in (status.get("run_cohorts") or {}).items() if c == "VALID_PROSPECTIVE"})
    states = status.get("outcome_states") or {}
    done = sum(v for k, v in states.items() if k.startswith("VALID_PROSPECTIVE/COMPLETED"))
    pending = sum(v for k, v in states.items() if k.startswith("VALID_PROSPECTIVE/PENDING"))
    incomplete = sum(v for k, v in states.items() if k.startswith("VALID_PROSPECTIVE/INCOMPLETE"))
    update = status.get("latest_update") or {}
    return {"status": "REAL", "capital_configured": capital_configured, "target": BASELINE_TARGET, "completed": done, "pending": pending, "incomplete": incomplete,
            "valid_observations": (status.get("by_class_and_cohort") or {}).get("PORTFOLIO_TOP5/VALID_PROSPECTIVE", 0), "scan_dates": len(valid),
            "last_scan_date": f"{valid[-1][:4]}-{valid[-1][4:6]}-{valid[-1][6:]}" if valid else None, "latest_update_session": update.get("as_of_session")}


def alerts(qsf: Dict[str, Dict[str, Any]], baseline: Dict[str, Any], auto: Dict[str, Any], integrity: str, forward: Optional[Dict[str, Any]] = None, challenger: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    names = {"US": "미국", "KR": "한국"}
    out = []
    if integrity != "OK":
        out.append({"level": "bad", "text": "QSF 기록 파일 검증에 실패했습니다. 기록을 믿기 전에 원인을 확인해야 합니다."})
    if not auto.get("installed"):
        out.append({"level": "bad", "text": "매일 자동 실행이 설치되어 있지 않습니다."})
    if not baseline.get("capital_configured"):
        out.append({"level": "bad", "text": "자본금이 비어 있어 기준 모델의 매일 스캔을 건너뜁니다. 모델 탭에서 입력하세요."})
    if baseline.get("status") != "REAL":
        out.append({"level": "warn", "text": "기준 모델 추적 기록을 읽지 못했습니다."})
    if forward is not None:
        check = forward.get("price_check") or {}
        if check.get("gaps") or check.get("stale"):
            out.append({"level": "bad", "text": f"한국 시세 대조({check.get('session')}): KRX 종가와 다른 종목 {check.get('gaps')}개, 날짜가 늦은 종목 {check.get('stale')}개. 해당 종목의 라이브 점수를 믿기 전에 확인하세요."})
        if forward.get("integrity") != "OK":
            out.append({"level": "bad", "text": "한국 결합 점수 기록 검증에 실패했습니다. 원인을 확인해야 합니다."})
        elif not forward.get("sessions"):
            out.append({"level": "warn", "text": "한국 결합 점수 기록이 아직 없습니다."})
        elif (forward.get("behind_sessions") or 0) >= BEHIND_ALERT:
            out.append({"level": "warn", "text": f"한국 결합 점수 기록이 {forward['behind_sessions']}거래일 뒤처져 있습니다. KRX 키와 자동 실행을 확인하세요."})
        fund = forward.get("fund") or {}
        if fund.get("integrity") not in (None, "OK"):
            out.append({"level": "bad", "text": "한국 재무 점수 기록 검증에 실패했습니다. 원인을 확인해야 합니다."})
        elif (fund.get("behind_sessions") or 0) >= BEHIND_ALERT:
            out.append({"level": "warn", "text": f"한국 재무 점수 기록이 {fund['behind_sessions']}거래일 뒤처져 있습니다. DART 키와 자동 실행을 확인하세요."})
        events = forward.get("events") or {}
        if events.get("integrity") not in (None, "OK"):
            out.append({"level": "bad", "text": "한국 공시 사건 기록 검증에 실패했습니다. 원인을 확인해야 합니다."})
        elif (events.get("behind_sessions") or 0) >= BEHIND_ALERT:
            out.append({"level": "warn", "text": f"한국 공시 사건 기록이 {events['behind_sessions']}거래일 뒤처져 있습니다. DART 키와 자동 실행을 확인하세요."})
    if challenger is not None:
        if challenger.get("integrity") != "OK":
            out.append({"level": "bad", "text": "미국 도전자 점수 기록 검증에 실패했습니다. 원인을 확인해야 합니다."})
        elif (challenger.get("behind_sessions") or 0) >= BEHIND_ALERT:
            out.append({"level": "warn", "text": f"미국 도전자 점수 기록이 {challenger['behind_sessions']}거래일 뒤처져 있습니다. 자동 실행을 확인하세요."})
        elif not challenger.get("sessions") and (challenger.get("due_sessions") or 0) >= BEHIND_ALERT:
            out.append({"level": "warn", "text": "미국 도전자 점수 기록이 시작되지 않았습니다. 자동 실행을 확인하세요."})
    tg = (auto.get("last_run") or {}).get("telegram") or {}
    if tg.get("status") == "FAILED":            # "connected" on the screen only means the two values look right; this is the last real send
        out.append({"level": "bad", "text": f"텔레그램 전달 실패({tg.get('error')}). 하루 요약과 판정 알림이 오지 않고 있습니다. .env의 텔레그램 값 두 개와 봇 차단 여부를 확인하세요."})
    out += [{"level": "warn", "text": n} for n in auto.get("notes") or []]
    failed = [STEP_LABELS.get(k, k) for k, v in (auto.get("steps") or {}).items() if isinstance(v, dict) and v.get("status") == automation.FAILED]
    if failed:
        out.append({"level": "bad", "text": f"최근 자동 실행에서 실패한 작업: {', '.join(failed)}"})
    for m, r in qsf.items():
        if r["calendar_status"] != "REAL":
            out.append({"level": "warn", "text": f"{names[m]} 거래일 달력을 받지 못해 빠진 날을 확인할 수 없습니다."})
            continue
        if not r["sessions"]:
            out.append({"level": "warn", "text": f"{names[m]} QSF 기록이 아직 없습니다."})
            continue
        if (r["behind_sessions"] or 0) >= BEHIND_ALERT:
            out.append({"level": "warn", "text": f"{names[m]} QSF 기록이 마지막 완료 거래일보다 {r['behind_sessions']}거래일 뒤처져 있습니다. 다음 자동 실행 때 맥이 켜져 있어야 합니다."})
        gaps = [d for d in r["missing"] if d <= r["last"]]
        if gaps:
            out.append({"level": "warn", "text": f"{names[m]} QSF 기록이 빠진 거래일 {len(gaps)}개: {', '.join(gaps[-5:])}"})
    return out


def _kr_calendar(qsf_service: Any) -> Optional[List[str]]:
    """KRX has no local calendar here, so the KOSPI's own bars stand in.  No bars means unknown, never 'nothing missing'."""
    try:
        rows = (qsf_service._history(["^KS11"]).get("data") or {}).get("^KS11") or []
    except Exception:
        return None
    last = qsf_service._session("KR", rows)
    days = [r["date"] for r in rows if r["date"] <= last]
    return days or None


def backup_alerts(saved: Dict[str, Any], second: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    return _first_backup_alerts(saved) + second_backup_alerts(second)


def second_backup_alerts(second: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    """The first backup sits on the disk that holds the records (assessment 2026-11-26).  Without a second place, or with one
    that fell behind, the page says so."""
    if second is None:
        return []
    if not second.get("on"):
        return [{"level": "warn", "text": "백업이 기록과 같은 디스크에만 있습니다. 디스크가 고장 나면 기록과 백업을 함께 잃습니다. 두 번째 백업 위치를 켜 두세요(RUNBOOK '두 번째 백업')."}] if second.get("first_on_records_disk") else []
    if not second.get("latest"):
        return [{"level": "warn", "text": f"두 번째 백업({second.get('path')})이 아직 없습니다. 다음 매일 작업이 만듭니다. 그 뒤에도 없으면 그 폴더에 쓸 수 없는 것입니다."}]
    if second["age_days"] > automation.BACKUP_STALE_DAYS:
        return [{"level": "warn", "text": f"두 번째 백업({second.get('path')})이 {second['age_days']}일 전 것입니다. 매일 작업의 '백업' 단계 설명에 실패 이유가 적힙니다."}]
    return []


def _first_backup_alerts(saved: Dict[str, Any]) -> List[Dict[str, str]]:
    if not saved.get("latest"):
        return [{"level": "warn", "text": "백업이 아직 없습니다."}]
    if saved["age_days"] > automation.BACKUP_STALE_DAYS:
        return [{"level": "warn", "text": f"마지막 백업이 {saved['age_days']}일 전입니다. 자동 실행을 확인하세요."}]
    return []


def audit_alerts(audits: Dict[str, Dict[str, Any]]) -> List[Dict[str, str]]:
    names = {"US": "미국", "KR": "한국"}
    fixed = {"KR": " 한국 일봉은 KRX 공식 자료로 다시 만들며(QSF-1.1.8), 남은 것은 KRX가 아직 내지 않은 최근 날이나 KRX에 없는 종목입니다."}
    out = []
    for m, a in audits.items():
        if a.get("status") == "REAL" and a.get("flagged"):
            kinds = ", ".join(f"{a['kind_text'][k]} {n}건" for k, n in a["by_kind"].items())
            out.append({"level": "bad" if a.get("bad") else "warn",
                        "text": f"{names[m]} 시세 이력 점검({a['session']}): {a['checked']}종목 중 {a['flagged']}종목에서 문제가 있습니다({kinds}). 점수는 이 시세로 계산됐고 이 문제들은 고치지 않았습니다.{fixed.get(m, '')} 종목 화면에 날짜가 표시됩니다."})
    return out


def build(terminal: Any) -> Dict[str, Any]:
    qsf_service = terminal.qsf
    live = qsf_service.ledger._live_rows()
    verify = qsf_service.ledger.verify()
    now = nyse_calendar.latest_completed_session(qsf_service.now())
    first_us = min((r["session"] for r in live if r["market"] == "US"), default=now.isoformat())
    us_calendar = [d.isoformat() for d in nyse_calendar.sessions_between(date.fromisoformat(first_us), now)]
    calendars = {"US": us_calendar, "KR": _kr_calendar(qsf_service)}
    qsf = {m: market_record([r for r in live if r["market"] == m], calendars[m]) for m in config.MARKETS}
    auto = automation.status(terminal.base)
    try:
        from pipeline import prospective_tracking as pt
        baseline = baseline_record(bool(auto.get("capital_configured")), pt.status(str(terminal.base / "tracking")))
    except Exception as exc:
        baseline = baseline_record(bool(auto.get("capital_configured")), None, type(exc).__name__)
    forward = kr_forward.status(terminal.base, calendars["KR"])
    forward["fund"] = kr_forward.status(terminal.base, calendars["KR"], kr_forward.FUND_FOLDER)
    forward["events"] = kr_events_forward.status(terminal.base, calendars["KR"])
    challenger = us_challenger.status(terminal.base, us_calendar)
    room = storage.disk(terminal.base)
    saved = automation.backup_status()
    second = automation.second_backup_status(terminal.base)
    from terminal.qsf import price_audit
    audits = price_audit.summary_view(terminal.base)
    challenger["due_sessions"] = sum(1 for d in us_calendar if d >= us_challenger.FIRST)
    last = auto.get("last_run") or {}
    steps = [{"name": STEP_LABELS.get(k, k), "status": (auto.get("steps") or {}).get(k, {}).get("status")} for k in STEP_LABELS]
    return {"status": "REAL", "model_version": config.MODEL_VERSION, "integrity": verify.get("status"), "qsf": qsf, "baseline": baseline, "kr_forward": forward, "us_challenger": challenger,
            "automation": {"installed": auto.get("installed"), "schedule_kst": auto.get("schedule_kst"), "schedule_text": auto.get("schedule_text"), "last_run_at": last.get("at"), "latest_session": auto.get("latest_session"), "steps": steps},
            "disk": room, "backup": saved, "backup_second": second, "alerts": ([{"level": room["level"], "text": storage.low_disk_text(terminal.base)}] if room["level"] != "ok" else []) + backup_alerts(saved, second) + audit_alerts(audits) + alerts(qsf, baseline, auto, verify.get("status"), forward, challenger), "price_audit": audits, "minimum_independent": config.MIN_INDEPENDENT,
            "note": "진행 상황만 보여 줍니다. 수익률을 계산하지 않으며, 기준을 채우기 전에는 점수의 성과를 판단할 수 없습니다."}
