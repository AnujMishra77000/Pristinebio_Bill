"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { AuthGate } from "@/app/components/AuthGate";
import { AppShell } from "@/app/components/AppShell";
import { ApiError, apiRequest, createIdempotencyKey } from "@/app/lib/api";

type Provider = { provider_key: string; available: boolean; environment: string; reason: string };
type Job = { id: number; invoice_id: number; provider_key: string; operation: string; status: string; attempt_count: number; max_attempts: number; external_reference: string | null; external_status: string | null; last_error_message: string | null };
type JobPage = { items: Job[]; total: number };
type Difference = { id: number; job_id: number; difference_type: string; status: string; local_status: string; details: { reason?: string } };
type DifferencePage = { items: Difference[]; total: number };

export default function IntegrationsPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [jobs, setJobs] = useState<JobPage | null>(null);
  const [differences, setDifferences] = useState<DifferencePage | null>(null);
  const [invoiceId, setInvoiceId] = useState("");
  const [providerKey, setProviderKey] = useState("client-accounting");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const createKey = useRef<string | null>(null);

  async function load() {
    const [providerData, jobData, differenceData] = await Promise.all([
      apiRequest<Provider[]>("/integrations/providers"),
      apiRequest<JobPage>("/integrations/jobs?page=1&page_size=50"),
      apiRequest<DifferencePage>("/integrations/reconciliation?page=1&page_size=50"),
    ]);
    setProviders(providerData); setJobs(jobData); setDifferences(differenceData);
  }

  useEffect(() => { void load().catch((requestError) => setError(requestError instanceof ApiError ? requestError.message : "Unable to load integration status.")); }, []);

  async function createJob(event: FormEvent) {
    event.preventDefault(); setError(null); setNotice(null);
    if (!createKey.current) createKey.current = createIdempotencyKey();
    try {
      const job = await apiRequest<Job>("/integrations/jobs", { method: "POST", headers: { "Idempotency-Key": createKey.current }, body: JSON.stringify({ invoice_id: Number(invoiceId), provider_key: providerKey, operation: "invoice_submission" }) });
      setNotice(`Job #${job.id} saved with external status: ${job.status}. No provider submission was made.`); createKey.current = null; setInvoiceId(""); await load();
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Integration job could not be saved. The same retry key is retained."); }
  }

  async function retryJob(id: number) {
    setError(null); setNotice(null);
    try { const job = await apiRequest<Job>(`/integrations/jobs/${id}/retry`, { method: "POST" }); setNotice(`Job #${job.id} is ${job.status}; attempt ${job.attempt_count}/${job.max_attempts}.`); await load(); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Retry could not be recorded."); }
  }

  async function cancelJob(id: number) {
    const reason = window.prompt("Reason for cancelling this integration job:");
    if (!reason?.trim()) return;
    setError(null); setNotice(null);
    try { await apiRequest<Job>(`/integrations/jobs/${id}/cancel`, { method: "POST", body: JSON.stringify({ reason }) }); setNotice(`Job #${id} cancelled and its reconciliation item was resolved.`); await load(); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Cancellation could not be recorded."); }
  }

  return <AuthGate><AppShell><section className="workspace-page"><div className="mb-8"><p className="text-xs font-bold uppercase tracking-[0.2em] text-[#147c86]">Integration readiness</p><h1 className="mt-2 text-3xl font-bold tracking-tight text-ink">Accounting & GST synchronization</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">External submission is separate from local approval. No provider has been configured, so this page records recoverable work without claiming GST or accounting acceptance.</p></div>
    {error && <p role="alert" className="mb-5 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}{notice && <p role="status" className="mb-5 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{notice}</p>}
    <div className="grid gap-6 xl:grid-cols-[minmax(320px,.7fr)_minmax(0,1.3fr)]"><form onSubmit={(event) => void createJob(event)} className="ui-panel"><h2 className="font-semibold text-ink">Record outbound work</h2><p className="mt-2 text-xs leading-5 text-slate-500">Use an approved invoice. The request remains idempotent if the network fails.</p><label className="mt-5 block text-xs font-semibold text-slate-500">Invoice ID<input required inputMode="numeric" value={invoiceId} onChange={(event) => setInvoiceId(event.target.value)} className="ui-input" /></label><label className="mt-4 block text-xs font-semibold text-slate-500">Provider key<input required value={providerKey} onChange={(event) => setProviderKey(event.target.value)} className="ui-input" /></label><button type="submit" className="mt-5 w-full rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-white">Create readiness job</button></form>
      <div className="space-y-6"><section className="rounded-2xl border border-amber-200 bg-amber-50 p-5"><h2 className="font-semibold text-amber-950">Provider availability</h2>{providers.map((provider) => <div key={provider.provider_key} className="mt-3 rounded-xl bg-white/70 p-3 text-sm"><p className="font-semibold text-amber-950">{provider.provider_key} · {provider.environment}</p><p className="mt-1 text-amber-900">{provider.available ? "Ready" : "Unavailable"}: {provider.reason}</p></div>)}</section>
      <section className="ui-panel"><div className="flex items-center justify-between"><h2 className="font-semibold text-ink">Outbound jobs</h2><span className="text-xs text-slate-400">{jobs?.total ?? 0} records</span></div><div className="mt-4 overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><thead><tr className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400"><th className="px-3 py-3">Job</th><th className="px-3 py-3">Invoice</th><th className="px-3 py-3">Status</th><th className="px-3 py-3">Attempts</th><th className="px-3 py-3">Action</th></tr></thead><tbody>{jobs?.items.map((job) => <tr key={job.id} className="border-b border-slate-50"><td className="px-3 py-3 font-semibold text-ink">#{job.id}<span className="block text-xs font-normal text-slate-400">{job.provider_key}</span></td><td className="px-3 py-3">#{job.invoice_id}</td><td className="px-3 py-3 capitalize">{job.status}<span className="block max-w-xs text-xs text-slate-400">{job.last_error_message}</span></td><td className="px-3 py-3">{job.attempt_count}/{job.max_attempts}</td><td className="px-3 py-3"><div className="flex gap-2">{!["accepted", "cancelled", "failed"].includes(job.status) && <button type="button" onClick={() => void retryJob(job.id)} className="rounded-lg border border-slate-200 px-2 py-1 text-xs font-semibold text-ink">Retry</button>}{job.status !== "cancelled" && job.status !== "accepted" && <button type="button" onClick={() => void cancelJob(job.id)} className="rounded-lg border border-red-200 px-2 py-1 text-xs font-semibold text-red-700">Cancel</button>}</div></td></tr>)}</tbody></table>{jobs?.items.length === 0 && <p className="py-8 text-center text-sm text-slate-500">No outbound jobs recorded.</p>}</div></section>
      <section className="ui-panel"><div className="flex items-center justify-between"><h2 className="font-semibold text-ink">Reconciliation queue</h2><span className="text-xs text-slate-400">{differences?.total ?? 0} open</span></div>{differences?.items.length ? <ul className="mt-4 divide-y divide-slate-100">{differences.items.map((difference) => <li key={difference.id} className="py-3 text-sm"><span className="font-semibold text-ink">Job #{difference.job_id}</span> · {difference.difference_type}<span className="block pt-1 text-xs text-slate-500">Local status: {difference.local_status} · {difference.details.reason}</span></li>)}</ul> : <p className="mt-4 text-sm text-slate-500">No open differences.</p>}</section></div></div></section></AppShell></AuthGate>;
}
