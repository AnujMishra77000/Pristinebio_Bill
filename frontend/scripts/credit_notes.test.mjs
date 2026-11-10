import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

const require = createRequire(import.meta.url);
async function compile(path, dependencies = {}, extraExports = '') {
  const source = await readFile(new URL(path, import.meta.url), 'utf8');
  const compiled = ts.transpileModule(`${source}\n${extraExports}`, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  const exports = {};
  new Function('require', 'exports', compiled)(name => dependencies[name] ?? require(name), exports);
  return exports;
}
const registers = await compile('../app/lib/billRegisters.ts');
const dates = await compile('../app/lib/indiaDate.ts');
const render = (Component, props = {}) => renderToStaticMarkup(createElement(Component, props));
const passthrough = ({ children }) => children;
const uiDependencies = {
  './AppShell': { AppShell: passthrough }, '@/app/components/AppShell': { AppShell: passthrough },
  './AppIcon': { AppIcon: () => null }, '@/app/components/AppIcon': { AppIcon: () => null },
  './PageHeader': { PageHeader: () => null }, '@/app/components/PageHeader': { PageHeader: () => null },
  '@/app/lib/api': {}, '@/app/lib/billRegisters': registers, '@/app/lib/invoiceEntrySession': {},
};
const note = (overrides = {}) => ({ id: 101, version: 3, document_type: 'credit_note', status: 'draft',
  invoice_number: 'PBPL/CN/2026-27/CN-7', invoice_date: '2026-10-23', buyer_name: 'Saved buyer',
  final_total: '118.00', ...overrides });

test('Credit Note register opens saved drafts and corrections in its own entry route', () => {
  assert.ok(registers.billRegisters['credit-note'], 'Credit Notes need their own register');
  assert.equal(registers.billEditHref('credit-note', note()), '/credit-notes?invoice=101');
  for (const status of ['approved', 'pdf_generated']) {
    assert.equal(registers.billEditHref('credit-note', note({ status })), '/credit-notes?invoice=101&correction=1');
  }
  for (const status of ['pending_approval', 'closed', 'cancelled']) assert.equal(registers.billEditHref('credit-note', note({ status })), null);
  assert.equal(registers.billEditHref('sales', note()), null);
  assert.equal(registers.billEditHref('credit-note', note({ document_type: 'sales' })), null);
  assert.equal(registers.billEditHref('credit-note', note({ version: 0 })), null);
});

test('Credit Note numbering follows its independent financial-year prefix', () => {
  for (const [date, expected] of [['2026-03-31', 'PBPL/CN/2025-26/'], ['2026-04-01', 'PBPL/CN/2026-27/'], ['', 'PBPL/CN/']]) {
    assert.equal(dates.invoiceNumberPrefix(date, 'credit_note'), expected);
  }
  assert.equal(dates.invoiceNumberPrefix('2026-04-01'), 'PBPL/2026-27/');
  assert.equal(dates.invoiceNumberPrefix('2026-04-01', 'reagent'), 'PBPL/2026-27/');
});

test('creation actions and Explore offer the Credit Note entry', async () => {
  const { BillingDocumentActions } = await compile('../app/components/BillingDocumentActions.tsx', uiDependencies);
  const { NavigationMenu } = await compile('../app/components/NavigationMenu.tsx', {
    ...uiDependencies, 'next/navigation': { usePathname: () => '/credit-notes' },
  });
  assert.match(render(BillingDocumentActions), /href="\/credit-notes"/);
  const navigation = render(NavigationMenu, { query: 'credit' });
  assert.match(navigation, /href="\/credit-notes"/);
  assert.match(navigation, /aria-current="page"/);
});

test('dashboard displays the backend Credit Note count and independent register link', async () => {
  let index = 0;
  const { default: Home } = await compile('../app/page.tsx', {
    ...uiDependencies,
    react: { useState: initial => [index++ === 0 ? { credit_note_count: 7, sales_invoice_count: 21 } : initial, () => {}], useEffect() {} },
    '@/app/components/AuthGate': { useAuthStatus: () => 'authenticated', AuthGateStatus: passthrough },
    '@/app/components/BillingDocumentActions': { BillingDocumentActions: () => null },
  });
  const html = render(Home);
  assert.match(html, /href="\/bill-registers\/credit-notes"/);
  const card = html.slice(html.indexOf('href="/bill-registers/credit-notes"')).split('</a>')[0];
  assert.match(card, />7 /);
});

test('approval and correction review links open the saved Credit Note by ID', async () => {
  const { CorrectionQueue } = await compile('../app/components/CorrectionQueue.tsx');
  const { ApprovalCard } = await compile('../app/approvals/page.tsx', {
    ...uiDependencies, '@/app/components/AuthGate': {}, '@/app/components/CorrectionQueue': {},
  }, 'export { ApprovalCard };');
  assert.match(render(CorrectionQueue, { total: 1, items: [{ collection: 'invoices', document_type: 'credit_note',
    document_id: 101, document_number: 'PBPL/CN/2026-27/CN-7', version: 4, reason: 'Reviewed change', previous_final_total: '118.00', final_total: '236.00' }] }),
  /href="\/credit-notes\?invoice=101&amp;correction=1"/);
  assert.match(render(ApprovalCard, { item: note({ status: 'pending_approval' }), type: 'invoice', busy: false, onApprove() {} }), /href="\/credit-notes\?invoice=101"/);
});

test('Credit Note register uses invoice endpoints with its own type filter', async () => {
  assert.ok(registers.billRegisters['credit-note']);
  const requests = [], effects = [];
  const { BillRegisterPage } = await compile('../app/components/BillRegisterPage.tsx', {
    ...uiDependencies,
    react: { Fragment: Symbol.for('react.fragment'), useState: value => [value, () => {}], useRef: () => ({ current: null }), useEffect: callback => effects.push(callback) },
    './AuthGate': { AuthGateStatus: passthrough, useAuthStatus: () => 'authenticated', useSessionState: () => ({ session: { user: { is_active: true, role: 'staff' } } }) },
    '@/app/lib/api': { apiRequest: async (path) => { requests.push(path); return { items: [], total: 0 }; } },
  });
  render(BillRegisterPage, { kind: 'credit-note' });
  effects.forEach(effect => effect());
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(requests[0], '/invoices/register?document_type=credit_note&sort=date_desc&page=1&page_size=10');
});

test('register offers Credit Note View/Edit and only prints confirmed saved PDFs', async () => {
  assert.ok(registers.billRegisters['credit-note']);
  const { BillRegisterActions } = await compile('../app/components/BillRegisterPage.tsx', { ...uiDependencies, './AuthGate': {} });
  const props = { kind: 'credit-note', isAdmin: false, onView() {}, onDelete() {}, onPrint() {} };
  const draft = render(BillRegisterActions, { ...props, bill: note() });
  assert.match(draft, />View<\/button>/);
  assert.match(draft, /href="\/credit-notes\?invoice=101"/);
  assert.doesNotMatch(draft, />Print<\/button>/);
  assert.match(render(BillRegisterActions, { ...props, bill: note({ status: 'pdf_generated', pdf_storage_key: 'cn.pdf' }) }), />Print<\/button>/);
});

test('Credit Note PDF printing targets the loaded final PDF frame and never prints a draft', async () => {
  assert.ok(registers.billRegisters['credit-note']);
  for (const status of ['draft', 'pending_approval', 'pdf_generated']) {
    let index = 0, printed = 0;
    const { BillPdfView } = await compile('../app/components/BillRegisterPage.tsx', {
      ...uiDependencies, './AuthGate': {},
      react: { useState: initial => [index++ === 0 ? note({ status, pdf_storage_key: status === 'pdf_generated' ? 'cn.pdf' : null }) : index === 2 ? 'blob:final-cn' : initial, () => {}],
        useRef: initial => ({ current: initial }), useEffect() {} },
    });
    const tree = BillPdfView({ kind: 'credit-note', id: 101, onClose() {}, autoPrint: true });
    const nodes = [];
    function visit(node) { if (!node || typeof node !== 'object') return; nodes.push(node); const children = node.props?.children; (Array.isArray(children) ? children.flat(Infinity) : [children]).forEach(visit); }
    visit(tree);
    const frame = nodes.find(node => node.type === 'iframe');
    frame.props.ref.current = { contentWindow: { focus() {}, print() { printed++; } } };
    const printButton = nodes.find(node => node.type === 'button' && node.props.children === 'Print');
    printButton?.props.onClick();
    assert.equal(printed, 0, 'Printing must wait for the final PDF iframe load');
    frame?.props.onLoad?.();
    assert.equal(printed, status === 'pdf_generated' ? 1 : 0);
  }
});

test('Credit Note register views use versioned draft previews and fetch stored final PDFs without writes', async () => {
  for (const status of ['draft', 'pdf_generated']) {
    const calls = [], effects = [];
    const { BillPdfView } = await compile('../app/components/BillRegisterPage.tsx', {
      ...uiDependencies, './AuthGate': {},
      react: { useState: initial => [initial, () => {}], useRef: () => ({ current: null }), useEffect: callback => effects.push(callback) },
      '@/app/lib/api': { apiRequest: async path => { calls.push({ path }); return note({ status, pdf_storage_key: status === 'pdf_generated' ? 'cn.pdf' : null }); },
        fetchFileBlob: async (path, options = {}) => { calls.push({ path, method: options.method ?? 'GET', body: options.body ? JSON.parse(options.body) : null }); return new Blob(['pdf']); } },
    });
    render(BillPdfView, { kind: 'credit-note', id: 101, onClose() {} });
    const cleanups = effects.map(effect => effect());
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(calls, [{ path: '/invoices/101' }, status === 'pdf_generated'
      ? { path: '/invoices/101/pdf', method: 'GET', body: null }
      : { path: '/invoices/101/preview-pdf', method: 'POST', body: { expected_version: 3 } }]);
    cleanups.forEach(cleanup => cleanup?.());
  }
});

test('dedicated pages bind Credit Note entry and the credit-note register', async () => {
  for (const [path, dependencies, expected] of [
    ['../app/credit-notes/page.tsx', { '@/app/components/InvoiceEntryPage': { InvoiceEntryPage: ({ documentType }) => createElement('div', { 'data-document-type': documentType }) } }, 'data-document-type="credit_note"'],
    ['../app/bill-registers/credit-notes/page.tsx', { '@/app/components/BillRegisterPage': { BillRegisterPage: ({ kind }) => createElement('div', { 'data-register-kind': kind }) } }, 'data-register-kind="credit-note"'],
  ]) {
    assert.ok(await readFile(new URL(path, import.meta.url), 'utf8').catch(() => null), `Missing route ${path}`);
    const { default: Page } = await compile(path, dependencies);
    assert.ok(render(Page).includes(expected));
  }
});

// Exercise the real form's hydration and payload construction. Only component,
// React lifecycle and HTTP boundaries are replaced; no billing data is invented by a mock.
async function formHarness() {
  const slots = [], values = new Map();
  let cursor = 0, loader, options, currentDocument = null;
  const react = {
    useState(initial) { const i = cursor++; if (!(i in slots)) slots[i] = typeof initial === 'function' ? initial() : initial;
      return [slots[i], next => { slots[i] = typeof next === 'function' ? next(slots[i]) : next; }]; },
    useRef(initial) { const i = cursor++; return slots[i] ??= { current: initial }; },
    useMemo: callback => callback(), useCallback: callback => callback, useEffect() {},
  };
  const entry = { active: true, has: key => values.has(key) };
  const submission = { busy: false, locked: false, unsaved: true,
    restore(document) { currentDocument = document; }, get document() { return currentDocument; } };
  const { InvoiceEntryForm } = await compile('../app/components/InvoiceEntryPage.tsx', {
    ...uiDependencies, react,
    '@/app/components/AuthGate': {},
    '@/app/components/AutoResizeTextarea': { AutoResizeTextarea: props => createElement('textarea', props) },
    '@/app/components/BillSubmissionPanel': { BillSubmissionPanel: () => null },
    '@/app/components/SavedBillLoadError': { SavedBillLoadError: () => null },
    '@/app/components/InvoiceSupplierPicker': { InvoiceSupplierPicker: () => null },
    '@/app/lib/indiaDate': dates,
    '@/app/lib/invoiceEntrySession': { useInvoiceEntryValue: (_entry, key, initial) => {
      if (!values.has(key)) values.set(key, typeof initial === 'function' ? initial() : initial);
      return [values.get(key), next => values.set(key, typeof next === 'function' ? next(values.get(key)) : next)];
    } },
    '@/app/lib/useBillSubmission': { useBillSubmission: input => { options = input; return submission; } },
    '@/app/lib/useSavedBillLoader': { useSavedBillLoader: input => { loader = input; return { blocked: false }; } },
  }, 'export { InvoiceEntryForm };');
  return { values, get loader() { return loader; }, get options() { return options; },
    render() { cursor = 0; return render(InvoiceEntryForm, { documentType: 'credit_note', authStatus: 'authenticated', entry, onStartNew() {} }); } };
}

test('saved Credit Notes hydrate Reagent fields, Decimal strings and manual suffix', async () => {
  const h = await formHarness();
  h.render();
  h.loader.hydrate(note({ buyer_customer_id: 5, branch_id: 1, buyer_name: 'Saved buyer snapshot', buyer_state_code: '36',
    buyer_address_line1: 'Saved address', consignee_name: 'Saved shipping snapshot', place_of_supply_state_code: '36',
    freight_charges: '1.25', packing_charges: '0.00', other_charges: '0.00', discount_amount: '0.00',
    lines: [{ product_id: 9, product_name: 'Saved transaction product', description: 'Saved description', hsn_sac: '3822',
      manufacturer_name: 'Merck', manufacturer_code: 'MRK', manufacturer_product_code: 'ART-18', part_no: 'ART-18', pack_size: '500 g',
      quantity: '12.345', rate: '100.1234', unit: 'kg', gst_rate: '18.00', cess_rate: '0.00', discount_amount: '0.00', discount_percent: '3.00', other_charge: '0.00' }] }));
  const html = h.render();
  assert.match(html, /value="CN-7"/);
  assert.match(html, /PBPL\/CN\/2026-27\//);
  assert.match(html, /Saved buyer snapshot/);
  assert.match(html, /Saved shipping snapshot/);
  assert.match(html, /MFG \/ Manufacturer/);
  assert.match(html, /MFG Product Code \/ Part No\./);
  assert.match(html, /Pack\/Size/);
  assert.match(html, /Disc %/);
  assert.doesNotMatch(html, />Other charge</);
  assert.doesNotMatch(html, />Cess %</);
  assert.equal(h.values.get('entryMode'), 'manual');
  assert.equal(h.options.collection, '/invoices');
  assert.equal(h.options.payload.document_type, 'credit_note');
  assert.equal(h.options.payload.invoice_number_suffix, 'CN-7');
  assert.equal(h.options.payload.lines[0].quantity, '12.345');
  assert.equal(h.options.payload.lines[0].rate, '100.1234');
  assert.equal(h.options.payload.lines[0].manufacturer_product_code, 'ART-18');
  assert.equal(h.options.payload.lines[0].part_no, 'ART-18');
  assert.equal(h.options.payload.lines[0].pack_size, '500 g');
  assert.equal(h.options.payload.lines[0].unit, 'kg');
  assert.equal(h.options.payload.lines[0].discount_percent, '3.00');
  assert.equal(h.options.payload.lines[0].other_charge, '0.00');
  assert.equal(h.options.payload.lines[0].cess_rate, '0.00');
  assert.equal(h.options.payload.buyer.name, 'Saved buyer snapshot');
  assert.equal(h.options.payload.consignee.name, 'Saved shipping snapshot');
});
