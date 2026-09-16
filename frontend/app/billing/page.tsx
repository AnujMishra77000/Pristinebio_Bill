"use client";

import Link from "next/link";

import { AppShell } from "@/app/components/AppShell";
import { AuthGate } from "@/app/components/AuthGate";

const cards = [
  {
    title: "Purchase Order",
    href: "/purchase-orders",
    eyebrow: "Buy raw material",
    description: "Create POs for suppliers/raw-material providers. Supplier and item details entered manually are saved for future use.",
    action: "Create purchase order",
  },
  {
    title: "Sales Invoice",
    href: "/invoices",
    eyebrow: "Sell to vendors",
    description: "Create sales invoice drafts for customers/vendors, preview backend totals, then submit for approval and PDF generation.",
    action: "Create sales invoice",
  },
];

export default function BillingPage() {
  return (
    <AuthGate>
      <AppShell>
        <div className="mx-auto max-w-6xl px-5 py-8 sm:px-8 lg:px-10 lg:py-10">
          <section>
            <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-[#6f8fe8]">Billing desk</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-ink sm:text-[40px]">Choose document type</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500 sm:text-[15px]">
              Start from blank entry boxes. Use saved parties/products only when you want to reuse data from previous orders.
            </p>
          </section>

          <section className="mt-8 grid gap-5 md:grid-cols-2">
            {cards.map((card) => (
              <Link key={card.href} href={card.href} className="group rounded-[26px] border border-slate-200/80 bg-white p-6 shadow-panel transition hover:-translate-y-0.5 hover:border-[#6f8fe8]">
                <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-[#6f8fe8]">{card.eyebrow}</p>
                <h2 className="mt-4 text-2xl font-semibold tracking-tight text-ink">{card.title}</h2>
                <p className="mt-3 text-sm leading-6 text-slate-500">{card.description}</p>
                <span className="mt-8 inline-flex rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-white transition group-hover:bg-[#243653]">{card.action}</span>
              </Link>
            ))}
          </section>
        </div>
      </AppShell>
    </AuthGate>
  );
}
