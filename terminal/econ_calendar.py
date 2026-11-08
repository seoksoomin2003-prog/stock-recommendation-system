"""Economic calendar: dates of scheduled US and Korean policy and data releases, copied from the official schedules.

Only dates the publishing institution has announced are listed; nothing is projected, and no forecast or consensus value is
shown.  Each series records the page it came from, the day it was checked and the last date it covers, so the screen can say
when the list has run out instead of looking empty.  When a source page publishes more dates, add them here with a new
``checked`` day.  Times are the institution's own (US releases at 08:30 New York time); a meeting with no stated time
shows the date only.
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")

SERIES = {
    "FOMC": {"name": "FOMC 금리 결정", "country": "US", "tz": "America/New_York", "time": None, "checked": "2026-11-08",
             "source": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
             "note": "회의 이틀째 날짜입니다. '경제전망 포함'은 연준이 경제전망 요약(SEP)을 함께 내는 회의입니다."},
    "CPI": {"name": "미국 소비자물가(CPI)", "country": "US", "tz": "America/New_York", "time": "08:30", "checked": "2026-11-08",
            "source": "https://www.bls.gov/schedule/news_release/cpi.htm"},
    "JOBS": {"name": "미국 고용보고서", "country": "US", "tz": "America/New_York", "time": "08:30", "checked": "2026-11-08",
             "source": "https://www.bls.gov/schedule/news_release/empsit.htm"},
    "BOK": {"name": "한국은행 금통위 기준금리 결정", "country": "KR", "tz": "Asia/Seoul", "time": None, "checked": "2026-11-08",
            "source": "https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do?mtgSe=A&menuNo=200755",
            "note": "한국은행은 2027년 일정을 아직 게시하지 않았습니다."},
}

# (series, date, what the release covers or a short label)
EVENTS = [
    *[("FOMC", d, label) for d, label in [
        ("2026-01-28", ""), ("2026-03-18", "경제전망 포함"), ("2026-04-29", ""), ("2026-06-17", "경제전망 포함"), ("2026-07-29", ""),
        ("2026-09-16", "경제전망 포함"), ("2026-10-28", ""), ("2026-12-09", "경제전망 포함"),
        ("2027-01-27", ""), ("2027-03-17", "경제전망 포함"), ("2027-04-28", ""), ("2027-06-09", "경제전망 포함"), ("2027-07-28", ""),
        ("2027-09-15", "경제전망 포함"), ("2027-10-27", ""), ("2027-12-08", "경제전망 포함")]],
    *[("CPI", d, ref) for d, ref in [
        ("2026-11-10", "2026년 10월분"), ("2026-12-10", "2026년 11월분"), ("2027-01-13", "2026년 12월분"), ("2027-02-11", "2027년 1월분"),
        ("2027-03-10", "2027년 2월분"), ("2027-04-13", "2027년 3월분"), ("2027-05-12", "2027년 4월분"), ("2027-06-10", "2027년 5월분"),
        ("2027-07-14", "2027년 6월분"), ("2027-08-11", "2027년 7월분"), ("2027-09-14", "2027년 8월분"), ("2027-10-14", "2027년 9월분"),
        ("2027-11-10", "2027년 10월분"), ("2027-12-10", "2027년 11월분")]],
    *[("JOBS", d, ref) for d, ref in [
        ("2026-11-06", "2026년 10월분"), ("2026-12-04", "2026년 11월분"), ("2027-01-08", "2026년 12월분"), ("2027-02-05", "2027년 1월분"),
        ("2027-03-05", "2027년 2월분"), ("2027-04-02", "2027년 3월분"), ("2027-05-07", "2027년 4월분"), ("2027-06-04", "2027년 5월분"),
        ("2027-07-02", "2027년 6월분"), ("2027-08-06", "2027년 7월분"), ("2027-09-03", "2027년 8월분"), ("2027-10-08", "2027년 9월분"),
        ("2027-11-05", "2027년 10월분"), ("2027-12-03", "2027년 11월분")]],
    *[("BOK", d, "") for d in ["2026-01-15", "2026-02-26", "2026-04-10", "2026-05-28", "2026-07-16", "2026-08-27", "2026-10-22", "2026-11-26"]],
]
STALE_DAYS = 120          # a list checked this long ago may have missed a changed date


def covers_until(series: str) -> str:
    return max(d for s, d, _ in EVENTS if s == series)


def _kst(series: str, day: str) -> Dict[str, Optional[str]]:
    s = SERIES[series]
    if not s["time"]:
        return {"date_kst": day, "time_kst": None, "time_local": None}
    hh, mm = map(int, s["time"].split(":"))
    local = datetime.fromisoformat(day).replace(hour=hh, minute=mm, tzinfo=ZoneInfo(s["tz"]))
    k = local.astimezone(KST)
    return {"date_kst": k.date().isoformat(), "time_kst": k.strftime("%H:%M"), "time_local": s["time"]}


def upcoming(today: date, days: int = 60) -> Dict[str, Any]:
    """Announced events from ``today`` (KST calendar) for ``days`` days, and per series how far the official list reaches."""
    end = date.fromordinal(today.toordinal() + days)
    items = []
    for series, day, label in EVENTS:
        k = _kst(series, day)
        dk = date.fromisoformat(k["date_kst"])
        if today <= dk <= end:
            s = SERIES[series]
            items.append({"series": series, "name": s["name"], "country": s["country"], "date": day, **k, "label": label,
                          "days_away": (dk - today).days, "time_zone": s["tz"]})
    items.sort(key=lambda i: (i["date_kst"], i["time_kst"] or "99"))
    series = []
    for key, s in SERIES.items():
        last = covers_until(key)
        checked = date.fromisoformat(s["checked"])
        series.append({"series": key, "name": s["name"], "country": s["country"], "source": s["source"], "checked": s["checked"],
                       "covers_until": last, "runs_out": date.fromisoformat(last) < end, "stale": (today - checked).days > STALE_DAYS,
                       "note": s.get("note")})
    return {"status": "REAL", "from": today.isoformat(), "to": end.isoformat(), "items": items, "series": series,
            "basis": "각 기관이 공식 발표한 일정만 담았습니다. 예상치·컨센서스는 없습니다. 미국 발표 시각은 뉴욕 08:30이며 한국 시각으로 바꿔 표시합니다."}
