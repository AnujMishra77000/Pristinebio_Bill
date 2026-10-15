export type UserRole = "admin" | "manager" | "staff";

export interface User { id: number; email: string; full_name: string; role: UserRole; branch_ids: number[]; is_active: boolean; password_change_required: boolean; mfa_enabled: boolean; mfa_required: boolean; mfa_verified: boolean; }
export interface SessionResponse { user: User; }
export interface AuthSession { id: string; created_at: string; last_seen_at: string; expires_at: string; current: boolean; }
export interface Invitation { id: number; email: string; role: UserRole; branch_ids: number[]; expires_at: string; accepted_at: string | null; revoked_at: string | null; }
export interface CreatedInvitation extends Omit<Invitation, "accepted_at" | "revoked_at"> { token: string; }
export interface AuthAuditEvent { id: number; actor_id: number | null; action: string; entity_type: string; entity_id: string | null; created_at: string; before: unknown; after: unknown; }
export interface Address { name: string | null; address_line1: string | null; address_line2: string | null; city: string | null; state: string | null; state_code: string | null; postal_code: string | null; }
export interface Company { id: number; legal_name: string; trade_name: string | null; pan: string | null; registered_address: string | null; logo_data_uri: string | null; is_active: boolean; }
export interface Branch { id: number; company_id: number; name: string; gstin: string; address_line1: string; address_line2: string | null; city: string; state: string; state_code: string; postal_code: string; phone: string | null; email: string | null; secondary_email: string | null; bank_name: string | null; bank_branch_name: string | null; bank_account_name: string | null; bank_account_number: string | null; bank_ifsc_code: string | null; terms_body: string | null; is_active: boolean; }
export interface SellerProfileResponse { company: Company | null; seller_profile: Branch | null; }
export interface Customer { id: number; branch_id: number; name: string; gstin: string | null; pan: string | null; email: string | null; phone: string | null; billing_address: Address; shipping_address: Address | null; is_active: boolean; }
export interface Supplier { id: number; branch_id: number; name: string; gstin: string | null; pan: string | null; email: string | null; phone: string | null; address: Address; is_default: boolean; is_active: boolean; }
export interface Purchaser { id: number; branch_id: number; name: string; gstin: string | null; pan: string | null; email: string | null; phone: string | null; address: Address; is_active: boolean; }
export interface Manufacturer { id: number; branch_id: number; code: string; name: string; is_active: boolean; }
export interface Product { id: number; branch_id: number; manufacturer_id: number | null; manufacturer_code: string | null; manufacturer_name: string | null; manufacturer_product_code: string | null; name: string; description: string | null; hsn_sac: string; unit: string; base_rate: string; gst_rate: string; cess_rate: string; is_active: boolean; }
export interface BankAccount { id: number; branch_id: number; bank_name: string; account_name: string; account_number: string; ifsc_code: string; branch_name: string | null; is_default: boolean; is_active: boolean; }
export interface Transporter { id: number; branch_id: number; name: string; gstin: string | null; phone: string | null; vehicle_number: string | null; is_active: boolean; }
export interface TermsAndConditions { id: number; branch_id: number; title: string; body: string; is_default: boolean; is_active: boolean; }
export type InvoiceStatus = "draft" | "pending_approval" | "approved" | "pdf_generated";
export interface BillCorrection { base_version: number; reason: string; status: "draft" | "pending_approval"; previous_final_total: string; }
export interface PendingBillCorrection {
  collection: "invoices" | "purchase-orders";
  document_id: number;
  document_type: "sales" | "reagent" | "domestic_oils";
  document_number: string;
  version: number;
  reason: string;
  previous_final_total: string;
  final_total: string;
  created_by_id: number;
  submitted_by_id: number;
}
export interface InvoiceLine {
  id: number;
  product_id: number;
  sort_order: number;
  product_name: string;
  description: string;
  manufacturer_name: string | null;
  manufacturer_code: string | null;
  manufacturer_product_code: string | null;
  part_no: string | null;
  pack_size: string | null;
  hsn_sac: string;
  quantity: string;
  unit: string;
  rate: string;
  other_charge: string;
  discount_amount: string;
  discount_percent: string;
  taxable_value: string;
  gst_rate: string;
  cess_rate: string;
  cgst_amount: string;
  sgst_amount: string;
  igst_amount: string;
  cess_amount: string;
  line_total: string;
}
export type InvoicePreviewLine = Omit<InvoiceLine, "id" | "product_id" | "sort_order" | "product_name">;
export interface InvoiceTotals {
  taxable_value: string;
  cgst_amount: string;
  sgst_amount: string;
  igst_amount: string;
  cess_amount: string;
  unrounded_total: string;
  round_off: string;
  final_total: string;
  amount_in_words: string;
}
export interface InvoicePreview extends InvoiceTotals { lines: InvoicePreviewLine[]; }
export interface Invoice extends InvoiceTotals {
  correction?: BillCorrection | null;
  created_by_id: number;
  submitted_by_id: number | null;
  id: number;
  document_type: "sales" | "reagent";
  branch_id: number;
  buyer_customer_id: number;
  supplier_id: number | null;
  consignee_customer_id: number | null;
  transporter_id: number | null;
  terms_and_conditions_id: number | null;
  status: InvoiceStatus;
  version: number;
  submitted_revision: number | null;
  approved_revision: number | null;
  returned_reason: string | null;
  invoice_number: string | null;
  invoice_sequence: number | null;
  financial_year: string | null;
  invoice_date: string;
  delivery_note_date: string | null;
  place_of_supply_state_code: string;
  po_number: string | null;
  payment_terms: string | null;
  branch_name: string;
  branch_gstin: string;
  buyer_name: string;
  buyer_gstin: string | null;
  buyer_pan: string | null;
  buyer_email: string | null;
  buyer_phone: string | null;
  buyer_address_line1: string;
  buyer_address_line2: string | null;
  buyer_city: string;
  buyer_state: string;
  buyer_state_code: string;
  buyer_postal_code: string;
  consignee_name: string | null;
  consignee_gstin: string | null;
  consignee_pan: string | null;
  consignee_email: string | null;
  consignee_phone: string | null;
  consignee_address_line1: string | null;
  consignee_address_line2: string | null;
  consignee_city: string | null;
  consignee_state: string | null;
  consignee_state_code: string | null;
  consignee_postal_code: string | null;
  transport_mode: string | null;
  vehicle_number: string | null;
  vehicle_type: string | null;
  lr_number: string | null;
  lr_date: string | null;
  expected_delivery_date: string | null;
  freight_charges: string;
  packing_charges: string;
  other_charges: string;
  discount_amount: string;
  seller_logo_data_uri: string | null;
  lines: InvoiceLine[];
  irn: string | null;
  signed_qr_data: string | null;
  e_way_bill_number: string | null;
  e_way_bill_date: string | null;
  acknowledgement_number: string | null;
  acknowledgement_date: string | null;
  pdf_sha256: string | null;
  pdf_template_version: string | null;
  pdf_storage_key: string | null;
  pdf_generated_by_id: number | null;
  pdf_generated_at: string | null;
}
export type PurchaseOrderLine = InvoiceLine;
export interface PurchaseOrder extends InvoiceTotals {
  correction?: BillCorrection | null;
  id: number;
  document_type: "domestic_oils" | "reagent";
  place_of_supply_state_code: string | null;
  delivery_note_date: string | null;
  po_reference_number: string | null;
  po_reference_date: string | null;
  transport_mode: string | null;
  vehicle_number: string | null;
  vehicle_type: string | null;
  lr_number: string | null;
  lr_date: string | null;
  consignee: { name: string; gstin: string | null; pan: string | null; email: string | null; phone: string | null; address: Address } | null;
  freight_charges: string;
  packing_charges: string;
  other_charges: string;
  discount_amount: string;
  lines: (PurchaseOrderLine & { manufacturer_id: number | null })[];
  branch_id: number;
  supplier_id: number;
  purchaser_id: number | null;
  created_by_id: number;
  purchase_order_number: string;
  order_date: string;
  expected_delivery_date: string | null;
  payment_terms: string | null;
  status: string;
  version: number;
  submitted_revision: number | null;
  approved_revision: number | null;
  submitted_by_id: number | null;
  approved_by_id: number | null;
  submitted_at: string | null;
  approved_at: string | null;
  cancellation_reason: string | null;
  closed_at: string | null;
  branch_name: string;
  branch_gstin: string;
  supplier_name: string;
  supplier_gstin: string | null;
  supplier_phone: string | null;
  supplier_pan: string | null;
  supplier_email: string | null;
  supplier_address_line1: string;
  supplier_address_line2: string | null;
  supplier_city: string;
  supplier_state: string;
  supplier_state_code: string;
  supplier_postal_code: string;
  purchaser_name: string | null;
  purchaser_gstin: string | null;
  purchaser_pan: string | null;
  purchaser_email: string | null;
  purchaser_phone: string | null;
  purchaser_address_line1: string | null;
  purchaser_address_line2: string | null;
  purchaser_city: string | null;
  purchaser_state: string | null;
  purchaser_state_code: string | null;
  purchaser_postal_code: string | null;
  pdf_sha256: string | null;
  pdf_template_version: string | null;
  pdf_storage_key: string | null;
  pdf_generated_by_id: number | null;
  pdf_generated_at: string | null;
}
export interface RegisterPage<T> { items: T[]; total: number; page: number; page_size: number; }
export interface DashboardActivity { document_type: "invoice" | "purchase_order"; document_id: number; action: string; actor_user_id: number; created_at: string; note: string | null; }
export interface DashboardSummary { invoice_count: number; sales_invoice_count: number; reagent_invoice_count: number; purchase_order_count: number; domestic_oils_purchase_order_count: number; reagent_purchase_order_count: number; draft_invoices: number; draft_purchase_orders: number; pending_invoice_approvals: number; pending_purchase_order_approvals: number; recent_activity: DashboardActivity[]; }
