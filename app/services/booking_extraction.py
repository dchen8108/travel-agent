from __future__ import annotations

from decimal import Decimal
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    flight_number: str = ""
    leg_status: Literal["booked", "changed", "cancelled", "unknown"] = "booked"
    fare_class: Literal["basic", "main", "unknown"] = "unknown"
    evidence: str = ""


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
    passenger_names: list[str] = Field(default_factory=list)
    summary: str = ""
    notes: str = ""
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

    def total_price_amount(self) -> Decimal | None:
        return normalize_extracted_total_price(
            self.total_price,
            context_texts=[self.summary, self.notes, *(leg.evidence for leg in self.legs)],
        )


SYSTEM_PROMPT = """You extract structured flight booking information from emails.

Rules:
- Only classify real flight booking confirmations, itinerary changes, or cancellations.
- If the email is marketing, spam, points promotions, newsletters, or unrelated travel content, set email_kind to not_booking.
- Normalize airline to the carrier code if clearly stated (AS, WN, DL, UA, AA, B6, HA, VX, NK, F9). Otherwise return the best short airline identifier you can infer.
- Normalize airports to 3-letter IATA codes when clearly stated.
- Use ISO dates YYYY-MM-DD.
- Use 24-hour times HH:MM in the local time shown in the email.
- Do not guess unknown fields. Use empty strings or null.
- If the itinerary contains multiple flight legs, include every leg.
- total_price should be the itinerary total in USD as a string amount that preserves cents, like "78.40". If unknown, return an empty string.
- confidence should reflect extraction reliability, not whether the email is desirable.
"""


def extract_booking_email(
    *,
    settings: Settings,
    model: str,
    from_address: str,
    subject: str,
    body_text: str,
) -> BookingEmailExtraction:
    api_key = openai_api_key(settings)
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. Set it in the environment or config/local/openai_api_key.txt."
        )

    client = OpenAI(api_key=api_key)
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
                    f"{body_text}"
                ),
            },
        ],
        text_format=BookingEmailExtraction,
    )
    if response.output_parsed is None:
        raise RuntimeError("The extraction model did not return structured booking output.")
    return response.output_parsed
