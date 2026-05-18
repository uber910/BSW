from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_TWO_PLACES = Decimal("0.01")


def quantize_amount(value: Decimal) -> Decimal:
    """Normalise bet amount to exactly two decimal places.

    Pydantic v2 `decimal_places=2` validates upper bound only — `Decimal("10")`
    passes but serialises as `"10"` not `"10.00"`. The spec requires exactly
    two decimal places in BetRead.amount; we accept `"10"` and
    quantize-on-input via AfterValidator on BetCreate.amount.

    ROUND_HALF_UP (not banker's rounding): `Decimal("10.005")` becomes
    `Decimal("10.01")`. This matches the user's monetary intuition.
    """
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
