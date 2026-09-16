export type UserRole = "admin" | "manager" | "staff";

export interface User { id: number; email: string; full_name: string; role: UserRole; branch_ids: number[]; is_active?: boolean; }
export interface TokenResponse { access_token: string; refresh_token?: string | null; token_type: "bearer"; user?: User | null; }
export interface Address { name: string | null; address_line1: string | null; address_line2: string | null; city: string | null; state: string | null; state_code: string | null; postal_code: string | null; }
export interface Company { id: number; legal_name: string; trade_name: string | null; pan: string | null; registered_address: string | null; logo_data_uri: string | null; is_active: boolean; }
export interface Branch { id: number; company_id: number; name: string; gstin: string; address_line1: string; address_line2: string | null; city: string; state: string; state_code: string; postal_code: string; phone: string | null; email: string | null; bank_name: string | null; bank_branch_name: string | null; bank_account_name: string | null; bank_account_number: string | null; bank_ifsc_code: string | null; terms_body: string | null; is_active: boolean; }
export interface SellerProfileResponse { company: Company | null; seller_profile: Branch | null; }
export interface Customer { id: number; branch_id: number; name: string; gstin: string | null; pan: string | null; email: string | null; phone: string | null; billing_address: Address; shipping_address: Address | null; is_active: boolean; }
export interface Supplier { id: number; branch_id: number; name: string; gstin: string | null; pan: string | null; email: string | null; phone: string | null; address: Address; is_active: boolean; }
export interface Product { id: number; branch_id: number; name: string; description: string | null; hsn_sac: string; unit: string; base_rate: string; gst_rate: string; cess_rate: string; is_active: boolean; }
export interface BankAccount { id: number; branch_id: number; bank_name: string; account_name: string; account_number: string; ifsc_code: string; branch_name: string | null; is_default: boolean; is_active: boolean; }
export interface Transporter { id: number; branch_id: number; name: string; gstin: string | null; phone: string | null; vehicle_number: string | null; is_active: boolean; }
export interface TermsAndConditions { id: number; branch_id: number; title: string; body: string; is_default: boolean; is_active: boolean; }
export type InvoiceStatus = "draft" | "pending_approval" | "approved" | "pdf_generated";
export interface InvoiceLine {
  id: number;
  product_id: number;
  sort_order: number;
  product_name: string;
  description: string;
  hsn_sac: string;
  quantity: string;
  unit: string;
  rate: string;
  other_charge: string;
  discount_amount: string;
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
  id: number;
  branch_id: number;
  buyer_customer_id: number;
  consignee_customer_id: number | null;
  transporter_id: number | null;
  terms_and_conditions_id: number | null;
  status: InvoiceStatus;
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
  consignee_name: string | null;
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
  id: number;
  branch_id: number;
  supplier_id: number;
  created_by_id: number;
  purchase_order_number: string;
  order_date: string;
  expected_delivery_date: string | null;
  payment_terms: string | null;
  status: string;
  branch_name: string;
  branch_gstin: string;
  supplier_name: string;
  supplier_gstin: string | null;
  supplier_phone: string | null;
  lines: PurchaseOrderLine[];
  pdf_sha256: string | null;
  pdf_template_version: string | null;
  pdf_storage_key: string | null;
  pdf_generated_by_id: number | null;
  pdf_generated_at: string | null;
}
