from decimal import Decimal, InvalidOperation

from .errors import Invalid

TWO = Decimal("0.01")


def parse_money(value, *, positive: bool = True, field: str = "amount") -> Decimal:
    try:
        d = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        raise Invalid(f"{field}: invalid number", code="invalid_amount")
    if not d.is_finite():
        raise Invalid(f"{field}: invalid number", code="invalid_amount")
    if d != d.quantize(TWO):
        raise Invalid(f"{field}: at most 2 decimals", code="too_many_decimals")
    if positive and d <= 0:
        raise Invalid(f"{field}: must be positive", code="amount_not_positive")
    if abs(d) > Decimal("99999999.99"):
        raise Invalid(f"{field}: too large", code="amount_too_large")
    return d.quantize(TWO)


def fmt(d: Decimal | None) -> str | None:
    return None if d is None else format(Decimal(d).quantize(TWO), "f")
