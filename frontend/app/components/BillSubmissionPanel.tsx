"use client";

import Link from "next/link";
import type { useBillSubmission } from "@/app/lib/useBillSubmission";

type Controller = Omit<ReturnType<typeof useBillSubmission>, "restore" | "amend">;
export function BillSubmissionPanel({ submission, ready, documentNumber }: { submission: Controller; ready: boolean; documentNumber?: string | null }) {
  const waiting = submission.document && ["pending_approval", "approved"].includes(submission.document.status) && !submission.finalReady;
  return <section aria-label="Bill submission" className="ui-panel mt-6 min-w-0">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 className="ui-section-title">Bill submission</h2><p className="mt-2 text-sm text-slate">Preview your bill here. Edit the same draft if needed, then Confirm.</p></div>
      <p className="text-xs font-semibold text-peacock">{submission.document ? `${documentNumber ?? `Draft #${submission.document.id}`} · ${submission.document.status.replaceAll("_", " ")} · Revision ${submission.document.version}` : "New draft"}</p>
    </div>
    {documentNumber && <h3 className="mt-3 font-semibold text-ink">{documentNumber}</h3>}
    <p className="mt-3 text-xs text-slate">{submission.document && !submission.unsaved ? "Saved" : "Unsaved changes"}{submission.review && !submission.finalReady ? " · Draft PDF under review" : ""}</p>
    <div className="mt-4 flex flex-wrap gap-2">
      <button className="ui-button" type="button" disabled={submission.busy || (!ready && !submission.document)} onClick={() => void submission.preview()}>Preview</button>
      <button className="ui-button" type="button" disabled={submission.busy || !submission.canEdit} onClick={() => { submission.edit(); window.setTimeout(() => document.querySelector<HTMLFormElement>("form[data-bill-entry]")?.querySelector<HTMLElement>("input:not([readonly]), textarea:not([readonly]), select")?.focus(), 0); }}>Edit</button>
      <button className="ui-button" type="button" disabled={submission.busy || !submission.finalReady} onClick={() => void submission.download()}>Download</button>
      <button className="ui-button" type="button" disabled={submission.busy || !submission.finalReady} onClick={() => void submission.print()}>Print</button>
      <button className="ui-button-primary" type="button" disabled={submission.busy || !submission.canConfirm || submission.finalReady} onClick={() => void submission.confirm()}>Confirm</button>
      {waiting && <button className="ui-button" type="button" disabled={submission.busy} onClick={() => void submission.checkApproval()}>Check approval</button>}
      {(submission.startNew || submission.finalReady || submission.document?.status === "pending_approval") && <button className="ui-button" type="button" disabled={submission.busy} onClick={() => submission.startNew ? submission.startNew() : window.location.reload()}>Start new bill</button>}
    </div>
    {submission.busy && <p className="mt-3 text-sm text-slate" aria-live="polite">Processing this bill…</p>}
    {submission.error && <div className="ui-alert mt-4 border-red-200 bg-red-50 text-red-800" role="alert">{submission.error}{/revision|another user/i.test(submission.error) && <Link className="ml-2 underline" href="/approvals" target="_blank" rel="noopener noreferrer">Open Approval workspace</Link>}</div>}
    {submission.message && <p className="mt-4 text-sm text-peacock" role="status">{submission.message}</p>}
    {!submission.finalReady && <p className="mt-3 text-xs text-slate">Download and Print unlock after confirmation and required approval. Staff and creator-Managers cannot approve their own bills.</p>}
    {submission.review && <div className="mt-5 overflow-hidden rounded-xl border border-line bg-warm">
      <p className="border-b border-line px-4 py-2 text-xs font-semibold text-ink">{submission.review.final ? "Confirmed PDF" : "Draft PDF · not finalized"}</p>
      <iframe key={submission.review.url} className="block h-[75vh] min-h-[420px] w-full border-0" data-ready={submission.frameReady} ref={submission.frameRef} onLoad={() => submission.frameLoaded(submission.review!.url)} title="Bill PDF preview" src={`${submission.review.url}#toolbar=0`} />
    </div>}
  </section>;
}
