import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const [productsPage, invoiceEntry] = await Promise.all([
  readFile(new URL("../app/products/page.tsx", import.meta.url), "utf8"),
  readFile(new URL("../app/components/InvoiceEntryPage.tsx", import.meta.url), "utf8"),
]);

test("Product master hides the removed save fields", () => {
  for (const removedField of [
    "Manufacturer\", type",
    "Manufacturer product code / Part No.",
    "Unit\", type",
    "Base rate\", required",
  ]) {
    assert.doesNotMatch(productsPage, new RegExp(removedField));
  }

  assert.match(productsPage, /Maintain reusable product names, descriptions, HSN\/SAC classification and tax rates\./);
});

test("Reagent product selection is independent from manufacturer selection", () => {
  assert.match(invoiceEntry, /return products\.filter\(\(product\) => product\.is_active\);/);
  assert.doesNotMatch(invoiceEntry, /selectableProducts\.filter\(\(product\) => !isReagent/);
  assert.match(invoiceEntry, /manufacturer_id: manufacturerId, manufacturer_product_code: "", part_no: ""/);
});
