"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell } from "@/app/components/AppShell";
import { AuthGateStatus, useAuthStatus } from "@/app/components/AuthGate";
import { AppIcon } from "@/app/components/AppIcon";
import { BillingDocumentActions } from "@/app/components/BillingDocumentActions";
import { PageHeader } from "@/app/components/PageHeader";
import { ApiError, apiRequest } from "@/app/lib/api";
import { billRegisters } from "@/app/lib/billRegisters";
import type { DashboardSummary } from "@/app/lib/types";

export default function HomePage() {
  const authStatus = useAuthStatus();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (authStatus !== "authenticated") return;
    let active = true;
    setError(null);
    void apiRequest<DashboardSummary>("/dashboard")
      .then((data) => { if (active) setSummary(data); })
      .catch((requestError: unknown) => { if (active) setError(requestError instanceof ApiError ? requestError.message : "Unable to load dashboard data."); });
    return () => { active = false; };
  }, [authStatus, retry]);

  return <AuthGateStatus status={authStatus}><AppShell><div className="workspace-page">
    <PageHeader icon="dashboard" eyebrow="Overview" title="Billing command center" description="Create a bill or explore your saved documents by date." />
    <BillingDocumentActions />
    <section aria-label="Saved bill registers" className="mt-8">
      <div className="mb-4"><h2 className="ui-section-title">Your bill registers</h2><p className="mt-1 text-sm text-slate">All saved bills, including drafts. Choose a register to filter dates and view a bill.</p></div>
      {error && <div className="ui-alert mb-4 border-red-200 bg-red-50 text-red-800" role="alert">{error}<button className="ui-button ml-3" type="button" onClick={() => setRetry((value) => value + 1)}>Retry loading</button></div>}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{Object.values(billRegisters).map((register) => <Link key={register.href} href={register.href} className="ui-panel group relative overflow-hidden transition hover:-translate-y-0.5 hover:border-emerald focus-visible:ring-2 focus-visible:ring-emerald">
        <div className="flex items-center justify-between gap-3"><span className="text-base font-semibold text-ink">{register.label}</span><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-peacock-deep text-lime"><AppIcon name={register.icon} size={21} /></span></div>
        <p className="mt-6 text-4xl font-semibold tabular-nums tracking-tight text-peacock-deep">{summary ? summary[register.countKey] : <span aria-label={error ? "Count unavailable" : "Loading count"} className="text-slate">—</span>}{" "}<span className="ml-2 text-xs font-normal tracking-normal text-slate">bills</span></p>
        <span className="mt-5 flex items-center justify-between border-t border-line pt-4 text-xs font-semibold text-peacock">View date-wise register<AppIcon name="arrow-right" size={17} className="transition-transform group-hover:translate-x-1" /></span>
      </Link>)}</div>
    </section>
  </div></AppShell></AuthGateStatus>;
}
