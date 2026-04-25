from __future__ import annotations

from decimal import Decimal
import re
from typing import Literal

from openai import APIConnectionError, APIStatusError, APITimeoutError, BadRequestError, OpenAI, OpenAIError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.catalog import normalize_stop_value
from app.flight_numbers import join_flight_numbers
from app.money import normalize_extracted_total_price
from app.settings import Settings
from app.services.runtime_secrets import openai_api_key


class BookingEmailLeg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    airline: str = ""
    origin_airport: str = ""
    destination_airport: str = ""
    departure_date: str = ""
    departure_time: str = ""
    arrival_time: str = ""
    arrival_day_offset: int = 0
    flight_number: str = ""
    leg_status: Literal["booked", "changed", "cancelled", "unknown"] = "booked"
    fare_class: Literal["basic", "main", "unknown"] = "unknown"
    evidence: str = ""

    @field_validator("arrival_day_offset")
    @classmethod
    def validate_arrival_day_offset(cls, value: int) -> int:
        if value < 0:
            return 0
        if value > 7:
            return 7
        return value

    @field_validator("flight_number", mode="before")
    @classmethod
    def normalize_flight_number(cls, value: object) -> str:
        return join_flight_numbers(value)


class BookingEmailSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    airline: str = ""
    origin_airport: str = ""
    destination_airport: str = ""
    departure_date: str = ""
    departure_time: str = ""
    arrival_time: str = ""
    arrival_day_offset: int = 0
    stops: str = ""
    flight_number: str = ""
    segment_status: Literal["booked", "changed", "cancelled", "unknown"] = "booked"
    fare_class: Literal["basic", "main", "unknown"] = "unknown"
    evidence: str = ""

    @field_validator("arrival_day_offset")
    @classmethod
    def validate_arrival_day_offset(cls, value: int) -> int:
        if value < 0:
            return 0
        if value > 7:
            return 7
        return value

    @field_validator("stops", mode="before")
    @classmethod
    def normalize_stops(cls, value: object) -> str:
        return normalize_stop_value(value, allow_empty=True)

    @field_validator("flight_number", mode="before")
    @classmethod
    def normalize_flight_number(cls, value: object) -> str:
        return join_flight_numbers(value)


class BookingEmailExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email_kind: Literal[
        "booking_confirmation",
        "itinerary_change",
        "cancellation",
        "not_booking",
        "unknown",
    ] = "unknown"
    confidence: float = 0.0
    record_locator: str = ""
    currency: str = "USD"
    total_price: str = ""
    cash_paid: str = ""
    flight_credits_applied: str = ""
    points_used: int = 0
    passenger_names: list[str] = Field(default_factory=list)
    summary: str = ""
    notes: str = ""
    segments: list[BookingEmailSegment] = Field(default_factory=list)
    legs: list[BookingEmailLeg] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if value < 0:
            return 0.0
        if value > 1:
            return 1.0
        return value

    @field_validator("total_price", mode="before")
    @classmethod
    def normalize_total_price(cls, value: object) -> str:
        if value in (None, ""):
            return ""
        return str(value).strip()

    @field_validator("cash_paid", "flight_credits_applied", mode="before")
    @classmethod
    def normalize_money_component(cls, value: object) -> str:
        if value in (None, ""):
            return ""
        return str(value).strip()

    @field_validator("points_used", mode="before")
    @classmethod
    def normalize_points_used(cls, value: object) -> int:
        if value in (None, ""):
            return 0
        text = str(value).strip().replace(",", "")
        if not text:
            return 0
        try:
            parsed = int(text)
        except ValueError:
            return 0
        return max(0, parsed)

    def total_price_amount(self) -> Decimal | None:
        return normalize_extracted_total_price(
            self.total_price,
            context_texts=[
                self.summary,
                self.notes,
                *(segment.evidence for segment in self.segments),
                *(leg.evidence for leg in self.legs),
            ],
        )

    def cash_paid_amount(self) -> Decimal | None:
        return normalize_extracted_total_price(
            self.cash_paid,
            context_texts=[
                self.summary,
                self.notes,
                *(segment.evidence for segment in self.segments),
                *(leg.evidence for leg in self.legs),
            ],
        )

    def flight_credits_amount(self) -> Decimal | None:
        return normalize_extracted_total_price(
            self.flight_credits_applied,
            context_texts=[
                self.summary,
                self.notes,
                *(segment.evidence for segment in self.segments),
                *(leg.evidence for leg in self.legs),
            ],
        )

    def points_value_amount(self) -> Decimal:
        return (Decimal(self.points_used) / Decimal("100")).quantize(Decimal("0.01"))

    def effective_total_price_amount(self) -> Decimal | None:
        explicit_total = self.total_price_amount()
        cash_paid = self.cash_paid_amount()
        credits_applied = self.flight_credits_amount()
        points_value = self.points_value_amount() if self.points_used > 0 else Decimal("0")
        if cash_paid is not None or credits_applied is not None or self.points_used > 0:
            effective_total = (cash_paid or Decimal("0")) + (credits_applied or Decimal("0")) + points_value
            if effective_total > Decimal("0"):
                return effective_total
            return explicit_total
        if explicit_total is not None:
            return explicit_total
        return cash_paid


class BookingExtractionError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


SYSTEM_PROMPT = """You extract structured flight booking information from emails.

Rules:
- Only classify real flight booking confirmations, itinerary changes, or cancellations.
- If the email is marketing, spam, points promotions, newsletters, or unrelated travel content, set email_kind to not_booking.
- Normalize airline to the carrier code if clearly stated (AS, WN, DL, UA, AA, B6, HA, VX, NK, F9). Otherwise return the best short airline identifier you can infer.
- Normalize airports to 3-letter IATA codes when clearly stated.
- Use ISO dates YYYY-MM-DD.
- Use 24-hour times HH:MM in the local time shown in the email.
- Do not guess unknown fields. Use empty strings or null.
- segments are the app-level booked flight units that should be stored in the app.
- Collapse connecting itineraries into one segment from first origin to final destination.
- For round trips or clearly separate booked journeys, create separate segments.
- Example: BUR -> SFO -> SEA on one outbound itinerary is one segment with origin_airport BUR, destination_airport SEA, and stops 1_stop.
- Example: LAX -> SFO outbound and SFO -> LAX return should be two separate segments.
- segments.stops must be one of: nonstop, 1_stop, 2_stops. Use 2_stops for 2 or more stops.
- segments.arrival_day_offset should capture whether the final arrival is on the same day (0), next day (1), or later. Do not rely only on clock comparison when time zones differ.
- If the itinerary contains multiple physical flight legs, include every leg in legs as well.
- For multi-leg segments, set flight_number to all flight designators in travel order joined by " | " when they are clearly stated, for example "AS 1484 | AS 530". If the flight designators are not clear, leave it empty.
- For multi-leg segments, if every leg clearly has the same fare family, set segment fare_class to that shared value. If the legs are mixed or ambiguous, use unknown.
- cash_paid should be the final cash charged in USD, preserving cents, like "5.60". If there was no cash charge, return "0" or an empty string.
- flight_credits_applied should be the total USD flight credit or voucher amount applied across all credits, preserving cents, like "50.00". If multiple credits were used, sum them. If none, return "0" or an empty string.
- points_used should be the total loyalty points redeemed as an integer, like 5500. If none, return 0.
- total_price should be the effective itinerary total in USD, including cash paid, flight credits applied, and points valued at 1 cent each. If unknown, return an empty string.
- confidence should reflect extraction reliability, not whether the email is desirable.
"""

BOOKING_RELEVANCE_MARKERS: tuple[str, ...] = (
    "confirmation",
    "confirmation code",
    "record locator",
    "reservation",
    "itinerary",
    "flight",
    "depart",
    "arriv",
    "passenger",
    "traveler",
    "booking",
    "ticket",
    "fare",
    "total",
    "receipt",
    "baggage",
    "cancel",
    "change",
    "nonstop",
    "stop",
    "layover",
    "connection",
    "points",
    "point",
    "credit",
    "credits",
    "voucher",
)


def prepare_booking_email_body(body_text: str, *, max_chars: int) -> str:
    normalized_lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in body_text.replace("\r", "").splitlines()
    ]
    normalized_lines = [line for line in normalized_lines if line]
    if not normalized_lines:
        return ""

    def add_line(line: str, selected: list[str], seen: set[str]) -> None:
        if line in seen:
            return
        seen.add(line)
        selected.append(line)

    selected_priority: list[str] = []
    selected_context: list[str] = []
    seen: set[str] = set()

    for index, line in enumerate(normalized_lines):
        lowered = line.lower()
        if any(marker in lowered for marker in BOOKING_RELEVANCE_MARKERS):
            for neighbor in normalized_lines[max(0, index - 1): min(len(normalized_lines), index + 2)]:
                add_line(neighbor, selected_priority, seen)
            continue
        if re.search(r"\b[A-Z]{3}\b", line):
            for neighbor in normalized_lines[max(0, index - 1): min(len(normalized_lines), index + 2)]:
                add_line(neighbor, selected_priority, seen)
            continue
        if re.search(r"\$\s*\d", line):
            for neighbor in normalized_lines[max(0, index - 1): min(len(normalized_lines), index + 2)]:
                add_line(neighbor, selected_priority, seen)
            continue
        if re.search(r"\b\d{1,2}:\d{2}\b", line):
            for neighbor in normalized_lines[max(0, index - 1): min(len(normalized_lines), index + 2)]:
                add_line(neighbor, selected_priority, seen)
            continue

    for line in normalized_lines[:24]:
        add_line(line, selected_context, seen)

    selected = selected_priority + selected_context
    prepared = "\n".join(selected) if selected else "\n".join(normalized_lines[:40])
    if len(prepared) <= max_chars:
        return prepared

    trimmed_lines: list[str] = []
    current_length = 0
    for line in selected:
        candidate_length = current_length + len(line) + (1 if trimmed_lines else 0)
        if candidate_length > max_chars:
            break
        trimmed_lines.append(line)
        current_length = candidate_length
    prepared = "\n".join(trimmed_lines)
    if prepared:
        return prepared
    return "\n".join(normalized_lines)[:max_chars]


def extract_booking_email(
    *,
    settings: Settings,
    model: str,
    from_address: str,
    subject: str,
    body_text: str,
    max_body_chars: int,
    prepared_body_text: str | None = None,
) -> BookingEmailExtraction:
    api_key = openai_api_key(settings)
    if not api_key:
        raise BookingExtractionError(
            "OPENAI_API_KEY is not configured. Set it in the environment or config/local/openai_api_key.txt.",
            retryable=False,
        )

    client = OpenAI(api_key=api_key)
    prepared_body = prepared_body_text if prepared_body_text is not None else prepare_booking_email_body(
        body_text,
        max_chars=max_body_chars,
    )
    try:
        response = client.responses.parse(
            model=model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Parse this email into the schema.\n\n"
                        f"From: {from_address}\n"
                        f"Subject: {subject}\n\n"
                        f"{prepared_body}"
                    ),
                },
            ],
            text_format=BookingEmailExtraction,
        )
    except (APIConnectionError, APITimeoutError) as exc:
        raise BookingExtractionError(str(exc), retryable=True) from exc
    except BadRequestError as exc:
        raise BookingExtractionError(str(exc), retryable=False) from exc
    except APIStatusError as exc:
        retryable = exc.status_code in {408, 409, 425, 429, 500, 502, 503, 504}
        raise BookingExtractionError(str(exc), retryable=retryable) from exc
    except OpenAIError as exc:
        raise BookingExtractionError(str(exc), retryable=False) from exc
    if response.output_parsed is None:
        raise BookingExtractionError(
            "The extraction model did not return structured booking output.",
            retryable=False,
        )
    return response.output_parsed
