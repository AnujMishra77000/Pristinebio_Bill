import { MasterDataPage } from "@/app/components/MasterDataPage";

export default function TransportersPage() {
  return (
    <MasterDataPage
      icon="transporters"
      title="Transporters"
      description="Keep transport contacts, GST details and vehicle numbers ready for dispatch."
      endpoint="/transporters"
      fields={[
        { name: "branch_id", label: "Seller/GST profile", type: "number", required: true },
        { name: "name", label: "Transporter name", type: "textarea", required: true },
        { name: "gstin", label: "GSTIN" },
        { name: "phone", label: "Phone" },
        { name: "vehicle_number", label: "Vehicle number" },
        { name: "is_active", label: "Active", type: "checkbox" },
      ]}
      columns={[
        { key: "id", label: "ID" },
        { key: "name", label: "Transporter" },
        { key: "gstin", label: "GSTIN" },
        { key: "phone", label: "Phone" },
        { key: "vehicle_number", label: "Vehicle" },
        { key: "is_active", label: "Active" },
      ]}
      initialForm={{
        branch_id: "",
        name: "",
        gstin: "",
        phone: "",
        vehicle_number: "",
        is_active: true,
      }}
    />
  );
}
