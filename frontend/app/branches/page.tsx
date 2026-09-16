"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { AppShell } from "@/app/components/AppShell";
import { AuthGateStatus, useAuthStatus } from "@/app/components/AuthGate";
import { ApiError, apiRequest } from "@/app/lib/api";
import type { Branch as SellerProfile, Company, SellerProfileResponse } from "@/app/lib/types";

const inputClass = "mt-1.5 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-ink outline-none transition-colors focus:border-[#6f8fe8]";

type CompanyForm = {
  legal_name: string;
  trade_name: string;
  pan: string;
  registered_address: string;
  logo_data_uri: string;
};

type SellerProfileForm = {
  name: string;
  gstin: string;
  address_line1: string;
  address_line2: string;
  city: string;
  state: string;
  state_code: string;
  postal_code: string;
  phone: string;
  email: string;
  bank_name: string;
  bank_branch_name: string;
  bank_account_name: string;
  bank_account_number: string;
  bank_ifsc_code: string;
  terms_body: string;
  is_active: boolean;
};

const blankCompany: CompanyForm = {
  legal_name: "",
  trade_name: "",
  pan: "",
  registered_address: "",
  logo_data_uri: "",
};

const blankSellerProfile: SellerProfileForm = {
  name: "Primary GSTIN",
  gstin: "",
  address_line1: "",
  address_line2: "",
  city: "",
  state: "",
  state_code: "36",
  postal_code: "",
  phone: "",
  email: "",
  bank_name: "",
  bank_branch_name: "",
  bank_account_name: "",
  bank_account_number: "",
  bank_ifsc_code: "",
  terms_body: "",
  is_active: true,
};

function companyPayload(form: CompanyForm) {
  return {
    legal_name: form.legal_name,
    trade_name: form.trade_name || null,
    pan: form.pan || null,
    registered_address: form.registered_address || null,
    logo_data_uri: form.logo_data_uri || null,
    is_active: true,
  };
}

function companyFormFromCompany(company: Company): CompanyForm {
  return {
    legal_name: company.legal_name,
    trade_name: company.trade_name ?? "",
    pan: company.pan ?? "",
    registered_address: company.registered_address ?? "",
    logo_data_uri: company.logo_data_uri ?? "",
  };
}

function sellerFormFromProfile(profile: SellerProfile): SellerProfileForm {
  return {
    name: profile.name,
    gstin: profile.gstin,
    address_line1: profile.address_line1,
    address_line2: profile.address_line2 ?? "",
    city: profile.city,
    state: profile.state,
    state_code: profile.state_code,
    postal_code: profile.postal_code,
    phone: profile.phone ?? "",
    email: profile.email ?? "",
    bank_name: profile.bank_name ?? "",
    bank_branch_name: profile.bank_branch_name ?? "",
    bank_account_name: profile.bank_account_name ?? "",
    bank_account_number: profile.bank_account_number ?? "",
    bank_ifsc_code: profile.bank_ifsc_code ?? "",
    terms_body: profile.terms_body ?? "",
    is_active: profile.is_active,
  };
}

export default function SellerProfilePage() {
  const authStatus = useAuthStatus();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [sellerProfiles, setSellerProfiles] = useState<SellerProfile[]>([]);
  const [companyForm, setCompanyForm] = useState<CompanyForm>(blankCompany);
  const [sellerForm, setSellerForm] = useState<SellerProfileForm>(blankSellerProfile);
  const [editingProfileId, setEditingProfileId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSavingSellerProfile, setIsSavingSellerProfile] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const primaryCompany = companies[0] ?? null;

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const profile = await apiRequest<SellerProfileResponse>("/companies/profile");
      setCompanies(profile.company ? [profile.company] : []);
      setSellerProfiles(profile.seller_profile ? [profile.seller_profile] : []);
      if (profile.company) setCompanyForm(companyFormFromCompany(profile.company));
      if (profile.seller_profile) {
        setEditingProfileId(profile.seller_profile.id);
        setSellerForm(sellerFormFromProfile(profile.seller_profile));
      } else {
        setEditingProfileId(null);
        setSellerForm(blankSellerProfile);
      }
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to load Seller/GST profile.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authStatus !== "authenticated") return;
    void loadData();
  }, [authStatus, loadData]);

  async function handleProfileSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    if (!companyForm.legal_name.trim() || !sellerForm.gstin.trim() || !sellerForm.address_line1.trim() || !sellerForm.city.trim() || !sellerForm.state.trim() || !sellerForm.postal_code.trim()) {
      setError("Complete the legal company name, GSTIN, seller address, city, state and postal code before saving.");
      return;
    }

    setIsSavingSellerProfile(true);
    try {
      const response = await apiRequest<SellerProfileResponse>("/companies/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...companyPayload(companyForm),
          seller_name: sellerForm.name,
          gstin: sellerForm.gstin,
          address_line1: sellerForm.address_line1,
          address_line2: sellerForm.address_line2 || null,
          city: sellerForm.city,
          state: sellerForm.state,
          state_code: sellerForm.state_code,
          postal_code: sellerForm.postal_code,
          phone: sellerForm.phone || null,
          email: sellerForm.email || null,
          bank_name: sellerForm.bank_name || null,
          bank_branch_name: sellerForm.bank_branch_name || null,
          bank_account_name: sellerForm.bank_account_name || null,
          bank_account_number: sellerForm.bank_account_number || null,
          bank_ifsc_code: sellerForm.bank_ifsc_code || null,
          terms_body: sellerForm.terms_body || null,
          is_active: sellerForm.is_active,
        }),
      });
      setCompanies(response.company ? [response.company] : []);
      setSellerProfiles(response.seller_profile ? [response.seller_profile] : []);
      if (response.company) setCompanyForm(companyFormFromCompany(response.company));
      setEditingProfileId(response.seller_profile?.id ?? null);
      setMessage("Seller/GST profile saved. Billing will use it automatically.");
      if (response.seller_profile) setSellerForm(sellerFormFromProfile(response.seller_profile));
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to save Seller/GST profile.");
    } finally {
      setIsSavingSellerProfile(false);
    }
  }

  function editProfile(profile: SellerProfile) {
    setEditingProfileId(profile.id);
    setSellerForm(sellerFormFromProfile(profile));
    setMessage("Editing Seller/GST profile.");
    setError(null);
  }

  return (
    <AuthGateStatus status={authStatus}>
      <AppShell>
        <div className="mx-auto max-w-[1440px] px-5 py-8 sm:px-8 lg:px-10 lg:py-10">
          <section>
            <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-[#6f8fe8]">Company setup</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-ink sm:text-[40px]">Seller/GST profile</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500 sm:text-[15px]">
              Set this once for your company. Sales invoices and purchase orders use these legal seller details automatically, so billing pages do not need branch selection.
            </p>
          </section>

          {(error || message) && (
            <div className={`mt-6 rounded-xl px-4 py-3 text-sm font-medium ${error ? "bg-[#fff0df] text-[#b46b22]" : "bg-[#dff8ee] text-[#24735b]"}`}>
              {error ?? message}
            </div>
          )}

          {isLoading && <p className="mt-6 text-sm text-slate-500">Loading Seller/GST profile…</p>}

          {!isLoading && (
            <section className="mt-8 grid gap-6 xl:grid-cols-[0.95fr_1.35fr]">
              <div className="space-y-6">
                <form onSubmit={handleProfileSubmit} className="rounded-[22px] border border-slate-200/80 bg-white p-5 shadow-panel sm:p-6">
                  <h2 className="text-lg font-semibold tracking-tight text-ink">Company profile</h2>
                  <p className="mt-2 rounded-xl bg-slate-50 px-3.5 py-3 text-sm leading-6 text-slate-500">
                    {primaryCompany ? "Update the legal details used on future bills." : "Create the company and Seller/GST profile together."}
                  </p>
                  <div className="mt-5 grid gap-4">
                    <label className="text-xs font-semibold text-slate-500">Legal company name<input className={inputClass} onChange={(event) => setCompanyForm((current) => ({ ...current, legal_name: event.target.value }))} required value={companyForm.legal_name} /></label>
                    <label className="text-xs font-semibold text-slate-500">Trade name<input className={inputClass} onChange={(event) => setCompanyForm((current) => ({ ...current, trade_name: event.target.value }))} value={companyForm.trade_name} /></label>
                    <label className="text-xs font-semibold text-slate-500">PAN<input className={inputClass} maxLength={10} onChange={(event) => setCompanyForm((current) => ({ ...current, pan: event.target.value.toUpperCase() }))} value={companyForm.pan} /></label>
                    <label className="text-xs font-semibold text-slate-500">Registered address<textarea className={`${inputClass} min-h-24 resize-y`} onChange={(event) => setCompanyForm((current) => ({ ...current, registered_address: event.target.value }))} value={companyForm.registered_address} /></label>
                  </div>
                  <button className="mt-6 w-full rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-[#243653] disabled:cursor-not-allowed disabled:opacity-60" disabled={isSavingSellerProfile} type="submit">
                    {isSavingSellerProfile ? "Saving…" : "Save company and Seller/GST profile"}
                  </button>
                </form>

                <article className="rounded-[22px] border border-slate-200/80 bg-white p-5 shadow-panel sm:p-6">
                  <h2 className="text-lg font-semibold tracking-tight text-ink">How billing uses this</h2>
                  <p className="mt-3 text-sm leading-6 text-slate-500">
                    Invoice and PO forms stay clean: you enter buyer/supplier and item details only. The PDF engine pulls seller GSTIN, address and contact from this profile.
                  </p>
                </article>
              </div>

              <div className="space-y-6">
                <form onSubmit={handleProfileSubmit} className="rounded-[22px] border border-slate-200/80 bg-white p-5 shadow-panel sm:p-6">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h2 className="text-lg font-semibold tracking-tight text-ink">{editingProfileId ? "Edit Seller/GST profile" : "Create Seller/GST profile"}</h2>
                      <p className="mt-1 text-xs text-slate-400">Used automatically for tax invoice and purchase-order PDFs.</p>
                    </div>
                    {editingProfileId && (
                      <button className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-500 hover:text-ink" onClick={() => { setEditingProfileId(null); setSellerForm(blankSellerProfile); }} type="button">
                        New profile
                      </button>
                    )}
                  </div>
                  <div className="mt-5 grid gap-4 sm:grid-cols-2">
                    <label className="text-xs font-semibold text-slate-500">Profile label<input className={inputClass} onChange={(event) => setSellerForm((current) => ({ ...current, name: event.target.value }))} required value={sellerForm.name} /></label>
                    <label className="text-xs font-semibold text-slate-500">GSTIN<input className={inputClass} maxLength={15} onChange={(event) => setSellerForm((current) => ({ ...current, gstin: event.target.value.toUpperCase() }))} required value={sellerForm.gstin} /></label>
                    <label className="text-xs font-semibold text-slate-500 sm:col-span-2">Address line 1<textarea className={`${inputClass} min-h-16 resize-y`} onChange={(event) => setSellerForm((current) => ({ ...current, address_line1: event.target.value }))} required value={sellerForm.address_line1} /></label>
                    <label className="text-xs font-semibold text-slate-500 sm:col-span-2">Address line 2<textarea className={`${inputClass} min-h-16 resize-y`} onChange={(event) => setSellerForm((current) => ({ ...current, address_line2: event.target.value }))} value={sellerForm.address_line2} /></label>
                    <label className="text-xs font-semibold text-slate-500">City<input className={inputClass} onChange={(event) => setSellerForm((current) => ({ ...current, city: event.target.value }))} required value={sellerForm.city} /></label>
                    <label className="text-xs font-semibold text-slate-500">State<input className={inputClass} onChange={(event) => setSellerForm((current) => ({ ...current, state: event.target.value }))} required value={sellerForm.state} /></label>
                    <label className="text-xs font-semibold text-slate-500">State code<input className={inputClass} maxLength={2} onChange={(event) => setSellerForm((current) => ({ ...current, state_code: event.target.value }))} required value={sellerForm.state_code} /></label>
                    <label className="text-xs font-semibold text-slate-500">Postal code<input className={inputClass} onChange={(event) => setSellerForm((current) => ({ ...current, postal_code: event.target.value }))} required value={sellerForm.postal_code} /></label>
                    <label className="text-xs font-semibold text-slate-500">Phone<input className={inputClass} onChange={(event) => setSellerForm((current) => ({ ...current, phone: event.target.value }))} value={sellerForm.phone} /></label>
                    <label className="text-xs font-semibold text-slate-500">Email<input className={inputClass} onChange={(event) => setSellerForm((current) => ({ ...current, email: event.target.value }))} type="email" value={sellerForm.email} /></label>
                    <div className="sm:col-span-2 rounded-2xl border border-[#cfe8dc] bg-[#f4fbf7] p-4">
                      <h3 className="text-sm font-semibold text-ink">Default invoice bank details</h3>
                      <p className="mt-1 text-xs leading-5 text-slate-500">These saved values appear in the lower-left bank section of new invoice PDFs when no separate bank master is selected.</p>
                      <div className="mt-4 grid gap-4 sm:grid-cols-2">
                        <label className="text-xs font-semibold text-slate-500">Bank name<input className={inputClass} onChange={(event) => setSellerForm((current) => ({ ...current, bank_name: event.target.value }))} value={sellerForm.bank_name} /></label>
                        <label className="text-xs font-semibold text-slate-500">Bank branch<input className={inputClass} onChange={(event) => setSellerForm((current) => ({ ...current, bank_branch_name: event.target.value }))} value={sellerForm.bank_branch_name} /></label>
                        <label className="text-xs font-semibold text-slate-500">Account name<input className={inputClass} onChange={(event) => setSellerForm((current) => ({ ...current, bank_account_name: event.target.value }))} value={sellerForm.bank_account_name} /></label>
                        <label className="text-xs font-semibold text-slate-500">Account number<input className={inputClass} onChange={(event) => setSellerForm((current) => ({ ...current, bank_account_number: event.target.value }))} value={sellerForm.bank_account_number} /></label>
                        <label className="text-xs font-semibold text-slate-500 sm:col-span-2">IFSC code<input className={inputClass} maxLength={20} onChange={(event) => setSellerForm((current) => ({ ...current, bank_ifsc_code: event.target.value.toUpperCase() }))} value={sellerForm.bank_ifsc_code} /></label>
                      </div>
                    </div>
                    <label className="text-xs font-semibold text-slate-500 sm:col-span-2">Terms and conditions<textarea className={`${inputClass} min-h-28 resize-y`} maxLength={10000} onChange={(event) => setSellerForm((current) => ({ ...current, terms_body: event.target.value }))} placeholder="One term per line" value={sellerForm.terms_body} /></label>
                    <label className="flex items-center gap-3 rounded-xl border border-slate-200 px-3.5 py-3 text-sm font-medium text-slate-600">
                      <input checked={sellerForm.is_active} className="h-4 w-4 rounded border-slate-300" onChange={(event) => setSellerForm((current) => ({ ...current, is_active: event.target.checked }))} type="checkbox" />
                      Active for billing
                    </label>
                  </div>
                  <button className="mt-6 w-full rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-[#243653] disabled:cursor-not-allowed disabled:opacity-60" disabled={isSavingSellerProfile} type="submit">
                    {isSavingSellerProfile ? "Saving…" : editingProfileId ? "Update Seller/GST profile" : "Save Seller/GST profile"}
                  </button>
                </form>

                <article className="overflow-hidden rounded-[22px] border border-slate-200/80 bg-white shadow-panel">
                  <div className="border-b border-slate-100 px-5 py-4 sm:px-6">
                    <h2 className="text-lg font-semibold tracking-tight text-ink">Saved Seller/GST profiles</h2>
                    <p className="mt-1 text-xs text-slate-400">{sellerProfiles.length} profile{sellerProfiles.length === 1 ? "" : "s"}</p>
                  </div>
                  <div className="divide-y divide-slate-100">
                    {sellerProfiles.map((profile) => (
                      <div key={profile.id} className="flex flex-wrap items-start justify-between gap-4 px-5 py-4 sm:px-6">
                        <div>
                          <p className="text-sm font-semibold text-ink">{profile.name}</p>
                          <p className="mt-1 text-xs text-slate-400">{profile.gstin} · {profile.city}, {profile.state}</p>
                          <p className="mt-1 text-xs text-slate-400">{profile.is_active ? "Active for billing" : "Inactive"}</p>
                        </div>
                        <button className="rounded-lg bg-[#f0f4ff] px-3 py-2 text-xs font-semibold text-[#516bb1]" onClick={() => editProfile(profile)} type="button">
                          Edit
                        </button>
                      </div>
                    ))}
                    {sellerProfiles.length === 0 && <p className="px-5 py-10 text-center text-sm text-slate-400 sm:px-6">No Seller/GST profile yet.</p>}
                  </div>
                </article>
              </div>
            </section>
          )}
        </div>
      </AppShell>
    </AuthGateStatus>
  );
}
