import type { ReactNode } from "react";

import { AppShell } from "@/app/components/AppShell";

const metrics = [
  {
    label: "Draft invoices",
    value: "18",
    detail: "+4 from last week",
    tone: "mint",
    icon: "↗",
  },
  {
    label: "Awaiting approval",
    value: "07",
    detail: "3 need attention today",
    tone: "lilac",
    icon: "◷",
  },
  {
    label: "Approved this month",
    value: "₹12,84,650",
    detail: "+18.6% vs last month",
    tone: "peach",
    icon: "₹",
  },
  {
    label: "Active customers",
    value: "42",
    detail: "Single seller profile",
    tone: "sky",
    icon: "●",
  },
];

const recentActivity = [
  {
    initials: "RK",
    name: "Rohit Kumar",
    action: "created invoice draft",
    reference: "INV-2026-0048",
    time: "12 min ago",
    color: "bg-[#dff8ee] text-[#24735b]",
  },
  {
    initials: "SA",
    name: "Sana Ahmed",
    action: "approved invoice",
    reference: "INV-2026-0046",
    time: "48 min ago",
    color: "bg-[#ece8ff] text-[#6352b6]",
  },
  {
    initials: "MP",
    name: "Meera Patel",
    action: "updated customer details",
    reference: "Apex Labs",
    time: "2 hrs ago",
    color: "bg-[#fff0df] text-[#b46b22]",
  },
];

function MetricCard({
  label,
  value,
  detail,
  tone,
  icon,
}: {
  label: string;
  value: string;
  detail: string;
  tone: string;
  icon: string;
}) {
  const toneClass = {
    mint: "bg-mint text-[#24735b]",
    lilac: "bg-lilac text-[#6352b6]",
    peach: "bg-peach text-[#b46b22]",
    sky: "bg-[#e3f2ff] text-[#3674a9]",
  }[tone];

  return (
    <article className="rounded-[22px] border border-slate-200/80 bg-white p-5 shadow-panel sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <p className="text-sm font-medium text-slate-500">{label}</p>
        <span className={`flex h-9 w-9 items-center justify-center rounded-xl text-sm font-bold ${toneClass}`}>
          {icon}
        </span>
      </div>
      <p className="mt-5 text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">{value}</p>
      <p className="mt-2 text-xs font-medium text-slate-400">{detail}</p>
    </article>
  );
}

function SectionHeading({ eyebrow, title, action }: { eyebrow: string; title: string; action?: ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-4">
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-400">{eyebrow}</p>
        <h2 className="mt-2 text-lg font-semibold tracking-tight text-ink">{title}</h2>
      </div>
      {action}
    </div>
  );
}

export default function HomePage() {
  return (
    <AppShell>
      <div className="mx-auto max-w-[1440px] px-5 py-8 sm:px-8 lg:px-10 lg:py-10">
          <section id="dashboard" className="flex flex-col justify-between gap-6 sm:flex-row sm:items-end">
            <div>
              <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-[#6f8fe8]">Overview</p>
              <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-ink sm:text-[40px]">Billing command center</h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500 sm:text-[15px]">
                Keep a clear view of drafts, approvals, and billing activity across your single-company workspace.
              </p>
            </div>
            <div className="flex items-center gap-2 self-start rounded-full border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-500 shadow-sm sm:self-auto">
              <span className="h-2 w-2 rounded-full bg-[#45b991]" />
              Single company
              <span className="ml-1 text-slate-300">⌄</span>
            </div>
          </section>

          <section className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Billing summary">
            {metrics.map((metric) => (
              <MetricCard key={metric.label} {...metric} />
            ))}
          </section>

          <section className="mt-8 grid gap-6 xl:grid-cols-[1.4fr_1fr]">
            <article className="rounded-[22px] border border-slate-200/80 bg-white p-5 shadow-panel sm:p-6">
              <SectionHeading
                eyebrow="Workflow pulse"
                title="Invoice activity"
                action={<span className="rounded-lg bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-500">This month · ⌄</span>}
              />
              <div className="mt-8 flex h-52 items-end gap-2 sm:gap-4">
                {[38, 52, 44, 67, 58, 76, 70, 88, 63, 82, 73, 94].map((height, index) => (
                  <div key={index} className="flex h-full flex-1 flex-col items-center justify-end gap-3">
                    <div className="w-full rounded-t-lg bg-[#dfe8ff] transition-colors hover:bg-[#9eb7ff]" style={{ height: `${height}%` }} />
                    <span className="text-[10px] font-medium text-slate-400">{["W1", "W2", "W3", "W4"][index % 4]}</span>
                  </div>
                ))}
              </div>
              <div className="mt-8 flex flex-wrap gap-x-6 gap-y-3 border-t border-slate-100 pt-5 text-xs text-slate-500">
                <span className="flex items-center gap-2"><i className="h-2 w-2 rounded-full bg-[#9eb7ff]" />Approved invoices</span>
                <span className="flex items-center gap-2"><i className="h-2 w-2 rounded-full bg-[#dff8ee]" />Drafts created</span>
              </div>
            </article>

            <article className="rounded-[22px] border border-slate-200/80 bg-white p-5 shadow-panel sm:p-6">
              <SectionHeading
                eyebrow="To review"
                title="Approval queue"
                action={<span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#fff0df] text-xs font-bold text-[#b46b22]">07</span>}
              />
              <div className="mt-7 space-y-4">
                {[
                  ["INV-2026-0047", "Apex Laboratories", "₹2,48,000", "2h ago"],
                  ["INV-2026-0045", "Nova Research", "₹1,84,650", "5h ago"],
                  ["INV-2026-0042", "Helix Chemicals", "₹96,400", "Yesterday"],
                ].map(([reference, customer, amount, time]) => (
                  <div key={reference} className="flex items-center gap-3 rounded-2xl border border-slate-100 p-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#f3f5ff] text-xs font-bold text-[#6276bd]">↗</span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-semibold text-ink">{reference}</p>
                      <p className="mt-1 truncate text-[11px] text-slate-400">{customer} · {time}</p>
                    </div>
                    <p className="shrink-0 text-xs font-semibold text-ink">{amount}</p>
                  </div>
                ))}
              </div>
              <button className="mt-6 w-full rounded-xl border border-slate-200 py-3 text-xs font-semibold text-slate-500 transition-colors hover:border-ink hover:text-ink">View approval queue</button>
            </article>
          </section>

          <section className="mt-8 rounded-[22px] border border-slate-200/80 bg-white p-5 shadow-panel sm:p-6">
            <SectionHeading
              eyebrow="Workspace activity"
              title="Recent activity"
              action={<button className="text-xs font-semibold text-[#6276bd] hover:text-ink">View all activity →</button>}
            />
            <div className="mt-6 divide-y divide-slate-100">
              {recentActivity.map((item) => (
                <div key={item.reference} className="flex items-center gap-3 py-4 first:pt-0 last:pb-0 sm:gap-4">
                  <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${item.color}`}>{item.initials}</span>
                  <p className="min-w-0 flex-1 truncate text-sm text-slate-500"><span className="font-semibold text-ink">{item.name}</span> {item.action} <span className="font-medium text-[#6276bd]">{item.reference}</span></p>
                  <span className="shrink-0 text-xs text-slate-400">{item.time}</span>
                </div>
              ))}
            </div>
          </section>
      </div>
    </AppShell>
  );
}
