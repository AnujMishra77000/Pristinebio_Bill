# Premium Frontend Shell and Operations UI Design

## Goal

Give the existing Pristine Biopharma billing PWA a compact, premium industrial interface with a dashboard-only sidebar, full-width operational pages, consistent feature icons, spacious data-entry layouts, and field-level validation messages.

## Scope

- Redesign the shared frontend shell and visual tokens.
- Keep the persistent sidebar on the dashboard only.
- Give all operational pages a top-left menu control and full-width content area.
- Apply the same page header, section-panel, icon, table and action patterns to billing and master-record pages.
- Keep all existing routes, API contracts, permission behavior, calculations and PDF actions unchanged.
- Remove user-facing copy that refers to AI agents, internal implementation phases or development status.
- Keep the existing single-company Seller/GST profile model; do not reintroduce branch selection.

## Non-goals

- No backend, database, authentication, billing-calculation or PDF-template changes.
- No new billing workflow or master-record capability.
- No dashboard analytics API; existing demonstration values remain demonstration values.
- No third-party icon dependency. Icons will be a small typed local SVG set.

## Visual system

Use a restrained premium palette consistent with the approved green/peacock-green brand direction:

- Deep peacock: `#073F3B` for navigation, primary actions and strong totals.
- Peacock green: `#0C554C` for table headers and active states.
- Emerald: `#0B7A5E` for links, positive states and section accents.
- Lime: `#B9E36A` for primary action emphasis and active dashboard navigation.
- Warm white: `#FCFCF8` for the page canvas.
- White: `#FFFFFF` for panels and form surfaces.
- Graphite: `#142521` for headings and values.
- Muted slate: `#71817E` for supporting text.
- Soft green line: `#E2EBE7` for borders.

Use moderate 12–16px panel radii, subtle green-tinted shadows, strong typographic hierarchy, generous form spacing, and responsive grids. Avoid decorative gradients, excessive pills, oversized text, and purple/lilac application chrome.

## Shell behavior

`AppShell` will accept a `mode` prop with `"dashboard"` and `"operational"` values.

- Dashboard mode: desktop left navigation is 214–224px wide and grouped into Workspace, Masters and Control. It shows concise labels and local SVG icons. The content starts at the first available column without a second permanent navigation bar.
- Operational mode: no desktop sidebar. A compact top-left `Menu` button opens a grouped navigation popover containing all existing routes. The current route is highlighted. The page title, breadcrumb and main action share the same top bar.
- Mobile: all pages use the compact top menu; dashboard navigation becomes the same menu rather than a second horizontal navigation strip.
- The existing logout action and session behavior remain unchanged.

## Page patterns

### Dashboard

Keep the current demonstration metrics and recent activity, but restyle them as four compact KPI cards, a workflow pulse panel, and a recent activity panel. Each KPI and activity row receives a meaningful icon or avatar treatment.

### Billing entry

Sales invoice and purchase-order pages use a full-width responsive workspace:

- Top bar with menu, breadcrumb, document title and primary save action.
- Spacious party/document sections in a 12-column layout.
- Full-width item table with readable long-text cells and a clear add-line action.
- Sticky or top-aligned live-total summary on wide screens; stacked before the form on narrow screens.
- Existing manual/saved modes, preview totals, save, approval, PDF, download and print actions remain intact.

### Master records

Customers, products, bank accounts, transporters and terms use the existing generic `MasterDataPage` contract, but render a premium split layout: creation form on the left and saved records/table on the right. Seller profile retains its dedicated page and uses the same section panels for company, GST, bank and terms details.

## Validation and errors

Create a shared field error representation keyed by field name. Inputs render:

- `aria-invalid="true"` when the field has an error.
- An `aria-describedby` link to the message directly below the input.
- A warm error border and subtle tinted background.
- The exact field message below that field, not only a page-level alert.

Backend Pydantic error arrays are mapped from their final `loc` segment to the form field name. Cross-field or network errors remain in a compact form-level alert at the top of the affected panel. Existing success messages remain visible but use the new status treatment.

## Component boundaries

- `frontend/app/components/AppShell.tsx`: dashboard/operational shell and responsive header.
- `frontend/app/components/AppIcon.tsx`: typed local SVG icon map and accessible icon wrapper.
- `frontend/app/components/NavigationMenu.tsx`: grouped route list and operational menu popover.
- `frontend/app/components/PageHeader.tsx`: breadcrumb, title, description, icon and primary action slot.
- `frontend/app/components/FormField.tsx`: shared label, input/textarea/select shell and field error rendering.
- `frontend/app/components/MasterDataPage.tsx`: reusable master form/table layout and field-level error mapping.
- `frontend/app/globals.css` and `frontend/tailwind.config.ts`: visual tokens and reusable surface utilities.
- `frontend/app/page.tsx`, `billing/page.tsx`, `invoices/page.tsx`, `purchase-orders/page.tsx`, master pages and `settings/page.tsx`: adopt the shell/page patterns and remove internal development copy.

Do not move invoice calculations, API calls, authentication logic or PDF actions into these presentation components.

## Acceptance criteria

1. Dashboard is the only route with a persistent desktop sidebar.
2. Every other route has a top-left menu and no persistent sidebar on desktop.
3. Each primary route has a dedicated icon and branded page header.
4. Billing entry fields occupy the available page width, with responsive stacking on small screens.
5. Master forms and record lists have readable spacing at desktop and mobile widths.
6. Validation errors appear below the related field for generic master forms, invoice forms and purchase-order forms; unrelated errors remain form-level.
7. No visible UI text says AI, agent, Phase 1A/1B/1E, generated by, or similar internal-development wording.
8. Existing API behavior, route URLs, permissions, calculations and PDF actions continue to work.
9. `npm run lint`, `npm run type-check` and `npm run build` pass after the redesign.

