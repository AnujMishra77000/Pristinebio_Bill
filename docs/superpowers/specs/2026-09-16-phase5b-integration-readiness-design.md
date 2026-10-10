# Phase 5B Integration Readiness Design

## Scope

The repository currently has no client-selected accounting provider, provider documentation, credentials, sandbox, approved accounting mappings, or confirmed GST-applicability requirements. Phase 5B therefore adds provider-agnostic integration readiness only. It must never claim an external submission, GST registration, or accounting success without a validated provider response.

## Design

Approved invoices can create durable outbound integration jobs scoped to the invoice branch. Each job stores a canonical request snapshot and payload hash, a caller-supplied idempotency key, bounded retry metadata, provider/external status, authoritative reference and timestamps when available, and failure or uncertain-outcome details. A database uniqueness constraint makes retries safe under concurrency. No secret is stored in these records.

Local invoice status remains the accounting application's approval state. External job status is separate and starts as `unavailable` while no provider is configured. User-entered IRN/e-way or other identifiers are informational only and cannot transition an external job to accepted.

Authorized Admin/Manager users can inspect jobs and reconciliation differences, retry bounded failures, or cancel with a reason. A future provider adapter will validate response status, reference, and timestamp before recording acceptance. The current implementation performs no outbound network call.

The current PBPL invoice series is preserved. Documentation will record compatibility concerns and a proposed future series/migration gate that requires accounting approval and never renumbers issued documents.

## Verification

Targeted tests cover provider unavailability, idempotency replay/conflict, approval gating, branch authorization, bounded retries, local-status immutability, and visible reconciliation. Migration SQL and frontend lint/type/build are run before completion.
