"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { AppShell } from "@/app/components/AppShell";
import { AuthGateStatus, useAuthStatus } from "@/app/components/AuthGate";
import { ApiError, apiRequest } from "@/app/lib/api";
import type { SellerProfileResponse } from "@/app/lib/types";

export type FieldConfig = {
  name: string;
  label: string;
  type?: "text" | "email" | "number" | "textarea" | "checkbox";
  required?: boolean;
};

type FormValue = string | boolean;

type MasterRecord = Record<string, unknown>;

type MasterDataPageProps = {
  title: string;
  description: string;
  endpoint: string;
  fields: FieldConfig[];
  columns: { key: string; label: string }[];
  initialForm: Record<string, FormValue>;
  transformPayload?: (payload: Record<string, unknown>) => Record<string, unknown>;
};

const SELLER_PROFILE_REQUIRED_MESSAGE = "Set up Seller/GST profile first before creating this record.";

function toPayload(fields: FieldConfig[], form: Record<string, FormValue>) {
  return fields.reduce<Record<string, unknown>>((payload, field) => {
    const value = form[field.name];
    if (field.type === "checkbox") {
      payload[field.name] = Boolean(value);
      return payload;
    }
    if (field.type === "number") {
      payload[field.name] = value === "" ? null : Number(value);
      return payload;
    }
    payload[field.name] = value === "" && !field.required ? null : value;
    return payload;
  }, {});
}

function readCell(record: MasterRecord, key: string) {
  return key.split(".").reduce<unknown>((value, part) => {
    if (value && typeof value === "object" && part in value) {
      return (value as Record<string, unknown>)[part];
    }
    return undefined;
  }, record);
}

function formatCell(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function MasterDataPage({
  title,
  description,
  endpoint,
  fields,
  columns,
  initialForm,
  transformPayload,
}: MasterDataPageProps) {
  const authStatus = useAuthStatus();
  const requiresSellerProfile = fields.some((field) => field.name === "branch_id");
  const visibleFields = fields.filter((field) => field.name !== "branch_id");
  const [records, setRecords] = useState<MasterRecord[]>([]);
  const [form, setForm] = useState<Record<string, FormValue>>(initialForm);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sellerProfileId, setSellerProfileId] = useState<number | null>(null);
  const [sellerProfileChecked, setSellerProfileChecked] = useState(!requiresSellerProfile);

  const loadRecords = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      setRecords(await apiRequest<MasterRecord[]>(endpoint));
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to load records.");
    } finally {
      setIsLoading(false);
    }
  }, [endpoint]);

  useEffect(() => {
    if (authStatus !== "authenticated") return;
    void loadRecords();
  }, [authStatus, loadRecords]);

  useEffect(() => {
    if (authStatus !== "authenticated" || !requiresSellerProfile) return;

    let isActive = true;
    async function loadSellerProfile() {
      try {
        const response = await apiRequest<SellerProfileResponse>("/companies/profile");
        const profile = response.seller_profile;
        if (!isActive) return;
        setSellerProfileId(profile?.id ?? null);
        setSellerProfileChecked(true);
        if (profile) {
          setForm((current) => ({ ...current, branch_id: String(profile.id) }));
        }
      } catch (requestError) {
        if (!isActive) return;
        setSellerProfileChecked(true);
        setError(requestError instanceof ApiError ? requestError.message : "Unable to load Seller/GST profile.");
      }
    }

    void loadSellerProfile();
    return () => {
      isActive = false;
    };
  }, [authStatus, requiresSellerProfile]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (requiresSellerProfile && !sellerProfileId) {
      setError(SELLER_PROFILE_REQUIRED_MESSAGE);
      return;
    }

    setIsSubmitting(true);
    try {
      const formForPayload = requiresSellerProfile && sellerProfileId
        ? { ...form, branch_id: String(sellerProfileId) }
        : form;
      const payload = transformPayload ? transformPayload(toPayload(fields, formForPayload)) : toPayload(fields, formForPayload);
      await apiRequest(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setForm(requiresSellerProfile && sellerProfileId ? { ...initialForm, branch_id: String(sellerProfileId) } : initialForm);
      await loadRecords();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to save record.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthGateStatus status={authStatus}>
      <AppShell>
        <div className="mx-auto max-w-[1440px] px-5 py-8 sm:px-8 lg:px-10 lg:py-10">
          <section className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
            <div>
              <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-[#6f8fe8]">Master records</p>
              <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-ink sm:text-[40px]">{title}</h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500 sm:text-[15px]">{description}</p>
            </div>
          </section>

          {requiresSellerProfile && sellerProfileChecked && !sellerProfileId && (
            <div className="mt-6 rounded-xl border border-[#ffe1bd] bg-[#fff8ef] px-4 py-3 text-sm font-medium text-[#b46b22]">
              {SELLER_PROFILE_REQUIRED_MESSAGE}{" "}
              <Link className="font-bold underline decoration-[#b46b22]/40 underline-offset-4" href="/branches">
                Open Seller/GST profile
              </Link>
            </div>
          )}

          <section className="mt-8 grid gap-6 xl:grid-cols-[0.9fr_1.4fr]">
            <form onSubmit={handleSubmit} className="rounded-[22px] border border-slate-200/80 bg-white p-5 shadow-panel sm:p-6">
              <h2 className="text-lg font-semibold tracking-tight text-ink">Create record</h2>
              <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
                {visibleFields.map((field) => {
                  const value = form[field.name];
                  if (field.type === "checkbox") {
                    return (
                      <label key={field.name} className="flex items-center gap-3 rounded-xl border border-slate-200 px-3.5 py-3 text-sm font-medium text-slate-600">
                        <input
                          checked={Boolean(value)}
                          className="h-4 w-4 rounded border-slate-300"
                          onChange={(event) => setForm((current) => ({ ...current, [field.name]: event.target.checked }))}
                          type="checkbox"
                        />
                        {field.label}
                      </label>
                    );
                  }
                  const inputClass = "mt-1.5 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-ink outline-none transition-colors placeholder:text-slate-300 focus:border-[#6f8fe8]";
                  return (
                    <label key={field.name} className="text-xs font-semibold text-slate-500">
                      {field.label}
                      {field.type === "textarea" ? (
                        <textarea
                          className={`${inputClass} min-h-24 resize-y`}
                          onChange={(event) => setForm((current) => ({ ...current, [field.name]: event.target.value }))}
                          required={field.required}
                          value={String(value)}
                        />
                      ) : (
                        <input
                          className={inputClass}
                          onChange={(event) => setForm((current) => ({ ...current, [field.name]: event.target.value }))}
                          required={field.required}
                          type={field.type ?? "text"}
                          value={String(value)}
                        />
                      )}
                    </label>
                  );
                })}
              </div>
              {error && <p className="mt-4 rounded-xl bg-[#fff0df] px-3.5 py-3 text-sm font-medium text-[#b46b22]">{error}</p>}
              <button
                className="mt-6 w-full rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-[#243653] disabled:cursor-not-allowed disabled:opacity-60"
                disabled={isSubmitting || (requiresSellerProfile && (!sellerProfileChecked || !sellerProfileId))}
                type="submit"
              >
                {isSubmitting ? "Saving…" : requiresSellerProfile && !sellerProfileId ? "Set up Seller/GST profile first" : "Save record"}
              </button>
            </form>

            <article className="overflow-hidden rounded-[22px] border border-slate-200/80 bg-white shadow-panel">
              <div className="border-b border-slate-100 px-5 py-4 sm:px-6">
                <h2 className="text-lg font-semibold tracking-tight text-ink">Records</h2>
                <p className="mt-1 text-xs text-slate-400">{isLoading ? "Loading…" : `${records.length} record${records.length === 1 ? "" : "s"}`}</p>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-100 text-left text-sm">
                  <thead className="bg-slate-50 text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
                    <tr>
                      {columns.map((column) => (
                        <th key={column.key} className="px-5 py-3 sm:px-6">{column.label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {records.map((record, index) => (
                      <tr key={typeof record.id === "number" ? record.id : index}>
                        {columns.map((column) => (
                          <td key={column.key} className="max-w-xs truncate px-5 py-4 text-slate-600 sm:px-6">
                            {formatCell(readCell(record, column.key))}
                          </td>
                        ))}
                      </tr>
                    ))}
                    {!isLoading && records.length === 0 && (
                      <tr>
                        <td className="px-5 py-10 text-center text-sm text-slate-400 sm:px-6" colSpan={columns.length}>
                          No records yet.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </article>
          </section>
        </div>
      </AppShell>
    </AuthGateStatus>
  );
}
