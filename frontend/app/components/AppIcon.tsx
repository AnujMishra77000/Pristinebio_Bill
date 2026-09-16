import type { ReactNode, SVGProps } from "react";

export const appIconNames = [
  "dashboard",
  "billing",
  "sales-invoice",
  "purchase-order",
  "customers",
  "products",
  "seller-profile",
  "users",
  "bank-accounts",
  "transporters",
  "terms",
  "settings",
  "menu",
] as const;

export type AppIconName = (typeof appIconNames)[number];

type AppIconProps = Omit<SVGProps<SVGSVGElement>, "name"> & {
  name: AppIconName;
  size?: number;
  strokeWidth?: number;
  label?: string;
};

const iconPaths: Record<AppIconName, ReactNode> = {
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
