import Link from "next/link";

import { AppIcon } from "@/app/components/AppIcon";

const documentTypes = [
  {
    title: "Sales Invoice",
    href: "/invoices",
    icon: "sales-invoice" as const,
    description: "Create a customer sales invoice.",
  },
  {
    title: "Purchase Order",
    href: "/purchase-orders",
    icon: "purchase-order" as const,
    description: "Create a purchase order for a supplier.",
  },
  {
    title: "Reagent Bill",
    href: "/reagent-bills",
    icon: "reagent" as const,
    description: "Create reagent bills with part number, GST, quantity, rate, per-unit and discount percentage fields.",
  },
  {
    title: "Reagent Purchase Order",
    href: "/reagent-purchase-orders",
    icon: "reagent-purchase-order" as const,
    description: "Order reagents with manufacturers, article numbers and reagent pricing.",
  },
];

export function BillingDocumentActions() {
  return (
    <section aria-label="Choose a bill type" className="mt-7">
      <div className="mb-4">
        <h2 className="text-lg font-semibold tracking-tight text-ink">Start a new document</h2>
        <p className="mt-1 text-sm text-slate">Choose a bill type to open its dedicated creation page.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {documentTypes.map((document) => (
          <Link key={document.href} href={document.href} className="group flex min-h-28 items-center gap-4 rounded-2xl border border-peacock-deep/10 bg-gradient-to-br from-peacock-deep to-peacock px-5 py-5 text-white shadow-[0_12px_28px_rgba(19,47,64,0.18)] transition duration-200 hover:-translate-y-1 hover:shadow-[0_18px_34px_rgba(19,47,64,0.26)] focus-visible:outline focus-visible:outline-3 focus-visible:outline-offset-4 focus-visible:outline-emerald">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-white/20 bg-white/10 text-lime shadow-inner">
              <AppIcon name={document.icon} size={23} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-base font-semibold tracking-tight">{document.title}</span>
              <span className="mt-1 block text-xs leading-5 text-white/75">{document.description}</span>
            </span>
            <AppIcon className="shrink-0 text-white/75 transition-transform group-hover:translate-x-1 group-hover:text-white" name="arrow-right" size={18} />
          </Link>
        ))}
      </div>
    </section>
  );
}
