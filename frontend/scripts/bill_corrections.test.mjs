import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import ts from 'typescript';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const require = createRequire(import.meta.url);
async function compile(path, dependencies) {
  const source = await readFile(new URL(path, import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  new Function('require', 'exports', compiled)(name => dependencies[name] ?? require(name), exports);
  return exports;
}
class ApiError extends Error { constructor(status, message, detail) { super(message); this.status = status; this.detail = detail; } }
// Minimal hook scheduler: real application functions, with only React and HTTP boundaries replaced.
async function harness({ collection = '/invoices', updateField, role = 'admin', document, respond } = {}) {
  let cursor = 0, effects = [], slots = [], current;
  const calls = [], values = new Map();
  const ref = (key, initial) => ({ get current() { return values.has(key) ? values.get(key) : initial; }, set current(value) { values.set(key, value); } });
  const react = {
    useCallback(callback, deps) { const index = cursor++; if (!slots[index] || deps.some((value, i) => value !== slots[index].deps[i])) slots[index] = { callback, deps }; return slots[index].callback; },
    useRef(initial) { const index = cursor++; return slots[index] ??= { current: initial }; },
    useState(initial) { const index = cursor++; if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial; return [slots[index], value => { slots[index] = typeof value === 'function' ? value(slots[index]) : value; }]; },
    useEffect(effect, deps) { const index = cursor++; if (!slots[index] || deps?.some((value, i) => value !== slots[index][i])) { slots[index] = deps; effects.push(effect); } },
  };
  const api = { ApiError, getStoredSession: () => ({ user: { id: 1, role } }), createIdempotencyKey: () => 'retry-key',
    async apiRequest(path, options = {}) { const call = { path, method: options.method ?? 'GET', body: options.body ? JSON.parse(options.body) : null }; calls.push(call); return respond(call); },
    async fetchFileBlob(path, options = {}) { calls.push({ path, method: options.method ?? 'GET', body: options.body ? JSON.parse(options.body) : null }); return new Blob(['pdf']); },
  };
  const entry = { active: true, write(key, value) { values.set(key, value); } };
  const sessions = { useInvoiceEntryRef: (_entry, key, initial) => ref(key, initial), useInvoiceEntryValue: (_entry, key, initial) => [values.has(key) ? values.get(key) : initial, value => values.set(key, typeof value === 'function' ? value(values.get(key) ?? initial) : value)] };
  const { useBillSubmission } = await compile('../app/lib/useBillSubmission.ts', { react, './api': api, './invoiceEntrySession': sessions });
  const payload = { document_type: 'sales', invoice_number_suffix: 'LEGACY-101', buyer: { name: 'Snapshot' }, lines: [{ quantity: '2.000', rate: '100.0000' }] };
  const RenderHarness = () => { cursor = 0; effects = []; current = useBillSubmission({ collection, updateField, payload, entrySession: entry, validate: () => null }); effects.forEach(effect => effect()); return current; };
  RenderHarness();
  if (document) { current.restore(document); RenderHarness(); RenderHarness(); }
  return { calls, render: RenderHarness, get current() { return current; }, payload, values };
}
const correction = (overrides = {}) => ({ id: 101, version: 5, status: 'draft', pdf_storage_key: null, created_by_id: 2, submitted_by_id: null, submitted_revision: null,
  correction: { base_version: 5, reason: '', status: 'draft', previous_final_total: '118.00' }, ...overrides });

test('a virtual correction cannot save without a reason or create another bill', async () => {
  const h = await harness({ document: correction(), respond() { throw Error('Unexpected HTTP'); } });
  await h.current.save(); h.render();
  assert.match(h.current.error, /correction reason/i);
  assert.deepEqual(h.calls, []);
});
test('reasoned correction saves the same ID and version using each normal PATCH shape', async () => {
  for (const [collection, updateField] of [['/invoices', undefined], ['/purchase-orders', 'domestic_details'], ['/purchase-orders', 'reagent_details']]) {
    const h = await harness({ collection, updateField, document: correction(), respond: call => correction({ version: 6, correction: { ...correction().correction, reason: call.body.correction_reason } }) });
    h.current.setCorrectionReason('Quantity corrected'); h.render();
    await h.current.preview(); h.render();
    assert.equal(h.calls[0].path, `${collection}/101/correction`);
    assert.equal(h.calls[0].method, 'PATCH');
    assert.equal(h.calls[0].body.expected_version, 5);
    assert.equal(h.calls[0].body.correction_reason, 'Quantity corrected');
    if (!updateField) assert.equal('invoice_number_suffix' in h.calls[0].body, false, 'Correction must retain the issued identity even for legacy numbers');
    assert.equal((updateField ? h.calls[0].body[updateField] : h.calls[0].body).lines[0].quantity, '2.000');
    assert.equal(h.calls[1].path, `${collection}/101/correction/preview-pdf`);
    assert.deepEqual(h.calls[1].body, { expected_version: 6 });
  }
});

test('lost correction approval recovers via plain correction GET before generating the new PDF', async () => {
  const final = { ...correction(), status: 'approved', version: 6, correction: null, submitted_revision: 5, approved_revision: 5 };
  const h = await harness({ document: correction({ status: 'pending_approval', submitted_revision: 5, correction: { ...correction().correction, reason: 'Changed quantity', status: 'pending_approval' } }), respond: call => {
    if (call.path.endsWith('/approve')) throw new ApiError(0, 'Lost approval response');
    if (call.method === 'GET') { assert.equal(call.path, '/invoices/101/correction'); return final; }
    return { ...final, status: 'pdf_generated', pdf_storage_key: 'new.pdf' };
  } });
  await h.current.preview(); h.render(); await h.current.confirm(); h.render();
  assert.equal(h.current.finalReady, true);
  assert.deepEqual(h.calls.map(call => call.path), ['/invoices/101/correction/preview-pdf', '/invoices/101/correction/approve', '/invoices/101/correction', '/invoices/101/generate-pdf', '/invoices/101/pdf']);
});
test('creator Managers cannot approve a reviewed correction while independent Managers can', async () => {
  for (const creator of [1, 2]) {
    const h = await harness({ role: 'manager', document: correction({ status: 'pending_approval', created_by_id: creator, submitted_by_id: creator, submitted_revision: 5, correction: { ...correction().correction, reason: 'Changed quantity', status: 'pending_approval' } }), respond: call => {
      if (call.path.endsWith('/approve')) return { ...correction(), status: 'approved', version: 6, correction: null };
      return { ...correction(), status: 'pdf_generated', version: 6, correction: null, pdf_storage_key: 'new.pdf' };
    } });
    await h.current.preview(); h.render(); await h.current.confirm(); h.render();
    assert.equal(h.calls.some(call => call.path.endsWith('/approve')), creator === 2);
  }
});

test('reviewers can return a pending correction with a required reason and Staff cannot return it', async () => {
  for (const role of ['admin', 'manager', 'staff']) {
    const h = await harness({ role, document: correction({ status: 'pending_approval', submitted_revision: 5, correction: { ...correction().correction, reason: 'Quantity correction', status: 'pending_approval' } }), respond: call => {
      assert.deepEqual(call, { path: '/invoices/101/correction/return', method: 'POST', body: { expected_version: 5, reason: 'Please verify quantity' } });
      return correction({ version: 6, correction: { ...correction().correction, reason: 'Quantity correction' } });
    } });
    assert.equal(h.current.canReturnCorrection, role !== 'staff');
    assert.equal(typeof h.current.returnCorrection, 'function');
    await h.current.returnCorrection(''); h.render();
    assert.equal(h.calls.length, 0);
    assert.equal(h.current.document.status, 'pending_approval');
    await h.current.returnCorrection('Please verify quantity'); h.render();
    assert.equal(h.calls.length, role === 'staff' ? 0 : 1);
    assert.equal(h.current.document.status, role === 'staff' ? 'pending_approval' : 'draft');
    assert.equal(h.current.locked, role === 'staff');
  }
});

async function staleLoader(role, collection = '/invoices') {
  const calls = [], hydrated = [], slots = [];
  let cursor = 0, effects = [], current;
  const react = {
    useCallback(callback, deps) { const index = cursor++; if (!slots[index] || deps.some((value, i) => value !== slots[index].deps[i])) slots[index] = { callback, deps }; return slots[index].callback; },
    useRef(initial) { const index = cursor++; return slots[index] ??= { current: initial }; },
    useState(initial) { const index = cursor++; if (!(index in slots)) slots[index] = initial; return [slots[index], value => { slots[index] = typeof value === 'function' ? value(slots[index]) : value; }]; },
    useEffect(effect, deps) { const index = cursor++; if (!slots[index] || deps?.some((value, i) => value !== slots[index][i])) { slots[index] = deps; effects.push(effect); } },
  };
  const detail = { code: 'version_conflict', correction_base_changed: true, current_version: 12, correction_version: 8, message: 'Ask Manager/Admin to restart this stale correction.' };
  const api = { ApiError, getStoredSession: () => ({ user: { id: 1, role } }), async apiRequest(path, options = {}) {
    const call = { path, method: options.method ?? 'GET', body: options.body ? JSON.parse(options.body) : null }; calls.push(call);
    if (call.method === 'GET') throw new ApiError(409, detail.message, detail);
    return { ...correction(), document_type: 'sales', version: 12, correction: { ...correction().correction, base_version: 12, reason: 'Restart after parent update' } };
  } };
  globalThis.window = { location: { search: collection === '/invoices' ? '?invoice=101&correction=1' : '?order=101&correction=1', pathname: '/invoices' }, confirm: () => true };
  const { useSavedBillLoader } = await compile('../app/lib/useSavedBillLoader.ts', { react, './api': api, 'next/navigation': { useSearchParams: () => new URLSearchParams(window.location.search) } });
  const RenderHarness = () => { cursor = 0; effects = []; current = useSavedBillLoader({ collection, parameter: collection === '/invoices' ? 'invoice' : 'order', documentType: 'sales', authenticated: true, ready: true, document: null, busy: false, unsaved: false, hasWork: false, hydrate: bill => hydrated.push(bill) }); effects.forEach(effect => effect()); return current; };
  RenderHarness(); await new Promise(resolve => setImmediate(resolve)); RenderHarness();
  return { calls, hydrated, render: RenderHarness, get current() { return current; } };
}
test('stale corrections can restart only with reviewer reason, discard confirmation and both server versions', async () => {
  for (const collection of ['/invoices', '/purchase-orders']) {
    const h = await staleLoader('manager', collection);
    assert.equal(h.current.canRestart, true);
    assert.equal(h.current.blocked, true);
    assert.equal(typeof h.current.restart, 'function');
    await h.current.restart(); h.render();
    assert.equal(h.calls.length, 1, 'A reason is required before restart');
    h.current.setRestartReason('Restart after parent update'); h.render();
    window.confirm = () => false;
    await h.current.restart(); h.render();
    assert.equal(h.calls.length, 1, 'Cancelled discard must not write');
    window.confirm = () => true;
    await h.current.restart(); h.render();
    assert.deepEqual(h.calls[1], { path: `${collection}/101/correction/restart`, method: 'POST', body: { expected_version: 12, correction_version: 8, reason: 'Restart after parent update' } });
    assert.equal(h.current.blocked, false);
    assert.equal(h.hydrated[0].correction.base_version, 12);
  }
});
test('Staff stale-correction loads retain the error and cannot call restart', async () => {
  const h = await staleLoader('staff');
  assert.equal(h.current.canRestart, false);
  assert.equal(typeof h.current.restart, 'function');
  h.current.setRestartReason('Not authorized'); h.render();
  await h.current.restart(); h.render();
  assert.equal(h.calls.length, 1);
  assert.equal(h.current.blocked, true);
  assert.match(h.current.error, /Manager\/Admin/i);
});
test('a correction conflict retains entered reason and original optimistic version', async () => {
  const h = await harness({ document: correction(), respond() { throw new ApiError(409, 'Another user changed this bill', { code: 'version_conflict' }); } });
  h.current.setCorrectionReason('Keep my reason'); h.render();
  await h.current.save(); h.render();
  assert.equal(h.current.correctionReason, 'Keep my reason');
  assert.equal(h.current.document.version, 5);
  assert.match(h.current.error, /fields are retained/i);
  assert.equal(h.current.unsaved, true);
});
test('a pending correction requires PDF review before Confirm and locks its fields', async () => {
  const h = await harness({ document: correction({ status: 'pending_approval', submitted_revision: 4, correction: { ...correction().correction, reason: 'Changed quantity', status: 'pending_approval' } }), respond() { throw Error('Unexpected HTTP'); } });
  assert.equal(h.current.locked, true);
  assert.equal(h.current.canConfirm, false);
  await h.current.confirm(); h.render();
  assert.deepEqual(h.calls, []);
  assert.match(h.current.error, /preview/i);
  await h.current.preview(); h.render();
  assert.equal(h.current.canConfirm, true);
});
test('Staff submit a reviewed correction without approving or generating a final PDF', async () => {
  const h = await harness({ role: 'staff', document: correction({ correction: { ...correction().correction, reason: 'Changed quantity' } }), respond: call => {
    assert.equal(call.path, '/invoices/101/correction/submit');
    return correction({ status: 'pending_approval', version: 6, submitted_revision: 5, submitted_by_id: 1, correction: { ...correction().correction, reason: 'Changed quantity', status: 'pending_approval' } });
  } });
  await h.current.preview(); h.render(); await h.current.confirm(); h.render();
  assert.deepEqual(h.calls.map(call => call.path), ['/invoices/101/correction/preview-pdf', '/invoices/101/correction/submit']);
  assert.equal(h.current.finalReady, false);
});
test('Admin approval clears correction routing before original final PDF generation', async () => {
  const location = { pathname: '/invoices', search: '?invoice=101&correction=1' };
  globalThis.window = { location, history: { replaceState(_state, _title, url) { location.search = new URL(url, 'http://localhost').search; } } };
  const h = await harness({ document: correction({ status: 'pending_approval', submitted_revision: 4, correction: { ...correction().correction, reason: 'Changed quantity', status: 'pending_approval' } }), respond: call => {
    if (call.path.endsWith('/correction/approve')) return { ...correction(), version: 6, status: 'approved', correction: null };
    assert.equal(call.path, '/invoices/101/generate-pdf');
    return { ...correction(), version: 6, status: 'pdf_generated', correction: null, pdf_storage_key: 'new.pdf' };
  } });
  await h.current.preview(); h.render(); await h.current.confirm(); h.render();
  assert.deepEqual(h.calls.map(call => call.path), ['/invoices/101/correction/preview-pdf', '/invoices/101/correction/approve', '/invoices/101/generate-pdf', '/invoices/101/pdf']);
  assert.equal(h.current.finalReady, true);
  assert.equal(location.search, '?invoice=101', 'A published correction must no longer open another correction after busy state changes');
});

test('query-only navigation hydrates the newly requested saved bill on a mounted entry form', async () => {
  const calls = [], hydrated = [], slots = [];
  let cursor = 0, effects = [];
  const react = {
    useCallback(callback, deps) { const index = cursor++; if (!slots[index] || deps.some((value, i) => value !== slots[index].deps[i])) slots[index] = { callback, deps }; return slots[index].callback; },
    useRef(initial) { const index = cursor++; return slots[index] ??= { current: initial }; },
    useState(initial) { const index = cursor++; if (!(index in slots)) slots[index] = initial; return [slots[index], value => { slots[index] = typeof value === 'function' ? value(slots[index]) : value; }]; },
    useEffect(effect, deps) { const index = cursor++; if (!slots[index] || deps?.some((value, i) => value !== slots[index][i])) { slots[index] = deps; effects.push(effect); } },
  };
  const document = { id: 101, document_type: 'sales', version: 5 };
  globalThis.window = { location: { pathname: '/invoices', search: '?invoice=101' }, confirm: () => true };
  const { useSavedBillLoader } = await compile('../app/lib/useSavedBillLoader.ts', {
    react, 'next/navigation': { useSearchParams: () => new URLSearchParams(window.location.search) },
    './api': { ApiError, getStoredSession: () => ({ user: { role: 'admin' } }), apiRequest: async path => { calls.push(path); return { ...document, id: 102 }; } },
  });
  const RenderHarness = () => { cursor = 0; effects = []; useSavedBillLoader({ collection: '/invoices', parameter: 'invoice', documentType: 'sales', authenticated: true, ready: true, document, busy: false, unsaved: false, hasWork: true, hydrate: bill => hydrated.push(bill) }); effects.forEach(effect => effect()); };
  RenderHarness();
  assert.deepEqual(calls, []);
  window.location.search = '?invoice=102';
  RenderHarness(); await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(calls, ['/invoices/102']);
  assert.equal(hydrated[0]?.id, 102);
});

test('correction queue shows exact before/after totals and links all four forms for review without blind approval', async () => {
  const { CorrectionQueue } = await compile('../app/components/CorrectionQueue.tsx', {});
  assert.equal(typeof CorrectionQueue, 'function');
  const html = renderToStaticMarkup(createElement(CorrectionQueue, { items: [
    { collection: 'invoices', document_type: 'sales', document_id: 101, document_number: 'SALES', reason: 'Fix quantity', previous_final_total: '118.00', final_total: '236.00' },
    { collection: 'invoices', document_type: 'reagent', document_id: 102, document_number: 'REAGENT', reason: 'Fix rate', previous_final_total: '9007199254740993.00', final_total: '9007199254740994.00' },
    { collection: 'purchase-orders', document_type: 'domestic_oils', document_id: 103, document_number: 'PO', reason: 'Fix transport', previous_final_total: '118.00', final_total: '236.00' },
    { collection: 'purchase-orders', document_type: 'reagent', document_id: 104, document_number: 'REAGENT PO', reason: 'Fix details', previous_final_total: '118.00', final_total: '236.00' },
  ], total: 4 }));
  for (const href of ['/invoices?invoice=101', '/reagent-bills?invoice=102', '/purchase-orders?order=103', '/reagent-purchase-orders?order=104']) assert.ok(html.includes(`${href}&amp;correction=1`));
  for (const text of ['Fix quantity', '118.00', '236.00', '9007199254740993.00', '9007199254740994.00']) assert.ok(html.includes(text));
  assert.doesNotMatch(html, /<button[^>]*>Approve<\/button>/);
});
