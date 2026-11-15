"""Clock rules for "now": service days, times past midnight, daylight saving, and invalid time zone names.

Every instant here is fixed, so the results never depend on when or where the tests run.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app import clock
from hypothesis import given, settings
from hypothesis import strategies as st

IST = clock.zone("Asia/Kolkata")
NEW_YORK = clock.zone("America/New_York")


def utc(*args: int) -> dt.datetime:
    return dt.datetime(*args, tzinfo=dt.UTC)


def test_zone_names_are_checked_not_guessed():
    assert clock.zone_or_none("Asia/Kolkata") is not None
    # Older names still resolve because the tzdata package carries the backward-compatible links.
    assert clock.zone_or_none("Asia/Calcutta") is not None
    assert clock.zone_or_none("Mars/Olympus") is None
    assert clock.zone_or_none("") is None
    assert clock.zone_or_none(" Asia/Kolkata") is None  # surrounding spaces are not part of a zone name
    assert clock.zone_or_none("../../etc/passwd") is None
    assert clock.zone_or_none("x" * 200) is None
    with pytest.raises(ValueError, match="not a known IANA time zone"):
        clock.zone("Nowhere/Land")


def test_naive_datetimes_are_refused():
    with pytest.raises(ValueError, match="naive"):
        clock.as_utc(dt.datetime(2027, 1, 11, 8, 0))


def test_service_day_starts_at_local_midnight_in_india():
    start = clock.service_day_start(IST, dt.date(2027, 1, 11))
    assert start == utc(2027, 1, 10, 18, 30)  # 00:00 IST on 11 January
    assert clock.local_time(IST, start).isoformat() == "2027-01-11T00:00:00+05:30"


def test_time_past_midnight_belongs_to_the_service_date_it_started_on():
    service_day = dt.date(2027, 1, 11)
    late_trip = clock.departure_instant(IST, service_day, 25 * 3600 + 10 * 60)  # written as 25:10:00
    assert clock.local_time(IST, late_trip).isoformat() == "2027-01-12T01:10:00+05:30"
    assert clock.service_date(IST, late_trip) == dt.date(2027, 1, 12)
    assert clock.is_next_day(IST, service_day, late_trip) is True
    ordinary = clock.departure_instant(IST, service_day, 8 * 3600)
    assert clock.is_next_day(IST, service_day, ordinary) is False


def test_candidate_service_dates_cover_trips_still_running_after_midnight_and_the_days_ahead():
    now = utc(2027, 1, 11, 19, 0)  # 00:30 IST on 12 January
    days = clock.candidate_service_dates(IST, now)
    assert days[0] == dt.date(2027, 1, 10)  # two days back, for trips that started before midnight
    assert days[-1] == dt.date(2027, 1, 19)  # seven days ahead of 12 January
    assert days == sorted(days)
    assert len(days) == clock.SERVICE_DAYS_LOOKBACK + clock.SERVICE_DAYS_AHEAD + 1


def test_seconds_into_service_day_tracks_the_local_clock():
    now = utc(2027, 1, 11, 19, 0)  # 00:30 IST on 12 January
    assert clock.seconds_into_service_day(IST, dt.date(2027, 1, 12), now) == 30 * 60
    # The same instant is 24h30m into the service day that began on 11 January.
    assert clock.seconds_into_service_day(IST, dt.date(2027, 1, 11), now) == 24 * 3600 + 30 * 60


def test_gtfs_day_follows_noon_minus_twelve_hours_across_a_daylight_saving_change():
    # New York moved its clocks forward on 14 March 2027. Noon minus 12 hours is taken in absolute time, so the
    # service day begins at 23:00 on the 13th, not at midnight, exactly as the GTFS definition describes.
    start = clock.service_day_start(NEW_YORK, dt.date(2027, 3, 14))
    assert start == utc(2027, 3, 14, 4, 0)
    assert clock.local_time(NEW_YORK, start).isoformat() == "2027-03-13T23:00:00-05:00"


def test_whole_minutes_round_down_and_go_negative_for_earlier_times():
    now = utc(2027, 1, 11, 2, 40)
    assert clock.whole_minutes_between(now, utc(2027, 1, 11, 3, 0)) == 20
    assert clock.whole_minutes_between(now, utc(2027, 1, 11, 2, 40, 59)) == 0
    assert clock.whole_minutes_between(now, utc(2027, 1, 11, 2, 39)) == -1


@settings(max_examples=300, deadline=None)
@given(
    day=st.dates(min_value=dt.date(2000, 1, 1), max_value=dt.date(2100, 12, 31)),
    gtfs_seconds=st.integers(min_value=0, max_value=5 * 86400),
)
def test_departure_wall_clock_is_the_gtfs_time_for_india(day: dt.date, gtfs_seconds: int):
    """India has no daylight saving, so the wall clock must equal the GTFS arithmetic exactly."""
    local = clock.local_time(IST, clock.departure_instant(IST, day, gtfs_seconds))
    expected_date = day + dt.timedelta(days=gtfs_seconds // 86400)
    assert local.date() == expected_date
    assert local.hour * 3600 + local.minute * 60 + local.second == gtfs_seconds % 86400


@settings(max_examples=300, deadline=None)
@given(
    instant=st.datetimes(min_value=dt.datetime(2000, 1, 1), max_value=dt.datetime(2100, 1, 1)),
)
def test_service_date_is_the_local_calendar_date_everywhere(instant: dt.datetime):
    """For any instant, the service date is the calendar date on the wall clock of the service's zone."""
    aware = instant.replace(tzinfo=dt.UTC)
    for zone in (IST, NEW_YORK):
        assert clock.service_date(zone, aware) == clock.local_time(zone, aware).date()


@settings(max_examples=200, deadline=None)
@given(
    day=st.dates(min_value=dt.date(2001, 1, 1), max_value=dt.date(2099, 12, 31)),
    seconds=st.integers(min_value=0, max_value=4 * 86400),
)
def test_departures_are_strictly_ordered_in_absolute_time(day: dt.date, seconds: int):
    """A later GTFS time is always a later instant, even across a daylight-saving change."""
    earlier = clock.departure_instant(NEW_YORK, day, seconds)
    later = clock.departure_instant(NEW_YORK, day, seconds + 1)
    assert (later - earlier) == dt.timedelta(seconds=1)
