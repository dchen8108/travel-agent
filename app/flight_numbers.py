from __future__ import annotations

import re
from collections.abc import Iterable

from app.catalog import airline_marketing_code, known_airline_code


_FLIGHT_NUMBER_SEPARATOR_RE = re.compile(r"\s*(?:\||,|/|;|\n)\s*")
_FLIGHT_NUMBER_PREFIX_RE = re.compile(r"^([A-Z]{2,3})\s*(\d[A-Z0-9]*)$")
_FLIGHT_NUMBER_SUFFIX_RE = re.compile(r"^(\d[A-Z0-9]*)$")


def split_flight_numbers(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        raw_parts = [str(item) for item in value]
    else:
        raw_text = str(value).strip()
        if not raw_text:
            return []
        raw_parts = _FLIGHT_NUMBER_SEPARATOR_RE.split(raw_text)
    normalized: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        cleaned = " ".join(str(part).strip().upper().split())
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def canonicalize_flight_number(value: object, *, airline: str = "") -> str:
    cleaned = " ".join(str(value or "").strip().upper().split())
    if not cleaned:
        return ""
    compact = cleaned.replace(" ", "")
    prefixed = _FLIGHT_NUMBER_PREFIX_RE.match(compact)
    if prefixed:
        return f"{prefixed.group(1)} {prefixed.group(2)}"
    known_airline = known_airline_code(airline)
    if known_airline:
        bare_suffix = _FLIGHT_NUMBER_SUFFIX_RE.match(compact)
        if bare_suffix:
            return f"{airline_marketing_code(known_airline)} {bare_suffix.group(1)}"
    return cleaned


def join_flight_numbers(values: object, *, airline: str = "") -> str:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in split_flight_numbers(values):
        canonical = canonicalize_flight_number(value, airline=airline)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        normalized.append(canonical)
    return ", ".join(normalized)
