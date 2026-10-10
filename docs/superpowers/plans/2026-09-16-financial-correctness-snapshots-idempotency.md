# Financial Correctness, Snapshots, and Reliable Saves Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure invoice and purchase-order creation, preview, draft persistence, approval recalculation, transaction snapshots, and retry behavior remain financially consistent and durable.

**Architecture:** Keep the modular monolith and existing invoice/Purchase Order APIs. Centralize Decimal precision and financial validation in a small backend validation service, make the calculator validate before rounding, and use forward migrations for the quantity precision and persistent creation-idempotency records. Preserve existing invoice snapshot columns and PDF interfaces; only feed them corrected transaction data.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, Alembic, PostgreSQL Numeric, Decimal/ROUND_HALF_UP, React/TypeScript, existing API client.

**Spec:** The Phase 1 financial correctness, transaction snapshots, and reliable saves request in the current conversation.

## Global Constraints

- Preserve Next.js, React, TypeScript, Tailwind, FastAPI, SQLAlchemy, Alembic, PostgreSQL, and modular-monolith structure.
- Do not modify invoice or purchase-order PDF generators, templates, CSS, fonts, logos, page layouts, pagination, or print formatting.
- Keep Decimal values as strings across JSON boundaries and use backend Decimal calculations only.
- Keep routes under `/api/v1`; make database changes only through forward migrations.
- Preserve issued invoices and existing historical snapshots; do not rewrite existing documents.
- Validate active masters for new transactions and keep inline transaction details separate from master updates.
- A supplied `Idempotency-Key` is scoped to the resolved branch and document type; same key plus same canonical payload replays the original document, while a different payload conflicts.

### Task 1: Decimal precision and financial validation

**Files:**
- Create: `backend/app/services/financial_validation.py`
- Modify: `backend/app/services/invoice_calculator.py`
- Modify: `backend/app/schemas/common.py`
- Modify: `backend/app/schemas/invoice.py`
- Modify: `backend/app/schemas/purchase_order.py`
- Modify: `backend/app/schemas/master_records.py`
- Modify: `backend/app/models/invoice.py`
- Modify: `backend/app/models/purchase_order.py`
- Create: `backend/alembic/versions/20260916_0008_financial_precision_and_idempotency.py`
- Test: `backend/tests/test_invoice_calculations.py`
- Test: `backend/tests/test_invoices.py`

**Interfaces:**
- `financial_validation.py` exports scale constants for quantity (3), rate (4), money (2), and tax percentage (2), plus Decimal normalization/validation helpers that reject non-finite, over-precision, and Numeric overflow values.
- `calculate_invoice(...)` raises a clear financial validation exception before any invalid value is rounded; valid existing fixtures retain `ROUND_HALF_UP` behavior.

- [ ] **Step 1: Write failing validation and precision tests**

Add tests proving that `Decimal("1.0004")` quantity is rejected before persistence/calculation rather than becoming `1.000`, that non-finite values and percentage values above 100 are rejected, that a line/header discount cannot make taxable value negative, and that whitespace-only required address/party fields and nonnumeric/`00` state codes return 422 responses.

- [ ] **Step 2: Run the focused tests and verify they fail for the current reasons**

```bash
cd backend
./.venv/bin/python -m pytest tests/test_invoice_calculations.py tests/test_invoices.py -q
```

Expected failures include accepted four-decimal quantity, missing financial validation, and whitespace/state-code acceptance.

- [ ] **Step 3: Implement exact Decimal policy**

Use `Decimal.quantize` only after finite, scale, sign, and Numeric-capacity checks. Accept quantity to the existing database/PDF-compatible three decimals, rate to four, money fields to two, and GST/cess percentages to two with a logical inclusive range of `0.00` through `100.00`; do not create a fixed GST slab list. Normalize valid values to their database quantum before calculation and persistence.

- [ ] **Step 4: Make calculation reconciliation explicit**

Keep each line taxable basis and tax rounded to money precision with `ROUND_HALF_UP`. Validate line and document taxable bases before rounding. Reconcile document totals using the existing weighted-by-line-taxable allocation for document-level charges minus discounts, with document tax totals equal to the sum of rounded line taxes plus the rounded allocated document adjustment tax; document this policy in `docs/BILLING_CONTEXT.md` and record the provisional accountant confirmation need in project status if no effective-dated tax-rule model exists.

- [ ] **Step 5: Add schema validators and forward Numeric migration**

Apply the same precision validators to invoice/PO line inputs, invoice/PO header charges and discounts, product rates, and common required address/state-code fields. Keep JSON serializers returning strings. Add only a forward migration that aligns any changed Numeric storage with the accepted policy; do not rewrite historical invoice values.

- [ ] **Step 6: Run focused tests and preserve established fixtures**

```bash
cd backend
./.venv/bin/python -m pytest tests/test_invoice_calculations.py tests/test_invoices.py tests/test_billing_entry_flow.py -q
```

Expected: all existing valid calculation/workflow tests plus the new invalid-input tests pass.

### Task 2: Transaction snapshots and inactive-master enforcement

**Files:**
- Modify: `backend/app/api/v1/invoices.py`
- Modify: `backend/app/api/v1/purchase_orders.py`
- Modify: `backend/app/api/dependencies.py` only if a shared active-master helper is required
- Test: `backend/tests/test_invoices.py`
- Test: `backend/tests/test_billing_entry_flow.py`

**Interfaces:**
- Inline invoice customer/consignee payloads produce independent invoice snapshot columns even when an active matching customer exists; the matching master remains unchanged.
- Inline PO supplier payloads produce independent PO supplier snapshot columns even when an active matching supplier exists; the matching master remains unchanged.
- New transactions reject inactive customer, consignee, supplier, product, bank account, transporter, or terms masters with a clear 422 detail.

- [ ] **Step 1: Write failing snapshot and inactive-master tests**

Create old active customer/supplier masters, submit inline details with the same match identity but changed names/addresses, and assert the persisted transaction snapshot uses the submitted details while the master remains old. Mark selected masters inactive and assert invoice/PO creation rejects them.

- [ ] **Step 2: Run the focused tests and verify the current snapshot regression**

```bash
cd backend
./.venv/bin/python -m pytest tests/test_invoices.py tests/test_billing_entry_flow.py -q -k "snapshot or inactive"
```

Expected: the inline snapshot test fails because current resolution returns the old master before snapshotting.

- [ ] **Step 3: Separate master resolution from transaction snapshot assignment**

Retain existing master reuse/creation behavior without mutating masters, but pass the inline payload to dedicated snapshot setters when it was supplied. Use the master snapshot only for saved-ID requests. Preserve stored snapshots during unrelated draft PATCH operations; refresh a snapshot only when its corresponding master reference is explicitly changed.

- [ ] **Step 4: Enforce active status on every new-transaction master lookup**

Check `is_active` for saved customers, products, suppliers, bank accounts, transporters, and terms before calculation or persistence. Keep inactive historical references readable and do not alter issued documents.

- [ ] **Step 5: Run the focused snapshot/workflow tests**

```bash
cd backend
./.venv/bin/python -m pytest tests/test_invoices.py tests/test_billing_entry_flow.py -q
```

### Task 3: Persistent creation idempotency and retry-aware frontend saves

**Files:**
- Modify: `backend/app/models/invoice.py`
- Modify: `backend/app/models/purchase_order.py`
- Modify: `backend/app/api/v1/invoices.py`
- Modify: `backend/app/api/v1/purchase_orders.py`
- Modify: `frontend/app/invoices/page.tsx`
- Modify: `frontend/app/purchase-orders/page.tsx`
- Test: `backend/tests/test_invoices.py`
- Test: `backend/tests/test_billing_entry_flow.py`
- Test: `frontend` targeted lint/type-check (no new frontend test framework)

**Interfaces:**
- `POST /api/v1/invoices` and `POST /api/v1/purchase-orders` accept `Idempotency-Key` headers.
- Canonical payload hashes are computed from Pydantic JSON-mode data with sorted keys and explicit nulls, scoped by resolved branch and document type.
- A replay with the same key/hash returns the original document without a second invoice/PO; a same-scope key with another hash returns HTTP 409.
- Frontend save handlers retain a key/signature pair for the same intended payload across retries and generate a new key after success or when the payload changes.

- [ ] **Step 1: Write failing replay/conflict tests**

Post each payload twice with one key and assert one row plus the original response; post a changed payload with the same key and assert 409. Include PO coverage and assert the idempotency mapping survives a new SQLAlchemy session. Add a database uniqueness test for the scoped key constraint.

- [ ] **Step 2: Run focused idempotency tests and verify they fail before implementation**

```bash
cd backend
./.venv/bin/python -m pytest tests/test_invoices.py tests/test_billing_entry_flow.py -q -k "idempot|retry|duplicate"
```

Expected: current endpoints create a second document and do not return a conflict.

- [ ] **Step 3: Add idempotency tables and forward migration**

Create invoice and PO creation-request models with branch scope, key, canonical payload hash, document foreign key, and a unique `(branch_id, idempotency_key)` constraint. Add them to the existing forward migration without modifying PDF tables or historical documents.

- [ ] **Step 4: Implement race-safe persistence**

Resolve branch first, insert the request record before document creation, flush to let the database unique constraint arbitrate concurrent requests, recover an existing record after a uniqueness conflict, compare hashes, and return the recorded document or 409. Keep document and idempotency-record writes in one transaction so failed creates leave no reusable key.

- [ ] **Step 5: Add frontend retry keys**

Use a ref holding `{ key, payloadSignature }`; send `Idempotency-Key` on create requests, reuse it only when the canonical form payload is unchanged, and clear it after a successful save. Do not add keys to preview calls.

- [ ] **Step 6: Run backend and frontend targeted checks**

```bash
cd backend
./.venv/bin/python -m pytest tests/test_invoices.py tests/test_billing_entry_flow.py -q
cd ../frontend
npm run lint
npm run type-check
```

### Task 4: Documentation and phase verification

**Files:**
- Modify: `docs/BILLING_CONTEXT.md`
- Modify: `docs/PROJECT_STATUS.md`
- Do not modify: `backend/app/services/invoice_pdf.py`, `backend/app/templates/invoice/v1/**`, or any PDF rendering implementation file.

- [ ] **Step 1: Document the rounding and idempotency contracts**

Record accepted Decimal scales, `ROUND_HALF_UP` stages, document-adjustment allocation policy, inactive-master behavior, snapshot semantics, and required frontend/API retry-key behavior.

- [ ] **Step 2: Run migration SQL and targeted/full phase checks**

```bash
cd backend
./.venv/bin/python -m alembic upgrade head --sql
./.venv/bin/python -m pytest -q
cd ../frontend
npm run lint
npm run type-check
npm run build
```

- [ ] **Step 3: Verify protected PDF files are unchanged**

Use a recorded file checksum before and after implementation for the invoice/Purchase Order generator files, templates, CSS, fonts, logos, and print layout assets. Report the result in project status without changing any of those files.

- [ ] **Step 4: Update `docs/PROJECT_STATUS.md` before stopping**

List implementation changes, migration revision, exact commands/results, the accountant decision needed for provisional document-adjustment allocation if applicable, and remaining limitations. Confirm no PDF implementation file changed.
