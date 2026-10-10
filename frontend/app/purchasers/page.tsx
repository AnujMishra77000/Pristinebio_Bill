"use client";

import { MasterDataPage } from "@/app/components/MasterDataPage";

export default function PurchasersPage() {
  return (
    <MasterDataPage
      icon="purchasers"
      title="Purchasers"
      description="Save the different purchaser companies used on your purchase orders. Manual PO entry remains available when a company is not yet saved."
      endpoint="/purchasers"
      fields={[
        { name: "branch_id", label: "Seller/GST profile", type: "number", required: true },
        { name: "name", label: "Purchaser company name", type: "textarea", required: true, section: "Purchaser details" },
        { name: "gstin", label: "GSTIN" },
        { name: "pan", label: "PAN" },
        { name: "email", label: "Accounts email", type: "email" },
        { name: "phone", label: "Contact phone" },
        { name: "address_name", label: "Address name", section: "Purchaser address" },
        { name: "address_line1", label: "Address line 1", type: "textarea", required: true },
        { name: "address_line2", label: "Address line 2", type: "textarea" },
        { name: "city", label: "City", required: true },
        { name: "state", label: "State", required: true },
        { name: "state_code", label: "State code", required: true },
        { name: "postal_code", label: "Postal code", required: true },
        { name: "is_active", label: "Active", type: "checkbox" },
      ]}
      columns={[
        { key: "id", label: "ID" },
        { key: "name", label: "Purchaser" },
        { key: "gstin", label: "GSTIN" },
        { key: "address.city", label: "City" },
        { key: "is_active", label: "Active" },
      ]}
      initialForm={{ branch_id: "", name: "", gstin: "", pan: "", email: "", phone: "", address_name: "", address_line1: "", address_line2: "", city: "", state: "", state_code: "", postal_code: "", is_active: true }}
      transformPayload={(payload) => ({
        branch_id: payload.branch_id,
        name: payload.name,
        gstin: payload.gstin,
        pan: payload.pan,
        email: payload.email,
        phone: payload.phone,
        address: {
          name: payload.address_name || null,
          address_line1: payload.address_line1,
          address_line2: payload.address_line2 || null,
          city: payload.city,
          state: payload.state,
          state_code: payload.state_code,
          postal_code: payload.postal_code,
        },
        is_active: payload.is_active,
      })}
      editable
      recordToForm={(record) => {
        const address = (record.address ?? {}) as Record<string, unknown>;
        return {
          branch_id: String(record.branch_id ?? ""),
          name: String(record.name ?? ""),
          gstin: String(record.gstin ?? ""),
          pan: String(record.pan ?? ""),
          email: String(record.email ?? ""),
          phone: String(record.phone ?? ""),
          address_name: String(address.name ?? ""),
          address_line1: String(address.address_line1 ?? ""),
          address_line2: String(address.address_line2 ?? ""),
          city: String(address.city ?? ""),
          state: String(address.state ?? ""),
          state_code: String(address.state_code ?? ""),
          postal_code: String(address.postal_code ?? ""),
          is_active: Boolean(record.is_active),
        };
      }}
    />
  );
}
