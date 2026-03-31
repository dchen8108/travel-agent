from __future__ import annotations

from datetime import date
from urllib.parse import quote_plus


def build_google_flights_query_url(origin: str, destination: str, travel_date: date) -> str:
    query = f"Flights from {origin} to {destination} on {travel_date.isoformat()}"
    return f"https://www.google.com/travel/flights?q={quote_plus(query)}"
