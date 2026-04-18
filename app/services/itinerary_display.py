from __future__ import annotations

from datetime import date, datetime
import re

from app.catalog import airline_display, airline_marketing_code
from app.models.booking import Booking
from app.models.base import utcnow
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget

_SUPERSCRIPT_TRANSLATION = str.maketrans({
    "+": "⁺",
    "-": "⁻",
    "0": "⁰",
    "1": "¹",
    "2": "²",
    "3": "³",
    "4": "⁴",
    "5": "⁵",
    "6": "⁶",
    "7": "⁷",
    "8": "⁸",
    "9": "⁹",
})


def booking_route_label(booking: Booking) -> str:
    route = f"{booking.origin_airport} \u2192 {booking.destination_airport}"
    airline = booking_airline_label(booking)
    return f"{route} \u00b7 {airline}" if airline else route


def booking_airline_label(booking: Booking) -> str:
    flight_number = " ".join(str(getattr(booking, "flight_number", "") or "").strip().upper().split())
    if not flight_number:
        return airline_display(booking.airline)
    marketing_code = airline_marketing_code(booking.airline)
    compact_prefix = f"{marketing_code}".upper()
    if flight_number.startswith(f"{compact_prefix} "):
        return flight_number
    if flight_number.startswith(compact_prefix) and len(flight_number) > len(compact_prefix):
        suffix = flight_number[len(compact_prefix):].strip()
        return f"{compact_prefix} {suffix}".strip()
    return f"{compact_prefix} {flight_number}".strip()


def _split_time_day_suffix(value: str) -> tuple[str, int | None]:
    raw = value.strip()
    if not raw:
        return "", None
    match = re.match(r"^(.*?)(?:\s*([+-]\d+))?$", raw)
    if not match:
        return raw, None
    base = (match.group(1) or "").strip()
    suffix = match.group(2)
    return base, (int(suffix) if suffix else None)


def format_day_delta_superscript(delta: int) -> str:
    if delta == 0:
        return ""
    return f"{delta:+d}".translate(_SUPERSCRIPT_TRANSLATION)


def format_departure_time_label(value: str, *, fallback_day_delta: int = 0) -> str:
    raw, explicit_day_delta = _split_time_day_suffix(value)
    if not raw:
        return ""
    meridiem_match = re.match(r"^\s*(\d{1,2}:\d{2})\s*([APap][Mm])", raw)
    if meridiem_match:
        return f"{meridiem_match.group(1)} {meridiem_match.group(2).upper()}"
    time_match = re.match(r"^\s*(\d{1,2}:\d{2})", raw)
    if time_match:
        raw = time_match.group(1)
    if "am" in raw.lower() or "pm" in raw.lower():
        return raw
    try:
        parsed = datetime.strptime(raw, "%H:%M")
    except ValueError:
        label = raw
    else:
        label = parsed.strftime("%I:%M %p").lstrip("0")
    day_delta = explicit_day_delta if explicit_day_delta is not None else fallback_day_delta
    return f"{label}{format_day_delta_superscript(day_delta)}" if day_delta else label


def format_departure_window_label(start_time: str, end_time: str, *, fallback_day_delta: int = 0) -> str:
    start_label = format_departure_time_label(start_time, fallback_day_delta=fallback_day_delta)
    end_label = format_departure_time_label(end_time, fallback_day_delta=fallback_day_delta)
    if start_label and end_label:
        return f"{start_label} \u2013 {end_label}"
    if start_label:
        return start_label
    if end_label:
        return f"Until {end_label}"
    return "Time window"


def format_time_range_label(departure_value: str, arrival_value: str, *, fallback_day_delta: int = 0) -> str:
    departure_label = format_departure_time_label(departure_value, fallback_day_delta=fallback_day_delta)
    arrival_label = format_departure_time_label(arrival_value, fallback_day_delta=fallback_day_delta)
    if departure_label and arrival_label:
        return f"{departure_label} \u2192 {arrival_label}"
    return departure_label or arrival_label


def format_refresh_timestamp_label(value: datetime, *, now: datetime | None = None) -> str:
    local_value = value.astimezone()
    current = now.astimezone() if now is not None else utcnow()
    time_label = format_departure_time_label(local_value.strftime("%H:%M"))
    if local_value.date() == current.date():
        return time_label
    if local_value.year == current.year:
        return f"{local_value.strftime('%b')} {local_value.day} · {time_label}"
    return f"{local_value.strftime('%b')} {local_value.day}, {local_value.year} · {time_label}"


def travel_day_delta(anchor_date: date, travel_date: date | None) -> int:
    if travel_date is None:
        return 0
    return (travel_date - anchor_date).days


def tracker_route_label(tracker: Tracker) -> str:
    if tracker.latest_winning_origin_airport and tracker.latest_winning_destination_airport:
        return f"{tracker.latest_winning_origin_airport} \u2192 {tracker.latest_winning_destination_airport}"
    origins = compact_airport_codes(tracker.origin_codes)
    destinations = compact_airport_codes(tracker.destination_codes)
    if origins and destinations:
        return f"{origins} \u2192 {destinations}"
    return ""


def fetch_target_route_label(
    target: TrackerFetchTarget,
    *,
    fallback_tracker: Tracker | None = None,
) -> str:
    route = f"{target.origin_airport} \u2192 {target.destination_airport}"
    airline = airline_display(target.latest_airline) if target.latest_airline else ""
    if not airline and fallback_tracker is not None and len(fallback_tracker.airline_codes) == 1:
        airline = airline_display(fallback_tracker.airline_codes[0])
    return f"{route} \u00b7 {airline}" if airline else route


def tracker_display_label(
    tracker: Tracker | None,
    *,
    current_target: TrackerFetchTarget | None = None,
) -> str:
    if current_target is not None:
        return fetch_target_route_label(current_target, fallback_tracker=tracker)
    if tracker is None:
        return ""
    route = tracker_route_label(tracker)
    if not route:
        return ""
    if len(tracker.airline_codes) == 1:
        return f"{route} \u00b7 {airline_display(tracker.airline_codes[0])}"
    return route


def route_option_display_label(
    origin_codes: list[str],
    destination_codes: list[str],
    airline_codes: list[str],
) -> str:
    route = ""
    origins = compact_airport_codes(origin_codes)
    destinations = compact_airport_codes(destination_codes)
    if origins and destinations:
        route = f"{origins} \u2192 {destinations}"
    airlines = ", ".join(airline_display(code) for code in airline_codes if code)
    if route and airlines:
        return f"{route} \u00b7 {airlines}"
    return route or airlines


def tracker_best_fetch_target(
    tracker: Tracker | None,
    targets: list[TrackerFetchTarget],
) -> TrackerFetchTarget | None:
    if tracker is None or not targets:
        return None
    if tracker.latest_winning_origin_airport and tracker.latest_winning_destination_airport:
        exact_targets = [
            target
            for target in targets
            if target.origin_airport == tracker.latest_winning_origin_airport
            and target.destination_airport == tracker.latest_winning_destination_airport
        ]
        if tracker.latest_observed_price is not None:
            exact_price_match = [
                target
                for target in exact_targets
                if target.latest_price == tracker.latest_observed_price
            ]
            if exact_price_match:
                return sorted(
                    exact_price_match,
                    key=lambda item: (item.origin_airport, item.destination_airport),
                )[0]
        if exact_targets:
            return sorted(
                exact_targets,
                key=lambda item: (item.origin_airport, item.destination_airport),
            )[0]
    if tracker.latest_observed_price is not None:
        priced_targets = [
            target
            for target in targets
            if target.latest_price == tracker.latest_observed_price
        ]
        if priced_targets:
            return sorted(
                priced_targets,
                key=lambda item: (item.origin_airport, item.destination_airport),
            )[0]
    live_targets = [target for target in targets if target.latest_price is not None]
    if live_targets:
        return sorted(
            live_targets,
            key=lambda item: (
                item.latest_price or 10**9,
                item.origin_airport,
                item.destination_airport,
            ),
        )[0]
    return sorted(
        targets,
        key=lambda item: (item.origin_airport, item.destination_airport),
    )[0]


def compact_airport_codes(codes: list[str]) -> str:
    return " | ".join(code for code in codes if code)
