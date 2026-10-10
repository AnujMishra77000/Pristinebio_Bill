# Phase 5B Integration Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable, provider-agnostic boundary for future accounting/GST synchronization without fabricating external success.

**Architecture:** Store outbound jobs, audit events, and reconciliation records in PostgreSQL. Expose authorized `/api/v1/integrations` endpoints for creation, listing, retry, cancellation, and readiness; the unconfigured adapter records `unavailable` and never makes a network request. Add a small operational page that surfaces these states.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL, Next.js, React, TypeScript, Tailwind.

**Spec:** `docs/superpowers/specs/2026-09-16-phase5b-integration-readiness-design.md`

## Global Constraints

- Preserve invoice and purchase-order PDF rendering, templates, CSS, fonts, logos, layouts, pagination, and interfaces.
- Use Decimal for financial values and strings across JSON boundaries.
- Keep API routes under `/api/v1` and enforce authorization on the backend.
- Use forward migrations only; never reset or rewrite historical documents.
- Do not implement live integrations without client provider requirements and sandbox access.

### Task 1: Persist integration boundary

**Files:**
- Create: `backend/app/models/integration.py`
- Create: `backend/alembic/versions/20260916_0013_integration_readiness.py`
- Modify: `backend/app/models/__init__.py`

**Interfaces:** `OutboundIntegrationJob`, `IntegrationAuditLog`, and `IntegrationReconciliation` persist scoped jobs, external outcomes, and recoverable differences. The unique scoped idempotency key is enforced in PostgreSQL.

- [ ] Add models and indexes with statuses `unavailable`, `queued`, `in_flight`, `accepted`, `rejected`, `uncertain`, `failed`, `reconciled`, and `cancelled`.
- [ ] Add the forward migration from `20260916_0012`.

### Task 2: Service and API

**Files:**
- Create: `backend/app/schemas/integration.py`
- Create: `backend/app/services/integration.py`
- Create: `backend/app/api/v1/integrations.py`
- Modify: `backend/app/api/v1/router.py`

**Interfaces:** `POST /api/v1/integrations/jobs` requires `Idempotency-Key`; `GET /jobs`, `POST /jobs/{id}/retry`, `POST /jobs/{id}/cancel`, `GET /reconciliation`, `GET /providers`, and `GET /numbering-review` are authorized operational endpoints.

- [ ] Require an approved invoice and branch access; persist canonical payload hash and an immutable request snapshot.
- [ ] Replay an identical scoped key; return conflict for a different payload.
- [ ] Record unavailable provider state, bounded retries, audit events, and reconciliation rows without outbound requests.
- [ ] Never accept a user-entered external identifier as authoritative.

### Task 3: Tests and frontend visibility

**Files:**
- Create: `backend/tests/test_phase5b_integration_readiness.py`
- Create: `frontend/app/integrations/page.tsx`
- Modify: `frontend/app/components/AppShell.tsx`

- [ ] Test idempotency, authorization, approval gating, retry bounds, unchanged local status, and reconciliation visibility.
- [ ] Add an Admin/Manager-only operational page with truthful unavailable/error/empty states and retry/cancel controls.

### Task 4: Documentation and verification

**Files:**
- Create: `docs/INTEGRATION_READINESS.md`
- Modify: `docs/BILLING_CONTEXT.md`
- Modify: `docs/PROJECT_STATUS.md`

- [ ] Document missing client inputs, status semantics, numbering proposal, migration gate, and GST non-assumptions.
- [ ] Run targeted backend tests, migration SQL, frontend lint/type-check/build, and protected PDF diff checks.
