import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

const require = createRequire(import.meta.url);
async function compile(path, dependencies = {}) {
  const source = await readFile(new URL(path, import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports = {};
  new Function('require', 'exports', compiled)(name => dependencies[name] ?? require(name), exports);
  return exports;
}
const registers = await compile('../app/lib/billRegisters.ts');
const { BillRegisterActions } = await compile('../app/components/BillRegisterPage.tsx', {
  './AppShell': {}, './AuthGate': {}, './AppIcon': {}, './PageHeader': {},
  '@/app/lib/api': {}, '@/app/lib/invoiceEntrySession': {}, '@/app/lib/billRegisters': registers,
});
const cases = [['sales', 'sales', '/invoices?invoice=101'], ['reagent', 'reagent', '/reagent-bills?invoice=101'],
  ['purchase', 'domestic_oils', '/purchase-orders?order=101'], ['reagent-purchase', 'reagent', '/reagent-purchase-orders?order=101']];
function bill(kind, documentType, status = 'draft') {
  return { id: 101, version: 5, document_type: documentType, status,
    ...(kind === 'sales' || kind === 'reagent' ? { invoice_number: 'PBPL/2026-27/EDIT-101' } : { purchase_order_number: 'PO-EDIT-101' }) };
}
function render(kind, value, isAdmin = false) {
  return renderToStaticMarkup(createElement(BillRegisterActions, { kind, bill: value, isAdmin, onView() {}, onDelete() {} }));
}

test('each draft has an Edit link to its existing bill in the correct entry form, including Staff', () => {
  for (const [kind, type, href] of cases) {
    const html = render(kind, bill(kind, type));
    assert.ok(html.includes(`href="${href}"`), `${kind} is missing its saved-draft Edit link`);
    assert.match(html, />Edit<\/a>/);
  }
});
test('confirmed or submitted records cannot offer direct financial editing', () => {
  for (const [kind, type] of cases) for (const status of ['pending_approval', 'approved', 'pdf_generated', 'closed', 'cancelled']) {
    assert.doesNotMatch(render(kind, bill(kind, type, status), true), />Edit<\/a>/);
  }
});
test('existing purchase-order amendments remain editable but invalid versions/types do not', () => {
  for (const kind of ['purchase', 'reagent-purchase']) assert.match(render(kind, bill(kind, registers.billRegisters[kind].documentType, 'amendment_pending')), />Edit<\/a>/);
  assert.doesNotMatch(render('sales', { ...bill('sales', 'sales'), version: 0 }), />Edit<\/a>/);
  assert.doesNotMatch(render('purchase', bill('purchase', 'reagent')), />Edit<\/a>/);
});
