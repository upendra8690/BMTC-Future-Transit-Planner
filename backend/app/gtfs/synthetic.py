"""Generator for a SYNTHETIC demo GTFS feed used by tests and local development.

Every agency, stop, route and timetable it produces is invented. Names carry "Demo" and the
agency is labelled SYNTHETIC, so none of it can be mistaken for real BMTC service. Import it
with kind SYNTHETIC_DEMO. It must never be marked as an official source.
"""

from __future__ import annotations

import datetime as dt
import io
import zipfile

AGENCY_NAME = "Demo Transit (SYNTHETIC)"

STOPS = [
    ("DS01", "Demo Central", 12.9750, 77.5950),
    ("DS02", "Demo Market", 12.9790, 77.6000),
    ("DS03", "Demo Park Gate", 12.9830, 77.6050),
    ("DS04", "Demo Tech Park", 12.9880, 77.6120),
    ("DS05", "Demo Lake View", 12.9930, 77.6180),
    ("DS06", "Demo Junction", 12.9980, 77.6240),
]

# route_id, short name, long name, stop ids in outbound order
ROUTES = [
    ("DR1", "DEMO-1", "Demo Central - Demo Junction", ["DS01", "DS02", "DS03", "DS04", "DS05", "DS06"]),
    ("DR2", "DEMO-2", "Demo Market - Demo Lake View", ["DS02", "DS03", "DS04", "DS05"]),
]

# service_id, weekday flags (Mon..Sun), first departure, last departure, headway in minutes
SERVICES = [
    ("DWKD", (1, 1, 1, 1, 1, 0, 0), 6 * 60, 22 * 60, 30),
    ("DWKE", (0, 0, 0, 0, 0, 1, 1), 7 * 60, 21 * 60, 60),
]
MINUTES_PER_SEGMENT = 4


def _hms(total_minutes: int) -> str:
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}:00"


def build_synthetic_feed(
    start: dt.date,
    end: dt.date,
    *,
    holiday: dt.date | None = None,
) -> bytes:
    """Return a complete GTFS ZIP for the given service window. A holiday removes weekday service."""
    stop_index = {stop_id: (name, lat, lon) for stop_id, name, lat, lon in STOPS}
    start_s, end_s = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")

    files: dict[str, str] = {}
    files["agency.txt"] = (
        "agency_id,agency_name,agency_url,agency_timezone\n"
        f"DEMO,{AGENCY_NAME},https://example.invalid/demo,Asia/Kolkata\n"
    )
    files["routes.txt"] = "route_id,agency_id,route_short_name,route_long_name,route_type\n" + "".join(
        f"{rid},DEMO,{short},{long_name},3\n" for rid, short, long_name, _ in ROUTES
    )
    files["stops.txt"] = "stop_id,stop_name,stop_lat,stop_lon,location_type\n" + "".join(
        f"{sid},{name},{lat},{lon},0\n" for sid, name, lat, lon in STOPS
    )
    files["calendar.txt"] = (
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
        + "".join(
            f"{service},{','.join(str(flag) for flag in flags)},{start_s},{end_s}\n"
            for service, flags, *_ in SERVICES
        )
    )
    exceptions = "service_id,date,exception_type\n"
    if holiday is not None:
        exceptions += f"DWKD,{holiday.strftime('%Y%m%d')},2\n"
    files["calendar_dates.txt"] = exceptions

    trips_lines = ["route_id,service_id,trip_id,trip_headsign,direction_id,shape_id\n"]
    stop_time_lines = ["trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"]
    shape_lines = ["shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"]

    for rid, _short, _long_name, stop_ids in ROUTES:
        for direction in (0, 1):
            ordered = stop_ids if direction == 0 else list(reversed(stop_ids))
            headsign = stop_index[ordered[-1]][0]
            shape_id = f"{rid}-D{direction}"
            for seq, sid in enumerate(ordered, start=1):
                _name, lat, lon = stop_index[sid]
                shape_lines.append(f"{shape_id},{lat},{lon},{seq}\n")
            for service, _flags, first, last, headway in SERVICES:
                for depart in range(first, last + 1, headway):
                    trip_id = f"{rid}-D{direction}-{service}-{depart:04d}"
                    trips_lines.append(f"{rid},{service},{trip_id},{headsign},{direction},{shape_id}\n")
                    for seq, sid in enumerate(ordered, start=1):
                        offset = (seq - 1) * MINUTES_PER_SEGMENT
                        clock = _hms(depart + offset)
                        stop_time_lines.append(f"{trip_id},{clock},{clock},{sid},{seq}\n")

    files["trips.txt"] = "".join(trips_lines)
    files["stop_times.txt"] = "".join(stop_time_lines)
    files["shapes.txt"] = "".join(shape_lines)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


# ---------------------------------------------------------------- synthetic Metro line
# A separate SYNTHETIC feed with one invented Metro line (GTFS route_type 1). Its stations sit within a short walk of
# the demo bus stops, so bus + Metro journeys can be planned and tested. Nothing here is a real BMRCL line or station.
METRO_AGENCY_NAME = "Demo Metro (SYNTHETIC)"
METRO_STOPS = [
    ("DM01", "Demo Metro Central", 12.9753, 77.5953),
    ("DM02", "Demo Metro Hub", 12.9820, 77.5850),
    ("DM03", "Demo Metro Tech Park", 12.9883, 77.6124),
    ("DM04", "Demo Metro East", 12.9950, 77.6400),
]
METRO_ROUTE = ("DMR1", "DEMO-M1", "Demo Metro Line (SYNTHETIC)", ["DM02", "DM01", "DM03", "DM04"])
METRO_ROUTE_COLOR = "7C3AED"
# Every day, 05:00 to 23:00, every 10 minutes, 3 minutes between stations.
METRO_SERVICE = ("DMALL", (1, 1, 1, 1, 1, 1, 1), 5 * 60, 23 * 60, 10)
METRO_MINUTES_PER_SEGMENT = 3


def build_synthetic_metro_feed(start: dt.date, end: dt.date) -> bytes:
    """Return a GTFS ZIP with one invented Metro line for the given service window. Import it as SYNTHETIC_DEMO."""
    stop_index = {stop_id: (name, lat, lon) for stop_id, name, lat, lon in METRO_STOPS}
    rid, short, long_name, stop_ids = METRO_ROUTE
    service, flags, first, last, headway = METRO_SERVICE
    files: dict[str, str] = {
        "agency.txt": (
            "agency_id,agency_name,agency_url,agency_timezone\n"
            f"DEMOM,{METRO_AGENCY_NAME},https://example.invalid/demo-metro,Asia/Kolkata\n"
        ),
        "routes.txt": (
            "route_id,agency_id,route_short_name,route_long_name,route_type,route_color\n"
            f"{rid},DEMOM,{short},{long_name},1,{METRO_ROUTE_COLOR}\n"
        ),
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon,location_type\n" + "".join(
            f"{sid},{name},{lat},{lon},0\n" for sid, name, lat, lon in METRO_STOPS
        ),
        "calendar.txt": (
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
            f"{service},{','.join(str(f) for f in flags)},{start.strftime('%Y%m%d')},{end.strftime('%Y%m%d')}\n"
        ),
    }
    trips = ["route_id,service_id,trip_id,trip_headsign,direction_id,shape_id\n"]
    times = ["trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"]
    shapes = ["shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"]
    for direction in (0, 1):
        ordered = stop_ids if direction == 0 else list(reversed(stop_ids))
        shape_id = f"{rid}-D{direction}"
        for seq, sid in enumerate(ordered, start=1):
            _name, lat, lon = stop_index[sid]
            shapes.append(f"{shape_id},{lat},{lon},{seq}\n")
        for depart in range(first, last + 1, headway):
            trip_id = f"{rid}-D{direction}-{depart:04d}"
            trips.append(f"{rid},{service},{trip_id},{stop_index[ordered[-1]][0]},{direction},{shape_id}\n")
            for seq, sid in enumerate(ordered, start=1):
                at = _hms(depart + (seq - 1) * METRO_MINUTES_PER_SEGMENT)
                times.append(f"{trip_id},{at},{at},{sid},{seq}\n")
    files["trips.txt"] = "".join(trips)
    files["stop_times.txt"] = "".join(times)
    files["shapes.txt"] = "".join(shapes)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()
