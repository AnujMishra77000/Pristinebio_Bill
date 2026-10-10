"use client";

import { MasterDataPage, type FieldConfig } from "@/app/components/MasterDataPage";

export default function ProductsPage() {
  const fields: FieldConfig[] = [
    { name: "branch_id", label: "Seller/GST profile", type: "number", required: true },
    { name: "name", label: "Product name", type: "textarea", required: true },
    { name: "description", label: "Description", type: "textarea" },
    { name: "hsn_sac", label: "HSN/SAC", required: true },
    { name: "gst_rate", label: "GST rate (%)", required: true },
    { name: "cess_rate", label: "Cess rate (%)", required: true },
    { name: "is_active", label: "Active", type: "checkbox" },
  ];

  return (
    <MasterDataPage
      icon="products"
      title="Products"
      description="Maintain reusable product names, descriptions, HSN/SAC classification and tax rates."
      endpoint="/products"
      fields={fields}
      columns={[
        { key: "id", label: "ID" },
        { key: "name", label: "Product" },
        { key: "hsn_sac", label: "HSN/SAC" },
        { key: "gst_rate", label: "GST %" },
        { key: "cess_rate", label: "Cess %" },
        { key: "is_active", label: "Status" },
      ]}
      initialForm={{ branch_id: "", name: "", description: "", hsn_sac: "", gst_rate: "", cess_rate: "0", is_active: true }}
      editable
      recordActions={{ activeField: "is_active" }}
      recordToForm={(record) => ({
        branch_id: String(record.branch_id ?? ""),
        name: String(record.name ?? ""),
        description: String(record.description ?? ""),
        hsn_sac: String(record.hsn_sac ?? ""),
        gst_rate: String(record.gst_rate ?? ""),
        cess_rate: String(record.cess_rate ?? "0"),
        is_active: Boolean(record.is_active),
      })}
    />
  );
}
