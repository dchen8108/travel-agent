from __future__ import annotations

from pathlib import Path

from app.ingestion.google_flights_email_parser import parse_google_flights_email


FIXTURE = Path(__file__).parent / "fixtures" / "google_flights_sample.eml"


def test_parse_google_flights_email_sample() -> None:
    parsed = parse_google_flights_email(FIXTURE)

    assert parsed.subject == "Prices for your tracked flights to Burbank, New York, Los Angeles have changed"
    assert parsed.message_id.endswith("@google.com>")
    assert len(parsed.sections) == 3
    assert len(parsed.observations) == 5

    first_section = parsed.sections[0]
    assert first_section.route_text == "San Francisco to Burbank"
    assert str(first_section.travel_date) == "2026-06-04"

    first_observation = parsed.observations[0]
    assert first_observation.origin_airport == "SFO"
    assert first_observation.destination_airport == "BUR"
    assert first_observation.price == 139
    assert first_observation.previous_price == 149
    assert first_observation.price_direction == "dropped"
    assert first_observation.airline == "Southwest"

    last_observation = parsed.observations[-1]
    assert last_observation.origin_airport == "JFK"
    assert last_observation.destination_airport == "LAX"
    assert last_observation.price == 434
    assert last_observation.previous_price == 269
    assert last_observation.price_direction == "increased"
