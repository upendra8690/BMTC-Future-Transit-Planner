"""The clock behind "now": local time in the feed's time zone, GTFS service days and absolute departure times.

GTFS writes a departure as seconds after "noon minus 12 hours" on its service date, in the agency's time zone.
A time of 25:10:00 is therefore 01:10 on the calendar day after its service date, and it belongs to the service
date it started on. The functions here take the instant as an argument and never read the machine's own clock or
time zone, so the same instant gives the same answer on every computer, and every rule can be tested at a fixed time.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from zoneinfo import ZoneInfo

DEFAULT_SERVICE_TIMEZONE = "Asia/Kolkata"
# A trip that starts on an earlier service date can still be running now, so the previous days are checked too.
# Two days covers departures written up to 72 hours after the service date began.
SERVICE_DAYS_LOOKBACK = 2
# When nothing is left today, the next departure is on a later service day. A week covers any weekday pattern.
SERVICE_DAYS_AHEAD = 7
MAX_ZONE_NAME_LENGTH = 100


@lru_cache(maxsize=64)
def _zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def zone_or_none(name: str | None) -> ZoneInfo | None:
    """The time zone for an IANA name such as Asia/Kolkata, or None when the name is not a known zone."""
    if not name or len(name) > MAX_ZONE_NAME_LENGTH or name != name.strip():
        return None
    try:
        return _zone(name)
    except (ValueError, OSError, KeyError):  # ZoneInfoNotFoundError is a KeyError
        return None


def zone(name: str) -> ZoneInfo:
    found = zone_or_none(name)
    if found is None:
        raise ValueError(f"'{name}' is not a known IANA time zone name, such as {DEFAULT_SERVICE_TIMEZONE}.")
    return found


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def as_utc(instant: dt.datetime) -> dt.datetime:
    """An aware UTC datetime. Naive values are refused, so a local clock reading can never pass for UTC."""
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("a naive datetime has no time zone; pass an aware datetime")
    return instant.astimezone(dt.UTC)


def local_time(tz: ZoneInfo, instant: dt.datetime) -> dt.datetime:
    return as_utc(instant).astimezone(tz)


def service_date(tz: ZoneInfo, instant: dt.datetime) -> dt.date:
    """The calendar date in the service's own time zone, which is what the timetable means by 'today'."""
    return local_time(tz, instant).date()


def service_day_start(tz: ZoneInfo, day: dt.date) -> dt.datetime:
    """Noon minus 12 hours on the service date, as an absolute UTC instant (the GTFS definition)."""
    noon = dt.datetime(day.year, day.month, day.day, 12, 0, 0, tzinfo=tz)
    return noon.astimezone(dt.UTC) - dt.timedelta(hours=12)


def departure_instant(tz: ZoneInfo, day: dt.date, gtfs_seconds: int) -> dt.datetime:
    return service_day_start(tz, day) + dt.timedelta(seconds=gtfs_seconds)


def seconds_into_service_day(tz: ZoneInfo, day: dt.date, instant: dt.datetime) -> float:
    return (as_utc(instant) - service_day_start(tz, day)).total_seconds()


def candidate_service_dates(tz: ZoneInfo, instant: dt.datetime) -> list[dt.date]:
    """Service dates to search for departures after this instant, in date order.

    The lookback days (trips that started before midnight), today, and the days ahead, so that the next departure
    is still found after the last one today.
    """
    today = service_date(tz, instant)
    return [
        today + dt.timedelta(days=offset)
        for offset in range(-SERVICE_DAYS_LOOKBACK, SERVICE_DAYS_AHEAD + 1)
    ]


def whole_minutes_between(start: dt.datetime, end: dt.datetime) -> int:
    """Whole minutes from start to end, rounded down. Negative when end is earlier."""
    return int((as_utc(end) - as_utc(start)).total_seconds() // 60)


def is_next_day(tz: ZoneInfo, day: dt.date, instant: dt.datetime) -> bool:
    """True when the departure falls on the calendar day after its service date (a time past midnight)."""
    return service_date(tz, instant) != day
