# Credit Note Reagent-Style Correction Plan

**Goal:** Keep Credit Notes as a separate document/register/number series while making their entry fields, validation, saved line snapshots, and PDF presentation match Reagent Bills.

**Scope guard:** Do not change Sales Invoice, Purchase Order, Reagent Bill, or Reagent Purchase Order behavior.

## Task 1: Lock the corrected backend contract

- Extend Credit Note API tests to require an active manufacturer, supported reagent unit, manufacturer/article/pack snapshots, and unchanged Decimal totals.
- Extend Credit Note PDF tests to require the Reagent Bill table structure while retaining the `Credit Note` title and copy labels.
- Run only the affected tests and confirm they fail for the expected missing behavior.

## Task 2: Implement the shared reagent-style behavior

- Treat `credit_note` as reagent-style in invoice input validation and calculation-line preparation.
- Build Credit Note PDF contexts with reagent fields/layout and a new template version; preserve historical generated PDFs.
- Treat Credit Note as reagent-style in the existing invoice entry component while retaining Credit Note labels, navigation, register, and numbering.

## Task 3: Verify and document

- Run targeted backend and frontend regressions, type-check, lint, and production build.
- Render representative Credit Note PDFs and inspect PNG output for reagent fields and layout.
- Update README and project/reference documentation to describe the corrected Credit Note behavior.

No commit is included because the working tree already contains user-owned, uncommitted project changes that must remain intact.
