from __future__ import annotations

import json

from app.models.base import ProgramWeekday, TripMode

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
    {"code": "Alaska", "label": "Alaska Airlines", "keywords": "AS"},
    {"code": "American", "label": "American Airlines", "keywords": "AA"},
    {"code": "Delta", "label": "Delta Air Lines", "keywords": "DL"},
    {"code": "JetBlue", "label": "JetBlue", "keywords": "B6"},
    {"code": "Southwest", "label": "Southwest Airlines", "keywords": "WN"},
    {"code": "United", "label": "United Airlines", "keywords": "UA"},
    {"code": "Hawaiian", "label": "Hawaiian Airlines", "keywords": "HA"},
    {"code": "Frontier", "label": "Frontier Airlines", "keywords": "F9"},
    {"code": "Spirit", "label": "Spirit Airlines", "keywords": "NK"},
    {"code": "Sun Country", "label": "Sun Country", "keywords": "SY"},
]

FARE_PREFERENCES = [
    {"value": "flexible", "label": "Flexible / travel credit"},
    {"value": "main", "label": "Main cabin or better"},
    {"value": "any", "label": "Any fare"},
    {"value": "best_value", "label": "Best value"},
    {"value": "lowest_price", "label": "Lowest price"},
    {"value": "nonstop", "label": "Nonstop-focused"},
]

TRIP_MODE_OPTIONS = [
    {"value": TripMode.ONE_WAY, "label": "One-way"},
    {"value": TripMode.ROUND_TRIP, "label": "Round-trip"},
]

WEEKDAY_OPTIONS = [weekday.value for weekday in ProgramWeekday]


def airport_codes() -> set[str]:
    return {item["code"] for item in SUPPORTED_AIRPORTS}


def airline_codes() -> set[str]:
    return {item["code"] for item in SUPPORTED_AIRLINES}


def fare_preference_values() -> set[str]:
    return {item["value"] for item in FARE_PREFERENCES}


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
            "label": item["label"],
            "keywords": item.get("keywords", ""),
        }
        for item in SUPPORTED_AIRLINES
    ]


def catalogs_json() -> str:
    payload = {
        "airports": airport_options(),
        "airlines": airline_options(),
        "farePreferences": FARE_PREFERENCES,
        "tripModes": TRIP_MODE_OPTIONS,
        "weekdays": WEEKDAY_OPTIONS,
    }
    return json.dumps(payload)
