"use client";

import { MasterDataPage } from "@/app/components/MasterDataPage";

export default function ManufacturersPage() {
  return (
    <MasterDataPage
      icon="products"
      title="Manufacturers"
      description="Maintain the MFG codes used to organize Reagent products, such as SIG and MRK."
      endpoint="/manufacturers"
      fields={[
        { name: "branch_id", label: "Seller/GST profile", type: "number", required: true },
        { name: "code", label: "Manufacturer code", required: true },
        { name: "name", label: "Manufacturer name", required: true },
        { name: "is_active", label: "Active", type: "checkbox" },
      ]}
      columns={[
        { key: "code", label: "MFG code" },
        { key: "name", label: "Manufacturer" },
        { key: "is_active", label: "Status" },
      ]}
      initialForm={{ branch_id: "", code: "", name: "", is_active: true }}
      editable
      recordActions={{ activeField: "is_active" }}
      recordToForm={(record) => ({
        branch_id: String(record.branch_id ?? ""),
        code: String(record.code ?? ""),
        name: String(record.name ?? ""),
        is_active: Boolean(record.is_active),
      })}
    />
  );
}
