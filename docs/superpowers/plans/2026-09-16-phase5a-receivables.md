# Phase 5A Receivables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add auditable customer receipts, allocation/reversal, derived receivables reporting, and credit controls without changing invoice approval or PDF rendering.

**Architecture:** Add payment ledger tables separate from invoices. All writes lock the receipt and invoice rows inside one transaction, use persisted idempotency keys, and derive payment status/outstanding balances from non-reversed allocations. Add paginated API reports and a small authenticated receipts/reconciliation screen.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL `NUMERIC`, Decimal, Next.js/TypeScript.

**Spec:** User Phase 5A request in the current task.

## Global Constraints

- Preserve invoice/PDF generators and historical invoice values.
- No payment gateway, GST, inventory, or general-ledger implementation.
- No opening balances are assumed; balances begin from Phase 5A receipts and allocations.
- Currency is explicit and currently defaults to INR for existing invoices.

### Task 1: Payment data model and migration

Add receipts, allocations, reversal audits, credit limits/overrides, payment idempotency, invoice currency and indexes in forward migration `20260916_0012`.

### Task 2: Atomic payment APIs

Add receipt creation/listing, allocation, reversal, derived payment status, credit-limit administration and override endpoints with branch authorization, Decimal validation, locks and idempotency.

### Task 3: Receivables reports and frontend

Add paginated statements, ageing, receipt/reconciliation APIs and authorized CSV export. Add a focused authenticated receipts/reconciliation screen without modifying billing/PDF screens.

### Task 4: Tests and status

Test partial/multi-invoice/unallocated credit, currency/over-allocation rejection, reversal, idempotency and authorization. Run targeted tests and update project status.
