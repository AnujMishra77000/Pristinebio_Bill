# Phase 1B Authentication, Permissions, and Master Records Design

## Goal

Phase 1B adds the secure identity foundation, branch-scoped authorization, and billing master records needed before invoice workflows begin.

## Scope

This phase implements:

- JWT access and refresh authentication.
- Argon2 password hashing.
- Admin, Manager, and Staff roles.
- Branch-scoped authorization.
- Company and branch models.
- Customer, product, bank account, transporter, and terms-and-conditions masters.
- Alembic migrations for the Phase 1B schema.
- Functional protected APIs under `/api/v1`.
- Basic frontend management screens for authentication and master records.
- Permission and validation tests.

This phase does not implement invoice calculations, PDF generation, GST APIs, inventory movement, batch or lot tracking, Celery jobs, or Android-specific behavior.

## Current Foundation

The existing backend exposes `GET /health` and `GET /api/v1/status`, loads environment configuration through Pydantic Settings, wires SQLAlchemy to PostgreSQL, and has an Alembic baseline. The frontend is a Next.js App Router dashboard shell with static navigation. Phase 1B will extend those pieces without changing the Phase 1A routes or shell intent.

## Backend Architecture

Phase 1B will organize backend code into focused modules:

- `app/core/security.py`: password hashing, JWT creation, token decoding, and token metadata.
- `app/models/`: SQLAlchemy models for users, branch assignments, company, branch, and master records.
- `app/schemas/`: Pydantic request and response schemas.
- `app/api/dependencies.py`: authentication and authorization dependencies.
- `app/api/v1/`: routers for auth, users, companies, branches, customers, products, bank accounts, transporters, and terms.

The versioned router remains the only API surface for application endpoints. `GET /health` stays unversioned as a system check.

## Authentication

Users authenticate with email and password through `POST /api/v1/auth/login`. Passwords are stored using Argon2id hashes through `pwdlib`, and plain passwords are never persisted or returned.

Successful login returns:

- `access_token`: a short-lived JWT for API authorization.
- `refresh_token`: a longer-lived JWT for renewing access.
- `token_type`: `bearer`.
- `user`: the authenticated user profile with role and branch assignments.

`POST /api/v1/auth/refresh` accepts a refresh token and returns a new access token. Refresh tokens include a token type claim so access tokens cannot be used on the refresh endpoint. Tokens include subject, role, token type, issued-at time, and expiry.

`GET /api/v1/auth/me` returns the current user profile when the access token is valid.

Settings will add:

- `JWT_SECRET_KEY`
- `JWT_ALGORITHM`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `REFRESH_TOKEN_EXPIRE_DAYS`

The default development secret is only for local setup and is documented in `.env.example`.

## Users and Roles

The `users` table stores:

- `id`
- `email`
- `full_name`
- `role`: `admin`, `manager`, or `staff`
- `hashed_password`
- `is_active`
- timestamps

The `user_branch_assignments` table stores user-to-branch access. Admin users can operate across all branches even without explicit assignment. Manager and Staff users must have assignments for every branch they access.

Admin permissions:

- All branches.
- All configuration and master records.
- User creation and branch assignment.

Manager permissions:

- Assigned branches only.
- Can manage branch-scoped master records for assigned branches.
- Has invoice approval capability for assigned branches, represented as a permission helper only in this phase.

Staff permissions:

- Assigned branches only.
- Can view and manage draft-supporting master records for assigned branches.
- Has draft creation capability, represented as a permission helper only in this phase.
- Cannot access admin configuration outside assigned branch context.

No role can access records whose `branch_id` is outside the user's authorized branch set.

## Company and Branch Models

The project is for one operating company, but the database model will allow a company row so the data remains explicit and testable.

`companies` stores:

- `id`
- `legal_name`
- `trade_name`
- `pan`
- `registered_address`
- `is_active`
- timestamps

`branches` stores:

- `id`
- `company_id`
- `name`
- `gstin`
- `address_line1`
- `address_line2`
- `city`
- `state`
- `state_code`
- `postal_code`
- `phone`
- `email`
- `is_active`
- timestamps

Company configuration is Admin-managed. Branches are Admin-managed, while Manager and Staff users may list/read only assigned branches.

## Master Records

All billing master records in this phase carry `branch_id` for consistent permission enforcement.

`customers` stores:

- `id`
- `branch_id`
- `name`
- `gstin`
- `pan`
- `email`
- `phone`
- billing address fields: name, line 1, line 2, city, state, state code, postal code
- shipping or consignee address fields: name, line 1, line 2, city, state, state code, postal code
- `is_active`
- timestamps

`products` stores:

- `id`
- `branch_id`
- `name`
- `description`
- `hsn_sac`
- `unit`
- `base_rate`: `Numeric(14, 4)` mapped to `Decimal`
- `gst_rate`: `Numeric(5, 2)` mapped to `Decimal`
- `cess_rate`: `Numeric(5, 2)` mapped to `Decimal`
- `is_active`
- timestamps

`bank_accounts` stores:

- `id`
- `branch_id`
- `bank_name`
- `account_name`
- `account_number`
- `ifsc_code`
- `branch_name`
- `is_default`
- `is_active`
- timestamps

`transporters` stores:

- `id`
- `branch_id`
- `name`
- `gstin`
- `phone`
- `vehicle_number`
- `is_active`
- timestamps

`terms_and_conditions` stores:

- `id`
- `branch_id`
- `title`
- `body`
- `is_default`
- `is_active`
- timestamps

The API will validate required fields, GSTIN length when supplied, positive or zero decimal rates, and branch authorization before create, read, update, or delete-style deactivation.

## API Design

All application APIs live under `/api/v1`.

Authentication:

- `POST /auth/login`
- `POST /auth/refresh`
- `GET /auth/me`

Users:

- `POST /users` Admin only.
- `GET /users` Admin only.
- `GET /users/{user_id}` Admin or self.
- `PATCH /users/{user_id}` Admin only.

Company and branches:

- `POST /companies` Admin only.
- `GET /companies` authenticated; Admin sees all, non-admin sees companies attached to assigned branches.
- `PATCH /companies/{company_id}` Admin only.
- `POST /branches` Admin only.
- `GET /branches` authenticated; Admin sees all, non-admin sees assigned branches.
- `GET /branches/{branch_id}` authenticated and branch-authorized.
- `PATCH /branches/{branch_id}` Admin only.

Branch-scoped masters:

- `POST /customers`, `GET /customers`, `GET /customers/{id}`, `PATCH /customers/{id}`
- `POST /products`, `GET /products`, `GET /products/{id}`, `PATCH /products/{id}`
- `POST /bank-accounts`, `GET /bank-accounts`, `GET /bank-accounts/{id}`, `PATCH /bank-accounts/{id}`
- `POST /transporters`, `GET /transporters`, `GET /transporters/{id}`, `PATCH /transporters/{id}`
- `POST /terms-and-conditions`, `GET /terms-and-conditions`, `GET /terms-and-conditions/{id}`, `PATCH /terms-and-conditions/{id}`

Create payloads include `branch_id`. List endpoints accept an optional `branch_id` filter. If omitted, Admin receives all records and non-admin users receive records from assigned branches only.

Patch endpoints support partial updates. Records are not hard-deleted in this phase; they can be deactivated through `is_active=false`.

## Frontend Design

The frontend will keep the existing App Router structure and evolve the current dashboard into a simple protected management workspace.

Screens:

- `/login`: email/password form that stores returned tokens client-side.
- `/`: dashboard summary using the existing shell style.
- `/branches`: branch list and basic create/edit form.
- `/customers`: customer list and form with separate billing and consignee/shipping address groups.
- `/products`: product list and form with HSN/SAC, unit, base rate, GST rate, and cess rate.
- `/bank-accounts`: bank account list and form.
- `/transporters`: transporter list and form.
- `/terms`: terms-and-conditions list and form.
- `/settings`: current user/company context and role display.

The UI will be basic but functional: responsive tables, compact forms, loading and error states, and role-aware navigation where obvious. It will not implement a polished onboarding flow, permission editor beyond Admin user creation and branch assignment, or any invoice workflow.

## Testing Strategy

Backend tests are required for:

- Health and status endpoints remain working.
- Password hashing verifies correct passwords and rejects incorrect passwords.
- Login rejects invalid credentials and returns access/refresh tokens for valid credentials.
- Refresh rejects access tokens and accepts refresh tokens.
- Admin can create users and master records.
- Manager can access assigned-branch records and cannot access unassigned branches.
- Staff can access assigned-branch records and cannot access unassigned branches.
- Product validation enforces required fields and decimal constraints.
- Customer validation supports distinct billing and shipping address fields.

Tests will use isolated database setup and dependency overrides so permission behavior is tested against real FastAPI routes and SQLAlchemy models.

Frontend verification will run:

- `npm run type-check`
- `npm run build`

Backend verification will run targeted tests during development and the full backend suite at Phase 1B completion.

Docker Compose validation will run `docker compose config` if Docker is available. If Docker remains unavailable, the exact blocker will be recorded again and the YAML parser fallback will be run.

## Error Handling

Authentication failures return `401`. Authenticated users attempting to access unauthorized branches return `403`. Missing records return `404`. Validation errors return FastAPI/Pydantic `422` responses. Inactive users cannot authenticate or use protected endpoints.

## Status Update Requirement

Before stopping, `docs/PROJECT_STATUS.md` will be updated with Phase 1B completed work, commands run, command results, blockers, and the exact next phase. The next phase will not be started.

## Self-Review

- Scope matches the requested Phase 1B and excludes future invoice, PDF, GST, and inventory behavior.
- All API routes are under `/api/v1` except the existing unversioned `/health` system endpoint.
- Money, rates, and quantity-ready values use `Decimal` through PostgreSQL `Numeric` columns.
- Branch authorization is explicit for every branch-scoped model.
- The spec contains no placeholder implementation requirements.
