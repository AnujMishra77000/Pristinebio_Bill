from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.services.financial_validation import (
    FinancialValidationError,
    normalize_money,
    normalize_quantity,
    normalize_rate,
    normalize_tax_rate,
    state_code,
)


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
    manufacturer_name: str | None = None
    manufacturer_code: str | None = None
    manufacturer_product_code: str | None = None
    part_no: str | None = None
    discount_percent: Decimal = ZERO
    pack_size: str | None = None


@dataclass(frozen=True)
class InvoiceLineCalculationResult:
    description: str
    manufacturer_name: str | None
    manufacturer_code: str | None
    manufacturer_product_code: str | None
    part_no: str | None
    hsn_sac: str
    quantity: Decimal
    unit: str
    rate: Decimal
    discount_amount: Decimal
    discount_percent: Decimal
    taxable_value: Decimal
    gst_rate: Decimal
    cess_rate: Decimal
    other_charge: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    line_total: Decimal
    pack_size: str | None = None


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
    state_code(branch_state_code, "Seller state code")
    state_code(place_of_supply_state_code, "Place of supply state code")
    if not lines:
        raise FinancialValidationError("At least one invoice line is required")

    freight_charges = normalize_money(freight_charges, "Freight charges")
    packing_charges = normalize_money(packing_charges, "Packing charges")
    other_charges = normalize_money(other_charges, "Other charges")
    discount_amount = normalize_money(discount_amount, "Document discount")
    is_intrastate = branch_state_code == place_of_supply_state_code
    calculated_lines: list[InvoiceLineCalculationResult] = []

    for index, line in enumerate(lines, start=1):
        quantity = normalize_quantity(line.quantity, f"Line {index} quantity")
        rate = normalize_rate(line.rate, f"Line {index} rate")
        other_charge = normalize_money(line.other_charge, f"Line {index} other charge")
        line_discount = normalize_money(line.discount_amount, f"Line {index} discount")
        discount_percent = normalize_tax_rate(line.discount_percent, f"Line {index} discount percent")
        if line_discount and discount_percent:
            raise FinancialValidationError(f"Line {index} must use either a discount amount or discount percent")
        gst_rate = normalize_tax_rate(line.gst_rate, f"Line {index} GST rate")
        cess_rate = normalize_tax_rate(line.cess_rate, f"Line {index} cess rate")
        line_base = (quantity * rate) + other_charge
        if discount_percent:
            line_discount = money(line_base * discount_percent / Decimal("100"))
        if line_discount > line_base:
            raise FinancialValidationError(f"Line {index} discount cannot exceed its taxable base")
        taxable_value = money(line_base - line_discount)
        cess_amount = money(taxable_value * cess_rate / Decimal("100"))
        if is_intrastate:
            cgst_amount = money(taxable_value * (gst_rate / Decimal("2")) / Decimal("100"))
            sgst_amount = money(taxable_value * (gst_rate / Decimal("2")) / Decimal("100"))
            igst_amount = ZERO
        else:
            cgst_amount = ZERO
            sgst_amount = ZERO
            igst_amount = money(taxable_value * gst_rate / Decimal("100"))
        line_total = money(taxable_value + cgst_amount + sgst_amount + igst_amount + cess_amount)
        calculated_lines.append(
            InvoiceLineCalculationResult(
                description=line.description,
                manufacturer_name=line.manufacturer_name,
                manufacturer_code=line.manufacturer_code,
                manufacturer_product_code=line.manufacturer_product_code,
                part_no=line.part_no,
                pack_size=line.pack_size,
                hsn_sac=line.hsn_sac,
                quantity=quantity,
                unit=line.unit,
                rate=rate,
                other_charge=other_charge,
                discount_amount=line_discount,
                discount_percent=discount_percent,
                taxable_value=taxable_value,
                gst_rate=gst_rate,
                cess_rate=cess_rate,
                cgst_amount=cgst_amount,
                sgst_amount=sgst_amount,
                igst_amount=igst_amount,
                cess_amount=cess_amount,
                line_total=line_total,
            )
        )

    line_taxable_total = sum((line.taxable_value for line in calculated_lines), ZERO)
    charges_total = money(freight_charges + packing_charges + other_charges)
    document_adjustment = charges_total - discount_amount
    raw_taxable_value = line_taxable_total + document_adjustment
    if raw_taxable_value < 0:
        raise FinancialValidationError("Document discount cannot exceed the taxable value")
    taxable_value = money(raw_taxable_value)
    if line_taxable_total > 0:
        weighted_gst_rate = sum((line.taxable_value * line.gst_rate for line in calculated_lines), ZERO) / line_taxable_total
        weighted_cess_rate = sum((line.taxable_value * line.cess_rate for line in calculated_lines), ZERO) / line_taxable_total
    else:
        weighted_gst_rate = ZERO
        weighted_cess_rate = ZERO

    line_cgst_total = sum((line.cgst_amount for line in calculated_lines), ZERO)
    line_sgst_total = sum((line.sgst_amount for line in calculated_lines), ZERO)
    line_igst_total = sum((line.igst_amount for line in calculated_lines), ZERO)
    line_cess_total = sum((line.cess_amount for line in calculated_lines), ZERO)
    allocated_cgst = money(document_adjustment * (weighted_gst_rate / Decimal("2")) / Decimal("100"))
    allocated_sgst = money(document_adjustment * (weighted_gst_rate / Decimal("2")) / Decimal("100"))
    allocated_igst = money(document_adjustment * weighted_gst_rate / Decimal("100"))
    allocated_cess = money(document_adjustment * weighted_cess_rate / Decimal("100"))

    if is_intrastate:
        cgst_amount = money(line_cgst_total + allocated_cgst)
        sgst_amount = money(line_sgst_total + allocated_sgst)
        igst_amount = ZERO
    else:
        cgst_amount = ZERO
        sgst_amount = ZERO
        igst_amount = money(line_igst_total + allocated_igst)
    cess_amount = money(line_cess_total + allocated_cess)

    unrounded_total = money(taxable_value + cgst_amount + sgst_amount + igst_amount + cess_amount)
    final_total = rupee(unrounded_total)
    round_off = money(final_total - unrounded_total)
    if final_total < 0:
        raise FinancialValidationError("Invoice total cannot be negative")

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
