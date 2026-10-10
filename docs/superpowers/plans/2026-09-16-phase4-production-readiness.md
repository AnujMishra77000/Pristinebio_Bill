# Phase 4 Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prepare a reviewable, production-oriented packaging and operations baseline without deploying, touching a live database, or changing PDF generation.

**Architecture:** Keep the existing modular monolith. Preserve the development Compose workflow and add an isolated production Compose definition with immutable images, private data services, explicit secrets, and a one-shot release migration command. Add lightweight structured request observability, bounded register queries, operational indexes, CI gates, and recovery runbooks.

**Tech Stack:** Docker Compose, Next.js standalone build, FastAPI/SQLAlchemy/Alembic, PostgreSQL, Redis, GitHub Actions, shell runbooks.

**Spec:** User Phase 4 request in the current task.

## Global Constraints

- Preserve all invoice/PDF generators, templates, CSS, fonts, logos, page layouts, pagination, and print formatting.
- Do not deploy or connect to a live database.
- Keep routes under `/api/v1`, use Decimal for financial values, and use forward migrations only.
- Production replicas must not run migrations independently.
- Clearly distinguish SQLite test coverage from PostgreSQL guarantees.

### Task 1: Production images and Compose

Add production Dockerfiles and `docker-compose.prod.yml`; use `npm ci`, standalone Next output, non-root users, private Postgres/Redis, health checks, resource limits, and no source mounts or reloaders.

### Task 2: Release configuration and migration command

Add an explicit one-shot migration command with failure handling, production environment documentation, and exact frontend build-time API configuration guidance.

### Task 3: Runtime observability and readiness

Add `/ready`, correlation IDs, structured redacted request/error logs, and configuration for an optional error-tracking sink without logging sensitive payloads.

### Task 4: Query/index hardening

Add a forward index migration and bounded list/register responses while preserving response compatibility and financial data semantics.

### Task 5: CI and recovery runbooks

Add CI gates for backend/PostgreSQL/migrations, frontend, and dependency scanning. Document backup, retention, restore, rollback, incident response, alerts, capacity assumptions, and proposed RPO/RTO targets pending client agreement.

### Task 6: Verification and status

Run targeted checks, then the Phase 4 completion suite available locally; verify protected PDF paths are unchanged and update `docs/PROJECT_STATUS.md` with evidence and limitations.
