from __future__ import annotations

from base64 import urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

from app.models.tracker import Tracker

GOOGLE_FLIGHTS_LANGUAGE = "en-US"
GOOGLE_FLIGHTS_TIME_FILTER_TFU = "EgYIABAAGAA"
GOOGLE_FLIGHTS_FILTER_FLAGS = b"\x08\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01"
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


@dataclass(frozen=True)
class GoogleFlightsSearchSpec:
    travel_date: str
    origin_airport: str
    destination_airport: str
    airline_codes: list[str]
    start_time: str
    end_time: str


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


def _encode_airport_message(code: str, *, filtered: bool = False) -> bytes:
    payload = bytearray()
    if filtered:
        payload.extend(_encode_enum_field(1, 1))
    payload.extend(_encode_string_field(2, code))
    return bytes(payload)


def _encode_info_message(tracker: Tracker) -> bytes:
    search = GoogleFlightsSearchSpec(
        travel_date=tracker.travel_date.isoformat(),
        origin_airport=tracker.primary_origin,
        destination_airport=tracker.primary_destination,
        airline_codes=tracker.airline_codes,
        start_time=tracker.start_time,
        end_time=tracker.end_time,
    )
    return _encode_info_message_from_search(search)


def _encode_info_message_from_search(search: GoogleFlightsSearchSpec) -> bytes:
    payload = bytearray()
    departure_window = _departure_hour_window(search.start_time, search.end_time)
    has_departure_filter = departure_window != (0, 23)
    if has_departure_filter:
        payload.extend(_encode_enum_field(1, 28))
        payload.extend(_encode_enum_field(2, 2))
    payload.extend(_encode_message_field(3, _encode_flight_data_message(search)))
    payload.extend(_encode_enum_field(8, 1))   # one adult
    payload.extend(_encode_enum_field(9, 1))   # economy
    if has_departure_filter:
        payload.extend(_encode_enum_field(14, 1))
        payload.extend(_encode_message_field(16, GOOGLE_FLIGHTS_FILTER_FLAGS))
    payload.extend(_encode_enum_field(19, 2))  # one-way
    return bytes(payload)


def build_google_flights_query_url(tracker: Tracker) -> str:
    return build_google_flights_query_url_for_search(
        travel_date=tracker.travel_date.isoformat(),
        origin_airport=tracker.primary_origin,
        destination_airport=tracker.primary_destination,
        airline_codes=tracker.airline_codes,
        start_time=tracker.start_time,
        end_time=tracker.end_time,
    )


def build_google_flights_query_url_for_search(
    *,
    travel_date: str,
    origin_airport: str,
    destination_airport: str,
    airline_codes: list[str],
    start_time: str,
    end_time: str,
) -> str:
    search = GoogleFlightsSearchSpec(
        travel_date=travel_date,
        origin_airport=origin_airport,
        destination_airport=destination_airport,
        airline_codes=airline_codes,
        start_time=start_time,
        end_time=end_time,
    )
    tfs = urlsafe_b64encode(_encode_info_message_from_search(search)).decode("utf-8").rstrip("=")
    params: dict[str, str] = {"tfs": tfs, "hl": GOOGLE_FLIGHTS_LANGUAGE}
    if _departure_hour_window(start_time, end_time) != (0, 23):
        params["tfu"] = GOOGLE_FLIGHTS_TIME_FILTER_TFU
    return f"https://www.google.com/travel/flights/search?{urlencode(params)}"


def generated_tracker_seed_summary(tracker: Tracker) -> str:
    route = f"{tracker.primary_origin} to {tracker.primary_destination} on {tracker.travel_date.isoformat()}"
    airline_text = ""
    if tracker.airline_codes:
        airline_text = f" with {', '.join(tracker.airline_codes)}"
    departure_text = ""
    if _departure_hour_window(tracker.start_time, tracker.end_time) != (0, 23):
        departure_start, departure_end = _departure_hour_window(tracker.start_time, tracker.end_time)
        departure_text = (
            f" and an hour-bucketed departure filter around {tracker.start_time}-{tracker.end_time} "
            f"({departure_start}:00-{departure_end + 1}:00)"
        )
    if len(tracker.origin_codes) == 1 and len(tracker.destination_codes) == 1:
        return f"Generated search opens {route}{airline_text}{departure_text}."
    return (
        f"Generated search opens {route}{airline_text}{departure_text} using the primary airport pair. "
        "Refine alternate airports directly in Google Flights if needed."
    )


def _departure_hour_window(start_time: str, end_time: str) -> tuple[int, int]:
    start = datetime.strptime(start_time, "%H:%M")
    end = datetime.strptime(end_time, "%H:%M")

    start_hour = start.hour
    end_exclusive = end.hour + (1 if end.minute > 0 else 0)
    if end_exclusive == 0:
        end_exclusive = 24
    if end_exclusive <= start_hour:
        end_exclusive = start_hour + 1
    end_inclusive = min(23, end_exclusive - 1)
    return start_hour, end_inclusive


def _encode_flight_data_message(search: GoogleFlightsSearchSpec) -> bytes:
    payload = bytearray()
    payload.extend(_encode_string_field(2, search.travel_date))
    payload.extend(_encode_enum_field(5, 0))  # nonstop only
    for airline in search.airline_codes:
        payload.extend(_encode_string_field(6, GOOGLE_FLIGHTS_AIRLINE_CODES.get(airline, airline)))
    departure_start, departure_end = _departure_hour_window(search.start_time, search.end_time)
    is_filtered = (departure_start, departure_end) != (0, 23)
    if is_filtered:
        payload.extend(_encode_enum_field(8, departure_start))
        payload.extend(_encode_enum_field(9, departure_end))
        payload.extend(_encode_enum_field(10, 0))
        payload.extend(_encode_enum_field(11, 23))
    payload.extend(_encode_message_field(13, _encode_airport_message(search.origin_airport, filtered=is_filtered)))
    payload.extend(_encode_message_field(14, _encode_airport_message(search.destination_airport, filtered=is_filtered)))
    return bytes(payload)
