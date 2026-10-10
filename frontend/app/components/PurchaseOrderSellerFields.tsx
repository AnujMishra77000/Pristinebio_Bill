"use client";

import { AutoResizeTextarea } from "@/app/components/AutoResizeTextarea";
import type { PurchaseOrder } from "@/app/lib/types";

export type PurchaseOrderSellerValues = {
  name: string; gstin: string; pan: string; phone: string; email: string;
  address_line1: string; address_line2: string; city: string; state: string;
  state_code: string; postal_code: string;
};

export function purchaseOrderSellerValues(order: PurchaseOrder): PurchaseOrderSellerValues {
  return {
    name: order.supplier_name, gstin: order.supplier_gstin ?? "", pan: order.supplier_pan ?? "",
    phone: order.supplier_phone ?? "", email: order.supplier_email ?? "",
    address_line1: order.supplier_address_line1, address_line2: order.supplier_address_line2 ?? "",
    city: order.supplier_city, state: order.supplier_state,
    state_code: order.supplier_state_code, postal_code: order.supplier_postal_code,
  };
}

const fields: [keyof PurchaseOrderSellerValues, string, boolean?][] = [
  ["name", "Seller company name", true], ["gstin", "GSTIN"], ["pan", "PAN"],
  ["phone", "Contact (phone)"], ["email", "Email"],
  ["address_line1", "Address line 1", true], ["address_line2", "Address line 2", true],
  ["city", "City"], ["state", "State"], ["state_code", "State code"], ["postal_code", "Postal code"],
];

export function PurchaseOrderSellerFields({ details, onChange, errors = {}, readOnly = false }: {
  details: PurchaseOrderSellerValues;
  onChange: (field: keyof PurchaseOrderSellerValues, value: string) => void;
  errors?: Record<string, string>;
  readOnly?: boolean;
}) {
  return <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
    {fields.map(([field, label, multiline]) => {
      const addressField = ["address_line1", "address_line2", "city", "state", "state_code", "postal_code"].includes(field);
      const error = errors[`supplier.${addressField ? "address." : ""}${field}`];
      const id = `po-seller-${field}`;
      const props = { id, value: details[field], readOnly, "aria-label": label, "aria-invalid": Boolean(error), "aria-describedby": error ? `${id}-error` : undefined };
      const update = (value: string) => onChange(field, ["gstin", "pan"].includes(field) ? value.toUpperCase() : value);
      return <label key={field} htmlFor={id} className={`ui-label block ${multiline ? "sm:col-span-2" : ""}`}>
        {label}
        {multiline
          ? <AutoResizeTextarea {...props} className="ui-input" rows={1} onChange={(event) => update(event.target.value)} />
          : <input {...props} className="ui-input" type={field === "email" ? "email" : field === "phone" ? "tel" : "text"} maxLength={field === "gstin" ? 15 : field === "pan" ? 10 : field === "state_code" ? 2 : undefined} onChange={(event) => update(event.target.value)} />}
        {error && <span id={`${id}-error`} className="mt-1 block text-xs text-red-700" role="alert">{error}</span>}
      </label>;
    })}
  </div>;
}

export function PurchaseOrderShippingDetails({ details }: { details: PurchaseOrderSellerValues }) {
  const address = [details.address_line1, details.address_line2, details.city, details.state, details.postal_code].filter(Boolean).join(", ");
  return <section aria-label="Seller / Shipping Address" className="mt-6 rounded-2xl border border-line bg-warm/50 p-4 sm:p-5">
    <h2 className="text-base font-bold text-ink">Seller / Shipping Address</h2>
    <p className="mt-2 text-xs leading-5 text-slate">Same as Seller. Enter or select the seller once; these details update automatically.</p>
    <p className="mt-4 break-words font-bold text-ink">{details.name || "Seller company name will appear here"}</p>
    <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
      {[["Address", address], ["GSTIN", details.gstin], ["State code", details.state_code], ["PAN", details.pan], ["Contact", details.phone], ["Email", details.email]].map(([label, value]) =>
        <div key={label} className={label === "Address" ? "sm:col-span-2 lg:col-span-3" : "min-w-0"}>
          <dt className="font-semibold text-slate">{label}</dt><dd className="mt-1 break-words text-ink">{value || "—"}</dd>
        </div>)}
    </dl>
  </section>;
}
