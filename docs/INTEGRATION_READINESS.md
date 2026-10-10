# Integration readiness (Phase 5B)

## Discovery result

The repository was checked for provider documentation, credentials, sandbox URLs, approved accounting mappings, GST-registration facts, turnover/applicability decisions, and tax-adviser instructions. None are present. The application therefore does not select or claim support for Tally, Zoho, SAP, QuickBooks, an ERP, or any GST provider. No outbound request is made by the current implementation.

Before enabling an adapter, the client must provide:

- Provider name, product/version, API documentation and supported operations.
- A non-production sandbox URL and credentials delivered through the deployment secret store.
- Approved chart-of-accounts, tax-code, customer/vendor, rounding and document mappings.
- GST registrations, states, turnover/applicability facts, filing workflow, and written accounting/tax-adviser approval for IRN/e-way operations.
- Provider test cases, expected duplicate behavior, rate limits, retention requirements, and reconciliation ownership.

No GST obligation or turnover threshold is assumed in this phase.

## Boundary and status semantics

`outbound_integration_jobs` is the durable hand-off boundary. A job contains the branch/invoice scope, operation, canonical request payload hash, immutable request snapshot, scoped idempotency key, bounded attempt count, provider status, authoritative external reference/timestamp when supplied by a validated adapter, response snapshot, and failure details. `integration_audit_logs` records actor, time, action, reason, and before/after status. `integration_reconciliations` keeps open differences visible until an authorized retry or reasoned cancellation resolves them.

Local invoice approval remains authoritative for the local workflow. An external job begins as `unavailable` when configuration is absent; this is not an external rejection or acceptance. A user-entered IRN, e-way bill number, or other claimed identifier is retained only in the request snapshot and can never populate `external_reference` or mark the job accepted. A future adapter must validate the provider response, allowed status, authoritative reference, and provider timestamp before writing acceptance.

Creation requires `Idempotency-Key`. The database unique constraint on branch and key is the concurrency backstop: the same payload replays the original job, while a changed provider, operation, invoice, or claimed identifier conflicts. Retry keeps the original key and is limited to three attempts. An uncertain outcome must remain uncertain until provider reconciliation; it must not be blindly submitted again. The current unavailable adapter makes no network call, so no external duplicate can be created.

Authorized Admin and Manager users can list jobs, inspect the reconciliation queue, retry recoverable work, or cancel with a required reason. Staff cannot create, list, retry, cancel, or reconcile integration jobs. All access is enforced server-side and remains branch-scoped.

## Numbering review and migration gate

Previously issued invoice numbers remain immutable. Sales Invoices and Reagent Bills now use `PBPL/{financial_year}/{staff_entered_suffix}`. Staff enters the suffix when creating either type of draft; the backend derives the Indian financial-year prefix from the invoice date, serializes number reservation under a PostgreSQL transaction lock, and enforces cross-type uniqueness through the existing database constraint. Approval preserves the entered number without automatic allocation. Sales and Reagent registers and dashboard counts remain separate. Compatibility with any provider or statutory document-series requirement remains unverified because no provider/accounting mapping was supplied.

No further numbering change is currently proposed. Any future provider-specific change requires an effective date for new documents, a forward-only migration/configuration record, mapping of old-to-new external references, duplicate/retry rules, and a reconciliation report. Issued invoices and historical snapshots must never be rewritten.

## Operational commands and limitations

Apply the forward migration with:

```bash
cd backend
./.venv/bin/python -m alembic upgrade head
```

Readiness is available at `/api/v1/integrations/providers`, job operations are under `/api/v1/integrations/jobs`, and open differences are under `/api/v1/integrations/reconciliation`. These endpoints are readiness controls, not a live accounting or GST integration. Inventory and batch/expiry workflows are outside this phase.
