# Billing context

## Product

This project is a chemical/raw-material billing system for one company in single-company mode. Branch selection is no longer part of the user workflow. The app uses one Seller/GST profile for legal seller identity on invoices and purchase orders. It is a web PWA first, with Android support planned later.

The system must support a controlled invoice workflow:

- Staff creates invoice drafts.
- Manager or Admin approves invoices. Admins may approve their own invoices and purchase orders.
- Approval is a business control and must remain distinct from draft creation.

Batch/lot inventory is deferred. Live GST IRN and e-way bill integration is also deferred.

## Phase 1 boundary

Phase 1 delivers the billing foundation and an accurate PDF generator. The foundation should establish the core company and Seller/GST profile context, users and roles, invoice draft/approval lifecycle, billing data needed by the approved layout, and deterministic invoice PDF output.

Do not implement batch/lot inventory, live GST IRN generation, live e-way bill integration, Android-specific functionality, or other future-phase behavior unless a later prompt explicitly requests it.

## Roles and permissions

| Role | Phase 1 responsibility |
| --- | --- |
| Admin | Full administrative access, including invoice approval |
| Manager | Invoice approval capability |
| Staff | Create and save invoice drafts; cannot approve invoices |

The exact permission matrix may be refined in a later implementation prompt, but the draft/approval separation is locked.

## Authorized Phase 2 security policy

The explicit Phase 2 prompt authorized authentication/session/sensitive-permission hardening beyond Phase 1 only. Seller identity, GST and bank-default edits, roles and assignments are Admin-only; assigned Staff draft creation and Manager/Admin approval remain. By the later client decision recorded in project status, Admin registration is currently repeatable and does not require a first-admin setup gate or master password. Staff and Manager accounts continue to use invitations so branch assignments remain controlled. Revocable HttpOnly cookie sessions replace localStorage tokens. Authenticator MFA and recovery-code setup were later disabled by explicit client decision. Existing hashes transition through a restricted password-upgrade session; issued documents and all PDF rendering files remain untouched. See `docs/SESSION_SECURITY.md` for the exact active policy, lifecycle, expiry, concurrency grace and operational limitations. Do not implement any later phase.

The client's 2026-09-16 request sets newly created or changed account passwords to 6–10 characters after NFC normalization. Existing hashes and longer passwords remain valid for login and current-password verification. Common-password blocking and Argon2 remain in effect. Authenticator MFA is disabled. No database reset or password-hash rewrite is authorized by this change.

## Locked technology stack

### Frontend

- Next.js
- React
- TypeScript
- Tailwind CSS
- Progressive Web App delivery now; Android later

### Backend and data

- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- PostgreSQL

### Deferred infrastructure

- Redis and Celery are reserved for later background jobs.

### PDF generation and verification

- Jinja2 templates
- Python Playwright with Chromium
- Pytest and Playwright testing
- Docker Compose for local and development orchestration

## Billing correctness rules

- Use `Decimal` for money and quantity values throughout the application and PDF-generation pipeline.
- Preserve exact values and explicit rounding rules from calculation through rendered output.
- Persist quantity at three decimal places, rates at four decimal places, document and line amounts at two decimal places, and GST/cess rates at two decimal places. Inputs with more precision are rejected before calculation so PostgreSQL cannot round a value and change approval totals.
- Apply `ROUND_HALF_UP` to line taxable values and taxes, then to document taxable/tax totals, and finally round the payable total to the nearest rupee. `round_off` is the difference between the rupee total and the two-decimal total.
- Document-level charges and discounts are allocated to tax groups using the existing taxable-value-weighted average GST and cess rates, with each allocated tax group rounded to two decimals before reconciliation. This is the current application policy; an accountant must confirm whether future tax rules require a different allocation basis.
- Creation requests may supply an `Idempotency-Key`. The key is scoped to the resolved branch and payload hash; a matching retry replays the original document, while a changed payload returns a conflict. Database uniqueness is the concurrency backstop.
- Customer, supplier, buyer, and consignee transaction fields are snapshotted from the submitted payload. Matching masters are not overwritten, and inactive saved masters are rejected for new transactions.
- Keep the Seller/GST profile explicit in saved invoice snapshots where it affects the legal or display output. Do not require branch selection in billing screens.
- Treat the approved invoice reference as a layout contract. Do not redesign, simplify, or omit fields without an explicit decision.
- Keep invoice approval state and audit-relevant transitions explicit and testable.
- Keep all API routes under `/api/v1`.

### Edit saved draft bills (approved 2026-10-09)

All four registers offer **Edit** for saved drafts: Sales → `/invoices?invoice={id}`, Reagent → `/reagent-bills?invoice={id}`, Purchase → `/purchase-orders?order={id}`, Reagent Purchase → `/reagent-purchase-orders?order={id}`. The PDF view also links to the editable draft. Keep existing PO amendment-pending editing; never expose direct financial editing for submitted, approved, PDF-generated, closed or cancelled records. Server-side profile authorization, optimistic versions and workflow restrictions remain authoritative.

Load transaction snapshots into the matching form, not current customer/product/seller master values. Sales/Reagent reopen in manual mode so buyer/consignee snapshots remain independently editable; resolve the saved reagent manufacturer code to an eligible manufacturer choice. Preserve stored rates, discounts, quantities, transport, dates and number. Reagent PO retains its existing saved-product flow and fixed seller rule; Domestic PO also retains fixed seller identity after save. Edited item names are transaction overrides, not product-master updates: preserve their explicit names and linked product IDs during draft PATCH even if the catalog name has subsequently changed.

Save the same document ID using `expected_version`; never create a second document to edit it. Preview the newly saved revision before Confirm, using existing approval/PDF actions. Failed or invalid-ID/wrong-type opens must block saving and offer Retry, not fall back to a blank creation form. Conflicts retain entered fields and offer an explicitly confirmed **Reload latest revision**. All four forms retain unsaved same-tab work; opening a different saved bill prompts before replacing it. Cancelling retains the current work; Start new bill/order removes the edit query and clears only the current entry, without deleting the saved record. Existing PDF implementation, formatting, financial calculations and issued history remain protected. No migration is required.

### Saved-buyer billing/shipping address choice (approved 2026-10-09)

Sales and Reagent **Use saved data** entry offers two mutually exclusive checkboxes after buyer selection: **Use billing address for shipping** and **Use saved shipping address**. A newly selected buyer defaults to its saved shipping address when present, otherwise billing. If no shipping address is saved, disable that choice and explain why. Copy the selected complete address (both lines, city, state, state code and PIN) into the existing consignee transaction payload; the buyer panel retains the billing address. Keep consignee name, PAN, phone and email independently editable, and preserve those entered fields when switching address sources.

Retain the source choice and copied address in the existing same-tab, authenticated-user entry session. Navigation and master reloads must not silently reset reviewed transaction addresses or a manually edited place-of-supply code. Changing buyers initializes a new default address; explicit source changes copy that source from the selected saved customer. Address switching does not change the existing separately editable place-of-supply/tax behavior. Preview, save, edit and approval use the existing snapshotted consignee/PDF interface. No master changes, historical rewrites, PDF formatting changes, migration or PO behavior changes are required.

### Saved-buyer GSTIN identity (approved 2026-10-09)

Normalize newly supplied buyer GSTINs by trimming and uppercasing, and match within the existing authorized seller-profile scope. Customer creation and inline Sales/Reagent buyer saves reuse the oldest active matching master without overwriting its name/address. A supplied, different GSTIN must never fall back to matching name/phone. If only inactive matches exist, reject a new transaction/recreation and require explicit reactivation. Master GSTIN/profile changes and reactivation must not create another matching identity. Buyers without GSTIN remain independent; no-GSTIN inline matching retains name/phone compatibility only against other no-GSTIN masters.

Manual consignee details remain transaction snapshots rather than automatically creating additional buyer masters. Submitted buyer/consignee names, addresses and contacts survive GSTIN reuse, editing, submission and approval. Preserve all historical master IDs, document snapshots and financial references; do not delete, merge or rewrite existing duplicates. The billing-only `/api/v1/customers?billing=true` query returns one active choice per normalized GSTIN/profile, deduplicated before its bounded limit. Dropdowns show company names and support name/GSTIN search. Generic customer lists/detail endpoints still expose existing records for master management/history.

The approved register follow-up adds `/api/v1/customers?register=true`: one normalized GSTIN/profile, preferring the oldest active record, otherwise the oldest inactive record. Customers without GSTIN remain separate. Deduplicate before `offset` and the bounded `limit`; the Customers register loads 100 at a time with **Load more customers**. This is a view, not a historical merge/deletion. **Edit** loads the chosen record's ID and separate billing/shipping fields; Update uses PATCH, not POST, preserving its profile assignment. Omitted addresses remain unchanged; explicit null clears optional shipping, while null name/billing address/profile/active status returns field-level validation errors. GSTIN collisions remain server-side conflicts shown beneath GSTIN. Generic lists and historical detail IDs remain available.

PostgreSQL transaction-scoped advisory locks serialize application customer creation, inline buyer saves and identity-changing master edits on the same normalized identity until commit/rollback. SQLite tests do not prove this concurrency guarantee; use the opt-in disposable PostgreSQL regression. No uniqueness migration or historical cleanup is authorized here; external SQL/import writers must adopt the same locking rule. The frontend picker searches its bounded returned list (100 unique choices by default), not an unlimited database search.

### Shared document-number families (confirmed 2026-10-08)

Sales Invoices and Reagent Bills share one live invoice-number namespace; Domestic Purchase Orders and Reagent Purchase Orders share another live PO-number namespace. Never scope uniqueness to document type or give either subtype a separate number reservation. Backend create/edit checks and database unique constraints apply across both types in each family. Duplicate live numbers return HTTP 409. Registers and dashboard counts remain separate by document type; counts do not allocate or reserve numbers.

Keep the existing manual number inputs: both invoice forms accept a suffix under `PBPL/{Indian financial year}/`, and both PO forms accept the full PO number. Sharing a namespace does not introduce automatic invoice suffix allocation, force consecutive manual numbers or merge invoice and PO namespaces. Preserve issued identifiers and the documented fresh-save reuse exception after successful Admin permanent deletion.

### Company header and pickup addresses

For newly created Sales Invoices, Reagent Bills, Domestic Oils POs and Reagent POs, the address below the company brand comes from `Company.registered_address`, independently of supplier details. Configure it in Seller/GST profile → Registered address. If it is blank, capture the GST-profile address as a compatibility fallback; never use a supplier address for the company header. Supplier saves only update supplier records.

Pickup Address is captured separately: Sales/Reagent entry has an active, seller-profile-scoped Supplier selection section with server-side name search. The default prefills a new bill, but the bill maker can choose another supplier or explicitly choose no pickup supplier. An omitted API `supplier_id` retains default-supplier compatibility; explicit null means no pickup supplier. POs retain their existing selected/manual supplier transaction address flow. Never copy the company address into Pickup Address.

Company and pickup snapshots are retained during submission/approval. Versioned draft edits may explicitly change the selected supplier and pickup snapshot without changing the company header. Including an unchanged supplier ID in an otherwise edited draft must preserve its saved pickup address, even if the master was edited/deactivated. Active masters are required for new selections. Master changes affect future documents, not saved transaction addresses. Used suppliers, including those retained in invoice revision history, must be deactivated rather than deleted; unused suppliers may be permanently deleted.

Migration `20261004_0020` adds nullable snapshots without backfilling old documents. Legacy bills retain their former address-data mapping and stored PDF references; do not rewrite/reissue them automatically. Existing PDF context interfaces, templates, CSS, fonts, logos, pagination and print formatting remain unchanged.

Migration `20261004_0021` adds nullable invoice `supplier_id` with a foreign key and index. Do not infer/backfill historical supplier associations from address text. Explicit supplier selection participates in creation idempotency; omitted selection preserves legacy request hashes. Supplier searches are bounded to 100 matches in the picker; search by name to find records outside the initial result window.

## Reference status

### Domestic Purchase Order dispatch entry (authorized update, 2026-10-08)

Domestic PO entry includes an optional **Dispatched through** textbox alongside order dates/payment terms. It accepts free text up to 100 characters, matching the existing `transport_mode` schema/database column. Trim before submission; blank explicitly clears the value. Creation and versioned full-draft edits persist it; an omitted edit field preserves the saved value. Show related validation errors beneath this field and retain entered work during retries/editing. The saved transaction value flows to the existing Invoice Details row in new Domestic PO PDFs (`a4-purchase-order-v10`). No template/CSS/layout, calculation or migration change is needed. Preserve approval immutability, historical files and the other bill formats.

### Domestic Purchase Order delivery date (authorized update, 2026-10-08)

The Domestic Purchase Order entry already omits Delivery Note Date and retains an optional Expected Delivery Date input. New Domestic PO PDFs omit the Delivery Note Date row and show a supplied Expected Delivery Date under Invoice Details, immediately after PO Date. Do not repeat it in Seller / Shipping Address; if no expected date was supplied, omit that row. This presentation uses `a4-purchase-order-v9`. Preserve stored dates and historical PDFs, the entry form, single-copy/four-product pagination, and all other content. Sales, Reagent Bills and Reagent POs retain their existing delivery-date placement and versions. No migration is needed.

### Sales Invoice party contacts and transport (authorized update, 2026-10-08)

New Sales Invoice PDFs show buyer and consignee phone numbers under `Contact:` and emails on a separate `Email:` line. Missing values omit only their own row. Vehicle No. and LR No. remain in Invoice Details and are not repeated in Consignee / Shipping Details; other shipment fields are unchanged. This Sales-only presentation uses `a4-invoice-v11`, with the existing template/CSS, four copies and pagination. Reagent Bills and both PO formats retain their existing mappings and versions. Preserve stored historical PDFs; no transaction data or migration changes are required.

### One copy per purchase order (authorized update, 2026-10-08)

New Domestic Purchase Order and Reagent Purchase Order PDFs each contain **one complete copy**, labelled `Purchase Order`. Preserve four-product-per-page pagination: a five-product PO contains two pages of the same copy, not four repeated copies. Sales Invoices and Reagent Bills retain their four existing copy labels. This supersedes earlier four-copy Reagent PO instructions only. Reagent PO uses `a4-reagent-purchase-order-v13`; Domestic PO remains `a4-purchase-order-v8`. Preview and final generation use the same context policy; existing stored PDFs remain unchanged. No forms, calculations, templates, CSS or pagination rules change.

### Reagent quantity display (authorized update, 2026-10-08)

In newly generated Reagent Bill and Reagent Purchase Order PDFs, the item-table **Quantity** cell contains only the entered numeric quantity, using the existing Decimal quantity formatter (for example `12`, `0.125`, `1234.5`). Do not append KG, GM, ML or any other unit/Per label. The client's follow-up makes these numeric values **bold at the same existing font size**. Units remain required/stored in transaction data and entry forms; calculations and Pack/Size are unchanged. Sales and Domestic PO quantity presentation retain their existing units and regular weight. This supersedes earlier reagent-only rules that printed the unit beside Quantity. New reagent versions are `a4-reagent-bill-v13` and `a4-reagent-purchase-order-v12`; existing stored PDFs are not rewritten.

### Four-product physical pages (authorized correction, 2026-10-08)

Sales Invoices, Reagent Bills, Domestic POs and Reagent POs accept any supported document line count, but newly rendered PDFs contain at most **four products per physical A4 page**. Product five begins a new complete page; normal ten-product documents paginate 4/4/2 per copy. Repeat the existing identity, party panels, table headings, bank details, terms, signature and footer on each product page. Preserve global serial numbers and existing copy-label behavior. Quantity, amount-in-words and all document calculation values are blank on intermediate pages and filled only on the final product page; line amounts/taxes remain visible beside their own products.

This correction supersedes continuous item-table flow and the separate Reagent PO closing sheet. Chromium measures real print-width content, maintains a common table/settlement depth across product pages, and uses bounded subdivision for unusually tall product rows (fewer than four may be necessary). Reclaim unused table whitespace before splitting; never clip rows, omit fixed text, or create a product-free calculation page. If even one product plus the complete fixed content cannot fit, PDF preview/generation returns a clear HTTP 422 asking for shorter oversized description/address/terms. Arbitrarily long combined text cannot fit a single A4 sheet at unchanged font sizes. No calculation or snapshot is rewritten.

New versions: Sales `a4-invoice-v10`, Domestic PO `a4-purchase-order-v8`, Reagent Bill `a4-reagent-bill-v11`, Reagent PO `a4-reagent-purchase-order-v10`. Restart/reload the backend and generate a new PDF. Existing stored PDFs remain unchanged; no migration is required.

The approved reference is named `AOPL 00937 (1).pdf`. The supplied four-page PDF was visually inspected and its fields, table columns, copy labels, and pagination rules are recorded in `docs/REFERENCE_INVOICE_MAP.md`.

## Financial-policy note

No effective-dated tax-rule table or tax-rule service exists in the current repository. The phase preserves the established line-rate calculation and documents the existing weighted allocation for document-level adjustments; it does not invent a statutory rate list. Before introducing maintained tax rules or changing adjustment allocation, obtain the accounting decision on effective dates, tax-group allocation, and treatment of mixed-rate documents.

## Working conventions

Read this file and `docs/PROJECT_STATUS.md` before work. Work only on the requested phase, preserve existing working code, add targeted tests for changed behavior, run targeted tests during development, and run the full suite only at phase completion. Update `docs/PROJECT_STATUS.md` before stopping. Future phases must not be implemented without an explicit prompt.

## Phase 3 operational workflow policy

The Sales Invoice, Domestic Oils PO, Reagent Bill and Reagent PO entry pages intentionally omit recent-document buttons and embedded lists/registers. The client's approved 2026-10-06 exception adds top-right **Sales invoices** and **Reagent bills** links on the corresponding entry pages to `/bill-registers/sales` and `/bill-registers/reagent`; it does not reintroduce embedded lists or change PO pages. Their unused list-loading requests are removed, but every backend list/register/detail/workflow API and saved record remains available. Entry forms retain master-data choices, current-document save/approval/PDF controls, and existing direct Reagent PO loading/version-conflict recovery. Do not restore embedded sections without an explicit prompt.

All four entry pages use an inline submission panel after backend totals: Preview saves/updates one versioned draft and renders its actual PDF in-page; Edit retains the same transaction and invalidates the preview; Confirm targets that exact reviewed version. Admin self-approval is allowed under the client's approved exception; Staff and creator-Managers require independent review. Download/Print unlock only for a confirmed approved document with a final stored PDF. Transient PDF-preview endpoints do not finalize documents or write stored PDF metadata/files. Never modify protected PDF layouts to implement entry/session controls. Unsaved session data stays in memory, not persistent browser storage.

All four entry sessions are retained separately by authenticated user and document kind across same-tab client navigation, including form values, draft ID/version, saved-payload signature, idempotent creation intent and in-flight save state. PO default-seller initialization runs once per entry; returning or reauthentication must not replace entered seller details, lines, dates, terms or transport with current masters. Master reloads must not replace retained consignee fields or supply-state overrides; transaction payloads must not drop those fields when a master lookup fails. Sales/Reagent also retain the explicitly selected buyer snapshot, sending it with its saved customer ID so an intervening customer master edit cannot silently change that transaction. Explicit buyer reselection captures current master details; inactive masters remain subject to backend validation.

Departed PDF blob URLs are revoked and editable drafts need a fresh preview before Confirm. Explicit Start new bill/order clears only that kind's work without deleting server records. Successful final approval/PDF confirmation keeps Download/Print on the current page and releases that entry for a fresh form on the next visit; pending approval or failed confirmation does not clear it. Successful logout/account change/disable clears all four entries and prevents late responses from repopulating them. Failed logout and same-user reauthentication retain work. Confirmed deletion invalidates matching entries in the correct invoice/PO family, including other-tab ID-only notifications, without clearing unrelated or same-numeric-ID documents from the other family. Full refresh/tab close clears memory; never persist sensitive forms to localStorage/sessionStorage to extend this behavior. Authentication expiry/refresh/security rules are unchanged.

### Explicit permanent-deletion exception (approved 2026-10-06)

Admin may permanently delete Sales, Domestic Oils Purchase, Reagent Bills and Reagent Purchase Orders from their registers, including finalized documents **only when unlinked to financial/integration history**. Staff and Manager cannot delete. Require the exact full number, document type and expected version server-side. Preserve all masters; block any receipt-allocation history (including reversed entries), any integration job, shared PDF reference or other external database dependency. Never silently cascade payments or external history. This is an explicit exception to preservation of the deleted document, not authority to alter surviving historical invoices or PDF layouts.

Owned document lines, transition audits and revisions are removed, but an independent minimal deletion audit retains actor/timestamp and identifiers/status/version. Creation-key tombstones survive removal: matching replay returns 410 rather than recreating the bill, changed-payload reuse remains a conflict. Migration `20261006_0023` introduces these nullable tombstones and the audit lookup index without historical backfill.

The client's 2026-10-08 follow-up explicitly allows reuse of a successfully deleted document's **Invoice No. or PO No.** on a new bill. Deletion already removes the live unique-number reservation; minimal deletion audits and old save-key tombstones do not reserve that number. Sales/Reagent retain their shared invoice-number namespace, and Domestic/Reagent POs retain their shared PO-number namespace. Create a new transaction with a fresh creation intent/key (the existing **Start new bill/order** flow does this automatically); never resurrect the deleted document, remove tombstones or reset numbering counters. Retries of the deleted document's original save remain 410, retries of the new save return its new document, and any duplicate number on a live document remains 409. Financial-year prefix rules and existing roles/deletion dependency protections still apply. Deletion dialogs/status and stale-save errors explain number reuse. The independent deletion audit keeps its actor/identifier evidence but is not an active bill or number reservation.

Commit document removal, audit and tombstones atomically before cleaning up explicitly referenced current/owned-revision PDF files. Never infer ownership by filename or ID, sweep orphan files, follow symlinks or delete another document's current/historical PDF. Failed cleanup remains durable and retryable through the same confirmed DELETE; report incomplete cleanup, not success. Downloaded PDFs and backups are not deleted. Matching retained invoice sessions are cleared across same-origin tabs using ID-only notifications and open entries recover as fresh forms; unrelated unsaved bills are preserved. No sensitive bill content is broadcast or persisted in browser storage.

The authorized Phase 3 adds reliable daily operations without changing the protected PDF implementation. Invoice actions are `draft -> pending_approval -> approved -> pdf_generated`; a pending invoice may return to `draft` only with a non-empty correction reason. The creator or submitter cannot approve their own invoice, and approval must target the exact submitted revision. Draft mutation carries an optimistic version when supplied by the client; stale versions receive a conflict and must be reloaded.

Purchase orders use `draft -> pending_approval -> approved`, with `amendment_pending` for a requested change, and terminal `cancelled` or `closed` states. Amendments preserve a versioned snapshot and require fresh submission and independent approval. Cancellation requires a reason. Inventory receipts and supplier accounting are deferred.

## Phase 5A receivables policy

Receipts and receipt allocations are separate financial entries. A receipt may be partially allocated across approved invoices for the same active customer and currency; the remaining amount is derived unallocated customer credit. Reversals are append-audited and excluded from balances. Invoice approval status remains independent from derived payment status, outstanding and overdue reporting. Existing invoices are not assumed paid or unpaid, and no opening balance is created without an explicit import policy. Payment writes require Decimal amounts, persistent idempotency keys, atomic row-locked transactions and branch authorization. Credit limits are Admin-managed; elevated overrides require an authorized actor and non-empty reason. The external accounting system remains the general-ledger authority; this phase does not create a general ledger, payment gateway, GST integration, inventory workflow or PDF template.

## Phase 5B integration-readiness policy

The client has not yet supplied an accounting/GST provider, documentation, sandbox credentials, approved mappings, or confirmed GST applicability requirements. Do not assume a provider, turnover threshold, registration, or statutory workflow. The integration boundary uses durable, branch-scoped outbound jobs with immutable request snapshots, payload-hash idempotency, database uniqueness for concurrent retries, bounded attempts, explicit unavailable/uncertain/failure states, response validation boundaries, audit history, and visible reconciliation records. Local invoice approval is separate from any external status. User-entered IRN/e-way values are never authoritative external acceptance. Existing issued invoice numbers are preserved. Sales Invoices and Reagent Bills use `PBPL/{financial_year}/{staff_entered_suffix}`: staff must enter the suffix on both forms, and the backend derives the prefix from the invoice date using the Indian 1 April–31 March financial year. Numbers are stored on draft creation and must be unique across both types; approval preserves the entered number. There is no automatic suffix allocation. Each type retains its separate register/count. No live network adapter, GST submission, inventory workflow, or PDF change is authorized until the client supplies the required inputs. See `docs/INTEGRATION_READINESS.md`.

## Reagent manufacturer and product catalog

### Reagent purchase orders

Purchase orders have two explicit types: `domestic_oils` (the existing PO workflow) and `reagent` (dedicated entry at `/reagent-purchase-orders`, with register APIs retained for future UI work). Reagent purchase orders use the same independent manufacturer/product selection, canonical units, article code, percentage discounts and Decimal tax calculation as Reagent Bills, but remain purchase-order records with their own PO numbering and approval/amendment history. They do not consume invoice numbers or create receivables, stock movements or supplier-accounting entries. Reagent PO previews are read-only; approved POs are immutable until an audited amendment, and version checks are mandatory for their edits/transitions. Final reagent PO PDFs require approval and use the reagent item format plus PO identity, bank/terms defaults and four copies. Existing Domestic Oils entries and PDF formatting must remain unchanged.

Both PO entry pages accept a full manually entered **PO No.** without a forced prefix. New numbers are trimmed, uppercased and limited to 100 printable characters on one line; duplicates are rejected across both PO types using the existing shared unique document-number column. Omission retains the original automatic PO series for compatibility. A draft number edit requires its current version and invalidates the current PDF reference without deleting an older file. Approved numbers cannot be changed, including through amendments, and historical identifiers are never normalized retrospectively. The existing PDF identity interfaces display the saved number without rendering/layout changes. Creation retry keys include supplied manual numbers, while older automatic-number request hashes remain compatible.

Manufacturers are separate active/inactive master records with a seller-profile-scoped unique code (for example, `SIG` or `MRK`). Products may link to a manufacturer and store its product/catalog code independently from the product name. Manufacturer/product codes are normalized to uppercase for matching; product codes must be unique within a manufacturer and seller profile. The Product screen must not request or display manufacturer, manufacturer product/catalog code, unit, or base rate. Its server-side compatibility defaults (`kg` and `0.0000`) preserve the existing non-null storage contract for new product records. Deactivate records rather than deleting records referenced by documents.

Reagent lines must use an active manufacturer and one of the canonical unit symbols `g`, `kg`, `mg`, `µg`, `mL`, `L`, or `t`. Existing business aliases such as `GM`, `KG`, `MG`, `ML`, and `TON` are normalized for new catalog and reagent-line writes. Reagent invoice lines preserve manufacturer name/code and product/catalog code as transaction snapshots; later master edits do not rewrite saved documents or revision history. The Reagent PDF's existing `Part No.` maps to the manufacturer product/catalog code. Its PDF layout has no separate manufacturer-code column unless explicitly requested.

For Reagent Bill entry, Product and Manufacturer are independent selections. An active product may be paired with any active manufacturer; any legacy Product manufacturer link is not used to restrict a new Reagent Bill. The selected manufacturer and line-level product code remain transaction snapshots.

Reagent Bills and Reagent Purchase Orders also accept optional line-level `pack_size` text, labelled **Pack/Size**, such as `500 g`, `100 mL` or `10 × 2 mL`. Trim text, normalize empty input to null and reject non-text, control characters or more than 100 characters. It is descriptive packaging information only: never multiply quantity/rate or change taxes using it. Save it with the transaction and revision snapshots, retain it at approval, and display it in a dedicated PDF column between Quantity and Rate. Saved master products/manufacturers are not changed by entering a pack size. Sales and Domestic Oils PO screens/tables do not gain this field.

Forward migration `20261005_0022` adds nullable `pack_size` columns to invoice and PO lines without historical backfill. Blank/omitted pack sizes preserve pre-field creation-request hashes; non-empty pack changes participate in save idempotency. Existing saved PDF files and metadata remain untouched. New Reagent PDFs use `a4-reagent-bill-v7` and `a4-reagent-purchase-order-v4`; Sales and Domestic PO template versions are unchanged.

Reagent PO terms sit bottom-left and the digital-signature block bottom-right above the existing green footer. Short copies fill the remaining space below their settlement section; long item tables retain normal-flow pagination and use a dedicated final settlement/closing sheet. The closing sections use normal, wrapping text rather than absolute positioning over invoice content. This presentation change does not automatically regenerate stored PDFs or change other bill formats.

The client's 2026-10-07 Reagent PO-only update labels the left PDF party panel **Supplier Details** and fills it from the purchase order's saved supplier snapshot: company name, full postal address, GSTIN, state code, PAN, phone and email. The right panel remains the saved consignee/shipping destination. The top and continuation-page title is **Purchase Order**. New Reagent PO PDFs use `a4-reagent-purchase-order-v5`; previously stored PDFs and other bill formats are not regenerated or changed. The entry page offers an active saved-supplier selector with a name filter, shows the selected details before saving, and retains manual supplier entry. After first save, the supplier stays fixed for that purchase order under the existing backend editing rule; a new order may choose another supplier.

## Invoice line presentation and GST breakout

Sales Invoice buyer/consignee names in both party-detail panels are bold. Reagent Bills and both Purchase Order formats retain their previous name styling; addresses, GSTIN, PAN and contact values retain their existing styling in every format.

Sales Invoice Item Details shows the saved transaction product name in bold, followed by its line Description in smaller regular text. Description line breaks and long-text wrapping are preserved. Empty or name-only fallback descriptions do not create an extra blank/duplicate line. Legacy contexts without a separate product-name snapshot use their existing description as the primary line rather than reading or inventing current catalog data. Reagent and both PO item presentations are unchanged by this Sales-only change. Existing stored PDFs are not automatically regenerated.

Reagent Bill and Reagent PO item descriptions use the transaction's product name as the primary bold line. The next line uses the saved transaction snapshot to show `MFG: <manufacturer name>, Artical No.: <number>` in regular text at 85% of the product-name font size, with safe wrapping. If the manufacturer name was not saved, its saved code is used; absent manufacturer/article values are omitted without an empty `MFG:` prefix or blank secondary line. The bold CGST/SGST or IGST rate breakdown follows directly below that secondary line. Their current table columns are Sr. No., Item Description, HSN/SAC, GST, Quantity, Pack/Size, Rate, Per, Disc % and Amount; the article number remains in Item Description, not a separate column. Domestic Oils Purchase Order item rows retain their existing presentation.

For Reagent Bills, the PDF Amount cell displays the backend-authoritative taxable goods amount before GST, followed by the line tax amounts. Intrastate lines show bold CGST and SGST breakdowns (the GST rate is split equally for display); interstate lines show bold IGST. The backend Decimal calculation remains authoritative for all displayed amounts.

### Authorized four-format PDF update (2026-10-07)

This explicit client request supersedes the previous presentation rules where they differ. Sales, Reagent Bills, Domestic Oils POs and Reagent POs display company emails in the top header instead of Pickup Address, with an `Add:` prefix at the start of each company/party postal address. Pickup selection and transaction data remain intact. Seller/GST profile has an optional validated **Second email**, editable only through the existing Admin permissions and sensitive-change audit. New documents snapshot both emails at creation, including an intentional empty list; edits/approval and later profile changes preserve that list. Legacy null snapshots retain the prior primary-email fallback and never acquire the current second email automatically. Existing stored PDF files/metadata are not rewritten.

By the client's 2026-10-07 follow-up, Item Description / Item Details values are left-aligned in all four PDF formats, including product names, secondary descriptions, MFG/article text and reagent GST labels within that cell. Other item values remain centered and Amount remains right-aligned; table headings remain centered. Reagent Bill/PO descriptions have larger bold product names and a 1.3 mm gap before the regular smaller MFG/article line. Their Per PDF column is removed, its 4% width goes to Disc % (now 10%), and the unit accompanies Quantity. The discount cell shows the saved backend discount amount in bold below its percentage, prefixed `@`. Unit remains required in entry/calculations. Vehicle No. appears last in Invoice Details for both reagent formats and is omitted from their shipping panel. Both PO PDFs label their existing supplier panel **Seller** and their destination panel **Seller / Shipping Address**, without changing either party's saved data.

The Reagent PO short item body is 64 mm, matching Reagent Bills; its bank/quantity section therefore sits lower. Compact PO metadata/shipping spacing and omission of an empty IRN block retain the tested short one-page copy. Multi-page item flow and bottom closing sections are preserved.

Tax-summary amounts remain the saved backend Decimal values. Nonzero intrastate tax uses SGST/CGST with each applicable GST rate divided by two for display; interstate uses IGST with the full applicable rates and no CGST/SGST rows. Mixed-rate labels list the distinct applicable rates against the existing aggregate (for example `SGST @ 2.5%, 9%`), rather than inventing a single effective rate or recalculating tax-group amounts. Half-rates retain their exact display precision. The existing place-of-supply calculation selects the tax mode; no manual tax-amount override was introduced.

Forward migration `20261007_0024` adds nullable `branches.secondary_email` and JSON email snapshots to invoices/POs without backfill. Current PDF versions are Sales `a4-invoice-v9`, Domestic PO `a4-purchase-order-v7`, Reagent Bill `a4-reagent-bill-v10`, Reagent PO `a4-reagent-purchase-order-v9`. The alignment, PO-panel and seller-state-header follow-ups need no additional migration; restart/reload the backend and generate a new PDF. Apply the earlier email migration if it has not yet been applied.

The client's subsequent PO-only correction displays the same saved supplier/seller identity in **Seller** and **Seller / Shipping Address** on both Domestic and Reagent PO PDFs: name, postal address, GSTIN, state code, PAN, phone and email. Both headings and seller names are bold. `Contact:` displays only the saved supplier phone; a separate `Email:` line displays the saved supplier email. Either missing value is omitted independently. Reagent transport details remain on the shipping side and Vehicle No. remains last in Invoice Details. Compact Reagent PO party-line spacing accommodates the additional contact/identity rows while retaining the 64 mm short item body. Purchaser/consignee records, entered snapshots, tax calculation, API/form fields and historical stored PDFs remain unchanged; this explicitly changes their printed party mapping only. Sales and Reagent Bill party formatting remains unchanged.

The follow-up entry-page request applies the same presentation to Domestic and Reagent PO forms. Enter or select the **Seller** once; a read-only **Seller / Shipping Address** panel mirrors its company name, address, GSTIN, state code, PAN, phone and email. Both headings are bold, Contact accepts phone only and Email has its own input. The default seller is a preselection, not an override of another selected or manually entered seller. Saved-master details are read-only; manage changes in Suppliers. After first save the seller remains fixed under the existing editing rule. New Reagent orders no longer offer independent consignee entry; historical consignee snapshots remain preserved internally when editing existing orders.

The client's subsequent removal request supersedes purchaser-entry requirements on both PO pages. Domestic PO **Purchaser company** and Reagent PO **Purchaser / buyer details**, including their manual/saved choices, searches and save-for-future controls, are removed. These forms do not load purchaser masters or submit purchaser fields. Both PO types accept new orders without a purchaser; no hidden purchaser or fabricated buyer is created. Existing Purchasers master/API and historical purchaser links/snapshots remain available. On a full-details edit, omitted purchaser fields preserve the saved link/snapshot; explicit purchaser input or null retains the compatible API update/clear behavior for editable orders. Reagent PO still requires its explicit place-of-supply state code, while Domestic PO retains its existing supplier-state tax rule. Seller/shipping matching, approval rules, Decimal calculations and PDF implementation are unchanged. Existing nullable columns support this change without a migration.

All four PDF headers now include **State Code:** followed by **State:** immediately below company emails. Display the recorded seller/GST state code and uppercase seller state name, not a buyer, consignee or supplier state. Invoices preserve their saved seller-state name; a legacy/current profile fallback is allowed only when codes match. POs have a saved code but no independent seller-state-name column: use the Seller/GST profile name only if its code still matches, otherwise omit the unavailable name. Do not hardcode `27`/`MAHARASHTRA`, invent a state name, rewrite issued PDFs or change tax calculations for this display field.
