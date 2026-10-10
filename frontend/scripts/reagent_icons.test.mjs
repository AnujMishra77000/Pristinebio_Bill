import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const require = createRequire(import.meta.url);
async function loadTypeScript(relativePath) {
  const source = await readFile(new URL(relativePath, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020 },
  });
  const loadedModule = { exports: {} };
  runInNewContext(outputText, { require, module: loadedModule, exports: loadedModule.exports });
  return loadedModule.exports;
}

const { AppIcon } = await loadTypeScript("../app/components/AppIcon.tsx");
const { billRegisters } = await loadTypeScript("../app/lib/billRegisters.ts");
const render = (name, props = {}) => renderToStaticMarkup(createElement(AppIcon, { name, ...props }));

test("Reagent icons render distinct chemistry artwork rather than generic product/order signs", () => {
  const reagent = render("reagent");
  const purchase = render("reagent-purchase-order");
  assert.ok((reagent.match(/<path /g) ?? []).length >= 2, "Reagent must render its bond structure");
  assert.ok((purchase.match(/<path /g) ?? []).length >= 2, "Reagent PO must render chemistry and its order marker");
  assert.notEqual(reagent, render("products"));
  assert.notEqual(purchase, render("purchase-order"));
  assert.notEqual(reagent, purchase);
});

test("Reagent icons retain inherited colors, sizing and accessible/decorative modes", () => {
  for (const name of ["reagent", "reagent-purchase-order"]) {
    const decorative = render(name, { size: 23 });
    assert.match(decorative, /aria-hidden="true"/);
    assert.match(decorative, /height="23"/);
    assert.match(decorative, /width="23"/);
    assert.match(decorative, /stroke="currentColor"/);
    assert.match(decorative, /fill="none"/);
    const labelled = render(name, { label: "Reagent chemistry" });
    assert.match(labelled, /role="img"/);
    assert.match(labelled, /aria-label="Reagent chemistry"/);
    assert.doesNotMatch(labelled, /aria-hidden/);
  }
});

test("Reagent registers select chemistry icons while other document symbols remain unchanged", () => {
  assert.equal(billRegisters.reagent.icon, "reagent");
  assert.equal(billRegisters["reagent-purchase"].icon, "reagent-purchase-order");
  assert.equal(billRegisters.sales.icon, "sales-invoice");
  assert.equal(billRegisters.purchase.icon, "purchase-order");
});
