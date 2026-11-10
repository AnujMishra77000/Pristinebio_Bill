"use client";

import { MasterDataPage } from "@/app/components/MasterDataPage";

export default function BankAccountsPage() {
  return (
    <MasterDataPage
      icon="bank-accounts"
      title="Bank accounts"
      description="Edit your bank details and set the default account for new bills and purchase orders. Setting a default replaces the previous default for this seller profile. Finalized PDFs keep their saved details."
      endpoint="/bank-accounts"
      editable
      recordToForm={(record) => ({
        branch_id: String(record.branch_id ?? ""),
        bank_name: String(record.bank_name ?? ""),
        account_name: String(record.account_name ?? ""),
        account_number: String(record.account_number ?? ""),
        ifsc_code: String(record.ifsc_code ?? ""),
        branch_name: String(record.branch_name ?? ""),
        is_default: record.is_default === true,
        is_active: record.is_active === true,
      })}
      recordActions={{ activeField: "is_active", defaultField: "is_default", defaultLabel: "bank account" }}
      fields={[
        { name: "branch_id", label: "Seller/GST profile", type: "number", required: true },
        { name: "bank_name", label: "Bank name", required: true },
        { name: "account_name", label: "Account name", required: true },
        { name: "account_number", label: "Account number", required: true },
        { name: "ifsc_code", label: "IFSC code", required: true },
        { name: "branch_name", label: "Bank branch name" },
        { name: "is_default", label: "Default account", type: "checkbox" },
        { name: "is_active", label: "Active", type: "checkbox" },
      ]}
      columns={[
        { key: "id", label: "ID" },
        { key: "bank_name", label: "Bank" },
        { key: "account_name", label: "Account name" },
        { key: "account_number", label: "Account no." },
        { key: "ifsc_code", label: "IFSC" },
        { key: "is_default", label: "Default" },
        { key: "is_active", label: "Status" },
      ]}
      initialForm={{
        branch_id: "",
        bank_name: "",
        account_name: "",
        account_number: "",
        ifsc_code: "",
        branch_name: "",
        is_default: false,
        is_active: true,
      }}
    />
  );
}
