# Phase 2 implementation plan

Scope: authentication, session security and sensitive-data permissions only. Preserve the dirty Phase 1 financial changes, historical documents, billing screens and all PDF implementation files. No deployment, Git changes or infrastructure mutations.

1. Backend: regression tests; forward migration 0009; 15–128 character NFC passphrases with a versioned common-password blocklist; legacy hashes remain usable only to complete a password upgrade. Persistent one-time first-admin setup and expiring, revocable invitations replace public registration/direct password provisioning.
2. Backend: host-only HttpOnly cookies, short access JWT bound to a revocable database session, hashed rotating refresh tokens with a bounded latest-predecessor concurrency grace. Exact origin and signed, session-bound double-submit CSRF protect unsafe requests. Persistent throttling and generic login errors; account-management audit and last-admin serialization. Encrypted PyOTP TOTP enrollment, one-use recovery codes, replay protection and authenticated administrative reset.
3. Frontend (focused worker): memory-only session metadata/CSRF; credentialed cookies; Web Locks refresh coordination and BroadcastChannel metadata; setup/invitation/password-upgrade/MFA login lifecycle, security management, invitation-based user management. Reauthentication overlay preserves mounted billing work. No billing redesign or PDF/print changes.
4. Backend: Admin-only seller/GST/bank configuration and audited before/after changes; production configuration validation and explicit Compose secret wiring.
5. Integration: targeted security and permission tests, frontend lint/type-check/build, forward migration SQL, auth/browser regressions where available, full suite at completion. Update security documentation, README and project status with commands, migration and exact limitations.

Interfaces: frontend brief `docs/superpowers/plans/2026-09-16-session-security-frontend.md`. Tasks 1/2/4 produce its API contract; task 3 only consumes it. Shared frontend API file preserves Phase 1 idempotency and download/preview helpers. Current workspace is explicitly user-selected and dirty; no worktree relocation or commits.

Progress: backend/frontend execution in progress. No later phases authorized.
