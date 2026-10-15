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
test('confirmed bills open a staged correction in their matching form', () => {
  for (const [kind, type, href] of cases) for (const status of kind === 'sales' || kind === 'reagent' ? ['approved', 'pdf_generated'] : ['approved']) {
    assert.ok(render(kind, bill(kind, type, status)).includes(`href="${href}&amp;correction=1"`));
  }
});
test('submitted, closed and cancelled records cannot offer editing', () => {
  for (const [kind, type] of cases) for (const status of ['pending_approval', 'closed', 'cancelled', ...(['purchase', 'reagent-purchase'].includes(kind) ? ['pdf_generated'] : [])]) {
    assert.doesNotMatch(render(kind, bill(kind, type, status), true), />Edit<\/a>/);
  }
});
test('existing purchase-order amendments remain editable but invalid versions/types do not', () => {
  for (const kind of ['purchase', 'reagent-purchase']) assert.match(render(kind, bill(kind, registers.billRegisters[kind].documentType, 'amendment_pending')), />Edit<\/a>/);
  assert.doesNotMatch(render('sales', { ...bill('sales', 'sales'), version: 0 }), />Edit<\/a>/);
  assert.doesNotMatch(render('purchase', bill('purchase', 'reagent')), />Edit<\/a>/);
});

test('the loaded PDF viewer distinguishes draft editing from confirmed corrections', async () => {
  for (const [status, label] of [['draft', 'Edit this draft'], ['amendment_pending', 'Edit this draft'], ['approved', 'Edit confirmed bill'], ['pdf_generated', 'Edit confirmed bill']]) {
    let stateIndex = 0;
    const kind = status === 'amendment_pending' ? 'purchase' : 'sales';
    const loaded = { ...bill(kind, kind === 'purchase' ? 'domestic_oils' : 'sales', status), invoice_date: '2026-10-15', order_date: '2026-10-15', buyer_name: 'Snapshot buyer', final_total: '118.00' };
    const { BillPdfView } = await compile('../app/components/BillRegisterPage.tsx', {
      react: { Fragment: Symbol.for('react.fragment'), useState: initial => [stateIndex++ === 0 ? loaded : initial, () => {}], useRef: () => ({ current: null }), useEffect() {} },
      './AppShell': {}, './AuthGate': {}, './AppIcon': { AppIcon: () => null }, './PageHeader': {},
      '@/app/lib/api': {}, '@/app/lib/invoiceEntrySession': {}, '@/app/lib/billRegisters': registers,
    });
    assert.equal(typeof BillPdfView, 'function');
    const html = renderToStaticMarkup(createElement(BillPdfView, { kind, id: 101, onClose() {} }));
    assert.ok(html.includes(`>${label}</a>`), `${status} must use ${label}`);
  }
});
