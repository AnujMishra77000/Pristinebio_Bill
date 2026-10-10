"use client";

import { MasterDataPage } from "@/app/components/MasterDataPage";

function supplierRecordToForm(record: Record<string, unknown>) {
  const address = (record.address && typeof record.address === "object" ? record.address : {}) as Record<string, unknown>;
  const text = (value: unknown) => typeof value === "string" ? value : value == null ? "" : String(value);
  return {
    branch_id: text(record.branch_id),
    name: text(record.name),
    gstin: text(record.gstin),
    pan: text(record.pan),
    email: text(record.email),
    phone: text(record.phone),
    address_name: text(address.name),
    address_line1: text(address.address_line1),
    address_line2: text(address.address_line2),
    city: text(address.city),
    state: text(address.state),
    state_code: text(address.state_code),
    postal_code: text(address.postal_code),
    is_default: Boolean(record.is_default),
    is_active: Boolean(record.is_active),
  };
}

export default function SuppliersPage() {
  return <MasterDataPage
    icon="suppliers"
    title="Suppliers"
    description="Save pickup suppliers here. Sales and Reagent bills can select any active supplier; the default prefills new bills. Your company registered address remains separate."
    endpoint="/suppliers"
    fields={[
      { name: "branch_id", label: "Seller/GST profile", type: "number", required: true },
      { name: "name", label: "Supplier name", type: "textarea", required: true, section: "Supplier details" },
      { name: "gstin", label: "GSTIN" },
      { name: "pan", label: "PAN" },
      { name: "email", label: "Email", type: "email" },
      { name: "phone", label: "Phone" },
      { name: "address_name", label: "Address name", section: "Supplier address" },
      { name: "address_line1", label: "Address line 1", type: "textarea", required: true },
      { name: "address_line2", label: "Address line 2", type: "textarea" },
      { name: "city", label: "City", required: true },
      { name: "state", label: "State", required: true },
      { name: "state_code", label: "State code", required: true },
      { name: "postal_code", label: "Postal code", required: true },
      { name: "is_default", label: "Set as default supplier", type: "checkbox" },
      { name: "is_active", label: "Active", type: "checkbox" },
    ]}
    columns={[{ key: "id", label: "ID" }, { key: "name", label: "Supplier" }, { key: "gstin", label: "GSTIN" }, { key: "address.city", label: "City" }, { key: "is_default", label: "Default" }, { key: "is_active", label: "Active" }]}
    initialForm={{ branch_id: "", name: "", gstin: "", pan: "", email: "", phone: "", address_name: "", address_line1: "", address_line2: "", city: "", state: "", state_code: "", postal_code: "", is_default: true, is_active: true }}
    transformPayload={(payload) => ({ ...payload, address: { name: payload.address_name || null, address_line1: payload.address_line1, address_line2: payload.address_line2 || null, city: payload.city, state: payload.state, state_code: payload.state_code, postal_code: payload.postal_code }, address_name: undefined, address_line1: undefined, address_line2: undefined, city: undefined, state: undefined, state_code: undefined, postal_code: undefined })}
    editable
    recordToForm={supplierRecordToForm}
    recordActions={{ activeField: "is_active", defaultField: "is_default", allowDelete: true }}
  />;
}
