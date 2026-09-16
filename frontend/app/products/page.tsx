import { MasterDataPage } from "@/app/components/MasterDataPage";

export default function ProductsPage() {
  return (
    <MasterDataPage
      title="Products"
      description="Create and view product masters with HSN/SAC, unit, base rate, GST rate, and cess rate. The Seller/GST profile is used automatically."
      endpoint="/products"
      fields={[
        { name: "branch_id", label: "Seller/GST profile", type: "number", required: true },
        { name: "name", label: "Product name", required: true },
        { name: "description", label: "Description", type: "textarea" },
        { name: "hsn_sac", label: "HSN/SAC", required: true },
        { name: "unit", label: "Unit", required: true },
        { name: "base_rate", label: "Base rate", required: true },
        { name: "gst_rate", label: "GST rate", required: true },
        { name: "cess_rate", label: "Cess rate", required: true },
        { name: "is_active", label: "Active", type: "checkbox" },
      ]}
      columns={[
        { key: "id", label: "ID" },
        { key: "name", label: "Product" },
        { key: "hsn_sac", label: "HSN/SAC" },
        { key: "unit", label: "Unit" },
        { key: "base_rate", label: "Base rate" },
        { key: "gst_rate", label: "GST %" },
        { key: "cess_rate", label: "Cess %" },
      ]}
      initialForm={{
        branch_id: "",
        name: "",
        description: "",
        hsn_sac: "",
        unit: "",
        base_rate: "",
        gst_rate: "",
        cess_rate: "0",
        is_active: true,
      }}
    />
  );
}
