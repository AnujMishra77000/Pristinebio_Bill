"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { AppShell } from "@/app/components/AppShell";
import { AuthGateStatus, useAuthStatus } from "@/app/components/AuthGate";
import { GrowingTextarea, fieldErrorsFromDetail } from "@/app/components/MasterDataPage";
import { PageHeader } from "@/app/components/PageHeader";
import { ApiError, apiRequest } from "@/app/lib/api";
import type { Branch as SellerProfile, Company, SellerProfileResponse } from "@/app/lib/types";

const inputClass = "ui-input mt-2";

type ProfileFieldProps = {
  name: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  multiline?: boolean;
  maxLength?: number;
  type?: string;
  error?: string;
};

function ProfileField({ name, label, value, onChange, required, multiline, maxLength, type, error }: ProfileFieldProps) {
  const props = {
    id: `profile-${name}`,
    name,
    value,
    required,
    maxLength,
    "aria-invalid": Boolean(error),
    "aria-describedby": error ? `profile-error-${name}` : undefined,
  };
  return (
    <div className={multiline ? "sm:col-span-2 xl:col-span-3" : "min-w-0"}>
      <label className="ui-label" htmlFor={props.id}>{label} {required && <span className="text-peacock" aria-hidden="true">*</span>}</label>
      {multiline ? <GrowingTextarea {...props} className={`${inputClass} min-h-24 resize-y`} onChange={(event) => onChange(event.target.value)} /> : <input {...props} className={inputClass} type={type ?? "text"} onChange={(event) => onChange(event.target.value)} />}
      {error && <p id={`profile-error-${name}`} className="mt-2 text-xs font-medium text-peacock-deep">{error}</p>}
    </div>
  );
}

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
  secondary_email: string;
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
  secondary_email: "",
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
    secondary_email: profile.secondary_email ?? "",
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
  const [loadError, setLoadError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);

  const primaryCompany = companies[0] ?? null;

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
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
      setLoadError(requestError instanceof ApiError ? requestError.message : "Unable to load Seller/GST profile.");
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
    setFieldErrors({});
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
          secondary_email: sellerForm.secondary_email || null,
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
      if (requestError instanceof ApiError) setFieldErrors(fieldErrorsFromDetail(requestError.detail, [...Object.keys(companyForm), ...Object.keys(sellerForm)]));
    } finally {
      setIsSavingSellerProfile(false);
    }
  }

  function editProfile(profile: SellerProfile) {
    setEditingProfileId(profile.id);
    setSellerForm(sellerFormFromProfile(profile));
    setMessage("Editing Seller/GST profile.");
    setError(null);
    setFieldErrors({});
  }

  function companyField(name: keyof CompanyForm, label: string, options: Partial<Pick<ProfileFieldProps, "required" | "multiline" | "maxLength">> = {}) {
    return <ProfileField name={name} label={label} value={companyForm[name]} error={fieldErrors[name]} {...options} onChange={(value) => setCompanyForm((current) => ({ ...current, [name]: name === "pan" ? value.toUpperCase() : value }))} />;
  }

  function sellerField(name: Exclude<keyof SellerProfileForm, "is_active">, label: string, options: Partial<Pick<ProfileFieldProps, "required" | "multiline" | "maxLength" | "type">> = {}) {
    return <ProfileField name={name} label={label} value={sellerForm[name]} error={fieldErrors[name]} {...options} onChange={(value) => setSellerForm((current) => ({ ...current, [name]: name === "gstin" || name === "bank_ifsc_code" ? value.toUpperCase() : value }))} />;
  }

  return (
    <AuthGateStatus status={authStatus}>
      <AppShell>
        <div className="workspace-page">
          <PageHeader
            icon="seller-profile"
            eyebrow="Company setup"
            title="Seller/GST profile"
            description="Your company identity, GST details and invoice defaults for future bills."
          />

          {isLoading && <div className="ui-panel mt-7 animate-pulse text-sm text-slate" role="status">Loading Seller/GST profile…</div>}
          {loadError && (
            <div className="ui-alert mt-7" role="alert">
              <p>{loadError}</p>
              <button className="ui-button mt-3" type="button" onClick={() => void loadData()} disabled={isLoading}>Try again</button>
            </div>
          )}

          {!isLoading && !loadError && (
            <div className="mt-7 space-y-6">
              <form onSubmit={handleProfileSubmit} className="ui-panel" aria-busy={isSavingSellerProfile}>
                <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line pb-5">
                  <div>
                    <h2 className="ui-section-title">{editingProfileId ? "Edit company profile" : "Create company profile"}</h2>
                    <p className="mt-2 text-sm text-slate">{primaryCompany ? "Update the details used on future invoices and purchase orders." : "Add your company and GST details to get ready for billing."}</p>
                  </div>
                  {editingProfileId && <button className="ui-button" type="button" onClick={() => { setEditingProfileId(null); setSellerForm(blankSellerProfile); setError(null); setFieldErrors({}); setMessage(null); }}>New profile</button>}
                </div>

                <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-peacock-deep">Company details</h3>
                  <p className="text-xs text-slate">Fields marked <span className="font-bold text-peacock">*</span> are required</p>
                </div>
                <div className="mt-5 grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
                  {companyField("legal_name", "Legal company name", { required: true, multiline: true })}
                  {companyField("trade_name", "Trade name")}
                  {companyField("pan", "PAN", { maxLength: 10 })}
                  {companyField("registered_address", "Registered address", { multiline: true })}
                </div>

                <p className="mt-3 text-xs leading-5 text-slate">Registered address is printed below your company brand on new bills. Supplier and pickup-address edits do not change it. If it is blank, the GST address below is saved as the company address for that bill.</p>
                <h3 className="mt-7 border-t border-line pt-6 text-sm font-semibold text-peacock-deep">GST registration & contact</h3>
                <div className="mt-5 grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
                  {sellerField("name", "Profile label", { required: true })}
                  {sellerField("gstin", "GSTIN", { required: true, maxLength: 15 })}
                  {sellerField("address_line1", "Address line 1", { required: true, multiline: true })}
                  {sellerField("address_line2", "Address line 2", { multiline: true })}
                  {sellerField("city", "City", { required: true })}
                  {sellerField("state", "State", { required: true })}
                  {sellerField("state_code", "State code", { required: true, maxLength: 2 })}
                  {sellerField("postal_code", "Postal code", { required: true })}
                  {sellerField("phone", "Phone")}
                  {sellerField("email", "Email", { type: "email" })}
                  {sellerField("secondary_email", "Second email", { type: "email" })}
                </div>

                <div className="mt-7 rounded-2xl border border-line bg-warm p-5">
                  <h3 className="text-sm font-semibold text-peacock-deep">Default invoice bank details</h3>
                  <p className="mt-2 text-sm leading-6 text-slate">Used on new invoices when a separate bank account is not selected.</p>
                  <div className="mt-5 grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
                    {sellerField("bank_name", "Bank name")}
                    {sellerField("bank_branch_name", "Bank branch")}
                    {sellerField("bank_account_name", "Account name")}
                    {sellerField("bank_account_number", "Account number")}
                    {sellerField("bank_ifsc_code", "IFSC code", { maxLength: 20 })}
                  </div>
                </div>

                <div className="mt-6">
                  {sellerField("terms_body", "Terms and conditions", { multiline: true, maxLength: 10000 })}
                  <p className="mt-2 text-xs text-slate">Enter each term on a separate line.</p>
                </div>
                <label className="mt-5 flex w-fit items-center gap-3 rounded-xl border border-line bg-warm px-4 py-3 text-sm font-medium text-ink">
                  <input checked={sellerForm.is_active} className="h-4 w-4 rounded border-line accent-peacock" onChange={(event) => setSellerForm((current) => ({ ...current, is_active: event.target.checked }))} type="checkbox" />
                  Active for billing
                </label>

                {error && <div className="ui-alert mt-5" role="alert">{error}</div>}
                {message && <div className="mt-5 rounded-xl border border-peacock/20 bg-warm-green px-4 py-3 text-sm font-medium text-peacock-deep" role="status">{message}</div>}
                <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-line pt-5">
                  <p className="text-xs text-slate">Company and seller details are saved together.</p>
                  <button className="ui-button-primary w-full sm:w-auto" disabled={isSavingSellerProfile} type="submit">
                    {isSavingSellerProfile ? "Saving…" : editingProfileId ? "Update Seller/GST profile" : "Save company and Seller/GST profile"}
                  </button>
                </div>
              </form>

              <article className="ui-panel">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
                  <h2 className="ui-section-title">Saved profiles</h2>
                  <span className="ui-badge">{sellerProfiles.length} profile{sellerProfiles.length === 1 ? "" : "s"}</span>
                </div>
                <div className="divide-y divide-line">
                  {sellerProfiles.map((profile) => (
                    <div key={profile.id} className="flex flex-wrap items-start justify-between gap-4 py-5">
                      <div className="min-w-0 flex-1">
                        <p className="break-words text-base font-semibold text-ink">{profile.name}</p>
                        <p className="mt-2 break-words text-sm text-slate">{profile.gstin} · {profile.city}, {profile.state}</p>
                        <span className="ui-badge mt-3">{profile.is_active ? "Active for billing" : "Inactive"}</span>
                      </div>
                      <button className="ui-button" onClick={() => editProfile(profile)} type="button">Edit profile</button>
                    </div>
                  ))}
                  {sellerProfiles.length === 0 && <div className="ui-empty py-10"><p className="font-semibold text-ink">No Seller/GST profile yet</p><p className="mt-2 text-sm text-slate">Complete the form above to save your company details.</p></div>}
                </div>
              </article>
            </div>
          )}
        </div>
      </AppShell>
    </AuthGateStatus>
  );
}
