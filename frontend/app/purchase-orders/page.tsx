"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { AppShell } from "@/app/components/AppShell";
import { AutoResizeTextarea } from "@/app/components/AutoResizeTextarea";
import { AuthGateStatus, useAuthStatus } from "@/app/components/AuthGate";
import { ApiError, apiRequest, downloadFile, previewPdf } from "@/app/lib/api";
import type { Product, PurchaseOrder, SellerProfileResponse, Supplier } from "@/app/lib/types";

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
  const authStatus = useAuthStatus();
  const [entryMode, setEntryMode] = useState<EntryMode>("manual");
  const [sellerProfiles, setSellerProfiles] = useState<NonNullable<SellerProfileResponse["seller_profile"]>[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([]);
  const [supplierId, setSupplierId] = useState("");
  const [manualSupplier, setManualSupplier] = useState<PartyForm>(blankParty);
  const [orderDate, setOrderDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [expectedDeliveryDate, setExpectedDeliveryDate] = useState("");
  const [paymentTerms, setPaymentTerms] = useState("Advance before dispatch");
  const [discountAmount, setDiscountAmount] = useState("0.00");
  const [lines, setLines] = useState<DraftLine[]>([initialLine(1)]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isBillingDataLoaded, setIsBillingDataLoaded] = useState(false);
  const [savedPurchaseOrder, setSavedPurchaseOrder] = useState<PurchaseOrder | null>(null);
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
        const [profileResult, supplierResult, productResult, orderResult] = await Promise.allSettled([
          apiRequest<SellerProfileResponse>("/companies/profile"),
          apiRequest<Supplier[]>("/suppliers"),
          apiRequest<Product[]>("/products"),
          apiRequest<PurchaseOrder[]>("/purchase-orders"),
        ]);
        const loadErrors: string[] = [];
        const sellerProfile = profileResult.status === "fulfilled" ? profileResult.value.seller_profile : null;
        const profileList = sellerProfile ? [sellerProfile] : [];
        if (profileResult.status === "rejected") loadErrors.push(`Seller profile: ${requestErrorMessage(profileResult.reason, "unable to load")}`);
        if (supplierResult.status === "fulfilled") setSuppliers(supplierResult.value);
        else loadErrors.push(`Saved suppliers: ${requestErrorMessage(supplierResult.reason, "unable to load")}`);
        if (productResult.status === "fulfilled") setProducts(productResult.value);
        else loadErrors.push(`Saved products: ${requestErrorMessage(productResult.reason, "unable to load")}`);
        if (orderResult.status === "fulfilled") setPurchaseOrders(orderResult.value);
        else loadErrors.push(`Recent purchase orders: ${requestErrorMessage(orderResult.reason, "unable to load")}`);
        setSellerProfiles(profileList);
        const activeProfile = profileList.find((profile) => profile.is_active) ?? profileList[0] ?? null;
        if (activeProfile?.state_code) {
          setManualSupplier((current) => ({ ...current, state_code: current.state_code || activeProfile.state_code }));
        }
        if (loadErrors.length) setError(`Some purchase data could not load. ${loadErrors.join(" ")}`);
      } catch (requestError) {
        setError(requestErrorMessage(requestError, "Unable to load purchase order data."));
      } finally {
        setIsBillingDataLoaded(true);
      }
    }
    void loadData();
  }, [authStatus]);

  function updateSupplier(field: keyof PartyForm, value: string) {
    setManualSupplier((current) => ({ ...current, [field]: value }));
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
      ...(entryMode === "saved" ? { supplier_id: asNumber(supplierId) } : { supplier: supplierPayload(manualSupplier) }),
      order_date: orderDate,
      expected_delivery_date: expectedDeliveryDate || null,
      payment_terms: paymentTerms || null,
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
    };
  }

  function validatePurchaseOrder() {
    if (!isBillingDataLoaded) return "Billing setup is still loading. Try again in a moment.";
    if (!sellerProfileReady) return "Set up Seller/GST profile first before saving purchase orders.";
    if (!orderDate) return "Enter the PO date before saving.";
    if (entryMode === "saved" && !supplierId) return "Select a saved supplier, or switch to Manual entry and enter the supplier details.";
    if (entryMode === "manual" && !partyComplete(manualSupplier)) {
      return "Complete supplier name, address line 1, city, state, state code and postal code before saving.";
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

  async function reloadPurchaseOrders() {
    const [orderResult, supplierResult, productResult] = await Promise.allSettled([
      apiRequest<PurchaseOrder[]>("/purchase-orders"),
      apiRequest<Supplier[]>("/suppliers"),
      apiRequest<Product[]>("/products"),
    ]);
    if (orderResult.status === "fulfilled") setPurchaseOrders(orderResult.value);
    if (supplierResult.status === "fulfilled") setSuppliers(supplierResult.value);
    if (productResult.status === "fulfilled") setProducts(productResult.value);
    const failures = [orderResult, supplierResult, productResult].filter((result) => result.status === "rejected");
    if (failures.length) throw failures[0].reason;
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);

    const validationError = validatePurchaseOrder();
    if (validationError) {
      setError(validationError);
      return;
    }

    setIsSaving(true);
    try {
      const saved = await apiRequest<PurchaseOrder>("/purchase-orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
      });
      setSavedPurchaseOrder(saved);
      setMessage(`Purchase order ${saved.purchase_order_number} saved. Supplier/product values are now available for choice mode.`);
      await reloadPurchaseOrders();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to save purchase order.");
    } finally {
      setIsSaving(false);
    }
  }

  async function generatePurchaseOrderPdf(purchaseOrderId: number) {
    setError(null);
    setMessage(null);
    try {
      const generated = await apiRequest<PurchaseOrder>(`/purchase-orders/${purchaseOrderId}/generate-pdf`, { method: "POST" });
      setSavedPurchaseOrder((current) => (current?.id === purchaseOrderId ? generated : current));
      await reloadPurchaseOrders();
      setMessage("Purchase order PDF generated.");
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to generate purchase order PDF.");
    }
  }

  async function downloadPurchaseOrderPdf(purchaseOrderId: number) {
    setError(null);
    try {
      await downloadFile(`/purchase-orders/${purchaseOrderId}/pdf`, `purchase-order-${purchaseOrderId}.pdf`);
      setMessage("Purchase order PDF downloaded.");
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to download purchase order PDF.");
    }
  }

  async function previewPurchaseOrderPdf(purchaseOrderId: number, autoPrint = false) {
    setError(null);
    try {
      await previewPdf(`/purchase-orders/${purchaseOrderId}/pdf`, `purchase-order-${purchaseOrderId}.pdf`, autoPrint);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to open purchase order PDF preview.");
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
            <p className="mt-6 text-[11px] font-bold uppercase tracking-[0.22em] text-[#6f8fe8]">Purchase workflow</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-ink sm:text-[40px]">Purchase order entry</h1>
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

          {savedPurchaseOrder && (
            <section className="mt-6 rounded-[22px] border border-[#cfdcff] bg-[#f0f4ff] p-5 sm:p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-[#516bb1]">Saved bill actions</p>
                  <h2 className="mt-2 text-lg font-semibold text-ink">{savedPurchaseOrder.purchase_order_number}</h2>
                  <p className="mt-1 text-sm text-slate-500">Generate the PDF, then preview, download or print it whenever needed.</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {!savedPurchaseOrder.pdf_storage_key && <button className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-600" onClick={() => void generatePurchaseOrderPdf(savedPurchaseOrder.id)} type="button">Generate PDF</button>}
                  {savedPurchaseOrder.pdf_storage_key && <>
                    <button className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-[#516bb1]" onClick={() => void previewPurchaseOrderPdf(savedPurchaseOrder.id)} type="button">Preview PDF</button>
                    <button className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-[#516bb1]" onClick={() => void downloadPurchaseOrderPdf(savedPurchaseOrder.id)} type="button">Download PDF</button>
                    <button className="rounded-lg bg-ink px-3 py-2 text-xs font-semibold text-white" onClick={() => void previewPurchaseOrderPdf(savedPurchaseOrder.id, true)} type="button">Print PDF</button>
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
                  <label className="text-xs font-semibold text-slate-500">
                    Supplier
                    <select className={inputClass} onChange={(event) => setSupplierId(event.target.value)} required value={supplierId}>
                      <option value="">{suppliers.length ? "Select saved supplier" : "No saved suppliers yet"}</option>
                      {suppliers.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.name}</option>)}
                    </select>
                  </label>
                ) : (
                  <>
                    <label className="text-xs font-semibold text-slate-500">Supplier/provider name<input className={inputClass} onChange={(event) => updateSupplier("name", event.target.value)} required value={manualSupplier.name} /></label>
                    <label className="text-xs font-semibold text-slate-500">GSTIN<input className={inputClass} maxLength={15} onChange={(event) => updateSupplier("gstin", event.target.value.toUpperCase())} value={manualSupplier.gstin} /></label>
                    <label className="text-xs font-semibold text-slate-500">PAN<input className={inputClass} maxLength={10} onChange={(event) => updateSupplier("pan", event.target.value.toUpperCase())} value={manualSupplier.pan} /></label>
                    <label className="text-xs font-semibold text-slate-500">Phone<input className={inputClass} onChange={(event) => updateSupplier("phone", event.target.value)} value={manualSupplier.phone} /></label>
                    <label className="text-xs font-semibold text-slate-500">Email<input className={inputClass} onChange={(event) => updateSupplier("email", event.target.value)} type="email" value={manualSupplier.email} /></label>
                    <label className="text-xs font-semibold text-slate-500 lg:col-span-2">Address line 1<AutoResizeTextarea className={inputClass} onChange={(event) => updateSupplier("address_line1", event.target.value)} required rows={1} value={manualSupplier.address_line1} /></label>
                    <label className="text-xs font-semibold text-slate-500 lg:col-span-2">Address line 2<AutoResizeTextarea className={inputClass} onChange={(event) => updateSupplier("address_line2", event.target.value)} rows={1} value={manualSupplier.address_line2} /></label>
                    <label className="text-xs font-semibold text-slate-500">City<input className={inputClass} onChange={(event) => updateSupplier("city", event.target.value)} required value={manualSupplier.city} /></label>
                    <label className="text-xs font-semibold text-slate-500">State<input className={inputClass} onChange={(event) => updateSupplier("state", event.target.value)} required value={manualSupplier.state} /></label>
                    <label className="text-xs font-semibold text-slate-500">State code<input className={inputClass} maxLength={2} onChange={(event) => updateSupplier("state_code", event.target.value)} required value={manualSupplier.state_code} /></label>
                    <label className="text-xs font-semibold text-slate-500">Postal code<input className={inputClass} onChange={(event) => updateSupplier("postal_code", event.target.value)} required value={manualSupplier.postal_code} /></label>
                  </>
                )}
                <label className="text-xs font-semibold text-slate-500">PO date<input className={inputClass} onChange={(event) => setOrderDate(event.target.value)} required type="date" value={orderDate} /></label>
                <label className="text-xs font-semibold text-slate-500">Expected delivery date<input className={inputClass} onChange={(event) => setExpectedDeliveryDate(event.target.value)} type="date" value={expectedDeliveryDate} /></label>
                <label className="text-xs font-semibold text-slate-500 lg:col-span-2">Payment terms<AutoResizeTextarea className={inputClass} onChange={(event) => setPaymentTerms(event.target.value)} rows={1} value={paymentTerms} /></label>
                <label className="text-xs font-semibold text-slate-500">Header discount<input className={inputClass} onChange={(event) => setDiscountAmount(event.target.value)} value={discountAmount} /></label>
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
                      <label className="text-xs font-semibold text-slate-500">Line discount<input className={inputClass} onChange={(event) => updateLine(line.key, { discount_amount: event.target.value })} value={line.discount_amount} /></label>
                      <label className="text-xs font-semibold text-slate-500">GST %<input className={inputClass} onChange={(event) => updateLine(line.key, { gst_rate: event.target.value })} required={entryMode === "manual"} value={line.gst_rate} /></label>
                      <label className="text-xs font-semibold text-slate-500">Cess %<input className={inputClass} onChange={(event) => updateLine(line.key, { cess_rate: event.target.value })} value={line.cess_rate} /></label>
                    </div>
                  </div>
                ))}
              </div>

              <button className="mt-6 w-full rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-white hover:bg-[#243653] disabled:cursor-not-allowed disabled:opacity-60" disabled={isSaving || !isBillingDataLoaded || !sellerProfileReady} type="submit">
                {isSaving ? "Saving PO…" : !sellerProfileReady ? "Set up Seller/GST profile first" : "Save purchase order"}
              </button>
            </form>

            <div className="mt-6 grid gap-6 lg:grid-cols-2">
              <article id="recent-purchase-orders" className="rounded-[22px] border border-slate-200/80 bg-white p-5 shadow-panel sm:p-6">
              <h2 className="text-lg font-semibold tracking-tight text-ink">Recent purchase orders</h2>
              <div className="mt-4 space-y-3">
                {purchaseOrders.map((order) => (
                  <div key={order.id} className="rounded-2xl border border-slate-100 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-ink">{order.purchase_order_number}</p>
                        <p className="mt-1 text-xs text-slate-400">{order.supplier_name} · {order.status}</p>
                      </div>
                      <p className="text-sm font-semibold text-ink">₹{order.final_total}</p>
                    </div>
                    <p className="mt-3 text-xs leading-5 text-slate-400">{order.lines.length} line item{order.lines.length === 1 ? "" : "s"}</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {!order.pdf_storage_key && <button className="rounded-lg bg-[#f0f4ff] px-3 py-2 text-xs font-semibold text-[#516bb1]" onClick={() => void generatePurchaseOrderPdf(order.id)} type="button">Generate PDF</button>}
                      {order.pdf_storage_key && <>
                        <button className="rounded-lg bg-[#f0f4ff] px-3 py-2 text-xs font-semibold text-[#516bb1]" onClick={() => void previewPurchaseOrderPdf(order.id)} type="button">Preview PDF</button>
                        <button className="rounded-lg bg-[#f0f4ff] px-3 py-2 text-xs font-semibold text-[#516bb1]" onClick={() => void downloadPurchaseOrderPdf(order.id)} type="button">Download PDF</button>
                        <button className="rounded-lg bg-ink px-3 py-2 text-xs font-semibold text-white" onClick={() => void previewPurchaseOrderPdf(order.id, true)} type="button">Print PDF</button>
                      </>}
                    </div>
                  </div>
                ))}
                {purchaseOrders.length === 0 && <p className="text-sm text-slate-400">No purchase orders yet.</p>}
              </div>
              </article>
            </div>
          </section>
        </div>
      </AppShell>
    </AuthGateStatus>
  );
}
