import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { beforeEach, test } from 'node:test';
import ts from 'typescript';

const load = createRequire(import.meta.url);
let sessions, auth;
let broadcasts;
beforeEach(async () => {
  globalThis.window = new EventTarget();
  broadcasts = [];
  globalThis.BroadcastChannel = class extends EventTarget {
    constructor(name) { super(); this.name = name; broadcasts.push(this); }
    sent = [];
    postMessage(data) { this.sent.push(data); }
  };
  auth = { session: { user: { id: 1, is_active: true } }, explicitlyLoggedOut: false };
  const source = await readFile(new URL('../app/lib/invoiceEntrySession.ts', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const output = { exports: {} };
  new Function('require', 'exports', compiled)(name => name === './api'
    ? { getSessionState: () => auth, SESSION_CHANGED_EVENT: 'changed' } : load(name), output.exports);
  sessions = output.exports;
});

test('all four entry kinds retain fields, version and retry identity independently; completed entries reopen fresh', () => {
  const entries = ['sales', 'reagent', 'purchase', 'reagent-purchase'].map(kind => {
    const entry = sessions.getInvoiceEntrySession(1, kind);
    entry.write('lines', [{ product_name: kind, quantity: '12.345' }]);
    entry.write('submission.document', { id: 101, version: 3 });
    entry.ref('submission.intent', null).current = { key: `${kind}-retry`, signature: 'original-payload', uncertain: true };
    assert.equal(sessions.getInvoiceEntrySession(1, kind), entry);
    return entry;
  });
  assert.equal(new Set(entries).size, 4);
  entries[2].write('submission.completed', true);
  const next = sessions.getInvoiceEntrySession(1, 'purchase');
  assert.notEqual(next, entries[2], 'Confirmed work must not reappear as the next unconfirmed entry');
  assert.equal(next.read('lines', null), null);
  assert.equal(entries[2].active, false);
  assert.equal(entries[3].read('submission.intent', null).key, 'reagent-purchase-retry');
  sessions.discardInvoiceEntrySession(1, 'reagent');
  assert.equal(entries[1].active, false);
  assert.equal(entries[0].read('lines', null)[0].quantity, '12.345');
});

test('invoice and PO deletion never erase the other family with the same numeric ID', () => {
  const sales = sessions.getInvoiceEntrySession(1, 'sales');
  const purchase = sessions.getInvoiceEntrySession(1, 'purchase');
  const reagentPurchase = sessions.getInvoiceEntrySession(1, 'reagent-purchase');
  for (const entry of [sales, purchase, reagentPurchase]) entry.write('submission.document', { id: 101 });
  sessions.invalidateInvoiceEntrySession(101);
  assert.equal(sales.active, false);
  assert.equal(purchase.active, true, 'Invoice deletion cannot erase a PO');
  assert.equal(reagentPurchase.active, true);
  sessions.invalidatePurchaseOrderEntrySession(101);
  assert.equal(purchase.active, false);
  assert.equal(reagentPurchase.active, false);
  assert.deepEqual(broadcasts[0].sent, [{ type: 'invoice-deleted', id: 101 }, { type: 'purchase-order-deleted', id: 101 }]);
});

test('logout clears every bill type and prevents late responses from restoring private work', () => {
  const entries = ['sales', 'reagent', 'purchase', 'reagent-purchase'].map(kind => sessions.getInvoiceEntrySession(1, kind));
  entries.forEach(entry => entry.write('private', 'unfinished buyer details'));
  auth = { session: null, explicitlyLoggedOut: true };
  window.dispatchEvent(new Event('changed'));
  for (const entry of entries) {
    assert.equal(entry.active, false);
    entry.write('private', 'late response');
    assert.equal(entry.read('private', null), null);
  }
});

test('deleting an invoice disposes only its saved session and rejects late responses', () => {
  const sales = sessions.getInvoiceEntrySession(1, 'sales');
  const reagent = sessions.getInvoiceEntrySession(1, 'reagent');
  sales.write('submission.document', { id: 101, version: 3 });
  sales.write('submission.intent', { key: 'private-retry-key' });
  reagent.write('submission.document', { id: 202, version: 1 });
  let notified = 0;
  sales.subscribe(() => notified++);
  assert.equal(typeof sessions.invalidateInvoiceEntrySession, 'function', 'Public deletion invalidation is missing');
  sessions.invalidateInvoiceEntrySession(101);
  assert.equal(sales.active, false);
  assert.equal(notified, 1);
  sales.write('submission.document', { id: 101, version: 4 });
  assert.equal(sales.read('submission.document', null), null);
  assert.equal(sales.read('submission.intent', null), null);
  assert.equal(sessions.getInvoiceEntrySession(1, 'sales').read('submission.document', null), null);
  assert.equal(reagent.active, true);
  assert.deepEqual(reagent.read('submission.document', null), { id: 202, version: 1 });
  assert.deepEqual(broadcasts[0].sent, [{ type: 'invoice-deleted', id: 101 }], 'Broadcast must contain no bill/form/user data');
});

test('other-tab deletion validates messages, clears matching copies and does not rebroadcast', () => {
  const sales = sessions.getInvoiceEntrySession(1, 'sales');
  const reagent = sessions.getInvoiceEntrySession(1, 'reagent');
  sales.write('submission.document', { id: 101 });
  reagent.write('submission.document', { id: 202 });
  assert.equal(broadcasts.length, 1, 'Retained entries must listen for cross-tab deletion');
  for (const data of [null, {}, { type: 'logout', id: 101 }, { type: 'invoice-deleted', id: '101' }, { type: 'invoice-deleted', id: 0 }, { type: 'invoice-deleted', id: 303 }]) {
    broadcasts[0].dispatchEvent(new MessageEvent('message', { data }));
    assert.equal(sales.active, true);
  }
  broadcasts[0].dispatchEvent(new MessageEvent('message', { data: { type: 'invoice-deleted', id: 202 } }));
  assert.equal(reagent.active, false);
  assert.equal(sales.active, true);
  assert.deepEqual(broadcasts[0].sent, []);
});

test('matching deletion notifies mounted entry recovery after removal without erasing unrelated or unsaved work', () => {
  const sales = sessions.getInvoiceEntrySession(1, 'sales');
  const reagent = sessions.getInvoiceEntrySession(1, 'reagent');
  sales.write('submission.document', { id: 101 });
  reagent.write('buyer', 'Unsaved reagent work');
  const recovered = [];
  window.addEventListener('pristine-bio-billing.invoice-entry-invalidated', event => {
    const fresh = sessions.getInvoiceEntrySession(1, event.detail.kind);
    assert.equal(fresh.active, true);
    assert.notEqual(fresh, sales, 'Remount must obtain a fresh entry after the erased entry is removed');
    assert.equal(fresh.read('submission.document', null), null);
    recovered.push(event.detail.kind);
  });
  sessions.invalidateInvoiceEntrySession(303);
  assert.deepEqual(recovered, []);
  broadcasts[0].dispatchEvent(new MessageEvent('message', { data: { type: 'invoice-deleted', id: 101 } }));
  assert.deepEqual(recovered, ['sales'], 'Mounted matching kind needs a recovery notification');
  assert.equal(reagent.active, true);
  assert.equal(reagent.read('buyer', ''), 'Unsaved reagent work');
  sessions.invalidateInvoiceEntrySession(101);
  assert.deepEqual(recovered, ['sales'], 'A fresh unsaved entry must not be reset by a repeated deletion event');
});

test('each user retains two independent sessions with immediate fields and shared retry identity', () => {
  const sales = sessions.getInvoiceEntrySession(1, 'sales');
  const reagent = sessions.getInvoiceEntrySession(1, 'reagent');
  sales.write('buyer', { name: 'Entered buyer', address: 'New address' });
  const intent = sales.ref('intent', null);
  intent.current = { key: 'exact-key', signature: '{"quantity":"12.345"}', uncertain: true };
  sales.ref('document', null).current = { id: 101, version: 3 };
  const returned = sessions.getInvoiceEntrySession(1, 'sales');
  assert.equal(returned, sales);
  assert.deepEqual(returned.read('buyer', null), { name: 'Entered buyer', address: 'New address' });
  assert.equal(returned.ref('intent', null).current, intent.current);
  assert.deepEqual(returned.ref('document', null).current, { id: 101, version: 3 });
  assert.equal(reagent.read('buyer', null), null);
  sales.write('supplier', null);
  assert.equal(returned.read('supplier', undefined), null, 'Explicit no-supplier must not become default');
});

test('start new clears only that kind and stale async writes cannot revive its old session', () => {
  const sales = sessions.getInvoiceEntrySession(1, 'sales');
  const reagent = sessions.getInvoiceEntrySession(1, 'reagent');
  sales.write('buyer', 'old'); reagent.write('buyer', 'keep');
  sessions.discardInvoiceEntrySession(1, 'sales');
  assert.equal(sales.active, false);
  sales.write('buyer', 'late response'); sales.ref('document', null).current = { id: 5 };
  assert.equal(sales.read('buyer', null), null);
  assert.equal(sessions.getInvoiceEntrySession(1, 'sales').read('buyer', null), null);
  assert.equal(sessions.getInvoiceEntrySession(1, 'reagent').read('buyer', null), 'keep');
});

test('reauthentication keeps work; logout clears it even while entry pages are absent', () => {
  const sales = sessions.getInvoiceEntrySession(1, 'sales');
  sales.write('buyer', 'retained');
  auth.reauthenticationRequired = true;
  window.dispatchEvent(new Event('changed'));
  assert.equal(sales.active, true);
  auth = { session: null, explicitlyLoggedOut: true };
  window.dispatchEvent(new Event('changed'));
  assert.equal(sales.active, false);
  assert.equal(sales.read('buyer', null), null);
  auth = { session: { user: { id: 1, is_active: true } }, explicitlyLoggedOut: false };
  assert.equal(sessions.getInvoiceEntrySession(1, 'sales').read('buyer', null), null);
});

test('account switch and disable dispose every previous session without persistent storage', () => {
  const sales = sessions.getInvoiceEntrySession(1, 'sales');
  const reagent = sessions.getInvoiceEntrySession(1, 'reagent');
  auth.session.user.id = 2;
  window.dispatchEvent(new Event('changed'));
  assert.equal(sales.active, false); assert.equal(reagent.active, false);
  const next = sessions.getInvoiceEntrySession(2, 'sales');
  assert.equal(next.read('buyer', ''), '');
  auth.session.user.is_active = false;
  window.dispatchEvent(new Event('changed'));
  assert.equal(next.active, false);
});
