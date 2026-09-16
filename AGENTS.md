# Project instructions

Read `docs/BILLING_CONTEXT.md` and `docs/PROJECT_STATUS.md` first, before making any change.

- Work only on the phase explicitly requested in the current prompt.
- Do not scan `.git`, `node_modules`, `.next`, `dist`, coverage directories, or virtual environments.
- Preserve existing working code and avoid unrelated refactors.
- Use `Decimal` for all money and quantity values; do not use binary floating-point types for billing calculations.
- Keep API routes under `/api/v1`.
- Add targeted tests for every changed behaviour.
- Run targeted tests during development. Run the full test suite only when the requested phase is complete.
- Update `docs/PROJECT_STATUS.md` before stopping work.
- Never implement a future phase without an explicit prompt.

The approved invoice-layout reference is mapped in `docs/REFERENCE_INVOICE_MAP.md`. Treat that document as the source of truth for invoice PDF layout once its visual inspection is complete; do not infer or silently change layout details.
