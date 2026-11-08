"""Economic calendar: official dates only, converted to Korean time, and an honest note when a series runs out."""
from datetime import date

from terminal import econ_calendar as ec


def test_dates_are_sorted_unique_and_weekdays():
    for s in ec.SERIES:
        days = [d for k, d, _ in ec.EVENTS if k == s]
        assert days == sorted(days) and len(days) == len(set(days))
        assert all(date.fromisoformat(d).weekday() < 5 for d in days)


def test_us_release_time_follows_daylight_saving():
    out = ec.upcoming(date(2026, 11, 8), 60)
    cpi = next(i for i in out["items"] if i["series"] == "CPI")
    assert (cpi["date"], cpi["date_kst"], cpi["time_kst"]) == ("2026-11-10", "2026-11-10", "22:30")   # 08:30 EST
    summer = ec._kst("CPI", "2027-06-10")
    assert summer["time_kst"] == "21:30"                                                                # 08:30 EDT
    fomc = next(i for i in out["items"] if i["series"] == "FOMC")
    assert fomc["date"] == "2026-12-09" and fomc["time_kst"] is None                                   # no time is invented


def test_series_running_out_is_flagged_not_hidden():
    out = ec.upcoming(date(2026, 11, 8), 60)
    bok = next(s for s in out["series"] if s["series"] == "BOK")
    assert bok["covers_until"] == "2026-11-26" and bok["runs_out"]
    assert not next(s for s in out["series"] if s["series"] == "CPI")["runs_out"]
    late = ec.upcoming(date(2027, 6, 1), 30)
    assert all(s["stale"] for s in late["series"])                     # checked 2026-11-08: needs a fresh look
    assert [i["date"] for i in out["items"] if i["date"] < "2026-11-08"] == []
