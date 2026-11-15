"""Name normalisation and search: the same stop is found whichever Unicode form, letter case or spacing is typed."""

from __future__ import annotations

import unicodedata

from app.services.text import fold, normalise
from fastapi.testclient import TestClient

from tests.helpers import admin_headers, zip_of

KANNADA_NAME = "ಮೆಜೆಸ್ಟಿಕ್ ಬಸ್ ನಿಲ್ದಾಣ"  # Majestic bus station, written in Kannada script
HINDI_NAME = "नेहरू प्लेस"  # a Devanagari place name


def test_composed_and_decomposed_forms_are_the_same_name():
    composed = "Café Coffee Day"
    decomposed = unicodedata.normalize("NFD", composed)
    assert composed != decomposed  # the two strings differ as code points
    assert normalise(decomposed) == composed
    assert fold(decomposed) == fold(composed)


def test_kannada_and_hindi_names_compare_equal_across_normal_forms():
    for name in (KANNADA_NAME, HINDI_NAME):
        assert fold(unicodedata.normalize("NFD", name)) == fold(unicodedata.normalize("NFC", name))


def test_case_folding_follows_unicode_not_just_ascii():
    assert fold("MAJESTIC") == fold("majestic")
    assert fold("ÉCOLE") == fold("école")
    assert fold("Straße") == fold("STRASSE")  # full case folding: ß folds to ss


def test_spacing_is_collapsed_and_trimmed():
    assert normalise("  Demo   Market\t  Stop ") == "Demo Market Stop"
    assert fold(None) == ""
    assert fold("   ") == ""


def _import_names(client: TestClient, names: list[str]) -> None:
    source = client.post(
        "/api/admin/data-sources",
        json={"name": "Names", "publisher": "Test", "kind": "COMMUNITY", "license": "test"},
        headers=admin_headers(),
    ).json()
    stops = "stop_id,stop_name,stop_lat,stop_lon,location_type\n" + "".join(
        f"S{i},{name},12.97,77.59,0\n" for i, name in enumerate(names, start=1)
    )
    files = {
        "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\nT,Names,https://example.invalid,Asia/Kolkata\n",
        "routes.txt": "route_id,route_short_name,route_long_name,route_type\nR1,N-1,Names route,3\n",
        "stops.txt": stops,
        "trips.txt": "route_id,service_id,trip_id,direction_id\nR1,WK,T1,0\n",
        "stop_times.txt": (
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            f"T1,08:00:00,08:00:00,S1,1\nT1,08:10:00,08:10:00,S{len(names)},2\n"
        ),
        "calendar.txt": (
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
            "WK,1,1,1,1,1,1,1,20270101,20271231\n"
        ),
    }
    response = client.post(
        "/api/admin/imports",
        files={"file": ("names.zip", zip_of(files), "application/zip")},
        data={"data_source_id": str(source["id"])},
        headers=admin_headers(),
    )
    assert response.status_code == 201, response.text


def _stop_names(client: TestClient, query: str) -> list[str]:
    response = client.get(
        "/api/stops", params={"classification": "UNVERIFIED_FEED", "year": 2027, "q": query, "limit": 100}
    )
    assert response.status_code == 200
    return [stop["name"] for stop in response.json()["results"]]


def test_search_finds_stops_whatever_the_case_spacing_or_normal_form(client: TestClient):
    _import_names(client, ["Majestic Bus Stand", "École Centrale", "Café Coffee Day", KANNADA_NAME, HINDI_NAME])
    assert _stop_names(client, "MAJESTIC") == ["Majestic Bus Stand"]
    assert _stop_names(client, "  majestic   bus ") == ["Majestic Bus Stand"]
    assert _stop_names(client, "école") == ["École Centrale"]
    assert _stop_names(client, "ÉCOLE") == ["École Centrale"]
    # The user's keyboard produced the decomposed form; the stored name is the composed form.
    assert _stop_names(client, unicodedata.normalize("NFD", "Café")) == ["Café Coffee Day"]
    assert _stop_names(client, KANNADA_NAME[:6]) == [KANNADA_NAME]
    assert _stop_names(client, unicodedata.normalize("NFD", HINDI_NAME)) == [HINDI_NAME]


def test_wildcard_characters_in_a_search_are_literal(client: TestClient):
    _import_names(client, ["Stop 100% Ready", "Stop A_B", "Plain Stop"])
    assert _stop_names(client, "%") == ["Stop 100% Ready"]
    assert _stop_names(client, "_") == ["Stop A_B"]
