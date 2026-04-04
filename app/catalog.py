from __future__ import annotations

import json

WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

SUPPORTED_AIRPORTS = [
    {"code": "BUR", "label": "Hollywood Burbank", "keywords": "Burbank Los Angeles"},
    {"code": "LAX", "label": "Los Angeles Intl", "keywords": "Los Angeles El Segundo"},
    {"code": "SNA", "label": "John Wayne / Orange County", "keywords": "Orange County Santa Ana Irvine"},
    {"code": "LGB", "label": "Long Beach", "keywords": "Long Beach Los Angeles"},
    {"code": "ONT", "label": "Ontario Intl", "keywords": "Ontario Inland Empire"},
    {"code": "SAN", "label": "San Diego Intl", "keywords": "San Diego Lindbergh"},
    {"code": "SFO", "label": "San Francisco Intl", "keywords": "San Francisco Bay Area"},
    {"code": "OAK", "label": "Oakland Intl", "keywords": "Oakland East Bay"},
    {"code": "SJC", "label": "San Jose Mineta Intl", "keywords": "San Jose Silicon Valley"},
    {"code": "SMF", "label": "Sacramento Intl", "keywords": "Sacramento"},
    {"code": "PSP", "label": "Palm Springs Intl", "keywords": "Palm Springs Coachella Valley"},
    {"code": "LAS", "label": "Harry Reid Intl", "keywords": "Las Vegas"},
    {"code": "PHX", "label": "Phoenix Sky Harbor", "keywords": "Phoenix"},
    {"code": "SEA", "label": "Seattle-Tacoma Intl", "keywords": "Seattle SeaTac"},
    {"code": "PDX", "label": "Portland Intl", "keywords": "Portland"},
    {"code": "DEN", "label": "Denver Intl", "keywords": "Denver"},
    {"code": "AUS", "label": "Austin-Bergstrom", "keywords": "Austin"},
    {"code": "DFW", "label": "Dallas/Fort Worth Intl", "keywords": "Dallas Fort Worth"},
    {"code": "DAL", "label": "Dallas Love Field", "keywords": "Dallas"},
    {"code": "IAH", "label": "George Bush Intercontinental", "keywords": "Houston"},
    {"code": "HOU", "label": "William P. Hobby", "keywords": "Houston"},
    {"code": "ATL", "label": "Hartsfield-Jackson Atlanta Intl", "keywords": "Atlanta"},
    {"code": "ORD", "label": "Chicago O'Hare Intl", "keywords": "Chicago"},
    {"code": "JFK", "label": "John F. Kennedy Intl", "keywords": "New York Queens"},
    {"code": "LGA", "label": "LaGuardia", "keywords": "New York Queens"},
    {"code": "EWR", "label": "Newark Liberty Intl", "keywords": "New York Newark"},
]

SUPPORTED_AIRLINES = [
    {"code": "Alaska", "label": "Alaska Airlines", "keywords": "AS Alaska Airlines"},
    {"code": "American", "label": "American Airlines", "keywords": "AA American Airlines"},
    {"code": "Delta", "label": "Delta Air Lines", "keywords": "DL Delta Air Lines"},
    {"code": "JetBlue", "label": "JetBlue", "keywords": "B6 JetBlue Airways"},
    {"code": "Southwest", "label": "Southwest Airlines", "keywords": "WN Southwest"},
    {"code": "United", "label": "United Airlines", "keywords": "UA United Airlines"},
    {"code": "Hawaiian", "label": "Hawaiian Airlines", "keywords": "HA Hawaiian"},
    {"code": "Frontier", "label": "Frontier Airlines", "keywords": "F9 Frontier"},
    {"code": "Spirit", "label": "Spirit Airlines", "keywords": "NK Spirit"},
    {"code": "Sun Country", "label": "Sun Country", "keywords": "SY Sun Country"},
]

AIRPORT_CODES = {item["code"] for item in SUPPORTED_AIRPORTS}
AIRLINE_CODES = {item["code"] for item in SUPPORTED_AIRLINES}
AIRPORT_LABELS = {item["code"]: item["label"] for item in SUPPORTED_AIRPORTS}
AIRLINE_FULL_LABELS = {item["code"]: item["label"] for item in SUPPORTED_AIRLINES}
AIRLINE_ALIASES = {
    "as": "Alaska",
    "alaska": "Alaska",
    "alaska airlines": "Alaska",
    "aa": "American",
    "american": "American",
    "american airlines": "American",
    "dl": "Delta",
    "delta": "Delta",
    "delta air lines": "Delta",
    "delta airlines": "Delta",
    "b6": "JetBlue",
    "jetblue": "JetBlue",
    "jetblue airways": "JetBlue",
    "wn": "Southwest",
    "southwest": "Southwest",
    "southwest airlines": "Southwest",
    "ua": "United",
    "united": "United",
    "united airlines": "United",
    "ha": "Hawaiian",
    "hawaiian": "Hawaiian",
    "hawaiian airlines": "Hawaiian",
    "f9": "Frontier",
    "frontier": "Frontier",
    "frontier airlines": "Frontier",
    "nk": "Spirit",
    "spirit": "Spirit",
    "spirit airlines": "Spirit",
    "sy": "Sun Country",
    "sun country": "Sun Country",
}


def airport_options() -> list[dict[str, str]]:
    return [
        {
            "value": item["code"],
            "label": item["label"],
            "keywords": item.get("keywords", ""),
        }
        for item in SUPPORTED_AIRPORTS
    ]


def airline_options() -> list[dict[str, str]]:
    return [
        {
            "value": item["code"],
            "label": item["code"],
            "keywords": " ".join(
                part
                for part in [item["code"], item["label"], item.get("keywords", "")]
                if part
            ),
        }
        for item in SUPPORTED_AIRLINES
    ]


def normalize_airport_code(value: str) -> str:
    airport = value.strip().upper()
    if airport not in AIRPORT_CODES:
        raise ValueError("Choose a supported airport.")
    return airport


def normalize_airline_code(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Choose a supported airline.")
    alias = AIRLINE_ALIASES.get(normalized.lower(), normalized)
    if alias not in AIRLINE_CODES:
        raise ValueError("Choose a supported airline.")
    return alias


def airport_label(code: str) -> str:
    normalized = normalize_airport_code(code)
    return AIRPORT_LABELS[normalized]


def airline_label(code: str) -> str:
    normalized = normalize_airline_code(code)
    return normalized


def airport_display(code: str) -> str:
    return f"{normalize_airport_code(code)} · {airport_label(code)}"


def airline_display(code: str) -> str:
    return airline_label(code)


def catalogs_json() -> str:
    payload = {
        "airports": airport_options(),
        "airlines": airline_options(),
        "weekdays": WEEKDAYS,
        "tripKinds": [
            {"value": "one_time", "label": "One-time"},
            {"value": "weekly", "label": "Weekly"},
        ],
    }
    return json.dumps(payload)
