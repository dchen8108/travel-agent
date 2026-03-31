from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from email import policy
from email.parser import BytesParser
from pathlib import Path
import re
from typing import Iterable


MARKET_HEADER_RE = re.compile(
    r"(?P<route>[A-Za-z][A-Za-z .'-]+ to [A-Za-z][A-Za-z .'-]+)\r?\n"
    r"(?P<display_date>[A-Za-z]{3}, [A-Za-z]{3} \d{1,2})\r?\n"
    r"One way · (?P<cabin>.+?) · (?P<adult_count>\d+ adult(?:s)?)\r?\n"
    r"(?P<market_url>https://www\.google\.com/travel/flights\?[^\r\n]+)",
    re.MULTILINE,
)

TRACKED_FLIGHT_RE = re.compile(
    r"(?P<time_line>[0-9:]+\s*[AP]M(?:\s*–\s*[0-9:]+\s*[AP]M(?:\+1)?)?)\r?\n"
    r"(?P<detail_line>[^\r\n]+)\r?\n"
    r"\$(?P<price>\d+)\s+\((?P<delta_text>[^)]+)\)\r?\n"
    r"(?P<flight_url>https://www\.google\.com/travel/flights\?[^\r\n]+)",
    re.MULTILINE,
)

AIRPORT_PAIR_RE = re.compile(r"(?P<origin>[A-Z]{3})[–-](?P<destination>[A-Z]{3})")
PRICE_DELTA_RE = re.compile(r"(?P<direction>dropped|increased) from \$(?P<previous>\d+)")


@dataclass(frozen=True)
class ParsedGoogleFlightsSection:
    route_text: str
    travel_date: date
    cabin_text: str
    adult_count_text: str
    market_url: str


@dataclass(frozen=True)
class ParsedGoogleFlightsObservation:
    route_text: str
    travel_date: date
    airline: str
    origin_airport: str | None
    destination_airport: str | None
    price: int
    previous_price: int | None
    price_direction: str | None
    is_nonstop: bool | None
    time_line: str
    detail_line: str
    flight_url: str


@dataclass(frozen=True)
class ParsedGoogleFlightsEmail:
    message_id: str
    subject: str
    received_at: datetime
    plain_text: str
    html_text: str | None
    sections: list[ParsedGoogleFlightsSection]
    observations: list[ParsedGoogleFlightsObservation]

    @property
    def raw_excerpt(self) -> str:
        return self.plain_text[:500]


def _extract_body_text(message) -> tuple[str, str | None]:
    plain_text = ""
    html_text = None
    for part in message.walk():
        if part.get_content_type() == "text/plain" and not plain_text:
            plain_text = part.get_content()
        elif part.get_content_type() == "text/html" and html_text is None:
            html_text = part.get_content()
    if not plain_text:
        raise ValueError("Google Flights email did not contain a text/plain body")
    return plain_text, html_text


def _derive_year(received_at: datetime, display_date: str) -> date:
    parsed = datetime.strptime(display_date, "%a, %b %d")
    candidate = date(received_at.year, parsed.month, parsed.day)
    if (candidate - received_at.date()).days < -180:
        candidate = date(received_at.year + 1, parsed.month, parsed.day)
    return candidate


def _parse_sections(plain_text: str, received_at: datetime) -> list[ParsedGoogleFlightsSection]:
    sections: list[ParsedGoogleFlightsSection] = []
    for match in MARKET_HEADER_RE.finditer(plain_text):
        sections.append(
            ParsedGoogleFlightsSection(
                route_text=match.group("route").strip(),
                travel_date=_derive_year(received_at, match.group("display_date")),
                cabin_text=match.group("cabin").strip(),
                adult_count_text=match.group("adult_count").strip(),
                market_url=match.group("market_url").strip(),
            )
        )
    return sections


def _iter_section_blocks(plain_text: str) -> Iterable[str]:
    section_starts = [m.start() for m in MARKET_HEADER_RE.finditer(plain_text)]
    if not section_starts:
        return []
    section_starts.append(len(plain_text))
    blocks: list[str] = []
    for idx, start in enumerate(section_starts[:-1]):
        end = section_starts[idx + 1]
        blocks.append(plain_text[start:end])
    return blocks


def _parse_observations(block: str, fallback_route: str, travel_date: date) -> list[ParsedGoogleFlightsObservation]:
    observations: list[ParsedGoogleFlightsObservation] = []
    for match in TRACKED_FLIGHT_RE.finditer(block):
        detail_line = match.group("detail_line").strip()
        airport_pair = AIRPORT_PAIR_RE.search(detail_line)
        delta_match = PRICE_DELTA_RE.search(match.group("delta_text"))
        observations.append(
            ParsedGoogleFlightsObservation(
                route_text=fallback_route,
                travel_date=travel_date,
                airline=detail_line.split("·", 1)[0].strip(),
                origin_airport=airport_pair.group("origin") if airport_pair else None,
                destination_airport=airport_pair.group("destination") if airport_pair else None,
                price=int(match.group("price")),
                previous_price=int(delta_match.group("previous")) if delta_match else None,
                price_direction=delta_match.group("direction") if delta_match else None,
                is_nonstop=parse_nonstop(detail_line),
                time_line=match.group("time_line").strip(),
                detail_line=detail_line,
                flight_url=match.group("flight_url").strip(),
            )
        )
    return observations


def parse_nonstop(detail_line: str) -> bool | None:
    normalized = detail_line.lower()
    if "nonstop" in normalized:
        return True
    if re.search(r"\b\d+\s+stop(?:s)?\b", normalized):
        return False
    if "1 stop" in normalized or "2 stops" in normalized or "stopover" in normalized:
        return False
    return None


def _parse_google_flights_message(message) -> ParsedGoogleFlightsEmail:
    plain_text, html_text = _extract_body_text(message)
    received_at = message["Date"].datetime
    sections = _parse_sections(plain_text, received_at)

    observations: list[ParsedGoogleFlightsObservation] = []
    if sections:
        for section, block in zip(sections, _iter_section_blocks(plain_text)):
            observations.extend(_parse_observations(block, section.route_text, section.travel_date))

    return ParsedGoogleFlightsEmail(
        message_id=str(message["Message-ID"] or ""),
        subject=str(message["Subject"] or "Google Flights price update"),
        received_at=received_at,
        plain_text=plain_text,
        html_text=html_text,
        sections=sections,
        observations=observations,
    )


def parse_google_flights_email_bytes(payload: bytes) -> ParsedGoogleFlightsEmail:
    message = BytesParser(policy=policy.default).parsebytes(payload)
    return _parse_google_flights_message(message)


def parse_google_flights_email(path: Path) -> ParsedGoogleFlightsEmail:
    message = BytesParser(policy=policy.default).parse(path.open("rb"))
    return _parse_google_flights_message(message)


ParsedObservation = ParsedGoogleFlightsObservation
ParsedEmail = ParsedGoogleFlightsEmail
