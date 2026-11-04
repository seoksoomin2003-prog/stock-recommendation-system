"""Dependency-free NYSE session calendar for the live freshness gate.

Daily bars are considered complete at 17:00 America/New_York. Early closes
still produce a completed daily bar, so they intentionally use that boundary.
"""
import pandas as pd
from pandas.tseries.holiday import (GoodFriday, Holiday, MO, USLaborDay,
                                    USMartinLutherKingJr, USMemorialDay,
                                    USThanksgivingDay, nearest_workday)
from datetime import datetime, timezone, time


def _nyse_holidays(start, end):
    """Regular NYSE holidays, including Good Friday (not a federal holiday)."""
    rules = [
        Holiday("NewYearsDay", month=1, day=1, observance=nearest_workday),
        USMartinLutherKingJr,
        Holiday("PresidentsDay", month=2, day=1, offset=pd.DateOffset(weekday=MO(3))),
        GoodFriday,
        USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, observance=nearest_workday, start_date="2022-01-01"),
        Holiday("IndependenceDay", month=7, day=4, observance=nearest_workday),
        USLaborDay,
        USThanksgivingDay,
        Holiday("Christmas", month=12, day=25, observance=nearest_workday),
    ]
    dates = []
    for rule in rules:
        dates.extend(rule.dates(start, end))
    return pd.DatetimeIndex(dates).normalize().unique()


def _is_nyse_session(day: pd.Timestamp) -> bool:
    day = pd.Timestamp(day).normalize().tz_localize(None)
    return day.day_of_week < 5 and day not in _nyse_holidays(day - pd.Timedelta(days=7), day + pd.Timedelta(days=7))

def expected_latest_trading_session(current_utc: datetime = None) -> pd.Timestamp:
    """
    Returns the latest expected completed U.S. trading session as a timezone-aware Timestamp (Eastern Time).
    Accounts for weekends and U.S. equity-market holidays.
    """
    if current_utc is None:
        current_utc = datetime.now(timezone.utc)
        
    # Convert to Eastern Time (US/Eastern)
    timestamp = pd.Timestamp(current_utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize('UTC')
    current_et = timestamp.tz_convert('America/New_York')
                            
    # Market closes at 4:00 PM ET. We give a 1-hour buffer for end-of-day daily bar generation.
    # If it is before 5:00 PM ET, the "latest completely closed session" is the previous trading day.
    if current_et.time() < time(17, 0):
        target_date = current_et.normalize() - pd.Timedelta(days=1)
    else:
        target_date = current_et.normalize()
        
    # Walk backward to find the nearest valid trading day (skip weekends and holidays)
    while True:
        if not _is_nyse_session(target_date):
            target_date -= pd.Timedelta(days=1)
            continue
        break
        
    return target_date

def get_trading_session_lag(bar_timestamp: pd.Timestamp, current_utc: datetime = None) -> int:
    """
    Calculates the lag in trading sessions between the provided bar timestamp and the expected latest session.
    """
    expected = expected_latest_trading_session(current_utc).normalize().tz_convert(None)
    
    # Handle both tz-aware and naive timestamps safely
    if bar_timestamp.tz is not None:
        bar_date = bar_timestamp.tz_convert('America/New_York').normalize().tz_convert(None)
    else:
        bar_date = bar_timestamp.normalize()
    
    if bar_date >= expected:
        return 0
        
    # Count valid trading days between bar_date (exclusive) and expected (inclusive)
    b_days = pd.date_range(start=bar_date + pd.Timedelta(days=1), end=expected, freq='D')
    trading_days = [d for d in b_days if _is_nyse_session(d)]
    
    return len(trading_days)
