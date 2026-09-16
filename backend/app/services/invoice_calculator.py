from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


MONEY = Decimal("0.01")
RUPEE = Decimal("1")
ZERO = Decimal("0.00")


@dataclass(frozen=True)
class InvoiceCalculationLine:
    description: str
    hsn_sac: str
    quantity: Decimal
    unit: str
    rate: Decimal
    discount_amount: Decimal
    gst_rate: Decimal
    cess_rate: Decimal
    other_charge: Decimal = ZERO


@dataclass(frozen=True)
class InvoiceLineCalculationResult:
    description: str
    hsn_sac: str
    quantity: Decimal
    unit: str
    rate: Decimal
    discount_amount: Decimal
    taxable_value: Decimal
    gst_rate: Decimal
    cess_rate: Decimal
    other_charge: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    line_total: Decimal


@dataclass(frozen=True)
class InvoiceCalculationResult:
    lines: list[InvoiceLineCalculationResult]
    taxable_value: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    unrounded_total: Decimal
    round_off: Decimal
    final_total: Decimal
    amount_in_words: str


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def rupee(value: Decimal) -> Decimal:
    return value.quantize(RUPEE, rounding=ROUND_HALF_UP)


def calculate_invoice(
    *,
    branch_state_code: str,
    place_of_supply_state_code: str,
    lines: list[InvoiceCalculationLine],
    freight_charges: Decimal = ZERO,
    packing_charges: Decimal = ZERO,
    other_charges: Decimal = ZERO,
    discount_amount: Decimal = ZERO,
) -> InvoiceCalculationResult:
    is_intrastate = branch_state_code == place_of_supply_state_code
    calculated_lines: list[InvoiceLineCalculationResult] = []

    for line in lines:
        taxable_value = money((line.quantity * line.rate) + line.other_charge - line.discount_amount)
        cess_amount = money(taxable_value * line.cess_rate / Decimal("100"))
        if is_intrastate:
            cgst_amount = money(taxable_value * (line.gst_rate / Decimal("2")) / Decimal("100"))
            sgst_amount = money(taxable_value * (line.gst_rate / Decimal("2")) / Decimal("100"))
            igst_amount = ZERO
        else:
            cgst_amount = ZERO
            sgst_amount = ZERO
            igst_amount = money(taxable_value * line.gst_rate / Decimal("100"))
        line_total = money(taxable_value + cgst_amount + sgst_amount + igst_amount + cess_amount)
        calculated_lines.append(
            InvoiceLineCalculationResult(
                description=line.description,
                hsn_sac=line.hsn_sac,
                quantity=line.quantity,
                unit=line.unit,
                rate=line.rate,
                other_charge=money(line.other_charge),
                discount_amount=money(line.discount_amount),
                taxable_value=taxable_value,
                gst_rate=line.gst_rate,
                cess_rate=line.cess_rate,
                cgst_amount=cgst_amount,
                sgst_amount=sgst_amount,
                igst_amount=igst_amount,
                cess_amount=cess_amount,
                line_total=line_total,
            )
        )

    line_taxable_total = sum((line.taxable_value for line in calculated_lines), ZERO)
    charges_total = money(freight_charges + packing_charges + other_charges)
    taxable_value = money(line_taxable_total + charges_total - discount_amount)
    taxable_basis = line_taxable_total if line_taxable_total > 0 else Decimal("1")
    weighted_gst_rate = sum((line.taxable_value * line.gst_rate for line in calculated_lines), ZERO) / taxable_basis
    weighted_cess_rate = sum((line.taxable_value * line.cess_rate for line in calculated_lines), ZERO) / taxable_basis

    if is_intrastate:
        cgst_amount = money(taxable_value * (weighted_gst_rate / Decimal("2")) / Decimal("100"))
        sgst_amount = money(taxable_value * (weighted_gst_rate / Decimal("2")) / Decimal("100"))
        igst_amount = ZERO
    else:
        cgst_amount = ZERO
        sgst_amount = ZERO
        igst_amount = money(taxable_value * weighted_gst_rate / Decimal("100"))
    cess_amount = money(taxable_value * weighted_cess_rate / Decimal("100"))

    unrounded_total = money(taxable_value + cgst_amount + sgst_amount + igst_amount + cess_amount)
    final_total = rupee(unrounded_total)
    round_off = money(final_total - unrounded_total)

    return InvoiceCalculationResult(
        lines=calculated_lines,
        taxable_value=taxable_value,
        cgst_amount=cgst_amount,
        sgst_amount=sgst_amount,
        igst_amount=igst_amount,
        cess_amount=cess_amount,
        unrounded_total=unrounded_total,
        round_off=round_off,
        final_total=money(final_total),
        amount_in_words=amount_in_words(int(final_total)),
    )


ONES = [
    "",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _under_hundred(number: int) -> str:
    if number < 20:
        return ONES[number]
    return " ".join(part for part in [TENS[number // 10], ONES[number % 10]] if part)


def _under_thousand(number: int) -> str:
    hundreds, remainder = divmod(number, 100)
    parts = []
    if hundreds:
        parts.append(f"{ONES[hundreds]} Hundred")
    if remainder:
        parts.append(_under_hundred(remainder))
    return " ".join(parts)


def amount_in_words(number: int) -> str:
    if number == 0:
        return "Rupees Zero Only"

    crore, remainder = divmod(number, 10_000_000)
    lakh, remainder = divmod(remainder, 100_000)
    thousand, remainder = divmod(remainder, 1_000)

    parts = []
    if crore:
        parts.append(f"{_under_thousand(crore)} Crore")
    if lakh:
        parts.append(f"{_under_thousand(lakh)} Lakh")
    if thousand:
        parts.append(f"{_under_thousand(thousand)} Thousand")
    if remainder:
        parts.append(_under_thousand(remainder))

    return f"Rupees {' '.join(parts)} Only"
