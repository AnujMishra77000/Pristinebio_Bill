import type { AppIconName } from "@/app/components/AppIcon";
import type { DashboardSummary, Invoice, PurchaseOrder } from "./types";

type RegisterConfig = {
  label: string; title: string; href: string; icon: AppIconName;
  collection: "invoices" | "purchase-orders";
  documentType: "sales" | "domestic_oils" | "reagent";
  countKey: keyof Pick<DashboardSummary, "sales_invoice_count" | "domestic_oils_purchase_order_count" | "reagent_invoice_count" | "reagent_purchase_order_count">;
};

export const billRegisters = {
  sales: { label: "Sales", title: "Sales bills", href: "/bill-registers/sales", icon: "sales-invoice", collection: "invoices", documentType: "sales", countKey: "sales_invoice_count" },
  purchase: { label: "Purchase", title: "Purchase bills", href: "/bill-registers/purchase", icon: "purchase-order", collection: "purchase-orders", documentType: "domestic_oils", countKey: "domestic_oils_purchase_order_count" },
  reagent: { label: "Reagent", title: "Reagent bills", href: "/bill-registers/reagent", icon: "reagent", collection: "invoices", documentType: "reagent", countKey: "reagent_invoice_count" },
  "reagent-purchase": { label: "Reagent Purchase", title: "Reagent purchase bills", href: "/bill-registers/reagent-purchase", icon: "reagent-purchase-order", collection: "purchase-orders", documentType: "reagent", countKey: "reagent_purchase_order_count" },
} as const satisfies Record<string, RegisterConfig>;

export type BillRegisterKind = keyof typeof billRegisters;
export type RegisteredBill = Invoice | PurchaseOrder;
export function billEditHref(kind: BillRegisterKind, bill: RegisteredBill): string | null {
  const config = billRegisters[kind];
  if (bill.document_type !== config.documentType || !Number.isSafeInteger(bill.id) || bill.id <= 0 || !Number.isSafeInteger(bill.version) || bill.version <= 0) return null;
  if (bill.status !== "draft" && !(config.collection === "purchase-orders" && bill.status === "amendment_pending")) return null;
  const entry = { sales: "/invoices", reagent: "/reagent-bills", purchase: "/purchase-orders", "reagent-purchase": "/reagent-purchase-orders" }[kind];
  return `${entry}?${config.collection === "invoices" ? "invoice" : "order"}=${bill.id}`;
}
export const billNumber = (bill: RegisteredBill) => "invoice_number" in bill ? bill.invoice_number ?? `Draft #${bill.id}` : bill.purchase_order_number;
export const billDate = (bill: RegisteredBill) => "invoice_date" in bill ? bill.invoice_date : bill.order_date;
export const billParty = (bill: RegisteredBill) => "buyer_name" in bill ? bill.buyer_name : bill.purchaser_name ?? bill.supplier_name;
export const displayBillDate = (value: string) => new Date(`${value}T00:00:00+05:30`).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "Asia/Kolkata" });
