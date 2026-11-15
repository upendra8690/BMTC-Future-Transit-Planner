"""Search matches what the user typed, literally. A percent sign, an underscore or a backslash is not a wildcard."""

from __future__ import annotations

from app.services.schedule import LIKE_ESCAPE, contains_pattern
from fastapi.testclient import TestClient

from tests.helpers import admin_headers, valid_files, zip_of

UNVERIFIED = "UNVERIFIED_FEED"
MONDAY_2027 = "2027-01-11"


def punctuated_feed() -> bytes:
    """A valid feed whose stop names contain %, _ and a backslash.

    T1 runs Alpha to Beta; T2 runs 100% Market to Ram_Nagar.
    """
    files = valid_files()
    files["stops.txt"] = (
        "stop_id,stop_name,stop_lat,stop_lon,location_type\n"
        "S1,Alpha,12.97,77.59,0\n"
        "S2,Beta,12.98,77.60,0\n"
        "S3,100% Market,12.99,77.61,0\n"
        "S4,Ram_Nagar,12.991,77.611,0\n"
        "S5,Ram Nagar,12.992,77.612,0\n"
        "S6,Back\\slash Road,12.993,77.613,0\n"
    )
    files["trips.txt"] = "route_id,service_id,trip_id,direction_id\nR1,WK,T1,0\nR1,WK,T2,1\n"
    files["stop_times.txt"] = (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T1,08:00:00,08:00:00,S1,1\nT1,08:10:00,08:10:00,S2,2\n"
        "T2,09:00:00,09:00:00,S3,1\nT2,09:20:00,09:20:00,S4,2\n"
    )
    return zip_of(files)


def load_punctuated_feed(client: TestClient) -> None:
    source = client.post(
        "/api/admin/data-sources",
        headers=admin_headers(),
        json={"name": "Punctuation feed", "publisher": "Test publisher", "kind": "UNKNOWN", "license": "test"},
    ).json()
    response = client.post(
        "/api/admin/imports",
        headers=admin_headers(),
        files={"file": ("punctuation.zip", punctuated_feed(), "application/zip")},
        data={"data_source_id": str(source["id"])},
    )
    assert response.status_code == 201, response.text


def stop_names(client: TestClient, query: str) -> list[str]:
    response = client.get("/api/stops", params={"classification": UNVERIFIED, "q": query, "limit": 100})
    assert response.status_code == 200, response.text
    return sorted(stop["name"] for stop in response.json()["results"])


def journeys(client: TestClient, origin: str, destination: str) -> dict:
    response = client.get(
        "/api/journey",
        params={"origin": origin, "destination": destination, "date": MONDAY_2027, "classification": UNVERIFIED},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_pattern_helper_escapes_the_three_special_characters():
    assert LIKE_ESCAPE == "\\"
    assert contains_pattern("a%b_c\\d") == "%a\\%b\\_c\\\\d%"
    assert contains_pattern("plain") == "%plain%"


def test_percent_sign_matches_only_names_that_contain_one(client):
    load_punctuated_feed(client)
    assert stop_names(client, "%") == ["100% Market"]


def test_underscore_matches_only_a_real_underscore(client):
    load_punctuated_feed(client)
    assert stop_names(client, "ram_") == ["Ram_Nagar"]
    assert stop_names(client, "ram nagar") == ["Ram Nagar"]


def test_backslash_matches_only_a_real_backslash(client):
    load_punctuated_feed(client)
    assert stop_names(client, "\\") == ["Back\\slash Road"]


def test_ordinary_search_is_still_a_case_insensitive_contains_search(client):
    load_punctuated_feed(client)
    assert stop_names(client, "ALPH") == ["Alpha"]
    assert len(stop_names(client, "")) == 6


def test_journey_origin_and_destination_are_matched_literally(client):
    load_punctuated_feed(client)
    body = journeys(client, "100%", "ram_")
    assert len(body["journeys"]) == 1
    assert body["journeys"][0]["origin_stop"] == "100% Market"
    assert body["journeys"][0]["destination_stop"] == "Ram_Nagar"


def test_percent_signs_do_not_match_every_stop(client):
    load_punctuated_feed(client)
    # The journey endpoint needs at least two characters. "%%" is literal: no stop name contains two percent
    # signs, so nothing matches. If % were a wildcard, "%%" would include Alpha and list the Alpha to Beta trip.
    assert journeys(client, "%%", "beta")["journeys"] == []


def test_blank_origin_or_destination_gives_a_message_not_every_stop(client):
    load_punctuated_feed(client)
    body = journeys(client, "  ", "beta")
    assert body["journeys"] == []
    assert body["message"] == "Enter a name for both the origin and the destination."
