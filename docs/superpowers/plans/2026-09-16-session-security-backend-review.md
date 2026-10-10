# Phase 2 backend security review — 2026-09-16

## Verdict and evidence boundary

**Spec compliance: incomplete. Code quality: requires fixes before Phase 2 backend acceptance.** No Critical finding identified in the reviewed scope. Five Important findings remain: two authorization races, one PostgreSQL lock-order defect, inconsistent Unicode password bounds, and inaccurate concurrent sensitive-data audit snapshots. Minor items are separated below.

This is a source review, not an executed penetration test. Every reproduction below is a proposed deterministic schedule or request, **not run by this reviewer**. The controller reports **111 focused tests and four real PostgreSQL concurrency/migration tests passed**. Their passing results are acknowledged; no claim is made that those four tests lack concurrency coverage, or that they exercise the exact schedules below. No tests, subagents, commits, application-code edits, billing refactors, or PDF operations were performed. The only reviewer write is this report. PROJECT_STATUS.md was read and left unchanged under the explicit no-edits instruction.

Read AGENTS.md, docs/BILLING_CONTEXT.md, docs/PROJECT_STATUS.md, and the Phase 2 plan at docs/superpowers/plans/2026-09-16-session-security.md. Reviewed the requested auth/account/session/configuration/schema/model/migration and company/branch/bank routes and relevant test sources, with narrow reads of the referenced password helper and authentication test fixtures. Application mounting, Compose/deployment wiring, frontend behavior, blocklist data/version provenance, and PDF internals were not independently verified.

The checkout changed during review. The current login implementation locks the user **before** password verification at backend/app/api/v1/auth.py:117–119; the earlier login/password-change race is resolved and is **not** a finding. MFA confirmation flushes the newly assigned seed before verify_totp at auth.py:314–315; no missing-flush finding is raised. References below describe the last-read current contents.

## Important findings

### I1 — MFA administrative reset can proceed after its actor loses Admin permission

**Location:** backend/app/api/v1/users.py:86–98, especially 94–96; backend/app/api/dependencies.py:71–80; backend/app/api/v1/auth.py:278–280; backend/app/services/account_security.py:157–172.

Admin permission and session validity are checked in dependencies before the administrative lock is acquired. Once that lock is obtained, administrative_mfa_reset does not recheck the actor's role, active status, or originating session. verify_totp refreshes and locks the actor, but checks the authenticator only. Consequently a demoted actor can still reset another user's MFA using the request admitted before demotion.

**Reproduction schedule:** Have two active Admins A and B and a target T different from A. A submits POST /api/v1/users/{T}/mfa-reset with A's verified session, password, fresh TOTP, and reason. Pause after users.py:91–93 and before line 94. B demotes A with PATCH /api/v1/users/{A}, supplying valid assignments, and commits; that update revokes A's sessions. Resume A. The reset obtains the lock, verifies A's retained authenticator, and reaches reset_mfa without requiring A to remain an Admin. It can remove T's authenticator and revoke T's sessions after A's administrative authority was withdrawn.

There is a related stale-password check: mfa_reauth verifies the cached password **before** verify_totp refreshes the user. For administrative reset and recovery-code regeneration (auth.py:352–359), a concurrent password change between dependency loading and reauthentication can make the old password pass this check. The updated hash is loaded too late to affect the already-evaluated password result.

**Correction:** After acquiring the relevant serialization lock, refresh/lock the actor and validate current role, active status, and originating session before any sensitive change. Verify password and TOTP against that same current account state. Add barrier-controlled regressions for demotion and password change before reset/regeneration resumes.

### I2 — MFA verification can create a verified session from a source session already revoked

**Location:** backend/app/api/v1/auth.py:325–333, particularly 327–331; backend/app/api/dependencies.py:44–48. Related replacement paths: auth.py:183–202, 299–321, and 337–349.

The source session is validated once in get_current_user and cached on request.state. verify_mfa subsequently locks the user and verifies the code, but never reloads or validates the source session before issuing a replacement. Setting the old session's revoked_at again does not establish that it was still authorized to produce a new session.

**Reproduction schedule:** Start POST /api/v1/auth/mfa/verify with a valid password-authenticated challenge session S and fresh TOTP. Pause after dependency validation, before verify_totp. From a separate connection, POST /api/v1/auth/logout using S's refresh cookie and commit its revocation. Resume verification. It reaches new_session(..., mfa_verified=True), issuing a new usable verified session after logout completed. The same missing check allows a source session to expire during the gap without being rejected before replacement.

This requires an in-flight request and a valid second factor; it is not an unauthenticated MFA bypass. Its security impact is that committed revocation does not terminate a pending challenge's authority to establish a full session.

**Correction:** Reload and lock the originating session, enforce revocation/absolute/idle validity against current account state, and replace it atomically. Apply the invariant to all session-replacement paths with a consistent lock order. Add the logout-before-replacement and expiry-before-replacement schedules as regressions.

### I3 — Opposite user/session lock ordering can deadlock security operations on PostgreSQL

**Location:** backend/app/services/account_security.py:157–158 and 119–123; backend/app/api/v1/auth.py:186–199 and 147–150; backend/app/models/authentication.py:55. The refresh replay audit path at account_security.py:130–142 has the same ordering concern.

Password changes take FOR UPDATE on the User, then update its AuthSession rows. Logout takes FOR UPDATE on AuthSession first, then inserts a SecurityAudit row referencing that User. PostgreSQL's foreign-key check on the audit insert needs a key-share lock on the parent User, conflicting with the explicit FOR UPDATE held by password change.

**Reproduction schedule:** Request A starts a password change and holds the User lock; pause before revoke_user_sessions. Request B logs out an existing session S of that user, takes S's lock, and reaches audit insertion/commit, which waits for A's User lock. Resume A: its session-revocation update waits for B's S lock. The resulting cycle is A → S → B → User → A. PostgreSQL must abort a transaction with deadlock_detected (40P01). The scoped code does not retry this transaction, so one requested security operation cannot complete normally.

This is a statically derived database lock cycle, not an observed failing test. Passing refresh concurrency tests alone do not establish this different interaction's behavior.

**Correction:** Establish one lock order or a shared per-user serialization mechanism across password/MFA changes, logout, revocation, and replay audit. Include the audit foreign-key lock in the design. Validate the exact two-connection schedule on PostgreSQL.

### I4 — A valid NFC passphrase can be accepted for creation but rejected for login and reauthentication

**Location:** backend/app/schemas/user.py:26–27; backend/app/schemas/auth.py:10, 19–21, 43; backend/app/core/security.py:33–39; backend/app/api/v1/auth.py:51–54.

Creation and new-password inputs allow 256 raw characters before normalization and enforce 128 characters after NFC normalization. Login, current_password, and MFA reauthentication instead reject more than 128 raw characters before the version-aware password verifier can normalize them.

**Reproduction:** Use the uncommon string raw = ("e\u0301x" * 63) + "yz" as a new passphrase. It has 191 raw code points and normalizes to ("éx" * 63) + "yz", exactly 128 characters. Creation/password-setting validation accepts and stores the normalized value. Submitting the identical original input to login or as current_password returns 422 before verification. A user must change the Unicode representation manually to authenticate.

**Correction:** Use consistent bounded pre-normalization input across credential-entry schemas, then enforce the normalized limit for policy-version-1 passwords. Preserve original text for legacy-hash verification. Add a decomposed-Unicode round trip covering setting, login, password change, and MFA reauthentication. This is an authentication availability/spec defect, not a privilege escalation.

### I5 — Concurrent seller/GST/bank writes produce incorrect before/after audit snapshots

**Location:** backend/app/api/v1/bank_accounts.py:82–91; backend/app/api/v1/branches.py:85–97; backend/app/api/v1/companies.py:70–75, 141–143, and 216–223; backend/app/services/account_security.py:44–50.

The routes capture complete ORM snapshots without locking or refreshing the records for the write. Concurrent requests can capture the same original state; the later commit then records a before state that was already superseded. With disjoint PATCH fields, its after snapshot can also contain stale unchanged fields even though the database preserves the first request's update.

**Reproduction schedule:** Start two Admin PATCH requests for the same bank account and pause both after before=snapshot. A changes account_number from N0 to N1 and commits. B changes bank_name and commits. B's audit before still shows N0, and its after snapshot can still show N0, although the stored account contains N1. Changing account_number in both requests instead yields an incorrect transition history N0→N1 followed by N0→N2, rather than N1→N2.

**Correction:** Lock and refresh affected records before taking the before snapshot, mutate and flush, and record the actual resulting state in the same transaction. Lock both company and seller records consistently for profile upsert. Add targeted concurrent audit assertions; no billing calculations or PDF changes are needed. This is a sensitive-configuration audit integrity/spec defect.

## Minor items

1. **MFA reenrollment audit reports an incorrect previous state.** auth.py:320 hard-codes before={"mfa_enabled":False}, although authenticated replacement of an existing authenticator is permitted at 289–290. Capture the real previous state before changing it. A successful authenticated reenrollment should report True→True with an appropriate replacement action or metadata.
2. **Recoverable refresh ciphertext has no bounded retention in the reviewed implementation.** account_security.py:148 stores successor_encrypted and models/authentication.py:25–27 has no ciphertext expiry; rotation does not clear older ciphertext. Acceptance grace is correctly bounded, but decryptable successor material remains stored after that grace. Retain needed hashes for replay detection while clearing ciphertext once it can no longer serve the latest-predecessor grace. Exploitation additionally requires the encryption key; this is not a cookie-only attack.

## Requirement assessment

| Requirement | Source assessment |
| --- | --- |
| Permanent first setup | Implemented: persistent singleton closure, existing-user closure, and PostgreSQL advisory serialization; migration 0009 seeds closure without changing hashes. |
| Invitations/direct provisioning removal | Implemented: Admin-issued hashed tokens, 48-hour expiry, revocation, single-use acceptance, stored email/role/assignment authority, and 410 direct provisioning/registration paths. |
| Passphrase policy and legacy upgrade | NFC validation and legacy restricted sessions implemented; I4 prevents full input-contract compliance. Blocklist loading is present; data/version provenance was outside this bounded review. |
| Session revocation/rotation/replay/concurrency | Session-bound cookies and database validity checks, rotating hashed credentials, latest-predecessor grace, and replay revocation implemented; I2/I3 remain. Current login lock ordering addresses the earlier password race. |
| Exact Origin, CSRF, cookies | Exact allowlist checks and signed session-bound cookie/header CSRF comparison present for unsafe /api/v1 requests. Cookies are host-only, HttpOnly, SameSite=Lax, with Secure/__Host- names when enabled. Middleware mounting/browser integration was not independently reviewed. |
| Last active Admin | Advisory serialization plus locked target/other-Admin checks implemented. No last-Admin-removal defect identified. |
| Admin sensitive permissions and audit | Admin dependencies present on company/seller/GST/bank writes. I1 weakens current-authority enforcement for MFA reset; I5 breaks accurate configuration transition snapshots. |
| Complete TOTP lifecycle | Enrollment expiry, encrypted seed, confirmation flush, one-use/replay-controlled TOTP, recovery/replacement codes, forced reenrollment, authenticated other-user Admin reset, and session revocation present. I1/I2/I3 prevent acceptance as fully robust under concurrency. |
| Production fail closed | Settings reject development/default signing or encryption configuration, non-independent keys, unsafe cookies/HTTP origin, weak configured bootstrap token, and default database credentials. Missing encryption key also denies account setup/login. Compose and actual deployment wiring were outside scope. |
| PDF/billing preservation | Reviewer performed no billing or PDF edits, inspections, rendering, or test runs. No broader preservation claim about other concurrent work is made. |

The implementation contains the planned backend feature set and useful security lifecycle tests. Acceptance remains blocked by the Important authorization, transaction, input-contract, and audit defects above. Recommendations are for the controller's implementation work; this review implements none of them.
