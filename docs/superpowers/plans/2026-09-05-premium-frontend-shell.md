# Premium Frontend Shell and Operations UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the approved Demo A premium industrial UI to the existing frontend while preserving every current route, API contract, permission rule, billing calculation, workflow action and PDF behavior.

**Architecture:** Add small presentation components for local SVG icons, grouped navigation, page headers and field errors. Make `AppShell` explicit about dashboard versus operational mode, then migrate pages to the shared patterns without moving data-fetching or billing logic out of existing pages.

**Tech Stack:** Next.js App Router, React 19, TypeScript, Tailwind CSS, existing API client, existing Playwright smoke scripts.

**Spec:** `docs/superpowers/specs/2026-09-05-premium-frontend-shell-design.md`

## Global Constraints

- Frontend-only change; do not modify backend, database, auth, invoice calculations or PDF templates.
- Preserve all existing route URLs and API payloads.
- Dashboard is the only route with a persistent desktop sidebar.
- Operational pages use a top-left menu and full-width content.
- Do not add a third-party icon dependency; use typed local SVG icons.
- Keep seller profile/single-company behavior; do not reintroduce branch selection.
- Keep Decimal values represented as strings in frontend state and payloads.
- Keep field validation and backend error details contextual to the related form.
- Run targeted frontend checks while working and full frontend checks after the redesign.

---

### Task 1: Add the visual foundation and icon/navigation primitives

**Files:**
- Create: `frontend/app/components/AppIcon.tsx`
- Create: `frontend/app/components/NavigationMenu.tsx`
- Create: `frontend/app/components/PageHeader.tsx`
- Modify: `frontend/app/globals.css`
- Modify: `frontend/tailwind.config.ts`

**Interfaces:**
- `AppIcon({ name, size, strokeWidth, label })` renders a typed local SVG icon without a dependency.
- `NavigationMenu({ mobile, onNavigate })` renders grouped routes: Workspace, Masters and Control, with current-route highlighting.
- `PageHeader({ icon, eyebrow, title, description, breadcrumb, action })` renders the shared operational header.

- [ ] **Step 1: Add typed icon names and SVG paths** for dashboard, billing, sales invoice, purchase order, customers, products, seller profile, users, bank accounts, transporters, terms, settings and menu.
- [ ] **Step 2: Add the grouped route model** in `NavigationMenu.tsx` and make active route matching work for nested routes.
- [ ] **Step 3: Add visual tokens** for deep peacock, peacock green, emerald, lime, warm white, graphite, muted slate, green borders and green-tinted panel shadow.
- [ ] **Step 4: Run the frontend compiler** with `cd frontend && npm run type-check` and resolve only errors introduced by these new components.

### Task 2: Rebuild the shared shell with dashboard and operational modes

**Files:**
- Modify: `frontend/app/components/AppShell.tsx`
- Modify: `frontend/app/components/AuthGate.tsx`
- Modify: `frontend/app/lib/api.ts` only if shared error formatting needs a presentation-safe helper

**Interfaces:**
- `AppShell({ children, mode = "operational", title?, icon? })` supports dashboard and operational layouts.
- Dashboard mode renders the compact 214–224px desktop sidebar.
- Operational mode renders no persistent desktop sidebar and places `NavigationMenu` behind a top-left Menu button.

- [ ] **Step 1: Write the shell acceptance checklist** covering dashboard sidebar visibility, operational menu visibility, active route state, logout presence and mobile stacking.
- [ ] **Step 2: Replace the always-on sidebar** with the explicit `mode` prop and grouped `NavigationMenu`.
- [ ] **Step 3: Add the operational top bar** with menu button, breadcrumb/title slot and right-side user/logout controls.
- [ ] **Step 4: Preserve `AuthGateStatus` behavior** and update its loading/unauthenticated surfaces to the new palette without changing session behavior.
- [ ] **Step 5: Run `cd frontend && npm run lint && npm run type-check`**.

### Task 3: Add shared field-level validation presentation and improve master records

**Files:**
- Create: `frontend/app/components/FormField.tsx`
- Modify: `frontend/app/components/MasterDataPage.tsx`
- Modify: `frontend/app/customers/page.tsx`
- Modify: `frontend/app/products/page.tsx`
- Modify: `frontend/app/bank-accounts/page.tsx`
- Modify: `frontend/app/transporters/page.tsx`
- Modify: `frontend/app/terms/page.tsx`

**Interfaces:**
- `FieldErrors = Record<string, string>`.
- `FormField({ name, label, error, required, children })` attaches `aria-invalid` and `aria-describedby` to its child control and renders the error immediately below it.
- `fieldErrorsFromApiError(error)` maps FastAPI/Pydantic `detail[].loc` final segments to field names and returns form-level messages separately.

- [ ] **Step 1: Add a failing TypeScript usage/check** for field errors rendering below a field and for mapping a Pydantic location such as `body.email` to `email`.
- [ ] **Step 2: Implement `FormField` and the API-error mapping helper** without changing payload transformation.
- [ ] **Step 3: Update `MasterDataPage`** to keep `fieldErrors` and `formError` separate, clear the field error on edit, and render the split form/table layout with the new page header and icon.
- [ ] **Step 4: Keep Seller/GST profile gating contextual** and ensure missing seller profile errors remain near the create action while field errors render under inputs.
- [ ] **Step 5: Run targeted checks** with `cd frontend && npm run lint && npm run type-check`.

### Task 4: Redesign the dashboard and billing chooser

**Files:**
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/billing/page.tsx`

- [ ] **Step 1: Update dashboard to use `AppShell mode="dashboard"`** and retain the current demonstration metrics/activity values.
- [ ] **Step 2: Apply KPI icon cards, workflow pulse panel, recent activity panel and compact responsive spacing** from the approved visual system.
- [ ] **Step 3: Update the billing chooser to use operational mode** with two dedicated document cards, invoice/purchase icons and clear action hierarchy.
- [ ] **Step 4: Remove internal-development wording** from visible dashboard/billing copy while keeping business terminology.
- [ ] **Step 5: Run `cd frontend && npm run type-check`**.

### Task 5: Redesign sales invoice and purchase-order entry screens

**Files:**
- Modify: `frontend/app/invoices/page.tsx`
- Modify: `frontend/app/purchase-orders/page.tsx`

**Interfaces:**
- Keep all existing state, API paths, payload builders, totals, saved-record actions and PDF actions unchanged.
- Add page-level `FieldErrors` state and use shared field styling for party, document and line-item controls.

- [ ] **Step 1: Add focused validation mapping cases** for buyer/consignee, invoice date, line item, supplier, quantity, rate and GST fields.
- [ ] **Step 2: Change both pages to `AppShell mode="operational"`** and add the shared top bar/page header.
- [ ] **Step 3: Recompose each page into a full-width 12-column workspace** with party/document panels, full-width dynamic item table and live-total summary.
- [ ] **Step 4: Render field errors directly below the matching control**, keeping cross-field/network errors in the panel alert.
- [ ] **Step 5: Preserve all existing buttons and actions**: save, update, submit, approve, preview, generate PDF, download and print.
- [ ] **Step 6: Run targeted smoke checks** using existing frontend scripts where applicable, then `cd frontend && npm run lint && npm run type-check`.

### Task 6: Migrate seller profile, settings and remaining operational pages

**Files:**
- Modify: `frontend/app/branches/page.tsx`
- Modify: `frontend/app/settings/page.tsx`
- Modify: `frontend/app/users/page.tsx`

- [ ] **Step 1: Apply operational shell, PageHeader and icon identity** to Seller profile, Settings and Users.
- [ ] **Step 2: Give Seller profile company, GST, bank and terms sections full-width responsive spacing** while preserving the existing API payload including account number and terms body.
- [ ] **Step 3: Replace the Settings page internal Phase 1B description** with business-facing account/settings language.
- [ ] **Step 4: Keep role and permission controls unchanged** and render errors contextually.
- [ ] **Step 5: Run `cd frontend && npm run lint && npm run type-check`**.

### Task 7: Full frontend verification and documentation

**Files:**
- Modify: `docs/PROJECT_STATUS.md`

- [ ] **Step 1: Run `cd frontend && npm run lint`** and record the result.
- [ ] **Step 2: Run `cd frontend && npm run type-check`** and record the result.
- [ ] **Step 3: Run `cd frontend && npm run build`** and record the result.
- [ ] **Step 4: Run existing browser smoke scripts** for auth error handling, seller profile and manual consignee flows when their local-server prerequisites are available.
- [ ] **Step 5: Verify with source search** that visible UI copy contains no AI/agent/internal phase wording.
- [ ] **Step 6: Update `docs/PROJECT_STATUS.md`** with the redesign scope and exact commands/results, then stop without changing backend behavior.

## Review checklist

- Dashboard is the only persistent sidebar route.
- All operational pages use the top-left menu and full-width content.
- Icons are consistent, local SVGs and accessible.
- Form controls have correct `aria-invalid`/`aria-describedby` behavior.
- API payloads and route URLs are unchanged.
- Billing totals, workflow actions, PDF actions and permissions are unchanged.
- No hidden branch selection or internal development copy was reintroduced.

