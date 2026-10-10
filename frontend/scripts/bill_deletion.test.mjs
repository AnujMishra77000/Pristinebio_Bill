import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const elements = [];
let typedConfirmation;
let request;
class ApiError extends Error {
  constructor(status, message, detail) { super(message); this.status = status; this.detail = detail; }
}
const runtime = require('react/jsx-runtime');
const capture = name => (type, props, ...rest) => {
  elements.push({ type, props });
  // Exercise the real controlled-input handler and React state during SSR's
  // render-phase rerender; capture the final DOM handlers, never mock hooks.
  if (type === 'input' && typedConfirmation !== undefined && props.value !== typedConfirmation) {
    props.onChange({ target: { value: typedConfirmation } });
  }
  return runtime[name](type, props, ...rest);
};
async function compile(path, dependencies = {}) {
  const source = await readFile(new URL(path, import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports = {};
  new Function('require', 'exports', compiled)(name => dependencies[name] ?? require(name), exports);
  return exports;
}
const registers = await compile('../app/lib/billRegisters.ts');
globalThis.window = new EventTarget();
globalThis.BroadcastChannel = undefined;
const sessions = await compile('../app/lib/invoiceEntrySession.ts', {
  './api': { getSessionState: () => ({ session: { user: { id: 1, is_active: true } } }), SESSION_CHANGED_EVENT: 'changed' },
});
const components = await compile('../app/components/BillRegisterPage.tsx', {
  'next/link': { default: () => null }, './AppShell': {}, './AuthGate': {}, './AppIcon': {}, './PageHeader': {},
  '@/app/lib/api': { ApiError, apiRequest: (...args) => request(...args) }, '@/app/lib/invoiceEntrySession': sessions, '@/app/lib/billRegisters': registers,
  'react/jsx-runtime': { ...runtime, jsx: capture('jsx'), jsxs: capture('jsxs') },
});

test('all four deletion dialogs explain that deleted document numbers can be reused', () => {
  for (const kind of ['sales', 'purchase', 'reagent', 'reagent-purchase']) {
    const bill = { id: 101, version: 3, document_type: kind.includes('reagent') ? 'reagent' : kind === 'purchase' ? 'domestic_oils' : 'sales',
      invoice_number: 'PBPL/2026-27/REUSE-001', purchase_order_number: 'PO-REUSE-001' };
    const html = renderToStaticMarkup(createElement(components.BillDeleteDialog, {
      kind, bill, canDelete: true, onCancel() {}, onDeleted() {},
    }));
    assert.match(html, /number can be reused for a new bill/i);
  }
});

test('cleanup-pending 503 invalidates erased invoice and view but retains exact retry until 204', async () => {
  const bill = { id: 101, version: 3, document_type: 'sales', invoice_number: 'PBPL/2026-27/SALES-001' };
  const entry = sessions.getInvoiceEntrySession(1, 'sales');
  entry.write('submission.document', bill);
  const calls = [];
  let pending = true, viewOpen = true, successes = 0;
  request = async (path, options) => {
    calls.push([path, options.method, JSON.parse(options.body)]);
    if (pending) throw new ApiError(503, 'Service Unavailable', { code: 'pdf_cleanup_pending', message: 'Bill removed; private PDF cleanup pending. Retry deletion.' });
  };
  typedConfirmation = bill.invoice_number;
  try {
    render(components.BillDeleteDialog, { kind: 'sales', bill, canDelete: true, onCancel() {},
      onDeletionPending() { viewOpen = false; }, onDeleted() { successes++; } });
  } finally { typedConfirmation = undefined; }
  const submit = elements.findLast(node => node.type === 'form').props.onSubmit;
  await submit({ preventDefault() {} });
  assert.equal(entry.active, false, 'Erased draft must not survive cleanup-pending');
  assert.equal(viewOpen, false, 'Erased PDF view must close on cleanup-pending');
  assert.equal(successes, 0, 'A 503 must not claim completion');
  pending = false;
  await submit({ preventDefault() {} });
  assert.equal(successes, 1);
  assert.deepEqual(calls, Array(2).fill(['/invoices/101', 'DELETE', {
    expected_version: 3, confirmation_number: 'PBPL/2026-27/SALES-001', document_type: 'sales',
  }]));
});

test('other deletion failures preserve invoice session and view with no success', async () => {
  for (const code of ['delete_failed', 'invalid_pdf_path']) {
    sessions.discardInvoiceEntrySession(1, 'sales');
    const entry = sessions.getInvoiceEntrySession(1, 'sales');
    const bill = { id: 101, version: 3, document_type: 'sales', invoice_number: 'PBPL/2026-27/SALES-001' };
    entry.write('submission.document', bill);
    request = async () => { throw new ApiError(503, 'Service Unavailable', { code, message: 'Deletion failed' }); };
    typedConfirmation = bill.invoice_number;
    try {
      render(components.BillDeleteDialog, { kind: 'sales', bill, canDelete: true,
        onCancel() {}, onDeletionPending() { assert.fail('Record still exists'); }, onDeleted() { assert.fail('Deletion failed'); } });
    } finally { typedConfirmation = undefined; }
    await elements.findLast(node => node.type === 'form').props.onSubmit({ preventDefault() {} });
    assert.equal(entry.active, true);
    assert.equal(entry.read('submission.document', null).id, 101);
  }
});

test('all four dialogs reject nonexact confirmation and send one versioned DELETE while busy', async () => {
  for (const [kind, type, collection, billNumber] of [
    ['sales', 'sales', 'invoices', 'PBPL/2026-27/SALES-001'],
    ['reagent', 'reagent', 'invoices', 'PBPL/2026-27/REAGENT-001'],
    ['purchase', 'domestic_oils', 'purchase-orders', 'CLIENT/PO-001'],
    ['reagent-purchase', 'reagent', 'purchase-orders', 'CLIENT/RPO-001'],
  ]) {
    const bill = { id: 101, version: 3, document_type: type,
      ...(collection === 'invoices' ? { invoice_number: billNumber } : { purchase_order_number: billNumber }) };
    let outgoing = 0, completed = 0, cancelled = 0, finish;
    request = async (path, options) => {
      outgoing++;
      assert.equal(path, `/${collection}/101`);
      assert.equal(options.method, 'DELETE');
      assert.deepEqual(JSON.parse(options.body), { expected_version: 3, confirmation_number: billNumber, document_type: type });
      await new Promise(resolve => { finish = resolve; });
    };
    const props = { kind, bill, canDelete: true, onCancel() { cancelled++; },
      onDeleted() { completed++; }, onDeletionPending() { assert.fail('No cleanup pending response'); } };
    for (const text of ['', billNumber.split('/').at(-1), `${billNumber} `, billNumber.toLowerCase()]) {
      typedConfirmation = text;
      try { render(components.BillDeleteDialog, props); } finally { typedConfirmation = undefined; }
      assert.equal(elements.findLast(node => node.type === 'button' && node.props.type === 'submit').props.disabled, true);
      await elements.findLast(node => node.type === 'form').props.onSubmit({ preventDefault() {} });
      assert.equal(outgoing, 0, 'Disabled confirmation must also guard form submission');
    }
    typedConfirmation = billNumber;
    try { render(components.BillDeleteDialog, props); } finally { typedConfirmation = undefined; }
    const submit = elements.findLast(node => node.type === 'form').props.onSubmit;
    const dialog = elements.findLast(node => node.type === 'dialog');
    dialog.props.ref.current = { close() { assert.fail('Busy modal cannot close'); } };
    const pending = submit({ preventDefault() {} });
    await submit({ preventDefault() {} });
    dialog.props.onCancel({ preventDefault() {} });
    elements.findLast(node => node.type === 'button' && node.props.children === 'Cancel').props.onClick();
    assert.equal(outgoing, 1); assert.equal(cancelled, 0); assert.equal(completed, 0);
    finish(); await pending;
    assert.equal(completed, 1);
  }
});
const render = (component, props) => {
  elements.length = 0;
  assert.equal(typeof component, 'function', 'Deletion UI component is missing');
  return renderToStaticMarkup(createElement(component, props));
};

test('real row actions expose Delete only to Admin across all four register schemas', () => {
  for (const [kind, number, bill] of [
    ['sales', 'PBPL/2026-27/SALES-001', { invoice_number: 'PBPL/2026-27/SALES-001' }],
    ['reagent', 'PBPL/2026-27/REAGENT-001', { invoice_number: 'PBPL/2026-27/REAGENT-001' }],
    ['purchase', 'CLIENT/PO-001', { purchase_order_number: 'CLIENT/PO-001' }],
    ['reagent-purchase', 'CLIENT/RPO-001', { purchase_order_number: 'CLIENT/RPO-001' }],
  ]) {
    const props = { bill: { ...bill, id: 101, version: 3 }, kind, onView() {}, onDelete() {} };
    const admin = render(components.BillRegisterActions, { ...props, isAdmin: true });
    assert.ok(admin.includes(`aria-label="View bill ${number}"`));
    assert.ok(admin.includes(`aria-label="Delete bill ${number}"`));
    assert.ok(!admin.includes('disabled=""'));
    for (const role of ['staff', 'manager']) {
      const html = render(components.BillRegisterActions, { ...props, isAdmin: role === 'admin' });
      assert.ok(html.includes('View bill'));
      assert.ok(!html.includes('Delete bill'));
    }
    assert.ok(render(components.BillRegisterActions, { ...props, bill: { ...props.bill, version: 0 }, isAdmin: true }).includes('disabled=""'));
  }
});

test('Cancel and Escape close the native modal before restoring focus outside it', () => {
  for (const action of ['button', 'escape']) {
    let returned = false;
    const nativeDialog = { open: true, close() { this.open = false; } };
    render(components.BillDeleteDialog, {
      kind: 'sales', bill: { id: 101, version: 3, document_type: 'sales', invoice_number: 'PBPL/2026-27/SALES-001' }, canDelete: true,
      onCancel() { assert.equal(nativeDialog.open, false, 'Close top-layer modal before focusing its trigger'); returned = true; },
      onDeleted() { assert.fail('Cancellation must not succeed as deletion'); },
    });
    const dialog = elements.find(node => node.type === 'dialog');
    dialog.props.ref.current = nativeDialog;
    if (action === 'button') elements.find(node => node.type === 'button' && node.props.children === 'Cancel').props.onClick();
    else dialog.props.onCancel({ preventDefault() {} });
    assert.equal(returned, true);
  }
});

test('real deletion dialog names the full bill and starts with destructive submission disabled', () => {
  const html = render(components.BillDeleteDialog, {
    kind: 'sales', bill: { id: 101, version: 3, invoice_number: 'PBPL/2026-27/SALES-001' },
    canDelete: true, onCancel() {}, onDeleted() {},
  });
  assert.ok(html.includes('<dialog'));
  assert.ok(html.includes('aria-labelledby="delete-bill-title"'));
  assert.ok(html.includes('aria-describedby="delete-bill-warning"'));
  assert.ok(html.includes('PBPL/2026-27/SALES-001'));
  assert.ok(html.includes('cannot be undone'));
  assert.ok(html.includes('Full bill number'));
  assert.ok(html.includes('disabled=""'));
});
