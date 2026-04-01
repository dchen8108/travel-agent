from __future__ import annotations

from base64 import b64encode
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.models.tracker import Tracker


ALLOWED_TRACKER_HOSTS = {"google.com", "www.google.com", "c.gle"}
GOOGLE_FLIGHTS_LANGUAGE = "en-US"
GOOGLE_FLIGHTS_AIRLINE_CODES = {
    "Alaska": "AS",
    "American": "AA",
    "Delta": "DL",
    "JetBlue": "B6",
    "Southwest": "WN",
    "United": "UA",
    "Hawaiian": "HA",
    "Frontier": "F9",
    "Spirit": "NK",
    "Sun Country": "SY",
}


def _encode_varint(value: int) -> bytes:
    remaining = value
    chunks = bytearray()
    while True:
        to_write = remaining & 0x7F
        remaining >>= 7
        if remaining:
            chunks.append(to_write | 0x80)
        else:
            chunks.append(to_write)
            break
    return bytes(chunks)


def _field_key(field_number: int, wire_type: int) -> bytes:
    return _encode_varint((field_number << 3) | wire_type)


def _encode_string_field(field_number: int, value: str) -> bytes:
    encoded = value.encode("utf-8")
    return _field_key(field_number, 2) + _encode_varint(len(encoded)) + encoded


def _encode_message_field(field_number: int, payload: bytes) -> bytes:
    return _field_key(field_number, 2) + _encode_varint(len(payload)) + payload


def _encode_enum_field(field_number: int, value: int) -> bytes:
    return _field_key(field_number, 0) + _encode_varint(value)


def _encode_airport_message(code: str) -> bytes:
    return _encode_string_field(2, code)


def _encode_flight_data_message(tracker: Tracker) -> bytes:
    payload = bytearray()
    payload.extend(_encode_string_field(2, tracker.travel_date.isoformat()))
    payload.extend(_encode_enum_field(5, 0))  # nonstop only
    for airline in tracker.airline_codes:
        payload.extend(_encode_string_field(6, GOOGLE_FLIGHTS_AIRLINE_CODES.get(airline, airline)))
    payload.extend(_encode_message_field(13, _encode_airport_message(tracker.primary_origin)))
    payload.extend(_encode_message_field(14, _encode_airport_message(tracker.primary_destination)))
    return bytes(payload)


def _encode_info_message(tracker: Tracker) -> bytes:
    payload = bytearray()
    payload.extend(_encode_message_field(3, _encode_flight_data_message(tracker)))
    payload.extend(_encode_enum_field(8, 1))   # one adult
    payload.extend(_encode_enum_field(9, 1))   # economy
    payload.extend(_encode_enum_field(19, 2))  # one-way
    return bytes(payload)


def build_google_flights_query_url(tracker: Tracker) -> str:
    tfs = b64encode(_encode_info_message(tracker)).decode("utf-8")
    params = urlencode({"tfs": tfs, "hl": GOOGLE_FLIGHTS_LANGUAGE})
    return f"https://www.google.com/travel/flights/search?{params}"


def generated_tracker_seed_summary(tracker: Tracker) -> str:
    route = f"{tracker.primary_origin} to {tracker.primary_destination} on {tracker.travel_date.isoformat()}"
    airline_text = ""
    if tracker.airline_codes:
        airline_text = f" with {', '.join(tracker.airline_codes)}"
    if len(tracker.origin_codes) == 1 and len(tracker.destination_codes) == 1:
        return f"Generated search opens {route}{airline_text}."
    return (
        f"Generated search opens {route}{airline_text} using the primary airport pair. "
        "Refine alternate airports in Google Flights, then paste the exact tracked link back here."
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
