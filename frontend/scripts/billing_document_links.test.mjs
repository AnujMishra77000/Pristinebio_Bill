import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const [actions, billingPage] = await Promise.all([
  readFile(new URL("../app/components/BillingDocumentActions.tsx", import.meta.url), "utf8"),
  readFile(new URL("../app/billing/page.tsx", import.meta.url), "utf8"),
]);

test("billing creation links retain all four dedicated destinations", () => {
  const choices = [...actions.matchAll(/title: "([^"]+)",\s*href: "([^"]+)",\s*icon:/g)]
    .map(([, title, href]) => [title, href]);

  assert.deepEqual(choices, [
    ["Sales Invoice", "/invoices"],
    ["Purchase Order", "/purchase-orders"],
    ["Reagent Bill", "/reagent-bills"],
    ["Reagent Purchase Order", "/reagent-purchase-orders"],
  ]);
  assert.match(actions, /<Link key=\{document\.href\} href=\{document\.href\}/);
  assert.match(billingPage, /<BillingDocumentActions\s*\/>/);
  // Dashboard availability during loading/failure is exercised in the real
  // browser by verify_dashboard_registers_ui.py, not an obsolete source gate.
});
