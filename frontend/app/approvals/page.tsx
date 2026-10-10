"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell } from "@/app/components/AppShell";
import { AppIcon } from "@/app/components/AppIcon";
import { AuthGateStatus, useAuthStatus } from "@/app/components/AuthGate";
import { PageHeader } from "@/app/components/PageHeader";
import { ApiError, apiRequest } from "@/app/lib/api";
import type { Invoice, PurchaseOrder } from "@/app/lib/types";

type DocumentType = "invoice" | "purchase-order";

export default function ApprovalsPage() {
  const authStatus = useAuthStatus();
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  async function load() {
    setError(null);
    try {
      const [invoiceQueue, poQueue] = await Promise.all([
        apiRequest<Invoice[]>("/invoices/approval-queue"),
        apiRequest<PurchaseOrder[]>("/purchase-orders/approval-queue"),
      ]);
      setInvoices(invoiceQueue);
      setPurchaseOrders(poQueue);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to load approval work.");
    }
  }

  useEffect(() => { if (authStatus === "authenticated") void load(); }, [authStatus]);

  async function approve(type: DocumentType, documentId: number, version: number) {
    setBusy(documentId); setError(null);
    try {
      await apiRequest(`/${type === "invoice" ? "invoices" : "purchase-orders"}/${documentId}/approve`, {
        method: "POST", body: JSON.stringify({ expected_version: version }),
      });
      await load();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Approval could not be completed. Reload and review the document.");
    } finally { setBusy(null); }
  }

  async function returnInvoice(documentId: number, version: number, reason: string) {
    setBusy(documentId); setError(null);
    try {
      await apiRequest(`/invoices/${documentId}/return-for-correction`, {
        method: "POST", body: JSON.stringify({ expected_version: version, reason }),
      });
      await load();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "The invoice could not be returned for correction.");
    } finally { setBusy(null); }
  }

  return <AuthGateStatus status={authStatus}><AppShell><main className="workspace-page">
    <PageHeader icon="approvals" eyebrow="Controlled decisions" title="Approval workspace" description="Review the exact submitted revision before approving. Staff and Manager submissions require independent approval; Admins may approve their own documents." action={<span className="ui-badge"><AppIcon name="security" size={15} />Admin self-approval enabled</span>} />
    {error && <p className="ui-alert mt-6 border-red-200 bg-red-50 text-red-800" role="alert">{error}</p>}
    <section className="mt-6 grid gap-6 xl:grid-cols-2"><Queue title="Sales invoices" empty="No invoice approvals are waiting." items={invoices} type="invoice" busy={busy} onApprove={approve} onReturn={returnInvoice} /><Queue title="Purchase orders" empty="No purchase-order approvals are waiting." items={purchaseOrders} type="purchase-order" busy={busy} onApprove={approve} /></section>
  </main></AppShell></AuthGateStatus>;
}

function Queue({ title, empty, items, type, busy, onApprove, onReturn }: { title: string; empty: string; items: (Invoice | PurchaseOrder)[]; type: DocumentType; busy: number | null; onApprove: (type: DocumentType, id: number, version: number) => Promise<void>; onReturn?: (id: number, version: number, reason: string) => Promise<void>; }) {
  return <section className="ui-panel"><div className="ui-section-heading"><h2 className="ui-section-title">{title}</h2><span className="ui-badge">{items.length} waiting</span></div>{items.length === 0 ? <div className="ui-empty"><AppIcon name="check" size={24} className="text-emerald" /><span>{empty}</span></div> : <div className="space-y-3">{items.map((item) => <ApprovalCard busy={busy === item.id} item={item} key={item.id} onApprove={() => onApprove(type, item.id, item.version)} onReturn={onReturn ? (reason) => onReturn(item.id, item.version, reason) : undefined} type={type} />)}</div>}</section>;
}

function ApprovalCard({ item, type, busy, onApprove, onReturn }: { item: Invoice | PurchaseOrder; type: DocumentType; busy: boolean; onApprove: () => Promise<void>; onReturn?: (reason: string) => Promise<void>; }) {
  const [reason, setReason] = useState("");
  const invoice = type === "invoice" ? item as Invoice : null;
  const po = type === "purchase-order" ? item as PurchaseOrder : null;
  const label = invoice ? invoice.invoice_number ?? `Draft #${invoice.id}` : po!.purchase_order_number;
  const party = invoice ? invoice.buyer_name : po!.supplier_name;
  const detailsHref = po?.document_type === "reagent" ? `/reagent-purchase-orders?order=${po.id}` : type === "invoice" ? "/invoices" : "/purchase-orders";
  return <article className="rounded-xl border border-line bg-warm/40 p-4"><div className="flex flex-wrap items-start justify-between gap-4"><div><p className="font-semibold text-ink">{label}</p><p className="mt-1 text-sm text-slate">{party} · ₹{item.final_total}</p><p className="mt-1 text-xs text-slate">Submitted revision {item.submitted_revision ?? item.version}</p></div><div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">{onReturn && <><label className="min-w-48 flex-1"><span className="sr-only">Correction reason for {label}</span><input aria-label={`Correction reason for ${label}`} className="ui-input mt-0" onChange={(event) => setReason(event.target.value)} placeholder="Correction reason" value={reason} /></label><button className="ui-button border-amber-200 bg-amber-50 text-amber-900" disabled={busy || !reason.trim()} onClick={() => void onReturn(reason.trim())} type="button">Return</button></>}<Link className="ui-button" href={detailsHref}>Open details</Link><button className="ui-button-primary" disabled={busy} onClick={() => void onApprove()} type="button">{busy ? "Working…" : "Approve"}</button></div></div></article>;
}
