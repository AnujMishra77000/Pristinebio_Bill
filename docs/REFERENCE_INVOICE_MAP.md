# Approved reference invoice map

## Verification status

| Item | Status |
| --- | --- |
| Source file inspected | `/Users/anujmishra/Downloads/AOPL 00937 (1) (1).pdf` |
| Reference filename | `AOPL 00937 (1) (1).pdf` (the approved file supplied for this phase) |
| Page count | 4 |
| Page size/orientation | A4 portrait, approximately 595.28 x 841.88 points |
| Visual inspection | Complete; all four pages rendered to PNG and reviewed |
| Text extraction | Supporting check only; visual inspection is authoritative |

The source contains the real business values, logo artwork, QR payload, signed-IRN text, and sample customer data. Those values are reference evidence only and must not be hardcoded into the application or test fixtures.

## Visual structure

The full invoice copy uses a white page, navy text, light grey-blue rules, and a purple accent for the grand-total row and footer rule. The page has a generous white margin and a compact, information-dense A4 composition.

### Page 1 - full copy

Reading order and approximate placement:

1. Top header: seller logo at upper left; centered `Tax Invoice` title; copy label at upper right.
2. Seller block at upper left: legal name, address, GSTIN, contact, and pickup address.
3. Invoice identity block at upper right: IRN label/value, QR area, invoice number, invoice date, payment terms, PO number/date, E-Way Bill No., and acknowledgement number.
4. Bordered two-column party block: `Buyer Details` on the left and `Consignee / Shipping Details` on the right.
5. Item table spanning the page width.
6. `Total Quantity` line immediately below the table, aligned to the right.
7. Lower content split into two columns: amount-in-words, bank details, and transporter details on the left; tax summary and final total on the right.
8. `Terms and Conditions:` numbered list below the settlement/tax block.
9. Lower-right signature block with digital-signature wording and timestamp.
10. Purple footer rule, `Powered by` plus provider mark on the left, and `This is a Computer Generated Tax Invoice` on the right.

### Page 2 - sparse copy

The inspected page is otherwise blank and shows only the top-right copy label `Duplicate for Transporter`. It does not repeat the invoice body, table, totals, terms, signature, or footer.

### Page 3 - full copy

The page repeats the complete page-1 structure and content. The only observed data difference is the top-right copy label: `Triplicate for Supplier`.

### Page 4 - sparse copy

The inspected page is otherwise blank and shows only the top-right copy label `Extra`. It does not repeat the invoice body, table, totals, terms, signature, or footer.

## Sections and fields

The following labels and field behaviors were observed on the full invoice pages. A field marked conditional is rendered only when the approved invoice snapshot contains a value; the reference demonstrates values for the listed sample invoice.

| Section | Exact visible labels / fields | Type and behavior | Repeats in reference |
| --- | --- | --- | --- |
| Document header | `Tax Invoice`; copy label | Static title; copy label varies by copy | On full copies; copy label alone on sparse pages |
| Seller identity | Logo; legal seller name; address; `GSTIN:`; `Contact:`; `Pickup Address:` | Branding asset and text; seller/branch snapshot | Full pages only |
| IRN and QR | `IRN No.:`; IRN value; signed QR image area | Conditional text and optional QR area | Full pages only |
| Invoice identity | `Invoice No:`; `Invoice Date:`; `Payment Terms:`; `PO No:`; `PO Date:`; `E-Way Bill No.:`; `Ack. No.:` | Invoice snapshot values; PO, E-Way, and acknowledgement are conditional | Full pages only |
| Buyer party | `Buyer Details`; buyer name; address lines; `GSTIN:`; `Contact:` | Customer billing snapshot; long address wraps | Full pages only |
| Consignee party | `Consignee / Shipping Details`; consignee name; address lines; `GSTIN:`; `Mode of Shipment:`; `Vehicle No:`; `Vehicle Type:`; `LR/Docket No.:`; `Trans Doc Date:`; `Expected Delivery Date:` | Shipping/customer and transport snapshot; transport fields conditional | Full pages only |
| Line items | Ten columns listed below | Repeated rows; description, HSN/SAC, and numeric values wrap/aligned within cells | Full pages only |
| Quantity | `Total Quantity:` | Aggregate quantity rendered below the table, right aligned | Full pages only |
| Amount in words | `Total Amount in words:` | Text value below the table, left aligned | Full pages only |
| Bank settlement | `Bank Name:`; `Branch Name:`; branch/location text; `A/C No.:`; `IFSC:` | Bank-account snapshot; value block left aligned | Full pages only |
| Transporter | `Transporter:`; `GSTIN:` | Transporter master snapshot; conditional | Full pages only |
| Tax summary | `Taxable Value`; `SGST`; `CGST`; `Cess Amount`; `Discount Value`; `Round Off Amount`; `Total Invoice Amount` | Right-side bordered summary; tax rows are conditional by tax regime; final row uses purple fill | Full pages only |
| Terms | `Terms and Conditions:` followed by numbered clauses | Long wrapped numbered text | Full pages only |
| Signature | `Digitally Signed By`; seller name; generated/signed timestamp | Conditional signature metadata block | Full pages only |
| Footer | `Powered by`; provider mark; `This is a Computer Generated Tax Invoice` | Static generated-invoice footer | Full pages only |

Not visibly present in this reference: page number, total-page count, reverse-charge label, PAN, salesperson, currency label, UPI/payment reference, prepared-by/checked-by labels, company seal, or a separate branch-name label in the seller header. Branch name may still be supplied by the application context when available, but it must not be invented in the rendered reference layout.

## Exact line-item table

The table is full-width, has a lightly tinted header row, thin grey-blue borders, and ten columns in this exact order:

| Order | Exact header | Observed rendering |
| ---: | --- | --- |
| 1 | `S No.` | Narrow; serial number is left/center aligned |
| 2 | `Item Details` | Largest column; product description wraps |
| 3 | `HSN /SAC` | Narrow; HSN may wrap across two lines |
| 4 | `Quantity` | Numeric quantity and unit appear in the same cell on separate lines |
| 5 | `Base Rate` | Decimal rate, right aligned |
| 6 | `Other Charge` | Decimal amount, right aligned |
| 7 | `Discount` | Decimal amount/value, right aligned |
| 8 | `GST (%)` | Rate and percent sign may wrap to separate lines |
| 9 | `Cess` | Decimal amount/rate, right aligned |
| 10 | `Amount` | Comma-grouped line amount, right aligned; narrow values may wrap |

The reference has one visible item row. No per-line tax amount columns are present; tax values appear in the summary block. The table’s header and row borders align with the outer party-block borders. The Phase 1D generator must keep a row together, allow safe wrapping for long descriptions/HSN values, and repeat the table header on generated continuation pages.

## Four copy labels

The labels are exact, including capitalization and wording:

1. `Original for Recipient`
2. `Duplicate for Transporter`
3. `Triplicate for Supplier`
4. `Extra`

Each label is top-right aligned on its copy. The full reference pages show labels 1 and 3; the sparse pages show labels 2 and 4. The Phase 1D product requirement explicitly requires four complete generated copies from one immutable invoice snapshot; therefore the implementation will use these labels while rendering the full approved invoice body for every copy. Only the copy label may differ between copies.

## Pagination and continuation behavior

### Observed reference behavior

- All four pages are A4 portrait.
- The reference has no visible page-number or total-page field.
- Page 1 and page 3 are full invoice pages with the same structure.
- Page 2 and page 4 contain only their copy label; they do not act as continuation pages.
- The single visible item row does not demonstrate row splitting, table-header repetition, or a totals-on-final-page case.
- Full pages reserve bottom space for the terms, digital-signature block, purple footer rule, provider mark, and generated-invoice footer.

### Phase 1D generated behavior

The production generator extends the observed structure for real invoice data:

- Render one immutable approved invoice snapshot into four complete copies.
- Use A4 portrait with fixed print margins and CSS print color adjustment.
- Keep the header/identity and table structure stable; for long invoices, allow the item table to flow across pages.
- Repeat invoice identity and table headings on continuation pages.
- Keep each item row together where possible; long text wraps within the row and never overflows the printable area.
- Keep total quantity, amount in words, bank/transporter details, tax summary, final total, terms, signature, and footer content on the final page.
- Do not split the totals/terms/signature group across pages; if it does not fit, move the complete group to the next page.
- Keep copy labels on every copy’s first page. Generated continuation pages use the invoice identity/table header required for context and do not introduce a different copy label.
- Values such as IRN, QR, E-Way Bill, acknowledgement, bank, transporter, logo, and signature are optional data from the snapshot. Empty optional values render as blank/omitted fields; reference sample values are never fallback defaults.

## Layout acceptance checklist

- A4 portrait output with no clipped content, overlaps, or broken borders.
- Seller, buyer, consignee, invoice identity, transport, item, tax, settlement, terms, signature, and footer sections appear in the documented order.
- Exact ten-column table order and labels are preserved.
- Copy labels are exact and are the only data difference between copies.
- Short invoices produce a balanced complete page per copy.
- Twenty-item and eighty-item invoices paginate with repeated identity/table headings and final-page totals/terms.
- Long names, addresses, descriptions, and terms wrap safely.
- Intrastate and interstate snapshots show the appropriate tax summary rows without inventing IRN/E-Way values.
