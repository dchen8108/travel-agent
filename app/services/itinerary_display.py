from __future__ import annotations

from datetime import date, datetime
import re

from app.catalog import airline_display
from app.models.booking import Booking
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget


def booking_route_label(booking: Booking) -> str:
    route = f"{booking.origin_airport} \u2192 {booking.destination_airport}"
    airline = airline_display(booking.airline)
    return f"{route} \u00b7 {airline}" if airline else route


def format_departure_time_label(value: str) -> str:
    raw = value.strip()
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
        return raw
    return parsed.strftime("%I:%M %p").lstrip("0")


def travel_day_delta_label(anchor_date: date, travel_date: date | None) -> str:
    if travel_date is None:
        return ""
    delta = (travel_date - anchor_date).days
    if delta == 0:
        return ""
    unit = "day" if abs(delta) == 1 else "days"
    return f"{delta:+d} {unit}"


def tracker_route_label(tracker: Tracker) -> str:
    if tracker.latest_winning_origin_airport and tracker.latest_winning_destination_airport:
        return f"{tracker.latest_winning_origin_airport} \u2192 {tracker.latest_winning_destination_airport}"
    origins = _compact_airport_codes(tracker.origin_codes)
    destinations = _compact_airport_codes(tracker.destination_codes)
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


def _compact_airport_codes(codes: list[str]) -> str:
    return "|".join(code for code in codes if code)
