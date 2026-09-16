# Phase 1A Application Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the runnable Next.js, FastAPI, PostgreSQL, and Redis application foundation with a tested backend health surface and a responsive demonstration dashboard.

**Architecture:** The frontend is a standalone Next.js App Router application that renders a static Phase 1A shell and dashboard. The backend is a standalone FastAPI application with environment settings, a SQLAlchemy PostgreSQL connection factory, Alembic baseline configuration, an unversioned `/health` probe, and a versioned `/api/v1/status` router. Docker Compose wires the four services without adding domain behavior.

**Tech Stack:** Next.js, React, TypeScript, Tailwind CSS, FastAPI, Pydantic Settings, SQLAlchemy, Alembic, PostgreSQL, Redis, Docker Compose, Pytest, and HTTPX-backed FastAPI TestClient.

**Spec:** User-approved Phase 1A design in the current task, constrained by `AGENTS.md`, `docs/BILLING_CONTEXT.md`, and `docs/PROJECT_STATUS.md`.

## Global Constraints

- Implement only Phase 1A application foundation.
- Do not implement authentication, invoice calculations, PDF generation, GST APIs, or inventory workflows.
- Keep API routes under `/api/v1`.
- Use environment-based configuration and provide `.env.example` without secrets.
- Use PostgreSQL as the configured SQLAlchemy database and Redis as reserved infrastructure only.
- Add backend health tests and run backend tests.
- Run frontend type-check and production build.
- Validate `docker compose config`.
- Update `docs/PROJECT_STATUS.md` with completed work, exact commands run, and the exact next phase.
- Stop after Phase 1A; do not begin Phase 1B.

## File map

- `docker-compose.yml`: four-service local orchestration and health checks.
- `.env.example`: documented local configuration variables and safe development defaults.
- `.gitignore`: ignores generated frontend, Python, and local environment artifacts.
- `frontend/`: Next.js App Router, Tailwind styling, responsive shell, and demonstration dashboard.
- `backend/app/core/config.py`: typed environment settings.
- `backend/app/db/session.py`: SQLAlchemy engine, declarative base, and session dependency.
- `backend/app/api/v1/router.py`: versioned API router.
- `backend/app/main.py`: FastAPI application, CORS, `/health`, and router registration.
- `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`: migration baseline wiring.
- `backend/tests/test_health.py`: health and versioned-router behavior tests.
- `docs/PROJECT_STATUS.md`: phase completion record and next-phase boundary.

---

### Task 1: Root environment and container foundation

**Files:**
- Create: `.env.example`
- Create: `.gitignore`
- Create: `docker-compose.yml`
- Create: `frontend/Dockerfile`
- Create: `frontend/.dockerignore`
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`

**Interfaces:**
- Consumes: no application code; only documented service names and ports.
- Produces: Compose services named `frontend`, `backend`, `postgres`, and `redis`, with backend environment variables `DATABASE_URL`, `REDIS_URL`, `FRONTEND_ORIGIN`, and `API_V1_PREFIX`.

- [ ] **Step 1: Add safe environment examples and ignore rules**

Create `.env.example` with `APP_ENVIRONMENT`, `BACKEND_PORT`, `FRONTEND_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DATABASE_URL`, `REDIS_URL`, `FRONTEND_ORIGIN`, `NEXT_PUBLIC_API_BASE_URL`, and `API_V1_PREFIX`. Create `.gitignore` entries for `.env`, `node_modules`, `.next`, Python caches, virtual environments, coverage output, and generated build output.

- [ ] **Step 2: Add Compose services and health checks**

Use PostgreSQL 16 Alpine with a named volume and `pg_isready`, Redis 7 Alpine with `redis-cli ping`, and Node/Python build contexts for the application services. Make the backend wait for healthy PostgreSQL and make the frontend wait for the backend. Set Compose defaults so `docker compose config` succeeds even when `.env` is absent.

- [ ] **Step 3: Add development Dockerfiles**

Use Node 20 Alpine for the frontend and Python 3.12 slim for the backend. Install declared dependencies in each image, expose ports 3000 and 8000, and run Next.js dev / Uvicorn reload commands.

- [x] **Step 4: Validate Compose syntax**

Run `docker compose config` and fix only Phase 1A configuration errors. The exact command is blocked in this workspace because Docker is not installed; YAML parsing passed independently and confirmed all four services.

### Task 2: Backend health and API foundation with TDD

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/pytest.ini`
- Create: `backend/app/__init__.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/db/__init__.py`
- Create: `backend/app/db/session.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/v1/__init__.py`
- Create: `backend/app/api/v1/router.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/test_health.py`

**Interfaces:**
- Consumes: Compose environment variables from Task 1.
- Produces: `GET /health -> {"status": "ok"}` and `GET /api/v1/status -> {"status": "ok", "api_version": "v1"}`; `get_settings()`, `engine`, `SessionLocal`, `Base`, and `get_db()` for later phases.

- [ ] **Step 1: Declare backend dependencies and test discovery**

Add FastAPI, Uvicorn, Pydantic Settings, SQLAlchemy, psycopg, Alembic, Pytest, and HTTPX dependencies. Configure Pytest to run from `backend` with `pythonpath = .`.

- [ ] **Step 2: Write the failing health tests first**

Add tests that import the FastAPI app and assert the exact status code and JSON response for `/health`, plus the versioned `/api/v1/status` response. Run `python -m pytest backend/tests/test_health.py -q` before creating the application modules; the expected failure is an import error because `app.main` does not yet exist.

- [ ] **Step 3: Implement typed configuration and database session wiring**

Use `pydantic_settings.BaseSettings` with `.env` support and defaults suitable for local Docker and local Python runs. Create a PostgreSQL SQLAlchemy engine using the configured `DATABASE_URL`, a `sessionmaker`, a declarative `Base`, and a request-scoped `get_db()` generator. Do not open a database connection during app import.

- [ ] **Step 4: Implement the FastAPI app and routers**

Create the app with title/environment settings, CORS restricted to the configured frontend origin, a plain `/health` endpoint, and an `APIRouter` included at `settings.api_v1_prefix` with a `/status` endpoint. Keep the route implementations free of domain logic.

- [ ] **Step 5: Run the targeted backend tests**

Run `python -m pytest backend/tests/test_health.py -q` and require both tests to pass.

### Task 3: Alembic baseline

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/.gitkeep`

**Interfaces:**
- Consumes: `backend.app.core.config.get_settings()` and `backend.app.db.session.Base` from Task 2.
- Produces: a migration environment that reads the configured PostgreSQL URL and is ready for later domain migrations without adding Phase 1B models.

- [ ] **Step 1: Add Alembic configuration**

Configure `script_location = alembic`, `prepend_sys_path = .`, and a harmless placeholder URL overridden by `env.py`.

- [ ] **Step 2: Wire offline and online migration contexts**

Import the settings and metadata, set the runtime database URL, and implement both offline and online migration functions using SQLAlchemy’s configured metadata.

- [ ] **Step 3: Confirm the migration environment imports**

Run `cd backend && python -m alembic current` without creating a revision or schema models.

### Task 4: Frontend shell and demonstration dashboard

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/next-env.d.ts`
- Create: `frontend/next.config.ts`
- Create: `frontend/postcss.config.mjs`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/app/layout.tsx`
- Create: `frontend/app/page.tsx`
- Create: `frontend/app/globals.css`

**Interfaces:**
- Consumes: `NEXT_PUBLIC_API_BASE_URL` only as documented environment context; the dashboard remains static in Phase 1A.
- Produces: a responsive `/` page with navigation labels Dashboard, Invoices, Customers, Products, Branches, and Settings, plus realistic demonstration summary cards.

- [ ] **Step 1: Add the Next.js and Tailwind project manifests**

Use compatible Next.js, React, TypeScript, Tailwind, PostCSS, and type package versions. Add `dev`, `type-check`, and `build` scripts.

- [ ] **Step 2: Add the root layout and global visual system**

Set application metadata, load the global CSS, and define a restrained billing dashboard palette, typography, spacing, focus states, and responsive breakpoints.

- [ ] **Step 3: Add the responsive application shell**

Render a desktop sidebar and a mobile-friendly top navigation treatment using CSS breakpoints. Show the six required navigation labels, with Dashboard marked active. Keep all non-dashboard items presentation-only links; do not create future workflow pages.

- [ ] **Step 4: Add realistic static dashboard cards**

Show summary cards for draft invoices, invoices awaiting approval, approved monthly value, and active customers, with supporting trend/context text and a recent-activity panel. Use display-only values; do not add invoice calculations or API calls.

- [ ] **Step 5: Run frontend type-check and production build**

Run `cd frontend && npm install`, then `npm run type-check` and `npm run build`.

### Task 5: Phase handoff documentation and final verification

**Files:**
- Modify: `docs/PROJECT_STATUS.md`

**Interfaces:**
- Consumes: actual command output from Tasks 1-4.
- Produces: a status record stating Phase 1A completion, the exact commands run, and the exact Phase 1B boundary.

- [ ] **Step 1: Record completed Phase 1A work**

Replace the Phase 0 blocked status with the completed foundation scope, while preserving the PDF-reference blocker as outside this phase if still applicable.

- [ ] **Step 2: Record exact verification commands**

List the actual backend test, Alembic import check, frontend type-check, frontend build, and `docker compose config` commands run, including their observed result.

- [ ] **Step 3: Name the exact next phase**

Set the next phase to `Phase 1B - billing domain foundation`: company/branch/GSTIN, customer/product domain models, and the draft/approval lifecycle. Explicitly state that Phase 1B is not started in this task and that PDF generation, GST APIs, authentication, calculations, and inventory remain out of scope here.

- [x] **Step 4: Run the final required checks**

Run the backend tests, frontend type-check, frontend production build, and `docker compose config` again after documentation changes. Report only verified results. Backend tests, frontend type-check, and frontend build passed; `docker compose config` remained blocked because Docker is not installed.
