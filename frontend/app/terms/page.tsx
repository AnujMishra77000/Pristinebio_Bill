import { MasterDataPage } from "@/app/components/MasterDataPage";

export default function TermsPage() {
  return (
    <MasterDataPage
      title="Terms and conditions"
      description="Create and view reusable invoice terms. The Seller/GST profile is used automatically."
      endpoint="/terms-and-conditions"
      fields={[
        { name: "branch_id", label: "Seller/GST profile", type: "number", required: true },
        { name: "title", label: "Title", required: true },
        { name: "body", label: "Body", type: "textarea", required: true },
        { name: "is_default", label: "Default terms", type: "checkbox" },
        { name: "is_active", label: "Active", type: "checkbox" },
      ]}
      columns={[
        { key: "id", label: "ID" },
        { key: "title", label: "Title" },
        { key: "body", label: "Body" },
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
