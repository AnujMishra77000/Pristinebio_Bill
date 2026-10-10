# Phase 2 authentication and security policy

## Passphrases and existing accounts

New/registered/invited/changed passwords contain **6–10 Unicode characters after NFC normalization**, as explicitly requested by the client on 2026-09-16. Spaces, paste, password managers and arbitrary character combinations are allowed; there is no uppercase/digit requirement or scheduled password reset. Whole-value common/compromised and account-context passwords are rejected. Argon2 hashes remain in place.

This client-requested range supersedes the earlier 15–128 requirement; no NIST password-policy compliance is claimed for this range. A local versioned SecLists 10,000-password snapshot (fetched 2026-09-16 from [the upstream list](https://github.com/danielmiessler/SecLists/blob/master/Passwords/Common-Credentials/10k-most-common.txt), MIT license) plus obvious service/repetitive values provides offline blocking. This is not exhaustive breach screening. Review/update the snapshot during security maintenance; never send plaintext passphrases to third parties.

Existing passwords and hashes are preserved, including passwords longer than ten characters. Login and current-password reauthentication continue to accept existing credentials; only newly set passwords must satisfy the new range. No database migration or forced reset is needed for this change.

Migration `20260916_0009` sets existing accounts to password policy version 0 without rewriting their hashes. Their old password can establish only a 10-minute restricted session to upgrade the passphrase. Ordinary business APIs refuse restricted sessions. After upgrade the old password no longer works. Existing bearer/localStorage credentials are intentionally no longer accepted; users sign in again and complete transition. No accounts are auto-promoted.

## Provisioning and sensitive permissions

Admin registration is available at `/auth/register` and creates an active Admin account without a master password or first-account restriction. Multiple Admin registrations are currently allowed. Staff and Manager accounts are provisioned through fully authenticated Admin invitations with role and branch assignments; direct `/users` password creation remains disabled.

Fully authenticated Admins issue role/email/assignment-bound invitations. Tokens are stored hashed, expire after 48 hours, can be revoked and can be accepted only once. The UI reveals a delivery link once; an administrator must deliver it privately. There is no email provider or fake email success. Invitation URLs use fragments, not query parameters. Accepting a token cannot substitute a different email/role.

Seller identity, GST configuration, bank/default account configuration, roles and assignments require Admin authorization on the backend. Assigned Staff retain customer/product entry and invoice drafts; assigned Managers/Admins retain approval. Role, assignment, identity or activation edits revoke affected user sessions. Last-active-Admin demotion/disable is blocked under a PostgreSQL advisory transaction lock. No automatic historical billing changes occur.

Append-only application audit records capture actor, UTC timestamp, action/entity and before/after for sensitive edits. Credential material (passwords, hashes, tokens, authenticator seeds/recovery codes) is never included. Logo changes are represented by checksums. Only Admins can read the bounded audit endpoint. Database operators must separately enforce audit retention and least-privileged database access; the application does not protect against a database superuser.

## Sessions, cookies and browser safety

The single design is direct FastAPI host-only HttpOnly cookies. Production uses `__Host-billing_access`, `__Host-billing_refresh` and `__Host-billing_csrf`: Secure, Path=/, no Domain, SameSite=Lax. Development HTTP uses unprefixed cookies with Secure=false. Use one hostname consistently for backend/frontend (localhost for both, or 127.0.0.1 for both); ports may differ. Production requires same-site HTTPS origins; cross-site deployment is not supported by this cookie policy.

Access JWTs expire after 15 minutes and contain a database session ID. Every protected request checks the live session and active account; revoked/expired sessions fail even with an otherwise valid JWT. Fully established sessions have 8-hour idle and 14-day absolute expiry by default, and never extend the absolute limit. Restricted password sessions expire after 10 minutes. Activity persists at most once per minute. Configuration bounds are enforced.

Refresh credentials are random, hashed in PostgreSQL, rotated under a session row lock. The immediately preceding credential can return the **same successor** for 10 seconds to handle concurrent tabs/lost responses; that encrypted successor is only used inside the grace window. Earlier-generation reuse or reuse after grace revokes the entire session and is audited. No grace applies to revoked/expired accounts/sessions. This narrow overlap is a documented trade-off: replay within that latest-predecessor window cannot be distinguished from concurrency. Signing/encryption keys must be independent and persistent.

Logout revokes the current session and clears cookies. Logout-all/password change revokes every previous session; password change issues only a new current session with the appropriate security restrictions. Account disable and role/assignment changes revoke sessions immediately. Password completion replaces the session ID. Browser memory contains user metadata and CSRF only; no auth token is stored in localStorage/sessionStorage or returned in JSON. Legacy localStorage credentials are removed.

Credentialed fetch, same-tab singleflight refresh and cross-tab Web Locks coordinate renewal. BroadcastChannel messages contain no credentials. Reauthentication overlays keep an already-authenticated billing page mounted; failed authentication does not clear entered fields or a pending save's idempotency key. Reload/closing the browser is not an offline draft persistence feature.

Every unsafe `/api/v1` request—including login, setup, refresh and invitation acceptance—requires an exact allowed Origin and an `X-CSRF-Token` matching an HttpOnly signed cookie bound to the current access-session identity. `/auth/csrf` returns a one-hour CSRF value; renew it after session replacement and once on CSRF expiry. SameSite alone is not treated as CSRF protection. CORS permits credentials only for exact configured origins (development also permits localhost/127 aliases). See [OWASP sessions](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) and [CSRF guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

## Throttling and authentication errors

PostgreSQL-backed 15-minute buckets cap authentication attempts at 8 per normalized subject and 40 per client IP per action category. Setup, invitation acceptance and password changes are also throttled. Unknown/bad-password/disabled accounts produce the same 401 message; unknown accounts incur dummy Argon2 verification. Throttle returns 429/Retry-After. Validation responses omit submitted secret values. The application does not trust arbitrary forwarded IP headers; configure trusted proxy sources when hosting, not `*`.

Authenticator MFA and recovery-code setup are disabled by explicit client decision. Admin registration requires only the normal passphrase. Legacy MFA columns and endpoints remain only for backward-compatible data/schema handling; they are not part of active login, registration, authorization or the frontend security screens. `MFA_ENCRYPTION_KEY` is not required for local or production startup.

There is no authenticator or recovery-code enrollment requirement, no MFA challenge during sign-in, and no MFA reset workflow in the frontend. Password, session revocation, invitation and Admin master-password controls remain active.

## Production startup

`APP_ENVIRONMENT=production` refuses missing/weak/development signing secrets, insecure cookies, non-HTTPS origin, unsupported signing algorithms and default database credentials. Pydantic errors hide input values. Compose explicitly requires signing keys; it is a local-development definition (reload/dev commands), not a production deployment recipe. No production infrastructure was changed.

Generate a private signing value locally with `secrets.token_urlsafe(48)` and store it in backend/.env or your secret manager, not frontend environment/repository. Never commit `.env` or output keys into logs. The signing key must persist across restarts. Local setup and login no longer depend on an MFA encryption key.
