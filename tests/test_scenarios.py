"""Scenario rules: validation, transparent estimates, comparison and export safety."""

from __future__ import annotations

import csv
import io

import pytest
from app.models import CLASS_SCENARIO
from app.schemas import ScenarioIn
from app.services import scenarios as scn
from app.services import schedule as sched
from app.services.exports import comparison_pdf, scenario_pdf, scenarios_csv
from app.services.schedule import haversine_km
from pydantic import ValidationError

OWNER = "owner-a"
BASE = {
    "name": "Proposed trial",
    "year": 2028,
    "route_code": "PROP-001",
    "origin_name": "Origin Stop",
    "destination_name": "Destination Stop",
    "first_departure": "06:00",
    "last_departure": "22:00",
    "frequency_minutes": 15,
    "operating_days": ["MON", "TUE", "WED", "THU", "FRI"],
    "stops": [],
}


def estimate(payload: dict) -> dict:
    return scn.estimate_scenario(payload, avg_speed_kmph=15.0, dwell_minutes=0.5, detour_factor=1.3)


def make_payload(database, **overrides) -> dict:
    """Store a scenario through the real service and return its payload, exactly as the API shows it."""
    with database.session() as session:
        scenario = scn.create_scenario(session, ScenarioIn(**{**BASE, **overrides}), OWNER)
        session.commit()
        return scn.scenario_payload(scenario)


# ---------------------------------------------------------------- validation

def test_a_valid_scenario_passes_validation():
    ScenarioIn(**BASE)


@pytest.mark.parametrize("year", [2026, 2031, 2100])
def test_years_outside_the_planning_window_are_rejected(year):
    with pytest.raises(ValidationError):
        ScenarioIn(**{**BASE, "year": year})


@pytest.mark.parametrize("frequency", [0, 241])
def test_frequency_bounds_are_enforced(frequency):
    with pytest.raises(ValidationError):
        ScenarioIn(**{**BASE, "frequency_minutes": frequency})


def test_last_departure_cannot_precede_the_first():
    with pytest.raises(ValidationError):
        ScenarioIn(**{**BASE, "first_departure": "22:00", "last_departure": "06:00"})


def test_a_latitude_needs_a_longitude():
    with pytest.raises(ValidationError):
        ScenarioIn(**{**BASE, "origin_lat": 12.97})


def test_a_stop_needs_both_coordinates_or_neither():
    with pytest.raises(ValidationError):
        ScenarioIn(**{**BASE, "stops": [{"name": "Half given", "lat": 12.97}]})


def test_unknown_operating_days_are_rejected():
    with pytest.raises(ValidationError):
        ScenarioIn(**{**BASE, "operating_days": ["FUNDAY"]})


def test_operating_days_are_normalised_and_deduplicated():
    assert ScenarioIn(**{**BASE, "operating_days": ["mon", "MON", "sat"]}).operating_days == ["MON", "SAT"]


@pytest.mark.parametrize("code", ["=HACK", "-1", " spaced"])
def test_route_codes_cannot_start_with_symbols_or_spaces(code):
    with pytest.raises(ValidationError):
        ScenarioIn(**{**BASE, "route_code": code})


# ---------------------------------------------------------------- estimates

def test_departures_follow_the_service_window_and_frequency(database):
    result = estimate(make_payload(database))
    assert result["classification"] == CLASS_SCENARIO
    assert result["span_minutes"] == 960
    assert result["departures_per_day"] == 65        # 06:00 to 22:00 every 15 minutes, inclusive
    assert result["departures_per_week"] == 65 * 5   # five operating days


def test_missing_coordinates_are_reported_not_guessed(database):
    result = estimate(make_payload(database))
    assert result["estimated_distance_km"] is None
    assert result["estimated_journey_minutes"] is None
    assert "coordinates" in result["missing"]


def test_distance_is_the_straight_line_times_the_detour_factor(database):
    payload = make_payload(database, origin_lat=0.0, origin_lon=0.0, destination_lat=0.0, destination_lon=0.1)
    result = estimate(payload)
    assert result["estimated_distance_km"] == pytest.approx(11.1195 * 1.3, abs=0.01)
    assert result["estimated_journey_minutes"] == round(result["estimated_distance_km"] / 15 * 60)
    assert result["missing"] is None


def test_journey_time_adds_dwell_time_per_intermediate_stop(database):
    payload = make_payload(
        database,
        origin_lat=12.9750, origin_lon=77.5950,
        destination_lat=12.9980, destination_lon=77.6240,
        stops=[{"name": "Middle", "lat": 12.9880, "lon": 77.6120}],
    )
    result = estimate(payload)
    chain_km = haversine_km(12.9750, 77.5950, 12.9880, 77.6120) + haversine_km(12.9880, 77.6120, 12.9980, 77.6240)
    expected_km = round(chain_km * 1.3, 2)
    assert result["estimated_distance_km"] == expected_km
    assert result["stops_between"] == 1
    assert result["estimated_journey_minutes"] == round(expected_km / 15 * 60 + 1 * 0.5)
    assert result["assumptions"]["average_bus_speed_kmph"] == 15.0
    assert "placeholder" in result["assumptions"]["method"]
    assert result["notice"] == scn.SCENARIO_NOTICE


def test_scenarios_do_not_touch_the_timetable_tables(database):
    make_payload(database)
    with database.session() as session:
        counts = sched.database_counts(session)
    assert counts["scenarios"] == 1
    assert counts["routes"] == 0
    assert counts["stop_times"] == 0


# ---------------------------------------------------------------- comparison and exports

def test_comparison_reports_the_difference_b_minus_a(database):
    a = make_payload(database, name="Every fifteen", frequency_minutes=15)
    b = make_payload(database, name="Every thirty", frequency_minutes=30)
    comparison = scn.compare_payloads(a, estimate(a), b, estimate(b))
    assert comparison["classification"] == CLASS_SCENARIO
    assert comparison["difference_b_minus_a"]["departures_per_day"] == 33 - 65
    assert comparison["difference_b_minus_a"]["estimated_distance_km"] is None
    assert comparison["notice"] == scn.SCENARIO_NOTICE


def test_csv_export_neutralises_spreadsheet_formulas(database):
    payload = make_payload(database, name='=HYPERLINK("https://example.invalid","open")')
    rows = list(csv.reader(io.StringIO(scenarios_csv([(payload, estimate(payload))]))))
    assert rows[0][0] == "classification"
    assert rows[1][0] == CLASS_SCENARIO
    assert rows[1][1].startswith("'=HYPERLINK")


def test_pdf_exports_are_real_pdf_documents(database):
    payload = make_payload(database)
    result = estimate(payload)
    assert scenario_pdf(payload, result).startswith(b"%PDF-")
    assert comparison_pdf(scn.compare_payloads(payload, result, payload, result)).startswith(b"%PDF-")
