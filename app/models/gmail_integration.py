from __future__ import annotations

from email.utils import parseaddr

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GmailIntegrationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    inbox_label_ids: list[str] = Field(default_factory=lambda: ["INBOX"])
    allowed_from_addresses: list[str] = Field(default_factory=list)
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
    max_body_chars: int = 12000
    max_retry_attempts: int = 2
    min_auto_create_confidence: float = 0.85
    launchd_poll_interval_seconds: int = 180
    launchd_max_messages: int = 10
    debug_log_model_io: bool = False

    @field_validator("max_messages_per_poll")
    @classmethod
    def validate_message_limit(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_messages_per_poll must be at least 1.")
        return value

    @field_validator("allowed_from_addresses")
    @classmethod
    def normalize_allowed_from_addresses(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            raw = value.strip()
            if not raw:
                continue
            _name, address = parseaddr(raw)
            candidate = (address or raw).strip().lower()
            if not candidate:
                continue
            if "@" not in candidate:
                raise ValueError("allowed_from_addresses must contain email addresses.")
            if candidate in seen:
                continue
            seen.add(candidate)
            normalized.append(candidate)
        return normalized

    @field_validator("max_body_chars")
    @classmethod
    def validate_max_body_chars(cls, value: int) -> int:
        if value < 1000:
            raise ValueError("max_body_chars must be at least 1000.")
        return value

    @field_validator("max_retry_attempts")
    @classmethod
    def validate_max_retry_attempts(cls, value: int) -> int:
        if value < 0:
            raise ValueError("max_retry_attempts must be at least 0.")
        return value

    @field_validator("launchd_poll_interval_seconds", "launchd_max_messages")
    @classmethod
    def validate_positive_runtime_values(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Runtime values must be at least 1.")
        return value

    @field_validator("min_auto_create_confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("min_auto_create_confidence must be between 0 and 1.")
        return value
