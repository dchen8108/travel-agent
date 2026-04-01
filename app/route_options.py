from __future__ import annotations

from datetime import date, datetime, timedelta

from app.catalog import WEEKDAYS
from app.models.base import FareClassPolicy


def split_pipe(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split("|") if part.strip()]


def join_pipe(values: list[str]) -> str:
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return "|".join(deduped)


def weekday_index(weekday: str) -> int:
    return WEEKDAYS.index(weekday)


def weekday_from_anchor(anchor_weekday: str, day_offset: int) -> str:
    index = (weekday_index(anchor_weekday) + day_offset) % len(WEEKDAYS)
    return WEEKDAYS[index]


def weekday_from_anchor_date(anchor_date: date, day_offset: int) -> str:
    return WEEKDAYS[(anchor_date.weekday() + day_offset) % len(WEEKDAYS)]


def day_offset_label(anchor_weekday: str, day_offset: int) -> str:
    weekday = weekday_from_anchor(anchor_weekday, day_offset)
    token = "T" if day_offset == 0 else f"T{day_offset:+d}"
    return f"{weekday} ({token})"


def travel_date_for_offset(anchor_date: date, day_offset: int) -> date:
    return anchor_date + timedelta(days=day_offset)


def parse_time(value: str) -> str:
    return datetime.strptime(value, "%H:%M").strftime("%H:%M")


def validate_time_window(start_time: str, end_time: str) -> tuple[str, str]:
    start = parse_time(start_time)
    end = parse_time(end_time)
    if end <= start:
        raise ValueError("End time must be after start time.")
    return start, end


def departure_time_from_time_line(time_line: str) -> str | None:
    if not time_line:
        return None
    first_part = time_line.split("–", 1)[0].strip().replace("+1", "")
    try:
        parsed = datetime.strptime(first_part, "%I:%M %p")
    except ValueError:
        return None
    return parsed.strftime("%H:%M")


def arrival_time_from_time_line(time_line: str) -> str | None:
    if "–" not in time_line:
        return None
    second_part = time_line.split("–", 1)[1].strip().replace("+1", "")
    try:
        parsed = datetime.strptime(second_part, "%I:%M %p")
    except ValueError:
        return None
    return parsed.strftime("%H:%M")


def time_in_window(start_time: str, end_time: str, candidate: str | None) -> bool:
    if candidate is None:
        return False
    return start_time <= candidate <= end_time


def route_option_summary(
    origin_airports: list[str],
    destination_airports: list[str],
    airlines: list[str],
    day_label: str,
    start_time: str,
    end_time: str,
    fare_class_policy: str = FareClassPolicy.INCLUDE_BASIC,
) -> str:
    origins = ", ".join(origin_airports)
    destinations = ", ".join(destination_airports)
    airline_label = ", ".join(airlines)
    fare_label = "Basic allowed" if fare_class_policy == FareClassPolicy.INCLUDE_BASIC else "Basic excluded"
    return f"{origins} → {destinations} · {day_label} · {start_time}-{end_time} · {airline_label} · {fare_label}"


def cumulative_route_option_bias(savings_needed_vs_previous: list[int], index: int) -> int:
    if index <= 0:
        return 0
    return sum(max(0, int(value)) for value in savings_needed_vs_previous[: index + 1])
