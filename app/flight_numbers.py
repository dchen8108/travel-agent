from __future__ import annotations

import re
from collections.abc import Iterable


_FLIGHT_NUMBER_SEPARATOR_RE = re.compile(r"\s*(?:\||,|/|;|\n)\s*")


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


def join_flight_numbers(values: object) -> str:
    return " | ".join(split_flight_numbers(values))
