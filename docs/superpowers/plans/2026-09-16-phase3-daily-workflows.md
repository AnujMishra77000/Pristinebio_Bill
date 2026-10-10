# Phase 3 Daily Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make daily invoice and purchase-order work revision-safe, auditable, searchable and operationally reliable.

**Architecture:** Add forward-only workflow/version/history columns and append-only audit records to the existing transaction models. Keep the existing invoice and PO endpoints compatible while adding explicit action and register endpoints. Frontend entry pages retain their current visual identity and use the new operational APIs for status, conflict recovery and approvals.

**Tech Stack:** Next.js, React, TypeScript, Tailwind, FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL.

**Spec:** User-authorized Phase 3 request in this task.

## Global Constraints

- Do not modify invoice or purchase-order PDF rendering files, templates, CSS, fonts, logos, page layouts, pagination, or print formatting.
- Use Decimal values and JSON decimal strings; preserve all issued documents and historical snapshots.
- Keep routes under `/api/v1`; enforce permissions on the backend.
- Use forward migrations only; no database reset or inventory, payments, GST, or supplier-accounting work.

---

### Task 1: Revision-safe invoice workflow

**Files:** invoice model/schema/router, forward migration, invoice workflow tests.

- [ ] Add transaction version, submitted revision and immutable revision snapshots.
- [ ] Require a matching version for mutations; return a structured 409 conflict on stale writes.
- [ ] Add audited return-for-correction requiring a reason, and prohibit an invoice creator from approving their own submitted revision.
- [ ] Test return, revision mismatch, self-approval rejection and successful independent approval.

### Task 2: Purchase-order lifecycle

**Files:** PO model/schema/router, forward migration, PO workflow tests.

- [ ] Add explicit draft, pending approval, approved, amendment pending, cancelled and closed states plus version/history records.
- [ ] Implement submit, approve, amendment, cancellation and closure endpoints with reasons and independent approval.
- [ ] Test lifecycle legality, amendment history and stale-write conflicts.

### Task 3: Registers and dashboard APIs

**Files:** invoice/PO routers, new dashboard router/schema, API router, tests.

- [ ] Add paginated/searchable/filterable/sortable register endpoints and document detail/approval-queue queries.
- [ ] Add an authorized dashboard endpoint derived solely from real document/audit data, with no outstanding-payment metric.
- [ ] Test authorization, paging/filtering and empty result contracts.

### Task 4: Operational frontend reliability

**Files:** dashboard, invoice/PO pages, shared components/types/API client, supplier page, frontend contract tests.

- [ ] Replace dashboard fixtures with API data and usable empty/error states.
- [ ] Add real approval workspace, register controls and detail links.
- [ ] Surface server field errors and version conflicts; show saved/unsaved state and preserve recoverable server drafts without persisting sensitive form data locally.
- [ ] Add supplier management entry point and accessible keyboard/focus behavior.

### Task 5: Verification and status

**Files:** tests and `docs/PROJECT_STATUS.md`.

- [ ] Run targeted backend/frontend checks during implementation and full relevant suites at completion.
- [ ] Verify protected PDF paths have no diff, document migration instructions/results/limitations, and stop after Phase 3.
