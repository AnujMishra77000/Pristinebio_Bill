from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class FinancialValidationError(ValueError):
    """Raised when billing input cannot be represented safely in storage."""


QUANTITY_SCALE = 3
RATE_SCALE = 4
MONEY_SCALE = 2
TAX_RATE_SCALE = 2


def _quantum(scale: int) -> Decimal:
    return Decimal(1).scaleb(-scale)


def normalize_decimal(
    value: Decimal,
    field_name: str,
    *,
    scale: int,
    precision: int = 14,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
) -> Decimal:
    if not isinstance(value, Decimal):
        try:
            value = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise FinancialValidationError(f"{field_name} must be a valid decimal") from exc
    if not value.is_finite():
        raise FinancialValidationError(f"{field_name} must be finite")

    quantum = _quantum(scale)
    try:
        normalized = value.quantize(quantum, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise FinancialValidationError(f"{field_name} is too large for billing storage") from exc

    if normalized != value:
        raise FinancialValidationError(
            f"{field_name} supports at most {scale} decimal places"
        )

    integer_digits = precision - scale
    storage_maximum = (Decimal(10) ** integer_digits) - quantum
    if abs(normalized) > storage_maximum:
        raise FinancialValidationError(f"{field_name} is too large for billing storage")
    if minimum is not None and normalized < minimum:
        raise FinancialValidationError(f"{field_name} must be at least {minimum}")
    if maximum is not None and normalized > maximum:
        raise FinancialValidationError(f"{field_name} must be at most {maximum}")
    return normalized


def normalize_quantity(value: Decimal, field_name: str = "Quantity") -> Decimal:
    return normalize_decimal(
        value,
        field_name,
        scale=QUANTITY_SCALE,
        minimum=Decimal("0.001"),
    )


def normalize_rate(value: Decimal, field_name: str = "Rate") -> Decimal:
    return normalize_decimal(value, field_name, scale=RATE_SCALE, minimum=Decimal("0"))


def normalize_money(value: Decimal, field_name: str = "Amount") -> Decimal:
    return normalize_decimal(value, field_name, scale=MONEY_SCALE, minimum=Decimal("0"))


def normalize_tax_rate(value: Decimal, field_name: str = "Tax rate") -> Decimal:
    return normalize_decimal(
        value,
        field_name,
        scale=TAX_RATE_SCALE,
        precision=5,
        minimum=Decimal("0"),
        maximum=Decimal("100.00"),
    )


def required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


def optional_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text")
    value = value.strip()
    return value or None


def state_code(value: str, field_name: str = "State code") -> str:
    normalized = required_text(value, field_name)
    if len(normalized) != 2 or not normalized.isdigit() or normalized == "00":
        raise ValueError(f"{field_name} must be a valid two-digit code")
    return normalized
