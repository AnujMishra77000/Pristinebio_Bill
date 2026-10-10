from decimal import Decimal

from app.services.invoice_calculator import InvoiceCalculationLine, calculate_invoice


def test_required_intrastate_calculation_fixture_uses_half_up_rounding():
    result = calculate_invoice(
        branch_state_code="36",
        place_of_supply_state_code="36",
        lines=[
            InvoiceCalculationLine(
                description="Chemical raw material",
                hsn_sac="29181590",
                quantity=Decimal("9798.000"),
                unit="KG",
                rate=Decimal("30.00"),
                discount_amount=Decimal("0.00"),
                gst_rate=Decimal("18.00"),
                cess_rate=Decimal("0.00"),
            )
        ],
    )

    assert result.taxable_value == Decimal("293940.00")
    assert result.cgst_amount == Decimal("26454.60")
    assert result.sgst_amount == Decimal("26454.60")
    assert result.igst_amount == Decimal("0.00")
    assert result.unrounded_total == Decimal("346849.20")
    assert result.round_off == Decimal("-0.20")
    assert result.final_total == Decimal("346849.00")
    assert result.amount_in_words == "Rupees Three Lakh Forty Six Thousand Eight Hundred Forty Nine Only"


def test_interstate_calculation_uses_igst_instead_of_cgst_sgst():
    result = calculate_invoice(
        branch_state_code="36",
        place_of_supply_state_code="29",
        lines=[
            InvoiceCalculationLine(
                description="Chemical raw material",
                hsn_sac="29181590",
                quantity=Decimal("9798.000"),
                unit="KG",
                rate=Decimal("30.00"),
                discount_amount=Decimal("0.00"),
                gst_rate=Decimal("18.00"),
                cess_rate=Decimal("0.00"),
            )
        ],
    )

    assert result.taxable_value == Decimal("293940.00")
    assert result.cgst_amount == Decimal("0.00")
    assert result.sgst_amount == Decimal("0.00")
    assert result.igst_amount == Decimal("52909.20")
    assert result.final_total == Decimal("346849.00")


def test_line_other_charge_is_included_in_the_taxable_value_and_pdf_snapshot():
    result = calculate_invoice(
        branch_state_code="36",
        place_of_supply_state_code="36",
        lines=[
            InvoiceCalculationLine(
                description="Chemical raw material",
                hsn_sac="29181590",
                quantity=Decimal("10.000"),
                unit="KG",
                rate=Decimal("30.00"),
                other_charge=Decimal("5.00"),
                discount_amount=Decimal("0.00"),
                gst_rate=Decimal("18.00"),
                cess_rate=Decimal("0.00"),
            )
        ],
    )

    assert result.lines[0].other_charge == Decimal("5.00")
    assert result.lines[0].taxable_value == Decimal("305.00")
    assert result.taxable_value == Decimal("305.00")


def test_reagent_line_percentage_discount_is_calculated_with_decimal_rounding():
    result = calculate_invoice(
        branch_state_code="36",
        place_of_supply_state_code="36",
        lines=[
            InvoiceCalculationLine(
                description="Laboratory reagent",
                part_no="RX-001",
                hsn_sac="38221990",
                quantity=Decimal("3.000"),
                unit="BTL",
                rate=Decimal("199.99"),
                discount_amount=Decimal("0.00"),
                discount_percent=Decimal("12.50"),
                gst_rate=Decimal("18.00"),
                cess_rate=Decimal("0.00"),
            )
        ],
    )

    assert result.lines[0].part_no == "RX-001"
    assert result.lines[0].discount_percent == Decimal("12.50")
    assert result.lines[0].discount_amount == Decimal("75.00")
    assert result.lines[0].taxable_value == Decimal("524.97")
    assert result.taxable_value == Decimal("524.97")
