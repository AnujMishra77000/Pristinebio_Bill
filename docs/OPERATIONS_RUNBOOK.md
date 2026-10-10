# Production operations runbook

This is a reviewable operating baseline, not a deployment or a restoration claim. The application is a single-company modular monolith. Validate capacity, recovery targets, secrets, proxy rules, and ownership with the client before production use.

## Release sequence

1. Build immutable images with `docker compose -f docker-compose.prod.yml build`.
2. Run the release migration once from the exact backend image:

   ```bash
   docker compose -f docker-compose.prod.yml run --rm backend /app/scripts/release_migrate.sh
   ```

   A non-zero migration exits the release and must be investigated before any new application replica starts. The compose service command never runs migrations, so replicas do not race each other.
3. Start the reviewed image with `docker compose -f docker-compose.prod.yml up -d` behind an HTTPS reverse proxy. Route the public API origin configured into the frontend to the backend service; PostgreSQL and Redis remain on the internal data network.
4. Check `/health`, `/ready`, proxy TLS/origin behavior, and a non-destructive authenticated smoke test.

## Configuration and secrets

Production requires strong independent `JWT_SECRET_KEY`, persistent `MFA_ENCRYPTION_KEY`, non-default PostgreSQL credentials, `COOKIE_SECURE=true`, and an HTTPS `FRONTEND_ORIGIN`. Keep `.env` outside source control. Rotate secrets only with the documented session/MFA recovery procedure. The `NEXT_PUBLIC_API_BASE_URL` value is compiled into the Next.js browser bundle at image build time; changing it at runtime requires rebuilding the frontend image. Backend secrets are runtime environment values.

The reverse proxy must terminate HTTPS, forward only the configured public origin, preserve `X-Request-ID` when valid or generate one, and not expose the private data network. Do not trust arbitrary client-supplied forwarded IP headers without an explicit proxy configuration.

## Health, alerts and logs

- `/health` is a liveness check and does not require PostgreSQL.
- `/ready` executes `SELECT 1` and is the readiness check for database connectivity.
- Consume JSON stdout events `request_completed`, `unhandled_exception`, and `error_tracking`. Request bodies, query strings, cookies, authorization headers, passwords, MFA values, and financial payloads are deliberately not logged.
- Alert on readiness failures, sustained HTTP 5xx responses, migration failure, database connection exhaustion, disk growth in PDF storage, and backup age/verification failure. Include the request ID in incident tickets.
- `ERROR_TRACKING_DSN` is reserved for the deployment’s collector; the application emits a redacted structured error event without claiming a third-party account or live integration.

## Dependency advisory review

The frontend is pinned to the official supported Next.js 15.5.24 maintenance patch. On 2026-09-16, `npm audit` reported one moderate Next.js finding and one high PostCSS finding because that supported Next.js line bundles PostCSS 8.4.31; npm offered a fix only through Next.js 16.3.5, which is a major upgrade. The project does not silently take that breaking upgrade. The CI gate fails critical findings and unexpected high findings, while surfacing this reviewed exception for an explicit future framework decision. The non-major `sharp` fix was applied to the lockfile.

## Backup and recovery

Use a scheduled, encrypted PostgreSQL logical or physical backup owned by the deployment operator. Example logical backup (run only against the intended production service):

```bash
pg_dump --format=custom --no-owner --file="billing-$(date -u +%Y%m%dT%H%M%SZ).dump" "$DATABASE_URL"
pg_restore --list billing-YYYYMMDDTHHMMSSZ.dump
```

Retain daily backups for 35 days and monthly backups for 12 months unless the client’s retention/legal policy requires more. Store backups separately from the database host and encrypt them. Restoration must be performed into a new isolated PostgreSQL instance, followed by `pg_restore`, `alembic upgrade head`, application smoke tests, invoice immutability checks, and an explicit business sign-off. No restore has been proven by this task.

Proposed recovery targets for client agreement: RPO 24 hours for daily backups and RTO 4 hours for a prepared replacement environment. These are targets, not achieved guarantees.

## Rollback and incident response

- If an application image fails, stop rollout and run the previous compatible image. Do not downgrade the database schema automatically; forward migrations are expected to be backward-compatible for the release handoff window.
- If a migration fails, keep the previous image serving when safe, preserve the migration error and database diagnostics, and escalate for a reviewed forward fix. Never reset, drop, or restore over the only database during an incident.
- For suspected data corruption, disable writes at the proxy, preserve logs/request IDs and the database snapshot, notify the owner, and restore only into an isolated instance for comparison. Issued invoice/PDF snapshots are historical records and must not be rewritten automatically.

## Capacity assumptions

The Compose limits are conservative starting values for one company and moderate daily billing. Validate with representative invoice sizes, concurrent users, PDF generation duration, database pool behavior, and storage growth. This setup makes no unlimited-scale claim; PDF generation is CPU/memory intensive and should be measured before increasing worker counts.
