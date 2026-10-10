import { MasterDataPage } from "@/app/components/MasterDataPage";

export default function TermsPage() {
  return (
    <MasterDataPage
      icon="terms"
      title="Terms and conditions"
      description="Save reusable terms and choose the default for future invoices."
      endpoint="/terms-and-conditions"
      fields={[
        { name: "branch_id", label: "Seller/GST profile", type: "number", required: true },
        { name: "title", label: "Title", required: true },
        { name: "body", label: "Terms and conditions", type: "textarea", required: true },
        { name: "is_default", label: "Default terms", type: "checkbox" },
        { name: "is_active", label: "Active", type: "checkbox" },
      ]}
      columns={[
        { key: "id", label: "ID" },
        { key: "title", label: "Title" },
        { key: "body", label: "Terms and conditions" },
        { key: "is_default", label: "Default" },
        { key: "is_active", label: "Active" },
      ]}
      initialForm={{
        branch_id: "",
        title: "",
        body: "",
        is_default: false,
        is_active: true,
      }}
    />
  );
}
