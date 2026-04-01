from __future__ import annotations

from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from app.models.tracker import Tracker


ALLOWED_TRACKER_HOSTS = {"google.com", "www.google.com", "c.gle"}


def build_google_flights_query_url(tracker: Tracker) -> str:
    query = f"Flights to {tracker.primary_destination} from {tracker.primary_origin} on {tracker.travel_date.isoformat()}"
    return f"https://www.google.com/travel/flights?q={quote(query)}"


def generated_tracker_seed_summary(tracker: Tracker) -> str:
    if len(tracker.origin_codes) == 1 and len(tracker.destination_codes) == 1:
        return f"Generated search opens {tracker.primary_origin} to {tracker.primary_destination} on {tracker.travel_date.isoformat()}."
    return (
        f"Generated search opens {tracker.primary_origin} to {tracker.primary_destination} on {tracker.travel_date.isoformat()} "
        "as a starting point. Refine airports or filters in Google Flights, then paste the exact tracked link back here."
    )


def normalize_google_flights_url(raw_url: str) -> str:
    url = raw_url.strip()
    if not url:
        return ""

    parsed = urlsplit(url)
    host = parsed.netloc.lower()
    if host not in ALLOWED_TRACKER_HOSTS:
        raise ValueError("Paste a Google Flights link.")

    if host in {"google.com", "www.google.com"} and not parsed.path.startswith("/travel/flights"):
        raise ValueError("Paste a Google Flights flights page link.")

    if host in {"google.com", "www.google.com"}:
        params = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key not in {"authuser", "pli"}]
        cleaned_query = urlencode(params, doseq=True)
        return urlunsplit((parsed.scheme or "https", host, parsed.path, cleaned_query, parsed.fragment))

    return url
