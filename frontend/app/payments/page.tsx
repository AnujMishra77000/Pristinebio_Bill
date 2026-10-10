"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiRequest, createIdempotencyKey } from "@/app/lib/api";
import { AuthGate } from "@/app/components/AuthGate";
import { AppShell } from "@/app/components/AppShell";

type Customer = { id: number; name: string };
type Receipt = { id: number; receipt_number: string; customer_id: number; receipt_date: string; currency: string; amount: string; allocated_amount: string; unallocated_amount: string; status: string };
type ReceiptPage = { items: Receipt[]; total: number; page: number; page_size: number };

export default function PaymentsPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [receipts, setReceipts] = useState<ReceiptPage | null>(null);
  const [customerId, setCustomerId] = useState("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  async function load() {
    const [customerData, receiptData] = await Promise.all([
      apiRequest<Customer[]>("/customers?limit=500"),
      apiRequest<ReceiptPage>("/payments/receipts?page=1&page_size=50"),
    ]);
    setCustomers(customerData.map((item) => ({ id: item.id, name: item.name })));
    setReceipts(receiptData);
  }
  useEffect(() => { void load().catch((e) => setError(e instanceof Error ? e.message : "Unable to load receivables.")); }, []);

  async function save(event: FormEvent) {
    event.preventDefault(); setError(null); setSaved(null);
    try {
      const receipt = await apiRequest<Receipt>("/payments/receipts", { method: "POST", headers: { "Idempotency-Key": createIdempotencyKey() }, body: JSON.stringify({ customer_id: Number(customerId), receipt_date: date, currency: "INR", amount }) });
      setSaved(`${receipt.receipt_number} saved. Unallocated credit: ₹${receipt.unallocated_amount}`); setAmount(""); await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Receipt could not be saved."); }
  }

  return <AuthGate><AppShell><section className="workspace-page"><div className="mb-8"><p className="text-xs font-bold uppercase tracking-[0.2em] text-[#147c86]">Receivables</p><h1 className="mt-2 text-3xl font-bold tracking-tight text-ink">Receipts & reconciliation</h1><p className="mt-2 max-w-2xl text-sm text-slate-500">Record customer receipts separately from invoices, allocate them later, and keep unallocated credit visible.</p></div><div className="grid gap-6 xl:grid-cols-[minmax(320px,.7fr)_minmax(0,1.3fr)]"><form onSubmit={(event) => void save(event)} className="ui-panel"><h2 className="font-semibold text-ink">Record receipt</h2><label className="mt-5 block text-xs font-semibold text-slate-500">Customer<select required value={customerId} onChange={(e) => setCustomerId(e.target.value)} className="ui-input"><option value="">Choose customer</option>{customers.map((customer) => <option key={customer.id} value={customer.id}>{customer.name}</option>)}</select></label><label className="mt-4 block text-xs font-semibold text-slate-500">Receipt date<input required type="date" value={date} onChange={(e) => setDate(e.target.value)} className="ui-input" /></label><label className="mt-4 block text-xs font-semibold text-slate-500">Amount (INR)<input required min="0.01" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} className="ui-input" /></label>{error && <p role="alert" className="mt-4 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}{saved && <p role="status" className="mt-4 rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{saved}</p>}<button type="submit" className="mt-5 w-full rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-white">Save receipt</button></form><div className="ui-panel"><div className="flex items-center justify-between"><h2 className="font-semibold text-ink">Receipt history</h2><span className="text-xs text-slate-400">{receipts?.total ?? 0} records</span></div><div className="mt-5 overflow-x-auto"><table className="w-full min-w-[680px] text-left text-sm"><thead><tr className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400"><th className="px-3 py-3">Receipt</th><th className="px-3 py-3">Date</th><th className="px-3 py-3">Amount</th><th className="px-3 py-3">Allocated</th><th className="px-3 py-3">Unallocated</th><th className="px-3 py-3">Status</th></tr></thead><tbody>{receipts?.items.map((item) => <tr key={item.id} className="border-b border-slate-50"><td className="px-3 py-3 font-semibold text-ink">{item.receipt_number}</td><td className="px-3 py-3 text-slate-500">{item.receipt_date}</td><td className="px-3 py-3">₹{item.amount}</td><td className="px-3 py-3">₹{item.allocated_amount}</td><td className="px-3 py-3 font-semibold text-[#11646d]">₹{item.unallocated_amount}</td><td className="px-3 py-3 capitalize text-slate-500">{item.status}</td></tr>)}</tbody></table>{receipts?.items.length === 0 && <p className="py-10 text-center text-sm text-slate-500">No receipts recorded yet.</p>}</div></div></div></section></AppShell></AuthGate>;
}
