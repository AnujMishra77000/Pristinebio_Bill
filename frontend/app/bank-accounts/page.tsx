import { MasterDataPage } from "@/app/components/MasterDataPage";

export default function BankAccountsPage() {
  return (
    <MasterDataPage
      title="Bank accounts"
      description="Create and view bank account details used later by invoices. The Seller/GST profile is used automatically."
      endpoint="/bank-accounts"
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
