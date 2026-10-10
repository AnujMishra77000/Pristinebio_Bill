import type { ReactNode, SVGProps } from "react";

export const appIconNames = [
  "dashboard",
  "billing",
  "sales-invoice",
  "purchase-order",
  "reagent",
  "reagent-purchase-order",
  "customers",
  "products",
  "seller-profile",
  "users",
  "bank-accounts",
  "transporters",
  "terms",
  "settings",
  "menu",
  "approvals", "suppliers", "purchasers", "security", "payments", "integrations",
  "search", "plus", "arrow-right", "close", "chevron-down", "logout", "check", "clock",
] as const;

export type AppIconName = (typeof appIconNames)[number];

type AppIconProps = Omit<SVGProps<SVGSVGElement>, "name"> & {
  name: AppIconName;
  size?: number;
  strokeWidth?: number;
  label?: string;
};

const iconPaths: Record<AppIconName, ReactNode> = {
  approvals: <><path d="M9 3H5v18h14V3h-4M9 2h6v4H9z" /><path d="m8 13 3 3 5-6" /></>,
  suppliers: <><path d="M3 21V8l9-5 9 5v13H3ZM3 9h18M8 21v-7h8v7M7 11h.01M17 11h.01" /></>,
  purchasers: <><path d="M4 20V8l8-5 8 5v12H4Z" /><path d="M8 20v-6h8v6M7 10h.01M17 10h.01" /></>,
  security: <><path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6l-8-3Z" /><path d="m8 12 3 3 5-6" /></>,
  payments: <><rect x="3" y="5" width="18" height="15" rx="2" /><path d="M3 9h18M15 13h6M16 16h.01" /></>,
  integrations: <><path d="M8 3v5M16 3v5M5 8h14v3a7 7 0 0 1-14 0V8ZM12 18v4" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  "arrow-right": <path d="M4 12h16m-6-6 6 6-6 6" />,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  "chevron-down": <path d="m6 9 6 6 6-6" />,
  logout: <><path d="M9 4H4v16h5M9 12h12m-5-5 5 5-5 5" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  dashboard: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </>
  ),
  billing: (
    <>
      <path d="M6 3h12a2 2 0 0 1 2 2v14H4V5a2 2 0 0 1 2-2Z" />
      <path d="M8 7h8M8 11h8M8 15h5" />
    </>
  ),
  "sales-invoice": (
    <>
      <path d="M6 3h9l4 4v14H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
      <path d="M14 3v5h5M8 12h8M8 16h5" />
    </>
  ),
  "purchase-order": (
    <>
      <path d="M5 7h14M5 17h14M8 4l-3 3 3 3M16 14l3 3-3 3" />
      <path d="M5 7h14v10H5z" />
    </>
  ),
  reagent: (
    <>
      <path d="m12 4 6.9 4v8L12 20l-6.9-4V8L12 4Z" />
      <path d="m8 8.9 4-2.3M16.4 9.4v5.2M12 17.2l-4-2.3M5.1 8 2 6M18.9 16 22 18" />
    </>
  ),
  "reagent-purchase-order": (
    <>
      <path d="m8 3 5.2 3v6L8 15l-5.2-3V6L8 3Z" />
      <path d="m5.2 6.7 2.8-1.6M11.2 7.2v3.6M8 12.9l-2.8-1.6M13.2 6 16 4.4" />
      <path d="M15 12h4l3 3v7h-7V12ZM19 12v3h3M17 18h3" />
    </>
  ),
  customers: (
    <>
      <circle cx="9" cy="8" r="3" />
      <path d="M3.5 20a5.5 5.5 0 0 1 11 0M16 11a3 3 0 1 0 0-6M16 14.5a5.5 5.5 0 0 1 4.5 5.5" />
    </>
  ),
  products: (
    <>
      <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z" />
      <path d="m4.5 7.5 7.5 4 7.5-4M12 12v9" />
    </>
  ),
  "seller-profile": (
    <>
      <path d="M4 20V9l8-6 8 6v11H4Z" />
      <path d="M9 20v-6h6v6M7 10h.01M12 10h.01M17 10h.01" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3" />
      <circle cx="17" cy="9" r="2.5" />
      <path d="M3.5 20a5.5 5.5 0 0 1 11 0M15 15.5a4.5 4.5 0 0 1 5 4.5" />
    </>
  ),
  "bank-accounts": (
    <>
      <path d="m3 9 9-5 9 5M5 10v7M9 10v7M15 10v7M19 10v7M3 20h18" />
    </>
  ),
  transporters: (
    <>
      <path d="M3 6h11v10H3zM14 10h4l3 3v3h-7z" />
      <circle cx="7" cy="18" r="2" />
      <circle cx="18" cy="18" r="2" />
    </>
  ),
  terms: (
    <>
      <path d="M5 3h14v18H5z" />
      <path d="M8 7h8M8 11h8M8 15h5" />
    </>
  ),
  settings: (
    <>
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
      <circle cx="12" cy="12" r="4" />
    </>
  ),
  menu: (
    <>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </>
  ),
};

export function AppIcon({ name, size = 20, strokeWidth = 1.8, label, ...props }: AppIconProps) {
  const accessibleLabel = label ?? (props["aria-label"] as string | undefined);

  return (
    <svg
      aria-hidden={accessibleLabel ? undefined : true}
      aria-label={accessibleLabel}
      fill="none"
      height={size}
      role={accessibleLabel ? "img" : undefined}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={strokeWidth}
      viewBox="0 0 24 24"
      width={size}
      {...props}
    >
      {iconPaths[name]}
    </svg>
  );
}
