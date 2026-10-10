# Project status

## Unconfirmed billing sessions and customer register — implemented and verified (2026-10-09)

- Implemented the client's approved bounded design. All four forms retain separate authenticated-user, same-tab memory through navigation: seller/buyer/consignee fields, line items, quantities/rates, dates, transport, number, saved document/version/signature, retry key and in-flight save state. Domestic/Reagent PO now reuse the existing session mechanism rather than page-local submission state. Master reloads initialize a default seller once and do not replace retained entered values. Save retries resolve the same intended transaction rather than creating another bill.
- Successful final approval/PDF confirmation leaves Download/Print on the current page and starts a fresh entry on its next visit. Pending approval and failed confirmation retain work. Explicit Start new clears only that kind without deleting server records; logout, account change/disable and confirmed deletion clear only the appropriate entries and reject late writes. PO deletion now invalidates PO sessions separately from invoices, including same-origin ID/family-only notifications, so identical numeric IDs in different tables cannot erase each other's work. Auth/session expiry, refresh, CSRF and permissions are unchanged.
- Reproduced a related Sales/Reagent gap: a saved buyer was submitted by master ID only, so editing that customer while billing could silently change its transaction address. Retain the selected buyer snapshot and submit it alongside the same ID; draft PATCH preserves that ID. Explicit reselection loads the current customer. Existing backend active-master checks, snapshot handling and approval immutability remain authoritative; invoice APIs/calculators and PDF implementation were not changed.
- Customer register uses `GET /api/v1/customers?register=true&limit=100&offset=...`: one normalized GSTIN per authorized profile, preferring the oldest active record, otherwise the oldest inactive one. No-GSTIN customers remain separate. Deduplication happens before pagination; **Load more customers** reaches later records without unbounded responses. Generic list/detail APIs still expose historical records; nothing was merged or deleted.
- Enabled **Edit** with complete billing/shipping address mapping and same-ID PATCH, retaining its profile assignment and fields after errors. GSTIN conflicts appear beneath GSTIN. Corrected explicit-null optional shipping clearing and required-null validation (name, billing address, profile, active flag), which previously ignored clearing or raised a database error. Omitted addresses remain unchanged. Master edits do not rewrite saved invoices.

### Relevant files

Frontend: `app/lib/invoiceEntrySession.ts`, `useBillSubmission.ts`, new `app/components/RetainedBillEntry.tsx`, `InvoiceEntryPage.tsx`, `BillRegisterPage.tsx`, `MasterDataPage.tsx`, both PO pages and Customers page. Backend: `app/api/v1/customers.py`, CustomerUpdate in `app/schemas/master_records.py`. Regressions: `backend/tests/test_customer_register_editing.py`, extended `frontend/scripts/invoice_entry_session.test.mjs` and `verify_po_seller_retry_ui.py`, new `verify_bill_session_customer_ui.py` and `verify_customer_register_paging_ui.py`. Updated billing context and this status. Preserved the existing dirty working tree.

### Verification evidence

- Superpowers test-first runs reproduced register duplicates, absent Edit, missing confirmation release, invoice/PO ID collision, ignored shipping clearing, null-required-field database failure, master-only buyer payload and missing later-page access before their fixes. Corrected fixture email and textarea locators; the Explore navigation test now waits for the destination URL instead of racing route completion.
- From `backend/`: `./.venv/bin/python -m pytest tests/test_customer_register_editing.py tests/test_customer_gstin_identity.py tests/test_master_records.py tests/test_saved_bill_editing.py tests/test_saved_shipping_addresses.py -q --tb=line --show-capture=no` — **48 passed**, one existing Starlette/httpx deprecation warning. Isolated SQLite coverage of scoped/deduplicated pagination, historical IDs, same-customer edits, clearing/omission/null/collision rules, buyer snapshot preservation, both taxes and existing bill edits/workflows. No live PostgreSQL/concurrency guarantee is inferred.
- From `frontend/`: `node --test scripts/*.test.mjs` — **40 passed**; `npm run type-check` and targeted ESLint over the nine changed application files — **passed**. Isolated `NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1 npm run build -- --no-lint` in `/private/tmp/billing-session-db7Qmz/frontend` — **passed**, 30 routes, with lint checked separately. The client's running frontend and `.next` were not replaced.
- Browser commands use `FRONTEND_BASE_URL=http://127.0.0.1:3000 ../backend/.venv/bin/python scripts/<script>.py`. `verify_bill_session_customer_ui.py` — **all four end-to-end flows passed**, including saved draft navigation, customer edit/error/same-ID PATCH, failure/retry without POST, Confirm/final actions/fresh next entry, 390px width and both invoice kinds retaining a chosen buyer after master edits. `verify_po_seller_retry_ui.py` — **both PO types passed**, including unsaved navigation and uncertain creation retaining exact key/body. `verify_invoice_navigation_ui.py` — **both invoice types passed**, covering dynamic fields, uncertain/in-flight saves, independent sessions, master failure, logout/reauthentication and refresh behavior. `verify_saved_bill_edit_recovery_ui.py` — **16 scenarios passed** across all four forms. `verify_customer_register_paging_ui.py` — **passed**, including later records, Refresh resetting pagination and 390px width. All APIs were intercepted; fixture PDF bytes verify controls, not new PDF rendering.
- `git diff --check` passed. PDF service, HTML and both PDF CSS SHA-256 hashes exactly match their starting values. Fonts, logos, layout, pagination, print formatting and financial calculations are unchanged.
- A focused read-only Superpowers reviewer found no material correctness/security issue in the scoped retention, retry/version identity, PO initialization and customer edit/register handling. It did not rerun tests or modify files; verification evidence above is from the main agent's fresh runs.

### Activation / limitations

Reload/restart the backend if auto-reload is disabled and refresh the frontend. No migration or dependency installation is required. Unsaved memory survives same-tab client navigation, not full refresh/tab close; reopen saved server drafts through Edit. Logout/account switching intentionally clears private work. Pending Staff approval is not treated as completed final approval. Register pagination is a live view; Refresh reflects intervening master changes, not a historical database snapshot. Existing duplicate master rows/history remain stored, and unregistered/no-GSTIN customers are not falsely merged.

No client database, full unrelated backend suite, fresh PDF fixture rendering, Docker startup, deployment, commit or push was performed. Earlier documented full-suite/MFA and real PostgreSQL verification limitations remain unchanged. Stop after this approved session/customer feature.

## Edit saved bills across all four registers — completed (2026-10-09)

- Completed the resumed, approved **draft-editing** scope. Sales, Purchase, Reagent and Reagent Purchase registers now offer **Edit** for editable saved records and their PDF view offers **Edit this draft**. Each opens its matching entry page with the existing document ID. Submitted/approved/PDF-generated/closed/cancelled records remain read-only; existing PO amendment-pending editing is preserved. No finalized invoice was unlocked or rewritten.
- Shared loading validates ID/type/version, cancels stale requests, blocks creation after a failed open, exposes Retry and protects unsaved work. All four forms hydrate transaction party/item/date/transport/number snapshots, not changed master values. Sales/Reagent reopen their independent buyer/consignee snapshots in manual mode and recover manufacturer selection from the saved code. POs retain fixed seller identity. Save uses one optimistic-version PATCH; preview/confirmation targets that exact saved revision. Conflict recovery retains entered fields until explicit reload confirmation. Start new bill/order clears the edit query so the old bill cannot reopen as the new one; it does not delete the saved record.
- Found and reproduced an associated backend defect in all four types: replacing a saved line ignored its explicit product name and substituted a later catalog name. Limited the fix to draft-update line snapshots, honoring the submitted transaction name and linked product ID without changing the master. Creation behavior, Decimal calculations, number families, approval policy and PDF interfaces remain unchanged.
- Application files: `frontend/app/components/BillRegisterPage.tsx`, `frontend/app/components/InvoiceEntryPage.tsx`, `frontend/app/purchase-orders/page.tsx`, `frontend/app/reagent-purchase-orders/page.tsx`, `frontend/app/lib/billRegisters.ts`, `frontend/app/lib/useSavedBillLoader.ts`, `frontend/app/lib/useBillSubmission.ts`, `frontend/app/lib/types.ts`; draft line-name handling in `backend/app/api/v1/invoices.py` and `backend/app/api/v1/purchase_orders.py`. New regressions: `backend/tests/test_saved_bill_editing.py`, `frontend/scripts/bill_editing.test.mjs`, `frontend/scripts/verify_saved_bill_editing_ui.py`, `frontend/scripts/verify_saved_bill_edit_recovery_ui.py`. Updated billing context and this status. All pre-existing user changes were preserved.

### Verification

- Test-first register/browser checks reproduced missing Edit links; four later backend regressions reproduced overwritten transaction item names. Final backend command from `backend/`: `./.venv/bin/python -m pytest tests/test_saved_bill_editing.py tests/test_inline_invoice_parties.py tests/test_phase3_workflows.py tests/test_financial_correctness.py tests/test_reagent_purchase_orders.py -q --tb=line --show-capture=no -k 'not pdf_fixtures'` — **57 passed, 2 PDF fixture cases deselected**, one existing Starlette/httpx deprecation warning. Covers one-record editing across all four types, unchanged numbers, preview/save/approval total consistency, version conflicts, revisions, approved immutability, Staff/profile isolation and independent product-name/master snapshots. Reagent PO workflow tests were corrected to submit the required explicit approval version; no policy was loosened. Isolated SQLite coverage only, not a live PostgreSQL concurrency claim.
- From `frontend/`: `node --test scripts/bill_editing.test.mjs scripts/bill_deletion.test.mjs scripts/invoice_entry_session.test.mjs` — **17 passed**, including role-neutral draft Edit links, finalized exclusions, existing deletion safeguards and session lifecycle. `FRONTEND_BASE_URL=http://127.0.0.1:3000 ../backend/.venv/bin/python scripts/verify_saved_bill_editing_ui.py` — **all four register→snapshot→single PATCH→preview→confirm flows passed**, including stored names/addresses/rates/manufacturer data, linked product IDs, final Download/Print readiness, disabled final fields, 390px width and Start new clearing the saved ID. Browser PDF bytes are isolated fixtures; no client records or rendering implementation were used/changed. Corrected two test-fixture issues: mixed invoice/PO fields and the Reagent PO Manufacturer accessible name.
- `FRONTEND_BASE_URL=http://127.0.0.1:3000 ../backend/.venv/bin/python scripts/verify_saved_bill_edit_recovery_ui.py` — **16 scenarios passed**, across all four forms: failed load/retry, wrong document type, invalid ID, and concurrent edit with retained input, cancelled reload, accepted latest-version reload and versioned retry, with zero creation requests. All browser API traffic was intercepted.
- `npm run type-check` and `npx --no-install eslint app/lib/useSavedBillLoader.ts app/lib/billRegisters.ts app/lib/useBillSubmission.ts app/lib/types.ts app/components/BillRegisterPage.tsx app/components/InvoiceEntryPage.tsx app/purchase-orders/page.tsx app/reagent-purchase-orders/page.tsx --max-warnings=0` — **passed**. Isolated `NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1 npm run build -- --no-lint` in `/private/tmp/billing-saved-edit-dTYWFk/frontend` — **passed**, 30 routes, with lint checked separately. The running frontend and `.next` were not replaced. `git diff --check` passed. PDF service, HTML and both PDF CSS files retain their exact starting SHA-256 hashes; fonts, logos, page layout, pagination and print formatting were untouched.

### Activation / limitations

Reload/restart the backend if not using auto-reload and refresh the frontend. No migration or dependency install is needed. POs retain the existing rule that their seller is fixed after save; approved POs use the existing reasoned amendment lifecycle rather than direct edits. A saved reagent manufacturer's code must still resolve to an active available choice for a new edit; inactive/missing masters are not silently accepted. Same-tab Sales/Reagent work remains memory-only; full refresh clears unsaved memory. This is not authorization to edit finalized invoices directly. No unrelated full suite, fresh PDF fixture/raster generation, live database access, Docker start, deployment, commit or push. No change-specific blocker; stop after this approved saved-draft editing feature.

## Saved-buyer billing/shipping address choice — completed (2026-10-09)

- Fixed the confirmed form-side cause: the shared Sales/Reagent helper always copied `Customer.billing_address` despite a separately saved shipping address. After saved-buyer selection, both forms now offer **Use billing address for shipping** and **Use saved shipping address** as mutually exclusive checkboxes. Default to shipping when available, otherwise billing; unavailable shipping is disabled with a clear explanation. Copy the complete selected address into the existing consignee payload so the PDF shipping panel receives the chosen data while the buyer panel retains billing data.
- Switching sources preserves entered consignee name/PAN/phone/email and the separately editable place-of-supply code. The selected source and transaction address use the existing in-memory per-user/per-kind entry session and survive client navigation/master reloads; an explicit buyer change initializes its default. No persistent browser storage or new master records are introduced. Existing preview/save/versioned editing, approval, tax and PDF data interfaces remain unchanged. Historical snapshots are preserved.
- Application change is limited to `frontend/app/components/InvoiceEntryPage.tsx`; no backend production code, schema/model, migration, PO form, PDF service/template/CSS/font/logo/layout or financial calculation changed. Added `frontend/scripts/verify_shipping_address_choice_ui.py` and `backend/tests/test_saved_shipping_addresses.py`; updated this status and billing context. Preserved existing user changes.

### Verification

- Test-first browser check reproduced the missing address choices and billing-only prefill. Final command from `frontend/`: `FRONTEND_BASE_URL=http://127.0.0.1:3000 ../backend/.venv/bin/python scripts/verify_shipping_address_choice_ui.py` — **passed** for both Sales/Reagent: shipping default, exclusive choices (including clicking the selected checkbox), keyboard switching, complete address values, independent contact preservation, retained client navigation, unchanged manual tax override, saved payload, missing-shipping fallback, buyer changes and 390px width. Every API request was intercepted; no client records were created. The first post-change run used a label locator that did not match the existing textarea wrapper; targeting its actual accessible textbox fixed that test selector without changing the component.
- From `backend/`: `./.venv/bin/python -m pytest tests/test_saved_shipping_addresses.py tests/test_customer_gstin_identity.py tests/test_inline_invoice_parties.py tests/test_master_records.py -q --tb=line --show-capture=no` — **43 passed**, one existing Starlette/httpx deprecation warning. Six new real-API cases cover both bill types with shipping, billing and absent shipping; verify distinct addresses, unchanged totals, IGST, manual contacts, draft edits, approval and immunity to later master edits. The unchanged PDF context and rendered four-copy HTML contain the selected shipping address and retained buyer billing address, not the edited master street. Tests use isolated SQLite; no live PostgreSQL claim. No fresh PDF rasterization was required because rendering/layout code is unchanged.
- `node --test scripts/invoice_entry_session.test.mjs` — **7 passed**; `npm run type-check` and `npx --no-install eslint app/components/InvoiceEntryPage.tsx --max-warnings=0` — **passed**. Isolated `NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1 npm run build -- --no-lint` in `/private/tmp/billing-shipping-choice-j14U6h/frontend` — **passed**, 30 routes, with lint checked separately. The running frontend server and its `.next` were not replaced. `git diff --check` passed; PDF service, HTML and both PDF CSS hashes exactly match the task's starting values.

No migration or backend restart is required for this frontend change. Refresh the browser and select a saved buyer to use the new choices. No dependency install, unrelated full suite, client database access, Docker start, deployment, commit or push. No change-specific blocker; stop after this approved address-selection change.

## GSTIN-based saved-buyer identity — completed (2026-10-09)

- Fixed the confirmed duplicate sources: Customer POST always inserted; inline buyer matching was case-sensitive and could reuse a different GSTIN by name/phone; manual consignees automatically became additional buyer masters. New customer and inline Sales/Reagent buyer inputs normalize GSTINs, reuse an existing active matching master within authorized seller-profile scope, and leave that master's identity/address unchanged. Customer POST returns 200 for reuse and 201 for a new record. Inactive-only matches are rejected; identity-changing master edits/reactivation return a clear 409 on collision. No-GSTIN buyers remain supported.
- Added a billing-only active/deduplicated customer query, filtering before its limit. Both Sales and Reagent pickers display company names only, retain name/GSTIN search and defensively hide duplicate/inactive options. Manually entered consignees stay separate transaction snapshots. Tests verify submitted buyer/consignee addresses survive draft edits, submission and Manager approval with unchanged totals. Historical duplicate rows, IDs, snapshots, master-management/detail endpoints and financial/integration references remain intact; no records were merged/deleted or client data rewritten.
- Application files: `backend/app/services/customer_identity.py`, `backend/app/api/v1/customers.py`, `backend/app/api/v1/invoices.py`, `backend/app/schemas/master_records.py`, `backend/app/schemas/invoice.py`, `frontend/app/components/InvoiceEntryPage.tsx`. Regressions: `backend/tests/test_customer_gstin_identity.py`, `backend/tests/test_postgresql_customer_identity.py`, `frontend/scripts/verify_buyer_gstin_ui.py`; updated the existing consignee browser mock for the billing query/accessible picker. Corrected two existing invoice-test expectations to use the current PDF template-version constant instead of obsolete v8; the renderer itself was not changed.

### Verification

- Test-first backend run reproduced duplicate saves, case sensitivity, list-limit pollution, missing inactive/collision checks, unwanted consignee masters and wrong-GSTIN name fallback. Final command from `backend/`: `./.venv/bin/python -m pytest tests/test_customer_gstin_identity.py tests/test_postgresql_customer_identity.py tests/test_master_records.py tests/test_financial_correctness.py tests/test_inline_invoice_parties.py tests/test_invoices.py -q --tb=line --show-capture=no` — **75 passed, 1 skipped**, one existing Starlette/httpx deprecation warning. Includes actual API persistence, authorization, existing snapshot/idempotency/approval behavior, new GSTIN checks, PostgreSQL lock-key unit coverage and two unchanged PDF-generation lifecycle checks. The first wider run exposed only sandbox Chromium restrictions, then the two stale version assertions; both final PDF lifecycle checks passed after permission and assertion correction.
- From `frontend/`: `FRONTEND_BASE_URL=http://127.0.0.1:3000 ../backend/.venv/bin/python scripts/verify_buyer_gstin_ui.py` — **passed** for both Sales/Reagent, normalized duplicates, name labels, inactive filtering, name/GSTIN search, editable consignee and 390px width. All API calls were intercepted fixtures, not client data. The first browser attempt selected the pickup-supplier combobox; the regression now targets the explicit Saved buyer accessible label and passes.
- `npm run type-check` and `npx --no-install eslint app/components/InvoiceEntryPage.tsx --max-warnings=0` — **passed**. Isolated `NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1 npm run build -- --no-lint` in `/private/tmp/billing-buyer-gstin-bf4X7r/frontend` — **passed**, 30 routes; lint ran separately. The client's running frontend and `.next` were not replaced. `git diff --check` passed. PDF service, HTML and both PDF CSS SHA-256 hashes exactly match this task's starting hashes; PDF formatting, fonts, logos, layouts, financial calculations and numbering are unchanged.

### Activation / limits

No migration is required. Reload/restart the backend if needed and refresh Sales/Reagent entry. PostgreSQL advisory locks serialize all affected application writers until commit/rollback without a destructive historical uniqueness migration. The real parallel PostgreSQL test is **unverified/skipped** because `TEST_SECURITY_DATABASE_URL` is unset; SQLite/lock-unit coverage is not a PostgreSQL race guarantee. External SQL/import writers must use the same locking policy. The picker remains bounded to 100 unique active choices by default and searches that returned list. Existing duplicate masters remain visible in master management/history, intentionally. No dependencies added, unrelated full suite, live database access, Docker start, deployment, commit or push; no change-specific blocker. Stop after this approved buyer-identity fix.

## Purchase Order Dispatched through input — completed (2026-10-08)

- Added an optional **Dispatched through** textbox to Domestic PO entry, alongside order details, with a 100-character limit, stable accessible label and related error directly beneath it. Values remain during validation/network failures and draft editing, and are trimmed into the existing `transport_mode` payload; blank becomes explicit null.
- Confirmed three broken links: no entry input/payload, Domestic creation/full-draft edits skipped the already-defined field (the existing metadata helper was Reagent-only), and the PO PDF context forced it blank. Creation now persists it, versioned edits update/clear supplied values while preserving omitted values, and the PDF context passes the saved snapshot to the existing row. Approval retains it and still blocks direct finalized edits. No financial calculations, authorization, numbered-document rules, migrations or historical PDFs changed. New Domestic PDF version: **`a4-purchase-order-v10`**; other format versions remain unchanged.
- Application files: `frontend/app/purchase-orders/page.tsx`, `backend/app/api/v1/purchase_orders.py`, `backend/app/services/invoice_pdf.py`. Regressions: `backend/tests/test_bill_header_tax_layout.py`, `frontend/scripts/verify_po_seller_entry_ui.py`; updated billing context/reference notes and this status. All existing user changes were preserved. The HTML and both PDF CSS files retain exact starting SHA-256 hashes; fonts, logos, pagination and print styling were not edited.
- Test-first backend checks reproduced three persistence failures and the browser check reproduced the missing textbox. After the fix, the first backend subset passed **5 tests**. Final command from `backend/`: `./.venv/bin/python -m pytest tests/test_bill_header_tax_layout.py tests/test_purchase_order_numbers.py tests/test_invoice_pdf.py::test_purchase_order_context_renders_a_separate_document_title_and_metadata 'tests/test_pdf_four_item_pages.py::test_four_products_per_physical_page_with_fixed_sections[5-purchase]' -q --tb=short --show-capture=no --basetemp=/private/tmp/billing-po-dispatch-6jzQRy/verified` — **68 passed**, one existing Starlette/httpx deprecation warning. Covers trimmed persistence, retry replay, versioned editing, omitted-vs-null/blank clearing, maximum length, stale-update conflict, approval preservation/immutability, authoritative unchanged totals, numbering, other formats and pagination. Isolated SQLite coverage; no new live PostgreSQL guarantee is claimed.
- From `frontend/`: `FRONTEND_BASE_URL=http://127.0.0.1:3000 ../backend/.venv/bin/python scripts/verify_po_seller_entry_ui.py` — **all four scenarios passed** (manual/saved suppliers for Domestic/Reagent PO). Domestic checks include the new input/limit, field-level errors, retained values, stable retry key/payload, versioned dispatch editing and 390px layout. All API traffic was intercepted as isolated browser fixtures; no real client backend record was changed. The first post-change browser run exposed the error text becoming part of the field's accessible name; corrected it with an explicit stable label and reran successfully. Backend tests separately verify actual API persistence and approval.
- `npm run type-check`, `npm run lint`, and the final targeted `npx --no-install eslint app/purchase-orders/page.tsx --max-warnings=0` — **passed**. Isolated production `NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1 npm run build -- --no-lint` in `/private/tmp/billing-po-dispatch-6jzQRy/frontend` — **passed**, including type validation and 30 static pages. Lint ran separately; the running frontend's `.next` directory was not replaced. No client server was stopped or restarted.
- Actual one-item/five-item Domestic POs rendered to one/two A4 pages and all three pages to PNG; visually inspected each, confirming **ROAD / Courier** fits the existing Invoice Details row without layout defects. Bundled `pdfplumber` verified one dispatch label/value per page and no reintroduced Delivery Note Date. `git diff --check` passed. No dependencies added, unrelated full suite, live database access, deployment, commit or push. Refresh entry and create a new PDF; reload backend if needed. Existing stored PDFs are not rewritten. No change-specific blocker; stop after this approved dispatch fix.

## Purchase Order delivery-date placement — completed (2026-10-08)

- Applied the approved Domestic PO-only correction: new PDFs omit **Delivery Note Date**, and a supplied **Expected Delivery Date** appears in **Invoice Details** immediately after PO Date, not in Seller / Shipping Address. The entry form already omitted Delivery Note Date and keeps its optional Expected Delivery Date input. Missing expected dates omit their row. New Domestic PO PDFs use **`a4-purchase-order-v9`**; stored dates, calculations and historical PDFs are preserved.
- Changes are limited to the Domestic PO context condition/version in `backend/app/services/invoice_pdf.py` and its date-row branch in `backend/app/templates/invoice/v1/invoice.html`. Reagent PO retains its delivery-note and shipping expected-date behavior; Sales and Reagent Bills also retain their existing mappings and versions. Added API-persistence, optional-date, other-format and real Chromium/PDF regressions in `backend/tests/test_bill_header_tax_layout.py`; updated billing context/reference notes and this status. Existing user changes, entry form, both PDF CSS files, fonts, logos, table/terms/footer styles and financial/business code were preserved. Frontend/CSS SHA-256 hashes match the task's starting values.
- Test-first checks reproduced two expected Domestic PO failures; three other-format checks already passed. The first corrected subset passed **6 tests**. Final command from `backend/`: `./.venv/bin/python -m pytest tests/test_bill_header_tax_layout.py tests/test_invoice_pdf.py::test_purchase_order_context_renders_a_separate_document_title_and_metadata tests/test_invoice_pdf.py::test_sales_invoice_meta_shows_only_approved_transport_fields_in_order tests/test_invoice_pdf.py::test_reagent_bill_pdf_uses_its_versioned_item_columns 'tests/test_pdf_four_item_pages.py::test_four_products_per_physical_page_with_fixed_sections[5-purchase]' 'tests/test_pdf_four_item_pages.py::test_four_products_per_physical_page_with_fixed_sections[5-reagent_purchase]' 'tests/test_pdf_four_item_pages.py::test_purchase_orders_have_one_copy_and_invoices_keep_four[1-purchase]' 'tests/test_pdf_four_item_pages.py::test_purchase_orders_have_one_copy_and_invoices_keep_four[5-purchase]' 'tests/test_pdf_four_item_pages.py::test_purchase_orders_have_one_copy_and_invoices_keep_four[1-reagent_purchase]' 'tests/test_pdf_four_item_pages.py::test_purchase_orders_have_one_copy_and_invoices_keep_four[5-reagent_purchase]' -q --tb=short --show-capture=no --basetemp=/private/tmp/billing-po-delivery-m0ShqO/verified` — **54 passed**, one existing Starlette/httpx deprecation warning. Confirms saved/cleared dates, unchanged totals, header placement, no duplicate shipping date, other formats, copy policy and four-product pagination. `git diff --check` passed.
- One-item and five-item Domestic POs rendered to **one and two A4 pages**, with all three pages converted to PNG and visually inspected: date label/value fit the identity column, no clipping/overlap, and bank/totals/terms/signature/footer remain complete. Bundled `pdfplumber` verified each PDF page contains exactly one Expected Delivery Date and its value, and no Delivery Note Date. Synthetic-data demo: `output/pdf/purchase-order-delivery-date-demo.pdf`. Used the existing Chromium/PNG workflow; the PDF skill's artifact-marker helper is unavailable on this local runtime. No dependencies added.
- Reload/restart the backend if needed and generate a new Domestic PO PDF. Existing stored PDFs are not rewritten. No frontend build/unrelated full suite, migration, client database access, deployment, commit or push; no change-specific blocker. Stop after this approved presentation correction.

## Sales Invoice party-contact presentation — completed (2026-10-08)

- Applied the approved Sales-only PDF context correction: each buyer/consignee phone is shown under **Contact:** and its email under **Email:** on a separate line. Missing values omit only their own row. Vehicle No. and LR/Docket No. are no longer repeated in Consignee / Shipping Details; their existing Invoice Details rows and other shipment fields remain. New Sales PDFs use **`a4-invoice-v11`**. Reagent Bills and both PO mappings/versions are unchanged.
- Application change is limited to `backend/app/services/invoice_pdf.py`. Added real transaction/context/HTML/Chromium regressions in `backend/tests/test_bill_header_tax_layout.py` and updated the existing Sales version assertion in `backend/tests/test_invoice_pdf.py`. Updated billing context/reference notes and this status. HTML, both PDF CSS files, fonts, logos, page layout, calculations, forms, APIs and database schemas were not edited; template/CSS SHA-256 hashes match their starting values. Existing user changes and historical stored PDFs were preserved.
- Test-first checks reproduced five expected failures (joined phone/email, email-only wrongly labelled Contact, duplicate transport fields). After the mapping fix, the initial targeted subset passed **13 tests**. Final command from `backend/`: `./.venv/bin/python -m pytest tests/test_bill_header_tax_layout.py tests/test_invoice_pdf.py::test_versioned_invoice_template_contains_all_copies_and_reference_sections tests/test_invoice_pdf.py::test_sales_invoice_meta_shows_only_approved_transport_fields_in_order tests/test_invoice_pdf.py::test_short_sales_invoice_uses_42mm_table_and_one_page_per_copy tests/test_invoice_pdf.py::test_reagent_bill_pdf_uses_its_versioned_item_columns 'tests/test_pdf_four_item_pages.py::test_four_products_per_physical_page_with_fixed_sections[5-sales]' -q --tb=short --show-capture=no --basetemp=/private/tmp/billing-sales-party-KFt28e/verified` — **43 passed**, one existing Starlette/httpx deprecation warning. Includes optional contacts/emails, unchanged other formats, persisted snapshots, four copies, Sales identity order, table size and four-product physical pages. The first render-check run found only an unavailable `pdftotext` executable; tests now use the project's available `pdfinfo`/`pdftoppm` workflow, with PDF text checked separately using bundled `pdfplumber` (no new dependency).
- One-item and five-item Sales PDFs rendered to **4 and 8 A4 pages**, respectively; every page rasterized to PNG. Bundled `pdfplumber` verified all 12 pages contain each correct party phone/email and exactly one vehicle/LR value. Visually inspected the short page plus continuation/final long pages: independent contact/email rows, no duplicate transport, overlap or clipping; bank/totals/terms/footer remain intact. Demo with synthetic data: `output/pdf/sales-invoice-party-details-demo.pdf`. `git diff --check` passed. No unrelated full suite/frontend build, client database access, migration, deployment, commit or push.
- Reload/restart the backend if required and generate a new Sales PDF to see the change. Existing stored files are intentionally not rewritten. No change-specific blocker; stop after this approved presentation change.

## Shared invoice and purchase-order numbering — verified (2026-10-08)

- Confirmed the requested behavior already exists: Sales/Reagent share `Invoice.invoice_number` uniqueness, and Domestic/Reagent POs share `PurchaseOrder.purchase_order_number` uniqueness. Both families reject duplicate live numbers across document types; each type retains its own dashboard/register count. Existing manual entry, Indian financial-year prefixes, approval preservation, creation idempotency and deleted-number reuse remain intact. No application-code change or migration was necessary; no issued record was renumbered.
- Added PO regressions for both cross-type directions, normalized duplicate creation, duplicate draft edits, retry replay and independent register/dashboard counts. Extended the database-constraint race simulation to cross-type saves in both directions and the invoice regression to reject Sales reuse of a Reagent number. Files: `backend/tests/test_purchase_order_numbers.py`, `backend/tests/test_invoices.py`, `docs/BILLING_CONTEXT.md` and this status. Preserved all pre-existing user changes.
- Verification from `backend/`: `./.venv/bin/python -m pytest tests/test_purchase_order_numbers.py tests/test_invoices.py::test_sales_and_reagent_reject_shared_number_duplicates_and_replay_same_save tests/test_invoices.py::test_sales_and_reagent_share_manual_number_namespace_but_keep_separate_register_counts tests/test_invoices.py::test_draft_number_edit_keeps_the_suffix_when_financial_year_changes_and_rejects_conflicts tests/test_invoices.py::test_approved_invoice_number_uses_indian_financial_year_from_invoice_date tests/test_invoices.py::test_manual_numbering_preserves_historical_numbers_and_does_not_allocate_a_sequence tests/test_invoices.py::test_manual_invoice_numbers_are_unique_across_branches tests/test_invoices.py::test_invoice_number_counter_uses_postgresql_advisory_transaction_lock tests/test_bill_deletion.py::test_admin_can_reuse_generated_deleted_bill_number_as_a_new_save -q --tb=short --show-capture=no` — **28 passed**; one existing Starlette/httpx deprecation warning. Baseline subset also passed before test additions. These use isolated SQLite databases plus a PostgreSQL advisory-lock unit check; the missed-precheck test exercises a real unique constraint but is not a real parallel PostgreSQL test. Live PostgreSQL concurrency remains unverified in this task.
- `git diff --check` passed. PDF service, HTML and both PDF CSS files retain their exact starting SHA-256 hashes; frontend, PDF layout/formatting and financial code were not changed. No unrelated build/full suite, client database access, deployment, commit or push. No change-specific blocker; stop after this numbering verification.

## Reusing deleted invoice and PO numbers — verified and clarified (2026-10-08)

- Traced Admin deletion, unique-number checks, creation tombstones and frontend creation intents. Successful permanent deletion already removes the live number reservation. Verified real API submit→approve→generate→delete→new-save flows for Sales, Reagent Bill, Domestic PO and Reagent PO: Admin can enter the same number on a new document, new-save retries replay that new document, and another live duplicate is rejected. The deleted document's old save key remains blocked so delayed retries cannot accidentally recreate it. No numbering counter, deletion audit or financial/integration safeguard was removed or reset.
- Added explicit number-reuse guidance to the shared register deletion dialog/success message and the invoice/PO stale-save responses. Existing Start new bill/order already generates a fresh save key. Minimal deletion audit identifiers are retained for accountability, not number reservation. Preserved unrelated live documents, masters, PDF cleanup ownership and Admin-only deletion.
- Files: existing `backend/app/api/v1/invoices.py`, `backend/app/api/v1/purchase_orders.py` (error guidance only), `frontend/app/components/BillRegisterPage.tsx`; regression additions in `backend/tests/test_bill_deletion.py` and `frontend/scripts/bill_deletion.test.mjs`; billing context and this status. No service/model/schema, financial-calculation, PDF renderer/template/CSS/font/logo or migration change was necessary. All existing working-tree changes were preserved.
- Verification from `backend/`: `./.venv/bin/python -m pytest tests/test_bill_deletion.py tests/test_purchase_order_numbers.py tests/test_invoices.py::test_sales_and_reagent_reject_shared_number_duplicates_and_replay_same_save tests/test_invoices.py::test_manual_invoice_numbers_are_unique_across_branches -q --tb=short --show-capture=no` — **72 passed**, one existing Starlette/httpx warning. The four generated-document reuse regressions passed before any application change, confirming the existing release behavior; the new stale-save guidance regressions first failed, then passed. Covers permanent removal/file cleanup, permissions, dependencies, rollback, creation tombstones, fresh same-number saves, new retry idempotency and active-number uniqueness.
- From `frontend/`: `node --test scripts/bill_deletion.test.mjs` — **7 passed** against real rendered React components/handlers; `npm run type-check` and `npm run lint` — **passed**. `git diff --check` passed. SHA-256 hashes of the PDF service, HTML and both CSS files match the task's starting hashes. No unrelated full suite/production build or browser-server run was repeated; no live PostgreSQL integration/concurrency claim is made. Backend checks used isolated test databases and temporary PDF storage; the lifecycle renderer stub tests ownership/status, not PDF formatting.
- Restart/reload backend/frontend if needed. After successful deletion, choose **Start new bill/order** and enter the released Invoice No./PO No.; do not retry the deleted bill's old save. No migration, actual client-record deletion, live database access, deployment, commit or push. Existing financial/integration-linked bills remain non-deletable. No change-specific blocker remains.

## One PDF copy for both purchase-order types — completed (2026-10-08)

- Domestic Purchase Orders already generated one complete copy; verified and preserved that behavior. Reagent Purchase Orders now inherit the same single `Purchase Order` copy rather than creating four invoice-style copies. Sales Invoices and Reagent Bills retain all four existing labels. A PO with more than four products still spans multiple pages of its one copy; totals remain on the final product page.
- Application change is limited to the copy policy and Reagent PO version in `backend/app/services/invoice_pdf.py`: **a4-reagent-purchase-order-v13**. Domestic PO remains **a4-purchase-order-v8**; Sales and Reagent Bill versions are unchanged. Templates, CSS, fonts, logos, layouts, calculations, frontend/API/schema/model code and stored PDFs are unchanged. Updated relevant PO/copy/style tests and billing context/reference notes; preserved existing user changes.
- Test-first check reproduced the unwanted four Reagent PO labels. Final command from `backend/`: `./.venv/bin/python -m pytest tests/test_pdf_four_item_pages.py::test_purchase_orders_have_one_copy_and_invoices_keep_four tests/test_reagent_purchase_orders.py tests/test_pdf_reagent_quantity.py 'tests/test_pdf_four_item_pages.py::test_four_products_per_physical_page_with_fixed_sections[5-reagent_purchase]' 'tests/test_pdf_four_item_pages.py::test_four_products_per_physical_page_with_fixed_sections[5-purchase]' -q --tb=short --show-capture=no --basetemp=/private/tmp/billing-single-po-copy` — **40 passed**. Additional manufacturer/style fixture command `./.venv/bin/python -m pytest tests/test_pdf_name_description_style.py::test_reagent_secondary_line_labels_saved_manufacturer_without_empty_prefixes 'tests/test_pdf_name_description_style.py::test_style_fixtures_render_with_existing_format_specific_items[reagent_po]' -q --tb=short --show-capture=no --basetemp=/private/tmp/billing-single-po-style` — **3 passed**. Confirms both PO copy counts, unchanged four-copy invoice behavior, short/multi-page POs, stored PDF metadata, numeric/bold quantity and manufacturer formatting. Rendered PDFs to PNG and visually inspected both short POs plus the final page of a five-product Reagent PO. One existing Starlette/httpx warning remains; `git diff --check` passed. No unrelated full suite/frontend build was repeated.
- Restart/reload the backend and generate a new PO PDF. Previously finalized files retain their stored copies. No migration, client database access, historical rewrite, deployment, commit or push; no change-specific blocker.

## Bold reagent quantities at unchanged size — completed (2026-10-08)

- Made numeric item-table Quantity values bold in Reagent Bill and Reagent Purchase Order PDFs only, using inherited font size. Numeric-only formatting, alignment, saved units, Decimal calculations, Pack/Size, pagination and other bill types are unchanged. PDF CSS, frontend and API/model/schema code were not changed; existing working-tree changes and stored PDFs were preserved.
- Changed reagent Quantity markup in `backend/app/templates/invoice/v1/invoice.html` and version metadata in `backend/app/services/invoice_pdf.py`: **a4-reagent-bill-v13**, **a4-reagent-purchase-order-v12**. Added computed-style regressions to `backend/tests/test_pdf_reagent_quantity.py` and updated the existing reagent version assertion; updated billing context/reference notes.
- Test-first computed-style check failed at regular weight before the change. Final command from `backend/`: `./.venv/bin/python -m pytest tests/test_pdf_reagent_quantity.py tests/test_invoice_pdf.py::test_reagent_bill_pdf_uses_its_versioned_item_columns 'tests/test_pdf_four_item_pages.py::test_four_products_per_physical_page_with_fixed_sections[5-reagent]' 'tests/test_pdf_four_item_pages.py::test_four_products_per_physical_page_with_fixed_sections[5-reagent_purchase]' -q --tb=short --show-capture=no --basetemp=/private/tmp/billing-reagent-bold-quantity` — **19 passed**. Checks bold weight with unchanged computed font size, unchanged Sales/PO weight, numeric quantities and multi-page behavior. Both PDFs rendered to PNG and visually inspected; no clipping/overlap. One existing Starlette/httpx warning remains; `git diff --check` passed. No unrelated full suite or frontend build was repeated.
- Restart/reload the backend and generate a new PDF. Existing finalized files retain their saved formatting. No migration, client database access, deployment, commit or push; no change-specific blocker.

## Numeric-only reagent Quantity cells — completed (2026-10-08)

- Removed the unit/Per label from item-table Quantity cells in **Reagent Bills and Reagent Purchase Orders only**. Values still use the existing Decimal formatter: `12`, `0.125`, `1234.5`; no KG, GM, ML or other suffix. Saved units, unit entry, calculations, Pack/Size, column alignment and four-product pagination remain unchanged. Sales and Domestic PO PDFs retain their quantity/unit display. Existing stored PDFs were not rewritten.
- Changed only the reagent branch of shared `backend/app/templates/invoice/v1/invoice.html`, reagent version constants in `backend/app/services/invoice_pdf.py`, focused quantity tests and the affected existing version assertion. New versions: **a4-reagent-bill-v12**, **a4-reagent-purchase-order-v11**. Sales/PO versions, both PDF CSS files, API/model/schema/frontend code and existing working-tree changes were preserved. Updated billing context/reference amendments. No migration is needed.
- Test-first reproduction failed because the Quantity cell contained `12KG` rather than `12`. Final command from `backend/`: `./.venv/bin/python -m pytest tests/test_pdf_reagent_quantity.py tests/test_bill_header_tax_layout.py::test_real_render_cell_alignment_email_spacing_and_page_balance tests/test_invoice_pdf.py::test_reagent_bill_pdf_uses_its_versioned_item_columns 'tests/test_pdf_four_item_pages.py::test_four_products_per_physical_page_with_fixed_sections[5-reagent]' 'tests/test_pdf_four_item_pages.py::test_four_products_per_physical_page_with_fixed_sections[5-reagent_purchase]' -q --tb=short --show-capture=no --basetemp=/private/tmp/billing-reagent-numeric-quantity` — **19 passed**. Covers numeric/fractional quantity with KG/GM/ML/µg inputs, unchanged other formats, real Chromium PDF generation, one-page copies, computed alignment and five-product pagination. Both reagent PDFs were rendered to PNG and visually inspected: numeric-only Quantity, no clipping/overlap. One existing Starlette/httpx deprecation warning remains; `git diff --check` passed. No unrelated full suite/frontend build was repeated.
- Restart/reload the backend and preview/generate a **new** PDF. Existing finalized downloads keep their stored version. No client database, financial history, deployment, commit or push was touched. No change-specific blocker remains.

## Four-product physical PDF pages — completed (2026-10-08)

- Visually inspected all eight pages of `purchase-orders-30.pdf`: each copy put eight products on one page and moved bank/totals/terms to a product-free closing page. Corrected all four bill formats using complete physical page blocks of at most four products. Normal ten-item documents use 4/4/2 per copy; global serial numbers and existing copy labels are retained. Entry forms still accept more than four items.
- Repeat fixed identity/party/table/bank/terms/signature/footer content on each product page. Intermediate quantity, amount-in-words and document total/tax cells are blank; complete authoritative totals are on the final product page only. Removed the separate Reagent PO closing sheet, reserved the footer in layout, and equalized item/settlement depth across pages. Bounded Chromium fitting can reclaim empty table whitespace or split tall rows into smaller product groups; it cannot loop indefinitely. Impossible single-product/fixed-content combinations return actionable HTTP 422 without finalizing or storing a malformed PDF.
- Relevant changes: `backend/app/services/invoice_pdf.py`, shared invoice HTML/CSS, Reagent PO CSS, layout-error handling in existing invoice/PO PDF endpoints; `backend/tests/test_pdf_four_item_pages.py` plus affected existing PDF assertions. New versions: Sales **a4-invoice-v10**, Domestic PO **a4-purchase-order-v8**, Reagent Bill **a4-reagent-bill-v11**, Reagent PO **a4-reagent-purchase-order-v10**. No frontend, financial calculations, issued snapshots or existing stored PDFs were changed; all pre-existing working-tree changes were preserved.
- Verification: the original five-product regression failed before implementation; the initial corrected run passed **17** pagination checks. From `backend/`, `./.venv/bin/python -m pytest tests/test_pdf_four_item_pages.py tests/test_invoice_pdf.py tests/test_pdf_name_description_style.py tests/test_reagent_purchase_orders.py::test_reagent_po_pdf_fixtures -q --tb=short --show-capture=no --basetemp=/private/tmp/billing-four-final-check` passed **57** cases, with one remaining interstate fixture requiring row-whitespace reclamation and inspection of the actual normalized print HTML rather than its nominal pre-fit HTML. Both were corrected. Final command `./.venv/bin/python -m pytest tests/test_reagent_purchase_orders.py::test_reagent_po_pdf_fixtures tests/test_pdf_four_item_pages.py::test_oversized_pdf_returns_actionable_error_without_finalizing_bill -q --tb=short --show-capture=no --basetemp=/private/tmp/billing-four-verified-final` — **6 passed**, including that corrected 20-item IGST case and all four HTTP 422/no-finalization cases. The additional focused eight-item/long-product run passed both pagination cases, and the independent layout-error/subdivision run passed **5** checks. One existing Starlette/httpx deprecation warning remains. `git diff --check` passed.
- The related existing PDF/submission/state/party regression run passed **140** checks; its initial PDF failures were addressed and the affected cases rerun in the batches above. No full unrelated application suite or frontend build was rerun. Tests use isolated test databases, not the client database. Focused read-only review identified a singleton subdivision edge case; corrected it and added real Chromium PDF-boundary inspection and a successful long-product subdivision regression.
- Rendered test PDFs to PNG and visually inspected all four formats, intermediate/final eight-item Reagent PO pages, and final corrected 20-item IGST pages. Actual PDF text confirms twenty products paginate **4/4/4/4/4**, every page includes bank/terms/signature/footer, and amount-in-words/totals occur only on the fifth product page of each copy. The 10-item fixture was also independently verified as 4/4/2. A synthetic eight-item preview is available at `output/pdf/demo-four-items-per-page.pdf`; it contains test data, not a newly issued client bill.
- Activation: restart/reload the backend, then preview/generate a **new** PDF. No migration, reset, live/client database access, deployment, commit or push. Already stored finalized PDFs remain unchanged. Limitation: fixed text plus a single row must physically fit A4 at the retained font sizes; excessively large combined terms/addresses/descriptions produce the documented validation error, not an extra closing page. No unrelated frontend/full application checks were repeated.

## Seller State Code and State in every PDF header — completed (2026-10-07)

- Added separate **State Code:** and **State:** lines directly below both company emails in Sales, Reagent Bill, Domestic PO and Reagent PO headers. State names display in uppercase, matching the requested `State Code: 27` / `State: MAHARASHTRA` example. Values come from the seller, never the buyer/consignee/supplier or hardcoded reference details.
- Both document types use their saved `branch_state_code`. Invoices use the saved `seller_state`, with an existing-profile compatibility fallback only when state codes agree. POs do not have a separately saved seller-state name: use the current Seller/GST profile name only when its code matches the saved PO code, otherwise omit the unavailable name rather than pairing different states. No historical snapshot or stored PDF was rewritten. No migration is needed.
- Changes: `backend/app/services/invoice_pdf.py`, shared `backend/app/templates/invoice/v1/invoice.html`, new `backend/tests/test_pdf_seller_state.py` and affected version/complete-fixture assertions in `backend/tests/test_invoice_pdf.py`; billing context/reference amendment notes and this status. New versions: Sales **a4-invoice-v9**, Domestic PO **a4-purchase-order-v7**, Reagent Bill **a4-reagent-bill-v10**, Reagent PO **a4-reagent-purchase-order-v9**. Existing working-tree changes were preserved. Both PDF CSS files, fonts, logos, item widths/heights, calculations and frontend remain unchanged.
- Test-first Chromium check reproduced the missing header lines. Command from `backend/`: `./.venv/bin/python -m pytest tests/test_pdf_seller_state.py tests/test_bill_header_tax_layout.py tests/test_po_seller_panels.py -q --tb=short --show-capture=no --basetemp=/private/tmp/billing-seller-state-header` — **34 passed**. Eight state/format cases render PDF then PNG, check email→code→state order and four-copy short-page counts, retained saved codes after profile changes and no wrong-state fallback. Visually inspected the Maharashtra PNG for each of all four formats: new rows aligned, no clipping/overlaps or extra short pages.
- Existing PDF regression command `./.venv/bin/python -m pytest tests/test_invoice_pdf.py tests/test_reagent_purchase_orders.py tests/test_pdf_name_description_style.py -q --tb=short --show-capture=no` passed **47** cases (including short/long rendering); one older `SimpleNamespace` PO fixture lacked the model's existing state-code fields. Added the actual saved/profile fields to that fixture and reran `tests/test_invoice_pdf.py::test_purchase_order_context_renders_a_separate_document_title_and_metadata` — **1 passed**. An additional real-render/state/header run passed all **12** renderer cases; its same stale-fixture failure was resolved by this final targeted rerun. One existing Starlette/httpx warning remains. `git diff --check` passed. No unrelated full-suite or frontend build was repeated for this PDF-only change.
- Restart/reload the backend and generate a new PDF to see these lines; finalized downloads retain their original stored file. No client database, deployment, commit or push was touched. The four-product-per-page pagination request below remains pending its bank/terms/signature repetition confirmation and was not implemented in this header-only task. No header-specific blocker remains; PO state-name snapshot limitations are stated above.

## Four-product PDF pages for all bill types — earlier design pause, superseded (2026-10-07)

- Current request covers Sales Invoice, Reagent Bill, Domestic PO and Reagent PO PDF pagination: at most four product lines per physical page, with full document quantity/tax/final-total values only on the page containing the last product. Earlier pages retain an empty quantity/calculation table. Entry forms must still accept more than four products per document; this is not a document-level limit.
- Read-only inspection confirmed the shared HTML currently renders one continuous item table per copy, and long Reagent POs can put their settlement/closing block on a separate sheet. Proposed change: explicit complete page blocks (e.g. ten products → 4/4/2 per copy), repeated fixed identity/party/table/closing sections, and no separate product-free totals page. Preserve financial calculations, historical PDFs, current styling and all four copy labels.
- This earlier design-only pause is superseded by the client's explicit 2026-10-08 correction above: repeat fixed sections on product pages and do not create a separate closing sheet. No PDF/application code, database, migration, tests or rendered outputs were changed in the earlier design turn.

## Remove purchaser/buyer entry from both PO forms — completed (2026-10-07)

- Removed Domestic PO **Purchaser company** and Reagent PO **Purchaser / buyer details**, including their fields, manual/saved controls, searches and save-for-future options. Removed purchaser-master loading and purchaser fields from both form payloads/validation. Seller is entered/selected once and Seller / Shipping Address remains its matching read-only panel; phone and email remain separate. Other entry fields, seller recovery, line items, approval controls and PDF presentation were preserved.
- Removed the Reagent PO schema's purchaser-required check so preview/save work without the removed section. Both models already support nullable purchaser columns; no migration or fabricated hidden purchaser is needed. Reagent place-of-supply validation and Domestic supplier-state GST calculation are unchanged. Full-details edits now update purchaser linkage/snapshot only when purchaser fields are explicitly supplied: omission preserves historical values, while compatible explicit-null clearing remains available for editable documents. Purchaser masters/APIs and previously saved records were not deleted.
- Relevant application files: `frontend/app/purchase-orders/page.tsx`, `frontend/app/reagent-purchase-orders/page.tsx`, `backend/app/schemas/purchase_order.py`, `backend/app/api/v1/purchase_orders.py`. Added `backend/tests/test_po_optional_purchaser.py`; updated the obsolete missing-purchaser validation expectation to missing-place-of-supply and affected browser fixtures. Updated billing context and this status; preserved all pre-existing working-tree changes.
- Test-first checks reproduced the visible purchaser controls, Reagent preview's purchaser-required error and purchaser snapshot loss on an omitted-fields edit. Final backend command from `backend/`: `./.venv/bin/python -m pytest tests/test_po_optional_purchaser.py tests/test_purchasers.py tests/test_reagent_purchase_orders.py tests/test_inline_submission.py -q --tb=short --show-capture=no` — **90 passed**, one existing Starlette/httpx deprecation warning. Covers no-purchaser preview/create/idempotent retry/edit/approval, stable totals, no fabricated purchaser master, historical snapshot preservation, explicit-null clearing, existing master validation/workflow and real PDF preview/rendering.
- Frontend `npm run lint`, `npm run type-check` and isolated production `npm run build` — **passed**. Browser scripts using fixture APIs on the built test server all **passed**: `verify_po_seller_entry_ui.py` (four manual/saved PO cases, removed fields absent from UI/payload, matching seller/shipping, mobile); `verify_po_seller_retry_ui.py` (both lost-response recovery cases); `verify_reagent_purchase_order_ui.py` (seller-only entry, conflict reload and preview/confirmation); `verify_manual_po_number_ui.py` (Domestic numbering/retry); `verify_bill_submission_ui.py` (all four bill types across Admin/Manager/Staff). Browser commands from `frontend/`: `../backend/.venv/bin/python scripts/<script-name>`. Focused read-only review found no material issues; `git diff --check` passed.
- No migration is required. Refresh the frontend and reload/restart the backend if it is not using automatic reload. PDF renderer, templates and CSS SHA-256 hashes match the start of this task; stored PDFs and financial history are unchanged. No client database, deployment, commit or push was accessed/performed. Validation used isolated test databases and mocked browser API fixtures, not new live-PostgreSQL guarantees. The full unrelated backend suite was not repeated for this scoped follow-up. No feature-specific blocker remains.

## Matching PO entry forms to Seller / Shipping Address — completed (2026-10-07)

- Updated Domestic Oils and Reagent PO entry pages only: bold **Seller** and **Seller / Shipping Address** headings; one selected/manual seller identity automatically mirrored into the shipping panel; separate **Contact (phone)** and **Email** inputs with inline API validation errors. Saved seller fields and post-save identity are read-only. Required purchaser records remain clearly separate; existing historical consignee snapshots, financial calculations, revision checks and approval rules are preserved. Removed the misleading independent Reagent consignee-entry controls for new orders.
- Fixed the Domestic PO save payload silently choosing the default supplier instead of the seller shown in the form. Both manual entry and saved-seller selection now reach preview/create/update through the existing interfaces. Accessible field names remain stable when validation messages appear; retained same-intent idempotency keys on retries and responsive layout. A focused review also found a lost-response edge case: if creation committed before the seller was changed locally, recovery now restores only the persisted fixed seller while retaining other unsaved fields, allowing the same order to be saved again without duplicate creation.
- Relevant files: `frontend/app/purchase-orders/page.tsx`, `frontend/app/reagent-purchase-orders/page.tsx`, shared `frontend/app/components/PurchaseOrderSellerFields.tsx`; new `frontend/scripts/verify_po_seller_entry_ui.py`, `frontend/scripts/verify_po_seller_retry_ui.py` and updated existing PO/submission browser fixtures. Updated billing context and this status. All pre-existing working-tree changes were preserved.
- Verification: test-first browser check reproduced missing Seller/mirror behavior. `npm run lint`, `npm run type-check`, `npm run build` **passed** on an isolated copy of the frontend; no running development build was overwritten. Browser commands from `frontend/`, using the built test server at `http://127.0.0.1:3100`: `../backend/.venv/bin/python scripts/verify_po_seller_entry_ui.py` **4 manual/saved PO scenarios passed**; `../backend/.venv/bin/python scripts/verify_reagent_purchase_order_ui.py` **passed** (saved selection, reload/version-conflict recovery, preview/confirmation, mobile); `../backend/.venv/bin/python scripts/verify_bill_submission_ui.py` **passed for all four bill types and Admin/Manager/Staff** (same-draft edits, retries, preview, download/print and mobile). Browser APIs used isolated fixtures, not client data.
- Backend command from `backend/`: `./.venv/bin/python -m pytest tests/test_purchasers.py tests/test_inline_submission.py tests/test_reagent_purchase_orders.py -q --tb=short` — **86 passed**, one existing Starlette/httpx deprecation warning. The first sandbox run passed 80 tests but blocked Chromium in six renderer tests; the permission-approved rerun passed all 86. These existing tests use isolated test databases; this does not establish new live-PostgreSQL guarantees. No client database was accessed.
- Review follow-up verification: `../backend/.venv/bin/python scripts/verify_po_seller_retry_ui.py` **passed for both PO forms**, after first reproducing the frozen incorrect seller. The test simulates a committed-but-lost creation response, a changed seller and other edited terms: the original key/document is recovered, the persisted seller is restored, other edits remain, and saving can resume without a second order. Existing first-save manual/saved identity modes remain intact; displayed saved identities use transaction snapshots rather than refreshed master values.
- No migration or backend restart is needed for this frontend change. Refresh the frontend (restart/rebuild only if not running development mode). PDF renderer, HTML, shared CSS and Reagent PO CSS SHA-256 hashes are unchanged from the start of this task; stored PDFs/metadata and Sales/Reagent invoice screens are unchanged. No deployment, commit or push. Existing broader limitations remain documented below; no feature-specific blocker remains.

## Matching PO seller panels and separate contact/email — completed (2026-10-07)

- Both Domestic Oils and Reagent PO PDFs now use the order's saved supplier/seller snapshot for **Seller** and **Seller / Shipping Address**: the same company name, postal address, GSTIN, state code, PAN, phone and email. Later supplier-master edits do not replace those values. Reagent shipping transport metadata remains on the right; Vehicle No. stays in Invoice Details. Saved purchaser/consignee fields, revision history and tax calculation are preserved independently and were not rewritten.
- Panel headings and seller company names are bold. PO `Contact:` contains phone only and `Email:` is its own row; either absent value is omitted independently. Inspection confirmed both entry pages already use separate phone/email inputs and database columns, so no frontend, schema or API changes were needed. Added a compatible optional email field to the existing PDF party context. Reagent PO's party-line spacing was compacted just enough to fit the added identity/contact rows in the tested short page while retaining the 64 mm item body.
- Application changes: `backend/app/services/invoice_pdf.py`, shared invoice HTML/CSS and existing Reagent PO CSS. New versions are Domestic PO **a4-purchase-order-v6** and Reagent PO **a4-reagent-purchase-order-v8**. Sales **a4-invoice-v8** and Reagent Bill **a4-reagent-bill-v9** retain their formatting/version and original party mapping. Existing stored PDF files/checksums/metadata are untouched. Added `backend/tests/test_po_seller_panels.py` and updated affected PDF snapshot/name/version assertions; updated billing context/reference notes and this status. Preserved existing dirty user changes.
- Test-first checks reproduced the combined phone/email value. Initial full-contact Reagent PO overflowed; the scoped spacing correction restored a complete short page. Final command from `backend/`: `./.venv/bin/python -m pytest tests/test_po_seller_panels.py tests/test_reagent_purchase_orders.py tests/test_invoice_pdf.py tests/test_pdf_name_description_style.py tests/test_inline_submission.py::test_pdf_preview_returns_inline_bytes_from_saved_snapshot_without_any_billing_writes tests/test_purchasers.py tests/test_bill_header_tax_layout.py::test_real_render_cell_alignment_email_spacing_and_page_balance tests/test_billing_entry_flow.py::test_saved_purchase_order_can_generate_previewable_downloadable_pdf -q --tb=line --show-capture=no --basetemp=/private/tmp/po-seller-panels-regression` — **68 passed**, one existing Starlette warning. Covers matching seller snapshots after master changes, independent missing phone/email values, real bold font weights, short-page fit, long Reagent PO pagination/footer pixels, unchanged Sales/Reagent Bill presentation, preview immutability and purchaser persistence. Both full-contact short PO PDFs were rendered to PNG and visually inspected. `git diff --check` — **passed**.
- No new migration is needed. Restart/reload the backend and generate a new PO PDF to see the change; previously finalized downloads keep their existing stored PDF. No client database, financial calculator, authentication, deployment, commit or push was changed. Full-suite/frontend builds were not repeated for this PO-only PDF correction; existing broader limitations remain documented below. No feature-specific blocker remains.

## Item Description left alignment in all four bill PDFs — completed (2026-10-07)

- Applied the client's requested left alignment to Item Description / Item Details values in Sales, Domestic Oils PO, Reagent Bill and Reagent PO. Product names, secondary descriptions and reagent MFG/article/GST text follow the left edge. Headings remain centered, other item values remain centered, and Amount values remain right-aligned. Existing fonts, spacing, widths, calculations, entry forms and pagination were preserved.
- Changes are limited to scoped shared PDF CSS, template-version metadata and the corresponding Reagent PO closing-block version checks. New versions: Sales `a4-invoice-v8`, Domestic PO `a4-purchase-order-v5`, Reagent Bill `a4-reagent-bill-v9`, Reagent PO `a4-reagent-purchase-order-v7`. Existing saved PDFs and metadata are untouched. Updated alignment regressions, existing version assertions, billing context/reference correction notes and this status. Existing working-tree changes were preserved.
- Test-first Chromium checks failed for centered descriptions in all four formats before the correction. Final command from `backend/`: `./.venv/bin/python -m pytest tests/test_bill_header_tax_layout.py::test_real_render_cell_alignment_email_spacing_and_page_balance tests/test_invoice_pdf.py tests/test_pdf_name_description_style.py tests/test_reagent_purchase_orders.py::test_reagent_po_pdf_fixtures tests/test_invoices.py::test_approved_invoice_generates_downloadable_pdf_and_persists_metadata tests/test_invoices.py::test_pdf_generated_status_transition_is_recorded tests/test_billing_entry_flow.py::test_saved_purchase_order_can_generate_previewable_downloadable_pdf -q --tb=line --show-capture=no --basetemp=/private/tmp/billing-description-left-final` — **43 passed**, one existing Starlette warning. Covers actual computed left alignment and nested text, unchanged heading/numeric alignment, wrapping, one/six/twenty/eighty-item PDF cases, both GST modes, short/long Reagent PO layout and generated version metadata. Rendered all four short PDFs to PNG and visually checked the new alignment. `git diff --check` — **passed**.
- No schema change or new migration is needed. Restart/reload the backend and generate a new PDF to see the change; existing finalized downloads retain their stored file. No frontend, client database, authentication, infrastructure, deployment, commit or push was changed. No full backend suite/frontend build was repeated for this narrowly scoped presentation correction; the previous full-suite limitations remain documented below. No feature-specific blocker remains.

## Four-format PDF layout and optional second seller email — completed (2026-10-07)

- Implemented the client's requested changes for Sales Invoices, Reagent Bills, Domestic Oils Purchase Orders and Reagent Purchase Orders. Their headers show company emails on consecutive safely wrapping lines instead of Pickup Address; company/buyer/supplier/shipping postal blocks start with **Add:**. Pickup selection and its saved transaction data remain available. All item values are centered except the right-aligned Amount cell.
- Added optional **Second email** to Seller/GST profile, its validated APIs and the existing Admin-only audit path. New invoices and POs snapshot both emails at creation, including intentionally empty values. Profile edits, draft edits and approval do not replace those snapshots. Legacy null snapshots keep the previous primary-email fallback and do not infer/backfill a second email. Omitted profile-update fields preserve the existing second email; explicit null clears it.
- Both reagent PDFs move Vehicle No. to the last Invoice Details row and omit it from shipping. Product names are larger/bold with a **1.3 mm** gap before their smaller regular MFG/article line. Removed Per from the PDF item table, retained units with Quantity, and transferred its **4%** width to Disc % (**10%**). Discount cells show the saved Decimal discount amount in bold below the percentage with an **@** prefix. Unit entry/calculations remain functional.
- Both PO PDFs now label the saved supplier panel **Seller** and destination panel **Seller / Shipping Address**, preserving their independent transaction details. Reagent PO's short item body is **64 mm**, matching Reagent Bills and lowering bank/quantity details. Compact PO metadata/shipping spacing and omission of empty IRN blocks retain a one-page short copy; long copies retain repeated item headings and their final settlement/terms/signature/footer page.
- Tax summaries show saved amounts with the applicable percentage labels: e.g. **SGST @ 9%**, **CGST @ 9%**, or **IGST @ 18%**. IGST does not create CGST/SGST rows. Mixed-rate labels list distinct applicable rates against the existing aggregate, e.g. **SGST @ 2.5%, 9%**; half-rate display retains exact precision. Calculators, stored financial amounts, tax selection by place of supply and accounting policy were not changed. No manual tax-amount override was introduced.
- New template versions: Sales **a4-invoice-v7**, Domestic PO **a4-purchase-order-v4**, Reagent Bill **a4-reagent-bill-v8**, Reagent PO **a4-reagent-purchase-order-v6**. Existing stored PDF files, checksums and generation metadata are not regenerated or rewritten. Only explicitly requested PDF presentation and the required seller-email data path were changed; existing dirty user changes were preserved.

### Relevant files and activation

Existing backend company/invoice/PO models, branch/company schemas, company/invoice/PO save APIs, `app/services/invoice_pdf.py`, shared invoice HTML/CSS and Reagent PO CSS; frontend Seller/GST profile page and Branch type. Regressions: `tests/test_bill_header_tax_layout.py`, seller-profile tests and updated existing PDF assertions; `frontend/scripts/verify_seller_email_ui.py`. Updated billing context/reference-deviation notes and this status.

Forward migration **20261007_0024_seller_secondary_email.py** follows **20261006_0023**, adding nullable `branches.secondary_email` and JSON email-snapshot columns on invoices/POs. It has no historical backfill or reset and **has not been applied to the client database**. Before starting the updated backend:

```sh
cd /Users/anujmishra/Developer/Pristine_Bio_billing/backend
./.venv/bin/python -m alembic upgrade head
```

Restart the backend/frontend, set the optional second email under Seller/GST profile, and generate a new PDF. Existing finalized PDF downloads retain their saved version. No client database, production infrastructure, deployment, commit or push was accessed.

### Verification evidence

- Superpowers test-first checks reproduced missing second-email persistence/validation, incorrect tax labels and missing reagent Vehicle No. metadata before implementation. Initial fixture input mistakes were corrected before assessing behavior. The initial enlarged Reagent PO short copy overflowed; compact spacing corrected it, and the final short-copy and long-copy checks passed.
- Complete backend command: `./.venv/bin/python -m pytest -q --tb=line --show-capture=no --basetemp=/private/tmp/billing-all-oct07` — **508 passed, 2 pre-existing MFA failures, 8 PostgreSQL checks skipped**. Failures: `test_privileged_mfa_enrollment_and_recovery_full_lifecycle` (disabled-MFA policy versus old test) and `test_mfa_recovery_replacement_and_administrative_reset` (existing missing `UserRole` import in `account_security.py:172`). Authentication is outside this request and was not repaired.
- Final scoped command after adding email-audit and PDF-footer pixel checks: `./.venv/bin/python -m pytest tests/test_bill_header_tax_layout.py tests/test_seller_profile.py tests/test_reagent_purchase_orders.py::test_reagent_po_pdf_fixtures -q --tb=line --show-capture=no --basetemp=/private/tmp/billing-oct07-final` — **33 passed**. Covers all four modes, both GST regimes, mixed rates, authoritative totals, email preservation across approval/master changes, intentional empty/legacy snapshots, Admin-only edits, validation, omitted/null updates, before/after audit, isolated forward migration, actual Chromium alignment/spacing, A4 page counts and raster-painted final footer. No repeated full-suite run was required because no production code changed after the complete run.
- Offline PostgreSQL migration command `./.venv/bin/python -m alembic upgrade 20261006_0023:head --sql` — **passed**, transactional DDL/version advancement. Isolated SQLite migration test preserved issued PDF references and financial values and left new columns null. Real PostgreSQL migration execution remains unverified; `TEST_SECURITY_DATABASE_URL` is unset.
- Frontend `npm run lint`, `npm run type-check` — **passed**. An isolated production `npm run build` with `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1` — **passed**, 30 routes; the client's running `.next` directory/processes were not changed. `FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_seller_email_ui.py` — **passed** against that built frontend, verifying second-email save/reload/clear, related field errors with retained input and 390px layout. Browser API responses are isolated fixtures; real persistence/permissions are covered by backend tests. The temporary frontend server was stopped.
- All four short PDFs rendered to PNG and were visually reviewed; the full-data short Reagent PO and long IGST PO continuation/final sheets were also checked. One, six, twenty and eighty items plus long text, both taxes and stored metadata remain covered by the existing passing PDF tests. Every inspected short copy is a complete page, with centered values, email lines, tax labels, bank/terms/signature and green footer. One existing Starlette deprecation warning remains. `git diff --check` — **passed**.

No feature-specific blocker remains. Local activation requires the forward migration/restarts above. Stop after this requested four-format update.

## Reagent Purchase Order supplier panel and title — completed (2026-10-07)

- The Reagent PO entry page now labels its party section **Supplier Details**, allows the bill maker to choose an active saved supplier by name, and shows its company name, full address, state code, GSTIN, PAN, phone and email. The current default supplier prefills new orders; manual entry remains available. Starting a new order clears the prior search. A saved order displays its transaction snapshot and keeps its supplier fixed, matching the existing backend update rule. Purchaser/consignee fields and other bill entry pages are unchanged.
- The Reagent PO PDF now shows that saved supplier snapshot in its left **Supplier Details** panel, including state code; the right **Consignee / Shipping Details** panel remains separate. Its top title and continuation identity say **Purchase Order**. Standard terms appear once; bottom terms/signature placement, item table, tax data, four copies and other document formats are preserved. New Reagent PO PDFs use version **`a4-reagent-purchase-order-v5`**. Existing stored PDFs are not rewritten or reissued.
- Application files: `frontend/app/reagent-purchase-orders/page.tsx`, `frontend/app/lib/types.ts`, `backend/app/services/invoice_pdf.py` and `backend/app/templates/invoice/v1/invoice.html`. Regressions: `frontend/scripts/verify_reagent_purchase_order_ui.py`, `backend/tests/test_reagent_purchase_orders.py`, `backend/tests/test_inline_submission.py`. Updated this status and billing context. No schema or migration is needed; no client database, deployment, commit or push was touched.

### Verification

- Test-first checks reproduced the wrong buyer heading in the PDF and absence of the saved-supplier selector in the browser. A saved-master regression verifies supplier identity, address, state code, tax/contact fields, a separate consignee and snapshot stability after the master changes. Resetting supplier search was also reproduced as a failing browser check before its fix.
- `./.venv/bin/python -m pytest tests/test_reagent_purchase_orders.py -q --tb=line --show-capture=no` — **14 passed**; the saved-snapshot inline preview checks were rerun after updating their old purchaser-panel expectation — **8 passed**. One item and twenty item PDF fixtures rendered through Chromium to **4 and 12 A4 pages**; all pages were converted to PNG. Short first page, long first page and final long page were visually inspected for the title, supplier details, state code, totals, terms and footer. One existing Starlette deprecation warning remains.
- Frontend `npm run lint`, `npm run type-check`, `node --test scripts/*.test.mjs` — **passed** (33 Node tests); an isolated production `npm run build` — **passed**, 30 routes. The Reagent PO browser regression passed against that isolated build, covering selection of a nondefault saved supplier, every displayed supplier field, submitted supplier ID, saved-snapshot display, save retries, conflict recovery, approval/PDF actions, search reset and 390px width.
- The first complete backend run, before correcting the two inline preview assertions, reported **480 passed, 4 failed, 8 skipped**: two expected failures for the changed Reagent PO panel and two pre-existing unrelated MFA failures (`test_privileged_mfa_enrollment_and_recovery_full_lifecycle` and `test_mfa_recovery_replacement_and_administrative_reset`). The two related preview cases passed in the targeted rerun. PostgreSQL-only tests are skipped without `TEST_SECURITY_DATABASE_URL`; no PostgreSQL integration claim is made.
- Final broad backend command: `./.venv/bin/python -m pytest -q --tb=line --show-capture=no -k 'not test_privileged_mfa_enrollment_and_recovery_full_lifecycle and not test_mfa_recovery_replacement_and_administrative_reset'` — **482 passed, 8 skipped, 2 known MFA cases deselected**, one Starlette warning. This confirms the Reagent PO assertion update left no other backend regression. The two MFA tests were not repaired because authentication is outside this request.

### Limits / activation

The saved-supplier picker filters the bounded list returned by the existing supplier API (first 100); manual supplier entry remains possible for suppliers outside that list. Supplier identity cannot change after a PO is saved under the existing backend rule. Restart/reload the backend and frontend, then generate a **new** Reagent PO PDF to see the updated title and supplier panel. No migration is required. Stop after this Reagent PO-only change.

## Permanent deletion in all four bill registers — implemented (2026-10-06)

- Implemented the client's approved deletion policy for **Sales, Domestic Oils Purchase, Reagent Bills and Reagent Purchase Orders**, including finalized but otherwise unlinked bills. Admin sees Delete beside View; Staff and Manager do not, and the backend independently denies them. Confirmation requires the exact full bill number, document type and currently reviewed version. Cancel/Escape does not delete; duplicate clicks are suppressed and server errors remain visible without claiming success.
- Added authenticated, CSRF-protected `DELETE /api/v1/invoices/{id}` and `DELETE /api/v1/purchase-orders/{id}`. The transaction locks the document, checks authorization/version/confirmation, preserves masters, and permanently removes its owned lines, workflow audits and revision snapshots. Any receipt-allocation history, including reversals, or any outbound integration record blocks invoice deletion. Other foreign-key dependencies fail safely rather than cascading unrelated financial history.
- A minimal independent `SecurityAudit` records actor, UTC timestamp, branch, number, type, version and previous status; it does not retain addresses, item details or financial amounts. Original creation keys become tombstones: an identical replay receives **410 `bill_deleted`**, a changed payload remains **409**, and an exact repeated DELETE is safe. A fresh key remains a distinct new creation intent; automatic recreation by an old retry is prohibited.
- Only explicitly referenced PDF files from the document/current or owned revision snapshots are eligible for removal. Unsafe paths, symlinks and references shared by another bill/current or historical revision block deletion. Database deletion and the audit/tombstones commit **before** filesystem cleanup. Cleanup failure returns **503 `pdf_cleanup_pending`**, retains a durable exact-file plan, and instructs retry with the same number/version/type; success is shown only after cleanup completes. Unreferenced/orphan files are not inferred from filenames or removed. Downloaded copies and backups are outside deletion scope.
- Registers reload and repair an emptied last page after success; the deleted PDF view closes. Matching retained Sales/Reagent entry sessions are invalidated in the same tab and other same-origin tabs, and an open deleted entry remounts as a fresh form instead of writing to a disposed session. The broadcast contains only the document ID, no bill fields. Unrelated unsaved entries remain intact. Dashboard metrics continue to use backend data on their next load.
- Backend files: `app/services/bill_deletion.py`, invoice/PO API routes and models, `models/authentication.py`, `schemas/common.py`, `tests/test_bill_deletion.py`, and migration **`20261006_0023_bill_deletion_tombstones.py`**. Frontend files: shared `BillRegisterPage.tsx`, `InvoiceEntryPage.tsx`, `invoiceEntrySession.ts`, deletion Node/browser regressions. Updated this status and billing context. Existing dirty working changes were preserved; no application auth policy, financial calculator, PDF renderer, template, CSS, font, logo, pagination or print interface was modified.

### Migration / local activation

Migration `20261006_0023` adds nullable `deleted_at` to the two creation-request tables and a security-audit lookup index. It has no historical backfill or database reset. **It has not been applied to the client database.** Before using the updated backend, back up normally and run:

```sh
cd /Users/anujmishra/Developer/Pristine_Bio_billing/backend
./.venv/bin/python -m alembic upgrade head
```

Restart the backend and frontend using the existing local startup commands. Deletion then appears in the four dashboard-linked bill registers for a signed-in Admin. No production deployment, Docker startup, commit or push was performed.

### Verification

- Test-first backend deletion regressions reproduced missing endpoints and later identified shared-revision PDF ownership and stale creation-replay defects, corrected before completion. Final command from `backend/`: `./.venv/bin/python -m pytest tests/test_bill_deletion.py tests/test_financial_correctness.py tests/test_inline_submission.py tests/test_bill_register_dates.py -q --tb=line --show-capture=no` — **154 passed**, including **48 deletion tests**, with one existing Starlette warning. Covers all four types, role checks, validation, stale versions, masters/children/audit, original-key tombstones, dependency blockers, database rollback, safe file ownership, cleanup retries and existing financial/PDF interfaces. Every deletion test now uses an isolated SQLite database and temporary PDF directory.
- Full backend command `./.venv/bin/python -m pytest -q --tb=line --show-capture=no`, run before the final six additional ownership/replay guard tests, reported **475 passed, 2 pre-existing unrelated failures, 8 skipped**. Failures remain `test_privileged_mfa_enrollment_and_recovery_full_lifecycle` (old mandatory-MFA assertion versus disabled-MFA policy) and `test_mfa_recovery_replacement_and_administrative_reset` (existing missing `UserRole` import at `account_security.py:172`). Final scoped tests were rerun after review fixes. Authentication was deliberately not changed.
- PostgreSQL-only checks remain skipped because `TEST_SECURITY_DATABASE_URL` is unset. SQLite coverage does **not** establish PostgreSQL row-lock/concurrent-deletion guarantees. Offline PostgreSQL migration check `./.venv/bin/python -m alembic upgrade 20261005_0022:head --sql` — **passed**, including transactional DDL/index/version advancement; actual migration execution/rollback on a dedicated PostgreSQL database remains unverified.
- Frontend `node --test scripts/*.test.mjs` — **33 passed**; `npm run lint`, `npm run type-check`, `npm run build` — **passed**, with 30 routes produced. A fresh isolated copy of the final frontend source also passed the production build. Its temporary verification server did not modify or stop the client's running servers.
- `FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_bill_deletion_ui.py` — **passed** against that fresh build: all four Admin registers at 390px, exact confirmation, Cancel/Escape and focus restoration, inert background controls, visible server failures, duplicate-click suppression, cleanup-pending retry with an empty-body 204, PDF-view closure, last-page/count repair, Staff/Manager button restrictions, and both Sales/Reagent two-tab retained-session invalidation followed by fresh editable draft creation. Unknown API requests are aborted; fixtures never delete client bills. No backend integration claim is inferred from mocked browser data.
- Initial browser attempts exposed conflicting shared development/production `.next` artifacts (500 missing vendor chunk) and a stale build without the final remount recovery. Rebuilt a temporary source copy at `/private/tmp/billing-delete-verify.WdC2Xt` instead of altering the client's running processes; final complete verification passed. The modal focus assertion was corrected after proving native Tab may visit browser chrome while page controls remain inert; no JavaScript focus-trap behavior was added. Temporary verification servers were stopped after checks.
- PDF implementation before/after SHA-256 matches for `app/services/invoice_pdf.py`, shared invoice HTML/CSS and Reagent PO CSS. Targeted `git diff --check` passed. Existing renderer tests needed a permitted Chromium launch after the sandbox denied it; the permitted final targeted run passed. These assertions concern implementation files, **not** the storage incident below.

### Storage-test incident and limitations

An early draft-deletion test mistakenly used the configured PDF folder rather than a temporary folder. At that point the first implementation inferred old PDFs by `invoice-1-*.pdf` filenames, so it **may have removed previously stored invoice-1 PDF artifacts** despite using an isolated test database. There is no before-test file inventory, so actual file loss cannot be established or ruled out. This was disclosed to the client immediately. A subsequent explicitly permitted **read-only** local PostgreSQL check found **no invoice record with ID 1**; no client database row was deleted, updated or migrated by this work. Archived/orphan-file impact remains uncertain and no recovery has been claimed.

Corrected all deletion tests to mandatory temporary storage and removed filename-based ownership inference from the implementation. It now removes only explicit current/owned-revision references and protects other bills' references, with regressions for unrelated files even when their filename shares the deleted ID. No automated restoration, PDF regeneration, historical rewrite or orphan sweep was attempted. Restoring any affected artifact requires an identified backup and explicit direction. Large legacy revision histories and multi-worker cleanup races have not been load-tested; there is no background cleanup worker. Stop after this approved deletion feature; no further phase is authorized.

## Sales/Reagent register links and navigation-retained entry sessions — completed (2026-10-06)

- Added top-right **Sales invoices** → `/bill-registers/sales` and **Reagent bills** → `/bill-registers/reagent` links using the existing header/button styling. Existing date-wise registers and view actions are reused; no embedded recent lists, new routes or backend list requests were introduced.
- Preserved each authenticated user's Sales/Reagent entry independently in same-tab application memory: manual/saved modes, buyer/consignee fields, selected supplier (including explicit no-supplier), invoice numbering/dates, transport/charges, dynamic line items, manufacturer/article/pack data and field errors. Necessary masters and live backend totals reload on return without replacing transaction fields.
- Retained saved draft ID/version/signature, original creation retry key/payload and in-flight busy state. An uncertain creation is replayed before changed input updates the original draft. A save completing after navigation updates that same session. Departure revokes the local PDF blob; returning to an editable draft requires a fresh preview before Confirm.
- **Start new bill** resets only the current kind, with confirmation for unsaved input; it never deletes server drafts. Successful logout/account change/disable clears both retained sessions even when entry pages are absent; disposed sessions reject late local writes. Failed logout and same-user reauthentication retain work. PO behavior remains local and unchanged.
- Application files: `frontend/app/components/InvoiceEntryPage.tsx`, `BillSubmissionPanel.tsx`, `frontend/app/lib/useBillSubmission.ts`, and new `invoiceEntrySession.ts`. Added `frontend/scripts/invoice_entry_session.test.mjs` and `verify_invoice_navigation_ui.py`; updated billing context and this status. Existing dirty working code was preserved. No migration, dependency, API/authentication policy, financial-calculation or backend change is needed. No client database, Docker, deployment, commit or push was used.

### Verification

- Test-first browser checks reproduced lost fields for **both** Sales and Reagent before implementation. The new helper's four tests initially failed because the implementation was absent, then passed. Final full frontend command from `frontend/`: `node --test scripts/*.test.mjs` — **24 passed**. Covers independent sessions, shared retry/document identity, type-scoped reset, stale writes, reauthentication, off-page logout, account switch and disable.
- `npm run lint`, `npm run type-check`, `npm run build` — **passed**; production build produces 30 routes. An initial helper lint issue and the later unnecessary callback dependency were corrected. The first baseline browser launch lacked a production build; this was a test-server prerequisite, not evidence of a billing failure.
- `FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_invoice_navigation_ui.py` — **passed** against the built frontend. Both kinds exercise all rendered fields, two lines, manual/saved consignee, register/customer navigation, exact retry key/body after a lost creation response, original draft/version, in-flight PATCH completion, fresh review, a failed customer reload, independent reset, failed/successful off-page logout and login, hard-refresh clearing, and 390px layout. API fixtures fail closed on unknown paths and do not access client data. Initial extended-test failures were corrected selector/navigation-load timing issues; no successful backend integration is inferred from mocked responses.
- `FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_bill_submission_ui.py` — **passed** after the review corrections for all **four bill types × three roles**: inline preview, recoverable creation/transition failures, same-draft edit/conflict, approval-safe Confirm, download/print and mobile layout.
- Focused review identified two retention defects, both corrected: the saved-consignee payload no longer depends on successful master reload; initialization effects track actual buyer/mode/state changes rather than counting effect setups, preserving fields under StrictMode effect replay. Failed-master persistence is covered by the browser regression; development StrictMode replay was reviewed statically, not separately certified in a development-browser run. No PDF or unrelated backend concern was included in this correction.
- Targeted `git diff --check` — **passed**. Before/after SHA-256 matches for `backend/app/services/invoice_pdf.py`, shared invoice HTML/CSS and Reagent PO CSS. PDF generators, templates, layout, fonts, logos, pagination, saved bytes and metadata are **unchanged**. Backend/PDF suites were not rerun for this frontend-only task; existing backend limitations remain as documented below.

### Limits / next action

Unsaved entries survive only in-app navigation in the **same tab**. Full refresh, tab close and successful logout intentionally clear memory; localStorage/sessionStorage are not used for billing content. Saved server drafts are unaffected. Cross-device restoration/offline storage is not implemented. Reload/restart the frontend normally to load the changed code, then keep the tab open while preparing a bill. No task-specific blocker remains. Stop after this approved navigation/session update; no additional phase is authorized.

## Reagent chemistry icons — completed (2026-10-06)

- Implemented the approved icon-only design: **Reagent Bills** use an organic hexagonal bond structure; **Reagent Purchase Orders** use a matching smaller structure with an order-document marker. Added two lightweight outline SVGs to the existing `AppIcon` registry; currentColor, sizes, stroke style and decorative/labelled accessibility behavior remain unchanged. No new dependency or image asset was added.
- Applied both icons consistently to dashboard/billing creation shortcuts, dashboard register cards, Explore navigation, entry-page headers and dedicated register headers. Product, Sales and Domestic PO symbols, labels, routes, button styles, financial calculations, forms and workflow behavior remain unchanged. Existing dirty working code was preserved.
- Application files: `frontend/app/components/AppIcon.tsx`, `BillingDocumentActions.tsx`, `NavigationMenu.tsx`, `InvoiceEntryPage.tsx`, `frontend/app/lib/billRegisters.ts`, and `frontend/app/reagent-purchase-orders/page.tsx`. Added `frontend/scripts/reagent_icons.test.mjs` and `frontend/scripts/verify_reagent_icons_ui.py`; updated this status only. No backend or PDF implementation file was edited, no migration is needed, and no client database, Docker, deployment, commit or push was used.

### Verification

- Superpowers test-first regressions: **2 failed / 1 passed** before implementation (missing artwork and generic register icons), then **3 passed**. Full frontend Node command from `frontend/`: `node --test scripts/*.test.mjs` — **20 passed**. Real TypeScript/React server rendering verifies distinct glyphs, sizing/colors/accessibility and register mappings. The initial lint finding in the new test helper's local `module` variable was fixed by renaming it; no application behavior changed.
- `npm run lint`, `npm run type-check`, `npm run build` — **passed**; the build produced 30 routes. Backend suites/PDF fixtures were not rerun because this is a frontend icon-only change and all backend/PDF files remain untouched.
- Against the built frontend on temporary local port 3100: `FRONTEND_BASE_URL=http://127.0.0.1:3100 ICON_SCREENSHOT_DIR=/private/tmp/reagent-icons-CljfR5 ../backend/.venv/bin/python scripts/verify_reagent_icons_ui.py` — **passed** at 1440px and 390px. Checks dashboard/creation cards, billing desk, Explore links/Escape dismissal, both entry and register headers, inherited color/decorative semantics and unclipped SVG geometry including strokes. Fresh desktop/mobile screenshots were visually inspected. No billing save/authentication/data integration claim is made.
- Focused review confirmed all identified icon consumers (including register empty states) are consistent. Its test-isolation finding was verified: the reused API mock could let unknown GETs fall through. The icon browser check now allowlists mocked paths and aborts unmatched requests. Final desktop/mobile re-verification **passed**, including an explicit browser fetch probe proving fail-closed behavior; the full Node suite still reports **20 passed**. No production code change was required for this finding.
- Temporary port-3100 verification servers were stopped, and a final listener check confirmed the port is free. User backend/frontend processes were not stopped. The existing standalone-build `next start` warning was limited to temporary local verification; production packaging was not changed in this icon task.
- Before/after SHA-256 checks match for `backend/app/services/invoice_pdf.py`, shared invoice HTML/CSS and Reagent PO CSS. PDF generators, templates, layouts, fonts, logos, pagination and saved files were **unchanged**. Targeted `git diff --check` — **passed**.

No icon-specific blocker remains. Reload/restart the frontend normally to see the new symbols. Stop after the approved icon-only update; no further feature or phase is authorized.

## Reagent PO bottom terms/signature placement — completed (2026-10-05)

- Implemented the client's approved **Reagent Purchase Order only** correction: Terms and Conditions bottom-left, digital-signature text bottom-right, both above the unchanged green footer/Canvatech branding. Root cause was a normal-flow wrapper preventing the shared final zone's automatic margin from stretching to the page bottom.
- Updated `backend/app/templates/invoice/v1/reagent_purchase_order.css`: closing wrapper fills remaining space for short copies; long item tables retain their existing normal-flow pagination and use a complete final settlement/closing sheet. Reagent-only grid rules align the two closing sections and reset the inherited short-copy signature offset/absolute footer. Text remains in flow and wraps instead of being positioned over table/settlement content. No item fields, financial calculations, entry screens, other bill layouts, font/logo/branding or workflow were changed.
- Advanced only `REAGENT_PURCHASE_ORDER_TEMPLATE_VERSION` to `a4-reagent-purchase-order-v4` in `backend/app/services/invoice_pdf.py` and both corresponding final-wrapper conditions in shared `invoice.html`. Shared `invoice.css` is untouched. Extended the existing real Reagent PO PDF fixtures in `backend/tests/test_reagent_purchase_orders.py` with Chromium geometry regressions. Updated this status and billing context; preserved existing dirty working code.
- No migration is required. Restart the backend if reload is not active and generate a **new** Reagent PO PDF. Existing stored PDFs/checksums/metadata and historical records are not regenerated or modified. No client database, frontend change, Docker startup, deployment, commit or push was used.

### Verification

- Test-first checks reproduced incorrect bottom placement for both fixtures: **2 failed** before implementation. After the fix, short/multi-page fixture checks — **2 passed**. Final targeted command from `backend/`: `./.venv/bin/python -m pytest tests/test_reagent_purchase_orders.py tests/test_invoice_pdf.py tests/test_pdf_name_description_style.py -q --tb=line --show-capture=no` — **47 passed**. Covers preserved Sales/Reagent/Domestic PO presentation, Reagent PO wrappers, stored PDF metadata, four copies and both GST modes.
- Actual one-item and twenty-item Reagent POs were rendered through the existing Jinja2/Chromium engine and all **16 pages** converted with Poppler to PNG. Page counts remain **4** and **12** respectively. Visually inspected the short first copy, long continuation and long final page: terms/signature align above the footer without overlap or clipping. Bundled `pdfplumber` verified placement on all **8 final-copy pages**: terms heading at **712.8pt**, signature heading at **751.3pt**, left/right alignment and all text within the A4 bottom margin. Scratch fixtures: `/private/tmp/reagent-po-bottom-XJtetx`. Extremely long terms spanning additional sheets are not certified by these two standard-terms fixtures.
- Final full backend command `./.venv/bin/python -m pytest -q --tb=line --show-capture=no` — **433 passed, 2 pre-existing unrelated failures, 8 skipped**. Failures remain `test_privileged_mfa_enrollment_and_recovery_full_lifecycle` (old mandatory-MFA assertion versus disabled-MFA policy) and `test_mfa_recovery_replacement_and_administrative_reset` (pre-existing missing `UserRole` import at `account_security.py:172`). Authentication was not changed. PostgreSQL checks remain skipped because `TEST_SECURITY_DATABASE_URL` is unset; no live database guarantee is claimed. Frontend checks were not rerun because frontend files are unchanged.
- Focused read-only review found no new actionable defect in the demonstrated one-/twenty-item fixtures, scoped CSS loading, version wrappers or bottom alignment. It confirmed that unusually long terms spanning extra sheets remain unverified; no universal pagination guarantee is claimed. Other bill formats, finance, authentication and saved PDFs were outside the requested correction and were not changed.
- Targeted `git diff --check` — **passed**; one existing Starlette deprecation warning remains. No new dependency was added; bundled PDF inspection tools are QA-only.

No standard-terms Reagent PO placement blocker has been observed. Stop after this approved correction; no additional feature/phase is authorized.

## Reagent MFG secondary-line styling — completed (2026-10-05)

- Implemented the client's approved format for **Reagent Bills and Reagent Purchase Orders only**: bold product name, followed by `MFG: <manufacturer name>, Artical No.: <number>` in regular text at **85%** of the product-name font size. Long secondary values wrap within Item Description. Saved manufacturer code remains the fallback if no name was captured; missing values do not invent metadata, show an empty `MFG:` label, or create a blank secondary line. Bold GST breakdown remains below it.
- Changes are limited to the Reagent secondary-line branch in `backend/app/templates/invoice/v1/invoice.html`, a Reagent-scoped font-size selector in `invoice.css`, and the two Reagent version constants in `backend/app/services/invoice_pdf.py`. New rendering versions are `a4-reagent-bill-v7` and `a4-reagent-purchase-order-v3`; the two existing PO final-block conditions were advanced together to preserve their wrapper. Sales remains `a4-invoice-v6`, Domestic PO remains `a4-purchase-order-v3`. Separate Reagent PO CSS, primary/GST styles, other layout sections, Pack/Size and all financial/data workflows were left unchanged.
- Extended `backend/tests/test_pdf_name_description_style.py` with real Chromium regressions for name/code/article combinations, missing fields, exact font-size/weight, escaped text, long wrapping and GST ordering, plus actual PDF-to-PNG fixtures for both Reagent types. Updated the existing Reagent version assertion in `test_invoice_pdf.py` and the current billing-context policy. Existing dirty working code was preserved; no frontend, API, model, migration, authentication or infrastructure changes were made.
- No migration is needed for this presentation change. Restart the backend if automatic reload is not active, then generate a **new** Reagent PDF through the existing preview/generation workflow. Existing stored PDF files/checksums/metadata and historical snapshots are not automatically regenerated or rewritten. No client database, Docker, deployment, commit or push was used.

### Verification

- Superpowers test-first checks reproduced the missing `MFG:` prefix in both formats: **2 failed** before implementation. Final targeted command from `backend/`: `./.venv/bin/python -m pytest tests/test_pdf_name_description_style.py tests/test_invoice_pdf.py tests/test_reagent_purchase_orders.py -q --tb=line --show-capture=no --basetemp=/private/tmp/billing-mfg-style-MwYPF7` — **47 passed**. Includes existing Sales/Domestic PO behavior, Reagent PO context/wrappers, short/long fixtures, both GST modes and PDF metadata checks.
- Rendered fresh short and long-metadata PDFs for both Reagent types through Jinja2/Chromium; first pages were converted with Poppler and visually inspected. The smaller secondary line shows `MFG:` without clipping or overlap, and long metadata wraps above the GST labels. Existing multi-page behavior is preserved, not newly certified or redesigned. Scratch verification artifacts are under `/private/tmp/billing-mfg-style-MwYPF7`.
- Final complete backend command `./.venv/bin/python -m pytest -q --tb=line --show-capture=no` — **433 passed, 2 pre-existing unrelated failures, 8 skipped**. Failures remain `test_privileged_mfa_enrollment_and_recovery_full_lifecycle` (old mandatory-MFA assertion versus disabled-MFA policy) and `test_mfa_recovery_replacement_and_administrative_reset` (pre-existing missing `UserRole` import at `account_security.py:172`). Authentication was not changed. PostgreSQL-only tests remain skipped because `TEST_SECURITY_DATABASE_URL` is unset; no live PostgreSQL guarantee is claimed. Frontend checks were not rerun because frontend files are unchanged.
- Targeted `git diff --check` — **passed**. Reagent PO CSS SHA-256 remains `273b0a3faa4d9e90555da7d9d734a211c66dba99c36d2e838043b19819c04c26`. One existing Starlette deprecation warning remains.
- Focused read-only review found no actionable new issues: Reagent-only scope, metadata fallbacks, 85% sizing, GST ordering and both version-bound PO wrappers are coherent. Unrelated dirty changes, authentication failures, finance and existing pagination were intentionally not changed.

No MFG-styling-specific blocker remains. Stop after this approved Reagent-only update; no additional feature or phase is authorized.

## Reagent Pack/Size line field — completed (2026-10-05)

- Added staff-editable **Pack/Size** to each Reagent Bill and Reagent Purchase Order line, with examples `500 g`, `100 mL` and `10 × 2 mL`. It is optional descriptive text, trimmed and limited to 100 printable characters; blank input becomes null. Invalid inputs return line-field validation errors. The forms retain values through retry/edit, show relevant errors below the field and restore saved PO pack sizes during version-conflict reload.
- Persisted independent transaction/revision snapshots through preview, creation, editing, submission and approval. Pack/Size does not modify product/manufacturer masters, quantities, rates, discounts, taxes or totals. Approved-line immutability remains enforced. Non-empty pack sizes participate in creation idempotency; omitted/blank values retain legacy request hashes. Two older legacy-hash test fixtures now omit the new field when reconstructing actual historical payloads.
- Added a dedicated **Pack/Size** PDF column between Quantity and Rate for Reagent formats only, rebalancing their ten columns to 100% width and permitting long pack text to wrap safely. Reagent template versions advance to `a4-reagent-bill-v6` and `a4-reagent-purchase-order-v2`. Sales/Domestic PO entry fields, table branches, calculations and versions remain unchanged. Reagent PO CSS, logos, fonts, branding and all unrelated layout sections remain unchanged; stored PDFs/checksums/metadata are not rewritten.
- Relevant files: existing invoice/PO line models and schemas, invoice/PO API mapping and invoice revision snapshot, descriptive metadata in the shared calculator result, structured exclusions supported by `services/idempotency.py`, existing PDF context/template and reagent-only CSS selectors; `frontend/app/components/InvoiceEntryPage.tsx`, `frontend/app/reagent-purchase-orders/page.tsx`, shared line type; new `backend/tests/test_reagent_pack_size.py` and targeted existing PDF/hash/browser regressions. No new module, dependency, financial policy, authentication change, client-data reset, Docker startup, deployment, commit or push occurred. Existing dirty working code was preserved.

### Migration / local activation

Forward migration `backend/alembic/versions/20261005_0022_reagent_pack_size.py` follows `20261004_0021` and adds nullable `VARCHAR(100)` columns to `invoice_lines` and `purchase_order_lines`, with no historical backfill. It was **not applied to the client database**. Before using the changed backend, stop it and run:

```sh
cd /Users/anujmishra/Developer/Pristine_Bio_billing/backend
./.venv/bin/python -m alembic upgrade head
```

Restart the backend/frontend with their existing local commands. Historical Pack/Size values remain blank rather than guessed; existing saved PDF bytes are retained.

### Verification

- Test-first checks reproduced missing pack snapshots, ignored validation, unchanged-key payload conflicts and the absent PDF column before implementation. Final targeted backend command from `backend/`: `./.venv/bin/python -m pytest tests/test_reagent_pack_size.py tests/test_invoice_pdf.py tests/test_pdf_name_description_style.py tests/test_reagent_purchase_orders.py tests/test_financial_correctness.py -q --tb=line --show-capture=no` — **72 passed**. Covers exact unchanged Decimal totals, preview/save/approval consistency, revisions, immutable approved data, idempotency and preserved Sales/PO format checks.
- Rendered one-item and twenty-item fixtures for each Reagent type through the real Jinja2/Chromium engine, converted all **28 PDF pages** to PNG, and inspected first-copy short, continuation and final-page layouts. Pack/Size wraps without clipped values; one-item fixtures remain four pages (one per copy). Long text may require additional pages under the existing pagination behavior; no pagination redesign is claimed.
- `./.venv/bin/python -m alembic upgrade 20261004_0021:head --sql` — **passed**, transactional PostgreSQL ALTER statements rendered without database access. The isolated SQLite migration regression preserved historical names, quantities, amounts and issued PDF references; new values remained null. Runtime PostgreSQL migration/concurrency behavior is not claimed from SQLite/offline SQL checks.
- Complete backend run `./.venv/bin/python -m pytest -q --tb=line --show-capture=no` — **427 passed, 4 failed, 8 skipped** before final test-fixture/accessibility corrections. Two failures were old hash fixtures inadvertently including the new nullable field in their simulated pre-field payloads. After correcting those fixtures, `./.venv/bin/python -m pytest tests/test_reagent_pack_size.py tests/test_invoice_suppliers.py::test_legacy_idempotency_payload_hash_still_replays_without_supplier_field tests/test_purchase_order_numbers.py::test_creation_retry_with_legacy_payload_hash_preserves_original_order -k 'not pdf' -q --tb=line --show-capture=no` — **12 passed, 5 deselected**. No repeated full-suite run was performed.
- Remaining unrelated failures: `test_privileged_mfa_enrollment_and_recovery_full_lifecycle` (old mandatory-MFA expectation versus disabled-MFA policy) and `test_mfa_recovery_replacement_and_administrative_reset` (pre-existing missing `UserRole` import in `account_security.py:172`). PostgreSQL-only tests remain skipped because `TEST_SECURITY_DATABASE_URL` is unset; one existing Starlette warning remains. Authentication was not changed.
- From `frontend/`: `npm run lint`, `npm run type-check`, `npm run build` — **passed**. Final production rebuild after the stable Pack/Size accessibility-label correction also passed, producing 30 routes and checking lint/types.
- Against the built frontend with isolated HTTP fixtures: `FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_bill_submission_ui.py` — **passed after the final label fix**, all four bill types × Admin/Staff/Manager, including reagent Pack/Size input/field errors, stable retry payloads, same-draft edits, approval-safe confirmation, download/print and mobile width. Non-Reagent entry has no Pack/Size control. `scripts/verify_reagent_purchase_order_ui.py` with the same environment/command — **passed**, including retained saved pack values and reload recovery. Browser fixtures validate UI behavior; real persistence/calculations are covered by backend tests.
- Focused read-only review found no actionable feature regressions. Targeted `git diff --check` — **passed**. Reagent PO CSS SHA-256 remains `273b0a3faa4d9e90555da7d9d734a211c66dba99c36d2e838043b19819c04c26`. Temporary port-3100 verification servers were stopped; no user backend/frontend process was stopped.

No Pack/Size-specific blocker remains. Apply the forward migration/restart locally before use. No further feature or phase is authorized.

## Sales-only PDF names and secondary item descriptions — completed (2026-10-05)

- Implemented the approved presentation, then applied the client's latest scope restriction: **Sales Invoice only**. Item Details shows the transaction's product name in bold, followed directly by its entered Description in smaller regular text. Line breaks, escaped text and long-text wrapping are preserved; blank/name-only fallback descriptions do not add duplicate text or an empty spacer. Sales buyer/consignee names are also bold, with their other details unchanged.
- Reagent Bills, Domestic Oils POs and Reagent POs retain their pre-task item and party-name styling. Their template versions remain `a4-reagent-bill-v5`, `a4-purchase-order-v3` and `a4-reagent-purchase-order-v1`. Only Sales advances to `a4-invoice-v6`. Reagent PO CSS is byte-for-byte unchanged.
- Relevant changes: the existing Sales branches in `backend/app/templates/invoice/v1/invoice.html`, scoped rules in `invoice.css`, and the Sales version constant in `backend/app/services/invoice_pdf.py`. Added `backend/tests/test_pdf_name_description_style.py` and updated existing Sales template-version assertions. Updated billing context and this status. No frontend, API, calculator, model, migration, authentication, infrastructure or client-data change was made. Existing dirty working code was preserved.
- Existing saved PDF files, checksums and generation metadata are not rewritten or automatically regenerated. The new presentation applies when a Sales PDF is rendered through the existing preview/generation interface. No migration is required; restart the backend if it is not running with automatic reload.

### Verification

- Superpowers test-first checks reproduced the missing name/description presentation. A further Sales-only regression failed for the three non-Sales modes before their broader name styling was reverted.
- From `backend/`: `./.venv/bin/python -m pytest tests/test_pdf_name_description_style.py tests/test_invoice_pdf.py tests/test_reagent_purchase_orders.py tests/test_invoices.py::test_pdf_generated_status_transition_is_recorded tests/test_invoices.py::test_approved_invoice_generates_downloadable_pdf_and_persists_metadata tests/test_billing_entry_flow.py::test_saved_purchase_order_can_generate_previewable_downloadable_pdf -q --tb=line --show-capture=no --basetemp=/private/tmp/billing-pdf-style-lSeIHB` — **46 passed after the final Sales-only correction**. Real Chromium checks cover bold/regular font weights, smaller secondary text, line breaks, escaping, long-name/address wrapping and unchanged non-Sales cells. Existing tests cover one/six/twenty/eighty items, long text/terms, both GST modes, four copies, generated metadata and immutable finalized records.
- Rendered representative Sales, Reagent, Domestic PO and Reagent PO fixtures through the existing engine to A4 PDFs, converted each first page to PNG with Poppler and visually inspected all four after the scope correction. Sales displays the bold product followed by smaller Description; non-Sales names and item presentations retain their prior styling. No overlap or clipping was observed in the inspected pages.
- The earlier complete backend run `./.venv/bin/python -m pytest -q --tb=line --show-capture=no` returned **411 passed, 5 failed, 8 skipped**. Three failures were stale template-version expectations, now corrected/restored and explicitly passing in the final 46-test run. Two unrelated pre-existing MFA failures remain: `test_privileged_mfa_enrollment_and_recovery_full_lifecycle` (old mandatory-MFA expectation against disabled-MFA policy), and `test_mfa_recovery_replacement_and_administrative_reset` (existing missing `UserRole` import at `account_security.py:172`). No repeated full-suite run or unrelated authentication repair was performed.
- PostgreSQL-only checks remain skipped because `TEST_SECURITY_DATABASE_URL` is unset. No live database was accessed. Frontend checks were not rerun because no frontend code changed. Targeted `git diff --check` — **passed**; one existing Starlette deprecation warning remains.

No Sales-styling blocker remains. Stop after this approved Sales-only change; no additional phase or PO/Reagent redesign is authorized.

## Searchable supplier selection and supplier-delete feedback — completed (2026-10-05)

- Fixed the verified deletion fault: the frontend request helper now accepts successful empty HTTP 204 responses instead of parsing JSON and falsely showing a deletion error. Real 409/validation errors remain visible. The existing Supplier screen can add records, delete unused suppliers permanently and deactivate used suppliers.
- Added one Supplier selection section to Sales Invoice and Reagent Bill entry only. Server-side name search is active-only and seller-profile-scoped with bounded results. The default prefills once; search/refresh/retry does not replace a manual choice. The selected name, pickup address, GSTIN/contact where present, Manage suppliers link and refresh/recovery controls are visible. Search Enter cannot accidentally submit a bill; selection errors appear below the field. Review locks the selector along with the rest of the entry form.
- Persisted nullable invoice `supplier_id` and independent pickup snapshots. Invalid, inactive and unauthorized new selections are rejected by the backend. Version checks are required for supplier edits; a genuinely changed selection updates pickup only, while sending the same ID preserves saved address data even after master edits/deactivation. Approval and revision history preserve snapshots. Suppliers referenced by current invoices, invoice revisions or POs cannot be permanently deleted; deactivation is supported.
- Explicit selection participates in invoice creation idempotency. Omitted API selection retains the prior default behavior and prior creation-request hashes; explicit null means no pickup supplier. The existing submission hook retains the intended key/body across retries and edits the same versioned draft. Historical invoices are not backfilled or rewritten.
- Relevant files: invoice/supplier APIs, invoice model/schema; `frontend/app/components/InvoiceSupplierPicker.tsx`, shared `InvoiceEntryPage.tsx`, Supplier page explanatory text, API helper and Invoice type; targeted API/request-helper/browser tests. Updated billing context and this status. Existing dirty changes were preserved. Superpowers test-first work and focused review produced explicit unchanged-snapshot and historical-reference regressions.
- Both PO entry implementations and all PDF generation/templates/CSS/fonts/logos/layout/print files were left unchanged. Before/after SHA-256 values match for `invoice_pdf.py`, shared invoice HTML/CSS and Reagent PO CSS. Company registered address remains independent of supplier choice. No live/client database access, actual supplier deletion, Docker startup, deployment, commit or push occurred.

### Migration and local activation

Forward migration `backend/alembic/versions/20261004_0021_invoice_pickup_supplier.py` (after `20261004_0020`) adds the nullable supplier foreign key and index only, with no historic-data backfill. Apply to the operator's configured database, then restart the backend and frontend:

```sh
cd /Users/anujmishra/Developer/Pristine_Bio_billing/backend
./.venv/bin/python -m alembic upgrade head
```

### Verification

- `cd backend && ./.venv/bin/python -m pytest tests/test_invoice_suppliers.py tests/test_suppliers.py tests/test_bill_addresses.py -q --tb=short --show-capture=no` — **42 passed after the final review fixes**, including active/scoped search, strict IDs, immutable approval/snapshot data, supplier edit conflicts/history, idempotency compatibility, isolated migration preservation and real address PDF-preview regressions. The newly added deletion/snapshot regressions were observed failing before their fixes.
- `cd frontend && node --test scripts/session_security.test.mjs` — **14 passed**, including the real request-helper HTTP 204 regression, true 409 errors and preservation of session/retry behavior.
- `cd frontend && npm run lint && npm run type-check && npm run build` — **passed** (commands executed individually; production build generated 30 pages). Type-check was also rerun after the build.
- `cd frontend && FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_invoice_supplier_ui.py` — **passed against the production build**: both entry modes, default/override, scoped search, pinned selection, search/save recovery, identical retry key/body, local field error, versioned edits/review locking, mobile width, Supplier add, empty-204 deletion and true-409/deactivation feedback. Browser API fixtures are isolated; real persistence/authorization is covered by backend tests, not mocked browser success claims.
- `cd frontend && FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_bill_submission_ui.py` — **passed** against the local development preview for all four bill types and Admin/Staff/Manager: inline preview, retry/conflict recovery, same-draft editing, safe confirmation/approval, download/print and mobile behavior.
- `cd backend && ./.venv/bin/python -m alembic upgrade 20261004_0020:head --sql` — **passed**, PostgreSQL forward DDL rendered without connecting to a database. Isolated SQLite migration execution preserved issued PDF references, amounts and address snapshots.
- Complete backend run `./.venv/bin/python -m pytest -q --tb=short --show-capture=no` before the final review fixes — **400 passed, 2 pre-existing MFA failures, 8 PostgreSQL tests skipped**. The final review fixes were then verified with the 42-test targeted run above; no repeated full run was needed. The failures remain `test_privileged_mfa_enrollment_and_recovery_full_lifecycle` (old mandatory-MFA assertion against current disabled-MFA policy) and `test_mfa_recovery_replacement_and_administrative_reset` (existing missing `UserRole` import in `account_security.py:172`). Authentication was outside this request and was not changed.
- Targeted `git diff --check` — **passed**. Temporary port-3100 test servers were stopped after verification.

### Remaining limitations / next step

- Apply the forward migration and restart locally before using selection; it was not applied to client data. Disposable PostgreSQL was unavailable (`TEST_SECURITY_DATABASE_URL` unset), so runtime PostgreSQL locking/FK behavior is not claimed from SQLite or offline SQL checks.
- No separate new-supplier API creation defect was reproduced; real isolated creation/default-switch tests and the Supplier-management browser creation path pass. If the client still gets a save failure after activation, capture its exact field/API error rather than guessing or rewriting data.
- The picker searches across matching authorized suppliers and displays at most 100 results; refine the name query for larger catalogs. Existing default-100/max-500 master/PO list bounds predate this task and were not broadened or redesigned. Legacy bills without supplier IDs are not retrospectively linked by guessing address text.
- This approved supplier task is complete. No additional phase, authentication repair, PO redesign or PDF change is authorized by it.

## Independent company and pickup addresses — completed (2026-10-04)

- Diagnosed the supplied `/Users/anujmishra/Desktop/Bii_1.pdf`: all four copies used the Seller/GST-profile address for both the brand header and Pickup Address. Supplier POST/PATCH already saved only supplier records; the defect was coupled PDF address sources, not a supplier-save overwrite of Company/Branch data. The client approved separating these sources, including the active-default-supplier pickup rule for Sales/Reagent.
- New Sales Invoices, Reagent Bills, Domestic Oils POs and Reagent POs capture `company_registered_address` independently from `pickup_address`. The company header uses the saved Company registered address, retaining explicit line breaks. When that field is blank, the GST-profile address is captured once as a compatibility fallback, never a supplier address.
- Sales/Reagent pickup uses only an active default supplier in the resolved seller profile. With none configured, Pickup Address is omitted rather than duplicating the company address. Each PO uses its selected or inline supplier transaction address; versioned PO draft edits may change pickup without changing the company header. Later supplier/default/company changes do not rewrite saved address snapshots, including on approval or idempotent replay. Invoice revision history now includes both address snapshots; PO revision history already captures all document columns.
- Clarified Registered address and supplier-pickup behavior on the existing Seller/GST profile and Suppliers pages. No billing-form redesign, new module, finance/auth change or unrelated refactor was introduced. Existing dirty user changes were preserved. No client database, Docker, deployment, commit or push was used.
- Application changes: new `backend/app/services/billing_addresses.py`; address columns/read fields and creation/revision hooks in existing invoice/PO models, schemas and APIs; two address-data mappings in `backend/app/services/invoice_pdf.py`; explanatory copy on the two profile pages. Added `backend/tests/test_bill_addresses.py`, extended `frontend/scripts/verify_seller_profile_ui.py`, and updated this status/billing context.
- **PDF formatting is unchanged:** before/after SHA-256 values match for shared invoice HTML/CSS and Reagent PO CSS. Fonts, logos, rendering engine, context signatures, page layouts, pagination and print formatting were not modified. The PDF service file itself changed only to select the independent address snapshots; it is not claimed to be byte-for-byte unchanged. Existing PDF files/references/checksums and issued financial data were not rewritten.

### Migration / local activation

Stop the local backend, then run:

```bash
cd /Users/anujmishra/Developer/Pristine_Bio_billing/backend
./.venv/bin/python -m alembic upgrade head
```

Restart the backend and frontend with their existing local commands. Configure the fixed company address under **Seller/GST profile → Registered address** and pickup addresses under **Suppliers**; select the active default supplier for future Sales/Reagent bills. Migration `20261004_0020_bill_address_snapshots.py` follows `20261003_0019` and adds two nullable TEXT columns to each transaction table, with no backfill. It was not applied to the client database. Old documents with null snapshots retain their prior address-data mapping and stored PDFs; do not automatically regenerate/reissue them to retrofit this change.

### Verification

- Test-first regressions reproduced the fault: **14 failed / 4 passed** before implementation. Final targeted command from `backend/`: `./.venv/bin/python -m pytest tests/test_bill_addresses.py tests/test_seller_profile.py tests/test_suppliers.py tests/test_billing_entry_flow.py tests/test_reagent_purchase_orders.py -q --tb=short --show-capture=no` — **52 passed**. Covers all four bill types, supplier-save isolation, new versus previous pickup addresses, selected/inline PO addresses, default activation/profile scope, absent defaults, blank registered-address fallback, approval/revision snapshots, retry replay and legacy PDF references.
- Actual authenticated preview APIs rendered all four new address fixtures through the unchanged Jinja2/Chromium engine without finalizing drafts or storing PDF metadata. Converted all **13 pages** to PNG; first page of each bill type was visually inspected. Bundled `pypdf` text extraction verified distinct company and pickup addresses on every page/copy. These are synthetic test transactions, not client bills.
- Forward migration applied successfully against isolated SQLite tables containing historical PDF references/totals; values stayed unchanged and new columns remained null. `./.venv/bin/python -m alembic upgrade 20261003_0019:head --sql` — **passed**, producing transactional PostgreSQL ALTER statements only for the four new columns and Alembic revision update. No live PostgreSQL migration/concurrency guarantee is claimed.
- From `frontend/`: `npm run lint`, `npm run type-check`, `npm run build` — **passed**, with 30 production routes. `node --test scripts/*.test.mjs` — **16 passed**. `FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_seller_profile_ui.py` — **passed** against the production build, checking both address explanations and preserved single-company billing setup. Browser API fixtures are isolated; real API/database behavior is tested separately above. Temporary port-3100 verification server was stopped.
- Final complete backend command: `./.venv/bin/python -m pytest -q --tb=line --show-capture=no` — **386 passed, 2 pre-existing failures, 8 skipped**, one existing Starlette deprecation warning. Failures remain `test_privileged_mfa_enrollment_and_recovery_full_lifecycle` (expects enforcement despite disabled-MFA policy) and `test_mfa_recovery_replacement_and_administrative_reset` (existing missing `UserRole` import at `app/services/account_security.py:172`). Authentication was not changed. PostgreSQL-only tests remain skipped because disposable `TEST_SECURITY_DATABASE_URL` is not configured.
- Focused read-only review found no actionable address-related issue. `git diff --check` on affected tracked files — **passed**.

No address-specific blocker remains; the local migration and profile configuration above are required before using the new mapping. Historical records intentionally are not retrofitted. Stop after this approved address correction; no further phase is authorized.

## Dashboard bill counts and dedicated registers — completed (2026-10-04)

- Removed dashboard Draft invoices, Invoice approvals, Draft purchase orders, PO approvals and Recent activity, plus its approval shortcut. Existing approval pages/APIs and all four creation shortcuts remain unchanged.
- Added responsive Sales, Purchase, Reagent and Reagent Purchase count links using existing authorized backend totals. Purchase uses the Domestic Oils count, not the combined PO count. No hardcoded runtime counts, new financial metrics or dummy bills were introduced. Loading/failure displays an unavailable count rather than a false zero; creation/register links remain usable, with dashboard retry support.
- Added four dedicated pages: `/bill-registers/sales`, `/bill-registers/purchase`, `/bill-registers/reagent`, `/bill-registers/reagent-purchase`. Each lists saved records, including clearly labelled drafts, by invoice/order date newest first, grouped by date, with ten-record pagination, single-date/custom-range filters, an applied-date label and clear/reset controls. Invalid/inverted ranges receive explicit errors; filters reset pagination. Empty and server-error states are genuine and recoverable.
- Existing `/api/v1/invoices/register` and `/api/v1/purchase-orders/register` now accept inclusive `date_from`/`date_to` ISO dates. Validation rejects malformed/impossible dates and inverted ranges. Counts and rows use the same filters and existing branch authorization; ID tie-breaks make pagination stable when dates match. Existing API defaults and document-type separation are retained.
- Each row has View. The same-page viewer fetches fresh authorized details, then uses the existing stored-PDF endpoint for finalized files, or the version-bound transient preview endpoint with a Draft/Unstored preview label. View never submits, approves, generates a final file, changes status or updates financial data. PDF failures and revision conflicts show actionable messages; retry reloads the current revision. Closing/changing views revokes blob URLs, obsolete requests are cancelled/ignored, and no billing content is persisted in browser storage. Keyboard pagination restores focus to the page summary; View buttons identify their bill number.
- Application changes are limited to `frontend/app/page.tsx`, new `frontend/app/lib/billRegisters.ts`, new `frontend/app/components/BillRegisterPage.tsx`, four new register page wrappers, and the two existing backend register functions/date imports. Added `backend/tests/test_bill_register_dates.py` and `frontend/scripts/verify_dashboard_registers_ui.py`. The legacy creation-link test no longer assumes the removed dashboard source-code gate; real browser checks now verify creation links during dashboard failure. Updated this status only; entry pages, shared navigation, financial calculations, authentication and masters were not edited.
- No migration is required. Restart the backend to load the date-filter query parameters and reload/restart the frontend as appropriate. Existing saved documents and issued numbers are preserved. No live client database, Docker startup, deployment, commit or push was used. Temporary test servers on port 3100 are stopped.

### Verification

- Test-first date regressions demonstrated ignored filters before implementation. From `backend/`: `./.venv/bin/python -m pytest tests/test_bill_register_dates.py tests/test_phase3_workflows.py -q --tb=short --show-capture=no` — **30 passed**. Includes all four types, inclusive/one-sided/empty ranges, invalid dates, deterministic ascending/descending pagination, type isolation, unauthorized branch exclusion/detail denial and correctly separated dashboard counts.
- Complete backend suite: `./.venv/bin/python -m pytest -q --tb=line --show-capture=no` — **363 passed, 2 pre-existing unrelated MFA failures, 8 skipped**, one existing Starlette warning. Failures remain `test_privileged_mfa_enrollment_and_recovery_full_lifecycle` (disabled MFA policy versus old assertion) and `test_mfa_recovery_replacement_and_administrative_reset` (existing missing `UserRole` import at `app/services/account_security.py:172`). Authentication was not changed to address them. PostgreSQL-only tests remain skipped because a disposable `TEST_SECURITY_DATABASE_URL` is not configured; SQLite coverage is not evidence of live PostgreSQL guarantees.
- From `frontend/`: `npm run lint`, `npm run type-check`, `npm run build` — **passed**, 30 production routes including all four new registers. `node --test scripts/*.test.mjs` — **16 passed**. An initial type-check while development route types were being regenerated reported stale `.next` route declarations; the final cleanly generated production build and explicit type-check pass without application-type changes.
- Against the final built frontend on an isolated port: `FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_dashboard_registers_ui.py` — **passed** in full Chromium for all four types: correct counts/destinations, preserved creation links during dashboard failure, date filters/applied labels, range validation, pagination/focus, uniquely labelled View controls, same-page stored/draft PDFs, version-conflict retry, PDF errors/retry, empty/server-error recovery and 390px layout. `scripts/verify_billing_entry_only_ui.py` with the same command — **passed** for all four unchanged creation pages: no embedded recent/register UI or unused list requests. Browser checks use isolated HTTP fixtures; actual backend data filtering/authorization is tested separately in SQLite. Desktop dashboard/register and mobile register screenshots were generated and visually inspected; the narrow table scrolls inside its container without page overflow.
- Superpowers bounded design, test-first checks and one focused read-only review kept the change scoped. Review found no critical/important issues; its two accessibility findings were reproduced and fixed with regression coverage. `git diff --check` on affected tracked files — **passed**.
- Before/after SHA-256 values match for `backend/app/services/invoice_pdf.py`, shared invoice HTML/CSS and Reagent PO CSS. **PDF generators, templates, CSS, fonts, logos, page layout, pagination and print formatting were unchanged.**

### Limitations / next work

No feature-specific blocker remains. Native embedded-PDF support still depends on the browser; Safari/mobile plugin and physical-printer behavior are not newly certified. No real client-database session or PostgreSQL integration run was performed. Existing unrelated MFA test failures remain documented above. No further module or phase is authorized; stop after this dashboard/register change.

## Canvatech footer colour — verified (2026-10-03)

The requested dark glossy black is already present in the shared PDF footer: only `Canvatech` uses `#111`, bold weight and a restrained white highlight/dark shadow; `By` remains regular black without a shadow. Read-only Chromium computed-style checks verified every copy in Sales Invoice, Domestic Oils PO, Reagent Bill and Reagent PO template modes. The existing focused footer regression also passed. No application, template, CSS, layout, stored PDF or historical data changes were needed. Previously generated/stored PDFs retain their original appearance; new previews/generated PDFs use the existing dark styling. No further development is authorized by this request.

## Inline bill submission panel — completed (2026-10-03)

- Added Preview, Edit, Download, Print and Confirm controls below authoritative backend totals on Sales Invoice, Reagent Bill, Domestic Oils PO and Reagent PO pages. PDF previews are authenticated blobs embedded in the same page; no external preview window or third-party viewer is opened. Draft previews are explicitly labelled unfinalized. Entry fields lock during review; Edit unlocks the same draft and invalidates its preview without losing form data. Confirm requires the exact saved/previewed version. Final download/print remain disabled before confirmation and required approval. A confirmed/submitted session can start a new bill explicitly.
- Creation uses one retry key and original payload. An uncertain committed creation is resolved with that original intent before changed input is PATCHed to the same document, rather than starting another creation. Duplicate clicks are guarded. PATCH conflicts retain entered fields and direct users to the latest reviewed revision; Reagent PO retains its explicit confirmed reload/deep link. Saved-master refreshes cannot reset the consignee or manually chosen supply state; a preview is bound to its persisted payload rather than unsaved refreshed input. PDF URLs are revoked on edit/replacement/unmount; form/PDF data is not stored in browser persistent storage.
- Preserved the approved permission distinction: Admin can confirm/approve their own bill; Staff and creator-Managers submit for authorized independent review. Check approval refreshes only the current document, not a removed register. Staff cannot generate final invoice PDFs; a Manager/Admin must do so after approval. Lost submit/approve responses reconcile only the exact submitted/approved revision. Final PDFs load in a separately keyed frame; Print waits for that final frame instead of printing a previous draft or the entry form. Existing PO amendment controls remain available with a reason and optimistic version.
- New `POST /api/v1/invoices/{id}/preview-pdf` and `POST /api/v1/purchase-orders/{id}/preview-pdf` require a strict positive integer `expected_version`, authorization and branch access. They render the current transaction snapshot through the existing engine and return inline `application/pdf` with `Cache-Control: no-store`, without changing status/version/audits, stored checksums or PDF files. Domestic PO financial preview is now supported without master writes. Domestic full draft PATCH uses `domestic_details`; invoice PATCH now accepts inline buyer/consignee transaction details, including an explicit same-buyer consignee reset, without rewriting historical masters or issued documents. Approved financial data remains immutable.
- Application files: invoice/PO API and schema files; shared `frontend/app/lib/useBillSubmission.ts` and `frontend/app/components/BillSubmissionPanel.tsx`; authenticated PDF fetch in `frontend/app/lib/api.ts`; the three shared/dedicated entry implementations. Added 81 API regressions across `tests/test_inline_submission.py` and `tests/test_inline_invoice_parties.py`, a four-document/three-role browser regression and a valid blank-A4 browser HTTP fixture; updated the Reagent PO browser regression for the new controls. Superpowers bounded design/TDD/parallel backend implementation and one focused review influenced only this requested flow.
- No database migration is required for these changes: existing document versions, statuses, snapshots and idempotency records are reused. No reset, live client database access, Docker startup, deployment, commit or push. Existing recent/register UI stays removed and its APIs/records remain intact. Both original final-generator function bodies are preserved. Before/after SHA-256 matches for `invoice_pdf.py`, shared invoice HTML/CSS and Reagent PO CSS confirm protected rendering, fonts/logos, layout and pagination were not changed.

### Verification

- Backend targeted worker regression: **187 passed**. Independent rerun from `backend/`: `./.venv/bin/python -m pytest -q tests/test_inline_submission.py tests/test_inline_invoice_parties.py` — **81 passed**, including actual Chromium A4 PDF rendering for all four types, preview mutation/storage checks, authentication/branch/version validation, Decimal totals, same-ID full edits, snapshots, atomic validation failures and finalized immutability.
- Complete backend suite: `./.venv/bin/python -m pytest -q` — **338 passed, 2 pre-existing unrelated MFA failures, 8 skipped**, one existing Starlette warning. The failures remain `test_privileged_mfa_enrollment_and_recovery_full_lifecycle` (disabled MFA policy versus old assertion) and `test_mfa_recovery_replacement_and_administrative_reset` (existing missing `UserRole` import in `account_security.py:172`). They were not changed as part of this billing request. PostgreSQL-only checks require a disposable `TEST_SECURITY_DATABASE_URL`; production PostgreSQL concurrency is not claimed as verified.
- Frontend `npm run lint`, `npm run type-check`, `npm run build` — **passed**, 26 production routes. `node --test scripts/*.test.mjs` — **16 passed**. `FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_bill_submission_ui.py` — **passed** against the final production build in full Chromium, all four document types with Admin, Staff and Manager (12 scenarios): embedded real PDF response/load, no preview popups, disabled pre-confirm output, creation committed with lost response then edited/retried under the original key, same-ID PATCH, optimistic conflict retention, PDF failures, lost submitted/approved responses, exact-version confirmation, final file download, PDF-frame print invocation and 390px mobile width. Focused scripts `verify_manual_po_number_ui.py`, `verify_billing_entry_only_ui.py`, `verify_invoice_financial_year_ui.py` and updated `verify_reagent_purchase_order_ui.py` also **passed**, preserving manual numbers, absent register requests, India-local FY inputs and explicit PO conflict reload. Browser scenarios use isolated API fixtures; actual PDF engine/API behavior is separately covered by backend tests. The default Chromium headless shell does not load native embedded PDFs; the final test uses full Chromium (`channel="chromium"`) to verify the viewer load handshake rather than simulating it.
- `git diff --check` on affected tracked files — **passed**. Temporary verification frontend on port 3100 is stopped at handoff; client servers and data are not modified.

### Limitations / next work

This request adds only the approved submission flow. The native PDF viewer/print dialog depends on browser support; physical-printer output and Safari/mobile PDF plugin behavior are not certified. Entry recovery is memory-only until the server draft exists; refreshing/leaving before confirmation can discard unsaved edits. Existing Domestic PO final-generation API compatibility still allows draft PDFs, while the new panel intentionally gates final actions on confirmation/approval. Existing PO bank/terms defaults and all PDF formatting remain as before. No future phase is authorized.

## Remove recent-document UI from billing entry — completed (2026-10-03)

- Removed the Recent Purchase Orders/Recent reagent purchase orders shortcut from all four entry pages, plus the embedded Recent sales invoices, Recent purchase orders, Recent reagent bills and Reagent purchase order register sections. Removed register search/status/pagination controls and their now-unused loading state/GET requests. No backend API or stored document was deleted; list/register/detail/workflow endpoints remain available for future implementation.
- Kept the entry forms, manual invoice/PO numbers, saved master choices, live totals, current-document actions and PDF preview/download/print. Domestic PO submit/amend controls formerly available only in its removed list now live in the existing Saved bill actions panel. Master lists still refresh after a save so automatically saved profiles/products remain selectable. Workflow/PDF actions no longer refetch an unused register.
- Sales/Domestic PO stale-version errors preserve entered data and direct the user to review the latest document in the existing Approval workspace; they no longer misleadingly claim that a removed register was refreshed. Reagent PO direct `?order=` loading and its explicit confirmed reload/version-conflict flow remain unchanged. Invoice live totals use the available full-width section after removal of the adjacent list; there is no broader visual redesign.
- Application changes are limited to `frontend/app/components/InvoiceEntryPage.tsx`, `frontend/app/purchase-orders/page.tsx` and `frontend/app/reagent-purchase-orders/page.tsx`. Added `frontend/scripts/verify_billing_entry_only_ui.py` and updated this status plus billing context. No migration, live database access, Docker startup, deployment, commit or push was performed.
- Before/after SHA-256 checks match for the invoice/PO API files, API router, PDF generator, shared invoice HTML/CSS and Reagent PO CSS. Backend API implementations and PDF rendering/layout files are unchanged by this request.

### Verification

- Test-first browser regression failed against the old UI on all four pages because recent shortcuts were still present. It passes after removal, including absent headings/buttons, zero list/register requests, enabled creation controls, genuine entry independence from a deliberately unavailable register API, no page errors and 390px mobile width.
- From `frontend/`: `npm run lint`, `npm run type-check`, `npm run build` — **passed**, with 26 production routes. `node --test scripts/*.test.mjs` — **16 passed**.
- `FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_billing_entry_only_ui.py` — **passed** against development and the production build. The same command using `scripts/verify_manual_po_number_ui.py` and `scripts/verify_reagent_purchase_order_ui.py` — **passed**, preserving manual numbers, field-level errors, retry-key retention, saved purchaser/product choices, conflict recovery and current-document approval/PDF controls. `scripts/verify_invoice_financial_year_ui.py` — **passed** against the production build for both Sales/Reagent invoice number inputs and the March/April FY boundary. Browser checks use isolated API fixtures, not client data.
- From `backend/`: `./.venv/bin/python -m pytest -q --tb=line --show-capture=no` — **257 passed, 2 failed, 8 skipped**. The same two pre-existing, unrelated MFA failures remain: `test_privileged_mfa_enrollment_and_recovery_full_lifecycle` expects MFA enforcement despite the current disabled-MFA policy; `test_mfa_recovery_replacement_and_administrative_reset` encounters the existing missing `UserRole` import at `app/services/account_security.py:172`. No authentication change was made. PostgreSQL-only checks remain skipped because no disposable `TEST_SECURITY_DATABASE_URL` is configured; live PostgreSQL behavior is not claimed as verified.
- `git diff --check` on the affected files — **passed**. Temporary local verification servers are stopped before handoff. The earlier attempt to start a production preview found no build; verification used development for the red/green checks, then a fresh successful production build for the final checks.

No blocker specific to this UI removal remains. Refresh/restart the frontend to load the new entry-only pages. Stop here; adding future register UI or other development requires an explicit request.

## Manual PO No. input — completed (2026-10-03)

- Added an accessible **PO No.** input to both `/purchase-orders` (Domestic Oils) and `/reagent-purchase-orders`. Staff can enter a full number without a forced prefix. Blank inputs retain automatic numbering for existing-client compatibility; manually supplied numbers are trimmed/uppercased, limited to 100 characters and checked for blank/control-character values.
- Creation persists the supplied `purchase_order_number` instead of replacing it with an automatic number. Case-insensitive prechecks reject duplicates across both PO types; the existing database UNIQUE constraint is the concurrent-write backstop, and a database uniqueness failure returns a field-specific HTTP 409 rather than an internal server error. Historical identifiers are not rewritten. No new database column or migration is required.
- Reagent draft reload/edit retains the entered number. Number edits require the current version, remain recorded in revision snapshots and invalidate stale PDF references without deleting historical files. Previously approved PO numbers cannot change, even during amendments. Existing authorization, approval and financial calculations are preserved.
- Both forms show duplicate/validation feedback beneath the PO number field and retain entered data after failures. Unchanged intended retries keep the same idempotency key and payload; changing the number creates a different save intent. Compatibility coverage caught and fixed the additional optional field changing older automatic-number payload hashes: those retries still return the original document, without modifying old idempotency records.
- The existing Domestic and Reagent PO PDF context/HTML interfaces already display the saved document number in Invoice Details. **No PDF generator, template, CSS, font, logo, pagination or print-format file was edited for this request.** No live database, Docker service, deployment, commit or push was used. The temporary browser-test server was stopped.

### Files and verification

Changed application files: `backend/app/schemas/purchase_order.py`, `backend/app/api/v1/purchase_orders.py`, `backend/app/services/idempotency.py`, `frontend/app/purchase-orders/page.tsx`, `frontend/app/reagent-purchase-orders/page.tsx`. Added `backend/tests/test_purchase_order_numbers.py` and `frontend/scripts/verify_manual_po_number_ui.py`; extended `frontend/scripts/verify_reagent_purchase_order_ui.py`; updated this status and `docs/BILLING_CONTEXT.md`.

- Test-first number checks failed before implementation, then passed. Final targeted command from `backend/`: `./.venv/bin/python -m pytest tests/test_purchase_order_numbers.py tests/test_reagent_purchase_orders.py tests/test_financial_correctness.py tests/test_purchasers.py tests/test_billing_entry_flow.py tests/test_phase3_workflows.py -q --tb=short --show-capture=no` — **60 passed**, including 14 manual-number regressions and existing short/long PDF fixture checks. Chromium rendering was rerun outside the macOS sandbox after a sandbox-only browser launch denial.
- From `frontend/`: `npm run lint`, `npm run type-check`, `npm run build` — all passed; 26 pages generated.
- From `frontend/`, against an isolated fixture-backed local test server: `FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_manual_po_number_ui.py` and the same command with `scripts/verify_reagent_purchase_order_ui.py` — both passed. Verified manual payloads, inline duplicate feedback, changed-intent keys, retry-key retention, saved/reloaded reagent numbers, existing approval/PDF actions and 390px mobile width. These browser checks mock APIs; actual authorization, persistence and PDF header data are covered by backend tests.
- Final complete backend command: `./.venv/bin/python -m pytest -q --tb=line --show-capture=no` — **257 passed, 2 failed, 8 skipped**. The two failures are pre-existing/outside this request: `test_privileged_mfa_enrollment_and_recovery_full_lifecycle` expects MFA gating that the current registration/login policy disabled; `test_mfa_recovery_replacement_and_administrative_reset` encounters the existing missing `UserRole` import at `app/services/account_security.py:172`. Authentication code was not changed to address them.
- Eight PostgreSQL security/concurrency checks remain skipped because `TEST_SECURITY_DATABASE_URL` is not configured. New uniqueness/race-backstop tests exercised the real SQLite UNIQUE constraint with a simulated missed precheck, not real PostgreSQL concurrency. No PostgreSQL-only guarantee is claimed from that coverage.

Restart the backend/frontend to load the updated forms and API; this request requires **no migration**. The previously documented Reagent PO migration remains required if it has not yet been applied. No feature-specific blocker remains. Stop here; do not begin further development without an explicit request.

## Reagent Purchase Orders alongside Domestic Oils (2026-10-03)

- Added a dedicated `/reagent-purchase-orders` entry/register page and a fourth creation card on the dashboard/Billing desk, plus an Explore menu destination. Existing `/purchase-orders` remains the Domestic Oils page; its fields, default supplier behavior and document layout were not changed.
- Purchase orders now carry `document_type=domestic_oils|reagent`; existing orders are tagged `domestic_oils` by the forward migration. List/register endpoints default to Domestic Oils and accept `document_type=reagent` for the separate register. PO numbering remains in the existing PO series, independent of Sales/Reagent invoice numbers. Dashboard returns both separate PO counts and the existing combined count.
- Reagent entry supports manual/saved purchasers with name search, the saved default supplier, independent product/manufacturer selection, article number, HSN/SAC, quantity, the seven reagent units, rate, GST and percentage discount. Separate editable consignee snapshots include address, GSTIN, PAN, phone and email. Order/reference dates, payment terms, transport, vehicle/LR and document-level adjustments match the existing Reagent Bill inputs.
- Preview uses the shared Decimal calculator without creating masters. Saved line snapshots retain manufacturer ID/name/code, article number and discount percentage. Existing precision, tax reconciliation, active-master and authorization rules apply. Creation keeps the persistent idempotency constraint; the frontend retains the same key/payload after a failed intended save. Financial edits and workflow changes require the exact reagent PO version; conflicts preserve entered fields and offer a confirmed reload.
- Reagent POs use the existing PO draft/submission/approval/amendment lifecycle, including Manager/Admin approval and the existing Admin self-approval policy. Approved financial records are read-only until an audited amendment. Full reagent revision snapshots include financial inputs, parties, line metadata and prior PDF references; amendment invalidates the current PDF reference without deleting the historical file. Final PDF generation requires an approved/closed Reagent PO and retains checksum, template version, actor and timestamp. Preview, download and print actions are available after generation.
- PDF mode `a4-reagent-purchase-order-v1` reuses the Reagent Bill nine-column presentation and four copy labels, with product name, manufacturer/article secondary line, bold GST breakdown, pre-GST goods amount, bank defaults, terms and branding. Short copies use a 42mm reserved item body; long orders continue with repeated identity/table headings and totals/terms grouped on the final page. Visual review caught and fixed inherited Chromium table-fragmentation overlap only for this new mode.
- PDF changes are limited to the new context builder, mode-specific CSS and a conditional final-block wrapper in the shared HTML. Existing Sales Invoice, Reagent Bill and Domestic Oils PO layout branches, shared CSS, fonts and logos are preserved; existing PDF regressions pass. The shared template file is therefore not literally unchanged, but the new wrapper is rendered only for the new Reagent PO version.

### Migration and startup

Stop the local backend, then run:

```bash
cd /Users/anujmishra/Developer/Pristine_Bio_billing/backend
./.venv/bin/python -m alembic upgrade head
```

Restart the backend and frontend using the existing local commands. Revision `20261003_0019_reagent_purchase_orders.py` follows `20261001_0018`; it adds nullable reagent metadata/consignee fields, manufacturer line snapshots and discount percentage, a document-type constraint and a type-scoped register index. Existing invoices and saved financial values are not rewritten. Migration SQL was validated offline; no client database was accessed or reset, and the migration was not applied during this task.

### Verification and limitations

- Initial regression failed because reagent fields were ignored by the PO endpoint; it now passes.
- Related API/workflow/calculation tests: **43 passed, 2 PDF cases deselected**. Final reagent non-rendering regressions after the PDF metadata test was added: **11 passed, 2 deselected**.
- Reagent and existing PDF checks: `./.venv/bin/python -m pytest tests/test_reagent_purchase_orders.py tests/test_invoice_pdf.py -q --tb=short --show-capture=no` — **30 passed** before the additional API-metadata test (the latter separately passed). One-item intrastate and twenty-item interstate fixtures were rendered to PDF and every page to PNG; short and continuation/final pages were visually inspected. The short fixture has four pages; the long fixture has twelve (three per copy). No overlap remains in the reviewed fixtures.
- Full backend suite: **242 passed, 8 skipped, 2 existing MFA failures** before the last additional metadata regression. Failures remain `test_privileged_mfa_enrollment_and_recovery_full_lifecycle` (disabled MFA policy) and `test_mfa_recovery_replacement_and_administrative_reset` (existing missing `UserRole` import). They were not changed. PostgreSQL-specific tests were skipped because `TEST_SECURITY_DATABASE_URL` is not configured; real PostgreSQL concurrency remains unverified locally.
- Frontend `npm run type-check`, `npm run lint`, `npm run build` — **passed**. `node --test scripts/billing_document_links.test.mjs` — **passed**. `FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_reagent_purchase_order_ui.py` — **passed** for saved purchaser search, independent product/MFG selection, retry-key retention, version-conflict recovery, approval/PDF controls, and 390px layout. Browser checks use isolated API fixtures; real backend business behavior is covered separately by API tests, not a live client-database session.
- `DATABASE_URL=postgresql+psycopg://billing:billing@localhost:5432/billing ./.venv/bin/python -m alembic upgrade 20261001_0018:head --sql` — **passed**, without connecting to PostgreSQL. `git diff --check` — **passed**.
- No deployment, database reset, inventory, GST integration, accounting integration, or unrelated feature was added. The next step is to apply the forward migration locally and use the new Reagent Purchase Order card; further development requires an explicit request.

## Invoice product presentation and line GST breakdown (2026-10-02)

Updated the Reagent Bill line presentation so the product name is the primary bold text in Item Description. The saved manufacturer name and Artical No. now render together directly below it as the regular secondary line, followed immediately by the bold CGST/SGST or IGST rate breakdown. The Reagent table's dedicated `Artical No.` column remains available. Sales Invoice and Purchase Order item rows retain their existing presentation.

The PDF context now carries the immutable manufacturer-name snapshot instead of relying only on its code. Reagent line Amount cells continue to show the backend-authoritative taxable goods value before GST, followed by bold line-tax amounts. Intrastate lines show the equal CGST/SGST rate split; interstate lines show IGST. No financial calculation policy was changed.

Changed files: `backend/app/services/invoice_pdf.py`, `backend/app/templates/invoice/v1/invoice.html`, `backend/app/templates/invoice/v1/invoice.css`, and focused assertions in `backend/tests/test_invoice_pdf.py`.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **14 passed** with one existing Starlette/httpx deprecation warning. A dedicated fixture was rendered to A4 PDF/PNG and all copy pages were visually inspected; the secondary line and GST line are stacked without clipping or overlap. The complete backend suite reported **213 passed, 8 skipped, 2 unrelated existing MFA failures** (`test_privileged_mfa_enrollment_and_recovery_full_lifecycle` conflicts with the intentionally disabled MFA policy; `test_mfa_recovery_replacement_and_administrative_reset` reaches a pre-existing missing `UserRole` import). No frontend, migration, or database changes were required.

## Independent Reagent Product and Manufacturer selection (2026-10-02)

Reagent Bill entry now treats Product and Manufacturer as independent selections. The active product list is no longer filtered by the selected manufacturer, changing the manufacturer no longer clears the selected product, and backend validation accepts any active same-profile manufacturer with any active product. For manual Reagent lines, the auto-saved Product record remains generic; the selected manufacturer and product code are retained on the invoice line snapshot. Existing Sales, Purchase Order, Product master, and PDF behavior was preserved.

Verification: `cd backend && ./.venv/bin/pytest tests/test_billing_entry_flow.py tests/test_manufacturers.py -q` — **13 passed** with one existing Starlette/httpx deprecation warning. `cd frontend && node --test scripts/product_master_fields.test.mjs` — **2 passed**; `npm run lint`, `npm run type-check`, and `npm run build` — **passed**. No migration or PDF-file change was required.

## Product master catalog simplification (2026-10-02)

The Product screen now saves and lists only reusable catalog data: product name, description, HSN/SAC, GST rate, cess rate, and active status. It no longer asks for or displays Manufacturer, Manufacturer product code / Part No., Unit, or Base rate. Existing Product rows and their historical fields were preserved; no migration is required. New Product API requests may omit unit and base rate, which use the database-compatible defaults `kg` and `0.0000` without exposing those fields to bill makers. The existing Reagent workflow was not changed.

Verification: `cd backend && ./.venv/bin/pytest tests/test_master_records.py -q` — **passed**. `cd frontend && node --test scripts/product_master_fields.test.mjs`, `npm run lint`, `npm run type-check`, and `npm run build` — **passed**. `git diff --check` — **passed**. One existing Starlette/httpx deprecation warning remains.

PDF templates, renderer, CSS, fonts, logo, pagination, and print formatting were not changed.

## Reagent manufacturers and product catalog (2026-10-01)

Added a dedicated Manufacturers register for active/inactive records such as SIG and MRK, with unique uppercase codes per seller profile. Extended Product master with an optional manufacturer link and a distinct manufacturer product/catalog code. Product codes are unique per manufacturer and seller profile; units are stored as canonical symbols (`g`, `kg`, `mg`, `µg`, `mL`, `L`, `t`) while accepted aliases such as `GM`, `KG`, `MG`, `ML`, and `TON` normalize to those symbols.

Reagent entry now lets the bill maker select an active manufacturer and then a saved product, or enter a manual product under that manufacturer. Product selection fills manufacturer, HSN/SAC, unit, rates, and product code; line-level edits affect only that bill. Reagent drafts persist manufacturer name/code and product code snapshots, and revision snapshots include them. Inactive or cross-profile manufacturers are blocked for new reagent products/bills. Sales invoices and PO workflows are otherwise unchanged.

Migration: from `backend/`, run `./.venv/bin/alembic upgrade head`. Revision `20261001_0018` creates `manufacturers`, adds manufacturer linkage/code to products, and adds manufacturer snapshot fields to invoice lines. Existing product links and historical invoice snapshots are left untouched; the migration was SQL-validated but not applied to a live/local database during this task.

Verification: `./.venv/bin/pytest tests/test_manufacturers.py tests/test_invoices.py tests/test_billing_entry_flow.py tests/test_master_records.py tests/test_models.py -q -k 'not pdf_generated_status_transition_is_recorded and not approved_invoice_generates_downloadable_pdf_and_persists_metadata'` — **35 passed, 2 deselected**. The two excluded cases invoke Chromium, which is blocked by this machine's macOS sandbox (`MachPortRendezvousServer: Permission denied`). Frontend `npm run lint`, `npm run type-check`, and `npm run build` — **passed**. `./.venv/bin/python -m alembic upgrade head --sql` and `git diff --check` — **passed**.

PDF templates, renderer, CSS, and layout were not changed. The existing Reagent `Part No.` column displays the manufacturer product/catalog code; the manufacturer identifier (for example, SIG/MRK) is saved in the invoice snapshot but is not yet printed as a separate PDF column.

## Premium billing shortcuts on dashboard and Billing desk (2026-10-01)

Added three prominent, responsive brand-colored creation buttons directly below the dashboard header and retained them on the Billing desk: Sales Invoice → `/invoices`, Purchase Order → `/purchase-orders`, and Reagent Bill → `/reagent-bills`. Their shared component appears before dashboard-data-dependent content, so all three remain visible while metrics load or fail. Each is a keyboard-focusable link with a matching icon, concise description, and hover feedback; existing bill pages and workflows were not changed.

Verification: `node --test frontend/scripts/billing_document_links.test.mjs` — **passed**; frontend lint, type-check, and production build — **passed**.

## Reagent Bill generator (2026-10-01)

Added a separate Reagent Bills workflow at `/reagent-bills`, accessible from the Billing desk and feature menu. It reuses the existing Sales Invoice entry, customer/seller details, approval, audit, numbering, PDF actions, and financial calculation workflow, while persisting a `sales`/`reagent` document type and filtering the invoice register by type (the existing endpoint defaults to Sales). Reagent item snapshots now include Part No. and Disc %; percentage discounts are calculated server-side with Decimal/ROUND_HALF_UP, persisted alongside the derived discount amount, and recalculated consistently through approval.

Reagent PDFs use a versioned template mode (`a4-reagent-bill-v1`) and the requested item columns in order: Item Description, HSN/SAC, GST, Part No., Quantity, Rate, Per, Disc %, Amount. Sales Invoice and PO table columns remain unchanged. The Amount cell remains the pre-GST taxable line value, matching the current Sales Invoice behavior.

Migration: from `backend/`, run `./.venv/bin/alembic upgrade head`. This adds `invoices.document_type` (existing records default to `sales`) and `invoice_lines.part_no` / `discount_percent`.

Verification: targeted backend calculation and invoice tests — **11 passed, 4 PDF-rendering cases deselected**; focused Reagent PDF rendering test — **1 passed**; frontend lint, TypeScript type-check, and production build — **passed**. Generated Reagent PDF visually inspected as A4. Its four copy labels each follow the existing shared short-invoice pagination, which currently produces 8 pages total because terms/signature/footer continue onto a second page per copy; existing shared PDF layout was not otherwise changed. One existing Starlette/httpx deprecation warning remains.

## Item Amount excludes GST (2026-10-01)

Sales Invoice and Purchase Order item-table Amount cells now display each saved line's taxable value (goods/charges less line discount, before GST and cess), rather than the GST-inclusive line total. The tax summary and final payable amount remain unchanged and continue to show taxes and the GST-inclusive total.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **11 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected one-item Sales Invoice and PO pages. Both show the pre-GST item amount (300.00), while the summary shows 300.00 taxable value, 27.00 + 27.00 GST, and the unchanged 354.00 final payable total. `git diff --check` — passed.

## Purchase Order item label content (2026-10-01)

Purchase Order item-table cells now show the saved material/product name under “Item Details” instead of the material description. Sales invoice item descriptions are unchanged. Added a focused regression assertion using distinct product-name and description values.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **10 passed** with one existing Starlette/httpx deprecation warning. Rendered and visually checked a PO page; “Sodium Hydroxide” appears in Item Details, with no material-description text. The preview also shows the pre-existing Terms/footer overlap associated with the 64mm table setting; it was not changed in this narrowly scoped update.

## Latest invoice item-table default height (2026-10-01)

Doubled the shared invoice/PO item-table body from 32mm to 64mm. The first item row keeps its existing 2.5mm clearance below the header. A one-item PDF leaves the unused table body blank, and a six-item PO fixture fits within the default table body.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **10 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected one-item Sales Invoice and six-item PO PDFs. The one-item Sales Invoice's Terms and Conditions continue onto a second page because of the larger reserved table area; footer/content pagination beyond the requested table sizing remains unchanged. `git diff --check` — passed.

## Latest item-row clearance below table headers (2026-10-01)

Increased the first item row's top padding from 1.2mm to 2.5mm, creating a clearer gap below the item-table header border in both shared invoice and PO PDF layouts. Row spacing and table columns are unchanged.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected Sales Invoice and PO sample pages with the adjusted gap; `git diff --check` — passed.

## Latest sales and PO footer rule color (2026-10-01)

Changed the shared bottom footer rule from lime to the standard green token, so both Sales Invoice and Purchase Order PDFs use the same green line.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected a Sales Invoice and PO PDF, confirming the shared footer rule is green in both; `git diff --check` — passed.

## Latest glossy pale-green Purchase Order header finish (2026-10-01)

Lightened the shared Supplier Details, Delivery Details, and item-table header backgrounds to a white-to-pale-green gradient, adding a subtle white inset highlight while preserving the peacock shadow and dark borders. Added focused style assertions for both header types.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected a one-page A4 PO PDF with the updated header treatment; `git diff --check` — passed.

## Latest Purchase Order header and PAN confirmation (2026-10-01)

Confirmed Supplier Details, Delivery Details, and item-table headers use the same glossy greenish-white gradient and inset peacock shadow. Mapped the supplier PAN into Supplier Details; the purchaser PAN remains visible in Delivery Details from its existing transaction snapshot. No stylesheet or migration change was needed.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected a representative one-page A4 PO PDF showing both PAN values and the shared glossy greenish-white headers; `git diff --check` — passed.

## Latest Purchase Order PDF content parity (2026-10-01)

Added the seller's active default bank details and terms to generated Purchase Order PDFs, including the standard terms block used on sales invoices. Mapped the existing purchaser PAN, phone, and email snapshots into the PO Delivery Details section. Bank and terms fall back to the seller profile when no active default record is configured. No migration was needed.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected a representative PO PDF page showing all requested content; `git diff --check` — passed.

## Latest invoice and purchase-order header containment and item spacing (2026-10-01)

Constrained the glossy header shadow inside each Buyer/Consignee and item-table header box, added clear top spacing before the first item row, and verified the shared invoice template applies the same styling and content flow to Purchase Order PDFs. No separate PO renderer or duplicated layout was introduced.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected representative invoice and Purchase Order PDFs as A4 PNGs; invoice output was 8 pages under the existing 32mm short-table setting and Purchase Order output was 1 page; `git diff --check` — passed.

## Latest invoice table borders and typography refinement (2026-10-01)

Removed the lime accent line from invoice table headers, changed table outer and inner borders to dark black, and applied Arial with Arial Narrow fallback to invoice text and dense table headers. The embedded stylesheet is now rendered as CSS so the requested font family is honored by Chromium. No billing calculations or document content changed.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered the one-item fixture to A4 PDF and PNG and visually inspected black borders, header treatment, and Arial typography; `pdfinfo` confirmed A4 output. The existing 32mm item-table setting still produces 8 pages for the one-item fixture because each copy's footer continues onto a separate page.

## Latest invoice unified header styling and doubled item-table space (2026-10-01)

Applied the existing glossy greenish-white item-table header treatment to the Buyer Details and Consignee / Shipping Details headers so all invoice section headers share the same background, accent border, shadow, and dark peacock-green text. Doubled the reserved short-invoice item-table body from 16mm to 32mm. No financial logic, document content, or unrelated layout rules were changed.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected a one-item A4 fixture; the requested 32mm table space and matching header treatment are present. The one-item fixture now uses 8 A4 pages because the doubled table space leaves the existing footer on a continuation page for each copy. `git diff --check` — passed.

## Latest invoice item-table fixed five-row layout (2026-10-01)

Reserved a compact 16mm item-table body for short invoices, giving one-to-five product invoices a consistent table area. Product rows now keep vertical column borders but remove horizontal separators, using compact readable spacing between products. Short-copy footer and signature positioning are scoped to invoices with up to five products so long-invoice pagination remains independent.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected one-item and five-item fixtures; both remain 4 A4 pages with the footer and signature clear and anchored; `pdfinfo` checks for 20-item and 80-item fixtures completed without rendering errors; `git diff --check` — passed.

## Latest invoice item-table glossy header refinement (2026-10-01)

Softened the item-table header from translucent green-aqua to a glossy greenish-white gradient with subtle green tinting. The existing dark text, lime accent border, and peacock shadow remain unchanged.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected `tmp/pdfs/glossy-green-white-header.pdf`; `pdfinfo` confirmed 4 A4 pages; the header is light, readable, and free of clipping or layout change; `git diff --check` — passed.

## Latest invoice item-table header color refinement (2026-10-01)

Changed only the item-table header bands to a light, translucent green-to-aqua gradient with dark peacock-green text. Preserved the existing lime accent border and peacock shadow styling.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected `tmp/pdfs/light-item-header.pdf`; `pdfinfo` confirmed 4 A4 pages; the lighter header remains readable with no clipping or layout change; `git diff --check` — passed.

## Latest invoice terms vertical position refinement (2026-09-30)

Moved the Terms and Conditions block another 1.5mm upward by increasing the controlled space below it to 6mm, while keeping the signature and footer in their existing bottom position.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected `tmp/pdfs/terms-lifted-6mm.pdf`; `pdfinfo` confirmed 4 A4 pages; Terms and Conditions is higher with no clipping or overlap and the signature/footer remain anchored; `git diff --check` — passed.

## Latest invoice terms vertical position refinement (2026-09-30)

Lifted the Terms and Conditions block a further 1.5mm by increasing the controlled space below it to 4.5mm, keeping the signature and footer in their existing bottom position.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected `tmp/pdfs/terms-lifted-again.pdf`; `pdfinfo` confirmed 4 A4 pages; Terms and Conditions sits further up while the signature/footer remain anchored and unclipped; `git diff --check` — passed.

## Latest invoice bank-detail spacing refinement (2026-09-30)

Increased the spacing below the Bank Details heading and between each bank-detail line while preserving the existing bank placement beside the quantity summary.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected the four-page one-item PDF at A4 size; Bank Details line spacing is visibly increased without clipping or pagination change; `git diff --check` — passed.

## Latest invoice bank placement beside quantity summary (2026-09-30)

Moved only the Bank Details block to the left side of the existing Quantity and calculation table row, so it appears directly before the quantity summary without changing the amount-in-words row, table alignment, terms, or footer styling.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected the four-page one-item PDF at A4 size; Bank Details now sits to the left of the Quantity/calculation table, with no clipping or pagination change; `git diff --check` — passed.

## Latest invoice consignee snapshot and PDF detail rendering (2026-09-30)

Preserved consignee PAN, phone, and email in invoice transaction snapshots, mapped them into the PDF context, and rendered them in the Consignee / Shipping Details panel. The panel remains content-driven so longer addresses and added identity/contact/shipment details grow without clipping.

Migration: `20260930_0016_consignee_snapshot_details.py`; apply with `cd backend && ./.venv/bin/python -m alembic upgrade head` against the configured PostgreSQL database.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; `cd backend && ./.venv/bin/python -m alembic upgrade head --sql` — passed; rendered and visually inspected the long-text consignee fixture; PAN, phone/email, addresses, and shipment details are visible without clipping; local development database upgraded successfully and `alembic current` reports `20260930_0016 (head)`; `git diff --check` — passed.

## Latest invoice Canvatech prefix styling (2026-09-30)

Separated the footer label so `By` is black and regular weight while `Canvatech` remains large, bold, and neon blue.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected the four-page one-item PDF at A4 size; `By` is black and regular while `Canvatech` remains large, bold, and neon blue; `git diff --check` — passed.

## Latest invoice footer alignment and Canvatech styling (2026-09-30)

Moved both bottom footer text lines to the left side of the invoice and enlarged `By Canvatech` with a neon blue glow while preserving the existing green footer rule and A4 pagination.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected the four-page one-item PDF at A4 size; both footer lines are left-aligned and `By Canvatech` is larger with neon blue styling; `git diff --check` — passed.

## Latest invoice terms color and spacing refinement (2026-09-30)

Added a clearer 2.5mm separation between the black bold Bank Details block and Terms and Conditions, and changed the complete terms block so every numbered line renders in black.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected the four-page one-item PDF at A4 size; terms spacing and black text are correct; `git diff --check` — passed.

## Latest invoice summary alignment and closing typography update (2026-09-30)

Enlarged the Total Amount in words line to use a full-width row immediately below the item table with deliberate spacing. Total Quantity and the final tax calculation table now remain right-aligned on the next row, while keeping the one-page-per-copy layout. Bank details are black and bold, and the Terms and Conditions heading is black and bold.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected the four-page one-item PDF at A4 size; `pdfinfo` confirmed 4 pages and A4 dimensions; `git diff --check` — passed.

## Latest invoice terms wrapping and bank-heading styling (2026-09-30)

Constrained Terms and Conditions text to an 81-character reference line width so longer terms wrap cleanly at word boundaries. Added a small gap between Bank Details and Terms and Conditions, and changed only the Bank Details heading to black while retaining green bank values.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected the long-text four-copy PDF at A4 size; terms wrap safely, the Bank Details heading is black, and the requested spacing is visible; `git diff --check` — passed.

## Latest invoice Rate and Amount column balance (2026-09-30)

Reduced Rate from 14% to 12% and transferred the 2% directly to Amount, increasing Amount to 17% while preserving the 100% table width.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** with one existing Starlette/httpx deprecation warning; rendered and visually inspected the four-page one-item PDF; Rate is narrower and Amount wider while GST remains readable; `git diff --check` — passed.

## Latest invoice GST and amount column balance (2026-09-30)

Reduced the GST column from 8% to 7% and increased the Amount column from 14% to 15%, preserving the 100% table width while keeping the GST header readable and improving amount readability.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed**; rendered and visually inspected the four-page one-item PDF; the GST header/value remain readable and the wider Amount column fits without spilling the footer; `git diff --check` — passed.

## Latest invoice closing-section typography update (2026-09-30)

Added a bold `Bank Details` heading, enlarged and bolded the Terms and Conditions heading, compacted the terms list while retaining full-width wrapping, and changed the digital-signature text to a light-bold weight. The final-section spacing preserves a deliberate gap before the bottom footer line.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed**; rendered and visually inspected the four-page one-item PDF; Bank Details and Terms headings are emphasized, terms are compact, the signature remains right-aligned, and the footer gap is preserved; `git diff --check` — passed.

## Latest invoice party-panel and column balance update (2026-09-30)

Added a small amount of vertical breathing room to Buyer/Consignee panels. Reduced Item Details width and balanced HSN/SAC, Quantity, Rate, and Amount to equal widths while retaining the GST column and the existing financial calculations.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed**; rendered and visually inspected one-item and 80-item A4 PDFs; one-item output remained four pages and 80-item output remained 16 pages; `git diff --check` — passed.

## Latest invoice standard terms update (2026-09-30)

Added the four requested standard payment, return, transport-loss, and weightment terms directly below the bank-details section for Tax Invoice PDFs. Existing saved terms remain above them; Purchase Order PDFs are unchanged.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed**; rendered and visually inspected the four-page one-item PDF; all four terms fit below the bank details without moving the footer to a new page; `git diff --check` — passed.

## Latest invoice summary cleanup (2026-09-30)

Removed the rendered `Cess Amount` and `Discount Value` rows from the invoice tax summary while preserving backend calculations. Changed `Total Amount in words` to an inline, wrapping-safe label/value line so short values such as `Rupees Fifty Three Only` remain on the same line.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed**; rendered and visually inspected the four-page one-item PDF; the two rows are absent and the amount-in-words label/value render inline; `git diff --check` — passed.

## Latest invoice bank and signature finishing touches (2026-09-30)

Removed the separator line above the lower-left bank details. The digital signature block is now right-aligned, slightly larger, and kept at the lower-right above the computer-generated footer.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed**; rendered and visually inspected the four-page one-item PDF; bank separator is absent and the enlarged signature is right-aligned above the footer; `git diff --check` — passed.

## Latest invoice item-table and bank placement update (2026-09-30)

Simplified the rendered item table to S No., Item Details, HSN/SAC, Quantity, Rate, GST (%) and Amount. Other Charges, Discount and Cess remain available to backend calculations but are no longer rendered as item columns; HSN/SAC now has a wider balanced column. Moved the saved bank-default block to the lower-left final section of the PDF with the requested labels and profile-driven values.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed**; rendered and visually inspected one-item and 80-item A4 fixtures; the one-item output has the bank block at lower-left and the 80-item output retained A4 pagination with 16 pages; `git diff --check` — passed.

## Latest invoice bank-detail placement and top-section cleanup (2026-09-30)

Moved the saved bank-default details into the left summary column immediately below `Total Amount in words`, while preserving the requested bold green labels and profile-driven values. Removed the outer boxes and backgrounds from the seller/company and Invoice Details header sections; their internal alignment, metadata rows, and readable separators remain intact.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed**; rendered and visually inspected the four-page one-item PDF; `git diff --check` — passed. No migration was required.

## Latest invoice PDF header alignment refinement (2026-09-30)

Refined the existing versioned Jinja2 invoice header without changing its data contract, pagination engine, copy behavior, calculations, or PDF service interface. The seller logo now sits outside the seller-details border as a standalone mark; seller identity remains in a structured bordered panel; and invoice identity, IRN, and transport/payment metadata remain in a matching right-hand panel whose top edge aligns with the seller-details panel. Long text remains wrapped through the existing safe-wrap rules.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed**; rendered and visually inspected the one-item and 80-item A4 fixtures as PNGs; 80-item output remained 20 A4 pages with continuation tables and final terms/footer; `git diff --check` — passed. PDF generation remains Playwright/Chromium-based and the existing four-copy behavior is unchanged.

## Latest Admin self-approval workflow (2026-09-30)

Admins may now submit and approve their own Sales Invoices and Purchase Orders. Staff and Manager self-approval remains blocked and still requires an independent authorized approver. The backend rule is enforced for both document types, while the approval workspace now states the Admin exception clearly. Approval status, audit transitions, immutable approved data, revision checks, and PDF generation were unchanged; no migration or PDF implementation change was needed.

Verification: `cd backend && ./.venv/bin/pytest tests/test_phase3_workflows.py::test_admin_can_self_approve_invoice_and_purchase_order tests/test_phase3_workflows.py::test_invoice_return_for_correction_preserves_reviewed_revision_and_blocks_self_approval tests/test_invoices.py::test_staff_can_submit_manager_can_approve_and_approved_invoice_is_immutable -q` — **3 passed**; `cd frontend && npm run lint && npm run type-check` — passed; `git diff --check` — passed.

## Latest repeatable Admin registration (2026-09-30)

Removed the one-time first-Admin setup gate, `ADMIN_REGISTRATION_MASTER_PASSWORD` dependency, `/auth/setup-status`, and `/auth/bootstrap-admin`. Admin registration is now a normal repeatable `POST /api/v1/auth/register` flow that creates an active Admin account; duplicate emails remain rejected. The login screen is a single generic sign-in form for Admin, Manager, and Staff accounts, with no separate Admin sign-in mode. Staff and Manager accounts remain invitation-based so role and branch assignment stay controlled. Existing cookie sessions, refresh rotation, authorization, audit logging, billing workflows, and PDF generators/templates were unchanged.

No database migration was needed. The legacy `admin_setup_state` table remains in the schema for forward compatibility with existing databases but is no longer consulted by runtime registration. The master-password environment variable was removed from configuration examples and production validation.

Verification: `cd backend && ./.venv/bin/pytest tests/test_auth.py tests/test_session_security.py -q` — **39 passed**; `cd backend && ./.venv/bin/python -m compileall -q app` — passed; `cd frontend && npm run lint && npm run type-check` — passed; `cd frontend && node --test scripts/session_security.test.mjs` — **13 passed**; `git diff --check` — passed. A standard Admin registration now works repeatedly at `/register`; Staff/Manager invitation acceptance remains available through `/login#invite=...`.

## Latest supplier default and lifecycle controls (2026-09-17)

Added persisted Supplier default selection with one default supplier per branch. Only active suppliers can be marked default; choosing a new default clears the previous one, and deactivating a default clears its flag. The Suppliers screen now provides explicit Set/Clear default, Activate/Deactivate, Edit, and permanently Delete actions. Permanent deletion is allowed for unused suppliers; suppliers referenced by purchase orders are protected so historical PO snapshots remain intact and the supplier must be deactivated instead. Purchase Orders now prefer the explicitly selected active default supplier and continue to fall back to the first active supplier for legacy data without a default.

Migration: `20260917_0015_supplier_defaults.py`. Apply forward with `cd backend && ./.venv/bin/python -m alembic upgrade head` against the configured PostgreSQL database; do not reset the database. The migration backfills the first active supplier per branch and adds a unique partial database index for the default selection.

Verification: `cd backend && ./.venv/bin/pytest tests/test_suppliers.py tests/test_purchasers.py tests/test_billing_entry_flow.py -q` — **14 passed**; `cd frontend && npm run lint && npm run type-check` — **passed**; `cd backend && ./.venv/bin/python -m alembic upgrade head --sql` — **passed**; `git diff --check` — **passed**.

## Latest Purchase Order default-supplier reuse (2026-09-17)

Purchase Orders now automatically use the first active saved Supplier master as the default supplier/provider. The existing supplier details are prefilled and read-only in the PO form, the saved supplier ID is submitted directly, and an `Edit supplier master` link is provided for changes that should apply to future orders. If no active supplier exists yet, manual supplier entry remains available for the initial setup. Purchaser selection, products, calculations, workflow, backend APIs, and PDF rendering were unchanged.

Verification: `cd frontend && npm run lint` — **passed**; `cd frontend && npm run type-check` — **passed**; focused Purchase Order default-supplier UI contract — **passed**.

## Latest Purchase Order mode-selector cleanup (2026-09-17)

Removed the first duplicate `Manual entry` / `Use saved data` selector from the Purchase Order page. Purchase-order supplier and line-item entry remains manual-first, while the separate purchaser selector for adding a new purchaser or choosing a saved purchaser remains available. Backend APIs, saved records, calculations, workflow, and PDF output were not changed.

Verification: `cd frontend && npm run lint` — **passed**; `cd frontend && npm run type-check` — **passed**.

## Latest PDF quantity display correction (2026-09-17)

PDF quantity display now removes insignificant trailing zero decimals, so a stored whole quantity such as `8900.000` renders as `8900`, while meaningful values such as `10.500` and `10.005` remain visible as `10.5` and `10.005`. The quantity unit is aligned inline with the number instead of being forced onto a separate block line. Stored Decimal precision and financial calculations are unchanged.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **9 passed** (including A4 rendering fixtures); `git diff --check` — **passed**.

## Latest PO PDF discount removal (2026-09-17)

Removed the Discount item-table column and Discount Value tax-summary row from Purchase Order PDF output. The PO context now explicitly disables discount rendering and uses a nine-column table with the existing column widths redistributed. Sales Invoice PDFs keep their existing discount column and summary because discount remains supported there. The shared PDF interface, fonts, logo handling, CSS, page size, pagination and footer layout were otherwise unchanged; no migration was needed.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py -q` — **8 passed** (including one-item, twenty-item, eighty-item, long-text and IGST PDF fixtures; Chromium required elevated macOS execution); `git diff --check` — **passed**.

## Latest PO discount removal (2026-09-17)

Removed header and line discount inputs from the Purchase Order entry screen. New PO requests now reject non-zero header or line discounts with a clear validation response; zero-value requests remain backward compatible. Existing historical PO discount columns and protected PDF layout remain unchanged.

Verification: `cd backend && ./.venv/bin/pytest tests/test_purchasers.py tests/test_billing_entry_flow.py tests/test_financial_correctness.py tests/test_phase3_workflows.py -q` — **29 passed**; `cd frontend && npm run lint && npm run type-check` — **passed**; `git diff --check` — **passed**.

## Latest PO delivery-details mapping (2026-09-17)

Purchase-order PDF context now uses the selected purchaser snapshot in the existing `Delivery Details` panel when available. The panel shows purchaser company name, address, GSTIN, and the existing expected-delivery detail. Legacy purchase orders without purchaser data continue using the seller-profile delivery fallback. Only the existing data mapping in `backend/app/services/invoice_pdf.py` changed; the Jinja template, CSS, fonts, logos, pagination and page layout remain unchanged.

Verification: `cd backend && ./.venv/bin/pytest tests/test_invoice_pdf.py::test_purchase_order_context_renders_a_separate_document_title_and_metadata -q` — **1 passed**; the test asserts purchaser name, address, GSTIN and postal code are rendered in the generated HTML.

## Latest purchaser and saved-buyer improvements (2026-09-17)

Added a separate Purchaser master for purchase orders so one legal seller profile can work with different purchaser companies while keeping suppliers independent. Authenticated users can create, list, edit, activate/deactivate and reuse purchaser records from `/api/v1/purchasers`. Purchase orders now accept either a saved purchaser or complete manual purchaser details; an optional "Save this purchaser" choice creates a reusable master. The submitted purchaser fields are copied into immutable PO snapshot columns, so manual transaction details are not replaced by a matching older master. Older API clients that omit purchaser data remain compatible and retain a null purchaser snapshot.

Added a Purchasers page and Explore-menu entry, separate purchaser controls on PO entry, and name/GSTIN search for the saved buyer selector on sales invoices. PDF rendering and layout implementation files were not changed.

Migration: `20260917_0014_purchaser_master.py`. Apply forward with `cd backend && ./.venv/bin/python -m alembic upgrade head` against the configured PostgreSQL database. Do not reset the database.

Verification: `cd backend && ./.venv/bin/pytest tests/test_purchasers.py tests/test_billing_entry_flow.py tests/test_financial_correctness.py tests/test_phase3_workflows.py -q` — **27 passed**; `cd backend && ./.venv/bin/python -m compileall -q app` — **passed**; `cd frontend && npm run lint` — **passed**; `cd frontend && npm run type-check` — **passed**; `cd frontend && npm run build` — **passed**, 23 static routes; `cd backend && ./.venv/bin/python -m alembic upgrade head --sql` — **passed**; `git diff --check` — **passed**. The complete backend suite was also run: **184 passed, 10 existing failures, 8 skipped**. The failures are the previously disabled authenticator/MFA expectations and restricted-sandbox Chromium PDF launches; no purchaser or PO regression failed. The skipped tests require a disposable PostgreSQL security database.

## Current phase

Phase 5B - integration readiness for accounting and applicable GST workflows.

## Status

Latest auth simplification (2026-09-17): Disabled the authenticator/MFA setup flow by explicit client decision. First Admin registration now requires only the configured `ADMIN_REGISTRATION_MASTER_PASSWORD` and the existing 6–10 character passphrase; login and active-role authorization no longer require `MFA_ENCRYPTION_KEY` or an authenticator challenge. Removed authenticator and MFA-reset controls from the frontend while preserving cookie sessions, password changes, invitations, role permissions, audit records, and legacy MFA schema/API compatibility. No migration or PDF change was needed.

Verification for auth simplification: `cd backend && ./.venv/bin/pytest tests/test_auth.py -q` — **12 passed**; `cd frontend && node --test scripts/session_security.test.mjs` — **13 passed**; frontend `npm run lint`, `npm run type-check` and `npm run build` — **passed**. The existing full session-security browser harness still assumes the old mocked MFA/invoice flow and was not used as acceptance evidence for this change.

Latest frontend visual redesign (2026-09-17): Applied the approved Midnight Teal direction across the application shell and operational screens. The permanent feature sidebar was replaced by a compact top-right Explore menu with grouped search; dashboard, billing desk, invoice/PO entry, approvals, masters, seller profile, account security, users, receivables and integration screens now use the full workspace width, consistent controls, responsive panels, readable tables, growing text areas and clearer empty/error states. Added reusable teal tokens, buttons, inputs, panels, table styles, focus states and typed application icons. Backend behavior, API payloads, authentication semantics and protected PDF generators/templates were not changed.

Verification: `cd frontend && npm run lint` — **passed**; `npm run type-check` — **passed**; `npm run build` — **passed**, 22 static routes; `node --test scripts/session_security.test.mjs` — **15 passed**; local Playwright UI contracts for auth errors, session security, manual consignee editing and seller-profile navigation — **passed**. Local browser verification confirmed the redesigned sign-in screen and Explore menu. No database migration was needed.

Latest requested password-length change (2026-09-16): Newly set account passwords now require 6–10 NFC-normalized Unicode characters in first-admin setup, invitation acceptance, and password changes. Backend and frontend validation, on-screen guidance, authentication test fixtures, README, and session policy were updated. Existing hashes and longer passwords remain usable for login and reauthentication. Common-password blocking, Argon2, MFA, and the separate admin-registration master password were preserved. No migration, database access, billing change, or protected PDF change was made.

Verification: `cd backend && ./.venv/bin/pytest tests/test_auth.py tests/test_session_security.py tests/test_account_provisioning_mfa.py -q` — **59 passed** (existing Starlette deprecation warning); `cd frontend && node --test scripts/session_security.test.mjs` — **15 passed**; frontend `npm run lint` and `npm run type-check` — **passed**. PostgreSQL concurrency test input fixtures were updated for the new password policy, but those integration tests and browser fixture scripts were not executed in this focused change.

Phase 1 financial correctness hardening is complete. Phase 1 now covers the application foundation, authentication and permissions, master records, invoice draft and approval workflow, Decimal financial calculations, immutable invoice PDF generation, final verification, and reliable transaction saves.

Latest authentication setup hardening (2026-09-16): Replaced the first-admin `ADMIN_BOOTSTRAP_TOKEN`/`X-Setup-Token` credential with the private server-side `ADMIN_REGISTRATION_MASTER_PASSWORD` submitted only in the dedicated setup request body. Setup remains permanently one-time, public registration remains disabled, and existing invitation, session, MFA, role, and billing flows are unchanged. The master password is not stored, logged, returned by the API, or exposed to the frontend build. Invitation acceptance uses its own passphrase schema and does not require the admin master password.

Verification for this change: `cd backend && ./.venv/bin/pytest tests/test_auth.py tests/test_session_security.py tests/test_account_provisioning_mfa.py::test_invitation_single_use_email_bound_and_hashed -q` — **34 passed**; `cd backend && ./.venv/bin/python -m compileall -q app` — **passed**; `cd frontend && npm run lint` — **passed**; `cd frontend && npm run type-check` — **passed**; `cd frontend && npm run build` — **passed**. No database migration was needed and protected PDF implementation files were not modified.

Latest first-admin setup diagnosis (2026-09-16): Local setup requests were reaching the backend but the private `ADMIN_REGISTRATION_MASTER_PASSWORD` in `backend/.env` was still a placeholder, so the constant-time comparison correctly returned HTTP 401. The setup failure now uses a setup-specific safe message instead of the misleading sign-in message. A real private master password must be configured and the backend restarted; no secret value was read into logs or written by this fix. Final focused verification: **35 passed**; frontend lint and type-check passed; legacy token credential names are absent from runtime backend/frontend code.

Latest Phase 1 financial-correctness hardening (2026-09-16): Aligned invoice and purchase-order inputs with PostgreSQL precision before calculation and persistence; rejected non-finite/overflow values, excessive discounts, invalid state codes, inappropriate tax rates, and whitespace-only required fields; preserved omitted-versus-explicit-null PATCH semantics; blocked inactive saved or inline transaction parties; and kept manually entered buyer, consignee, and supplier details as transaction snapshots without overwriting matching masters. Added persistent, branch-scoped invoice and purchase-order idempotency records with payload-hash conflict detection and database uniqueness for concurrent requests. Frontend save retries retain the same key for the same payload. Protected PDF generators and templates were not modified.

Migration for this hardening: `20260916_0008_financial_correctness_idempotency`. Apply it with `cd backend && ./.venv/bin/python -m alembic upgrade head` against the configured PostgreSQL database; do not reset the database.

Last verification pass: 2026-09-16 financial-correctness hardening and complete Phase 1 regression verification.

Latest PO copy cleanup (2026-09-16): Removed the redundant raw-material/saved-profile helper paragraph from the Purchase Order entry header. Purchase-order fields, workflow, API calls and PDF actions are unchanged.

Latest PO entry cleanup (2026-09-16): Removed the Freight charges, Packing charges and Other charges header inputs from the Purchase Order form. Purchase-order calculations continue using their backend zero defaults, and sales-invoice charge fields are unchanged.

Latest repository-readiness cleanup (2026-09-16): Added ignore rules for generated invoice storage and local Superpowers work files, and removed the development master password from README. GitHub access, remote configuration and application code were not changed.

PO copy cleanup verification (2026-09-16): The exact requested paragraph is absent from `frontend/app/purchase-orders/page.tsx`; frontend lint and type-check were run after the change.

Latest premium frontend redesign Task 1 (2026-09-05): Added the dependency-free typed local SVG icon primitive, grouped navigation model, shared page-header primitive, and approved green visual tokens/shadow. Scope was limited to the Task 1 frontend component/token files; no backend, business logic, route behavior, or unrelated pages were modified. `cd frontend && npm run type-check` and `cd frontend && npm run lint` passed.

Latest requested auth enhancement: Admin self-registration now requires a configured master password. Successful public registration creates an active Admin only after the master password passes server-side validation. Staff and Manager accounts are created after Admin login from the Users screen. User account passwords are exactly 6 characters with uppercase, lowercase, and number checks; the Admin registration master password remains separately configured.

Latest requested billing-entry enhancement: Billing now separates `Purchase Order` documents for raw-material purchases from `Sales Invoice` documents for customer/vendor sales. First-time entry is manual-first with blank boxes, while saved supplier/customer/product choice mode remains available after records exist.

Latest focused billing UI enhancement: Both billing entry pages now provide a top-left `Recent Purchase Orders` shortcut, use the full available content width for data entry, and render long addresses, descriptions, names, and payment terms in auto-growing textareas. Preview and recent records remain below the full-width entry form in responsive cards.

Latest billing document action enhancement: Sales invoices now expose saved-bill actions for approval, PDF generation, preview, download and print while preserving the approved-only PDF workflow. Purchase orders now have a separate versioned A4 PDF path with stored metadata, authenticated preview/download/print actions, and idempotent generation.

Latest save-flow hardening: Sales invoice and purchase-order forms now use app-level validation instead of silent browser submit blocking. Save buttons now surface a clear message when required party, address, product/material, quantity, rate or GST fields are missing, and API validation details from the backend are displayed in readable form.

Latest auth-guard hardening: Protected pages now verify an active JWT session before loading branch, customer, product, invoice, supplier, purchase-order, user, settings, or master-record data. Missing or expired sessions are cleared and shown the login prompt, preventing repeated `401 Unauthorized` billing API calls before bill creation.

Latest single-company/no-branch hardening: Branch selection and Branch ID fields have been removed from the user-facing workflow. The sidebar now exposes `Seller profile`, the old branch setup page has been replaced by a company-first `Seller/GST profile` setup screen, and invoice, purchase-order, customer, product, bank-account, transporter and terms pages use the active Seller/GST profile automatically. If no Seller/GST profile exists, sales invoices and purchase orders show a clear setup message and disable save actions instead of failing silently. The existing Phase 1 database/API internals still store this legal GST context in the legacy branch table for compatibility, but billing users no longer choose or type branch IDs.

Latest company-branding enhancement: The supplied `PB.png` source is stored at `backend/app/templates/invoice/v1/pb-logo.png`, with a transparent-canvas-trimmed display copy rendered in the existing seller-logo slot on every Sales Invoice and Purchase Order copy when no explicit company logo is configured. Explicitly configured company logos continue to take precedence.

Latest invoice layout enhancement: The logo now uses a transparent-canvas-trimmed display copy with `contain` rendering so the complete mark remains visible. Sales invoice numbers now use the company-wide `PBPL/{financial-year}/NO. {sequence}` format, delivery-note date is stored and displayed beside invoice metadata, and `Dispatched through` is an editable invoice field. Buyer/Consignee headings, item headings, totals, and footer accents now use bold bright-green and peacock-green styling with a lime lower accent/shadow; the invoice body remains white.

Latest seller-header alignment enhancement: The invoice seller block now explicitly anchors the PB logo, legal/trade name, address, GSTIN, contact and pickup address to one professional left edge. Default and configured logos use contained left-center positioning so the complete logo remains visible without drifting or cropping.

Latest invoice-footer enhancement: Each generated invoice copy now uses the printable A4 height to keep the green footer rule at the bottom of short pages. `By Canvatech` appears immediately below the rule in bold dark black, followed by the existing computer-generated-invoice footer; multi-page invoices retain the footer on the final page.

Latest auth connectivity/error handling enhancement: Development CORS now accepts both `http://localhost:3000` and `http://127.0.0.1:3000` while retaining the configured origin. Login and Admin registration replace browser-level `Failed to fetch` errors with action-specific guidance to start the backend; normal API validation, duplicate-email, invalid-master-password and invalid-credentials responses continue to surface their backend messages.

Latest invoice color enhancement: Invoice-body header bands now use the approved bright-green-to-peacock-green gradient with a lime-green accent and soft peacock-green shadow. This applies to Buyer Details, Consignee/Shipping Details, item-table headings, tax totals, and footer accents only; the application/page background was not changed.

Latest Seller/GST profile enhancement: The Seller profile screen now uses an atomic `/api/v1/companies/profile` upsert. Staff can bootstrap the first company and primary seller profile, the creator is assigned to the new internal seller context, and assigned Staff/Manager users can edit and save seller details for future bills. Existing branch-scoped authorization remains enforced, while Admin retains full access.

Latest seller billing-default enhancement (2026-09-05): Seller/GST profile editing now includes optional bank name, bank branch, account name, account number, IFSC code, and terms-and-conditions fields. These values persist on the seller profile, are copied into new invoice snapshots when no separate bank/terms master is selected, and render in the existing reference lower-left bank/terms PDF area.

Latest session and saved-master-data hardening: Access-token expiry is now handled by a concurrency-safe silent refresh using the stored refresh token. The browser keeps the session until the user explicitly presses `Log out`; API failures no longer clear local session storage automatically. Billing and master-record screens now read the canonical Seller/GST profile endpoint, load saved customers/products independently from recent invoice history, and keep saved customer choices visible when an unrelated list request fails. Saved customer choices include the customer GSTIN when available.

Latest sales invoice entry enhancement: Manual sales entry now includes a `Consignee same as buyer` option enabled by default. Bill makers can disable it to edit a complete separate consignee snapshot, including name, GSTIN, PAN, phone, email, billing/shipping address fields, city, state, state code and postal code. Saved-data mode now selects only the Buyer, opens a separate Consignee editor, copies the buyer GSTIN and billing address into read-only fields, and leaves consignee name, PAN, phone and email for manual entry. The existing backend inline-party path persists the separate consignee without changing calculations, approval workflow or PDF generation.

Latest company-name verification: A project-owned source, template, test, documentation, and configuration scan found no legacy company-name occurrence; application branding is already `PRISTINE BIOPHARMA` / `Pristine Biopharma`. The external reference PDF and unavailable local runtime database were not modified.

Stop after Phase 1. Do not implement future phases without an explicit prompt.

## Completed features

- Next.js App Router frontend with TypeScript, Tailwind, responsive dashboard shell, invoice entry, master-record screens, login flow, and authenticated API client.
- FastAPI backend with Pydantic schemas, SQLAlchemy models, Alembic migrations, PostgreSQL configuration, environment-based settings, `/health`, and `/api/v1` routing.
- Docker Compose services for frontend, backend, PostgreSQL, and Redis placeholder service.
- JWT access and refresh authentication with Argon2 password hashing.
- Secure Admin registration flow: public registration requires `ADMIN_REGISTRATION_MASTER_PASSWORD`; Staff and Manager users are created by Admin after login; user passwords are exactly 6 characters.
- Admin, Manager, and Staff roles with current Seller/GST profile permissions.
- Company, Seller/GST profile, customer, product, bank-account, transporter, and terms-and-conditions masters.
- Customer billing and consignee/shipping address support.
- Product HSN/SAC, unit, base rate, GST rate, and cess rate fields with PostgreSQL decimal columns.
- Invoice workflow: `draft` to `pending_approval` to `approved` to `pdf_generated`.
- Staff draft creation/submission, Manager/Admin approval, finalized-invoice immutability, idempotent creation and submit/approve/PDF generation, and status-transition audit logs.
- Company-wide financial-year invoice numbering with PostgreSQL advisory transaction locking.
- Backend-authoritative Decimal calculations using `ROUND_HALF_UP`, including the required intrastate fixture and interstate IGST support.
- Financial input precision is enforced before calculation/persistence, invalid discounts and numeric/text/state inputs return clear validation errors, and document adjustments reconcile with line taxes under the documented weighted-rate policy.
- Buyer, consignee, and supplier transaction snapshots preserve submitted details independently of matching master records; inactive masters are blocked for new transactions.
- Persistent branch-scoped invoice and purchase-order creation idempotency with payload-hash conflict detection and database uniqueness for concurrent requests; frontend retries preserve the same key for the same intended save.
- Versioned Jinja2 plus Python Playwright/Chromium A4 invoice generator with four complete copies, continuation table headers, long-text wrapping, optional real IRN/e-way fields, PDF SHA-256, template version, creator, and generation timestamp.
- README startup and verification commands.
- Frontend ESLint setup added for Phase 1E verification.
- Billing desk chooser added for `Purchase Order` versus `Sales Invoice`.
- Supplier master and separate purchase-order storage/API added under `/api/v1/suppliers` and `/api/v1/purchase-orders`.
- Sales invoice drafts can now be created without exposing `branch_id` when the user has a default authorized branch.
- Manual sales entry can auto-save a new buyer/customer and product while saving the invoice draft.
- Manual purchase-order entry can auto-save a new supplier and product while saving the purchase order.
- Sales and purchase screens now support manual entry and saved-data choice mode.
- Sales invoice and purchase-order forms now use full-width responsive layouts with auto-growing long-text fields and a shared Recent Purchase Orders shortcut.
- Saved sales invoices and purchase orders now provide PDF generation, preview, download and print actions; Purchase Order PDFs use `a4-purchase-order-v1` and retain checksum, creator and generation timestamp metadata.
- Branch wording is removed from the normal frontend flow. Seller/GST profile setup now collects company details first, then GSTIN/address/contact details required by tax invoice and purchase-order PDFs.
- The supplied PB company logo is available as the default seller logo in the versioned invoice/Purchase Order PDF template, while configured company logos remain supported.
- Sales invoice numbering now uses the collision-safe company-wide `PBPL/{financial-year}/NO. 00001` format with an advisory transaction lock across branches.
- Sales invoice delivery-note date is available in the API, database migration, entry form, and PDF metadata block.
- Invoice PDF styling now uses the approved green/peacock-green accent and bold Buyer/Consignee headings; the trimmed PB logo display asset preserves the complete logo without top/bottom cropping.
- Seller/GST profile creation and editing is now functional for Staff, Manager, and Admin through the existing Seller profile screen, including first-time Staff bootstrap.
- Seller/GST profiles now store optional default bank/account details and invoice terms; new invoice snapshots inherit those values without changing the separate master-record workflow.
- Session persistence now survives access-token expiry and refreshes access tokens silently; explicit logout is available from the application shell.
- Saved customer and product master data is loaded independently from recent invoice/order history, preventing one failing history request from hiding reusable master records in billing selectors.
- Manual sales invoice entry now supports an editable separate consignee with clear field labels, required-address validation, and backend payload integration.
- Saved-buyer sales invoice entry now keeps consignee identity separate while sharing only the selected buyer GSTIN and address; reference transport fields are available for manual entry.

## Test and build results

- `cd backend && ./.venv/bin/python -m pytest -q` - passed: 138 tests, 1 existing Starlette/httpx `TestClient` deprecation warning. Browser-backed PDF tests passed with local Chromium process permission.
- `cd backend && ./.venv/bin/python -m pytest tests/test_financial_correctness.py tests/test_invoice_calculations.py tests/test_billing_entry_flow.py -q` - passed: 23 tests, 1 existing Starlette/httpx warning.
- `cd backend && ./.venv/bin/python -m pytest tests/test_invoice_pdf.py -q --basetemp=/private/tmp/phase-1e-pdf-fixtures-pytest` - passed: 6 tests, 1 existing Starlette/httpx warning.
- PDF-to-PNG validation with `pdftoppm -png -r 144` - passed for all generated fixtures.
- PDF fixture page counts and size:
  - `one-item-cgst-sgst.pdf` - 4 pages, 4 PNGs, A4 `594.96 x 841.92 pts`.
  - `twenty-items-cgst-sgst.pdf` - 8 pages, 8 PNGs, A4 `594.96 x 841.92 pts`.
  - `eighty-items-cgst-sgst.pdf` - 20 pages, 20 PNGs, A4 `594.96 x 841.92 pts`.
  - `long-address-description-terms.pdf` - 8 pages, 8 PNGs, A4 `594.96 x 841.92 pts`.
  - `one-item-igst.pdf` - 4 pages, 4 PNGs, A4 `594.96 x 841.92 pts`.
- Visual PNG inspection - passed for short invoice balance, all four copy labels, continuation identity/table headings, final-page totals/terms/signature/footer, long address/product/terms wrapping, and IGST tax summary.
- `cd backend && ./.venv/bin/python -m alembic upgrade head --sql` - passed: migration SQL rendered through revision `20260916_0008`.
- `cd frontend && npm run lint` - passed.
- `cd frontend && npm run type-check` - passed.
- `cd frontend && npm run build` - passed: Next.js production build generated 16 static pages including `/invoices` and `/purchase-orders`.
- Auth registration enhancement targeted checks:
  - `cd backend && ./.venv/bin/python -m pytest tests/test_auth.py tests/test_users.py -q` - passed: 34 tests, 1 existing Starlette/httpx `TestClient` deprecation warning.
  - `cd frontend && npm run lint` - passed.
  - `cd frontend && npm run type-check` - passed.
- `cd frontend && npm run build` - passed: Next.js production build generated 14 static pages including `/users`.
- Billing-entry enhancement targeted checks:
  - `cd backend && ./.venv/bin/python -m pytest tests/test_billing_entry_flow.py -q` - passed: 3 tests, 1 existing Starlette/httpx `TestClient` deprecation warning.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_billing_entry_flow.py tests/test_invoices.py tests/test_master_records.py tests/test_remaining_masters.py -q` - passed: 41 tests, 1 existing Starlette/httpx warning. Existing PDF tests required unsandboxed Chromium permission because restricted macOS execution denied Playwright launch.
  - `cd backend && ./.venv/bin/python -m alembic upgrade head --sql` - passed: migration SQL rendered through revision `20260830_0004`.
  - `cd frontend && npm run type-check` - passed.
- `cd frontend && npm run build` - passed: Next.js production build generated 16 static pages including `/billing`, `/invoices`, and `/purchase-orders`.
- Billing UI hardening checks: `cd frontend && npm run lint` - passed; `cd frontend && npm run type-check` - passed; `cd frontend && npm run build` - passed with `/invoices` and `/purchase-orders` included.
- Manual consignee entry checks: `cd backend && ./.venv/bin/python -m pytest tests/test_invoices.py -q -k manual_invoice_preserves_separate_consignee_snapshot --basetemp=/private/tmp/pristine-consignee-pytest` - passed: 1 test, 8 deselected, 1 existing Starlette/httpx warning; `cd frontend && FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_manual_consignee_ui.py` - passed against a local Next.js server, including separate consignee payload assertions; `cd frontend && npm run lint` - passed; `cd frontend && npm run type-check` - passed; `cd frontend && npm run build` - passed with `/invoices` included.
- Saved-buyer consignee contract check: included in `cd backend && ./.venv/bin/python -m pytest tests/test_invoices.py -q --basetemp=/private/tmp/pristine-consignee-invoices-final` - passed: 10 tests, 1 existing Starlette/httpx warning; the Playwright regression `cd frontend && FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_manual_consignee_ui.py` passed for copied read-only GSTIN/address, manual consignee fields and separate payload submission.
- PDF/document action targeted checks: `cd backend && ./.venv/bin/python -m pytest tests/test_billing_entry_flow.py tests/test_invoices.py tests/test_invoice_pdf.py -q` - passed: 19 tests, 1 existing Starlette/httpx warning. Real Chromium PDF fixtures passed with required macOS browser permission.
- `cd backend && ./.venv/bin/python -m alembic upgrade head --sql` - passed through revision `20260830_0005` for purchase-order PDF metadata.
- Final frontend checks after PDF actions: `cd frontend && npm run lint` - passed; `cd frontend && npm run type-check` - passed; `cd frontend && npm run build` - passed with `/invoices` and `/purchase-orders` included.
- Invoice layout enhancement targeted checks: `cd backend && ./.venv/bin/python -m pytest tests/test_invoices.py tests/test_invoice_pdf.py -q` - passed: 16 tests, 1 existing Starlette/httpx `TestClient` deprecation warning. Browser-backed tests passed with local Chromium process permission.
- Invoice layout enhancement migration check: `cd backend && ./.venv/bin/python -m alembic upgrade head --sql` - passed through revision `20260831_0006`.
- Invoice layout enhancement frontend checks: `cd frontend && npm run lint` - passed; `cd frontend && npm run type-check` - passed; `cd frontend && npm run build` - passed with `/invoices` included.
- Representative multi-line invoice PDF visual check: generated PDF remained A4, rendered to PNG, and was inspected for complete logo visibility, green/peacock-green headings/table/totals, delivery/dispatch metadata, continuation headers, and final-page totals/terms/footer.
- Seller/GST profile enhancement targeted checks: `cd backend && ./.venv/bin/python -m pytest tests/test_seller_profile.py tests/test_permissions.py -q` - passed: 19 tests, 1 existing Starlette/httpx `TestClient` deprecation warning.
- Seller/GST profile enhancement frontend checks: `cd frontend && npm run lint` - passed; `cd frontend && npm run type-check` - passed; `cd frontend && npm run build` - passed with `/branches` included.
- Seller billing-default enhancement checks (2026-09-05): `cd backend && ./.venv/bin/python -m pytest -q tests/test_seller_profile.py tests/test_invoices.py::test_invoice_preview_and_draft_creation_return_backend_authoritative_totals` - passed: 5 tests, 1 existing Starlette/httpx `TestClient` deprecation warning; `cd frontend && npm run lint && npm run type-check && npm run build` - passed; `cd backend && ./.venv/bin/python -m compileall -q app alembic` - passed; `cd backend && ./.venv/bin/python -m alembic upgrade head --sql` - passed through revision `20260905_0007`.
  - `cd frontend && npm run lint` - passed.
- Save-flow hardening recheck:
  - `curl -sS -i --max-time 5 http://127.0.0.1:8000/health` - blocked locally: backend was not running on port 8000.
  - `curl -sS -i --max-time 5 http://127.0.0.1:3000/invoices` - blocked locally: frontend was not running on port 3000.
  - `pg_isready -h 127.0.0.1 -p 5432 -d billing` - blocked locally: PostgreSQL was not responding on port 5432.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_billing_entry_flow.py::test_manual_sales_invoice_uses_default_branch_and_auto_saves_customer_and_product -q` - passed.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_billing_entry_flow.py tests/test_invoices.py::test_staff_can_submit_manager_can_approve_and_approved_invoice_is_immutable tests/test_invoices.py::test_approved_invoice_generates_downloadable_pdf_and_persists_metadata tests/test_invoices.py::test_pdf_generation_is_rejected_until_invoice_is_approved -q` - passed except browser-backed PDF generation under restricted macOS sandbox.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_invoice_pdf.py::test_pdf_fixtures_render_to_a4_with_four_complete_copies tests/test_invoices.py::test_approved_invoice_generates_downloadable_pdf_and_persists_metadata -q` - passed with browser process permission: 6 tests.
  - `cd frontend && npm run lint` - passed.
  - `cd frontend && npm run type-check` - passed.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_billing_entry_flow.py::test_manual_sales_invoice_uses_default_branch_and_auto_saves_customer_and_product tests/test_invoices.py::test_staff_can_submit_manager_can_approve_and_approved_invoice_is_immutable -q` - passed: 2 tests.
  - `cd frontend && npm run build` - passed with `/invoices` and `/purchase-orders` included.
- Auth-guard 401 recheck:
  - Temporary Playwright regression `/private/tmp/pristine_auth_guard_check.py` initially failed before the fix because `/invoices` fired unauthenticated requests to `/api/v1/branches`, `/api/v1/customers`, `/api/v1/products`, and `/api/v1/invoices`.
  - The same browser regression passed after the fix for `/invoices` and `/purchase-orders`: no protected billing API requests fire without an authenticated session.
  - `cd frontend && npm run lint` - passed.
  - `cd frontend && npm run type-check` - passed.
  - `cd frontend && npm run build` - passed with `/invoices` and `/purchase-orders` included.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_billing_entry_flow.py::test_manual_sales_invoice_uses_default_branch_and_auto_saves_customer_and_product tests/test_invoices.py::test_staff_can_submit_manager_can_approve_and_approved_invoice_is_immutable -q` - passed: 2 tests.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_billing_entry_flow.py tests/test_invoices.py::test_approved_invoice_generates_downloadable_pdf_and_persists_metadata -q` - passed with browser process permission: 5 tests.
- Single-company/no-branch hardening checks:
  - `cd frontend && FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_seller_profile_ui.py` - failed before the fix because `/branches` still showed `Branches` and `Company ID`; passed after the fix with browser process permission.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_billing_entry_flow.py -q` - passed: 6 tests, 1 existing Starlette/httpx `TestClient` deprecation warning.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_permissions.py tests/test_billing_entry_flow.py -q` - passed: 21 tests, 1 existing Starlette/httpx `TestClient` deprecation warning.
  - `cd frontend && npm run lint` - passed.
  - `cd frontend && npm run type-check` - passed.
  - `cd frontend && npm run build` - passed with `/branches`, `/invoices`, and `/purchase-orders` included.
- Company-logo enhancement targeted checks:
  - `cd backend && ./.venv/bin/python -m pytest tests/test_invoice_pdf.py::test_default_company_logo_is_rendered_in_each_seller_logo_slot -q` - passed: 1 test, 1 existing Starlette/httpx warning.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_invoice_pdf.py -q` - passed: 8 tests, 1 existing Starlette/httpx warning; Chromium required local browser process permission.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_invoices.py::test_approved_invoice_generates_downloadable_pdf_and_persists_metadata -q` - passed: 1 test, 1 existing Starlette/httpx warning.
- Seller-header alignment verification (2026-09-03):
  - `cd backend && ./.venv/bin/python -m pytest tests/test_invoice_pdf.py::test_default_company_logo_is_rendered_in_each_seller_logo_slot -q` - passed after the regression assertion was observed failing before the CSS fix.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_invoice_pdf.py -q --basetemp=/private/tmp/pristine-left-aligned-pdf-tests` - passed: 8 tests, 1 existing Starlette/httpx warning.
  - A representative generated PDF remained four-page A4 (`594.96 x 841.92 pts`); page 1 was rendered to PNG and visually inspected for left-edge alignment, complete logo visibility, wrapping, borders and totals.
- Auth connectivity/error handling verification (2026-09-03):
  - `cd backend && ./.venv/bin/python -m pytest tests/test_health.py::test_development_cors_allows_localhost_alias_for_auth_requests -q` - passed after reproducing the pre-fix 400 CORS response.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_auth.py tests/test_health.py -q` - passed: 22 tests, 1 existing Starlette/httpx warning.
  - `cd frontend && FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_auth_error_messages.py` - passed for both login and Admin registration network failures after reproducing the raw `Failed to fetch` message before the fix.
  - `cd frontend && npm run lint` - passed.
  - `cd frontend && npm run type-check` - passed.
  - `cd frontend && npm run build` - passed: Next.js production build generated 16 static pages.
  - Local reachability check before verification confirmed that PostgreSQL `localhost:5432`, backend `localhost:8000`, and frontend `localhost:3000` were not listening; this was the direct cause of the browser-level `Failed to fetch` symptom in that local session.
- Invoice-footer verification (2026-09-03):
  - `cd backend && ./.venv/bin/python -m pytest tests/test_invoice_pdf.py::test_versioned_invoice_template_contains_all_copies_and_reference_sections -q` - passed after the footer assertions were observed failing before the template/CSS change.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_invoice_pdf.py -q --basetemp=/private/tmp/pristine-footer-pdf-tests` - passed: 8 tests, 1 existing Starlette/httpx warning.
  - Rendered one-item and twenty-item PDFs remained A4 with 4 and 8 pages respectively; first/final pages were rendered to PNG and visually inspected for bottom anchoring, exact `By Canvatech` placement, dark bold styling and preserved pagination.
  - Generated one-item PDF page 1 was converted to PNG and visually inspected: the supplied logo is readable in the top-left seller area without clipping or layout changes; PDF remained A4 and four pages.
  - PB.png checksum verified: `12e32eb77675af858e08d3dd5cbc70e48f6e9989646f433557037b47de0bef14` (source and repository asset match).
- Session and saved-customer flow recheck:
  - Focused pre-fix browser regression reproduced the defect: a failing `/api/v1/invoices` response left the saved-customer selector empty even when `/api/v1/customers` returned a customer.
  - Focused post-fix browser regression passed: saved customer remained selectable while invoice history returned 500; refreshed access token was stored and the session was cleared only after clicking `Log out`.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_billing_entry_flow.py::test_manual_sales_invoice_uses_default_branch_and_auto_saves_customer_and_product tests/test_billing_entry_flow.py::test_saved_sales_invoice_can_be_created_without_exposing_branch_id tests/test_invoices.py::test_staff_can_submit_manager_can_approve_and_approved_invoice_is_immutable -q` - passed: 3 tests.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_seller_profile.py tests/test_master_records.py -q` - passed: 13 tests.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_invoice_calculations.py::test_required_intrastate_calculation_fixture_uses_half_up_rounding tests/test_invoice_calculations.py::test_interstate_calculation_uses_igst_instead_of_cgst_sgst tests/test_invoices.py::test_invoice_preview_and_draft_creation_return_backend_authoritative_totals -q` - passed: 3 tests.
  - `cd frontend && npm run lint` - passed.
  - `cd frontend && npm run type-check` - passed.
  - `cd frontend && npm run build` - passed: Next.js production build generated 16 static pages.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_invoices.py::test_approved_invoice_generates_downloadable_pdf_and_persists_metadata -q` - passed: 1 test with local Chromium permission.
  - `cd backend && ./.venv/bin/python -m pytest tests/test_invoice_pdf.py -q --basetemp=/private/tmp/pristine-invoice-green-pdf` - passed: 8 tests with local Chromium permission; generated PDFs were rendered to PNG and visually inspected for green/peacock-green headers, lime accents, readable white body content, and preserved layout/wrapping.
  - Local PostgreSQL inspection confirmed migration `20260831_0006` is at head and the saved-customer table contains an active record. The empty selector was a frontend all-or-nothing loading boundary, not missing customer data or an unapplied migration.
- `docker compose config` - blocked in this environment: `zsh:1: command not found: docker`.
- Compose YAML fallback validation - passed: services `backend`, `frontend`, `postgres`, and `redis` exist; backend env includes `DATABASE_URL` and `PDF_STORAGE_DIR`; frontend env includes `NEXT_PUBLIC_API_BASE_URL`.
- `cd frontend && npm audit --audit-level=high` - found 3 high-severity advisories in the Next.js dependency tree (`postcss`/`sharp`). The available npm audit fix requires upgrading to Next.js 16.3.3, a breaking major upgrade outside this Phase 1 hardening scope.

## Phase 1 verification coverage

- Admin, Manager, and Staff permissions are covered by authentication, user, permission, master-record, and invoice workflow tests.
- Legacy Seller/GST profile access checks remain covered across company, customer, product, remaining-master, user, and invoice tests.
- Customer and product masters are covered for creation, validation, branch scoping, patching, and Decimal preservation.
- Draft and approval workflow, finalized-invoice immutability, duplicate request protection, audit logs, and invoice-number safety are covered by invoice tests.
- Exact Decimal calculations, intrastate CGST/SGST, interstate IGST, rounding, amount in words, and line other charges are covered by calculation tests.
- Four-copy PDF generation, short and multi-page layouts, long text wrapping, A4 sizing, PDF checksum, metadata, and PDF download are covered by PDF and invoice tests plus PNG inspection.
- API validation and error responses are covered by auth, permissions, master-record, user, invoice, and remaining-master tests.
- Responsive dashboard and billing screen were checked by source review of the Tailwind responsive shell/invoice layouts plus successful lint, type-check, and production build.
- Docker configuration, database migrations, and environment documentation were checked through Compose validation/fallback, Alembic SQL rendering, `.env.example`, and `README.md`.

## Known limitations

- Docker CLI is not installed in this execution environment, so `docker compose config` could not run here. The YAML fallback validation passed.
- Local manual app verification could not run during the latest recheck because PostgreSQL, backend, and frontend were not running on localhost.
- Playwright Chromium PDF rendering is blocked by the restricted macOS sandbox; it passes when run with browser process permission.
- Frontend npm audit has 3 high-severity advisories in the Next.js dependency tree. The available automated fix requires a breaking upgrade to Next.js 16.3.3 and was not applied in Phase 1.
- Live GST IRN/e-way bill generation is not implemented; optional IRN/e-way fields display only when real values already exist on the invoice snapshot.
- Runtime PDF files are stored under the configured `PDF_STORAGE_DIR`; no repository-committed invoice PDFs are produced.
- No effective-dated tax-rule table exists yet. The current weighted-rate allocation is documented and regression-tested; accounting confirmation is required before introducing maintained tax rules or changing allocation treatment for mixed-rate documents.
- No Git branch/commit/PR actions were performed because this workspace is not a Git repository.

## Deferred phases

- GST integration.
- Inventory and batch/lot workflows.
- Commercial documents beyond tax invoices.
- Payments.
- Offline support.
- Android application work.

## Exact next phase

No next phase is defined. Stop after Phase 1 and wait for an explicit prompt before implementing any later phase.

## Guardrails

- Work only on the explicitly requested phase.
- Preserve existing working code.
- Use `Decimal` for money and quantity.
- Keep API routes under `/api/v1`.
- Add targeted tests for changed behavior.
- Run targeted tests during development and the full suite only at phase completion.
- Update this file before stopping work.
- Never implement a future phase without an explicit prompt.

## Phase 2: authentication, session security and sensitive-data permissions

This section supersedes the Phase 1-only status notes above for the explicitly authorized Phase 2 work. Billing calculations, invoice/PO workflows, transaction snapshots and PDF rendering were preserved; no later project phase was started.

### Completed

- Added forward Alembic migration `20260916_0009_session_security.py`. It preserves existing Argon2 hashes at policy version 0, records permanent setup closure for any existing account, and adds revocable sessions, hashed rotating refresh credentials, invitations, MFA recovery codes, throttling and append-only security audits. It is forward-only and does not reset data.
- Replaced public master-password Admin registration and direct password provisioning with one-time private-token first-admin setup and 48-hour, hashed, revocable, single-use Admin invitations. `/auth/register` and `POST /users` now return 410.
- Replaced the exactly-six-character composition rule with 15–128 NFC-character passphrases, no composition requirement, whole-value common-password blocking, and a restricted legacy-password upgrade path. Existing hashes are not silently rewritten.
- Added server-side login throttling, generic authentication failures, safe validation responses, exact-origin checks, signed session-bound CSRF and credentialed CORS protections.
- Added host-only HttpOnly access/refresh/CSRF cookies, short access JWTs bound to database sessions, idle/absolute expiry, logout/logout-all, password-change session revocation, account-disable revocation, refresh rotation and latest-predecessor concurrency grace with replay revocation. Frontend auth metadata/CSRF is memory-only; the legacy localStorage credential is removed. Browser refresh coordination uses singleflight, Web Locks and credential-free BroadcastChannel notifications.
- Added mandatory Admin/Manager PyOTP MFA and optional Staff MFA with encrypted seeds, ten one-use hashed recovery codes, enrollment expiry, persisted TOTP-step replay prevention, recovery-forced reenrollment and authenticated different-Admin reset with reason. Security/account screens implement the lifecycle. Reauthentication keeps mounted billing forms and idempotency keys intact.
- Restricted seller/GST identity, bank account/defaults, roles and assignments to Admin authorization. Role, assignment, activation and sensitive profile changes revoke sessions and record actor, UTC time and sanitized before/after values. Last active Admin protection is serialized with a PostgreSQL advisory lock.
- Added `docs/SESSION_SECURITY.md`, updated `.env.example`, Compose backend secret wiring, README startup/security/migration/test commands, frontend `/security` and invitation/account-management UI. No PDF templates, CSS, fonts, logos, print helpers or PDF service files were modified.

### Verification evidence

- `cd backend && TEST_SECURITY_DATABASE_URL=postgresql+psycopg://anujmishra@127.0.0.1:55439/billing_security_test ./.venv/bin/python -m pytest -q --basetemp=/private/tmp/billing-phase2-final-tests-3` — **172 passed, 1 existing Starlette/httpx deprecation warning**. This included Phase 1 financial, workflow, master-record and Chromium PDF tests. The database was a temporary local cluster, stopped after verification.
- Real disposable PostgreSQL checks — **8 passed**: migration preserves a legacy hash and closes setup; concurrent refresh has one successor; invitation acceptance is single-use; concurrent last-Admin demotions preserve one Admin; revoked/demoted MFA races are denied; password/logout lock ordering completes; concurrent sensitive audit snapshots follow the committed state.
- `cd frontend && node --test scripts/session_security.test.mjs` — **15 passed**; `npm run lint` — **passed**; `npm run type-check` — **passed**; `npm run build` — **passed**, 17 static routes including `/security` and `/users`.
- Frontend Chromium contract regression `../backend/.venv/bin/python scripts/verify_session_security_ui.py` — **passed** for draft preservation, concurrent tabs, setup/invitation, MFA/recovery, session revocation and Admin security controls. It uses mocked API responses and makes no live writes.
- `cd backend && ./.venv/bin/python -m alembic upgrade head --sql` — **passed**, renders through `20260916_0009`.
- Ruby YAML fallback validation — **passed**, services `backend`, `frontend`, `postgres`, `redis`; Docker CLI is not installed here so `docker compose config` itself was unavailable. No Docker service or client database was started or modified.
- Protected PDF paths were checked with `git diff --name-only -- backend/app/services/invoice_pdf.py backend/app/templates`; no protected PDF implementation file appears in the diff.

### Known limitations and operational notes

- Run `./.venv/bin/python -m alembic upgrade head` against the intended PostgreSQL database before starting the updated backend. Never use reset/drop commands. The disposable concurrency database used for verification was stopped and was not the client database.
- `MFA_ENCRYPTION_KEY` must be persistent and independently generated from `JWT_SECRET_KEY`; missing/weak secrets, insecure production cookies, HTTP production origins and default production database credentials fail configuration. TOTP is not phishing-resistant WebAuthn and no NIST AAL2 claim is made.
- The local SecLists 10k snapshot is a versioned offline blocklist, not exhaustive breach screening. Trusted proxy configuration is deployment-specific; arbitrary forwarded IP headers are not trusted.
- The 10-second latest-predecessor refresh grace is intentional for multi-tab/lost-response safety; a replay inside that narrow window cannot be distinguished from concurrency. Older or late replay revokes the session. Encrypted predecessor material is cleared after the next rotation; key rotation still requires controlled re-encryption.
- A second Admin is required for administrative MFA reset. Losing the sole Admin's authenticator and recovery codes requires separately authorized operator recovery; setup never reopens. Invitation link delivery is manual and no email integration is claimed.
- Docker CLI was unavailable in this environment; Compose YAML fallback passed. Browser UI checks use mocked backend contracts, while backend cookie, CSRF, MFA and PostgreSQL behavior is covered by the backend suites and disposable PostgreSQL checks.

### Deferred phases

GST integration, inventory and batch/lot workflows, commercial documents, payments, offline support and Android remain deferred. No later phase was implemented.

## Phase 3: reliable daily billing workflows and operational frontend screens

### Completed

- Added forward migration `20260916_0010_daily_workflows.py` with optimistic transaction versions, submitted/approved revision markers, immutable invoice and purchase-order snapshots, PO lifecycle fields, and append-only PO audit history.
- Added invoice return-for-correction with a required reason, audited transition, version increment, and preserved revision snapshot. Invoice approval rejects creator/submitter self-approval and checks the exact submitted revision.
- Added purchase-order submission, independent approval, amendment request/history, cancellation with a reason, closure, and version-checked editing. Inventory receipts and supplier accounting were not added.
- Added paginated, searchable, filterable and sortable invoice/PO register APIs plus invoice and PO approval queues under `/api/v1`.
- Added an authorized live dashboard endpoint with real document counts, approval counts and audit activity. Outstanding-payment figures and fabricated dashboard activity fixtures were removed.
- Added `/approvals` workspace with independent approval controls, version-aware requests and recoverable API errors, a dedicated `/suppliers` management page, and visible version/conflict handling in the PO register. Existing PDF files and visual identity remain unchanged.

### Verification evidence

- `cd backend && ./.venv/bin/python -m pytest tests/test_phase3_workflows.py -q` — **4 passed**.
- `cd backend && ./.venv/bin/python -m pytest tests/test_invoices.py tests/test_billing_entry_flow.py tests/test_financial_correctness.py tests/test_phase3_workflows.py -q` — **32 passed; 2 PDF tests blocked by the restricted macOS Chromium sandbox**. The failures are the known Playwright `mach_port_rendezvous` permission block, not workflow failures.
- `cd backend && ./.venv/bin/python -m alembic upgrade head --sql` — **passed** through `20260916_0010_daily_workflows`.
- `cd frontend && npm run type-check` — **passed**; `npm run lint` — **passed**; `npm run build` — **passed**, 19 static routes including `/approvals` and `/suppliers`.
- Protected PDF files were checked with `git diff --name-only -- backend/app/services/invoice_pdf.py backend/app/templates/invoice backend/app/templates/purchase_order`; **no protected PDF implementation file changed**.

### Known limitations

- Existing unsubmitted records do not receive historical revision rows until they are next changed; their persisted transaction data is not rewritten.
- Existing list endpoints remain backward-compatible array responses; paginated register contracts are exposed at `/invoices/register` and `/purchase-orders/register`.
- The frontend approval page links to existing registers for detail review; document detail endpoints already exist and no duplicate detail route was introduced.

## Phase 4: production packaging, database performance and operational readiness

### Implemented

- Added `backend/Dockerfile.prod` and `frontend/Dockerfile.prod`. The backend uses a Playwright production image, exact backend pins from `requirements.lock`, a non-root user and configurable worker count. The frontend uses a multi-stage Node 22 standalone Next.js image, `npm ci`, a non-root runtime user and no source bind mounts.
- Added `docker-compose.prod.yml` with explicit production secrets/origins, HTTPS/secure-cookie expectations, named PDF/database volumes, resource limits, health checks, and private PostgreSQL/Redis networking. The existing `docker-compose.yml` remains the development source-mounted workflow; production Compose never runs Alembic automatically.
- Added `backend/scripts/release_migrate.sh`, which is a one-shot, failure-stopping migration step. Apply forward migration `20260916_0011_operational_indexes` with that command against the intended release database; never reset or downgrade the database.
- Added database indexes for branch/status/submission queues, dates, audit history, and active master name lookups. Invoice, PO and master list APIs now enforce a default 100-item bound with a maximum of 500; register endpoints retain backend pagination/search/filter/sort.
- Added `/ready` as a database-backed readiness check while `/health` remains a dependency-independent liveness check. Added request IDs, JSON request/error events, duration/status fields and redaction-by-design (no request body, query string, cookies, authorization, MFA or finance payload logging). `ERROR_TRACKING_DSN` is documented for the deployment collector and redacted `error_tracking` events are emitted without a claimed third-party integration.
- Added `.github/workflows/ci.yml` for locked backend installation, Alembic migration, backend tests, disposable PostgreSQL security/concurrency coverage, frontend `npm ci`/lint/type-check/build, and Python/npm dependency scans. The supported Next.js line is pinned to 15.5.24; the non-major `sharp` audit fix is in the lockfile. The remaining nested PostCSS/Next findings are documented as a reviewed supported-line exception because npm offers remediation only through a Next.js 16 major upgrade.
- Added `docs/OPERATIONS_RUNBOOK.md` covering release/migration failure handling, proxy/security expectations, logs and alerts, backup/retention, isolated restore validation, rollback and incident response, and capacity assumptions. Proposed RPO 24 hours/RTO 4 hours require client agreement and are not achieved guarantees.

### Migration and verification evidence

- `cd backend && ./.venv/bin/python -m alembic upgrade head --sql` — **passed**, renders through `20260916_0011`.
- `cd backend && ./.venv/bin/python -m pytest tests/test_health.py -q` — **5 passed**.
- `cd backend && ./.venv/bin/python -m pytest -q` — **168 passed, 8 skipped, 7 known PDF-render tests blocked** by the restricted macOS Chromium `mach_port_rendezvous` permission. The failed tests are existing PDF fixtures/status paths; no PDF files were changed.
- `cd backend && ./.venv/bin/pip check` — **passed**; the lock matches all project packages in the verification environment (excluding the environment’s `pip` self-package).
- `cd frontend && npm ci && npm run lint && npm run type-check && npm run build` — **passed**; production build generated 19 routes on Next.js 15.5.24.
- `cd frontend && npm audit --json` — **0 critical, 1 high and 1 moderate** remaining in the supported Next.js dependency tree; `sharp` was upgraded through the smallest non-major fix. The exact advisory applicability and upgrade decision are documented in `docs/OPERATIONS_RUNBOOK.md`.
- Docker CLI is unavailable in this environment, so `docker compose config` could not execute. Ruby YAML parsing and production policy checks **passed** for both Compose files and CI YAML; no containers were started and no live database was accessed.
- Protected PDF implementation/template/CSS/font/logo paths were checked with `git diff --name-only`; **unchanged**.

### Remaining limitations

- A deployment-specific third-party error collector is not configured; the application emits redacted structured error events and requires the operator to connect `ERROR_TRACKING_DSN` to its collector.
- The remaining nested PostCSS advisory requires a future, explicitly approved Next.js major-upgrade decision; the current official supported 15.5.24 line was retained.
- PostgreSQL integration/concurrency tests are present but require the CI disposable PostgreSQL service or a separately configured disposable database; ordinary local tests continue to use SQLite and do not prove PostgreSQL locking/index/query behavior.
- Docker image builds, container health checks, and restore procedures were not executed here because Docker is unavailable and no live database may be accessed. Restoration is documented, not proven.
- Capacity values are starting limits for one company and moderate daily billing; PDF CPU/memory, database pool sizing, storage growth and worker concurrency require load validation.

### Deferred phases

GST integration, inventory and batch/lot workflows, commercial documents, payments, offline support and Android remain deferred. No later product phase was implemented.
- Docker and live PostgreSQL startup were not run in this local-only pass. Migration SQL rendering passed. Chromium PDF execution remains environment-blocked as recorded above.

Stop after Phase 5A. Do not implement later phases without an explicit prompt.

## Phase 5A: receivables, payment allocation and reconciliation

### Implemented

- Added forward migration `20260916_0012_receivables.py`, separate `receipts` and `receipt_allocations` ledgers, payment audit logs, persistent payment idempotency records, customer credit limits/overrides, and explicit invoice currency defaulting to INR for historical rows.
- Added atomic, branch-authorized receipt creation, partial/multi-invoice allocation, derived unallocated customer credit, currency matching, allocation limits, row locks, duplicate-request replay, payload conflict detection, and audited receipt/allocation reversals.
- Kept invoice approval status independent from payment status. Statements and ageing derive outstanding, overdue and ageing buckets from approved invoices and non-reversed allocations; no invoice is marked paid by this module.
- Added paginated receipt history, customer statements, ageing, reconciliation, and Manager/Admin-only statement CSV export APIs. Added the authenticated `/payments` screen for recording receipts and viewing unallocated credit.
- Added Admin-managed credit limits and reason-required Admin/Manager credit overrides with audit history. No general ledger, opening-balance assumption, payment gateway, GST integration, inventory flow, or PDF template was added.

### Verification evidence

- `cd backend && ./.venv/bin/python -m pytest tests/test_phase5a_payments.py -q` — **5 passed**.
- `cd frontend && npm run lint && npm run type-check && npm run build` — **passed**, 20 static routes including `/payments`.
- `cd backend && ./.venv/bin/python -m alembic upgrade head --sql` — **passed**, renders through `20260916_0012`.
- No live database was accessed and no PDF implementation/template was modified.

### Remaining limitations

- Existing invoices begin with no assumed payment/opening balance. Opening-balance import and accounting-system reconciliation require an explicit client policy and external accounting authority.
- Payment status is intentionally derived by reporting queries rather than stored on invoices. Real PostgreSQL locking/concurrency guarantees require the disposable PostgreSQL integration suite/CI; local unit/API tests use SQLite.

### Deferred phases

GST integration, inventory and batch/lot workflows, commercial documents, offline support and Android remain deferred. Payment-gateway integration and a general ledger remain outside Phase 5A.

## Phase 5B: integration readiness for accounting and applicable GST workflows

### Completed

- Identified the available integration inputs: no provider documentation, credentials, sandbox access, approved accounting mappings, or confirmed GST applicability requirements exist in the repository or local configuration. No provider or GST obligation was assumed.
- Added forward migration `20260916_0013_integration_readiness.py` with durable outbound integration jobs, immutable request snapshots, scoped payload-hash idempotency, bounded retry metadata, external reference/status/timestamp fields, response/failure fields, append-only integration audit logs, and reconciliation records.
- Added provider-agnostic `/api/v1/integrations` endpoints for readiness, job creation/listing, retry, cancellation, invoice local-versus-external status, reconciliation, and invoice-number review. Unconfigured providers persist `unavailable` jobs and never fabricate an external acceptance or make an outbound request.
- Kept local invoice approval separate from external job state. Claimed user-entered IRN/e-way or other identifiers do not populate authoritative external fields. Admin/Manager access is branch-scoped; Staff access is denied server-side.
- Added the `/integrations` operational screen with truthful unavailable, error, empty, retry and cancellation states. The frontend retains the same idempotency key across a failed create retry.
- Documented required client inputs, future provider-adapter validation, uncertain outcomes, reconciliation recovery, current `PBPL/{financial_year}/NO. {sequence:05d}` numbering compatibility, and the accounting-approval gate for any future series change in `docs/INTEGRATION_READINESS.md` and `docs/BILLING_CONTEXT.md`.

### Verification evidence

- `cd backend && ./.venv/bin/python -m pytest tests/test_phase5b_integration_readiness.py -q` — **6 passed**; one existing Starlette/httpx deprecation warning remains.
- `cd backend && ./.venv/bin/python -m alembic upgrade head --sql` — **passed**, renders through `20260916_0013`.
- `cd frontend && npm run lint && npm run type-check && npm run build` — **passed**, production build generated 21 static routes including `/integrations`.
- Protected invoice and purchase-order PDF generators, templates, CSS, fonts, logos, layouts and pagination files were not modified by Phase 5B.

### Remaining blockers and limitations

- Live accounting or GST synchronization is unavailable until the client supplies a provider, documentation, sandbox credentials, approved mappings, and applicability/accounting approval. No external submission can be tested or claimed yet.
- The current adapter boundary records `unavailable`; no worker or outbound network adapter is enabled. A future adapter must validate provider responses and handle uncertain outcomes before any acceptance state is added.
- Numbering compatibility with a provider or statutory workflow is not confirmed. Issued invoices are preserved and must not be renumbered without written accounting approval.
- Migration SQL was rendered but no live database was accessed. Local backend tests use the existing SQLite test fixture and do not prove PostgreSQL concurrency beyond the database constraint encoded by the migration.

### Deferred phases

Live GST integration, inventory and batch/expiry workflows, commercial documents, further payment/accounting authority work, offline support and Android remain deferred. No inventory or PDF work was implemented.

Stop after Phase 5B and wait for an explicit prompt before implementing another phase.

## Local Admin reset (2026-09-16)

- Per explicit user approval, deleted the five local user accounts (`anuj@bio.in`, `anuj@bio.com`, `anuj@pb.in`, `dev@pd.in`, `dev@pb.in`) and their dependent sessions, security/audit records, invoice/PO/payment/integration records. This removed 9 local invoices and is irreversible unless separately backed up.
- Retained company, seller/branch profile, customer and product master records. No application code or PDF implementation was changed.
- Cleared `admin_setup_state.completed_at` after the transactional reset. Verification returned zero users, zero invoices, one company, one seller/branch profile, four customers and one product.
- Local backend verification: `GET /health` returned 200 and `GET /api/v1/auth/setup-status` returned `{"available":true}`.

## Auth onboarding recovery (2026-09-16)

- Root cause confirmed: the secure Phase 2 change intentionally retired public `POST /auth/register` with HTTP 410, while the frontend only conditionally exposed first-admin setup inside the login component. This left no dedicated registration/onboarding section.
- Added `frontend/app/register/page.tsx` for one-time First Admin setup using the private `X-Setup-Token` flow. Added a `/login` link and clear closed/unreachable setup messages. Public self-registration remains disabled; Staff/Manager onboarding remains invitation-only.
- `cd backend && ./.venv/bin/python -m pytest tests/test_auth.py tests/test_session_security.py -q` — **31 passed**.
- `cd frontend && npm run lint && npm run type-check && npm run build` — **passed**, production build generated 22 routes including `/register`.
- Local runtime check: ports 8000/3000 refused connections and PostgreSQL 5432 reported no response in this environment. Start PostgreSQL and both local servers before attempting browser login/setup. No billing or PDF code was changed.

## Reagent Bill manufacturer and tax-row correction (2026-10-02)

- Fixed approval recalculation so immutable reagent transaction snapshots retain manufacturer name, manufacturer code and manufacturer article number. The confirmed defect had preserved these values in the creation revision but replaced them with nulls during approval.
- Updated only the Reagent Bill item presentation to show the bold product name, then `<manufacturer>, Artical No.: <number>`, followed by separate bold CGST/SGST (or IGST) rows aligned with their amounts. Sales Invoice and Purchase Order item layouts were not changed.
- Advanced the Reagent Bill PDF template version to `a4-reagent-bill-v2`; no migration is required.
- Added regression coverage for manufacturer preservation through draft submission and Manager approval, plus exact Reagent item-row HTML structure.
- Verification: `cd backend && ./.venv/bin/python -m pytest tests/test_invoice_pdf.py tests/test_billing_entry_flow.py -q` — **23 passed**. Headless Chromium required execution outside the restricted sandbox.
- Rendered and visually inspected `tmp/pdfs/reagent-manufacturer-flow.pdf` and its first-page PNG. Manufacturer/article text and separate CGST/SGST labels align with their amounts without clipping or overlap.
- Existing finalized invoices were not rewritten. Any finalized record already affected by the previous null-overwrite defect requires an explicitly approved repair from its preserved revision before regeneration.

## Reagent Bill item-table column update (2026-10-02)

- Changed only the Reagent Bill PDF item table: added `Sr. No.`, removed the standalone `Artical No.` column, retained the article number inside Item Description, reduced Quantity to 6%, reduced Per to 4%, and expanded Item Description to 37%.
- Applied the approved widths: Sr. No. 5%, Item Description 37%, HSN/SAC 11%, GST 7%, Quantity 6%, Rate 10%, Per 4%, Disc % 7%, Amount 10%.
- Added Reagent-only compact cell padding so `Quantity` and units such as `KGS` remain on one line at the approved narrow widths. Sales Invoice and Purchase Order layouts were not changed.
- Advanced the Reagent Bill template version to `a4-reagent-bill-v3`; no migration is required.
- Verification: `cd backend && ./.venv/bin/python -m pytest tests/test_invoice_pdf.py -q` — **14 passed**. Rendered and visually inspected `output/pdf/reagent-bill-layout-v3.pdf`; the item table has no clipped text, mid-word wrapping or misaligned tax rows.

## Sales Invoice transport metadata preview (2026-10-02)

- Updated only the Sales Invoice header so Invoice Details now renders exactly in this order: PO No., Invoice No., Invoice Date, Delivery Note Date, Dispatched through, Vehicle No., LR No., and Payment Terms.
- Sales Invoice IRN/QR, PO Date, E-way Bill and acknowledgement rows are no longer rendered in the header; their stored transaction data is unchanged. Reagent Bill and Purchase Order metadata layouts remain unchanged.
- Advanced the Sales Invoice template version to `a4-invoice-v2`; no migration is required. Bank Details and the Quantity/Calculation table were left in place because rendered examples showed sufficient spacing.
- Added focused ordering/visibility coverage and updated PDF metadata expectations. `tests/test_invoice_pdf.py` — **15 passed**; the two PDF-generation metadata tests — **2 passed**.
- Full backend suite: **214 passed, 8 skipped, 2 unrelated existing MFA failures** in `test_account_provisioning_mfa.py` (`mfa_required` expectation and missing `UserRole` import). These were outside this Sales Invoice PDF scope.
- Rendered and visually inspected `output/pdf/sales-invoice-details-with-transport.pdf` and `output/pdf/sales-invoice-details-without-transport.pdf`. Final user confirmation of these previews is pending.

## Sales Invoice single-page short-table layout (2026-10-02)

- Reduced the reserved item-table body height from 64 mm to 42 mm only for short Sales Invoices containing up to five lines. The existing 64 mm default remains unchanged for Purchase Orders, Reagent Bills, and longer Sales Invoices.
- Advanced the Sales Invoice PDF template version to `a4-invoice-v3`; no migration is required.
- Added a focused PDF regression proving that a one-item Sales Invoice renders exactly four A4 pages, one page for each copy, and that the Sales-only table class is not applied to Purchase Order or Reagent contexts.
- Focused verification: `cd backend && ./.venv/bin/python -m pytest tests/test_invoice_pdf.py tests/test_invoices.py::test_pdf_generated_status_transition_is_recorded tests/test_invoices.py::test_approved_invoice_generates_downloadable_pdf_and_persists_metadata -q` — **18 passed**.
- Full backend verification: `cd backend && ./.venv/bin/python -m pytest -q` — **215 passed, 8 skipped, 2 unrelated existing MFA failures** in `test_account_provisioning_mfa.py` (`mfa_required` expectation and missing `UserRole` import).
- Regenerated and visually inspected `output/pdf/sales-invoice-42mm-preview.pdf`; `pdfinfo` reports four A4 pages and the green bottom line plus Canvatech branding remain contained on each copy's page.

## Staff-entered Sales Invoice number (2026-10-02)

- Added a Sales Invoice-only number control with the `PBPL/{financial_year}/` prefix and a required staff-entered suffix. The financial year now follows the invoice date on the Indian 1 April–31 March boundary. The suffix accepts uppercase letters, numbers, hyphens and slashes up to 30 characters and is shown with a field-level error when missing, malformed or duplicated.
- The backend now stores the complete invoice number on draft creation, permits version-checked changes while the invoice remains a draft, enforces global uniqueness through validation plus the existing database constraint, and preserves the exact number through submission, approval and PDF generation. Existing issued invoices were not rewritten.
- Purchase Order and Reagent Bill numbering remain unchanged. No PDF template/layout file or database migration was required.
- Updated the integration numbering review and readiness documentation to distinguish preserved historical auto-numbered invoices from the new client-approved Sales Invoice series.
- Backend invoice workflow verification: `cd backend && ./.venv/bin/python -m pytest tests/test_invoices.py tests/test_billing_entry_flow.py tests/test_financial_correctness.py tests/test_phase3_workflows.py -q` — **42 passed**. Numbering review regression — **1 passed**.
- Full backend verification: `cd backend && ./.venv/bin/python -m pytest -q` — **218 passed, 8 skipped, 2 unrelated existing MFA failures** in `test_account_provisioning_mfa.py` (`mfa_required` expectation and missing `UserRole` import).
- Frontend verification: `cd frontend && npm run type-check`, `npm run lint`, and `npm run build` — **passed**; the production build generated 23 application routes.

## Centered PDF item-table headings (2026-10-02)

- Centered every item-table column heading horizontally and vertically in the shared Sales Invoice, Purchase Order, and Reagent Bill PDF layout. Body-cell alignment, column widths, colors, borders, spacing, and pagination were not changed.
- Advanced the affected template versions to `a4-invoice-v4`, `a4-purchase-order-v2`, and `a4-reagent-bill-v4`; no migration is required.
- Added a browser-computed-style regression proving all rendered item-table headings resolve to centered/middle alignment.
- Targeted PDF and metadata verification: `cd backend && ./.venv/bin/python -m pytest tests/test_invoice_pdf.py tests/test_invoices.py::test_pdf_generated_status_transition_is_recorded tests/test_invoices.py::test_approved_invoice_generates_downloadable_pdf_and_persists_metadata tests/test_billing_entry_flow.py::test_saved_purchase_order_can_generate_previewable_downloadable_pdf -q` — **20 passed**.
- Full backend verification: `cd backend && ./.venv/bin/python -m pytest -q` — **219 passed, 8 skipped, 2 unrelated existing MFA failures** in `test_account_provisioning_mfa.py` (`mfa_required` expectation and missing `UserRole` import).
- Rendered `output/pdf/sales-invoice-centered-item-headings.pdf` as four A4 copies and visually inspected the first-page PNG. All table headings are centered without clipping, overlap, or border changes.

## Dark glossy Canvatech PDF footer branding (2026-10-02)

- Changed only the `Canvatech` word in the shared PDF footer from bright blue to bold dark black with a restrained glossy highlight/shadow. The preceding `By` remains normal-weight black, and footer position, spacing, green line, and all other invoice styling remain unchanged.
- Applied the shared footer change to Sales Invoice, Purchase Order, and Reagent Bill PDFs. Advanced template versions to `a4-invoice-v5`, `a4-purchase-order-v3`, and `a4-reagent-bill-v5`; no migration is required.
- Added a Chromium computed-style regression proving `Canvatech` renders bold dark black with a highlight while `By` remains unshadowed and normal weight.
- Targeted PDF and metadata verification: `cd backend && ./.venv/bin/python -m pytest tests/test_invoice_pdf.py tests/test_invoices.py::test_pdf_generated_status_transition_is_recorded tests/test_invoices.py::test_approved_invoice_generates_downloadable_pdf_and_persists_metadata tests/test_billing_entry_flow.py::test_saved_purchase_order_can_generate_previewable_downloadable_pdf -q` — **21 passed**.
- Full backend verification: `cd backend && ./.venv/bin/python -m pytest -q` — **220 passed, 8 skipped, 2 unrelated existing MFA failures** in `test_account_provisioning_mfa.py` (`mfa_required` expectation and missing `UserRole` import).
- Rendered `output/pdf/sales-invoice-dark-canvatech-preview.pdf` as four A4 pages and visually inspected the first page. The footer remains inside the page boundary and the dark branding is readable without clipping or overlap.

## Automatic Indian financial-year invoice prefix (2026-10-03)

- At that point Sales Invoices used a financial-year prefix and staff-entered suffix. This behavior was superseded by the shared automatic sequence recorded below.
- The frontend now displays the matching prefix for the selected invoice date and defaults new Sales Invoices and Purchase Orders to the current `Asia/Kolkata` calendar date instead of the browser's UTC date.
- The India-local date default remains in effect. Reagent and Purchase Order numbering at that point were unchanged.
- No database migration is required. No PDF generator, template, CSS, font, logo, pagination or print-layout file was changed.
- Verification at the time: backend invoice/PO/integration tests — **32 passed**; frontend India-time/FY Playwright regression — **passed**; frontend type-check, lint and production build — **passed**.

## Shared Sales and Reagent invoice numbering (2026-10-03)

This automatic-suffix policy was superseded by the later client request documented below.

- Sales Invoices and Reagent Bills now receive numbers from the same company-wide, financial-year-scoped sequence: `PBPL/{financial_year}/NO. 00001`. Numbers are assigned during approval for both types.
- The Sales-only suffix entry was removed. The PostgreSQL advisory transaction lock and persisted financial-year counter coordinate approvals; candidate numbers already present in historical records are skipped. The existing unique `invoice_number` constraint remains the final duplicate guard. No migration is required.
- Sales and Reagent registers remain filtered by document type. Dashboard register links now show separate Sales Invoice and Reagent Bill counts.
- The integration numbering review and billing context now describe the active shared series. Historical issued numbers are preserved. PDF rendering files were not changed.
- Targeted backend verification: `./.venv/bin/python -m pytest tests/test_invoices.py tests/test_billing_entry_flow.py tests/test_financial_correctness.py tests/test_phase3_workflows.py tests/test_phase5b_integration_readiness.py -q` — **50 passed**.
- Frontend verification: `npm run type-check` and `npm run lint` — **passed**; `npm run build` — **passed**. The focused invoice-entry Playwright regression confirmed India-local date defaults and removal of manual invoice-number input.
- Full backend suite: `./.venv/bin/python -m pytest -q` — **221 passed, 8 skipped, 2 failed**. Both failures are in the pre-existing privileged-MFA lifecycle tests (`test_privileged_mfa_enrollment_and_recovery_full_lifecycle` expects MFA to be enforced despite the current disabled-MFA flow; `test_mfa_recovery_replacement_and_administrative_reset` reaches an existing `NameError: UserRole is not defined`). PostgreSQL-only checks were skipped because `TEST_SECURITY_DATABASE_URL` is not configured. These are unrelated to invoice numbering and were not changed.
- `git diff --check` — **passed**. No database migration was needed; invoice numbering reuses the existing unique constraint, financial-year counter, and PostgreSQL advisory lock. PDF generator/template/layout files were not changed for this numbering work.

## Manual Invoice No. on Sales and Reagent forms (2026-10-03)

- Restored the editable `Invoice No.` field on both billing forms with the fixed `PBPL/{financial_year}/` prefix. Staff enters the suffix; no automatic suffix is assigned. The prefix follows the invoice date on the Indian 1 April–31 March boundary, and new forms still default to the current India-local date.
- New drafts require a valid suffix of 1–30 letters, digits, hyphens or slashes. Suffixes are trimmed and normalized to uppercase. The complete number is stored when the draft is saved, preserved through approval and PDF generation, and protected against duplicate numbers across Sales/Reagent and seller profiles by transaction locking plus the existing unique database constraint.
- Draft edits use the existing version check. Changing the financial year retains the entered suffix under the new prefix; conflicting edits roll back every attempted change. Invoice-number errors appear below the input. Save retries continue to use persistent idempotency.
- Existing issued numbers and separate document registers/dashboard counts are preserved. Legacy unnumbered drafts need a manual number through the existing draft PATCH API before submission; already-submitted unnumbered invoices must be returned for correction first.
- Relevant files: `backend/app/schemas/invoice.py`, `backend/app/api/v1/invoices.py`, `backend/app/api/v1/integrations.py`, `frontend/app/components/InvoiceEntryPage.tsx`, `frontend/app/lib/indiaDate.ts`, affected invoice test fixtures, and the focused frontend invoice-number regression.
- No migration is required. No PDF renderer, template, CSS, font, logo, layout, pagination or print-format file was edited for this change.
- Focused manual-number regressions: `./.venv/bin/python -m pytest tests/test_invoices.py -q -k 'manual_invoice or staff_entered or preview_does or shared_number or draft_number_edit or legacy_unnumbered' --tb=short` — **12 passed**. These cover required/invalid input, cross-type and cross-profile duplicates, idempotent replay, FY changes, approval preservation and rollback of rejected edits.
- Full backend verification: `./.venv/bin/python -m pytest -q --tb=line --show-capture=no` — **230 passed, 8 skipped, 2 pre-existing MFA failures**: `test_privileged_mfa_enrollment_and_recovery_full_lifecycle` expects MFA enforcement despite the disabled-MFA flow, and `test_mfa_recovery_replacement_and_administrative_reset` reaches the existing missing `UserRole` import. PostgreSQL-only tests were skipped because `TEST_SECURITY_DATABASE_URL` is not configured; real PostgreSQL concurrency remains unverified locally.
- Frontend `npm run type-check`, `npm run lint`, and `npm run build` — **passed**. `FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_invoice_financial_year_ui.py` — **passed** for both billing forms, including editable suffixes, normalization and the March/April FY boundary. The temporary verification server was stopped after the check.
- `git diff --check` — **passed**.
