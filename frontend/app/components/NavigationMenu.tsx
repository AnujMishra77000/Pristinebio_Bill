"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { AppIcon, type AppIconName } from "./AppIcon";

type NavigationRoute = {
  label: string;
  href: string;
  icon: AppIconName;
};

type NavigationGroup = {
  label: "Workspace" | "Masters" | "Control";
  routes: NavigationRoute[];
};

export const navigationGroups: NavigationGroup[] = [
  {
    label: "Workspace",
    routes: [
      { label: "Dashboard", href: "/", icon: "dashboard" },
      { label: "Billing", href: "/billing", icon: "billing" },
      { label: "Sales invoices", href: "/invoices", icon: "sales-invoice" },
      { label: "Reagent bills", href: "/reagent-bills", icon: "reagent" },
      { label: "Purchase orders", href: "/purchase-orders", icon: "purchase-order" },
      { label: "Reagent purchase orders", href: "/reagent-purchase-orders", icon: "reagent-purchase-order" },
      { label: "Approvals", href: "/approvals", icon: "approvals" },
      { label: "Receivables", href: "/payments", icon: "payments" },
    ],
  },
  {
    label: "Masters",
    routes: [
      { label: "Customers", href: "/customers", icon: "customers" },
      { label: "Products", href: "/products", icon: "products" },
      { label: "Manufacturers", href: "/manufacturers", icon: "products" },
      { label: "Suppliers", href: "/suppliers", icon: "suppliers" },
      { label: "Purchasers", href: "/purchasers", icon: "purchasers" },
      { label: "Seller profile", href: "/branches", icon: "seller-profile" },
      { label: "Bank accounts", href: "/bank-accounts", icon: "bank-accounts" },
      { label: "Transporters", href: "/transporters", icon: "transporters" },
      { label: "Terms", href: "/terms", icon: "terms" },
    ],
  },
  {
    label: "Control",
    routes: [
      { label: "Users", href: "/users", icon: "users" },
      { label: "Settings", href: "/settings", icon: "settings" },
      { label: "Security", href: "/security", icon: "security" },
      { label: "Integrations", href: "/integrations", icon: "integrations" },
    ],
  },
];

type NavigationMenuProps = {
  mobile?: boolean;
  onNavigate?: (href: string) => void;
  query?: string;
};

function isRouteActive(pathname: string, href: string) {
  return href === "/" ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
}

export function NavigationMenu({ mobile = false, onNavigate, query = "" }: NavigationMenuProps) {
  const pathname = usePathname();
  const filteredGroups = navigationGroups
    .map((group) => ({ ...group, routes: group.routes.filter((route) => `${group.label} ${route.label}`.toLowerCase().includes(query.trim().toLowerCase())) }))
    .filter((group) => group.routes.length > 0);

  return (
    <nav aria-label="Primary navigation" className={mobile ? "grid gap-5 sm:grid-cols-3" : "space-y-6"}>
      {filteredGroups.length === 0 && <p role="status" className="col-span-full px-3 py-8 text-center text-sm text-slate">No features match “{query}”.</p>}
      {filteredGroups.map((group) => (
        <section key={group.label} aria-labelledby={`navigation-${group.label.toLowerCase()}`}>
          <h2
            className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.2em] text-slate"
            id={`navigation-${group.label.toLowerCase()}`}
          >
            {group.label}
          </h2>
          <div className={mobile ? "space-y-1" : "space-y-1.5"}>
            {group.routes.map((route) => {
              const active = isRouteActive(pathname, route.href);

              return (
                <Link
                  aria-current={active ? "page" : undefined}
                  className={[
                    "group flex items-center gap-3 rounded-xl text-sm font-medium transition-colors",
                    mobile ? "px-3 py-2.5" : "px-3 py-2.5",
                    active
                      ? "bg-peacock-deep text-white shadow-sm"
                      : "text-slate hover:bg-warm-green hover:text-graphite",
                  ].join(" ")}
                  href={route.href}
                  key={route.href}
                  onClick={() => onNavigate?.(route.href)}
                >
                  <AppIcon
                    className={active ? "text-lime" : "text-slate group-hover:text-emerald"}
                    name={route.icon}
                    size={18}
                  />
                  {route.label}
                </Link>
              );
            })}
          </div>
        </section>
      ))}
    </nav>
  );
}
