"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";

import { AppShell } from "@/app/components/AppShell";
import { AppIcon } from "@/app/components/AppIcon";
import { AutoResizeTextarea } from "@/app/components/AutoResizeTextarea";
import { AuthGateStatus, useAuthStatus, useSessionState, type AuthStatus } from "@/app/components/AuthGate";
import { PageHeader } from "@/app/components/PageHeader";
import { BillSubmissionPanel } from "@/app/components/BillSubmissionPanel";
import { InvoiceSupplierPicker } from "@/app/components/InvoiceSupplierPicker";
import { ApiError, apiRequest } from "@/app/lib/api";
import { useBillSubmission } from "@/app/lib/useBillSubmission";
import { useSavedBillLoader } from "@/app/lib/useSavedBillLoader";
import { discardInvoiceEntrySession, getInvoiceEntrySession, INVOICE_ENTRY_INVALIDATED_EVENT, useInvoiceEntryValue, type InvoiceEntrySession } from "@/app/lib/invoiceEntrySession";
import { indiaDateInputValue, invoiceNumberPrefix } from "@/app/lib/indiaDate";
import type { Customer, Invoice, InvoicePreview, Manufacturer, Product, SellerProfileResponse, Supplier } from "@/app/lib/types";

type EntryMode = "manual" | "saved";
type SavedShippingAddressMode = "billing" | "shipping";

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
  manufacturer_id: string;
  product_name: string;
  manufacturer_product_code: string;
  description: string;
  part_no: string;
  pack_size: string;
  hsn_sac: string;
  quantity: string;
  unit: string;
  rate: string;
  other_charge: string;
  discount_amount: string;
  discount_percent: string;
  gst_rate: string;
  cess_rate: string;
};

const inputClass = "ui-input";
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

function consigneeFromCustomer(customer: Customer, addressMode: SavedShippingAddressMode): PartyForm {
  const address = addressMode === "shipping" && customer.shipping_address ? customer.shipping_address : customer.billing_address;
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

const initialLine = (key: number, defaultUnit = "KG"): DraftLine => ({
  key,
  product_id: "",
  manufacturer_id: "",
  product_name: "",
  manufacturer_product_code: "",
  description: "",
  part_no: "",
  pack_size: "",
  hsn_sac: "",
  quantity: "1.000",
  unit: defaultUnit,
  rate: "",
  other_charge: "0.00",
  discount_amount: "0.00",
  discount_percent: "0.00",
  gst_rate: "18.00",
  cess_rate: "0.00",
});

function partyFromInvoice(invoice: Invoice, prefix: "buyer" | "consignee"): PartyForm {
  return Object.fromEntries(Object.keys(blankParty()).map((field) => [field, invoice[`${prefix}_${field}` as keyof Invoice] ?? ""])) as PartyForm;
}

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

function lineComplete(line: DraftLine, mode: EntryMode, reagent = false) {
  if (!line.quantity) return false;
  if (mode === "saved") return Boolean(line.product_id && (!reagent || (line.manufacturer_id && line.description)));
  return Boolean(line.product_name && line.hsn_sac && line.unit && line.rate && line.gst_rate && (!reagent || (line.manufacturer_id && line.description)));
}

const reagentUnitOptions = [
  { value: "g", label: "Gram (g)" },
  { value: "kg", label: "Kilogram (kg)" },
  { value: "mg", label: "Milligram (mg)" },
  { value: "µg", label: "Microgram (µg)" },
  { value: "mL", label: "Millilitre (mL)" },
  { value: "L", label: "Litre (L)" },
  { value: "t", label: "Tonne (t)" },
];

function reagentUnit(value: string | null | undefined) {
  const aliases: Record<string, string> = {
    G: "g", GM: "g", GRAM: "g", GRAMS: "g",
    KG: "kg", KGS: "kg", KILOGRAM: "kg", KILOGRAMS: "kg",
    MG: "mg", MILLIGRAM: "mg", MILLIGRAMS: "mg",
    UG: "µg", "ΜG": "µg", "µG": "µg", MICROGRAM: "µg", MICROGRAMS: "µg",
    ML: "mL", MILLILITER: "mL", MILLILITRE: "mL", MILLILITERS: "mL", MILLILITRES: "mL",
    L: "L", LITER: "L", LITRE: "L", LITERS: "L", LITRES: "L",
    T: "t", TON: "t", TONS: "t", TONNE: "t", TONNES: "t",
  };
  if (!value) return "kg";
  return aliases[value.trim().toUpperCase()] ?? value;
}

function requestErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export function InvoiceEntryPage({ documentType }: { documentType: "sales" | "reagent" }) {
  const authStatus = useAuthStatus();
  const { session } = useSessionState();
  const [epoch, setEpoch] = useState(0);
  const userId = session?.user.id;
  useEffect(() => {
    const recover = (event: Event) => {
      if ((event as CustomEvent<{ kind?: string }>).detail?.kind === documentType) setEpoch((value) => value + 1);
    };
    window.addEventListener(INVOICE_ENTRY_INVALIDATED_EVENT, recover);
    return () => window.removeEventListener(INVOICE_ENTRY_INVALIDATED_EVENT, recover);
  }, [documentType]);
  return <AuthGateStatus status={authStatus}>{userId != null && session?.user.is_active &&
    <RetainedInvoiceEntry key={`${userId}:${documentType}:${epoch}`} userId={userId} documentType={documentType} authStatus={authStatus}
      onStartNew={() => { window.history.replaceState(null, "", window.location.pathname); discardInvoiceEntrySession(userId, documentType); setEpoch((value) => value + 1); }} />}
  </AuthGateStatus>;
}

function RetainedInvoiceEntry({ userId, ...props }: { userId: number; documentType: "sales" | "reagent"; authStatus: AuthStatus; onStartNew: () => void }) {
  const [entry] = useState(() => getInvoiceEntrySession(userId, props.documentType));
  return <InvoiceEntryForm {...props} entry={entry} />;
}

function InvoiceEntryForm({ documentType, authStatus, entry, onStartNew }: { documentType: "sales" | "reagent"; authStatus: AuthStatus; entry: InvoiceEntrySession; onStartNew: () => void }) {
  const isReagent = documentType === "reagent";
  const returning = useRef(entry.has("entryMode")).current;
  const [entryMode, setEntryMode] = useInvoiceEntryValue<EntryMode>(entry, "entryMode", "manual");
  const [sellerProfiles, setSellerProfiles] = useState<NonNullable<SellerProfileResponse["seller_profile"]>[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [selectedBuyerSnapshot, setSelectedBuyerSnapshot] = useInvoiceEntryValue<Customer | null>(entry, "selectedBuyerSnapshot", null);
  const [buyerSearch, setBuyerSearch] = useInvoiceEntryValue(entry, "buyerSearch", "");
  const [selectedSupplier, setSelectedSupplier] = useInvoiceEntryValue<Supplier | null | undefined>(entry, "selectedSupplier", undefined);
  const [supplierError, setSupplierError] = useInvoiceEntryValue<string | null>(entry, "supplierError", null);
  const chooseSupplier = useCallback((supplier: Supplier | null) => {
    setSelectedSupplier(supplier);
    setSupplierError(null);
  }, [setSelectedSupplier, setSupplierError]);
  const [products, setProducts] = useState<Product[]>([]);
  const [manufacturers, setManufacturers] = useState<Manufacturer[]>([]);
  const [buyerCustomerId, setBuyerCustomerId] = useInvoiceEntryValue(entry, "buyerCustomerId", "");
  const [manualBuyer, setManualBuyer] = useInvoiceEntryValue<PartyForm>(entry, "manualBuyer", blankParty);
  const [manualConsignee, setManualConsignee] = useInvoiceEntryValue<PartyForm>(entry, "manualConsignee", blankParty);
  const [savedConsignee, setSavedConsignee] = useInvoiceEntryValue<PartyForm>(entry, "savedConsignee", blankParty);
  const [savedShippingAddressMode, setSavedShippingAddressMode] = useInvoiceEntryValue<SavedShippingAddressMode>(entry, "savedShippingAddressMode", "billing");
  const [loadedInvoice, setLoadedInvoice] = useInvoiceEntryValue<Invoice | null>(entry, "loadedInvoice", null);
  const [versionConflict, setVersionConflict] = useInvoiceEntryValue(entry, "versionConflict", false);
  const [manualConsigneeSameAsBuyer, setManualConsigneeSameAsBuyer] = useInvoiceEntryValue(entry, "manualConsigneeSameAsBuyer", true);
  const [invoiceDate, setInvoiceDate] = useInvoiceEntryValue(entry, "invoiceDate", indiaDateInputValue);
  const [invoiceNumberSuffix, setInvoiceNumberSuffix] = useInvoiceEntryValue(entry, "invoiceNumberSuffix", "");
  const [invoiceNumberError, setInvoiceNumberError] = useInvoiceEntryValue<string | null>(entry, "invoiceNumberError", null);
  const [deliveryNoteDate, setDeliveryNoteDate] = useInvoiceEntryValue(entry, "deliveryNoteDate", "");
  const [placeOfSupplyStateCode, setPlaceOfSupplyStateCode] = useInvoiceEntryValue(entry, "placeOfSupplyStateCode", "36");
  const [poNumber, setPoNumber] = useInvoiceEntryValue(entry, "poNumber", "");
  const [paymentTerms, setPaymentTerms] = useInvoiceEntryValue(entry, "paymentTerms", "30 days");
  const [transportMode, setTransportMode] = useInvoiceEntryValue(entry, "transportMode", "Road");
  const [vehicleNumber, setVehicleNumber] = useInvoiceEntryValue(entry, "vehicleNumber", "");
  const [vehicleType, setVehicleType] = useInvoiceEntryValue(entry, "vehicleType", "");
  const [lrNumber, setLrNumber] = useInvoiceEntryValue(entry, "lrNumber", "");
  const [lrDate, setLrDate] = useInvoiceEntryValue(entry, "lrDate", "");
  const [expectedDeliveryDate, setExpectedDeliveryDate] = useInvoiceEntryValue(entry, "expectedDeliveryDate", "");
  const [freightCharges, setFreightCharges] = useInvoiceEntryValue(entry, "freightCharges", "0.00");
  const [packingCharges, setPackingCharges] = useInvoiceEntryValue(entry, "packingCharges", "0.00");
  const [otherCharges, setOtherCharges] = useInvoiceEntryValue(entry, "otherCharges", "0.00");
  const [discountAmount, setDiscountAmount] = useInvoiceEntryValue(entry, "discountAmount", "0.00");
  const [lines, setLines] = useInvoiceEntryValue<DraftLine[]>(entry, "lines", () => [initialLine(1, isReagent ? "kg" : "KG")]);
  const [packSizeErrors, setPackSizeErrors] = useInvoiceEntryValue<Record<number, string>>(entry, "packSizeErrors", () => ({}));
  const [preview, setPreview] = useState<InvoicePreview | null>(null);
  const [error, setError] = useInvoiceEntryValue<string | null>(entry, "error", null);
  const [message, setMessage] = useInvoiceEntryValue<string | null>(entry, "message", null);
  const [isBillingDataLoaded, setIsBillingDataLoaded] = useState(false);

  const selectedCustomer = useMemo(
    () => selectedBuyerSnapshot && String(selectedBuyerSnapshot.id) === buyerCustomerId
      ? selectedBuyerSnapshot : customers.find((customer) => String(customer.id) === buyerCustomerId),
    [buyerCustomerId, customers, selectedBuyerSnapshot],
  );
  const billingCustomers = useMemo(() => {
    const seen = new Set<string>();
    return customers.filter((customer) => {
      if (!customer.is_active) return false;
      const gstin = customer.gstin?.trim().toUpperCase();
      const identity = gstin ? `${customer.branch_id}:${gstin}` : `id:${customer.id}`;
      if (seen.has(identity)) return false;
      seen.add(identity);
      return true;
    });
  }, [customers]);
  const filteredCustomers = useMemo(() => {
    const query = buyerSearch.trim().toLowerCase();
    if (!query) return billingCustomers;
    return billingCustomers.filter((customer) => customer.name.toLowerCase().includes(query) || customer.gstin?.toLowerCase().includes(query));
  }, [buyerSearch, billingCustomers]);
  const selectableProducts = useMemo(() => {
    return products.filter((product) => product.is_active);
  }, [products]);
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
        const [profileResult, customerResult, productResult, manufacturerResult] = await Promise.allSettled([
          apiRequest<SellerProfileResponse>("/companies/profile"),
          apiRequest<Customer[]>("/customers?billing=true"),
          apiRequest<Product[]>("/products"),
          isReagent ? apiRequest<Manufacturer[]>("/manufacturers?active_only=true") : Promise.resolve([] as Manufacturer[]),
        ]);
        if (cancelled || !entry.active) return;
        const loadErrors: string[] = [];
        const sellerProfile = profileResult.status === "fulfilled" ? profileResult.value.seller_profile : null;
        const profileList = sellerProfile ? [sellerProfile] : [];
        if (profileResult.status === "rejected") loadErrors.push(`Seller profile: ${requestErrorMessage(profileResult.reason, "unable to load")}`);
        if (customerResult.status === "fulfilled") setCustomers(customerResult.value);
        else loadErrors.push(`Saved customers: ${requestErrorMessage(customerResult.reason, "unable to load")}`);
        if (productResult.status === "fulfilled") setProducts(productResult.value);
        else loadErrors.push(`Saved products: ${requestErrorMessage(productResult.reason, "unable to load")}`);
        if (manufacturerResult.status === "fulfilled") setManufacturers(manufacturerResult.value.filter((item) => item.is_active));
        else loadErrors.push(`Manufacturers: ${requestErrorMessage(manufacturerResult.reason, "unable to load")}`);
        setSellerProfiles(profileList);
        const activeProfile = profileList.find((profile) => profile.is_active) ?? profileList[0] ?? null;
        if (!returning && activeProfile?.state_code) {
          setPlaceOfSupplyStateCode(activeProfile.state_code);
          setManualBuyer((current) => ({ ...current, state_code: current.state_code || activeProfile.state_code }));
        }
        if (loadErrors.length) setError(`Some billing data could not load. ${loadErrors.join(" ")}`);
      } catch (requestError) {
        if (cancelled || !entry.active) return;
        setError(requestErrorMessage(requestError, `Unable to load ${isReagent ? "reagent bill" : "sales invoice"} data.`));
      } finally {
        if (!cancelled && entry.active) setIsBillingDataLoaded(true);
      }
    }
    void loadData();
    return () => { cancelled = true; };
  // Default initialization must never overwrite retained transaction fields.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authStatus, documentType, isReagent, entry, returning]);

  const previousSavedChoice = useRef(`${entryMode}:${buyerCustomerId}`);
  useEffect(() => {
    const choice = `${entryMode}:${buyerCustomerId}`;
    if (previousSavedChoice.current === choice) return;
    previousSavedChoice.current = choice;
    if (entryMode !== "saved") return;
    setSelectedBuyerSnapshot(selectedCustomer ?? null);
    if (entryMode === "saved" && selectedCustomer?.billing_address.state_code) {
      setPlaceOfSupplyStateCode(selectedCustomer.billing_address.state_code);
    }
    const addressMode = selectedCustomer?.shipping_address ? "shipping" : "billing";
    setSavedShippingAddressMode(addressMode);
    setSavedConsignee(selectedCustomer ? consigneeFromCustomer(selectedCustomer, addressMode) : blankParty());
    // Only an explicit choice change initializes fields, not a master reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entryMode, buyerCustomerId]);

  const previousManualState = useRef(`${entryMode}:${manualBuyer.state_code}`);
  useEffect(() => {
    const choice = `${entryMode}:${manualBuyer.state_code}`;
    if (previousManualState.current === choice) return;
    previousManualState.current = choice;
    if (entryMode === "manual" && manualBuyer.state_code) {
      setPlaceOfSupplyStateCode(manualBuyer.state_code);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entryMode, manualBuyer.state_code]);

  const buildPayload = useCallback(() => ({
    document_type: documentType,
    ...(loadedInvoice ? { branch_id: loadedInvoice.branch_id } : {}),
    supplier_id: selectedSupplier?.id ?? null,
    ...(entryMode === "saved"
      ? {
          buyer_customer_id: asNumber(buyerCustomerId),
          ...(selectedCustomer ? { buyer: {
            name: selectedCustomer.name, gstin: selectedCustomer.gstin, pan: selectedCustomer.pan,
            email: selectedCustomer.email, phone: selectedCustomer.phone,
            billing_address: selectedCustomer.billing_address, shipping_address: selectedCustomer.shipping_address, is_active: true,
          } } : {}),
          consignee: partyPayload(savedConsignee),
        }
      : {
          buyer: partyPayload(manualBuyer),
          ...(!manualConsigneeSameAsBuyer ? { consignee: partyPayload(manualConsignee) } : {}),
        }),
    invoice_date: invoiceDate,
    invoice_number_suffix: invoiceNumberSuffix.trim() || undefined,
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
      ...(line.product_id ? { product_id: asNumber(line.product_id) } : {}),
      product_name: line.product_name || null,
      ...(isReagent ? {
        manufacturer_id: asNumber(line.manufacturer_id),
        manufacturer_product_code: line.manufacturer_product_code || null,
      } : {}),
      description: line.description || null,
      part_no: (isReagent ? line.manufacturer_product_code : line.part_no) || null,
      ...(isReagent ? { pack_size: line.pack_size.trim() || null } : {}),
      hsn_sac: line.hsn_sac || null,
      quantity: line.quantity,
      unit: line.unit || null,
      rate: line.rate || null,
      other_charge: isReagent ? "0.00" : line.other_charge,
      discount_amount: isReagent ? "0.00" : line.discount_amount,
      discount_percent: isReagent ? line.discount_percent : "0.00",
      gst_rate: line.gst_rate || null,
      cess_rate: isReagent ? "0.00" : (line.cess_rate || null),
    })),
  }), [
    buyerCustomerId,
    documentType,
    discountAmount,
    deliveryNoteDate,
    entryMode,
    expectedDeliveryDate,
    freightCharges,
    invoiceDate,
    invoiceNumberSuffix,
    lrDate,
    lrNumber,
    lines,
    loadedInvoice,
    manualBuyer,
    isReagent,
    manualConsignee,
    manualConsigneeSameAsBuyer,
    otherCharges,
    packingCharges,
    paymentTerms,
    placeOfSupplyStateCode,
    poNumber,
    savedConsignee,
    selectedCustomer,
    selectedSupplier,
    transportMode,
    vehicleNumber,
    vehicleType,
  ]);

  const canPreview = Boolean(
    sellerProfileReady &&
    selectedSupplier !== undefined &&
    invoiceDate &&
    placeOfSupplyStateCode &&
    (entryMode === "saved"
      ? selectedCustomer && manualPartyComplete(savedConsignee)
      : manualPartyComplete(manualBuyer) && (manualConsigneeSameAsBuyer || manualPartyComplete(manualConsignee))) &&
    lines.every((line) => lineComplete(line, entryMode, isReagent)),
  );

  function validateInvoiceDraft() {
    if (!isBillingDataLoaded) return "Billing setup is still loading. Try again in a moment.";
    if (!sellerProfileReady) return "Set up Seller/GST profile first before saving bills.";
    if (selectedSupplier === undefined) {
      setSupplierError("Load suppliers successfully before saving. Use Refresh suppliers to retry.");
      return "Supplier details could not load. Refresh suppliers and try again; your entries are retained.";
    }
    if (!invoiceDate) return "Enter the invoice date before saving.";
    if (!/^[A-Z0-9][A-Z0-9/-]{0,29}$/.test(invoiceNumberSuffix.trim())) {
      setInvoiceNumberError("Enter an invoice number using 1–30 letters, digits, hyphens or slashes.");
      return "Enter a valid invoice number before saving.";
    }
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

    const incompleteLineIndex = lines.findIndex((line) => !lineComplete(line, entryMode, isReagent));
    if (incompleteLineIndex >= 0) {
      const lineNumber = incompleteLineIndex + 1;
      return entryMode === "saved"
        ? `Select a saved product and enter quantity for line ${lineNumber}.`
      : `Complete product name, ${isReagent ? "item description, " : ""}HSN/SAC, quantity, unit, rate and GST for line ${lineNumber}.`;
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

  function chooseSavedShippingAddress(addressMode: SavedShippingAddressMode) {
    if (!selectedCustomer || (addressMode === "shipping" && !selectedCustomer.shipping_address)) return;
    setSavedShippingAddressMode(addressMode);
    setSavedConsignee((current) => ({
      ...consigneeFromCustomer(selectedCustomer, addressMode),
      name: current.name,
      pan: current.pan,
      phone: current.phone,
      email: current.email,
    }));
  }

  function updateLine(key: number, changes: Partial<DraftLine>) {
    if ("pack_size" in changes) setPackSizeErrors((current) => ({ ...current, [key]: "" }));
    setLines((current) => current.map((line) => (line.key === key ? { ...line, ...changes } : line)));
  }

  function chooseProduct(key: number, productId: string) {
    const product = products.find((item) => String(item.id) === productId);
    updateLine(key, {
      product_id: productId,
      product_name: product?.name ?? "",
      description: product?.description ?? product?.name ?? "",
      hsn_sac: product?.hsn_sac ?? "",
      unit: isReagent ? reagentUnit(product?.unit) : (product?.unit ?? "kg"),
      rate: product?.base_rate ?? "",
      gst_rate: product?.gst_rate ?? "18.00",
      cess_rate: product?.cess_rate ?? "0.00",
      ...(!isReagent ? {
        manufacturer_id: product?.manufacturer_id == null ? "" : String(product.manufacturer_id),
        manufacturer_product_code: product?.manufacturer_product_code ?? "",
      } : {}),
    });
  }

  function chooseManufacturer(key: number, manufacturerId: string) {
    setLines((current) => current.map((line) => line.key === key
      ? { ...line, manufacturer_id: manufacturerId, manufacturer_product_code: "", part_no: "" }
      : line));
  }

  async function reloadBillingMasters() {
    const [customerResult, productResult, manufacturerResult] = await Promise.allSettled([
      apiRequest<Customer[]>("/customers?billing=true"),
      apiRequest<Product[]>("/products"),
      isReagent ? apiRequest<Manufacturer[]>("/manufacturers?active_only=true") : Promise.resolve([] as Manufacturer[]),
    ]);
    if (customerResult.status === "fulfilled") setCustomers(customerResult.value);
    if (productResult.status === "fulfilled") setProducts(productResult.value);
    if (manufacturerResult.status === "fulfilled") setManufacturers(manufacturerResult.value.filter((item) => item.is_active));
    const failures = [customerResult, productResult, manufacturerResult].filter((result) => result.status === "rejected");
    if (failures.length) throw failures[0].reason;
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setInvoiceNumberError(null);
    await submission.save();
  }
  const submission = useBillSubmission<Invoice>({
    collection: "/invoices", payload: buildPayload(), validate: (): string | null => savedBill.blocked ? "Load the saved bill successfully before saving; your current work is retained." : validateInvoiceDraft(),
    entrySession: entry, onStartNew,
    onCreated: reloadBillingMasters,
    onFailure: (failure) => {
      if (failure instanceof Error && /invoice.number/i.test(failure.message)) setInvoiceNumberError(failure.message);
      if (failure instanceof ApiError) {
        const detail = failure.detail;
        setVersionConflict(failure.status === 409 && typeof detail === "object" && detail !== null && "code" in detail && detail.code === "version_conflict");
        if (isReagent && Array.isArray(detail)) {
          const nextErrors: Record<number, string> = {};
          for (const issue of detail as { loc?: (string | number)[]; msg?: string }[]) {
            const path = issue.loc ?? [];
            const lineIndex = path[path.indexOf("lines") + 1];
            if (path.at(-1) === "pack_size" && typeof lineIndex === "number" && lines[lineIndex]) {
              nextErrors[lines[lineIndex].key] = issue.msg ?? "Enter a valid Pack/Size.";
            }
          }
          setPackSizeErrors(nextErrors);
        }
        const supplierField = Array.isArray(detail)
          ? detail.some((issue: { loc?: unknown[] }) => issue.loc?.includes("supplier_id"))
          : typeof detail === "object" && detail !== null && "field" in detail && detail.field === "supplier_id";
        if (supplierField) setSupplierError(failure.message);
      }
    },
  });
  const savedBill = useSavedBillLoader<Invoice & { editingSupplier?: Supplier | null }>({
    collection: "/invoices", parameter: "invoice", documentType, authenticated: authStatus === "authenticated", ready: isBillingDataLoaded,
    document: submission.document, busy: submission.busy, unsaved: submission.unsaved,
    hasWork: Boolean(submission.document || manualBuyer.name || invoiceNumberSuffix || lines.some((line) => line.product_name || line.product_id)),
    load: async (id, signal) => {
      const invoice = await apiRequest<Invoice>(`/invoices/${id}`, { signal, cache: "no-store" });
      const editingSupplier = invoice.supplier_id ? await apiRequest<Supplier>(`/suppliers/${invoice.supplier_id}`, { signal, cache: "no-store" }) : null;
      return { ...invoice, editingSupplier };
    },
    hydrate: (invoice) => {
      const buyer = partyFromInvoice(invoice, "buyer");
      previousSavedChoice.current = `manual:${invoice.buyer_customer_id}`;
      previousManualState.current = `manual:${buyer.state_code}`;
      setEntryMode("manual"); setBuyerCustomerId(String(invoice.buyer_customer_id)); setSelectedBuyerSnapshot(null);
      setManualBuyer(buyer); setManualConsignee(partyFromInvoice(invoice, "consignee")); setManualConsigneeSameAsBuyer(false);
      setSelectedSupplier(invoice.editingSupplier ?? null); setLoadedInvoice(invoice);
      setInvoiceDate(invoice.invoice_date); setInvoiceNumberSuffix(invoice.invoice_number?.replace(/^PBPL\/\d{4}-\d{2}\//, "") ?? "");
      setDeliveryNoteDate(invoice.delivery_note_date ?? ""); setPlaceOfSupplyStateCode(invoice.place_of_supply_state_code);
      setPoNumber(invoice.po_number ?? ""); setPaymentTerms(invoice.payment_terms ?? ""); setTransportMode(invoice.transport_mode ?? "");
      setVehicleNumber(invoice.vehicle_number ?? ""); setVehicleType(invoice.vehicle_type ?? ""); setLrNumber(invoice.lr_number ?? "");
      setLrDate(invoice.lr_date ?? ""); setExpectedDeliveryDate(invoice.expected_delivery_date ?? "");
      setFreightCharges(invoice.freight_charges); setPackingCharges(invoice.packing_charges); setOtherCharges(invoice.other_charges); setDiscountAmount(invoice.discount_amount);
      setLines(invoice.lines.map((line, index) => ({ ...initialLine(index + 1), ...line, key: index + 1, product_id: String(line.product_id),
        manufacturer_id: String(manufacturers.find((item) => item.code === line.manufacturer_code)?.id ?? ""),
        manufacturer_product_code: line.manufacturer_product_code ?? line.part_no ?? "", part_no: line.part_no ?? "", pack_size: line.pack_size ?? "" })));
      submission.restore(invoice); setVersionConflict(false); setError(null); setMessage(`Loaded ${invoice.invoice_number ?? `draft #${invoice.id}`}. ${invoice.status === "draft" ? "Edit this saved revision, then Preview and Confirm." : "Submitted/finalized financial data is read-only."}`);
    },
  });
  const isSaving = submission.busy;

  return (
      <AppShell>
        <div className="workspace-page">
          <PageHeader icon={isReagent ? "reagent" : "sales-invoice"} eyebrow={isReagent ? "Reagent workflow" : "Sales workflow"} title={isReagent ? "Reagent bill entry" : "Sales invoice entry"} description={`Create a ${isReagent ? "reagent bill" : "clean invoice"} for customers and vendors. Start with manual entry, or choose saved details when you are ready.${activeSellerProfile ? ` Seller profile: ${activeSellerProfile.name}.` : ""}`}
            action={<Link className="ui-button" href={`/bill-registers/${documentType}`}><AppIcon name={isReagent ? "reagent" : "sales-invoice"} size={18} />{isReagent ? "Reagent bills" : "Sales invoices"}</Link>} />

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

          {savedBill.blocked && <div className="ui-alert mt-4" role={savedBill.error ? "alert" : "status"}>
            {savedBill.error || "Loading the saved bill…"}
            {savedBill.error && <button className="ui-button ml-3" type="button" onClick={savedBill.retry}>Retry loading bill</button>}
          </div>}
          {versionConflict && <button className="ui-button mt-3" type="button" disabled={submission.busy} onClick={savedBill.reloadLatest}>Reload latest revision</button>}

          <section className="mt-8">
            <form data-bill-entry noValidate onSubmit={handleSave} className="ui-panel w-full p-5 sm:p-7 lg:p-8">
              <fieldset disabled={submission.locked || savedBill.blocked} className="min-w-0">
              <div className="flex flex-wrap gap-2 rounded-xl border border-line bg-warm p-2">
                {(["manual", "saved"] as EntryMode[]).map((mode) => (
                  <button key={mode} type="button" onClick={() => setEntryMode(mode)} className={`${toggleClass} ${entryMode === mode ? "bg-ink text-white" : "text-slate-500 hover:bg-white"}`}>
                    {mode === "manual" ? "Manual entry" : "Use saved data"}
                  </button>
                ))}
              </div>

              <InvoiceSupplierPicker profileId={activeSellerProfile?.id ?? null} selected={selectedSupplier}
                onChange={chooseSupplier} validationError={supplierError} />

              <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {entryMode === "saved" ? (
                  <>
                    <label className="text-xs font-semibold text-slate-500">
                      Buyer
                      <div className="mt-2 flex gap-2">
                        <input
                          aria-label="Search saved buyers by name"
                          className={`${inputClass} mt-0 min-w-0 flex-1`}
                          onChange={(event) => setBuyerSearch(event.target.value)}
                          placeholder="Search buyer by name"
                          type="search"
                          value={buyerSearch}
                        />
                        <button aria-label="Search saved buyers" className="ui-button shrink-0 px-3" onClick={() => setBuyerSearch((current) => current.trim())} type="button">
                          <AppIcon name="search" size={16} />
                        </button>
                      </div>
                      <select aria-label="Saved buyer" className={inputClass} onChange={(event) => {
                        setBuyerCustomerId(event.target.value);
                        setSelectedBuyerSnapshot(customers.find(customer => String(customer.id) === event.target.value) ?? null);
                      }} required value={buyerCustomerId}>
                        <option value="">{billingCustomers.length ? filteredCustomers.length ? "Select saved buyer" : "No buyer matches this search" : "No saved buyers yet"}</option>
                        {selectedCustomer && !filteredCustomers.some(customer => customer.id === selectedCustomer.id) && <option value={selectedCustomer.id}>{selectedCustomer.name}</option>}
                        {filteredCustomers.map((customer) => <option key={customer.id} value={customer.id}>{customer.name}</option>)}
                      </select>
                    </label>
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4 sm:col-span-2 lg:col-span-4">
                      <div>
                        <h2 className="text-sm font-semibold text-ink">Consignee details</h2>
                        <p className="mt-1 text-xs leading-5 text-slate-500">Choose the buyer&apos;s billing or saved shipping address. GSTIN is copied from the buyer; enter the remaining consignee details manually.</p>
                      </div>
                      {selectedCustomer ? (
                        <div className="mt-4">
                          <fieldset className="mb-4 rounded-xl border border-slate-200 bg-white p-3">
                            <legend className="px-1 text-xs font-semibold text-ink">Shipping address source</legend>
                            <div className="flex flex-wrap gap-x-6 gap-y-3">
                              <label className="inline-flex items-center gap-2 text-xs font-semibold text-slate-600">
                                <input type="checkbox" className="h-4 w-4 accent-[#147c86]" checked={savedShippingAddressMode === "billing"}
                                  onChange={() => chooseSavedShippingAddress("billing")} />
                                Use billing address for shipping
                              </label>
                              <label className={`inline-flex items-center gap-2 text-xs font-semibold ${selectedCustomer.shipping_address ? "text-slate-600" : "text-slate-400"}`}>
                                <input type="checkbox" className="h-4 w-4 accent-[#147c86]" checked={savedShippingAddressMode === "shipping"}
                                  disabled={!selectedCustomer.shipping_address} aria-describedby={!selectedCustomer.shipping_address ? "saved-shipping-unavailable" : undefined}
                                  onChange={() => chooseSavedShippingAddress("shipping")} />
                                Use saved shipping address
                              </label>
                            </div>
                            {!selectedCustomer.shipping_address && <p id="saved-shipping-unavailable" className="mt-2 text-xs text-slate-500">No saved shipping address for this buyer.</p>}
                          </fieldset>
                          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                            <PartyFields fieldLabelPrefix="Consignee " party={savedConsignee} nameLabel="Consignee name" onChange={updateSavedConsignee} readOnlyFields={savedConsigneeCopiedFields} />
                          </div>
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
                            className="h-4 w-4 accent-[#147c86]"
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
                <div className="text-xs font-semibold text-slate-500 sm:col-span-2">
                  <label htmlFor="invoice-number">Invoice No.</label>
                  <div className="mt-2 flex items-center rounded-xl border border-slate-200 bg-white focus-within:border-[#147c86] focus-within:ring-2 focus-within:ring-[#147c86]/15">
                    <span className="shrink-0 border-r border-slate-200 px-3 py-3 text-slate-600" data-testid="invoice-number-prefix">{invoiceNumberPrefix(invoiceDate)}</span>
                    <input
                      aria-describedby={invoiceNumberError ? "invoice-number-error" : undefined}
                      aria-invalid={Boolean(invoiceNumberError)}
                      className="min-w-0 flex-1 rounded-r-xl bg-transparent px-3 py-3 text-sm font-medium text-ink outline-none"
                      id="invoice-number"
                      maxLength={30}
                      onChange={(event) => { setInvoiceNumberSuffix(event.target.value.toUpperCase()); setInvoiceNumberError(null); }}
                      onInvalid={(event) => { event.preventDefault(); setInvoiceNumberError("Enter an invoice number using 1–30 letters, digits, hyphens or slashes."); event.currentTarget.focus(); }}
                      pattern="[A-Z0-9][A-Z0-9/-]{0,29}"
                      placeholder="Enter invoice number"
                      required
                      value={invoiceNumberSuffix}
                    />
                  </div>
                  {invoiceNumberError && <p className="mt-2 text-xs font-medium text-red-700" id="invoice-number-error" role="alert">{invoiceNumberError}</p>}
                </div>
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
                  <button className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-500 hover:text-ink" onClick={() => setLines((current) => [...current, initialLine(Date.now(), isReagent ? "kg" : "KG")])} type="button">Add line</button>
                </div>
                {lines.map((line, index) => (
                  <div key={line.key} className="rounded-2xl border border-slate-100 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-ink">Line {index + 1}</p>
                      {lines.length > 1 && <button className="text-xs font-semibold text-[#b46b22]" onClick={() => setLines((current) => current.filter((item) => item.key !== line.key))} type="button">Remove</button>}
                    </div>
                    <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
                      {isReagent && (
                        <label className="text-xs font-semibold text-slate-500 lg:col-span-2">
                          MFG / Manufacturer
                          <select className={inputClass} onChange={(event) => chooseManufacturer(line.key, event.target.value)} required value={line.manufacturer_id}>
                            <option value="">{manufacturers.length ? "Select manufacturer" : "Add a manufacturer first"}</option>
                            {manufacturers.map((manufacturer) => <option key={manufacturer.id} value={manufacturer.id}>{manufacturer.code} — {manufacturer.name}</option>)}
                          </select>
                        </label>
                      )}
                      {entryMode === "saved" ? (
                        <label className="text-xs font-semibold text-slate-500 lg:col-span-2">
                          Product
                          <select className={inputClass} onChange={(event) => chooseProduct(line.key, event.target.value)} required value={line.product_id}>
                            <option value="">{selectableProducts.length ? "Select saved product" : "No active products"}</option>
                            {selectableProducts.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}
                          </select>
                        </label>
                      ) : (
                        <label className="text-xs font-semibold text-slate-500 lg:col-span-2">Product name<AutoResizeTextarea className={inputClass} onChange={(event) => updateLine(line.key, { product_name: event.target.value })} required rows={1} value={line.product_name} /></label>
                      )}
                      <label className="text-xs font-semibold text-slate-500 lg:col-span-3">{isReagent ? "Item Description" : "Description"}<AutoResizeTextarea className={inputClass} onChange={(event) => updateLine(line.key, { description: event.target.value })} required={isReagent} rows={1} value={line.description} /></label>
                      <label className="text-xs font-semibold text-slate-500">HSN/SAC<input className={inputClass} onChange={(event) => updateLine(line.key, { hsn_sac: event.target.value })} required={entryMode === "manual"} value={line.hsn_sac} /></label>
                      {isReagent && <label className="text-xs font-semibold text-slate-500">MFG Product Code / Part No.<input className={inputClass} onChange={(event) => updateLine(line.key, { manufacturer_product_code: event.target.value.toUpperCase(), part_no: event.target.value.toUpperCase() })} value={line.manufacturer_product_code} /></label>}
                      <label className="text-xs font-semibold text-slate-500">Quantity<input className={inputClass} onChange={(event) => updateLine(line.key, { quantity: event.target.value })} required value={line.quantity} /></label>
                      {isReagent && <label className="text-xs font-semibold text-slate-500">Pack/Size<input className={inputClass} aria-label="Pack/Size" maxLength={100} placeholder="e.g. 500 g or 100 mL" aria-invalid={Boolean(packSizeErrors[line.key])} aria-describedby={packSizeErrors[line.key] ? `pack-size-${line.key}-error` : undefined} onChange={(event) => updateLine(line.key, { pack_size: event.target.value })} value={line.pack_size} />{packSizeErrors[line.key] && <span id={`pack-size-${line.key}-error`} className="mt-1 block text-xs text-red-700" role="alert">{packSizeErrors[line.key]}</span>}</label>}
                      {isReagent ? (
                        <label className="text-xs font-semibold text-slate-500">Per / Unit<select className={inputClass} onChange={(event) => updateLine(line.key, { unit: event.target.value })} required value={line.unit}>{reagentUnitOptions.map((unit) => <option key={unit.value} value={unit.value}>{unit.label}</option>)}</select></label>
                      ) : (
                        <label className="text-xs font-semibold text-slate-500">Unit<input className={inputClass} onChange={(event) => updateLine(line.key, { unit: event.target.value })} required={entryMode === "manual"} value={line.unit} /></label>
                      )}
                      <label className="text-xs font-semibold text-slate-500">Rate<input className={inputClass} onChange={(event) => updateLine(line.key, { rate: event.target.value })} required={entryMode === "manual"} value={line.rate} /></label>
                      {!isReagent && <label className="text-xs font-semibold text-slate-500">Other charge<input className={inputClass} onChange={(event) => updateLine(line.key, { other_charge: event.target.value })} value={line.other_charge} /></label>}
                      {isReagent ? <label className="text-xs font-semibold text-slate-500">Disc %<input className={inputClass} onChange={(event) => updateLine(line.key, { discount_percent: event.target.value })} value={line.discount_percent} /></label> : <label className="text-xs font-semibold text-slate-500">Line discount<input className={inputClass} onChange={(event) => updateLine(line.key, { discount_amount: event.target.value })} value={line.discount_amount} /></label>}
                      <label className="text-xs font-semibold text-slate-500">GST %<input className={inputClass} onChange={(event) => updateLine(line.key, { gst_rate: event.target.value })} required={entryMode === "manual"} value={line.gst_rate} /></label>
                      {!isReagent && <label className="text-xs font-semibold text-slate-500">Cess %<input className={inputClass} onChange={(event) => updateLine(line.key, { cess_rate: event.target.value })} value={line.cess_rate} /></label>}
                    </div>
                  </div>
                ))}
              </div>

              <button className="mt-6 w-full rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-white hover:bg-[#132f40] disabled:cursor-not-allowed disabled:opacity-60" disabled={isSaving || !isBillingDataLoaded || !sellerProfileReady} type="submit">
                {isSaving ? "Saving draft…" : !sellerProfileReady ? "Set up Seller/GST profile first" : `Save ${isReagent ? "reagent bill" : "sales invoice"} draft`}
              </button>
              </fieldset>
            </form>

            <div className="mt-6">
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
              <BillSubmissionPanel submission={submission} ready={canPreview && !savedBill.blocked} documentNumber={submission.document?.invoice_number} />
            </div>
          </section>
        </div>
      </AppShell>
  );
}
