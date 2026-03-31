from __future__ import annotations

from urllib.parse import quote_plus

from app.models.tracker import Tracker


def build_google_flights_query_url(tracker: Tracker) -> str:
    origins = " or ".join(tracker.origin_codes)
    destinations = " or ".join(tracker.destination_codes)
    airlines = " or ".join(tracker.airline_codes)
    query = (
        f"Flights from {origins} to {destinations} on {tracker.travel_date.isoformat()} "
        f"between {tracker.start_time} and {tracker.end_time} with {airlines}"
    )
    return f"https://www.google.com/travel/flights?q={quote_plus(query)}"
