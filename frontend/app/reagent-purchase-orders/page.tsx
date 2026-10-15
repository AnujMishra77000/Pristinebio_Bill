"use client";

import Link from "next/link";
import { cloneElement, isValidElement, type FormEvent, type ReactElement, type ReactNode, useEffect, useMemo, useState } from "react";
import { AppShell } from "@/app/components/AppShell";
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
import type { InvoicePreview, Manufacturer, Product, PurchaseOrder, SellerProfileResponse, Supplier } from "@/app/lib/types";

type Party = { name: string; gstin: string; pan: string; email: string; phone: string; address_line1: string; address_line2: string; city: string; state: string; state_code: string; postal_code: string };
type Line = { key: number; product_id: string; product_name: string; description: string; manufacturer_id: string; part_no: string; pack_size: string; hsn_sac: string; quantity: string; unit: string; rate: string; gst_rate: string; discount_percent: string };
type Details = { purchase_order_number: string; order_date: string; delivery_note_date: string; place_of_supply_state_code: string; po_reference_number: string; po_reference_date: string; payment_terms: string; transport_mode: string; vehicle_number: string; vehicle_type: string; lr_number: string; lr_date: string; expected_delivery_date: string; freight_charges: string; packing_charges: string; other_charges: string; discount_amount: string };
type Errors = Record<string, string>;
const units = [["g", "Gram — GM"], ["kg", "Kilogram — KG"], ["mg", "Milligram — MG"], ["µg", "Microgram — µg"], ["mL", "Millilitre — ML"], ["L", "Litre — L"], ["t", "Tonne — TON"]];
const blankParty = (): Party => ({ name: "", gstin: "", pan: "", email: "", phone: "", address_line1: "", address_line2: "", city: "", state: "", state_code: "36", postal_code: "" });
const blankLine = (key: number): Line => ({ key, product_id: "", product_name: "", description: "", manufacturer_id: "", part_no: "", pack_size: "", hsn_sac: "", quantity: "1.000", unit: "kg", rate: "", gst_rate: "18.00", discount_percent: "0.00" });
const blankDetails = (): Details => ({ purchase_order_number: "", order_date: indiaDateInputValue(), delivery_note_date: "", place_of_supply_state_code: "36", po_reference_number: "", po_reference_date: "", payment_terms: "30 days", transport_mode: "", vehicle_number: "", vehicle_type: "", lr_number: "", lr_date: "", expected_delivery_date: "", freight_charges: "0.00", packing_charges: "0.00", other_charges: "0.00", discount_amount: "0.00" });
function partyFromMaster(party: Supplier | NonNullable<PurchaseOrder["consignee"]>): Party {
  return { name: party.name, gstin: party.gstin ?? "", pan: party.pan ?? "", email: party.email ?? "", phone: party.phone ?? "", address_line1: party.address.address_line1 ?? "", address_line2: party.address.address_line2 ?? "", city: party.address.city ?? "", state: party.address.state ?? "", state_code: party.address.state_code ?? "", postal_code: party.address.postal_code ?? "" };
}
function partyPayload(party: Party) {
  return { name: party.name, gstin: party.gstin || null, pan: party.pan || null, email: party.email || null, phone: party.phone || null, is_active: true, address: { name: party.name, address_line1: party.address_line1, address_line2: party.address_line2 || null, city: party.city, state: party.state, state_code: party.state_code, postal_code: party.postal_code } };
}
function partyComplete(party: Party) { return [party.name, party.address_line1, party.city, party.state, party.state_code, party.postal_code].every((value) => value.trim()); }
function errorsFrom(error: unknown): Errors {
  if (!(error instanceof ApiError)) return {};
  if (!Array.isArray(error.detail)) {
    const detail = error.detail;
    if (detail && typeof detail === "object" && "field" in detail && typeof detail.field === "string" && "message" in detail) return { [detail.field]: String(detail.message) };
    return {};
  }
  return Object.fromEntries(error.detail.map((item: { loc?: (string | number)[]; msg?: string }) => [(item.loc ?? []).filter((value) => value !== "body" && value !== "reagent_details").join("."), item.msg ?? "Invalid value"]));
}
function Field({ name, label, errors, children, wide = false }: { name: string; label: string; errors: Errors; children: ReactNode; wide?: boolean }) {
  const child = isValidElement(children) ? children as ReactElement<{ id?: string; "aria-label"?: string; "aria-invalid"?: boolean; "aria-describedby"?: string }> : null;
  const control = child ? cloneElement(child, { id: name, "aria-label": child.props["aria-label"] ?? label, "aria-invalid": Boolean(errors[name]), "aria-describedby": errors[name] ? `${name}-error` : undefined }) : children;
  return <label htmlFor={name} className={`ui-label block ${wide ? "sm:col-span-2" : ""}`}>{label}{control}{errors[name] && <span id={`${name}-error`} className="mt-1 block text-xs text-red-700" role="alert">{errors[name]}</span>}</label>;
}
export default function ReagentPurchaseOrdersPage() {
  return <RetainedBillEntry kind="reagent-purchase">{({ entry, authStatus }) => <ReagentPurchaseOrderForm entry={entry} auth={authStatus} />}</RetainedBillEntry>;
}

function ReagentPurchaseOrderForm({ entry, auth }: { entry: InvoiceEntrySession; auth: AuthStatus }) {
  const [profile, setProfile] = useState<SellerProfileResponse | null>(null);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [manufacturers, setManufacturers] = useState<Manufacturer[]>([]);
  const [supplierId, setSupplierId] = useInvoiceEntryValue(entry, "supplierId", "");
  const [supplierSearch, setSupplierSearch] = useInvoiceEntryValue(entry, "supplierSearch", "");
  const [supplier, setSupplier] = useInvoiceEntryValue<Party>(entry, "supplier", blankParty);
  const [sameConsignee, setSameConsignee] = useInvoiceEntryValue(entry, "sameConsignee", true);
  const [consignee, setConsignee] = useInvoiceEntryValue<Party>(entry, "consignee", blankParty);
  const [details, setDetails] = useInvoiceEntryValue<Details>(entry, "details", blankDetails);
  const [lines, setLines] = useInvoiceEntryValue<Line[]>(entry, "lines", () => [blankLine(1)]);
  const [preview, setPreview] = useState<InvoicePreview | null>(null);
  const [errors, setErrors] = useInvoiceEntryValue<Errors>(entry, "errors", () => ({}));
  const [error, setError] = useInvoiceEntryValue(entry, "error", "");
  const [message, setMessage] = useInvoiceEntryValue(entry, "message", "");
  const [loaded, setLoaded] = useState(false);
  const [conflict, setConflict] = useInvoiceEntryValue(entry, "conflict", false);
  const payload = useMemo(() => ({
    document_type: "reagent", ...(supplierId ? { supplier_id: Number(supplierId) } : { supplier: partyPayload(supplier) }),
    consignee: sameConsignee ? null : partyPayload(consignee),
    ...Object.fromEntries(Object.entries(details).filter(([key, value]) => key !== "purchase_order_number" || value.trim()).map(([key, value]) => [key, key === "purchase_order_number" ? value.trim() : value || null])),
    lines: lines.map((line) => ({ ...(line.product_id ? { product_id: Number(line.product_id) } : {}), product_name: line.product_name || null, description: line.description || null, manufacturer_id: line.manufacturer_id ? Number(line.manufacturer_id) : null, manufacturer_product_code: line.part_no || null, part_no: line.part_no || null, pack_size: line.pack_size.trim() || null, hsn_sac: line.hsn_sac, quantity: line.quantity, unit: line.unit, rate: line.rate, gst_rate: line.gst_rate, discount_percent: line.discount_percent, other_charge: "0.00", discount_amount: "0.00", cess_rate: "0.00" })),
  }), [supplierId, supplier, sameConsignee, consignee, details, lines]);
  const signature = JSON.stringify(payload);
  const ready = Boolean(loaded && profile?.seller_profile?.is_active && details.order_date && details.place_of_supply_state_code && (supplierId || partyComplete(supplier)) && (sameConsignee || partyComplete(consignee)) && lines.every((line) => (line.product_id || line.product_name.trim()) && line.manufacturer_id && line.hsn_sac.trim() && line.quantity && line.rate && line.gst_rate && line.discount_percent));
  const submission = useBillSubmission<PurchaseOrder>({ collection: "/purchase-orders", payload, updateField: "reagent_details",
    entrySession: entry,
    onReturned: () => savedBill.reloadLatest(),
    validate: (): string | null => savedBill.blocked ? "Load the saved order successfully before saving; your fields are retained." : ready ? null : "Complete the seller and each reagent line before saving.",
    onFailure: (failure) => { setErrors(errorsFrom(failure)); setConflict(failure instanceof ApiError && failure.status === 409 && (failure.detail as { code?: string } | undefined)?.code === "version_conflict"); },
  });
  const saved = submission.document;
  const supplierDetails: Party | null = saved ? purchaseOrderSellerValues(saved) : supplierId ? supplier : null;
  useEffect(() => {
    if (!saved) return;
    const snapshot = purchaseOrderSellerValues(saved);
    const unchanged = supplierId ? Number(supplierId) === saved.supplier_id
      : (Object.keys(snapshot) as (keyof Party)[]).every((field) => supplier[field].trim() === snapshot[field].trim());
    if (unchanged) return;
    // Keep the recovered order's fixed seller without discarding other edits.
    setSupplierId(String(saved.supplier_id));
    setSupplier(snapshot);
  }, [saved, supplierId, supplier, setSupplierId, setSupplier]);
  const editing = saved && ["draft", "amendment_pending"].includes(saved.status) ? saved : null;
  const busy = submission.busy;
  const unsaved = Boolean(saved && submission.unsaved);
  const savedBill = useSavedBillLoader<PurchaseOrder>({
    collection: "/purchase-orders", parameter: "order", documentType: "reagent", authenticated: auth === "authenticated", ready: loaded,
    document: saved, busy, unsaved: submission.unsaved, hasWork: Boolean(saved || details.purchase_order_number || lines.some((line) => line.product_name || line.product_id)),
    hydrate: loadOrder,
  });

  useEffect(() => {
    if (auth !== "authenticated") return;
    let cancelled = false;
    void Promise.allSettled([apiRequest<SellerProfileResponse>("/companies/profile"), apiRequest<Supplier[]>("/suppliers"), apiRequest<Product[]>("/products"), apiRequest<Manufacturer[]>("/manufacturers")]).then(([profileResult, suppliersResult, productsResult, manufacturersResult]) => {
      if (cancelled || !entry.active) return;
      if (profileResult.status === "fulfilled") setProfile(profileResult.value);
      if (suppliersResult.status === "fulfilled") {
        setSuppliers(suppliersResult.value);
        const defaultSupplier = suppliersResult.value.find((item) => item.is_active && item.is_default) ?? suppliersResult.value.find((item) => item.is_active);
        if (!entry.read("supplierInitialized", false)) {
          if (defaultSupplier && !entry.read("supplierId", "") && !entry.read("supplier", blankParty()).name.trim()) { setSupplierId(String(defaultSupplier.id)); setSupplier(partyFromMaster(defaultSupplier)); }
          entry.write("supplierInitialized", true);
        }
      }
      if (productsResult.status === "fulfilled") setProducts(productsResult.value);
      if (manufacturersResult.status === "fulfilled") setManufacturers(manufacturersResult.value);
      const failed = [profileResult, suppliersResult, productsResult, manufacturersResult].find((result) => result.status === "rejected");
      if (failed?.status === "rejected") setError(failed.reason instanceof ApiError ? failed.reason.message : "Some billing data could not load. Your entries have been retained.");
      setLoaded(true);
    });
    return () => { cancelled = true; };
  }, [auth, entry, setSupplierId, setSupplier, setError]);

  useEffect(() => {
    if (!ready || savedBill.blocked || auth !== "authenticated") { setPreview(null); return; }
    let cancelled = false;
    setPreview(null);
    const timer = setTimeout(() => {
      void apiRequest<InvoicePreview>("/purchase-orders/preview", { method: "POST", body: signature }).then((result) => { if (!cancelled) { setPreview(result); setErrors({}); } }).catch((failure) => { if (!cancelled) { setErrors(errorsFrom(failure)); setError(failure instanceof ApiError ? failure.message : "Totals could not be refreshed. Your entries have been retained."); } });
    }, 300);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [auth, ready, signature, savedBill.blocked, setErrors, setError]);

  useEffect(() => {
    const dirty = unsaved || (!saved && lines.some((line) => line.product_name || line.product_id));
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsaved, saved, lines]);

  function updateLine(key: number, values: Partial<Line>) { setLines((current) => current.map((line) => line.key === key ? { ...line, ...values } : line)); }
  function chooseProduct(key: number, id: string) {
    const product = products.find((item) => String(item.id) === id);
    updateLine(key, { product_id: id, product_name: product?.name ?? "", description: product?.description ?? "", hsn_sac: product?.hsn_sac ?? "", gst_rate: product?.gst_rate ?? "18.00" });
    // Manufacturer, article, unit and rate belong to this transaction, not the product master.
  }
  function loadOrder(order: PurchaseOrder) {
    submission.restore(order); setSupplierId(String(order.supplier_id));
    setSameConsignee(!order.consignee);
    if (order.consignee) setConsignee(partyFromMaster(order.consignee));
    setDetails(Object.fromEntries(Object.keys(blankDetails()).map((key) => [key, order[key as keyof PurchaseOrder] ?? ""])) as Details);
    setLines(order.lines.map((line, index) => ({ key: index + 1, product_id: String(line.product_id), product_name: line.product_name, description: line.description, manufacturer_id: line.manufacturer_id ? String(line.manufacturer_id) : "", part_no: line.part_no ?? "", pack_size: line.pack_size ?? "", hsn_sac: line.hsn_sac, quantity: line.quantity, unit: line.unit, rate: line.rate, gst_rate: line.gst_rate, discount_percent: line.discount_percent })));
    setConflict(false); setMessage(`Loaded ${order.purchase_order_number}. ${["draft", "amendment_pending"].includes(order.status) ? "Edit and save this revision." : "Approved financial data is read-only. Request an amendment to edit."}`);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setErrors({}); setConflict(false); setError(""); setMessage(""); await submission.save();
  }
  async function amend(order: PurchaseOrder) {
    if (busy) return;
    const reason = window.prompt("Reason for this amendment:");
    if (!reason?.trim()) return;
    if (order.id !== saved?.id) return;
    setError(""); await submission.amend(reason, loadOrder);
  }
  const detailFields: [keyof Details, string, string?][] = [["purchase_order_number", "PO No."], ["order_date", "PO date", "date"], ["delivery_note_date", "Delivery note date", "date"], ["place_of_supply_state_code", "Place of supply state code"], ["po_reference_number", "Customer PO reference"], ["po_reference_date", "Customer PO date", "date"], ["payment_terms", "Payment terms"], ["transport_mode", "Dispatched through"], ["vehicle_number", "Vehicle number"], ["vehicle_type", "Vehicle type"], ["lr_number", "LR/Docket number"], ["lr_date", "Transport document date", "date"], ["expected_delivery_date", "Expected delivery date", "date"], ["freight_charges", "Freight charges"], ["packing_charges", "Packing charges"], ["other_charges", "Other charges"], ["discount_amount", "Header discount"]];

  return <AuthGateStatus status={auth}><AppShell><div className="workspace-page">
    <PageHeader icon="reagent-purchase-order" eyebrow="Reagent purchasing" title="Reagent purchase order" description="Manufacturer and article details, reagent pricing and the reagent bill PDF format." />
    <div className="mt-4 flex flex-wrap gap-3"><Link href="/purchase-orders" className="ui-button">Domestic Oils purchase order</Link><button className="ui-button" type="button" disabled={busy} onClick={() => { if ((unsaved || (!saved && lines.some((line) => line.product_name || line.product_id))) && !window.confirm("Discard unsaved changes and start a new order?")) return; submission.reset(); setSupplierSearch(""); setSameConsignee(true); setConsignee(blankParty()); setDetails(blankDetails()); setLines([blankLine(1)]); setPreview(null); setConflict(false); setErrors({}); setError(""); setMessage(""); const defaultSupplier = suppliers.find((item) => item.is_active && item.is_default) ?? suppliers.find((item) => item.is_active); setSupplierId(defaultSupplier ? String(defaultSupplier.id) : ""); setSupplier(defaultSupplier ? partyFromMaster(defaultSupplier) : blankParty()); }}>Start new order</button><span className="self-center text-sm text-slate" role="status">{saved ? unsaved ? "Unsaved changes" : `Saved · ${saved.status.replaceAll("_", " ")}` : "New draft · not saved"}</span></div>
    {error && <div className="ui-alert mt-5 border-red-200 bg-red-50 text-red-800" role="alert">{error}</div>}{message && <div className="ui-alert mt-5" role="status">{message}</div>}
    {loaded && !profile?.seller_profile?.is_active && <p className="ui-alert mt-5">Set up an active <Link className="underline" href="/branches">Seller profile</Link> before saving.</p>}
    <SavedBillLoadError loader={savedBill} />
    {conflict && editing && <button className="ui-button mt-3" type="button" disabled={busy} onClick={savedBill.reloadLatest}>Reload latest revision</button>}
    <form data-bill-entry className="ui-panel mt-6" onSubmit={save} noValidate>
      <fieldset disabled={submission.locked || savedBill.blocked} className="min-w-0 space-y-7">
        <section aria-label="Seller">
          <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-base font-bold text-ink">Seller</h2><Link href="/suppliers" className="ui-button">Manage sellers</Link></div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {!saved && <Field name="supplier_search" label="Search seller" errors={errors}><input className="ui-input" value={supplierSearch} onChange={(event) => setSupplierSearch(event.target.value)} placeholder="Search by seller name" /></Field>}
            <Field name="supplier_id" label="Saved seller" errors={errors}><select className="ui-input" disabled={Boolean(saved)} value={supplierId} onChange={(event) => { const id = event.target.value; setSupplierId(id); const selected = suppliers.find((item) => String(item.id) === id); setSupplier(selected ? partyFromMaster(selected) : blankParty()); setErrors({}); }}><option value="">Enter seller manually</option>{suppliers.filter((item) => String(item.id) === supplierId || (item.is_active && item.name.toLowerCase().includes(supplierSearch.toLowerCase()))).map((item) => <option key={item.id} value={item.id}>{item.name}{item.is_default ? " · Default" : ""}</option>)}</select></Field>
          </div>
          <PurchaseOrderSellerFields details={supplierDetails ?? supplier} errors={errors} readOnly={Boolean(supplierId) || Boolean(saved)} onChange={(field, value) => { setSupplier((current) => ({ ...current, [field]: value })); setErrors({}); }} />
          {saved && <p className="mt-2 text-xs text-slate">The seller is fixed for this saved order. Start a new order to choose another seller.</p>}
        </section>
        <PurchaseOrderShippingDetails details={supplierDetails ?? supplier} />
        <section>
          <h2 className="ui-section-title">Order and transport details</h2>
          <p className="mt-2 text-xs text-slate">Enter your full PO No., or leave it blank for automatic numbering. PO numbers are separate from sales and reagent invoices.</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{detailFields.map(([field, label, type]) => <Field key={field} name={field} label={label} errors={errors}>{field === "payment_terms" ? <AutoResizeTextarea className="ui-input" rows={1} value={details[field]} onChange={(event) => setDetails((current) => ({ ...current, [field]: event.target.value }))} /> : <input className="ui-input" type={type ?? "text"} value={details[field]} maxLength={field === "purchase_order_number" ? 100 : field === "place_of_supply_state_code" ? 2 : undefined} readOnly={field === "purchase_order_number" && Boolean(saved?.correction || editing?.approved_at)} placeholder={field === "purchase_order_number" ? "Enter your full PO number" : undefined} onChange={(event) => { const value = field === "purchase_order_number" ? event.target.value.toUpperCase() : event.target.value; setDetails((current) => ({ ...current, [field]: value })); if (field === "purchase_order_number") setErrors((current) => { const next = { ...current }; delete next.purchase_order_number; return next; }); }} />}</Field>)}</div>
        </section>
        <section><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="ui-section-title">Reagent line items</h2><div className="flex gap-2"><Link href="/manufacturers" className="ui-button">Manufacturers</Link><button type="button" className="ui-button" onClick={() => setLines((current) => [...current, blankLine(Date.now())])}>Add line</button></div></div><div className="mt-4 space-y-4">{lines.map((line, index) => <article key={line.key} className="rounded-xl border border-line p-4"><div className="flex justify-between gap-3"><h3 className="font-semibold text-ink">Line {index + 1}</h3>{lines.length > 1 && <button type="button" className="text-sm text-red-700" onClick={() => setLines((current) => current.filter((item) => item.key !== line.key))}>Remove</button>}</div><div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field name={`lines.${index}.product_id`} label="Saved product (optional)" errors={errors}><select className="ui-input" value={line.product_id} onChange={(event) => chooseProduct(line.key, event.target.value)}><option value="">Enter a new product below</option>{products.filter((item) => item.is_active).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></Field>
          <Field name={`lines.${index}.product_name`} label="Product name" errors={errors}><AutoResizeTextarea className="ui-input" readOnly={Boolean(line.product_id)} rows={1} value={line.product_name} onChange={(event) => updateLine(line.key, { product_name: event.target.value })} /></Field>
          <Field name={`lines.${index}.manufacturer_id`} label="Manufacturer" errors={errors}><select className="ui-input" value={line.manufacturer_id} onChange={(event) => updateLine(line.key, { manufacturer_id: event.target.value })}><option value="">Select manufacturer</option>{manufacturers.filter((item) => item.is_active).map((item) => <option value={item.id} key={item.id}>{item.code} · {item.name}</option>)}</select></Field>
          <Field name={`lines.${index}.part_no`} label="Article No." errors={errors}><input className="ui-input" maxLength={100} value={line.part_no} onChange={(event) => updateLine(line.key, { part_no: event.target.value })} /></Field>
          <Field name={`lines.${index}.description`} label="Description" errors={errors} wide><AutoResizeTextarea className="ui-input" rows={1} value={line.description} onChange={(event) => updateLine(line.key, { description: event.target.value })} /></Field>
          <Field name={`lines.${index}.pack_size`} label="Pack/Size" errors={errors}><input className="ui-input" maxLength={100} placeholder="e.g. 500 g or 100 mL" value={line.pack_size} onChange={(event) => updateLine(line.key, { pack_size: event.target.value })} /></Field>
          {([['hsn_sac', 'HSN/SAC'], ['quantity', 'Quantity'], ['rate', 'Rate'], ['gst_rate', 'GST %'], ['discount_percent', 'Disc %']] as [keyof Line, string][]).map(([field, label]) => <Field key={field} name={`lines.${index}.${field}`} label={label} errors={errors}><input className="ui-input" value={line[field]} onChange={(event) => updateLine(line.key, { [field]: event.target.value })} /></Field>)}
          <Field name={`lines.${index}.unit`} label="Per / unit" errors={errors}><select className="ui-input" value={line.unit} onChange={(event) => updateLine(line.key, { unit: event.target.value })}>{units.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></Field>
        </div>{preview?.lines[index] && <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 rounded-lg bg-warm p-3 text-sm"><span>Goods amount ₹{preview.lines[index].taxable_value}</span><strong>CGST ₹{preview.lines[index].cgst_amount}</strong><strong>SGST ₹{preview.lines[index].sgst_amount}</strong><strong>IGST ₹{preview.lines[index].igst_amount}</strong></div>}</article>)}</div></section>
      </fieldset>
      <section className="mt-6 rounded-xl border border-line bg-warm/50 p-4" aria-live="polite"><h2 className="ui-section-title">Live backend preview</h2>{preview ? <><dl className="mt-3 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">{([['Goods / taxable', preview.taxable_value], ['CGST', preview.cgst_amount], ['SGST', preview.sgst_amount], ['IGST', preview.igst_amount], ['Round-off', preview.round_off], ['Final total', preview.final_total]]).map(([label, value]) => <div key={label}><dt className="text-xs text-slate">{label}</dt><dd className="mt-1 font-semibold text-ink">₹{value}</dd></div>)}</dl><p className="mt-3 text-sm text-slate">{preview.amount_in_words}</p></> : <p className="mt-3 text-sm text-slate">Complete the details to calculate authoritative backend totals.</p>}</section>
      <button className="ui-button-primary mt-6 w-full" type="submit" disabled={submission.locked || !loaded}>{busy ? "Saving…" : editing ? "Save reagent PO changes" : "Save reagent purchase order"}</button>
    </form>
    <BillSubmissionPanel submission={submission} ready={ready && !savedBill.blocked} documentNumber={saved?.purchase_order_number} />
    {saved?.status === "approved" && <button className="ui-button mt-4" type="button" disabled={busy} onClick={() => void amend(saved)}>Amend</button>}
  </div></AppShell></AuthGateStatus>;
}
