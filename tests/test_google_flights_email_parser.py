from __future__ import annotations

from pathlib import Path

from app.ingestion.google_flights_email_parser import parse_google_flights_email


FIXTURE = Path(__file__).parent / "fixtures" / "google_flights_sample.eml"


def test_parse_google_flights_email_extracts_observations() -> None:
    parsed = parse_google_flights_email(FIXTURE)

    assert "tracked flights" in parsed.subject.lower()
    assert len(parsed.observations) == 5

    first = parsed.observations[0]
    assert first.route_text == "San Francisco to Burbank"
    assert first.origin_airport == "SFO"
    assert first.destination_airport == "BUR"
    assert first.price == 139
    assert first.previous_price == 149
    assert first.price_direction == "dropped"
