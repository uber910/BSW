from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_TWO_PLACES = Decimal("0.01")


def quantize_coefficient(value: Decimal) -> Decimal:
    """Normalise coefficient to exactly two decimal places.

    Pydantic v2 `decimal_places=2` validates upper bound only — `Decimal("10")`
    passes but serialises as `"10"` not `"10.00"`. The spec requires exactly two
    decimal places; we accept `"10"` and quantize-on-input. Used by
    EventCreate.coefficient and EventUpdate.coefficient (after-validators).
    """
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
