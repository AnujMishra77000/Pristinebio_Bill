# Frontend Phase 2 report — 2026-09-16

Status: focused frontend implementation complete and verified. Backend implementation, migrations, backend/PDF tests and the shared PROJECT_STATUS update remain owned by the independent controller. Only the frontend paths listed below and this report were edited by this task. No commits, subagents, billing-entry edits, PDF/print-helper edits or future-phase work.

## Files

Updated:

- `frontend/app/lib/api.ts` — cookie/CSRF session transport, refresh coordination, related authentication errors and session events; existing Phase 1 idempotency generator, error formatting, file download and PDF/print helpers preserved.
- `frontend/app/lib/types.ts` — session/user security fields, sessions, invitations and audit types; existing financial types preserved.
- `frontend/app/components/AuthGate.tsx` — real initial `/auth/me` validation and retained operational children after first authentication.
- `frontend/app/components/AppShell.tsx` — server-backed logout, Security navigation and global reauthentication support.
- `frontend/app/login/page.tsx` — shared authentication flow.
- `frontend/app/users/page.tsx` — Admin invitations, access editing, session revocation, MFA reset and audit events.
- `frontend/scripts/verify_auth_error_messages.py` — login/bootstrap and CSRF acquisition network-error fixtures.
- `frontend/scripts/verify_manual_consignee_ui.py` — replace localStorage auth mock with `/auth/me`/CSRF contract and replace saved-selection/save-response timing races with observable completion assertions.
- `frontend/scripts/verify_seller_profile_ui.py` — replace localStorage auth mock, mock canonical seller-profile response, and align a stale empty-company expectation with the existing page copy. No seller-page implementation changes.

Added:

- `frontend/app/lib/auth.ts` — NFC passphrase validation and ordered authentication requirements.
- `frontend/app/components/AuthFlow.tsx` — login, conditional bootstrap, fragment invitation acceptance, password upgrade, MFA verification/recovery/enrollment.
- `frontend/app/components/SecurityForms.tsx` — password, authenticator and acknowledged one-time recovery-code forms.
- `frontend/app/components/Reauthentication.tsx` — native modal preserving mounted forms and in-progress security enrollment.
- `frontend/app/security/page.tsx` — password changes, authenticator setup/replacement, recovery-code replacement, individual/current session revocation and logout-all.
- `frontend/scripts/session_security.test.mjs` — 15 targeted executable tests against the real API/auth modules, with network and browser-platform boundaries substituted.
- `frontend/scripts/verify_session_security_ui.py` — browser auth, security, Admin actions, draft preservation and concurrent-tab regressions.
- This report.

## Implemented behavior

All requests include cookies. Unsafe requests receive an in-memory CSRF token, including initial sign-in/setup/invitation acceptance and refresh/logout. Session-changing login/password/MFA responses renew CSRF; enrollment and recovery-code replacement also invalidate/renew it. Both the short CSRF error and backend detail beginning `CSRF validation failed; retry after renewing the security token` renew/retry once, preserving request body and idempotency header. Refresh itself receives the same bounded CSRF recovery.

Session metadata is memory-only; the legacy `pristine-bio-billing.session` localStorage key is removed. There are no access/refresh tokens in types, authorization headers or persisted session storage. Refresh uses singleflight and Web Locks, checks `/auth/me` after acquiring the lock, and sends no refresh-token body. BroadcastChannel emits only `{type: "changed"}` / `{type: "logout"}` notifications; receiving tabs validate their own cookies. Local logout occurs after successful server revocation.

Existing short passwords remain accepted for sign-in. Credential SecurityFields deliberately have no `maxLength`, allowing raw Unicode input through the backend's 256-character limits. New passphrases are 15–128 NFC Unicode characters, preserving spaces without composition rules; tests include 191 decomposed raw codepoints normalizing to 128. Enabled MFA verification precedes legacy password upgrade; mandatory enrollment follows when needed. Recovery forces re-enrollment, including Staff. Enrollment recovery codes stay visible until the user acknowledges saving them. A security-page enrollment acknowledgment does not trigger an unrelated sign-in overlay. A bad MFA code/current password returning 401 while `/auth/me` is valid stays a related action error, without replay, refresh, or session-expiry overlay.

Bootstrap is offered only when setup-status says available; its operator-supplied token is an input sent through `X-Setup-Token`, never a frontend environment value. Invitation tokens are read from the fragment, removed from the URL on load, and submitted only to invitation acceptance. Admin-created links use `/login#invite=...` and explicitly require manual delivery. No public register or direct user/password creation remains.

Operational children stay mounted after first authentication during expired-session or restricted-session recovery. Initial navigation still validates cookies. Failed saves surface their original error; reauthentication neither navigates nor resets draft inputs/idempotency references. Explicit logout can unmount protected content. Staff draft/Manager approval implementation and sensitive seller/bank forms were not changed; authorization remains backend-enforced.

## TDD and verification

Tests were written before corresponding implementation/refinements. Red runs reproduced missing cookie credentials, failed concurrent refresh/save replay, CSRF detail-prefix rejection, refresh CSRF failure, incorrect optional/legacy MFA order, Staff recovery bypass, and replay/overlay on a bad secret. Browser regression also caught an acknowledgment overlay blocking security enrollment; its fix was reverified. Test fixture selector/stage races were corrected using observable UI completion, not sleeps.

Commands below were run from `frontend`; final results:

| Command | Result |
| --- | --- |
| `node --test scripts/session_security.test.mjs` | PASS — 15 tests, 0 failures |
| `npm run lint` | PASS — 0 warnings/errors |
| `npm run type-check` | PASS |
| `npm run build` | PASS — 17 static pages, including `/security` and `/users` |
| `../backend/.venv/bin/python scripts/verify_session_security_ui.py` | PASS — draft preservation, concurrent tabs, authentication restrictions, bad-code error, enrollment/recovery, invitation/bootstrap, security sessions/recovery codes, invitation/revoke/edit/MFA-reset/audit controls |
| `../backend/.venv/bin/python scripts/verify_auth_error_messages.py` | PASS — actionable login/setup errors, including initial CSRF failure |
| `../backend/.venv/bin/python scripts/verify_manual_consignee_ui.py` | PASS — existing regression with cookie-auth fixtures |
| `../backend/.venv/bin/python scripts/verify_seller_profile_ui.py` | PASS — existing regression with cookie-auth fixtures |
| `git diff --check -- frontend/app/components/AppShell.tsx frontend/app/components/AuthGate.tsx frontend/app/lib/api.ts frontend/app/lib/types.ts frontend/app/login/page.tsx frontend/app/users/page.tsx frontend/scripts` (repository root) | PASS |

The preservation check verifies a non-null buyer input remains the same DOM node, unchanged input value, original 401 save error, and identical payload/idempotency key on retry after in-place sign-in. Two browser tabs start with expired access state, acquire real Web Locks, rotate once, broadcast metadata only, and propagate one server logout to the other tab. Targeted tests additionally verify same-body/key CSRF retry, bounded second failure, failed server logout retaining metadata, and bad-secret 401s not being replayed.

For a bounded preservation-only rerun: `AUTH_REGRESSION_FOCUS=draft ../backend/.venv/bin/python scripts/verify_session_security_ui.py`.

## Limits and handoff

Browser checks use real Chromium and the production frontend at `http://127.0.0.1:3100`, with mocked backend response contracts. They verify frontend network behavior, real Web Locks/BroadcastChannel, UI flows and mounted draft preservation; they do not independently prove live backend cookie attributes, CSRF cryptography, invitation delivery, TOTP cryptography or PostgreSQL migrations/concurrency. Those belong to the controller's backend verification. No live backend writes, backend test suite or PDF rendering were performed here.

The sandbox initially denied the local listener/Chromium launch. Browser verification ran with tool escalation. A development watcher returned a stale route while new pages were being added; final verification used the completed production build. The task's local server is stopped after verification. Existing dirty Phase 1 and controller changes remain preserved and uncommitted. Shared project documentation was intentionally left to the controller under the explicit frontend-and-report-only ownership rule.
