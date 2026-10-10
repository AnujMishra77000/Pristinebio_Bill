import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test, beforeEach } from 'node:test';
import ts from 'typescript';

let api, calls, messages, removed, csrf, authenticated, refreshCount, lockCount;
const user = { id: 1, email: 'admin@example.com', full_name: 'Admin', role: 'admin', branch_ids: [], is_active: true, password_change_required: false, mfa_enabled: true, mfa_required: true, mfa_verified: true };
let sequence = 0;
beforeEach(async () => {
  calls = []; messages = []; removed = []; csrf = 'anonymous'; authenticated = false; refreshCount = 0; lockCount = 0;
  const surface = new EventTarget();
  surface.localStorage = { getItem: () => null, setItem: () => assert.fail('Credentials must never be persisted'), removeItem: key => removed.push(key) };
  globalThis.window = surface;
  globalThis.BroadcastChannel = class { postMessage(value) { messages.push(value); } addEventListener() {} };
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { locks: { request: async (_name, callback) => { lockCount++; return callback(); } } } });
  globalThis.fetch = async (url, options = {}) => {
    const path = new URL(url).pathname.replace('/api/v1', '');
    calls.push({ path, ...options, headers: new Headers(options.headers) });
    const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
    if (path === '/auth/csrf') return json({ csrf_token: csrf });
    if (path === '/auth/login') { authenticated = true; csrf = 'session'; return json({ user }); }
    if (path === '/auth/refresh') { refreshCount++; authenticated = true; csrf = 'rotated'; return json({ user }); }
    if (path === '/auth/me') return authenticated ? json(user) : json({ detail: 'Unauthorized' }, 401);
    if (path === '/auth/logout') { authenticated = false; csrf = 'anonymous'; return json({ detail: 'Logged out' }); }
    if (!authenticated) return json({ detail: 'Session expired' }, 401);
    return json({ ok: true });
  };
  const source = await readFile(new URL('../app/lib/api.ts', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  api = await import(`data:text/javascript;base64,${Buffer.from(compiled + `\n//${sequence++}`).toString('base64')}`);
});

test('login includes cookies and anonymous CSRF, refreshes CSRF after session creation', async () => {
  await api.apiRequest('/auth/login', { method: 'POST', body: JSON.stringify({ email: user.email, password: 'old' }) });
  const login = calls.find(c => c.path === '/auth/login');
  assert.equal(login.credentials, 'include');
  assert.equal(login.headers.get('X-CSRF-Token'), 'anonymous');
  assert.equal(login.headers.get('Authorization'), null);
  await api.apiRequest('/customers', { method: 'POST', body: '{}' });
  assert.equal(calls.find(c => c.path === '/customers').headers.get('X-CSRF-Token'), 'session');
  assert.ok(removed.includes('pristine-bio-billing.session'));
  assert.deepEqual(api.getStoredSession(), { user });
  assert.ok(messages.every(message => !JSON.stringify(message).includes('csrf') && !JSON.stringify(message).includes('password')));
});

test('successful supplier DELETE accepts empty 204 and preserves server conflicts', async () => {
  await api.apiRequest('/auth/login', { method: 'POST', body: '{}' });
  const normalFetch = fetch;
  globalThis.fetch = (url, options) => new URL(url).pathname.endsWith('/suppliers/1')
    ? Promise.resolve(new Response(null, { status: 204 })) : normalFetch(url, options);
  assert.equal(await api.apiRequest('/suppliers/1', { method: 'DELETE' }), undefined);
  globalThis.fetch = (url, options) => new URL(url).pathname.endsWith('/suppliers/2')
    ? Promise.resolve(new Response('{"detail":"Supplier is used by a bill; deactivate it instead"}', { status: 409, headers: { 'Content-Type': 'application/json' } })) : normalFetch(url, options);
  await assert.rejects(api.apiRequest('/suppliers/2', { method: 'DELETE' }),
    error => error.status === 409 && /deactivate/.test(error.message));
  assert.deepEqual(api.getStoredSession(), { user });
});

test('concurrent expired-cookie requests refresh once inside Web Locks and replay exact save', async () => {
  const normalFetch = fetch;
  let release;
  const bothStarted = new Promise(resolve => { release = resolve; });
  globalThis.fetch = async (url, options) => {
    if (new URL(url).pathname.endsWith('/customers')) await bothStarted;
    if (new URL(url).pathname.endsWith('/invoices')) release();
    return normalFetch(url, options);
  };
  const body = '{"quantity":"1.000"}';
  const results = await Promise.all([api.apiRequest('/customers'), api.apiRequest('/invoices', { method: 'POST', headers: { 'Idempotency-Key': 'keep-this-key' }, body })]);
  assert.deepEqual(results, [{ ok: true }, { ok: true }]);
  assert.equal(refreshCount, 1);
  assert.equal(lockCount, 1);
  const refresh = calls.find(c => c.path === '/auth/refresh');
  assert.equal(refresh.body, undefined);
  assert.equal(refresh.credentials, 'include');
  assert.equal(refresh.headers.get('X-CSRF-Token'), 'anonymous');
  const saves = calls.filter(c => c.path === '/invoices');
  assert.equal(saves.length, 2);
  assert.ok(saves.every(c => c.body === body && c.headers.get('Idempotency-Key') === 'keep-this-key'));
  assert.equal(saves[1].headers.get('X-CSRF-Token'), 'rotated');
});

test('failed refresh preserves metadata, signals reauthentication, and returns original save error', async () => {
  await api.apiRequest('/auth/login', { method: 'POST', body: '{}' });
  const normalFetch = fetch;
  globalThis.fetch = (url, options) => new URL(url).pathname.endsWith('/auth/refresh') ? Promise.resolve(new Response('{"detail":"expired"}', { status: 401 })) : normalFetch(url, options);
  authenticated = false;
  await assert.rejects(api.apiRequest('/invoices', { method: 'POST', body: '{}' }), error => error.status === 401 && error.message === 'Session expired');
  assert.deepEqual(api.getStoredSession(), { user });
  assert.equal(api.getSessionState().reauthenticationRequired, true);
});

test('initial validation consults me even when memory metadata exists', async () => {
  await api.apiRequest('/auth/login', { method: 'POST', body: '{}' });
  calls.length = 0;
  await api.validateSession();
  assert.ok(calls.some(c => c.path === '/auth/me'));
});

test('logout waits for server revocation; failed revocation keeps the session', async () => {
  await api.apiRequest('/auth/login', { method: 'POST', body: '{}' });
  const normalFetch = fetch;
  globalThis.fetch = (url, options) => new URL(url).pathname.endsWith('/auth/logout') ? Promise.reject(new TypeError('Failed to fetch')) : normalFetch(url, options);
  await assert.rejects(api.logoutSession(), error => error.status === 0);
  assert.deepEqual(api.getStoredSession(), { user });
  globalThis.fetch = normalFetch;
  await api.logoutSession();
  assert.equal(api.getStoredSession(), null);
  assert.equal(api.getSessionState().explicitlyLoggedOut, true);
  assert.ok(calls.find(c => c.path === '/auth/logout').headers.get('X-CSRF-Token'));
});

test('CSRF acquisition network failure provides actionable login error', async () => {
  let firstUrl;
  globalThis.fetch = async url => { firstUrl ??= url; throw new TypeError('Failed to fetch'); };
  await assert.rejects(api.apiRequest('/auth/login', { method: 'POST', body: '{}' }), error => error.status === 0 && error.message.includes('Login could not reach') && !error.message.includes('Failed to fetch'));
  assert.ok(firstUrl.endsWith('/auth/csrf'));
});

test('passphrases use NFC Unicode character count and preserve spaces without composition rules', async () => {
  const source = await readFile(new URL('../app/lib/auth.ts', import.meta.url), 'utf8').catch(() => 'export const normalizePassphrase = value => value;');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  const auth = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
  assert.throws(() => auth.normalizePassphrase('short'), /6–10/);
  assert.equal(auth.normalizePassphrase('Qz7!xR'), 'Qz7!xR');
  assert.equal(auth.normalizePassphrase('Qz7!xR2@t9'), 'Qz7!xR2@t9');
  assert.equal(auth.normalizePassphrase('x y z!'), 'x y z!');
  assert.equal(auth.normalizePassphrase('cafe\u0301 x'), 'café x');
  assert.equal(auth.normalizePassphrase('😀'.repeat(10)), '😀'.repeat(10));
  assert.throws(() => auth.normalizePassphrase('😀'.repeat(11)), /6–10/);
});

test('legacy MFA metadata does not block a Staff login', async () => {
  const normalFetch = fetch;
  globalThis.fetch = (url, options) => new URL(url).pathname.endsWith('/auth/login') ? Promise.resolve(new Response(JSON.stringify({ user: { ...user, role: 'staff', mfa_required: false, mfa_verified: false } }))) : normalFetch(url, options);
  await api.apiRequest('/auth/login', { method: 'POST', body: '{}' });
  assert.equal(api.isSessionReady(), true);
  const source = await readFile(new URL('../app/lib/auth.ts', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  const auth = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
  assert.equal(auth.authStep({ ...user, role: 'staff', mfa_required: true, mfa_verified: false }), 'ready');
});

test('current-session deletion clears local metadata only after successful revocation', async () => {
  await api.apiRequest('/auth/login', { method: 'POST', body: '{}' });
  await api.revokeSession('current-session', true);
  assert.equal(api.getStoredSession(), null);
  const deletion = calls.find(c => c.path === '/auth/sessions/current-session');
  assert.equal(deletion.method, 'DELETE');
  assert.equal(deletion.headers.get('X-CSRF-Token'), 'session');
});

test('CSRF rejection renews and replays the same save once, without an auth refresh', async () => {
  await api.apiRequest('/auth/login', { method: 'POST', body: '{}' });
  const normalFetch = fetch;
  const saves = [];
  globalThis.fetch = async (url, options) => {
    if (new URL(url).pathname.endsWith('/invoices')) {
      saves.push({ ...options, headers: new Headers(options.headers) });
      if (saves.length === 1) { csrf = 'renewed'; return new Response('{"detail":"CSRF validation failed; retry after renewing the security token"}', { status: 403 }); }
    }
    return normalFetch(url, options);
  };
  await api.apiRequest('/invoices', { method: 'POST', body: '{"draft":"preserved"}', headers: { 'Idempotency-Key': 'same-save' } });
  assert.equal(saves.length, 2);
  assert.ok(saves.every(save => save.body === '{"draft":"preserved"}' && save.headers.get('Idempotency-Key') === 'same-save'));
  assert.equal(saves[1].headers.get('X-CSRF-Token'), 'renewed');
  assert.equal(refreshCount, 0);
  let attempts = 0;
  globalThis.fetch = (url, options) => new URL(url).pathname.endsWith('/invoices') ? (attempts++, Promise.resolve(new Response('{"detail":"CSRF validation failed"}', { status: 403 }))) : normalFetch(url, options);
  await assert.rejects(api.apiRequest('/invoices', { method: 'POST', body: '{}' }), error => error.status === 403);
  assert.equal(attempts, 2);
});

test('legacy password upgrade does not require an authenticator', async () => {
  const source = await readFile(new URL('../app/lib/auth.ts', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  const auth = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
  assert.equal(auth.authStep({ ...user, password_change_required: true, mfa_verified: false }), 'password');
  assert.equal(auth.authStep({ ...user, password_change_required: true, mfa_verified: true }), 'password');
});

test('CSRF failure on refresh itself renews and retries once without a request body', async () => {
  const normalFetch = fetch;
  let rejected = false;
  const attempts = [];
  globalThis.fetch = async (url, options) => {
    if (new URL(url).pathname.endsWith('/auth/refresh')) {
      attempts.push({ ...options, headers: new Headers(options.headers) });
      if (!rejected) { rejected = true; csrf = 'fresh-refresh'; return new Response('{"detail":"CSRF validation failed"}', { status: 403 }); }
    }
    return normalFetch(url, options);
  };
  const result = await api.apiRequest('/customers');
  assert.deepEqual(result, { ok: true });
  assert.equal(attempts.length, 2);
  assert.equal(attempts[1].headers.get('X-CSRF-Token'), 'fresh-refresh');
  assert.ok(attempts.every(attempt => attempt.body === undefined));
});

test('bad MFA code or current password preserves a valid session and is never replayed', async () => {
  await api.apiRequest('/auth/login', { method: 'POST', body: '{}' });
  const normalFetch = fetch;
  for (const path of ['/auth/mfa/verify', '/auth/password', '/auth/mfa/enroll', '/auth/mfa/recovery-codes', '/users/2/mfa-reset']) {
    let attempts = 0;
    globalThis.fetch = (url, options) => new URL(url).pathname.endsWith(path) ? (attempts++, Promise.resolve(new Response('{"detail":"Incorrect code or current password"}', { status: 401 }))) : normalFetch(url, options);
    await assert.rejects(api.apiRequest(path, { method: 'POST', body: '{"code":"bad"}' }), error => error.status === 401 && error.message === 'Incorrect code or current password');
    assert.equal(attempts, 1);
    assert.equal(refreshCount, 0);
    assert.equal(api.getSessionState().reauthenticationRequired, false);
    assert.deepEqual(api.getStoredSession(), { user });
  }
});
