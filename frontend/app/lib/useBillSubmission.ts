"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, apiRequest, createIdempotencyKey, downloadFile, fetchFileBlob, getStoredSession } from "./api";
import { useInvoiceEntryRef, useInvoiceEntryValue, type InvoiceEntrySession } from "./invoiceEntrySession";
import type { BillCorrection } from "./types";

type BillDocument = {
  id: number;
  version: number;
  status: string;
  pdf_storage_key: string | null;
  created_by_id?: number;
  submitted_by_id?: number | null;
  submitted_revision?: number | null;
  approved_revision?: number | null;
  correction?: BillCorrection | null;
};
type Options<T> = {
  collection: "/invoices" | "/purchase-orders";
  payload: object;
  updateField?: "domestic_details" | "reagent_details";
  validate: () => string | null;
  onFailure?: (failure: unknown) => void;
  onCreated?: (document: T) => Promise<void>;
  onReturned?: () => void;
  entrySession?: InvoiceEntrySession;
  onStartNew?: () => void;
};
const editable = (document: BillDocument) => ["draft", "amendment_pending"].includes(document.status);
const approved = (document: BillDocument) => ["approved", "pdf_generated", "closed"].includes(document.status);

/** One memory-only entry session; persisted drafts use one ID and optimistic versions. */
export function useBillSubmission<T extends BillDocument>(options: Options<T>) {
  const entry = options.entrySession;
  const [document, setDocument] = useInvoiceEntryValue<T | null>(entry, "submission.document", null);
  const [busy, setBusy] = useInvoiceEntryValue(entry, "submission.busy", false);
  const [review, setReview] = useState<{ url: string; signature: string; version: number; final: boolean } | null>(null);
  const [error, setError] = useInvoiceEntryValue(entry, "submission.error", "");
  const [message, setMessage] = useInvoiceEntryValue(entry, "submission.message", "");
  const [correctionReason, updateCorrectionReason] = useInvoiceEntryValue(entry, "submission.correctionReason", "");
  const reasonRef = useInvoiceEntryRef(entry, "submission.correctionReason", "");
  const [savedSignature, setSavedSignature] = useInvoiceEntryValue(entry, "submission.savedSignature", "");
  const savedSignatureRef = useInvoiceEntryRef(entry, "submission.savedSignature", "");
  const documentRef = useInvoiceEntryRef<T | null>(entry, "submission.document", null);
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const signature = JSON.stringify(document?.correction ? { ...options.payload, correction_reason: correctionReason.trim() } : options.payload);
  const signatureRef = useRef(signature);
  signatureRef.current = signature;
  const intent = useInvoiceEntryRef<{ signature: string; key: string; uncertain?: boolean } | null>(entry, "submission.intent", null);
  const busyRef = useInvoiceEntryRef(entry, "submission.busy", false);
  const baselineNext = useRef(false);
  const [restoreEpoch, setRestoreEpoch] = useState(0);
  const objectUrl = useRef<string | null>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);
  const printQueued = useRef<string | null>(null);
  const loadedUrl = useRef<string | null>(null);
  const [frameReady, setFrameReady] = useState(false);
  const mounted = useRef(true);
  const active = () => !entry || entry.active;
  function ensureActive() { if (!active()) throw new Error("This entry session has ended."); }

  function clearReview() {
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = null;
    printQueued.current = null;
    loadedUrl.current = null; setFrameReady(false);
    setReview(null);
  }
  function remember(next: T) {
    if (documentRef.current?.correction && !next.correction && approved(next) && typeof window !== "undefined" && window.location) {
      const query = new URLSearchParams(window.location.search);
      query.delete("correction");
      window.history.replaceState(null, "", `${window.location.pathname}${query.size ? `?${query}` : ""}`);
    }
    documentRef.current = next; setDocument(next);
  }
  function setCorrectionReason(reason: string) {
    const current = documentRef.current;
    if (!current?.correction || !editable(current) || busyRef.current) return;
    reasonRef.current = reason; updateCorrectionReason(reason);
  }
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; if (objectUrl.current) URL.revokeObjectURL(objectUrl.current); };
  }, []);
  useEffect(() => {
    if (baselineNext.current) { baselineNext.current = false; savedSignatureRef.current = signature; setSavedSignature(signature); }
    if (review && !review.final && review.signature !== signature) clearReview();
    // Review URLs and payload signatures deliberately remain memory-only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, restoreEpoch]);

  function restore(next: T) {
    const reason = next.correction?.reason ?? "";
    reasonRef.current = reason; updateCorrectionReason(reason);
    clearReview(); remember(next); entry?.write("submission.completed", false); baselineNext.current = true; setRestoreEpoch((value) => value + 1); setError("");
  }
  function reset() {
    if (busyRef.current) return;
    if (typeof window !== "undefined" && window.location) {
      const query = new URLSearchParams(window.location.search);
      query.delete(optionsRef.current.collection === "/invoices" ? "invoice" : "order");
      query.delete("correction");
      window.history.replaceState(null, "", `${window.location.pathname}${query.size ? `?${query}` : ""}`);
    }
    reasonRef.current = ""; updateCorrectionReason("");
    clearReview(); documentRef.current = null; setDocument(null); setSavedSignature("");
    savedSignatureRef.current = "";
    intent.current = null; setError(""); setMessage("");
    entry?.write("submission.completed", false);
  }
  function fail(failure: unknown) {
    const text = failure instanceof Error ? failure.message : "The request failed. Your entered details have been retained.";
    setError(`${text}${failure instanceof ApiError && failure.status === 409 && (failure.detail as { code?: string })?.code === "version_conflict" ? " Your fields are retained. Review the latest revision before retrying; do not overwrite another user's changes." : ""}`);
    if (mounted.current) optionsRef.current.onFailure?.(failure);
  }
  async function run(work: () => Promise<void>) {
    if (!active() || busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(""); setMessage("");
    try { await work(); } catch (failure) { if (active() && (mounted.current || entry)) fail(failure); }
    finally { busyRef.current = false; if (mounted.current || entry) setBusy(false); }
  }
  async function persist(): Promise<T> {
    ensureActive();
    let current = documentRef.current;
    const body = signatureRef.current;
    if (current && !editable(current)) return current;
    if (current?.correction && !reasonRef.current.trim()) throw new Error("Enter a correction reason before saving or previewing this correction.");
    const validation = optionsRef.current.validate();
    if (validation) throw new Error(validation);
    if (!current && intent.current?.uncertain && intent.current.signature !== body) {
      // Resolve a possibly committed POST with its original key/body before
      // treating changed input as a PATCH. Never issue a second creation intent.
      const original = intent.current;
      current = await apiRequest<T>(optionsRef.current.collection, { method: "POST", headers: { "Idempotency-Key": original.key }, body: original.signature });
      ensureActive();
      remember(current); savedSignatureRef.current = original.signature; setSavedSignature(original.signature); intent.current = null;
    }
    if (current && body === savedSignatureRef.current && (!current.correction || current.correction.reason === reasonRef.current.trim())) return current;
    const payload = JSON.parse(body) as Record<string, unknown>;
    let result: T;
    if (current) {
      let update: object;
      const { correction_reason: _reason, ...normalPayload } = payload;
      void _reason;
      if (current.correction && optionsRef.current.collection === "/invoices") delete normalPayload.invoice_number_suffix;
      if (optionsRef.current.updateField) update = { expected_version: current.version, [optionsRef.current.updateField]: normalPayload };
      else {
        const { document_type: _documentType, ...fields } = normalPayload;
        void _documentType;
        update = { ...fields, expected_version: current.version, ...(fields.buyer && fields.buyer_customer_id == null ? { buyer_customer_id: null } : {}), consignee_customer_id: null, consignee: fields.consignee ?? null };
      }
      if (current.correction) update = { ...update, correction_reason: reasonRef.current.trim() };
      result = await apiRequest<T>(`${optionsRef.current.collection}/${current.id}${current.correction ? "/correction" : ""}`, { method: "PATCH", body: JSON.stringify(update) });
    } else {
      if (intent.current?.signature !== body) intent.current = { signature: body, key: createIdempotencyKey() };
      try {
        result = await apiRequest<T>(optionsRef.current.collection, { method: "POST", headers: { "Idempotency-Key": intent.current.key }, body });
      } catch (failure) {
        if (active() && intent.current) intent.current.uncertain = failure instanceof ApiError && (failure.status === 0 || failure.status >= 500);
        throw failure;
      }
    }
    ensureActive();
    remember(result); savedSignatureRef.current = body; setSavedSignature(body); intent.current = null;
    if (!current && mounted.current && optionsRef.current.onCreated) {
      try { await optionsRef.current.onCreated(result); }
      catch { setMessage("Draft saved. Saved-data choices could not refresh; your bill is safe."); }
    }
    return result;
  }
  async function display(next: T, final: boolean) {
    ensureActive();
    if (!mounted.current) return;
    const body = savedSignatureRef.current;
    const path = `${optionsRef.current.collection}/${next.id}${!final && next.correction ? "/correction" : ""}`;
    const blob = await fetchFileBlob(`${path}/${final ? "pdf" : "preview-pdf"}`, final ? {} : { method: "POST", body: JSON.stringify({ expected_version: next.version }) });
    if (!mounted.current || !active()) return;
    if (!final && signatureRef.current !== body) {
      clearReview(); throw new Error("Entry details changed while saved data refreshed. Your draft is safe; Preview again to save and review these changes.");
    }
    clearReview();
    const url = URL.createObjectURL(blob);
    objectUrl.current = url;
    setReview({ url, signature: body, version: next.version, final });
  }
  async function save() {
    await run(async () => {
      const next = await persist();
      setMessage(editable(next) ? "Draft saved. Preview and confirm when ready." : "This bill is submitted or finalized. Its financial data is read-only.");
    });
  }
  async function preview() {
    await run(async () => {
      const next = await persist();
      await display(next, approved(next) && Boolean(next.pdf_storage_key));
      setMessage(approved(next) && next.pdf_storage_key ? "Final bill PDF ready." : "Review this draft PDF, then Edit or Confirm. It is not yet a finalized bill.");
    });
  }
  async function finish(next: T) {
    ensureActive();
    if (!approved(next)) {
      setMessage("Submitted for approval. Your bill is saved; download and print become available after authorized approval.");
      return;
    }
    if (!next.pdf_storage_key) {
      // Staff cannot generate invoice PDFs; the authorized approver must do it.
      if (optionsRef.current.collection === "/invoices" && getStoredSession()?.user.role === "staff") {
        setMessage("Approved. Ask the Manager/Admin to generate the final PDF; check approval here when ready.");
        return;
      }
      next = await apiRequest<T>(`${optionsRef.current.collection}/${next.id}/generate-pdf`, { method: "POST" });
      ensureActive();
      remember(next);
    }
    await display(next, true);
    // Keep Download/Print on this page; its next mount starts a fresh entry.
    entry?.write("submission.completed", true);
    setMessage("Bill confirmed. The final PDF is ready to download and print.");
  }
  async function transition(previous: T, operation: "submit" | "approve"): Promise<T> {
    ensureActive();
    const path = `${optionsRef.current.collection}/${previous.id}${previous.correction ? "/correction" : ""}`;
    try {
      const next = await apiRequest<T>(`${path}/${operation}`, { method: "POST", body: JSON.stringify({ expected_version: previous.version }) });
      ensureActive(); return next;
    } catch (failure) {
      // A lost response may follow a committed transition. Only adopt the exact
      // reviewed revision, never a newer editable draft or unrelated approval.
      if (!active() || !(failure instanceof ApiError) || (failure.status !== 0 && failure.status < 500)) throw failure;
      let latest: T;
      try { latest = await apiRequest<T>(path); } catch { throw failure; }
      ensureActive();
      const committed = operation === "submit"
        ? latest.submitted_revision === previous.version && (latest.status === "pending_approval" || approved(latest))
        : approved(latest) && latest.approved_revision === previous.submitted_revision && latest.submitted_revision === previous.submitted_revision;
      if (!committed) throw failure;
      return latest;
    }
  }
  async function confirm() {
    await run(async () => {
      let next = documentRef.current;
      if (!next) throw new Error("Preview the bill before confirming it.");
      if (next.correction && (!review || review.version !== next.version || review.signature !== signatureRef.current)) throw new Error("Preview the correction PDF before confirming this revision.");
      if (editable(next)) {
        if (!review || review.version !== next.version || review.signature !== signatureRef.current) throw new Error("Preview your latest changes before confirming this revision.");
        next = await transition(next, "submit");
        remember(next);
      }
      if (next.status === "pending_approval") {
        const user = getStoredSession()?.user;
        const mayApprove = user?.role === "admin" || (user?.role === "manager" && next.created_by_id != null && next.created_by_id !== user.id && next.submitted_by_id !== user.id);
        if (mayApprove) {
          next = await transition(next, "approve");
          remember(next);
        }
      }
      await finish(next);
    });
  }
  async function checkApproval() {
    await run(async () => {
      const previous = documentRef.current;
      if (!previous) return;
      const latest = await apiRequest<T>(`${optionsRef.current.collection}/${previous.id}${previous.correction ? "/correction" : ""}`);
      ensureActive();
      if (editable(latest)) throw new Error("The bill was returned or changed. Open its latest revision in the Approval workspace before editing; your entered fields remain here.");
      if (!approved(latest) && latest.status !== "pending_approval") throw new Error(`This bill is ${latest.status.replaceAll("_", " ")}. Review its details in the Approval workspace.`);
      if (latest.correction && latest.version !== previous.version) { clearReview(); throw new Error("The submitted correction revision changed. Reload the latest revision and review its PDF; your fields are retained."); }
      remember(latest); await finish(latest);
    });
  }
  const reviewer = () => ["admin", "manager"].includes(getStoredSession()?.user.role ?? "");
  const canReturnCorrection = Boolean(document?.correction && document.status === "pending_approval" && reviewer());
  async function returnCorrection(reason: string) {
    let returned = false;
    await run(async () => {
      const previous = documentRef.current;
      if (!reviewer() || !previous?.correction || previous.status !== "pending_approval") throw new Error("Only Manager/Admin can return a pending correction.");
      if (!reason.trim()) throw new Error("Enter a reviewer reason before returning this correction.");
      const next = await apiRequest<T>(`${optionsRef.current.collection}/${previous.id}/correction/return`, { method: "POST", body: JSON.stringify({ expected_version: previous.version, reason: reason.trim() }) });
      ensureActive(); restore(next); returned = true;
      setMessage("Correction returned to draft. Review the requested changes before resubmitting.");
    });
    if (returned && active() && mounted.current) optionsRef.current.onReturned?.();
  }
  async function amend(reason: string, hydrate?: (next: T) => void) {
    await run(async () => {
      const previous = documentRef.current;
      if (optionsRef.current.collection !== "/purchase-orders" || previous?.status !== "approved" || !reason.trim()) throw new Error("Only approved purchase orders can request a reasoned amendment.");
      const next = await apiRequest<T>(`/purchase-orders/${previous.id}/amend`, { method: "POST", body: JSON.stringify({ expected_version: previous.version, reason: reason.trim() }) });
      restore(next); hydrate?.(next); setMessage("Amendment opened. Edit the same order and submit the revised PDF for approval.");
    });
  }
  const finalReady = Boolean(document && approved(document) && document.pdf_storage_key);
  async function download() {
    await run(async () => {
      const next = documentRef.current;
      if (!next || !approved(next) || !next.pdf_storage_key) throw new Error("Confirm and complete approval before downloading.");
      await downloadFile(`${optionsRef.current.collection}/${next.id}/pdf`, `${optionsRef.current.collection.slice(1)}-${next.id}.pdf`);
      setMessage("Final PDF downloaded.");
    });
  }
  function printFrame() {
    try {
      const frame = frameRef.current?.contentWindow;
      if (!frame) throw new Error("Preview the final PDF before printing.");
      frame.focus(); frame.print(); setMessage("Print dialog requested for the final PDF.");
    } catch (failure) { fail(failure); }
  }
  async function print() {
    if (busyRef.current) return;
    if (review?.final && finalReady) {
      if (loadedUrl.current === review.url) printFrame();
      else { printQueued.current = review.url; setMessage("Loading the final PDF before opening its print dialog…"); }
      return;
    }
    await run(async () => {
      const next = documentRef.current;
      if (!next || !approved(next) || !next.pdf_storage_key) throw new Error("Confirm and complete approval before printing.");
      await display(next, true); printQueued.current = objectUrl.current;
    });
  }
  function frameLoaded(url: string) {
    if (objectUrl.current !== url) return;
    loadedUrl.current = url; setFrameReady(true);
    if (printQueued.current === url) { printQueued.current = null; printFrame(); }
  }
  function edit() { clearReview(); setError(""); setMessage("Editing the same draft. Preview your changes again before confirming."); }
  const unsaved = !document || signature !== savedSignature || Boolean(document.correction && editable(document) && (!document.correction.reason.trim() || document.correction.reason !== correctionReason.trim()));
  const locked = busy || Boolean(review && !review.final) || Boolean(document && !editable(document));
  const reviewed = Boolean(review && review.version === document?.version && review.signature === signature);
  const canConfirm = Boolean(document && (!document.correction || reviewed) && (editable(document) ? reviewed : document.status === "pending_approval" || approved(document)));
  const startNew = options.onStartNew ? () => {
    if (busyRef.current) return;
    if (unsaved && !window.confirm("Discard this entry and start a new bill? Saved server drafts will not be deleted.")) return;
    reset();
    options.onStartNew?.();
  } : undefined;
  return { document, busy, review, error, message, unsaved, locked, finalReady, canConfirm, canEdit: Boolean(document && editable(document)), correctionReason, setCorrectionReason, canReturnCorrection, returnCorrection, save, preview, confirm, edit, download, print, checkApproval, restore, reset, frameRef, frameLoaded, frameReady, amend, startNew };
}
