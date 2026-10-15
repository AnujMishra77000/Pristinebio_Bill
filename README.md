# Pristine Bio Billing

Single-company chemical/raw-material billing with master records, invoice draft/approval workflow, Decimal calculations and A4 PDFs. Phase 2 adds revocable cookie sessions and audited sensitive permissions. Authenticator MFA is disabled by the current client decision. PDF implementation is unchanged.

## Local Startup With Docker Compose

```bash
cp .env.example .env
# Generate and privately configure JWT_SECRET_KEY first (see below).
docker compose up --build
```

Services:

- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:8000/health`
- Versioned API: `http://localhost:8000/api/v1`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

Validate Compose configuration:

```bash
docker compose config
```

## Local Backend Startup

Use PostgreSQL locally or start only the database services with Docker Compose.

```bash
cd backend
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m playwright install chromium
cp ../.env.example .env
# Edit private backend/.env: use localhost in DATABASE_URL; configure the independent keys below.
DATABASE_URL=postgresql+psycopg://billing:billing@localhost:5432/billing ./.venv/bin/python -m alembic upgrade head
DATABASE_URL=postgresql+psycopg://billing:billing@localhost:5432/billing ./.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Security Configuration And Admin Registration

In `/Users/anujmishra/Developer/Pristine_Bio_billing/backend`, generate the signing secret locally, then copy it into **private backend/.env**. Do not post, commit or log the output:

```bash
./.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))'
# Use the output for JWT_SECRET_KEY. Keep it private and persistent.
```

For local HTTP set `COOKIE_SECURE=false`, `FRONTEND_ORIGIN=http://localhost:3000`, and frontend `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1`. Use localhost consistently on both sides. Redis/Docker need not run for these synchronous local workflows. Production requires `APP_ENVIRONMENT=production`, HTTPS, secure cookies and strong independent signing/encryption/database credentials. Compose is development-only and now explicitly requires signing/encryption configuration; no deployment was performed.

Apply forward migration `20260916_0009` with `./.venv/bin/python -m alembic upgrade head`; **do not reset the database**. It preserves all hashes/documents and requires existing policy-version-0 users to upgrade their password at next login. Old bearer tokens are no longer valid. Newly set passwords are 6–10 NFC Unicode characters with common-password blocking, no composition rule or periodic reset. Existing passwords, including longer ones, remain usable for login and reauthentication.

Open `http://localhost:3000/register` to create an active Admin account. Multiple Admin registrations are currently allowed; there is no first-admin setup gate or admin master password. Staff and Manager accounts continue to be provisioned through expiring invitations from `/users`, delivered privately by an Admin. `/security` manages passphrases and sessions. Authenticator MFA and recovery-code setup are disabled by client decision.

## Local Frontend Startup

```bash
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1` when running outside Docker Compose.

## Production Packaging Review

The development `docker-compose.yml` remains the local source-mounted workflow. The production review setup is `docker-compose.prod.yml`: it uses immutable multi-stage images, `npm ci`, a standalone Next.js server, non-root users, no source bind mounts or reloaders, private PostgreSQL/Redis networking, named PDF/database volumes, and explicit health/resource limits. It is not deployed by this repository.

Production frontend API configuration is build-time because `NEXT_PUBLIC_API_BASE_URL` is embedded in the browser bundle. Build with the public HTTPS API URL and rebuild when it changes:

```bash
cp .env.example .env.production
# Edit .env.production with strong independent secrets, HTTPS origins and private URLs.
docker compose --env-file .env.production -f docker-compose.prod.yml build
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm backend /app/scripts/release_migrate.sh
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

Run migrations exactly once per release before starting replicas. The backend image does not run Alembic on application startup. PostgreSQL and Redis have no host ports in the production Compose definition; an HTTPS reverse proxy must expose the configured public frontend/API origin.

## Test And Verification Commands

### Edit a confirmed bill

Apply the forward correction migration once before serving the updated backend:

```bash
cd backend
./.venv/bin/python -m alembic upgrade head
```

Restart the backend and refresh/rebuild the frontend. In **Your bill registers**, open Sales, Purchase, Reagent or Reagent Purchase, then choose **Edit** beside a confirmed bill. The matching form loads its saved transaction values, including the existing number, parties, addresses and items; loading errors block saving rather than opening a blank creation form. Enter a correction reason, save/preview the correction, and **Confirm**. Staff submits to the existing Manager/Admin approval workflow; reviewers open **Approval workspace → Bill corrections → Review correction**, preview the exact revision, then confirm or return it with a reason. Admin can confirm their own corrections.

The bill keeps its ID and number. The original confirmed values/PDF remain available until approval; the previous snapshot and PDF metadata are archived, and the corrected final PDF is generated through the same layout engine. Closed/cancelled records and bills with payment allocation or external-integration/GST references are not directly editable. On concurrent changes, reload explicitly; Manager/Admin can restart a stale correction against the current bill with a reason, preserving abandoned edits in the audit. Do not reset the database or apply migrations independently from every application replica.

Focused correction verification:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_confirmed_bill_corrections.py tests/test_bill_correction_migration.py tests/test_postgresql_bill_corrections.py -q
cd ../frontend
node --test scripts/bill_corrections.test.mjs scripts/bill_editing.test.mjs
FRONTEND_BASE_URL=http://127.0.0.1:3000 ../backend/.venv/bin/python scripts/verify_bill_corrections_ui.py
cd ../backend
FRONTEND_INTEGRATION_URL=http://127.0.0.1:3000 ./.venv/bin/python -m pytest tests/test_confirmed_correction_browser.py -q
```

Start the local frontend on port 3000 before browser checks. The frontend script uses intercepted API fixtures. The optional `FRONTEND_INTEGRATION_URL` test forwards browser API requests to the real FastAPI application with isolated in-memory test data, verifying register→Edit prefill, Staff submission and independent Manager confirmation for all four types. Both use fixture PDF bytes for browser controls, not client billing records or a new layout validation. The optional PostgreSQL race tests require the disposable `billing_security_test` database described below; SQLite tests alone do not establish PostgreSQL concurrency guarantees. No live migration or deployment is performed by these instructions.

### Other verification commands

Phase-relevant checks (run from repository root unless `cd` is shown):

Backend full suite:

```bash
cd backend
./.venv/bin/python -m pytest -q
```

Backend migration SQL check:

```bash
cd backend
./.venv/bin/python -m alembic upgrade head --sql
```

PDF fixture generation:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_invoice_pdf.py -q --basetemp=/private/tmp/phase-1-pdf-fixtures
```

PDF-to-PNG validation:

```bash
find /private/tmp/phase-1-pdf-fixtures -name '*.pdf' -type f -print0 | while IFS= read -r -d '' pdf_path; do
  pdftoppm -png -r 144 "$pdf_path" "${pdf_path%.pdf}"
done
```

Frontend checks:

```bash
cd frontend
npm run lint
npm run type-check
npm run build
```

Docker configuration:

```bash
docker compose config
```

Production Compose syntax check:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml config
```

Phase 4 release migration and dependency checks:

```bash
cd backend
./.venv/bin/python -m alembic upgrade head --sql
./.venv/bin/python -m pytest -q
./.venv/bin/pip install pip-audit
./.venv/bin/pip-audit -r requirements.lock
cd ../frontend
npm ci
npm run lint
npm run type-check
npm run build
npm audit --audit-level=high
```

Operational recovery procedures, backup retention, restore validation, rollback handling, alerts, proposed RPO/RTO targets and capacity assumptions are documented in [OPERATIONS_RUNBOOK.md](docs/OPERATIONS_RUNBOOK.md). RPO/RTO values require client agreement; no production deployment or restore is claimed.

Focused security regressions:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_session_security.py tests/test_account_provisioning_mfa.py tests/test_auth.py tests/test_users.py tests/test_permissions.py -q
```

Real security concurrency tests require a **disposable** PostgreSQL database named `billing_security_test`, never your billing database. Supply its private URL in `TEST_SECURITY_DATABASE_URL`, then run:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_postgresql_security.py -q
```

Without that variable, only those three integration tests skip. They use isolated, recoverably scoped temporary schemas. No production or client database is reset.

## Phase 1 Boundaries

Phase 1 does not include live GST IRN/e-way bill integration, inventory or batch/lot movement, commercial documents beyond invoices, payments, offline support, or Android-specific work.
