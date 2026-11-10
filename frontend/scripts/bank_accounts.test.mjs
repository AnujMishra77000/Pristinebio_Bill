import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import ts from 'typescript';

const require = createRequire(import.meta.url);
async function compile(path, dependencies) {
  const source = await readFile(new URL(path, import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  const exports = {};
  new Function('require', 'exports', compiled)(name => dependencies[name] ?? require(name), exports);
  return exports;
}

async function mount() {
  let cursor = 0, mounted = false, failSave = false;
  const state = [], effects = [], calls = [];
  const account = { id: 7, branch_id: 1, bank_name: 'Test Bank', account_name: 'Example Chemicals',
    account_number: '000123456789', ifsc_code: 'TEST0001234', branch_name: null,
    is_default: false, is_active: true };
  const hooks = {
    useState(initial) {
      const slot = cursor++;
      if (!(slot in state)) state[slot] = initial;
      return [state[slot], next => { state[slot] = typeof next === 'function' ? next(state[slot]) : next; }];
    },
    useRef(initial) { const slot = cursor++; return state[slot] ??= { current: initial }; },
    useEffect(effect) { if (!mounted) effects.push(effect); },
    useCallback(callback) { return callback; },
  };
  class ApiError extends Error {}
  const master = await compile('../app/components/MasterDataPage.tsx', {
    react: hooks, '@/app/components/AppShell': {}, '@/app/components/PageHeader': {},
    '@/app/components/AuthGate': { useAuthStatus: () => 'authenticated' },
    '@/app/lib/api': { ApiError, apiRequest: async (path, options = {}) => {
      if (options.method) {
        calls.push({ path, method: options.method, body: JSON.parse(options.body) });
        if (failSave) throw new ApiError('Save failed');
        return account;
      }
      if (path === '/companies/profile') return { seller_profile: { id: 1 } };
      assert.equal(path, '/bank-accounts');
      return [account];
    } },
  });
  const { default: BankAccountsPage } = await compile('../app/bank-accounts/page.tsx', {
    '@/app/components/MasterDataPage': master,
  });
  const props = BankAccountsPage().props;
  const render = () => {
    cursor = 0;
    const tree = master.MasterDataPage(props), nodes = [];
    function visit(node) {
      if (!node || typeof node !== 'object') return;
      nodes.push(node);
      const children = node.props?.children;
      (Array.isArray(children) ? children.flat(Infinity) : [children]).forEach(visit);
    }
    visit(tree);
    return nodes;
  };
  render(); mounted = true;
  effects.forEach(effect => effect());
  await new Promise(resolve => setImmediate(resolve));
  return { render, calls, account, failNextSave() { failSave = true; } };
}

test('bank Edit loads the saved account and updates the same ID with its leading zeros', async () => {
  const app = await mount();
  globalThis.window = { scrollTo() {} };
  try {
    const edit = app.render().find(node => node.type === 'button' && node.props.children === 'Edit');
    assert.ok(edit, 'Saved bank accounts must offer Edit');
    edit.props.onClick();
    let nodes = app.render();
    assert.equal(nodes.find(node => node.props?.id === 'master-account_number').props.value, '000123456789');
    assert.equal(nodes.find(node => node.props?.id === 'master-branch_name').props.value, '');
    nodes.find(node => node.props?.id === 'master-account_number').props.onChange({ target: { value: '000987654321' } });
    nodes = app.render();
    await nodes.find(node => node.type === 'form').props.onSubmit({ preventDefault() {} });
    assert.equal(app.calls.length, 1);
    assert.equal(app.calls[0].method, 'PATCH');
    assert.equal(app.calls[0].path, '/bank-accounts/7');
    assert.equal(app.calls[0].body.account_number, '000987654321');
    assert.equal(app.calls[0].body.branch_id, 1);
    assert.equal(app.calls[0].body.branch_name, null);
  } finally { delete globalThis.window; }
});

test('bank Set default targets the selected saved account with a bank-specific status', async () => {
  const app = await mount();
  const setDefault = app.render().find(node => node.type === 'button' && node.props.children === 'Set default');
  assert.ok(setDefault, 'Saved active bank accounts must offer Set default');
  await setDefault.props.onClick();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(app.calls, [{ path: '/bank-accounts/7', method: 'PATCH', body: { is_default: true } }]);
  const message = app.render().find(node => node.type === 'p' && node.props.role === 'status' && typeof node.props.children === 'string' && node.props.children.includes('updated'));
  assert.ok(message.props.children.includes('bank account'));
  assert.ok(!message.props.children.includes('supplier'));
});

test('failed bank edits retain the entered account and stay in edit mode for retry', async () => {
  const app = await mount();
  globalThis.window = { scrollTo() {} };
  try {
    const edit = app.render().find(node => node.type === 'button' && node.props.children === 'Edit');
    assert.ok(edit, 'Saved bank accounts must offer Edit');
    edit.props.onClick();
    app.render().find(node => node.props?.id === 'master-account_number').props.onChange({ target: { value: '000987654321' } });
    app.failNextSave();
    await app.render().find(node => node.type === 'form').props.onSubmit({ preventDefault() {} });
    const nodes = app.render();
    assert.equal(nodes.find(node => node.props?.id === 'master-account_number').props.value, '000987654321');
    assert.ok(nodes.some(node => node.type === 'button' && node.props.children === 'Update record'));
    assert.ok(nodes.some(node => node.props?.role === 'alert' && node.props.children === 'Save failed'));
  } finally { delete globalThis.window; }
});
