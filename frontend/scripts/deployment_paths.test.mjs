import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import ts from 'typescript';

async function load(path, env = {}) {
  const source = await readFile(new URL(path, import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  const exports = {};
  new Function('exports', 'process', compiled)(exports, { env });
  return exports;
}

test('Next.js serves the deployment under /bill while local development keeps root routes', async () => {
  const deployed = await load('../next.config.ts', { NEXT_PUBLIC_BASE_PATH: '/bill' });
  assert.equal(deployed.default.basePath, '/bill');
  assert.equal((await load('../next.config.ts')).default.basePath, '');
});

test('invitation links stay inside the billing deployment and encode the token in a fragment', async () => {
  const deployed = await load('../app/lib/auth.ts', { NEXT_PUBLIC_BASE_PATH: '/bill' });
  assert.equal(deployed.invitationUrl('https://www.pristinebiopharma.in', 'test/token+value'),
    'https://www.pristinebiopharma.in/bill/login#invite=test%2Ftoken%2Bvalue');
  const local = await load('../app/lib/auth.ts');
  assert.equal(local.invitationUrl('http://localhost:3000', 'token'), 'http://localhost:3000/login#invite=token');
});

test('login, CSRF, bill saves and PDF downloads use the /bill API with cookies', async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, ...options, headers: new Headers(options.headers) });
    if (url.endsWith('/auth/csrf')) return Response.json({ csrf_token: 'test-csrf-token' });
    if (url.endsWith('/pdf')) return new Response('%PDF-1.4 test', { headers: { 'Content-Type': 'application/pdf' } });
    return Response.json({ id: 7 });
  };
  try {
    const api = await load('../app/lib/api.ts', { NEXT_PUBLIC_API_BASE_URL: '/bill/api/v1' });
    await api.apiRequest('/auth/login', { method: 'POST', body: JSON.stringify({ email: 'test@example.com', password: 'Test12' }) });
    await api.apiRequest('/invoices', { method: 'POST', body: JSON.stringify({ invoice_number_suffix: '7' }) });
    assert.equal(await (await api.fetchFileBlob('/invoices/7/pdf')).text(), '%PDF-1.4 test');
    assert.deepEqual(calls.map(call => call.url), [
      '/bill/api/v1/auth/csrf', '/bill/api/v1/auth/login', '/bill/api/v1/invoices', '/bill/api/v1/invoices/7/pdf',
    ]);
    for (const call of calls) assert.equal(call.credentials, 'include');
    assert.equal(calls[1].headers.get('X-CSRF-Token'), 'test-csrf-token');
    assert.equal(calls[2].headers.get('X-CSRF-Token'), 'test-csrf-token');
  } finally { globalThis.fetch = originalFetch; }
});
