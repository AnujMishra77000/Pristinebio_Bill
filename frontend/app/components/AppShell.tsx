"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { clearSession } from "@/app/lib/api";

const navigation = [
  { label: "Dashboard", href: "/", icon: "▦" }, { label: "Billing", href: "/billing", icon: "▤" }, { label: "Sales Invoices", href: "/invoices", icon: "₹" }, { label: "Purchase Orders", href: "/purchase-orders", icon: "⇄" }, { label: "Customers", href: "/customers", icon: "♧" },
  { label: "Products", href: "/products", icon: "◇" }, { label: "Seller profile", href: "/branches", icon: "⌂" }, { label: "Users", href: "/users", icon: "◉" },
  { label: "Bank accounts", href: "/bank-accounts", icon: "▥" }, { label: "Transporters", href: "/transporters", icon: "↗" },
  { label: "Terms", href: "/terms", icon: "≡" }, { label: "Settings", href: "/settings", icon: "⚙" },
];

function BrandMark() { return <div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-[14px] bg-ink text-sm font-bold text-white shadow-sm">PB</span><div><p className="text-[15px] font-bold tracking-tight text-ink">Pristine Bio</p><p className="mt-0.5 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-400">Billing workspace</p></div></div>; }

function Navigation({ mobile = false }: { mobile?: boolean }) {
  const pathname = usePathname();
  return <nav className={mobile ? "flex gap-2 overflow-x-auto pb-1" : "space-y-1.5"} aria-label="Primary navigation">{navigation.map((item) => {
    const active = pathname === item.href;
    return <Link key={item.href} href={item.href} className={["group flex items-center gap-3 rounded-xl text-sm font-medium transition-colors", mobile ? "whitespace-nowrap px-3 py-2" : "px-3.5 py-3", active ? "bg-ink text-white shadow-[0_8px_18px_rgba(20,33,61,0.14)]" : "text-slate-500 hover:bg-slate-100 hover:text-ink"].join(" ")}><span className={active ? "text-white/80" : "text-slate-400 group-hover:text-ink"}>{item.icon}</span>{item.label}</Link>;
  })}</nav>;
}

function LogoutButton() {
  return <button aria-label="Log out" className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-500 transition-colors hover:border-[#6f8fe8] hover:text-ink" onClick={clearSession} type="button">Log out</button>;
}

export function AppShell({ children }: { children: ReactNode }) {
  return <main className="min-h-screen bg-[#f7f8fb] text-ink"><aside className="fixed inset-y-0 left-0 z-20 hidden w-72 flex-col border-r border-slate-200/80 bg-white px-6 py-7 lg:flex"><BrandMark /><div className="mt-14 flex-1"><p className="mb-4 px-3.5 text-[10px] font-bold uppercase tracking-[0.22em] text-slate-400">Workspace</p><Navigation /></div><div className="rounded-2xl bg-[#f0f4ff] p-4"><div className="flex items-center gap-2 text-xs font-semibold text-[#516bb1]"><span className="h-2 w-2 rounded-full bg-[#6f8fe8]" />Separated billing flow</div><p className="mt-2 text-xs leading-5 text-slate-500">Purchase raw materials with POs and sell finished/raw goods through sales invoices.</p></div></aside><div className="lg:pl-72"><header className="border-b border-slate-200/80 bg-white/90 px-5 py-4 backdrop-blur sm:px-8 lg:px-10"><div className="flex items-center justify-between gap-5"><div className="lg:hidden"><BrandMark /></div><div className="hidden lg:block"><p className="text-sm font-medium text-slate-400">Wednesday, 23 August 2026</p><p className="mt-1 text-sm font-semibold text-ink">Good morning, Anuj</p></div><div className="flex items-center gap-3 sm:gap-5"><div className="hidden text-right sm:block"><p className="text-xs font-semibold text-ink">Pristine Biopharma</p><p className="mt-1 text-[11px] text-slate-400">Single-company mode</p></div><LogoutButton /><span className="flex h-10 w-10 items-center justify-center rounded-full bg-[#dbe6ff] text-xs font-bold text-[#536fb8]">AM</span></div></div><div className="mt-5 lg:hidden"><Navigation mobile /></div></header>{children}</div></main>;
}
