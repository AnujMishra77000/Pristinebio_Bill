"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { AppShell } from "@/app/components/AppShell";
import { AppIcon } from "@/app/components/AppIcon";
import { AutoResizeTextarea } from "@/app/components/AutoResizeTextarea";
import { AuthGateStatus, type AuthStatus } from "@/app/components/AuthGate";
import { RetainedBillEntry } from "@/app/components/RetainedBillEntry";
import { PageHeader } from "@/app/components/PageHeader";
import { BillSubmissionPanel } from "@/app/components/BillSubmissionPanel";
import { SavedBillLoadError } from "@/app/components/SavedBillLoadError";
import { PurchaseOrderSellerFields, PurchaseOrderShippingDetails, purchaseOrderSellerValues } from "@/app/components/PurchaseOrderSellerFields";
import { ApiError, apiRequest } from "@/app/lib/api";
import { useBillSubmission } from "@/app/lib/useBillSubmission";
import { useSavedBillLoader } from "@/app/lib/useSavedBillLoader";
import { useInvoiceEntryValue, type InvoiceEntrySession } from "@/app/lib/invoiceEntrySession";
import { indiaDateInputValue } from "@/app/lib/indiaDate";
import type { InvoicePreview, Product, PurchaseOrder, SellerProfileResponse, Supplier } from "@/app/lib/types";

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
  gst_rate: string;
  cess_rate: string;
};

const inputClass = "ui-input";

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

function supplierToParty(supplier: Supplier): PartyForm {
  return {
    name: supplier.name,
    gstin: supplier.gstin ?? "",
    pan: supplier.pan ?? "",
    email: supplier.email ?? "",
    phone: supplier.phone ?? "",
    address_line1: supplier.address.address_line1 ?? "",
    address_line2: supplier.address.address_line2 ?? "",
    city: supplier.address.city ?? "",
    state: supplier.address.state ?? "",
    state_code: supplier.address.state_code ?? "",
    postal_code: supplier.address.postal_code ?? "",
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
  gst_rate: "18.00",
  cess_rate: "0.00",
});

function asNumber(value: string) {
  return Number(value);
}

function supplierPayload(supplier: PartyForm) {
  return {
    name: supplier.name,
    gstin: supplier.gstin || null,
    pan: supplier.pan || null,
    email: supplier.email || null,
    phone: supplier.phone || null,
    address: {
      name: supplier.name,
      address_line1: supplier.address_line1,
      address_line2: supplier.address_line2 || null,
      city: supplier.city,
      state: supplier.state,
      state_code: supplier.state_code,
      postal_code: supplier.postal_code,
    },
    is_active: true,
  };
}

function partyComplete(party: PartyForm) {
  return Boolean(party.name && party.address_line1 && party.city && party.state && party.state_code && party.postal_code);
}

function lineComplete(line: DraftLine, mode: EntryMode) {
  if (!line.quantity) return false;
  if (mode === "saved") return Boolean(line.product_id);
  return Boolean(line.product_name && line.hsn_sac && line.unit && line.rate && line.gst_rate);
}

function requestErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export default function PurchaseOrdersPage() {
  return <RetainedBillEntry kind="purchase">{props => <PurchaseOrderForm {...props} />}</RetainedBillEntry>;
}

function PurchaseOrderForm({ entry, authStatus }: { entry: InvoiceEntrySession; authStatus: AuthStatus }) {
  const [entryMode] = useState<EntryMode>("manual");
  const [sellerProfiles, setSellerProfiles] = useState<NonNullable<SellerProfileResponse["seller_profile"]>[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [supplierId, setSupplierId] = useInvoiceEntryValue(entry, "supplierId", "");
  const [manualSupplier, setManualSupplier] = useInvoiceEntryValue<PartyForm>(entry, "manualSupplier", blankParty);
  const [orderDate, setOrderDate] = useInvoiceEntryValue(entry, "orderDate", indiaDateInputValue);
  const [purchaseOrderNumber, setPurchaseOrderNumber] = useInvoiceEntryValue(entry, "purchaseOrderNumber", "");
  const [purchaseOrderNumberError, setPurchaseOrderNumberError] = useInvoiceEntryValue<string | null>(entry, "purchaseOrderNumberError", null);
  const [supplierErrors, setSupplierErrors] = useInvoiceEntryValue<Record<string, string>>(entry, "supplierErrors", () => ({}));
  const [expectedDeliveryDate, setExpectedDeliveryDate] = useInvoiceEntryValue(entry, "expectedDeliveryDate", "");
  const [transportMode, setTransportMode] = useInvoiceEntryValue(entry, "transportMode", "");
  const [paymentTerms, setPaymentTerms] = useInvoiceEntryValue(entry, "paymentTerms", "Advance before dispatch");
  const [lines, setLines] = useInvoiceEntryValue<DraftLine[]>(entry, "lines", () => [initialLine(1)]);
  const [error, setError] = useInvoiceEntryValue<string | null>(entry, "error", null);
  const [message, setMessage] = useInvoiceEntryValue<string | null>(entry, "message", null);
  const [preview, setPreview] = useState<InvoicePreview | null>(null);
  const [isBillingDataLoaded, setIsBillingDataLoaded] = useState(false);
  const [versionConflict, setVersionConflict] = useInvoiceEntryValue(entry, "versionConflict", false);
  const activeSellerProfile = useMemo(
    () => sellerProfiles.find((profile) => profile.is_active) ?? sellerProfiles[0] ?? null,
    [sellerProfiles],
  );
  const sellerProfileReady = Boolean(activeSellerProfile);

  useEffect(() => {
    if (authStatus !== "authenticated") return;
    let cancelled = false;
    async function loadData() {
      setIsBillingDataLoaded(false);
      try {
        const [profileResult, supplierResult, productResult] = await Promise.allSettled([
          apiRequest<SellerProfileResponse>("/companies/profile"),
          apiRequest<Supplier[]>("/suppliers"),
          apiRequest<Product[]>("/products"),
        ]);
        if (cancelled || !entry.active) return;
        const loadErrors: string[] = [];
        const sellerProfile = profileResult.status === "fulfilled" ? profileResult.value.seller_profile : null;
        const profileList = sellerProfile ? [sellerProfile] : [];
        if (profileResult.status === "rejected") loadErrors.push(`Seller profile: ${requestErrorMessage(profileResult.reason, "unable to load")}`);
        if (supplierResult.status === "fulfilled") {
          setSuppliers(supplierResult.value);
          const savedSupplier = supplierResult.value.find((supplier) => supplier.is_active && supplier.is_default) ?? supplierResult.value.find((supplier) => supplier.is_active) ?? null;
          if (!entry.read("supplierInitialized", false)) {
            if (!entry.read("supplierId", "") && !entry.read("manualSupplier", blankParty()).name.trim()) {
              setSupplierId(savedSupplier ? String(savedSupplier.id) : "");
              if (savedSupplier) setManualSupplier(supplierToParty(savedSupplier));
            }
            entry.write("supplierInitialized", true);
          }
        }
        else loadErrors.push(`Saved suppliers: ${requestErrorMessage(supplierResult.reason, "unable to load")}`);
        if (productResult.status === "fulfilled") setProducts(productResult.value);
        else loadErrors.push(`Saved products: ${requestErrorMessage(productResult.reason, "unable to load")}`);
        setSellerProfiles(profileList);
        const activeProfile = profileList.find((profile) => profile.is_active) ?? profileList[0] ?? null;
        if (activeProfile?.state_code) {
          setManualSupplier((current) => ({ ...current, state_code: current.state_code || activeProfile.state_code }));
        }
        if (loadErrors.length) setError(`Some purchase data could not load. ${loadErrors.join(" ")}`);
      } catch (requestError) {
        if (cancelled || !entry.active) return;
        setError(requestErrorMessage(requestError, "Unable to load purchase order data."));
      } finally {
        if (!cancelled && entry.active) setIsBillingDataLoaded(true);
      }
    }
    void loadData();
    return () => { cancelled = true; };
  }, [authStatus, entry, setSupplierId, setManualSupplier, setError]);

  function updateSupplier(field: keyof PartyForm, value: string) {
    setManualSupplier((current) => ({ ...current, [field]: value }));
    setSupplierErrors({});
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

  function buildPayload() {
    return {
      ...(supplierId ? { supplier_id: asNumber(supplierId) } : { supplier: supplierPayload(manualSupplier) }),
      order_date: orderDate,
      ...(purchaseOrderNumber.trim() ? { purchase_order_number: purchaseOrderNumber.trim() } : {}),
      expected_delivery_date: expectedDeliveryDate || null,
      transport_mode: transportMode.trim() || null,
      payment_terms: paymentTerms || null,
      lines: lines.map((line) => ({
        ...(line.product_id ? { product_id: asNumber(line.product_id) } : {}),
        product_name: line.product_name || null,
        description: line.description || null,
        hsn_sac: line.hsn_sac || null,
        quantity: line.quantity,
        unit: line.unit || null,
        rate: line.rate || null,
        other_charge: line.other_charge,
        gst_rate: line.gst_rate || null,
        cess_rate: line.cess_rate || null,
      })),
    };
  }

  function validatePurchaseOrder() {
    if (!isBillingDataLoaded) return "Billing setup is still loading. Try again in a moment.";
    if (!sellerProfileReady) return "Set up Seller/GST profile first before saving purchase orders.";
    if (!orderDate) return "Enter the PO date before saving.";
    if (!supplierId && !partyComplete(manualSupplier)) {
      return "Complete seller name, address line 1, city, state, state code and postal code before saving.";
    }

    const incompleteLineIndex = lines.findIndex((line) => !lineComplete(line, entryMode));
    if (incompleteLineIndex >= 0) {
      const lineNumber = incompleteLineIndex + 1;
      return entryMode === "saved"
        ? `Select a saved material and enter quantity for line ${lineNumber}.`
        : `Complete material name, HSN/SAC, quantity, unit, rate and GST for line ${lineNumber}.`;
    }

    return null;
  }

  async function reloadPurchaseMasters() {
    const [supplierResult, productResult] = await Promise.allSettled([
      apiRequest<Supplier[]>("/suppliers"),
      apiRequest<Product[]>("/products"),
    ]);
    if (supplierResult.status === "fulfilled") setSuppliers(supplierResult.value);
    if (productResult.status === "fulfilled") setProducts(productResult.value);
    const failures = [supplierResult, productResult].filter((result) => result.status === "rejected");
    if (failures.length) throw failures[0].reason;
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPurchaseOrderNumberError(null);
    setSupplierErrors({});
    setMessage(null);
    await submission.save();
  }
  const payload = buildPayload();
  const signature = JSON.stringify(payload);
  const ready = !validatePurchaseOrder();
  const submission = useBillSubmission<PurchaseOrder>({
    entrySession: entry,
    collection: "/purchase-orders", payload, updateField: "domestic_details", validate: (): string | null => savedBill.blocked ? "Load the saved order successfully before saving; your fields are retained." : validatePurchaseOrder(),
    onCreated: reloadPurchaseMasters,
    onReturned: () => savedBill.reloadLatest(),
    onStartNew: (): void => {
      submission.reset();
      const supplier = suppliers.find((item) => item.is_active && item.is_default) ?? suppliers.find((item) => item.is_active);
      setSupplierId(supplier ? String(supplier.id) : ""); setManualSupplier(supplier ? supplierToParty(supplier) : blankParty());
      setOrderDate(indiaDateInputValue()); setPurchaseOrderNumber(""); setExpectedDeliveryDate(""); setTransportMode("");
      setPaymentTerms("Advance before dispatch"); setLines([initialLine(1)]); setPreview(null); setError(null); setMessage(null);
      setVersionConflict(false); setPurchaseOrderNumberError(null); setSupplierErrors({});
    },
    onFailure: (failure) => {
      if (!(failure instanceof ApiError)) return;
      const detail = failure.detail;
      setVersionConflict(failure.status === 409 && typeof detail === "object" && detail !== null && "code" in detail && detail.code === "version_conflict");
      if (Array.isArray(detail)) {
        setSupplierErrors(Object.fromEntries(detail.map((issue: { loc?: (string | number)[]; msg?: string }) => [
          (issue.loc ?? []).filter((part) => part !== "body" && part !== "domestic_details").join("."), issue.msg ?? "Invalid value",
        ])));
        const issue = detail.find((item: { loc?: (string | number)[] }) => item.loc?.includes("purchase_order_number"));
        if (issue) setPurchaseOrderNumberError(issue.msg ?? "Enter a valid PO No.");
      } else if (detail && typeof detail === "object" && "field" in detail && detail.field === "purchase_order_number") {
        setPurchaseOrderNumberError("message" in detail ? String(detail.message) : "Enter a different PO No.");
      }
    },
  });
  const savedBill = useSavedBillLoader<PurchaseOrder>({
    collection: "/purchase-orders", parameter: "order", documentType: "domestic_oils", authenticated: authStatus === "authenticated", ready: isBillingDataLoaded,
    document: submission.document, busy: submission.busy, unsaved: submission.unsaved,
    hasWork: Boolean(submission.document || purchaseOrderNumber || lines.some((line) => line.product_name || line.product_id)),
    hydrate: (order) => {
      setSupplierId(String(order.supplier_id)); setManualSupplier(purchaseOrderSellerValues(order));
      setOrderDate(order.order_date); setPurchaseOrderNumber(order.purchase_order_number);
      setExpectedDeliveryDate(order.expected_delivery_date ?? ""); setTransportMode(order.transport_mode ?? ""); setPaymentTerms(order.payment_terms ?? "");
      setLines(order.lines.map((line, index) => ({ ...initialLine(index + 1), ...line, key: index + 1, product_id: String(line.product_id) })));
      submission.restore(order); setVersionConflict(false); setError(null); setMessage(`Loaded ${order.purchase_order_number}. ${["draft", "amendment_pending"].includes(order.status) ? "Edit this saved revision, then Preview and Confirm." : "Submitted/finalized financial data is read-only."}`);
    },
  });
  const isSaving = submission.busy;
  const displayedSeller = submission.document ? purchaseOrderSellerValues(submission.document) : manualSupplier;
  useEffect(() => {
    const order = submission.document;
    if (!order) return;
    const snapshot = purchaseOrderSellerValues(order);
    const unchanged = supplierId ? Number(supplierId) === order.supplier_id
      : (Object.keys(snapshot) as (keyof PartyForm)[]).every((field) => manualSupplier[field].trim() === snapshot[field].trim());
    if (unchanged) return;
    // A retry may recover a committed creation before a changed-seller PATCH
    // fails. Restore only its fixed identity; retain all other entered fields.
    setSupplierId(String(order.supplier_id));
    setManualSupplier(snapshot);
  }, [submission.document, supplierId, manualSupplier, setSupplierId, setManualSupplier]);
  useEffect(() => {
    if (!ready || savedBill.blocked || authStatus !== "authenticated") { setPreview(null); return; }
    let cancelled = false;
    setPreview(null);
    const timer = window.setTimeout(() => {
      void apiRequest<InvoicePreview>("/purchase-orders/preview", { method: "POST", body: signature })
        .then((result) => { if (!cancelled) setPreview(result); }).catch(() => { if (!cancelled) setPreview(null); });
    }, 350);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [authStatus, ready, signature, savedBill.blocked]);

  return (
    <AuthGateStatus status={authStatus}>
      <AppShell>
        <div className="workspace-page">
          <PageHeader icon="purchase-order" eyebrow="Purchase workflow" title="Purchase order entry" description="Capture supplier and raw material details in one readable workspace. Your entries remain separate from sales invoices." />

          {isBillingDataLoaded && !sellerProfileReady && (
            <div className="ui-alert mt-6 border-amber-200 bg-amber-50 text-amber-900">
              Set up Seller/GST profile first before creating bills.{" "}
              <Link className="font-bold underline decoration-[#b46b22]/40 underline-offset-4" href="/branches">
                Open Seller/GST profile
              </Link>
            </div>
          )}

          {(error || message) && (
            <div className={`ui-alert mt-6 ${error ? "border-red-200 bg-red-50 text-red-800" : "border-emerald-200 bg-warm-green text-peacock"}`} role={error ? "alert" : "status"}>
              {error ?? message}
            </div>
          )}

          <SavedBillLoadError loader={savedBill} />
          {versionConflict && <button className="ui-button mt-3" type="button" disabled={submission.busy} onClick={savedBill.reloadLatest}>Reload latest revision</button>}

          <section className="mt-8">
            <form data-bill-entry noValidate onSubmit={handleSave} className="ui-panel w-full p-5 sm:p-7 lg:p-8">
              <fieldset disabled={submission.locked || savedBill.blocked} className="min-w-0">
              <section className="mt-6 rounded-2xl border border-line p-4 sm:p-5" aria-label="Seller">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="text-base font-bold text-ink">Seller</h2>
                  <Link href="/suppliers" className="ui-button px-3 py-2 text-xs"><AppIcon name="suppliers" size={15} />Manage sellers</Link>
                </div>
                <label className="ui-label mt-4 block max-w-xl">Saved seller
                  <select aria-label="Saved seller" className={inputClass} disabled={Boolean(submission.document)} value={supplierId} onChange={(event) => {
                    const id = event.target.value;
                    setSupplierId(id);
                    const selected = suppliers.find((supplier) => String(supplier.id) === id);
                    setManualSupplier(selected ? supplierToParty(selected) : blankParty());
                    setSupplierErrors({});
                  }}>
                    <option value="">Enter seller manually</option>
                    {suppliers.filter((supplier) => supplier.is_active || String(supplier.id) === supplierId).map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.name}{supplier.is_default ? " · Default" : ""}</option>)}
                  </select>
                  {supplierErrors.supplier_id && <span className="mt-1 block text-xs text-red-700" role="alert">{supplierErrors.supplier_id}</span>}
                </label>
                <PurchaseOrderSellerFields details={displayedSeller} onChange={updateSupplier} errors={supplierErrors} readOnly={Boolean(supplierId) || Boolean(submission.document)} />
                {submission.document && <p className="mt-3 text-xs text-slate-500">The seller is fixed for this saved order. Start a new order to choose another seller.</p>}
              </section>
              <PurchaseOrderShippingDetails details={displayedSeller} />

              <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <label className="text-xs font-semibold text-slate-500">PO No.<input aria-label="PO No." readOnly={Boolean(submission.document?.correction)} aria-invalid={Boolean(purchaseOrderNumberError)} aria-describedby={purchaseOrderNumberError ? "po-number-error" : "po-number-hint"} className={inputClass} maxLength={100} onChange={(event) => { setPurchaseOrderNumber(event.target.value.toUpperCase()); setPurchaseOrderNumberError(null); }} placeholder="Enter your full PO number" value={purchaseOrderNumber} />{purchaseOrderNumberError ? <span id="po-number-error" role="alert" className="mt-1 block text-xs text-red-700">{purchaseOrderNumberError}</span> : <span id="po-number-hint" className="mt-1 block text-xs font-normal">{submission.document?.correction ? "The confirmed order number is fixed." : "Leave blank for automatic numbering."}</span>}</label>
                <label className="text-xs font-semibold text-slate-500">PO date<input className={inputClass} onChange={(event) => setOrderDate(event.target.value)} required type="date" value={orderDate} /></label>
                <label className="text-xs font-semibold text-slate-500">Expected delivery date<input className={inputClass} onChange={(event) => setExpectedDeliveryDate(event.target.value)} type="date" value={expectedDeliveryDate} /></label>
                <label className="text-xs font-semibold text-slate-500">Dispatched through<input aria-label="Dispatched through" aria-invalid={Boolean(supplierErrors.transport_mode)} aria-describedby={supplierErrors.transport_mode ? "po-dispatch-error" : undefined} className={inputClass} maxLength={100} placeholder="e.g. ROAD, RAIL or Courier" type="text" value={transportMode} onChange={(event) => { setTransportMode(event.target.value); setSupplierErrors((current) => { const next = { ...current }; delete next.transport_mode; return next; }); }} />{supplierErrors.transport_mode && <span id="po-dispatch-error" role="alert" className="mt-1 block text-xs text-red-700">{supplierErrors.transport_mode}</span>}</label>
                <label className="text-xs font-semibold text-slate-500 lg:col-span-2">Payment terms<AutoResizeTextarea className={inputClass} onChange={(event) => setPaymentTerms(event.target.value)} rows={1} value={paymentTerms} /></label>
              </div>

              <div className="mt-7 space-y-4">
                <div className="flex items-center justify-between gap-4">
                  <h2 className="text-lg font-semibold tracking-tight text-ink">Raw material lines</h2>
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
                          Product/material
                          <select className={inputClass} onChange={(event) => chooseProduct(line.key, event.target.value)} required value={line.product_id}>
                            <option value="">{products.length ? "Select saved material" : "No saved materials yet"}</option>
                            {products.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}
                          </select>
                        </label>
                      ) : (
                        <label className="text-xs font-semibold text-slate-500 lg:col-span-2">Material name<AutoResizeTextarea className={inputClass} onChange={(event) => updateLine(line.key, { product_name: event.target.value })} required rows={1} value={line.product_name} /></label>
                      )}
                      <label className="text-xs font-semibold text-slate-500 lg:col-span-3">Description<AutoResizeTextarea className={inputClass} onChange={(event) => updateLine(line.key, { description: event.target.value })} rows={1} value={line.description} /></label>
                      <label className="text-xs font-semibold text-slate-500">HSN/SAC<input className={inputClass} onChange={(event) => updateLine(line.key, { hsn_sac: event.target.value })} required={entryMode === "manual"} value={line.hsn_sac} /></label>
                      <label className="text-xs font-semibold text-slate-500">Quantity<input className={inputClass} onChange={(event) => updateLine(line.key, { quantity: event.target.value })} required value={line.quantity} /></label>
                      <label className="text-xs font-semibold text-slate-500">Unit<input className={inputClass} onChange={(event) => updateLine(line.key, { unit: event.target.value })} required={entryMode === "manual"} value={line.unit} /></label>
                      <label className="text-xs font-semibold text-slate-500">Rate<input className={inputClass} onChange={(event) => updateLine(line.key, { rate: event.target.value })} required={entryMode === "manual"} value={line.rate} /></label>
                      <label className="text-xs font-semibold text-slate-500">Other charge<input className={inputClass} onChange={(event) => updateLine(line.key, { other_charge: event.target.value })} value={line.other_charge} /></label>
                      <label className="text-xs font-semibold text-slate-500">GST %<input className={inputClass} onChange={(event) => updateLine(line.key, { gst_rate: event.target.value })} required={entryMode === "manual"} value={line.gst_rate} /></label>
                      <label className="text-xs font-semibold text-slate-500">Cess %<input className={inputClass} onChange={(event) => updateLine(line.key, { cess_rate: event.target.value })} value={line.cess_rate} /></label>
                    </div>
                  </div>
                ))}
              </div>

              <button className="mt-6 w-full rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-white hover:bg-[#132f40] disabled:cursor-not-allowed disabled:opacity-60" disabled={isSaving || !isBillingDataLoaded || !sellerProfileReady} type="submit">
                {isSaving ? "Saving PO…" : !sellerProfileReady ? "Set up Seller/GST profile first" : "Save purchase order"}
              </button>
              </fieldset>
            </form>
            <article className="ui-panel mt-6">
              <h2 className="ui-section-title">Live backend preview</h2>
              <dl className="mt-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">{[["Taxable value", preview?.taxable_value], ["CGST", preview?.cgst_amount], ["SGST", preview?.sgst_amount], ["IGST", preview?.igst_amount], ["Round-off", preview?.round_off], ["Final total", preview?.final_total]].map(([label, value]) => <div key={label}><dt className="text-xs text-slate">{label}</dt><dd className="mt-1 font-semibold text-ink">{value ?? "—"}</dd></div>)}</dl>
              <p className="mt-4 text-xs text-slate">{preview?.amount_in_words ?? "Complete required fields to preview backend totals."}</p>
            </article>
            <BillSubmissionPanel submission={submission} ready={ready && !savedBill.blocked} documentNumber={submission.document?.purchase_order_number} />
            {submission.document?.status === "approved" && <button className="ui-button mt-4" disabled={submission.busy} type="button" onClick={() => { const reason = window.prompt("Reason for this amendment:"); if (reason?.trim()) void submission.amend(reason); }}>Request amendment</button>}

          </section>
        </div>
      </AppShell>
    </AuthGateStatus>
  );
}
