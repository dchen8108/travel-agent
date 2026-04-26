from __future__ import annotations

from datetime import date, datetime, timedelta
import re

from app.catalog import stop_display_label
from app.flight_numbers import split_flight_numbers
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
    return append_route_stop_label(route, getattr(booking, "stops", ""))


def booking_airline_label(booking: Booking) -> str:
    flight_numbers = split_flight_numbers(getattr(booking, "flight_number", "") or "")
    if not flight_numbers:
        return ""
    return ", ".join(flight_numbers)


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


def _label_calendar_day_delta(
    value: str,
    *,
    anchor_date: date | None,
    fallback_day_delta: int,
) -> int | None:
    if anchor_date is None:
        return None
    match = re.search(r"\bon\s+(?:[A-Za-z]{3},\s+)?([A-Za-z]{3})\s+(\d{1,2})\b", value.strip())
    if not match:
        return None
    reference_date = anchor_date + timedelta(days=fallback_day_delta)
    month_label = match.group(1)
    day_label = match.group(2)
    candidates: list[date] = []
    for year in (reference_date.year - 1, reference_date.year, reference_date.year + 1):
        try:
            candidates.append(datetime.strptime(f"{month_label} {day_label} {year}", "%b %d %Y").date())
        except ValueError:
            continue
    if not candidates:
        return None
    best = min(candidates, key=lambda candidate: abs((candidate - reference_date).days))
    return (best - anchor_date).days


def format_day_delta_superscript(delta: int) -> str:
    if delta == 0:
        return ""
    return f"{delta:+d}".translate(_SUPERSCRIPT_TRANSLATION)


def format_departure_time_label(
    value: str,
    *,
    fallback_day_delta: int = 0,
    anchor_date: date | None = None,
) -> str:
    raw, explicit_day_delta = _split_time_day_suffix(value)
    if not raw:
        return ""
    meridiem_match = re.match(r"^\s*(\d{1,2}:\d{2})\s*([APap][Mm])", raw)
    if meridiem_match:
        label = f"{meridiem_match.group(1)} {meridiem_match.group(2).upper()}"
    else:
        time_match = re.match(r"^\s*(\d{1,2}:\d{2})", raw)
        if time_match:
            raw = time_match.group(1)
        if "am" in raw.lower() or "pm" in raw.lower():
            label = raw
        else:
            try:
                parsed = datetime.strptime(raw, "%H:%M")
            except ValueError:
                label = raw
            else:
                label = parsed.strftime("%I:%M %p").lstrip("0")
    parsed_day_delta = _label_calendar_day_delta(
        value,
        anchor_date=anchor_date,
        fallback_day_delta=fallback_day_delta,
    )
    day_delta = explicit_day_delta if explicit_day_delta is not None else (
        parsed_day_delta if parsed_day_delta is not None else fallback_day_delta
    )
    return f"{label}{format_day_delta_superscript(day_delta)}" if day_delta else label


def format_departure_window_label(
    start_time: str,
    end_time: str,
    *,
    fallback_day_delta: int = 0,
    anchor_date: date | None = None,
) -> str:
    start_label = format_departure_time_label(
        start_time,
        fallback_day_delta=fallback_day_delta,
        anchor_date=anchor_date,
    )
    end_label = format_departure_time_label(
        end_time,
        fallback_day_delta=fallback_day_delta,
        anchor_date=anchor_date,
    )
    if start_label and end_label:
        return f"{start_label} \u2013 {end_label}"
    if start_label:
        return start_label
    if end_label:
        return f"Until {end_label}"
    return "Time window"


def format_time_range_label(
    departure_value: str,
    arrival_value: str,
    *,
    fallback_day_delta: int = 0,
    fallback_departure_day_delta: int | None = None,
    fallback_arrival_day_delta: int | None = None,
    anchor_date: date | None = None,
) -> str:
    departure_day_delta = fallback_day_delta if fallback_departure_day_delta is None else fallback_departure_day_delta
    arrival_day_delta = departure_day_delta if fallback_arrival_day_delta is None else fallback_arrival_day_delta
    departure_label = format_departure_time_label(
        departure_value,
        fallback_day_delta=departure_day_delta,
        anchor_date=anchor_date,
    )
    arrival_label = format_departure_time_label(
        arrival_value,
        fallback_day_delta=arrival_day_delta,
        anchor_date=anchor_date,
    )
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
    return f"{target.origin_airport} \u2192 {target.destination_airport}"


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
    return route


def append_route_stop_label(route: str, stops: str | None) -> str:
    stop_label = stop_display_label(stops, allow_empty=True)
    if not route or not stop_label or stop_label == "Nonstop":
        return route
    return f"{route} \u00b7 {stop_label}"


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
