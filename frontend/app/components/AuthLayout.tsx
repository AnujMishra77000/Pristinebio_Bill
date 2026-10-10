import type { ReactNode } from "react";

export function AuthLayout({ eyebrow, title, description, children, footer }: { eyebrow: string; title: string; description: string; children: ReactNode; footer: ReactNode }) {
  return (
    <main className="min-h-screen bg-warm text-ink lg:grid lg:grid-cols-[0.95fr_1.05fr]">
      <aside className="relative overflow-hidden bg-peacock-deep px-6 py-8 text-white sm:px-10 lg:flex lg:min-h-screen lg:flex-col lg:justify-between lg:px-14 lg:py-12">
        <div aria-hidden="true" className="pointer-events-none absolute -bottom-48 -right-48 h-[36rem] w-[36rem] rounded-full border border-white/10" />
        <div aria-hidden="true" className="pointer-events-none absolute -bottom-32 -right-32 h-[28rem] w-[28rem] rounded-full border border-white/10" />
        <div className="relative flex items-center gap-3">
          <span aria-hidden="true" className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-white/20 bg-white/10 text-lg font-semibold tracking-tight">PB</span>
          <div><p className="text-lg font-semibold tracking-tight">Pristine Biopharma</p><p className="mt-0.5 text-[11px] font-medium uppercase tracking-[0.2em] text-white/70">Billing workspace</p></div>
        </div>
        <div className="relative my-16 hidden max-w-lg lg:block">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-white/70">Your daily operations, together</p>
          <p className="mt-6 text-5xl font-semibold leading-[1.12] tracking-[-0.04em] xl:text-6xl">Clarity for every<br />billing day.</p>
          <p className="mt-6 max-w-sm text-base leading-7 text-white/70">One workspace for your invoices, approvals, and customer receipts.</p>
          <div className="mt-10 grid grid-cols-3 gap-4 border-t border-white/15 pt-6 text-sm">
            <p><span className="mb-2 block text-xs text-white/50">01</span>Prepare</p>
            <p><span className="mb-2 block text-xs text-white/50">02</span>Review</p>
            <p><span className="mb-2 block text-xs text-white/50">03</span>Reconcile</p>
          </div>
        </div>
        <p className="relative hidden text-xs text-white/60 lg:block">Controlled access. Clear accountability.</p>
      </aside>
      <div className="flex min-w-0 items-center justify-center px-5 py-10 sm:px-10 sm:py-14">
        <div className="w-full max-w-lg">
          <header className="mb-8">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-peacock">{eyebrow}</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.035em] sm:text-4xl">{title}</h1>
            <p className="mt-3 text-sm leading-6 text-slate">{description}</p>
          </header>
          <div className="ui-panel min-w-0 shadow-panel">{children}</div>
          <footer className="mt-6 text-sm leading-6 text-slate">{footer}</footer>
        </div>
      </div>
    </main>
  );
}
