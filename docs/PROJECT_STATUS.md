# Project status

## Current phase

Phase 1E - final verification and hardening.

## Status

Phase 1E is complete. Phase 1 now covers the application foundation, authentication and permissions, master records, invoice draft and approval workflow, Decimal financial calculations, immutable invoice PDF generation, final verification, and local startup/test documentation.

Last verification pass: 2026-09-16 targeted PO copy cleanup; full Phase 1E verification rerun remains 2026-09-03.

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
- Staff draft creation/submission, Manager/Admin approval, finalized-invoice immutability, idempotent submit/approve/PDF generation, and status-transition audit logs.
- Company-wide financial-year invoice numbering with PostgreSQL advisory transaction locking.
- Backend-authoritative Decimal calculations using `ROUND_HALF_UP`, including the required intrastate fixture and interstate IGST support.
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

- `cd backend && ./.venv/bin/python -m pytest -q` - passed: 99 tests, 1 existing Starlette/httpx `TestClient` deprecation warning. The browser-backed PDF tests required unsandboxed Chromium permission because restricted macOS execution denied Playwright launch.
- `cd backend && ./.venv/bin/python -m pytest tests/test_invoice_pdf.py -q --basetemp=/private/tmp/phase-1e-pdf-fixtures-pytest` - passed: 6 tests, 1 existing Starlette/httpx warning.
- PDF-to-PNG validation with `pdftoppm -png -r 144` - passed for all generated fixtures.
- PDF fixture page counts and size:
  - `one-item-cgst-sgst.pdf` - 4 pages, 4 PNGs, A4 `594.96 x 841.92 pts`.
  - `twenty-items-cgst-sgst.pdf` - 8 pages, 8 PNGs, A4 `594.96 x 841.92 pts`.
  - `eighty-items-cgst-sgst.pdf` - 20 pages, 20 PNGs, A4 `594.96 x 841.92 pts`.
  - `long-address-description-terms.pdf` - 8 pages, 8 PNGs, A4 `594.96 x 841.92 pts`.
  - `one-item-igst.pdf` - 4 pages, 4 PNGs, A4 `594.96 x 841.92 pts`.
- Visual PNG inspection - passed for short invoice balance, all four copy labels, continuation identity/table headings, final-page totals/terms/signature/footer, long address/product/terms wrapping, and IGST tax summary.
- `cd backend && ./.venv/bin/python -m alembic upgrade head --sql` - passed: migration SQL rendered through revision `20260827_0003`.
- `cd frontend && npm run lint` - passed.
- `cd frontend && npm run type-check` - passed.
- `cd frontend && npm run build` - passed: Next.js production build generated 13 static pages including `/invoices`.
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
