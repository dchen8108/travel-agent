from __future__ import annotations

from decimal import Decimal

from app.money import format_money, normalize_extracted_total_price


def test_normalize_extracted_total_price_recovers_cents_from_summary() -> None:
    amount = normalize_extracted_total_price(
        7840,
        context_texts=["Total paid $78.40 USD."],
    )

    assert amount == Decimal("78.40")


def test_normalize_extracted_total_price_prefers_explicit_redemption_cash_component() -> None:
    amount = normalize_extracted_total_price(
        6,
        context_texts=["Payment: 5,500 pts + $5.60."],
    )

    assert amount == Decimal("5.60")


def test_format_money_omits_zero_cents_for_whole_dollars() -> None:
    assert format_money(85) == "$85"
    assert format_money(Decimal("78.40")) == "$78.40"
