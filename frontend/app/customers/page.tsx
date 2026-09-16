"use client";

import { MasterDataPage } from "@/app/components/MasterDataPage";

function text(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

function requiredText(payload: Record<string, unknown>, key: string) {
  return String(payload[key] ?? "");
}

function hasShippingAddress(payload: Record<string, unknown>) {
  return [
    "shipping_name",
    "shipping_address_line1",
    "shipping_address_line2",
    "shipping_city",
    "shipping_state",
    "shipping_state_code",
    "shipping_postal_code",
  ].some((key) => text(payload, key) !== null);
}

export default function CustomersPage() {
  return (
    <MasterDataPage
      title="Customers"
      description="Create and view customers with separate billing and consignee/shipping addresses. The Seller/GST profile is used automatically."
      endpoint="/customers"
      fields={[
        { name: "branch_id", label: "Seller/GST profile", type: "number", required: true },
        { name: "name", label: "Customer name", required: true },
        { name: "gstin", label: "GSTIN" },
        { name: "pan", label: "PAN" },
        { name: "email", label: "Email", type: "email" },
        { name: "phone", label: "Phone" },
        { name: "billing_name", label: "Billing name" },
        { name: "billing_address_line1", label: "Billing address line 1", required: true },
        { name: "billing_address_line2", label: "Billing address line 2" },
        { name: "billing_city", label: "Billing city", required: true },
        { name: "billing_state", label: "Billing state", required: true },
        { name: "billing_state_code", label: "Billing state code", required: true },
        { name: "billing_postal_code", label: "Billing postal code", required: true },
        { name: "shipping_name", label: "Shipping/consignee name" },
        { name: "shipping_address_line1", label: "Shipping address line 1" },
        { name: "shipping_address_line2", label: "Shipping address line 2" },
        { name: "shipping_city", label: "Shipping city" },
        { name: "shipping_state", label: "Shipping state" },
        { name: "shipping_state_code", label: "Shipping state code" },
        { name: "shipping_postal_code", label: "Shipping postal code" },
        { name: "is_active", label: "Active", type: "checkbox" },
      ]}
      columns={[
        { key: "id", label: "ID" },
        { key: "name", label: "Customer" },
        { key: "gstin", label: "GSTIN" },
        { key: "billing_address.city", label: "Billing city" },
        { key: "shipping_address.city", label: "Shipping city" },
        { key: "is_active", label: "Active" },
      ]}
      initialForm={{
        branch_id: "",
        name: "",
        gstin: "",
        pan: "",
        email: "",
        phone: "",
        billing_name: "",
        billing_address_line1: "",
        billing_address_line2: "",
        billing_city: "",
        billing_state: "",
        billing_state_code: "",
        billing_postal_code: "",
        shipping_name: "",
        shipping_address_line1: "",
        shipping_address_line2: "",
        shipping_city: "",
        shipping_state: "",
        shipping_state_code: "",
        shipping_postal_code: "",
        is_active: true,
      }}
      transformPayload={(payload) => ({
        branch_id: payload.branch_id,
        name: payload.name,
        gstin: payload.gstin,
        pan: payload.pan,
        email: payload.email,
        phone: payload.phone,
        billing_address: {
          name: text(payload, "billing_name"),
          address_line1: requiredText(payload, "billing_address_line1"),
          address_line2: text(payload, "billing_address_line2"),
          city: requiredText(payload, "billing_city"),
          state: requiredText(payload, "billing_state"),
          state_code: requiredText(payload, "billing_state_code"),
          postal_code: requiredText(payload, "billing_postal_code"),
        },
        shipping_address: hasShippingAddress(payload)
          ? {
              name: text(payload, "shipping_name"),
              address_line1: requiredText(payload, "shipping_address_line1"),
              address_line2: text(payload, "shipping_address_line2"),
              city: requiredText(payload, "shipping_city"),
              state: requiredText(payload, "shipping_state"),
              state_code: requiredText(payload, "shipping_state_code"),
              postal_code: requiredText(payload, "shipping_postal_code"),
            }
          : null,
        is_active: payload.is_active,
      })}
    />
  );
}
