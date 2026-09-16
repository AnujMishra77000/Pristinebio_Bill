# Billing context

## Product

This project is a chemical/raw-material billing system for one company in single-company mode. Branch selection is no longer part of the user workflow. The app uses one Seller/GST profile for legal seller identity on invoices and purchase orders. It is a web PWA first, with Android support planned later.

The system must support a controlled invoice workflow:

- Staff creates invoice drafts.
- Manager or Admin approves invoices.
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
- Keep the Seller/GST profile explicit in saved invoice snapshots where it affects the legal or display output. Do not require branch selection in billing screens.
- Treat the approved invoice reference as a layout contract. Do not redesign, simplify, or omit fields without an explicit decision.
- Keep invoice approval state and audit-relevant transitions explicit and testable.
- Keep all API routes under `/api/v1`.

## Reference status

The approved reference is named `AOPL 00937 (1).pdf`. The supplied four-page PDF was visually inspected and its fields, table columns, copy labels, and pagination rules are recorded in `docs/REFERENCE_INVOICE_MAP.md`.

## Working conventions

Read this file and `docs/PROJECT_STATUS.md` before work. Work only on the requested phase, preserve existing working code, add targeted tests for changed behavior, run targeted tests during development, and run the full suite only at phase completion. Update `docs/PROJECT_STATUS.md` before stopping. Future phases must not be implemented without an explicit prompt.
