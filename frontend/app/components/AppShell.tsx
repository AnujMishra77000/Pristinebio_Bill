"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { logoutSession } from "@/app/lib/api";
import { AppIcon } from "./AppIcon";
import { useSessionState } from "./AuthGate";
import { NavigationMenu } from "./NavigationMenu";
import { Reauthentication } from "./Reauthentication";

export function BrandMark() {
  return <Link href="/" aria-label="Pristine Biopharma home" className="flex min-w-0 items-center gap-2.5 sm:gap-3">
    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-peacock-deep text-sm font-bold tracking-tight text-lime shadow-sm">PB</span>
    <span className="min-w-0"><span className="block text-sm font-bold tracking-tight text-ink sm:text-[15px]">Pristine Biopharma</span><span className="mt-0.5 block text-[9px] font-semibold uppercase tracking-[0.18em] text-slate sm:text-[10px]">Billing workspace</span></span>
  </Link>;
}

function ExploreMenu() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const trigger = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const element = dialog.current;
    if (open) { element?.showModal(); window.setTimeout(() => element?.querySelector<HTMLInputElement>("input")?.focus(), 0); }
    else if (element?.open) element.close();
  }, [open]);

  function close() { setOpen(false); setQuery(""); trigger.current?.focus(); }

  return <>
    <button ref={trigger} className="ui-button-primary gap-2.5 !bg-peacock-deep hover:!bg-peacock" type="button" aria-haspopup="dialog" aria-expanded={open} aria-controls="explore-dialog" onClick={() => { setQuery(""); setOpen(true); }}>
      <AppIcon name="dashboard" size={17} /><span>Explore</span><AppIcon name="chevron-down" size={14} className="hidden sm:block" />
    </button>
    <dialog ref={dialog} id="explore-dialog" aria-labelledby="explore-title" className="explore-dialog" onCancel={(event) => { event.preventDefault(); close(); }} onClose={() => setOpen(false)}>
      <div className="border-b border-line p-5 sm:p-6">
        <div className="mb-5 flex items-start justify-between gap-4"><div><p className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald">Your workspace</p><h2 id="explore-title" className="mt-1 text-xl font-semibold tracking-tight text-ink">Explore features</h2></div><button type="button" aria-label="Close Explore" className="rounded-lg p-2 text-slate hover:bg-warm" onClick={close}><AppIcon name="close" size={20} /></button></div>
        <label className="flex items-center gap-3 rounded-xl border border-line bg-warm px-3.5 focus-within:border-emerald focus-within:ring-2 focus-within:ring-emerald/10"><AppIcon name="search" size={18} className="shrink-0 text-emerald" /><span className="sr-only">Find a feature</span><input className="h-11 w-full border-0 bg-transparent text-sm text-ink outline-none focus-visible:outline-none" placeholder="Find invoices, customers, settings…" value={query} onChange={(event) => setQuery(event.target.value)} type="search" /></label>
      </div>
      <div className="max-h-[60dvh] overflow-y-auto overscroll-contain p-3 sm:p-5"><NavigationMenu mobile query={query} onNavigate={close} /></div>
      <div className="flex items-center justify-between border-t border-line bg-warm/70 px-6 py-3 text-[11px] text-slate"><span>Everything you need, one place.</span><span className="hidden sm:inline">Esc to close</span></div>
    </dialog>
  </>;
}

function LogoutButton() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function logout() {
    setBusy(true); setError(null);
    try { await logoutSession(); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to log out. Try again."); } finally { setBusy(false); }
  }
  return <div className="relative"><button aria-label="Log out" disabled={busy} className="flex min-h-10 items-center gap-2 rounded-xl p-2.5 text-xs font-semibold text-slate hover:bg-warm hover:text-ink" onClick={() => void logout()} type="button"><AppIcon name="logout" size={17} /><span className="hidden md:inline">{busy ? "Logging out…" : "Log out"}</span></button>{error && <p role="alert" className="absolute right-0 top-12 z-20 w-64 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-800 shadow-panel">{error}</p>}</div>;
}

export function AppShell({ children }: { children: ReactNode }) {
  const { session } = useSessionState();
  const initials = session?.user.full_name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "PB";

  return <div className="min-h-screen bg-warm text-ink">
    <a href="#workspace-content" className="fixed left-4 top-4 z-50 -translate-y-24 rounded-xl bg-peacock-deep px-4 py-3 text-sm font-semibold text-white focus:translate-y-0">Skip to content</a>
    <header className="sticky top-0 z-30 border-b border-line bg-white/95 backdrop-blur-xl">
      <div className="mx-auto flex min-h-[76px] max-w-[1760px] items-center justify-between gap-3 px-4 sm:gap-6 sm:px-7 lg:px-9">
        <BrandMark />
        <div className="ml-auto flex items-center gap-2 sm:gap-4">
          <div className="hidden items-center gap-3 border-r border-line pr-5 lg:flex"><span className="flex h-9 w-9 items-center justify-center rounded-full border border-line bg-warm-green text-xs font-bold text-peacock">{initials}</span><div className="max-w-44"><p className="truncate text-xs font-semibold text-ink">{session?.user.full_name ?? "Billing account"}</p><p className="mt-0.5 text-[11px] capitalize text-slate">{session?.user.role ?? ""}</p></div></div>
          <LogoutButton /><ExploreMenu />
        </div>
      </div>
    </header>
    <main id="workspace-content" tabIndex={-1} className="min-w-0 outline-none" aria-label="Billing workspace">{children}</main>
    <Reauthentication />
  </div>;
}
