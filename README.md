# Pristine Bio Billing

Phase 1 is a web billing foundation for a chemical/raw-material company with multiple branches and GSTINs. It includes authentication, role and branch permissions, master records, invoice draft/approval workflow, Decimal-based calculations, and A4 invoice PDF generation.

## Local Startup With Docker Compose

```bash
cp .env.example .env
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
# Edit .env: use localhost in DATABASE_URL and set ADMIN_REGISTRATION_MASTER_PASSWORD.
DATABASE_URL=postgresql+psycopg://billing:billing@localhost:5432/billing ./.venv/bin/python -m alembic upgrade head
DATABASE_URL=postgresql+psycopg://billing:billing@localhost:5432/billing ./.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Initial Admin Registration

Open `http://localhost:3000/login`, choose Register, and enter the master password from `backend/.env`.

User passwords are exactly 6 characters and must include uppercase, lowercase, and a number.

The master password is intentionally not stored in the repository. Read it from
your private `backend/.env` file when registering the first Admin account.

After signing in as Admin, create Staff or Manager users from the Users screen.

## Local Frontend Startup

```bash
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1` when running outside Docker Compose.

## Test And Verification Commands

These commands were last checked during Phase 1E verification on 2026-08-28.

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

## Phase 1 Boundaries

Phase 1 does not include live GST IRN/e-way bill integration, inventory or batch/lot movement, commercial documents beyond invoices, payments, offline support, or Android-specific work.
