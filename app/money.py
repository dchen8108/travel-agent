from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Iterable


MONEY_QUANTUM = Decimal("0.01")
MONEY_WITH_DOLLAR_RE = re.compile(r"\$\s*(-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)")
MONEY_DECIMAL_RE = re.compile(r"(?<![\d#])-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{1,2}(?!\d)")


def parse_money(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, float):
        amount = Decimal(str(value))
    else:
        text = str(value).strip()
        if not text:
            return None
        cleaned = text.replace("$", "").replace(",", "")
        try:
            amount = Decimal(cleaned)
        except InvalidOperation:
            return None
    return amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def format_money(value: object) -> str:
    amount = parse_money(value)
    if amount is None:
        return "—"
    if amount == amount.to_integral():
        return f"${int(amount)}"
    return f"${amount:.2f}"


def extract_money_amounts(text: str) -> list[Decimal]:
    amounts: list[Decimal] = []
    seen: set[Decimal] = set()
    for match in MONEY_WITH_DOLLAR_RE.finditer(text):
        parsed = parse_money(match.group(1))
        if parsed is not None:
            amounts.append(parsed)
            seen.add(parsed)
    for match in MONEY_DECIMAL_RE.finditer(text):
        parsed = parse_money(match.group(0))
        if parsed is not None and parsed not in seen:
            amounts.append(parsed)
            seen.add(parsed)
    return amounts


def normalize_extracted_total_price(raw_value: object, *, context_texts: Iterable[str] = ()) -> Decimal | None:
    amount = parse_money(raw_value)
    if amount is None:
        return None

    context_amounts: list[Decimal] = []
    for text in context_texts:
        context_amounts.extend(extract_money_amounts(text or ""))
    context_amounts = list(dict.fromkeys(context_amounts))

    if any(candidate == amount for candidate in context_amounts):
        return amount

    rounded_candidates = [
        candidate
        for candidate in context_amounts
        if amount == candidate.to_integral_value(rounding=ROUND_HALF_UP)
        and abs(candidate - amount) < Decimal("1.00")
    ]
    if len(rounded_candidates) == 1:
        return rounded_candidates[0]

    if amount >= Decimal("1000"):
        cents_interpretation = (amount / Decimal("100")).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        if any(candidate == cents_interpretation for candidate in context_amounts):
            return cents_interpretation
        if len(context_amounts) >= 2:
            if sum(context_amounts, start=Decimal("0")).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP) == cents_interpretation:
                return cents_interpretation

    return amount
