"use client";

import Link from "next/link";
import { Fragment, useEffect, useRef, useState, type FormEvent } from "react";

import { AppShell } from "./AppShell";
import { AuthGateStatus, useAuthStatus, useSessionState } from "./AuthGate";
import { AppIcon } from "./AppIcon";
import { PageHeader } from "./PageHeader";
import { ApiError, apiRequest, fetchFileBlob } from "@/app/lib/api";
import { billRegisters, billEditHref, billNumber, billDate, billParty, displayBillDate, type BillRegisterKind, type RegisteredBill } from "@/app/lib/billRegisters";
import type { RegisterPage } from "@/app/lib/types";
import { invalidateInvoiceEntrySession, invalidatePurchaseOrderEntrySession } from "@/app/lib/invoiceEntrySession";

const PAGE_SIZE = 10;
const message = (error: unknown) => {
  if (error instanceof ApiError && error.detail && typeof error.detail === "object" && "message" in error.detail && typeof error.detail.message === "string") return error.detail.message;
  if (error instanceof ApiError && error.status === 409) return "This bill changed. Retry to view its latest revision.";
  return error instanceof Error ? error.message : "Unable to load bills. Please retry.";
};
const statusLabel = (value: string) => value.replaceAll("_", " ");
const validVersion = (bill: RegisteredBill) => Number.isSafeInteger(bill.version) && bill.version > 0;

export function BillRegisterActions({ kind, bill, isAdmin, onView, onDelete }: {
  kind?: BillRegisterKind; bill: RegisteredBill; isAdmin: boolean;
  onView: (button: HTMLButtonElement) => void; onDelete: (button: HTMLButtonElement) => void;
}) {
  const editHref = billEditHref(kind ?? ("invoice_number" in bill ? bill.document_type === "reagent" ? "reagent" : "sales" : bill.document_type === "reagent" ? "reagent-purchase" : "purchase"), bill);
  return <div className="flex flex-wrap gap-2">
    <button type="button" aria-label={`View bill ${billNumber(bill)}`} className="ui-button" onClick={(event) => onView(event.currentTarget)}>View</button>
    {editHref && <Link aria-label={`Edit bill ${billNumber(bill)}`} className="ui-button" href={editHref}>Edit</Link>}
    {isAdmin && <button type="button" aria-label={`Delete bill ${billNumber(bill)}`} disabled={!validVersion(bill)} title={!validVersion(bill) ? "Reload the register to obtain a valid bill version." : undefined} className="ui-button border-red-200 text-red-800" onClick={(event) => onDelete(event.currentTarget)}>Delete</button>}
  </div>;
}

export function BillDeleteDialog({ kind, bill, canDelete, onCancel, onDeletionPending, onDeleted }: {
  kind: BillRegisterKind; bill: RegisteredBill; canDelete: boolean;
  onCancel: () => void; onDeletionPending: () => void; onDeleted: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const busyRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const number = billNumber(bill);
  const config = billRegisters[kind];
  const allowed = canDelete && validVersion(bill) && bill.document_type === config.documentType && confirmation === number;

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    input.current?.focus();
    return () => { element?.close(); };
  }, []);

  function cancel() {
    if (busyRef.current) return;
    dialog.current?.close();
    onCancel();
  }

  async function remove(event: FormEvent) {
    event.preventDefault();
    if (!allowed || busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(null);
    try {
      await apiRequest<void>(`/${config.collection}/${bill.id}`, {
        method: "DELETE", body: JSON.stringify({ expected_version: bill.version, confirmation_number: confirmation, document_type: config.documentType }),
      });
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 503 && failure.detail && typeof failure.detail === "object" && "code" in failure.detail && failure.detail.code === "pdf_cleanup_pending") {
        if (config.collection === "invoices") invalidateInvoiceEntrySession(bill.id);
        else invalidatePurchaseOrderEntrySession(bill.id);
        onDeletionPending();
      }
      setError(message(failure));
      return;
    } finally { busyRef.current = false; setBusy(false); }
    if (config.collection === "invoices") invalidateInvoiceEntrySession(bill.id);
    else invalidatePurchaseOrderEntrySession(bill.id);
    onDeleted();
  }

  return <dialog ref={dialog} aria-labelledby="delete-bill-title" aria-describedby="delete-bill-warning" aria-busy={busy}
    className="ui-panel fixed inset-0 m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-lg overflow-y-auto backdrop:bg-black/50"
    onCancel={(event) => { event.preventDefault(); cancel(); }}>
    <form onSubmit={remove}>
      <h2 id="delete-bill-title" className="ui-section-title">Permanently delete bill</h2>
      <p className="mt-3 break-words font-semibold text-ink">{number}</p>
      <p id="delete-bill-warning" className="mt-3 text-sm text-red-800">This permanently deletes the bill and its stored PDF. This cannot be undone. Bills linked to payments or integrations cannot be deleted. After deletion, its number can be reused for a new bill.</p>
      <label className="ui-label mt-5">Full bill number<input ref={input} className="ui-input" value={confirmation} disabled={busy} autoComplete="off" spellCheck={false} aria-describedby="delete-bill-hint" onChange={(event) => { setConfirmation(event.target.value); setError(null); }} /></label>
      <p id="delete-bill-hint" className="mt-2 text-xs text-slate">Type the full bill number exactly as shown above to confirm.</p>
      {error && <p role="alert" className="ui-alert mt-4 border-red-200 bg-red-50 text-red-800 break-words">{error}</p>}
      {!canDelete && <p role="alert" className="ui-field-error mt-4">An active Admin session is required to delete bills.</p>}
      <div className="mt-5 flex flex-wrap justify-end gap-3">
        <button type="button" className="ui-button" disabled={busy} onClick={cancel}>Cancel</button>
        <button type="submit" className="ui-button border-red-200 bg-red-50 text-red-800" disabled={busy || !allowed}>{busy ? "Deleting…" : "Permanently delete"}</button>
      </div>
    </form>
  </dialog>;
}

function BillPdfView({ kind, id, onClose }: { kind: BillRegisterKind; id: number; onClose: () => void }) {
  const config = billRegisters[kind];
  const [bill, setBill] = useState<RegisteredBill | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const stored = bill?.pdf_storage_key && ["approved", "pdf_generated", "closed", "cancelled"].includes(bill.status);

  useEffect(() => { heading.current?.focus({ preventScroll: true }); heading.current?.scrollIntoView({ block: "nearest" }); }, []);
  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    const controller = new AbortController();
    setUrl(null); setBill(null); setError(null);
    void (async () => {
      try {
        const document = await apiRequest<RegisteredBill>(`/${config.collection}/${id}`, { signal: controller.signal, cache: "no-store" });
        if (!active) return;
        if (document.document_type !== config.documentType) throw new Error("This bill belongs to a different register.");
        setBill(document);
        const finalPdf = document.pdf_storage_key && ["approved", "pdf_generated", "closed", "cancelled"].includes(document.status);
        const blob = await fetchFileBlob(`/${config.collection}/${id}/${finalPdf ? "pdf" : "preview-pdf"}`, finalPdf ? { signal: controller.signal } : { method: "POST", body: JSON.stringify({ expected_version: document.version }), signal: controller.signal });
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      } catch (requestError) { if (active) setError(message(requestError)); }
    })();
    return () => { active = false; controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [config, id, attempt]);

  return <section aria-label="Bill PDF view" className="ui-panel mt-5">
    <div className="ui-section-heading"><div className="min-w-0"><h2 ref={heading} tabIndex={-1} className="ui-section-title break-words">{bill ? billNumber(bill) : "Bill PDF view"}</h2>{bill && <p className="mt-2 text-xs text-slate">{displayBillDate(billDate(bill))} · {billParty(bill)} · <span className="capitalize">{statusLabel(bill.status)}</span> · ₹ {bill.final_total}</p>}</div><button className="ui-button" type="button" onClick={onClose}><AppIcon name="close" size={16} />Close view</button></div>
    {bill && <div className="mb-4"><span className="ui-badge">{stored ? "Saved PDF" : bill.status === "draft" || bill.status === "amendment_pending" ? "Draft preview" : "Unstored preview"}</span>{billEditHref(kind, bill) && <Link className="ui-button ml-3" href={billEditHref(kind, bill)!}>Edit this draft</Link>}{!stored && <p className="mt-2 text-xs text-slate">Read-only preview of the current revision. Viewing does not approve, finalize or alter this bill.</p>}</div>}
    {error ? <div role="alert" className="ui-alert border-red-200 bg-red-50 text-red-800">{error}<button className="ui-button ml-3" type="button" onClick={() => setAttempt((value) => value + 1)}>Retry PDF</button></div> : url ? <iframe title={`PDF of ${bill ? billNumber(bill) : "bill"}`} src={url} className="h-[75dvh] min-h-[420px] w-full rounded-xl border border-line bg-warm" /> : <p role="status" className="py-8 text-sm text-slate">Loading PDF…</p>}
  </section>;
}

export function BillRegisterPage({ kind }: { kind: BillRegisterKind }) {
  const config = billRegisters[kind];
  const authStatus = useAuthStatus();
  const sessionState = useSessionState();
  const isAdmin = authStatus === "authenticated" && !sessionState.reauthenticationRequired && sessionState.session?.user.is_active === true && sessionState.session.user.role === "admin";
  const [mode, setMode] = useState("all");
  const [singleDate, setSingleDate] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [filterError, setFilterError] = useState<string | null>(null);
  const [dates, setDates] = useState({ from: "", to: "" });
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<RegisterPage<RegisteredBill> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewId, setViewId] = useState<number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<RegisteredBill | null>(null);
  const [deletedMessage, setDeletedMessage] = useState("");
  const deleteButton = useRef<HTMLButtonElement | null>(null);
  const deletionStatus = useRef<HTMLParagraphElement>(null);
  const focusDeletionStatus = useRef(false);
  const viewButton = useRef<HTMLButtonElement | null>(null);
  const pageStatus = useRef<HTMLParagraphElement>(null);
  const focusPageStatus = useRef(false);

  useEffect(() => {
    if (!loading && focusDeletionStatus.current) {
      focusDeletionStatus.current = false;
      deletionStatus.current?.focus({ preventScroll: true });
    }
    if (!loading && result && focusPageStatus.current) {
      focusPageStatus.current = false;
      pageStatus.current?.focus({ preventScroll: true });
    }
  }, [loading, result]);

  useEffect(() => {
    if (authStatus !== "authenticated") return;
    let active = true;
    const controller = new AbortController();
    setLoading(true); setError(null); setResult(null);
    const query = new URLSearchParams({ document_type: config.documentType, sort: "date_desc", page: String(page), page_size: String(PAGE_SIZE) });
    if (dates.from) query.set("date_from", dates.from);
    if (dates.to) query.set("date_to", dates.to);
    void apiRequest<RegisterPage<RegisteredBill>>(`/${config.collection}/register?${query}`, { signal: controller.signal, cache: "no-store" })
      .then((data) => {
        if (!active) return;
        const last = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
        if (page > last) { setPage(last); return; }
        setResult(data);
      })
      .catch((requestError) => { if (active) setError(message(requestError)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [authStatus, config, dates, page, attempt]);

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    if (mode === "date" && !singleDate) { setFilterError("Choose a bill date"); return; }
    if (mode === "range" && (!from || !to)) { setFilterError("Choose both start and end dates"); return; }
    if (mode === "range" && from > to) { setFilterError("End date must be on or after start date"); return; }
    focusPageStatus.current = false;
    setFilterError(null); setViewId(null); setPage(1);
    setDates(mode === "date" ? { from: singleDate, to: singleDate } : mode === "range" ? { from, to } : { from: "", to: "" });
  }
  function clearFilters() {
    focusPageStatus.current = false;
    setMode("all"); setSingleDate(""); setFrom(""); setTo(""); setDates({ from: "", to: "" }); setFilterError(null); setPage(1); setViewId(null);
  }
  const applied = !dates.from ? "All dates" : dates.from === dates.to ? displayBillDate(dates.from) : `${displayBillDate(dates.from)} – ${displayBillDate(dates.to)}`;

  return <AuthGateStatus status={authStatus}><AppShell><div className="workspace-page">
    <PageHeader icon={config.icon} eyebrow="Bill register" title={config.title} description="Saved bills organized by bill date, newest first. Drafts retain their workflow status." action={<Link className="ui-button" href="/"><AppIcon name="dashboard" size={16} />Dashboard</Link>} />
    {deleteTarget && <BillDeleteDialog key={deleteTarget.id} kind={kind} bill={deleteTarget} canDelete={isAdmin}
      onCancel={() => { setDeleteTarget(null); deleteButton.current?.focus(); }}
      onDeletionPending={() => { setViewId((current) => current === deleteTarget.id ? null : current); }}
      onDeleted={() => {
        const releasedNumber = "invoice_number" in deleteTarget ? deleteTarget.invoice_number : deleteTarget.purchase_order_number;
        setDeletedMessage(`Permanently deleted ${billNumber(deleteTarget)}.${releasedNumber ? " Its number is now available for a new bill." : ""}`);
        setViewId((current) => current === deleteTarget.id ? null : current);
        setDeleteTarget(null); focusDeletionStatus.current = true;
        setAttempt((value) => value + 1);
      }} />}
    {deletedMessage && <p ref={deletionStatus} tabIndex={-1} role="status" className="ui-alert mt-5 break-words">{deletedMessage}</p>}
    <section className="ui-panel mt-5" aria-label="Filter bill dates">
      <form onSubmit={applyFilters} className="flex flex-wrap items-end gap-4" noValidate>
        <label className="ui-label w-full sm:w-48">Date filter<select aria-label="Date filter" className="ui-input" value={mode} onChange={(event) => { setMode(event.target.value); setFilterError(null); }}><option value="all">All dates</option><option value="date">Single date</option><option value="range">Custom range</option></select></label>
        {mode === "date" && <label className="ui-label w-full sm:w-48">Bill date<input type="date" className="ui-input" value={singleDate} onChange={(event) => { setSingleDate(event.target.value); setFilterError(null); }} aria-invalid={Boolean(filterError)} aria-describedby={filterError ? "date-filter-error" : undefined} /></label>}
        {mode === "range" && <><label className="ui-label w-full sm:w-48">From date<input type="date" className="ui-input" value={from} onChange={(event) => { setFrom(event.target.value); setFilterError(null); }} aria-invalid={Boolean(filterError)} aria-describedby={filterError ? "date-filter-error" : undefined} /></label><label className="ui-label w-full sm:w-48">To date<input type="date" className="ui-input" value={to} onChange={(event) => { setTo(event.target.value); setFilterError(null); }} aria-invalid={Boolean(filterError)} aria-describedby={filterError ? "date-filter-error" : undefined} /></label></>}
        <button type="submit" className="ui-button-primary">Apply filters</button><button type="button" className="ui-button" onClick={clearFilters}>Clear filters</button>
        {filterError && <p id="date-filter-error" role="alert" className="ui-field-error w-full">{filterError}</p>}
      </form>
      <p role="status" className="mt-4 text-xs text-slate">Applied: <span className="font-semibold text-peacock">{applied}</span>{result && ` · ${result.total} ${result.total === 1 ? "bill" : "bills"}`}</p>
    </section>
    {viewId !== null && <BillPdfView key={viewId} kind={kind} id={viewId} onClose={() => { setViewId(null); viewButton.current?.focus(); }} />}
    <section aria-label="Saved bills" className="ui-panel mt-5 !p-0" aria-busy={loading}>
      {loading ? <p role="status" className="p-6 text-sm text-slate">Loading bills…</p> : error ? <div className="p-6"><p role="alert" className="ui-alert border-red-200 bg-red-50 text-red-800">{error}</p><button type="button" className="ui-button mt-3" onClick={() => setAttempt((value) => value + 1)}>Retry loading</button></div> : result && result.items.length ? <>
        <div className="ui-table-wrap"><table className="ui-table min-w-[720px]"><caption className="sr-only">{config.title}, ordered newest first by bill date</caption><thead><tr><th scope="col">Bill date</th><th scope="col">Bill number</th><th scope="col">{config.collection === "invoices" ? "Buyer" : "Purchaser / Supplier"}</th><th scope="col" className="text-right">Total</th><th scope="col">Status</th><th scope="col">Actions</th></tr></thead><tbody>{result.items.map((bill, index) => <Fragment key={bill.id}>
          {(index === 0 || billDate(bill) !== billDate(result.items[index - 1])) && <tr><th scope="rowgroup" colSpan={6} className="border-b border-line bg-warm-green/60 px-4 py-2 text-left text-xs font-semibold text-peacock">{displayBillDate(billDate(bill))}</th></tr>}
          <tr><td className="whitespace-nowrap">{displayBillDate(billDate(bill))}</td><td className="max-w-72 break-words font-semibold">{billNumber(bill)}</td><td className="max-w-72 break-words">{billParty(bill)}</td><td className="whitespace-nowrap text-right font-semibold tabular-nums">₹ {bill.final_total}</td><td><span className="ui-badge capitalize">{statusLabel(bill.status)}</span></td><td><BillRegisterActions kind={kind} bill={bill} isAdmin={isAdmin} onView={(button) => { viewButton.current = button; setViewId(bill.id); }} onDelete={(button) => { deleteButton.current = button; setDeletedMessage(""); setDeleteTarget(bill); }} /></td></tr>
        </Fragment>)}</tbody></table></div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-5 py-4"><p ref={pageStatus} tabIndex={-1} role="status" className="text-xs text-slate">Page {page} of {Math.max(1, Math.ceil(result.total / PAGE_SIZE))} · {result.total} bills</p><div className="flex gap-2"><button aria-label="Previous page" type="button" disabled={page === 1} className="ui-button" onClick={() => { focusPageStatus.current = true; setViewId(null); setPage((value) => value - 1); }}>Previous</button><button aria-label="Next page" type="button" disabled={page * PAGE_SIZE >= result.total} className="ui-button" onClick={() => { focusPageStatus.current = true; setViewId(null); setPage((value) => value + 1); }}>Next</button></div></div>
      </> : <div className="ui-empty"><AppIcon name={config.icon} size={28} /><p>{dates.from ? "No bills match these dates." : "No saved bills yet."}</p></div>}
    </section>
  </div></AppShell></AuthGateStatus>;
}
