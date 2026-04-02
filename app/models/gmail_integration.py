from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GmailIntegrationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    inbox_label_ids: list[str] = Field(default_factory=lambda: ["INBOX"])
    max_messages_per_poll: int = 20
    booking_keywords: list[str] = Field(
        default_factory=lambda: [
            "booking",
            "confirmation",
            "confirmation code",
            "e-ticket",
            "flight",
            "itinerary",
            "record locator",
            "reservation",
            "ticket",
        ]
    )
    spam_keywords: list[str] = Field(
        default_factory=lambda: [
            "bonus miles",
            "deal",
            "newsletter",
            "promotion",
            "sale",
            "unsubscribe",
        ]
    )
    model: str = "gpt-5.4"
    min_auto_create_confidence: float = 0.85

    @field_validator("max_messages_per_poll")
    @classmethod
    def validate_message_limit(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_messages_per_poll must be at least 1.")
        return value

    @field_validator("min_auto_create_confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("min_auto_create_confidence must be between 0 and 1.")
        return value
