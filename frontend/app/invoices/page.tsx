"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { AppShell } from "@/app/components/AppShell";
import { AutoResizeTextarea } from "@/app/components/AutoResizeTextarea";
import { AuthGateStatus, useAuthStatus } from "@/app/components/AuthGate";
import { ApiError, apiRequest, downloadFile, previewPdf } from "@/app/lib/api";
import type { Customer, Invoice, InvoicePreview, Product, SellerProfileResponse } from "@/app/lib/types";

type EntryMode = "manual" | "saved";

type PartyForm = {
  name: string;
  gstin: string;
  pan: string;
  email: string;
  phone: string;
  address_line1: string;
  address_line2: string;
  city: string;
  state: string;
  state_code: string;
  postal_code: string;
};

type DraftLine = {
  key: number;
  product_id: string;
  product_name: string;
  description: string;
  hsn_sac: string;
  quantity: string;
  unit: string;
  rate: string;
  other_charge: string;
  discount_amount: string;
  gst_rate: string;
  cess_rate: string;
};

const inputClass = "mt-1.5 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-ink outline-none transition-colors focus:border-[#6f8fe8]";
const toggleClass = "rounded-xl px-4 py-2 text-sm font-semibold transition";

const blankParty = (): PartyForm => ({
  name: "",
  gstin: "",
  pan: "",
  email: "",
  phone: "",
  address_line1: "",
  address_line2: "",
  city: "",
  state: "",
  state_code: "36",
  postal_code: "",
});

function consigneeFromCustomer(customer: Customer): PartyForm {
  const address = customer.billing_address;
  return {
    name: "",
    gstin: customer.gstin ?? "",
    pan: "",
    email: "",
    phone: "",
    address_line1: address.address_line1 ?? "",
    address_line2: address.address_line2 ?? "",
    city: address.city ?? "",
    state: address.state ?? "",
    state_code: address.state_code ?? "",
    postal_code: address.postal_code ?? "",
  };
}

const initialLine = (key: number): DraftLine => ({
  key,
  product_id: "",
  product_name: "",
  description: "",
  hsn_sac: "",
  quantity: "1.000",
  unit: "KG",
  rate: "",
  other_charge: "0.00",
  discount_amount: "0.00",
  gst_rate: "18.00",
  cess_rate: "0.00",
});

function asNumber(value: string) {
  return Number(value);
}

function partyPayload(party: PartyForm) {
  return {
    name: party.name,
    gstin: party.gstin || null,
    pan: party.pan || null,
    email: party.email || null,
    phone: party.phone || null,
    billing_address: {
      name: party.name,
      address_line1: party.address_line1,
      address_line2: party.address_line2 || null,
      city: party.city,
      state: party.state,
      state_code: party.state_code,
      postal_code: party.postal_code,
    },
    shipping_address: {
      name: party.name,
      address_line1: party.address_line1,
      address_line2: party.address_line2 || null,
      city: party.city,
      state: party.state,
      state_code: party.state_code,
      postal_code: party.postal_code,
    },
    is_active: true,
  };
}

function manualPartyComplete(party: PartyForm) {
  return Boolean(party.name && party.address_line1 && party.city && party.state && party.state_code && party.postal_code);
}

type PartyFieldsProps = {
  fieldLabelPrefix?: string;
  party: PartyForm;
  nameLabel: string;
  onChange: (field: keyof PartyForm, value: string) => void;
  readOnlyFields?: ReadonlySet<keyof PartyForm>;
};

function PartyFields({ fieldLabelPrefix = "", party, nameLabel, onChange, readOnlyFields }: PartyFieldsProps) {
  const fieldLabel = (label: string) => `${fieldLabelPrefix}${label}`;
  const isReadOnly = (field: keyof PartyForm) => readOnlyFields?.has(field) ?? false;
  const controlClass = (field: keyof PartyForm) => `${inputClass}${isReadOnly(field) ? " bg-slate-100 text-slate-500" : ""}`;

  return (
    <>
      <label className="text-xs font-semibold text-slate-500">{nameLabel}<input className={inputClass} onChange={(event) => onChange("name", event.target.value)} required value={party.name} /></label>
      <label className="text-xs font-semibold text-slate-500">{fieldLabel("GSTIN")}<input className={controlClass("gstin")} maxLength={15} onChange={(event) => onChange("gstin", event.target.value.toUpperCase())} readOnly={isReadOnly("gstin")} value={party.gstin} /></label>
      <label className="text-xs font-semibold text-slate-500">{fieldLabel("PAN")}<input className={controlClass("pan")} maxLength={10} onChange={(event) => onChange("pan", event.target.value.toUpperCase())} readOnly={isReadOnly("pan")} value={party.pan} /></label>
      <label className="text-xs font-semibold text-slate-500">{fieldLabel("Phone")}<input className={controlClass("phone")} onChange={(event) => onChange("phone", event.target.value)} readOnly={isReadOnly("phone")} value={party.phone} /></label>
      <label className="text-xs font-semibold text-slate-500">{fieldLabel("Email")}<input className={controlClass("email")} onChange={(event) => onChange("email", event.target.value)} readOnly={isReadOnly("email")} type="email" value={party.email} /></label>
      <label className="text-xs font-semibold text-slate-500 lg:col-span-2">{fieldLabel("Address line 1")}<AutoResizeTextarea className={controlClass("address_line1")} onChange={(event) => onChange("address_line1", event.target.value)} readOnly={isReadOnly("address_line1")} required rows={1} value={party.address_line1} /></label>
      <label className="text-xs font-semibold text-slate-500 lg:col-span-2">{fieldLabel("Address line 2")}<AutoResizeTextarea className={controlClass("address_line2")} onChange={(event) => onChange("address_line2", event.target.value)} readOnly={isReadOnly("address_line2")} rows={1} value={party.address_line2} /></label>
      <label className="text-xs font-semibold text-slate-500">{fieldLabel("City")}<input className={controlClass("city")} onChange={(event) => onChange("city", event.target.value)} readOnly={isReadOnly("city")} required value={party.city} /></label>
      <label className="text-xs font-semibold text-slate-500">{fieldLabel("State")}<input className={controlClass("state")} onChange={(event) => onChange("state", event.target.value)} readOnly={isReadOnly("state")} required value={party.state} /></label>
      <label className="text-xs font-semibold text-slate-500">{fieldLabel("State code")}<input className={controlClass("state_code")} maxLength={2} onChange={(event) => onChange("state_code", event.target.value)} readOnly={isReadOnly("state_code")} required value={party.state_code} /></label>
      <label className="text-xs font-semibold text-slate-500">{fieldLabel("Postal code")}<input className={controlClass("postal_code")} onChange={(event) => onChange("postal_code", event.target.value)} readOnly={isReadOnly("postal_code")} required value={party.postal_code} /></label>
    </>
  );
}

const savedConsigneeCopiedFields: ReadonlySet<keyof PartyForm> = new Set([
  "gstin",
  "address_line1",
  "address_line2",
  "city",
  "state",
  "state_code",
  "postal_code",
]);

function lineComplete(line: DraftLine, mode: EntryMode) {
  if (!line.quantity) return false;
  if (mode === "saved") return Boolean(line.product_id);
  return Boolean(line.product_name && line.hsn_sac && line.unit && line.rate && line.gst_rate);
}

function requestErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export default function InvoicesPage() {
  const authStatus = useAuthStatus();
  const [entryMode, setEntryMode] = useState<EntryMode>("manual");
  const [sellerProfiles, setSellerProfiles] = useState<NonNullable<SellerProfileResponse["seller_profile"]>[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [buyerCustomerId, setBuyerCustomerId] = useState("");
  const [manualBuyer, setManualBuyer] = useState<PartyForm>(blankParty);
  const [manualConsignee, setManualConsignee] = useState<PartyForm>(blankParty);
  const [savedConsignee, setSavedConsignee] = useState<PartyForm>(blankParty);
  const [manualConsigneeSameAsBuyer, setManualConsigneeSameAsBuyer] = useState(true);
  const [invoiceDate, setInvoiceDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [deliveryNoteDate, setDeliveryNoteDate] = useState("");
  const [placeOfSupplyStateCode, setPlaceOfSupplyStateCode] = useState("36");
  const [poNumber, setPoNumber] = useState("");
  const [paymentTerms, setPaymentTerms] = useState("30 days");
  const [transportMode, setTransportMode] = useState("Road");
  const [vehicleNumber, setVehicleNumber] = useState("");
  const [vehicleType, setVehicleType] = useState("");
  const [lrNumber, setLrNumber] = useState("");
  const [lrDate, setLrDate] = useState("");
  const [expectedDeliveryDate, setExpectedDeliveryDate] = useState("");
  const [freightCharges, setFreightCharges] = useState("0.00");
  const [packingCharges, setPackingCharges] = useState("0.00");
  const [otherCharges, setOtherCharges] = useState("0.00");
  const [discountAmount, setDiscountAmount] = useState("0.00");
  const [lines, setLines] = useState<DraftLine[]>([initialLine(1)]);
  const [preview, setPreview] = useState<InvoicePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isBillingDataLoaded, setIsBillingDataLoaded] = useState(false);
  const [savedInvoice, setSavedInvoice] = useState<Invoice | null>(null);

  const selectedCustomer = useMemo(
    () => customers.find((customer) => String(customer.id) === buyerCustomerId),
    [buyerCustomerId, customers],
  );
  const activeSellerProfile = useMemo(
    () => sellerProfiles.find((profile) => profile.is_active) ?? sellerProfiles[0] ?? null,
    [sellerProfiles],
  );
  const sellerProfileReady = Boolean(activeSellerProfile);

  useEffect(() => {
    if (authStatus !== "authenticated") return;
    async function loadData() {
      setIsBillingDataLoaded(false);
      try {
        const [profileResult, customerResult, productResult, invoiceResult] = await Promise.allSettled([
          apiRequest<SellerProfileResponse>("/companies/profile"),
          apiRequest<Customer[]>("/customers"),
          apiRequest<Product[]>("/products"),
          apiRequest<Invoice[]>("/invoices"),
        ]);
        const loadErrors: string[] = [];
        const sellerProfile = profileResult.status === "fulfilled" ? profileResult.value.seller_profile : null;
        const profileList = sellerProfile ? [sellerProfile] : [];
        if (profileResult.status === "rejected") loadErrors.push(`Seller profile: ${requestErrorMessage(profileResult.reason, "unable to load")}`);
        if (customerResult.status === "fulfilled") setCustomers(customerResult.value);
        else loadErrors.push(`Saved customers: ${requestErrorMessage(customerResult.reason, "unable to load")}`);
        if (productResult.status === "fulfilled") setProducts(productResult.value);
        else loadErrors.push(`Saved products: ${requestErrorMessage(productResult.reason, "unable to load")}`);
        if (invoiceResult.status === "fulfilled") setInvoices(invoiceResult.value);
        else loadErrors.push(`Recent invoices: ${requestErrorMessage(invoiceResult.reason, "unable to load")}`);
        setSellerProfiles(profileList);
        const activeProfile = profileList.find((profile) => profile.is_active) ?? profileList[0] ?? null;
        if (activeProfile?.state_code) {
          setPlaceOfSupplyStateCode(activeProfile.state_code);
          setManualBuyer((current) => ({ ...current, state_code: current.state_code || activeProfile.state_code }));
        }
        if (loadErrors.length) setError(`Some billing data could not load. ${loadErrors.join(" ")}`);
      } catch (requestError) {
        setError(requestErrorMessage(requestError, "Unable to load sales invoice data."));
      } finally {
        setIsBillingDataLoaded(true);
      }
    }
    void loadData();
  }, [authStatus]);

  useEffect(() => {
    if (entryMode === "saved" && selectedCustomer?.billing_address.state_code) {
      setPlaceOfSupplyStateCode(selectedCustomer.billing_address.state_code);
    }
  }, [entryMode, selectedCustomer]);

  useEffect(() => {
    if (entryMode !== "saved") return;
    setSavedConsignee(selectedCustomer ? consigneeFromCustomer(selectedCustomer) : blankParty());
  }, [entryMode, selectedCustomer]);

  useEffect(() => {
    if (entryMode === "manual" && manualBuyer.state_code) {
      setPlaceOfSupplyStateCode(manualBuyer.state_code);
    }
  }, [entryMode, manualBuyer.state_code]);

  const buildPayload = useCallback(() => ({
    ...(entryMode === "saved"
      ? {
          buyer_customer_id: asNumber(buyerCustomerId),
          ...(selectedCustomer ? { consignee: partyPayload(savedConsignee) } : {}),
        }
      : {
          buyer: partyPayload(manualBuyer),
          ...(!manualConsigneeSameAsBuyer ? { consignee: partyPayload(manualConsignee) } : {}),
        }),
    invoice_date: invoiceDate,
    delivery_note_date: deliveryNoteDate || null,
    place_of_supply_state_code: placeOfSupplyStateCode,
    po_number: poNumber || null,
    payment_terms: paymentTerms || null,
    transport_mode: transportMode || null,
    vehicle_number: vehicleNumber || null,
    vehicle_type: vehicleType || null,
    lr_number: lrNumber || null,
    lr_date: lrDate || null,
    expected_delivery_date: expectedDeliveryDate || null,
    freight_charges: freightCharges,
    packing_charges: packingCharges,
    other_charges: otherCharges,
    discount_amount: discountAmount,
    lines: lines.map((line) => ({
      ...(entryMode === "saved" ? { product_id: asNumber(line.product_id) } : { product_name: line.product_name }),
      description: line.description || null,
      hsn_sac: line.hsn_sac || null,
      quantity: line.quantity,
      unit: line.unit || null,
      rate: line.rate || null,
      other_charge: line.other_charge,
      discount_amount: line.discount_amount,
      gst_rate: line.gst_rate || null,
      cess_rate: line.cess_rate || null,
    })),
  }), [
    buyerCustomerId,
    discountAmount,
    deliveryNoteDate,
    entryMode,
    expectedDeliveryDate,
    freightCharges,
    invoiceDate,
    lrDate,
    lrNumber,
    lines,
    manualBuyer,
    manualConsignee,
    manualConsigneeSameAsBuyer,
    otherCharges,
    packingCharges,
    paymentTerms,
    placeOfSupplyStateCode,
    poNumber,
    savedConsignee,
    selectedCustomer,
    transportMode,
    vehicleNumber,
    vehicleType,
  ]);

  const canPreview = Boolean(
    sellerProfileReady &&
    invoiceDate &&
    placeOfSupplyStateCode &&
    (entryMode === "saved"
      ? selectedCustomer && manualPartyComplete(savedConsignee)
      : manualPartyComplete(manualBuyer) && (manualConsigneeSameAsBuyer || manualPartyComplete(manualConsignee))) &&
    lines.every((line) => lineComplete(line, entryMode)),
  );

  function validateInvoiceDraft() {
    if (!isBillingDataLoaded) return "Billing setup is still loading. Try again in a moment.";
    if (!sellerProfileReady) return "Set up Seller/GST profile first before saving sales invoices.";
    if (!invoiceDate) return "Enter the invoice date before saving.";
    if (!placeOfSupplyStateCode) return "Enter the place of supply state code before saving.";
    if (entryMode === "saved" && !buyerCustomerId) return "Select a saved buyer, or switch to Manual entry and enter the buyer details.";
    if (entryMode === "saved" && !manualPartyComplete(savedConsignee)) {
      return "Select a saved buyer, then enter the consignee name and remaining required details before saving.";
    }
    if (entryMode === "manual" && !manualPartyComplete(manualBuyer)) {
      return "Complete buyer name, address line 1, city, state, state code and postal code before saving.";
    }
    if (entryMode === "manual" && !manualConsigneeSameAsBuyer && !manualPartyComplete(manualConsignee)) {
      return "Complete consignee name, address line 1, city, state, state code and postal code before saving.";
    }

    const incompleteLineIndex = lines.findIndex((line) => !lineComplete(line, entryMode));
    if (incompleteLineIndex >= 0) {
      const lineNumber = incompleteLineIndex + 1;
      return entryMode === "saved"
        ? `Select a saved product and enter quantity for line ${lineNumber}.`
        : `Complete product name, HSN/SAC, quantity, unit, rate and GST for line ${lineNumber}.`;
    }

    return null;
  }

  useEffect(() => {
    if (authStatus !== "authenticated") {
      setPreview(null);
      return;
    }
    if (!canPreview) {
      setPreview(null);
      return;
    }
    const timeout = window.setTimeout(async () => {
      try {
        setPreview(await apiRequest<InvoicePreview>("/invoices/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(buildPayload()),
        }));
      } catch {
        setPreview(null);
      }
    }, 350);
    return () => window.clearTimeout(timeout);
  }, [authStatus, buildPayload, canPreview]);

  function updateParty(field: keyof PartyForm, value: string) {
    setManualBuyer((current) => ({ ...current, [field]: value }));
  }

  function updateConsignee(field: keyof PartyForm, value: string) {
    setManualConsignee((current) => ({ ...current, [field]: value }));
  }

  function updateSavedConsignee(field: keyof PartyForm, value: string) {
    setSavedConsignee((current) => ({ ...current, [field]: value }));
  }

  function updateLine(key: number, changes: Partial<DraftLine>) {
    setLines((current) => current.map((line) => (line.key === key ? { ...line, ...changes } : line)));
  }

  function chooseProduct(key: number, productId: string) {
    const product = products.find((item) => String(item.id) === productId);
    updateLine(key, {
      product_id: productId,
      product_name: product?.name ?? "",
      description: product?.description ?? product?.name ?? "",
      hsn_sac: product?.hsn_sac ?? "",
      unit: product?.unit ?? "KG",
      rate: product?.base_rate ?? "",
      gst_rate: product?.gst_rate ?? "18.00",
      cess_rate: product?.cess_rate ?? "0.00",
    });
  }

  async function reloadInvoices() {
    const [invoiceResult, customerResult, productResult] = await Promise.allSettled([
      apiRequest<Invoice[]>("/invoices"),
      apiRequest<Customer[]>("/customers"),
      apiRequest<Product[]>("/products"),
    ]);
    if (invoiceResult.status === "fulfilled") setInvoices(invoiceResult.value);
    if (customerResult.status === "fulfilled") setCustomers(customerResult.value);
    if (productResult.status === "fulfilled") setProducts(productResult.value);
    const failures = [invoiceResult, customerResult, productResult].filter((result) => result.status === "rejected");
    if (failures.length) throw failures[0].reason;
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);

    const validationError = validateInvoiceDraft();
    if (validationError) {
      setError(validationError);
      return;
    }

    setIsSaving(true);
    try {
      const saved = await apiRequest<Invoice>("/invoices", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
      });
      setSavedInvoice(saved);
      setMessage("Sales invoice draft saved. New customer/product values are now available for choice mode.");
      await reloadInvoices();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to save sales invoice draft.");
    } finally {
      setIsSaving(false);
    }
  }

  async function runAction(invoiceId: number, action: "submit" | "approve" | "generate-pdf") {
    setError(null);
    setMessage(null);
    try {
      const updated = await apiRequest<Invoice>(`/invoices/${invoiceId}/${action}`, { method: "POST" });
      setSavedInvoice((current) => (current?.id === invoiceId ? updated : current));
      setMessage(`Invoice ${action.replaceAll("-", " ")} completed.`);
      await reloadInvoices();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to update invoice.");
    }
  }

  async function downloadInvoice(invoiceId: number) {
    setError(null);
    setMessage(null);
    try {
      await downloadFile(`/invoices/${invoiceId}/pdf`, `invoice-${invoiceId}.pdf`);
      setMessage("Invoice PDF downloaded.");
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to download invoice PDF.");
    }
  }

  async function previewInvoice(invoiceId: number, autoPrint = false) {
    setError(null);
    try {
      await previewPdf(`/invoices/${invoiceId}/pdf`, `invoice-${invoiceId}.pdf`, autoPrint);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to open invoice PDF preview.");
    }
  }

  return (
    <AuthGateStatus status={authStatus}>
      <AppShell>
        <div className="w-full px-5 py-8 sm:px-8 lg:px-10 lg:py-10">
          <section>
            <Link href="/purchase-orders#recent-purchase-orders" className="inline-flex items-center rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-bold uppercase tracking-[0.12em] text-[#516bb1] shadow-sm transition hover:border-[#6f8fe8] hover:text-ink">
              Recent Purchase Orders
            </Link>
            <p className="mt-6 text-[11px] font-bold uppercase tracking-[0.22em] text-[#6f8fe8]">Sales invoice workflow</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-ink sm:text-[40px]">Sales invoice entry</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500 sm:text-[15px]">
              Use this for selling to vendors/customers. Start manual for new parties/items, or switch to choice mode after records have been saved.
              {activeSellerProfile ? ` Seller/GST profile: ${activeSellerProfile.name}.` : ""}
            </p>
          </section>

          {isBillingDataLoaded && !sellerProfileReady && (
            <div className="mt-6 rounded-xl border border-[#ffe1bd] bg-[#fff8ef] px-4 py-3 text-sm font-medium text-[#b46b22]">
              Set up Seller/GST profile first before creating bills.{" "}
              <Link className="font-bold underline decoration-[#b46b22]/40 underline-offset-4" href="/branches">
                Open Seller/GST profile
              </Link>
            </div>
          )}

          {(error || message) && (
            <div className={`mt-6 rounded-xl px-4 py-3 text-sm font-medium ${error ? "bg-[#fff0df] text-[#b46b22]" : "bg-[#dff8ee] text-[#24735b]"}`}>
              {error ?? message}
            </div>
          )}

          {savedInvoice && (
            <section className="mt-6 rounded-[22px] border border-[#cfdcff] bg-[#f0f4ff] p-5 sm:p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-[#516bb1]">Saved bill actions</p>
                  <h2 className="mt-2 text-lg font-semibold text-ink">{savedInvoice.invoice_number ?? `Draft #${savedInvoice.id}`}</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    {savedInvoice.status === "pdf_generated" ? "PDF is ready to preview, download or print." : "Submit this draft for approval before generating its PDF."}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {savedInvoice.status === "draft" && <button className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-[#516bb1]" onClick={() => void runAction(savedInvoice.id, "submit")} type="button">Submit for approval</button>}
                  {savedInvoice.status === "pending_approval" && <button className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-[#24735b]" onClick={() => void runAction(savedInvoice.id, "approve")} type="button">Approve</button>}
                  {savedInvoice.status === "approved" && <button className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-600" onClick={() => void runAction(savedInvoice.id, "generate-pdf")} type="button">Generate PDF</button>}
                  {savedInvoice.status === "pdf_generated" && <>
                    <button className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-[#516bb1]" onClick={() => void previewInvoice(savedInvoice.id)} type="button">Preview PDF</button>
                    <button className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-[#516bb1]" onClick={() => void downloadInvoice(savedInvoice.id)} type="button">Download PDF</button>
                    <button className="rounded-lg bg-ink px-3 py-2 text-xs font-semibold text-white" onClick={() => void previewInvoice(savedInvoice.id, true)} type="button">Print PDF</button>
                  </>}
                </div>
              </div>
            </section>
          )}

          <section className="mt-8">
            <form noValidate onSubmit={handleSave} className="w-full rounded-[22px] border border-slate-200/80 bg-white p-5 shadow-panel sm:p-6 lg:p-8">
              <div className="flex flex-wrap gap-2 rounded-2xl bg-slate-50 p-2">
                {(["manual", "saved"] as EntryMode[]).map((mode) => (
                  <button key={mode} type="button" onClick={() => setEntryMode(mode)} className={`${toggleClass} ${entryMode === mode ? "bg-ink text-white" : "text-slate-500 hover:bg-white"}`}>
                    {mode === "manual" ? "Manual entry" : "Use saved data"}
                  </button>
                ))}
              </div>

              <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {entryMode === "saved" ? (
                  <>
                    <label className="text-xs font-semibold text-slate-500">
                      Buyer
                      <select className={inputClass} onChange={(event) => setBuyerCustomerId(event.target.value)} required value={buyerCustomerId}>
                        <option value="">{customers.length ? "Select saved buyer" : "No saved buyers yet"}</option>
                        {customers.map((customer) => <option key={customer.id} value={customer.id}>{customer.name}{customer.gstin ? ` · ${customer.gstin}` : ""}</option>)}
                      </select>
                    </label>
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4 sm:col-span-2 lg:col-span-4">
                      <div>
                        <h2 className="text-sm font-semibold text-ink">Consignee details</h2>
                        <p className="mt-1 text-xs leading-5 text-slate-500">GSTIN and address are copied from the selected buyer. Enter the remaining consignee details manually.</p>
                      </div>
                      {selectedCustomer ? (
                        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                          <PartyFields fieldLabelPrefix="Consignee " party={savedConsignee} nameLabel="Consignee name" onChange={updateSavedConsignee} readOnlyFields={savedConsigneeCopiedFields} />
                        </div>
                      ) : (
                        <p className="mt-4 rounded-xl border border-dashed border-slate-200 bg-white px-3 py-3 text-xs text-slate-500">Select a saved buyer to load the shared GSTIN and address fields.</p>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    <PartyFields party={manualBuyer} nameLabel="Buyer/vendor name" onChange={updateParty} />
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4 sm:col-span-2 lg:col-span-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <h2 className="text-sm font-semibold text-ink">Consignee details</h2>
                          <p className="mt-1 text-xs leading-5 text-slate-500">Use a separate delivery party when goods ship to a different address.</p>
                        </div>
                        <label className="inline-flex items-center gap-2 text-xs font-semibold text-slate-600">
                          <input
                            aria-label="Consignee same as buyer"
                            checked={manualConsigneeSameAsBuyer}
                            className="h-4 w-4 accent-[#007c78]"
                            onChange={(event) => setManualConsigneeSameAsBuyer(event.target.checked)}
                            type="checkbox"
                          />
                          Consignee same as buyer
                        </label>
                      </div>
                      {!manualConsigneeSameAsBuyer && (
                        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                          <PartyFields fieldLabelPrefix="Consignee " party={manualConsignee} nameLabel="Consignee name" onChange={updateConsignee} />
                        </div>
                      )}
                    </div>
                  </>
                )}
                <label className="text-xs font-semibold text-slate-500">Invoice date<input className={inputClass} onChange={(event) => setInvoiceDate(event.target.value)} required type="date" value={invoiceDate} /></label>
                <label className="text-xs font-semibold text-slate-500">Delivery note date<input className={inputClass} onChange={(event) => setDeliveryNoteDate(event.target.value)} type="date" value={deliveryNoteDate} /></label>
                <label className="text-xs font-semibold text-slate-500">Place of supply state code<input className={inputClass} maxLength={2} onChange={(event) => setPlaceOfSupplyStateCode(event.target.value)} required value={placeOfSupplyStateCode} /></label>
                <label className="text-xs font-semibold text-slate-500">Customer PO number<input className={inputClass} onChange={(event) => setPoNumber(event.target.value)} value={poNumber} /></label>
                <label className="text-xs font-semibold text-slate-500 lg:col-span-2">Payment terms<AutoResizeTextarea className={inputClass} onChange={(event) => setPaymentTerms(event.target.value)} rows={1} value={paymentTerms} /></label>
                <label className="text-xs font-semibold text-slate-500">Dispatched through<input className={inputClass} onChange={(event) => setTransportMode(event.target.value)} value={transportMode} /></label>
                <label className="text-xs font-semibold text-slate-500">Vehicle number<input className={inputClass} onChange={(event) => setVehicleNumber(event.target.value)} value={vehicleNumber} /></label>
                <label className="text-xs font-semibold text-slate-500">Vehicle type<input className={inputClass} onChange={(event) => setVehicleType(event.target.value)} value={vehicleType} /></label>
                <label className="text-xs font-semibold text-slate-500">LR/Docket number<input className={inputClass} onChange={(event) => setLrNumber(event.target.value)} value={lrNumber} /></label>
                <label className="text-xs font-semibold text-slate-500">Transport document date<input className={inputClass} onChange={(event) => setLrDate(event.target.value)} type="date" value={lrDate} /></label>
                <label className="text-xs font-semibold text-slate-500">Expected delivery date<input className={inputClass} onChange={(event) => setExpectedDeliveryDate(event.target.value)} type="date" value={expectedDeliveryDate} /></label>
                <label className="text-xs font-semibold text-slate-500">Freight charges<input className={inputClass} onChange={(event) => setFreightCharges(event.target.value)} value={freightCharges} /></label>
                <label className="text-xs font-semibold text-slate-500">Packing charges<input className={inputClass} onChange={(event) => setPackingCharges(event.target.value)} value={packingCharges} /></label>
                <label className="text-xs font-semibold text-slate-500">Other charges<input className={inputClass} onChange={(event) => setOtherCharges(event.target.value)} value={otherCharges} /></label>
                <label className="text-xs font-semibold text-slate-500">Header discount<input className={inputClass} onChange={(event) => setDiscountAmount(event.target.value)} value={discountAmount} /></label>
              </div>

              <div className="mt-7 space-y-4">
                <div className="flex items-center justify-between gap-4">
                  <h2 className="text-lg font-semibold tracking-tight text-ink">Line items</h2>
                  <button className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-500 hover:text-ink" onClick={() => setLines((current) => [...current, initialLine(Date.now())])} type="button">Add line</button>
                </div>
                {lines.map((line, index) => (
                  <div key={line.key} className="rounded-2xl border border-slate-100 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-ink">Line {index + 1}</p>
                      {lines.length > 1 && <button className="text-xs font-semibold text-[#b46b22]" onClick={() => setLines((current) => current.filter((item) => item.key !== line.key))} type="button">Remove</button>}
                    </div>
                <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
                      {entryMode === "saved" ? (
                        <label className="text-xs font-semibold text-slate-500 lg:col-span-2">
                          Product
                          <select className={inputClass} onChange={(event) => chooseProduct(line.key, event.target.value)} required value={line.product_id}>
                            <option value="">{products.length ? "Select saved product" : "No saved products yet"}</option>
                            {products.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}
                          </select>
                        </label>
                      ) : (
                        <label className="text-xs font-semibold text-slate-500 lg:col-span-2">Product name<AutoResizeTextarea className={inputClass} onChange={(event) => updateLine(line.key, { product_name: event.target.value })} required rows={1} value={line.product_name} /></label>
                      )}
                      <label className="text-xs font-semibold text-slate-500 lg:col-span-3">Description<AutoResizeTextarea className={inputClass} onChange={(event) => updateLine(line.key, { description: event.target.value })} rows={1} value={line.description} /></label>
                      <label className="text-xs font-semibold text-slate-500">HSN/SAC<input className={inputClass} onChange={(event) => updateLine(line.key, { hsn_sac: event.target.value })} required={entryMode === "manual"} value={line.hsn_sac} /></label>
                      <label className="text-xs font-semibold text-slate-500">Quantity<input className={inputClass} onChange={(event) => updateLine(line.key, { quantity: event.target.value })} required value={line.quantity} /></label>
                      <label className="text-xs font-semibold text-slate-500">Unit<input className={inputClass} onChange={(event) => updateLine(line.key, { unit: event.target.value })} required={entryMode === "manual"} value={line.unit} /></label>
                      <label className="text-xs font-semibold text-slate-500">Rate<input className={inputClass} onChange={(event) => updateLine(line.key, { rate: event.target.value })} required={entryMode === "manual"} value={line.rate} /></label>
                      <label className="text-xs font-semibold text-slate-500">Other charge<input className={inputClass} onChange={(event) => updateLine(line.key, { other_charge: event.target.value })} value={line.other_charge} /></label>
                      <label className="text-xs font-semibold text-slate-500">Line discount<input className={inputClass} onChange={(event) => updateLine(line.key, { discount_amount: event.target.value })} value={line.discount_amount} /></label>
                      <label className="text-xs font-semibold text-slate-500">GST %<input className={inputClass} onChange={(event) => updateLine(line.key, { gst_rate: event.target.value })} required={entryMode === "manual"} value={line.gst_rate} /></label>
                      <label className="text-xs font-semibold text-slate-500">Cess %<input className={inputClass} onChange={(event) => updateLine(line.key, { cess_rate: event.target.value })} value={line.cess_rate} /></label>
                    </div>
                  </div>
                ))}
              </div>

              <button className="mt-6 w-full rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-white hover:bg-[#243653] disabled:cursor-not-allowed disabled:opacity-60" disabled={isSaving || !isBillingDataLoaded || !sellerProfileReady} type="submit">
                {isSaving ? "Saving draft…" : !sellerProfileReady ? "Set up Seller/GST profile first" : "Save sales invoice draft"}
              </button>
            </form>

            <div className="mt-6 grid gap-6 lg:grid-cols-2">
              <article className="rounded-[22px] border border-slate-200/80 bg-white p-5 shadow-panel sm:p-6">
                <h2 className="text-lg font-semibold tracking-tight text-ink">Live backend preview</h2>
                <div className="mt-5 grid gap-3 text-sm">
                  {[
                    ["Taxable value", preview?.taxable_value],
                    ["CGST", preview?.cgst_amount],
                    ["SGST", preview?.sgst_amount],
                    ["IGST", preview?.igst_amount],
                    ["Cess", preview?.cess_amount],
                    ["Round-off", preview?.round_off],
                    ["Final total", preview?.final_total],
                  ].map(([label, value]) => (
                    <div key={label} className="flex justify-between gap-4 border-b border-slate-100 pb-2 last:border-0">
                      <span className="text-slate-500">{label}</span>
                      <span className="font-semibold text-ink">{value ?? "—"}</span>
                    </div>
                  ))}
                </div>
                <p className="mt-4 text-xs leading-5 text-slate-400">{preview?.amount_in_words ?? "Complete required fields to preview backend totals."}</p>
              </article>

              <article className="rounded-[22px] border border-slate-200/80 bg-white p-5 shadow-panel sm:p-6">
                <h2 className="text-lg font-semibold tracking-tight text-ink">Recent sales invoices</h2>
                <div className="mt-4 space-y-3">
                  {invoices.map((invoice) => (
                    <div key={invoice.id} className="rounded-2xl border border-slate-100 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-ink">{invoice.invoice_number ?? `Draft #${invoice.id}`}</p>
                          <p className="mt-1 text-xs text-slate-400">{invoice.buyer_name} · {invoice.status.replaceAll("_", " ")}</p>
                        </div>
                        <p className="text-sm font-semibold text-ink">₹{invoice.final_total}</p>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {invoice.status === "draft" && <button className="rounded-lg bg-[#f0f4ff] px-3 py-2 text-xs font-semibold text-[#516bb1]" onClick={() => void runAction(invoice.id, "submit")} type="button">Submit</button>}
                        {invoice.status === "pending_approval" && <button className="rounded-lg bg-[#dff8ee] px-3 py-2 text-xs font-semibold text-[#24735b]" onClick={() => void runAction(invoice.id, "approve")} type="button">Approve</button>}
                        {invoice.status === "approved" && <button className="rounded-lg bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-500" onClick={() => void runAction(invoice.id, "generate-pdf")} type="button">Generate PDF</button>}
                        {invoice.status === "pdf_generated" && <>
                          <button className="rounded-lg bg-[#f0f4ff] px-3 py-2 text-xs font-semibold text-[#516bb1]" onClick={() => void previewInvoice(invoice.id)} type="button">Preview PDF</button>
                          <button className="rounded-lg bg-[#f0f4ff] px-3 py-2 text-xs font-semibold text-[#516bb1]" onClick={() => void downloadInvoice(invoice.id)} type="button">Download PDF</button>
                          <button className="rounded-lg bg-ink px-3 py-2 text-xs font-semibold text-white" onClick={() => void previewInvoice(invoice.id, true)} type="button">Print PDF</button>
                        </>}
                      </div>
                    </div>
                  ))}
                  {invoices.length === 0 && <p className="text-sm text-slate-400">No sales invoices yet.</p>}
                </div>
              </article>
            </div>
          </section>
        </div>
      </AppShell>
    </AuthGateStatus>
  );
}
