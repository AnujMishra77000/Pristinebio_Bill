import Link from "next/link";
import type { PendingBillCorrection } from "@/app/lib/types";

export function CorrectionQueue({ items, total }: { items: PendingBillCorrection[]; total: number }) {
  return <section aria-label="Confirmed bill corrections" className="ui-panel"><div className="ui-section-heading"><h2 className="ui-section-title">Confirmed bill corrections</h2><span className="ui-badge">{total} waiting</span></div>
    <p className="mb-4 text-sm text-slate">Open a correction to review its full details and PDF before Confirm. Approval replaces the confirmed revision.</p>
    {items.length === 0 ? <p className="ui-empty">No confirmed bill corrections are waiting.</p> : <div className="space-y-3">{items.map(item => {
      const invoice = item.collection === "invoices";
      const entry = invoice ? item.document_type === "reagent" ? "/reagent-bills" : "/invoices" : item.document_type === "reagent" ? "/reagent-purchase-orders" : "/purchase-orders";
      return <article key={`${item.collection}:${item.document_id}`} className="rounded-xl border border-line bg-warm/40 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><h3 className="font-semibold text-ink">{item.document_number}</h3><p className="mt-2 whitespace-pre-wrap break-words text-sm text-slate">{item.reason}</p><p className="mt-2 text-sm text-ink">Previous confirmed: ₹{item.previous_final_total} · Correction: ₹{item.final_total}</p><p className="mt-1 text-xs text-slate">Submitted revision {item.version}</p></div><Link className="ui-button" href={`${entry}?${invoice ? "invoice" : "order"}=${item.document_id}&correction=1`}>Review correction</Link></div></article>;
    })}</div>}
  </section>;
}
