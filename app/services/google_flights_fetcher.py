from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

import httpx
from selectolax.lexbor import LexborHTMLParser

from app.route_options import time_in_window


GOOGLE_FLIGHTS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

NO_RESULTS_MARKERS = (
    "no flights",
    "no matching flights",
    "no trips match",
    "try changing",
)


@dataclass(frozen=True)
class GoogleFlightsOffer:
    airline: str
    departure_label: str
    arrival_label: str
    price: int
    price_text: str

    @property
    def summary(self) -> str:
        details = [self.airline]
        if self.departure_label and self.arrival_label:
            details.append(f"{self.departure_label} → {self.arrival_label}")
        details.append(self.price_text)
        return " · ".join(details)


class GoogleFlightsFetchError(RuntimeError):
    pass


class GoogleFlightsNoResultsError(GoogleFlightsFetchError):
    pass


class GoogleFlightsNoWindowMatchError(GoogleFlightsFetchError):
    pass


def fetch_google_flights_offers(
    url: str,
    *,
    client: httpx.Client | None = None,
    timeout: float = 20.0,
) -> list[GoogleFlightsOffer]:
    owns_client = client is None
    http_client = client or httpx.Client(headers=GOOGLE_FLIGHTS_HEADERS, timeout=timeout, follow_redirects=True)
    try:
        response = http_client.get(url, headers=GOOGLE_FLIGHTS_HEADERS)
    finally:
        if owns_client:
            http_client.close()
    if response.status_code != 200:
        raise GoogleFlightsFetchError(f"Google Flights returned {response.status_code}.")
    return parse_google_flights_offers(response.text)


def parse_google_flights_offers(html: str) -> list[GoogleFlightsOffer]:
    parser = LexborHTMLParser(html)
    offers: list[GoogleFlightsOffer] = []
    rows = parser.css('div[jsname="IWWDBc"], div[jsname="YdtKid"]')
    for row_index, row in enumerate(rows):
        items = row.css("ul.Rk10dc li")
        if row_index > 0 and len(items) > 1:
            items = items[:-1]
        for item in items:
            airline_node = item.css_first("div.sSHqwe.tPgKwe.ogfYpf span")
            price_node = item.css_first(".YMlIz.FpEdX")
            time_nodes = item.css("span.mv1WYe div")
            airline = airline_node.text(strip=True) if airline_node else ""
            price_text = price_node.text(strip=True) if price_node else ""
            price = parse_google_flights_price(price_text)
            if price is None or not airline:
                continue
            departure_label = time_nodes[0].text(strip=True) if len(time_nodes) > 0 else ""
            arrival_label = time_nodes[1].text(strip=True) if len(time_nodes) > 1 else ""
            offers.append(
                GoogleFlightsOffer(
                    airline=airline,
                    departure_label=departure_label,
                    arrival_label=arrival_label,
                    price=price,
                    price_text=price_text,
                )
            )
    if not offers:
        lowered_html = html.lower()
        if any(marker in lowered_html for marker in NO_RESULTS_MARKERS):
            raise GoogleFlightsNoResultsError("No flight prices found in the Google Flights response.")
        raise GoogleFlightsFetchError("Could not parse flight prices from the Google Flights response.")
    return offers


def parse_google_flights_price(value: str) -> int | None:
    digits = re.sub(r"[^\d]", "", value or "")
    if not digits:
        return None
    return int(digits)


def best_google_flights_offer(offers: list[GoogleFlightsOffer]) -> GoogleFlightsOffer | None:
    if not offers:
        return None
    return min(offers, key=lambda item: (item.price, item.airline, item.departure_label, item.arrival_label))


def departure_time_for_offer(offer: GoogleFlightsOffer) -> str | None:
    return departure_time_from_offer_label(offer.departure_label)


def departure_time_from_offer_label(label: str) -> str | None:
    if not label:
        return None
    first_part = label.split(" on ", 1)[0].strip()
    for time_format in ("%I:%M %p", "%I %p"):
        try:
            parsed = datetime.strptime(first_part, time_format)
            return parsed.strftime("%H:%M")
        except ValueError:
            continue
    match = re.search(r"(\d{1,2}(?::\d{2})?\s*[AP]M)", first_part, flags=re.IGNORECASE)
    if not match:
        return None
    normalized = match.group(1).upper().replace("  ", " ").strip()
    for time_format in ("%I:%M %p", "%I %p"):
        try:
            parsed = datetime.strptime(normalized, time_format)
            return parsed.strftime("%H:%M")
        except ValueError:
            continue
    return None


def filter_google_flights_offers_by_departure_window(
    offers: list[GoogleFlightsOffer],
    *,
    start_time: str,
    end_time: str,
) -> list[GoogleFlightsOffer]:
    return [
        offer
        for offer in offers
        if time_in_window(start_time, end_time, departure_time_for_offer(offer))
    ]


def now_utc() -> datetime:
    return datetime.now().astimezone()
