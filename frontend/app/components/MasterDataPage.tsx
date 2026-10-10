"use client";

import { ComponentProps, FormEvent, TextareaHTMLAttributes, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";

import { AppShell } from "@/app/components/AppShell";
import { AuthGateStatus, useAuthStatus } from "@/app/components/AuthGate";
import { PageHeader } from "@/app/components/PageHeader";
import { ApiError, apiRequest } from "@/app/lib/api";
import type { SellerProfileResponse } from "@/app/lib/types";

export type FieldConfig = {
  name: string;
  label: string;
  type?: "text" | "email" | "number" | "textarea" | "checkbox" | "select";
  required?: boolean;
  section?: string;
  options?: { value: string; label: string }[];
  valueType?: "number";
};

type FormValue = string | boolean;

type MasterRecord = Record<string, unknown>;

type MasterDataPageProps = {
  icon: ComponentProps<typeof PageHeader>["icon"];
  title: string;
  description: string;
  endpoint: string;
  listEndpoint?: string;
  listPageSize?: number;
  fields: FieldConfig[];
  columns: { key: string; label: string }[];
  initialForm: Record<string, FormValue>;
  transformPayload?: (payload: Record<string, unknown>) => Record<string, unknown>;
  editable?: boolean;
  recordToForm?: (record: MasterRecord) => Record<string, FormValue>;
  recordActions?: {
    activeField?: string;
    defaultField?: string;
    allowDelete?: boolean;
  };
};

const SELLER_PROFILE_REQUIRED_MESSAGE = "Set up Seller/GST profile first before creating this record.";

export function GrowingTextarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const resize = () => {
      if (!ref.current) return;
      ref.current.style.height = "auto";
      ref.current.style.height = `${ref.current.scrollHeight + 2}px`;
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [props.value]);
  return <textarea {...props} ref={ref} />;
}

export function fieldErrorsFromDetail(detail: unknown, names: string[]): Record<string, string> {
  if (detail && typeof detail === "object" && "field" in detail && "message" in detail && typeof detail.field === "string" && typeof detail.message === "string" && names.includes(detail.field)) return { [detail.field]: detail.message };
  if (!Array.isArray(detail)) return {};
  const errors: Record<string, string> = {};
  for (const issue of detail) {
    if (!issue || typeof issue !== "object" || !Array.isArray(issue.loc) || typeof issue.msg !== "string") continue;
    const path = issue.loc.slice(issue.loc[0] === "body" ? 1 : 0).filter((part: unknown) => typeof part === "string");
    const field = path.join("_")
      .replace(/^billing_address_/, "billing_")
      .replace(/^shipping_address_/, "shipping_");
    const addressField = path[0] === "address" ? path.slice(1).join("_") : "";
    const candidates = [path.join("_"), field, addressField === "name" ? "address_name" : addressField, path.length === 1 && path[0] === "seller_name" ? "name" : ""];
    const name = candidates.find((candidate) => names.includes(candidate));
    if (name) errors[name] = issue.msg;
  }
  return errors;
}

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
    if (field.type === "select" && field.valueType === "number") {
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
  icon,
  title,
  description,
  endpoint,
  listEndpoint = endpoint,
  listPageSize,
  fields,
  columns,
  initialForm,
  transformPayload,
  editable = false,
  recordToForm,
  recordActions,
}: MasterDataPageProps) {
  const authStatus = useAuthStatus();
  const requiresSellerProfile = fields.some((field) => field.name === "branch_id");
  const visibleFields = fields.filter((field) => field.name !== "branch_id");
  const [records, setRecords] = useState<MasterRecord[]>([]);
  const [form, setForm] = useState<Record<string, FormValue>>(initialForm);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [sellerProfileId, setSellerProfileId] = useState<number | null>(null);
  const [sellerProfileChecked, setSellerProfileChecked] = useState(!requiresSellerProfile);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const loadingRecords = useRef(false);

  const loadRecords = useCallback(async (offset = 0) => {
    if (loadingRecords.current) return;
    loadingRecords.current = true;
    setIsLoading(true);
    setLoadError(null);
    try {
      let path = listEndpoint;
      if (listPageSize) {
        const [base, query] = listEndpoint.split("?");
        const params = new URLSearchParams(query);
        params.set("limit", String(listPageSize)); params.set("offset", String(offset));
        path = `${base}?${params}`;
      }
      const result = await apiRequest<MasterRecord[]>(path);
      setRecords(current => offset ? [...current, ...result] : result);
      setHasMore(Boolean(listPageSize && result.length === listPageSize));
    } catch (requestError) {
      setLoadError(requestError instanceof ApiError ? requestError.message : "Unable to load records.");
    } finally {
      loadingRecords.current = false;
      setIsLoading(false);
    }
  }, [listEndpoint, listPageSize]);

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
        setProfileError(requestError instanceof ApiError ? requestError.message : "Unable to load Seller/GST profile.");
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
    setFieldErrors({});
    setMessage(null);
    if (requiresSellerProfile && !sellerProfileId) {
      setError(SELLER_PROFILE_REQUIRED_MESSAGE);
      return;
    }

    setIsSubmitting(true);
    try {
      const formForPayload = editingId === null && requiresSellerProfile && sellerProfileId
        ? { ...form, branch_id: String(sellerProfileId) }
        : form;
      const payload = transformPayload ? transformPayload(toPayload(fields, formForPayload)) : toPayload(fields, formForPayload);
      await apiRequest(endpoint + (editingId === null ? "" : `/${editingId}`), {
        method: editingId === null ? "POST" : "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const wasEditing = editingId !== null;
      setEditingId(null);
      setForm(requiresSellerProfile && sellerProfileId ? { ...initialForm, branch_id: String(sellerProfileId) } : initialForm);
      setMessage(wasEditing ? "Record updated successfully." : "Record saved successfully.");
      await loadRecords();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to save record.");
      if (requestError instanceof ApiError) setFieldErrors(fieldErrorsFromDetail(requestError.detail, visibleFields.map((field) => field.name)));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function updateRecord(recordId: number, updates: Record<string, unknown>, successMessage: string) {
    setError(null);
    setMessage(null);
    try {
      await apiRequest(`${endpoint}/${recordId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });
      setMessage(successMessage);
      await loadRecords();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to update record.");
    }
  }

  async function deleteRecord(recordId: number) {
    if (!window.confirm("Delete this supplier permanently? This cannot be undone.")) return;
    setError(null);
    setMessage(null);
    try {
      await apiRequest(`${endpoint}/${recordId}`, { method: "DELETE" });
      if (editingId === recordId) {
        setEditingId(null);
        setForm(requiresSellerProfile && sellerProfileId ? { ...initialForm, branch_id: String(sellerProfileId) } : initialForm);
      }
      setMessage("Supplier deleted permanently.");
      await loadRecords();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to delete record.");
    }
  }

  return (
    <AuthGateStatus status={authStatus}>
      <AppShell>
        <div className="workspace-page">
          <PageHeader icon={icon} eyebrow="Master records" title={title} description={description} />

          {requiresSellerProfile && sellerProfileChecked && !sellerProfileId && (
            <div className="ui-alert mt-6" role="status">
              {profileError ?? SELLER_PROFILE_REQUIRED_MESSAGE}{" "}
              <Link className="font-semibold text-peacock underline underline-offset-4" href="/branches">
                Open Seller/GST profile
              </Link>
            </div>
          )}

          <section className="mt-7 space-y-6">
            <form onSubmit={handleSubmit} className="ui-panel" aria-busy={isSubmitting}>
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-5">
                <div>
                  <h2 className="ui-section-title">{editingId === null ? "New record" : "Edit record"}</h2>
                  <p className="mt-1 text-sm text-slate">Enter details to add to your {title.toLowerCase()} register.</p>
                </div>
                <p className="text-xs text-slate">Fields marked <span className="font-bold text-peacock">*</span> are required</p>
              </div>
              <div className="mt-5 grid gap-x-5 gap-y-5 sm:grid-cols-2 xl:grid-cols-3">
                {visibleFields.map((field) => {
                  const value = form[field.name];
                  const fieldError = fieldErrors[field.name];
                  if (field.type === "checkbox") {
                    return (
                      <label key={field.name} className="flex items-center gap-3 self-end rounded-xl border border-line bg-warm px-4 py-3 text-sm font-medium text-ink">
                        <input
                          checked={Boolean(value)}
                          className="h-4 w-4 rounded border-line accent-peacock"
                          onChange={(event) => setForm((current) => ({ ...current, [field.name]: event.target.checked }))}
                          type="checkbox"
                        />
                        {field.label}
                      </label>
                    );
                  }
                  const inputClass = `ui-input mt-2 ${fieldError ? "border-peacock ring-1 ring-peacock" : ""}`;
                  return (
                    <div key={field.name} className={field.type === "textarea" || field.section ? "sm:col-span-2 xl:col-span-3" : "min-w-0"}>
                      {field.section && <h3 className="mb-4 border-b border-line pb-3 text-sm font-semibold text-peacock-deep">{field.section}</h3>}
                      <label className="ui-label" htmlFor={`master-${field.name}`}>
                        {field.label} {field.required && <span className="text-peacock" aria-hidden="true">*</span>}
                        {field.type === "textarea" ? (
                          <GrowingTextarea
                            id={`master-${field.name}`}
                            className={`${inputClass} min-h-24 resize-y`}
                            aria-invalid={Boolean(fieldError)}
                            aria-describedby={fieldError ? `error-${field.name}` : undefined}
                            onChange={(event) => setForm((current) => ({ ...current, [field.name]: event.target.value }))}
                            required={field.required}
                            value={String(value)}
                          />
                        ) : field.type === "select" ? (
                          <select
                            id={`master-${field.name}`}
                            className={inputClass}
                            aria-invalid={Boolean(fieldError)}
                            aria-describedby={fieldError ? `error-${field.name}` : undefined}
                            onChange={(event) => setForm((current) => ({ ...current, [field.name]: event.target.value }))}
                            required={field.required}
                            value={String(value)}
                          >
                            <option value="">{field.required ? "Choose an option" : "None"}</option>
                            {String(value) && !field.options?.some((option) => option.value === String(value)) && (
                              <option value={String(value)}>Existing value: {String(value)}</option>
                            )}
                            {(field.options ?? []).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                          </select>
                        ) : (
                          <input
                            id={`master-${field.name}`}
                            className={inputClass}
                            aria-invalid={Boolean(fieldError)}
                            aria-describedby={fieldError ? `error-${field.name}` : undefined}
                            onChange={(event) => setForm((current) => ({ ...current, [field.name]: event.target.value }))}
                            required={field.required}
                            type={field.type ?? "text"}
                            value={String(value)}
                          />
                        )}
                      </label>
                      {fieldError && <p id={`error-${field.name}`} className="mt-2 text-xs font-medium text-peacock-deep">{fieldError}</p>}
                    </div>
                  );
                })}
              </div>
              {error && <p className="ui-alert mt-5" role="alert">{error}</p>}
              {message && <p className="mt-5 rounded-xl border border-peacock/20 bg-warm-green px-4 py-3 text-sm font-medium text-peacock-deep" role="status">{message}</p>}
              <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5">
                <p className="text-xs text-slate">{requiresSellerProfile && !sellerProfileChecked ? "Checking Seller/GST profile…" : "Your saved details will be available when creating bills."}</p>
              <button
                className="ui-button-primary w-full sm:w-auto"
                disabled={isSubmitting || (requiresSellerProfile && (!sellerProfileChecked || !sellerProfileId))}
                type="submit"
              >
                {isSubmitting ? "Saving…" : requiresSellerProfile && !sellerProfileId ? "Set up Seller/GST profile first" : editingId === null ? "Save record" : "Update record"}
              </button>
              {editingId !== null && <button className="ui-button" type="button" onClick={() => { setEditingId(null); setFieldErrors({}); setForm(requiresSellerProfile && sellerProfileId ? { ...initialForm, branch_id: String(sellerProfileId) } : initialForm); }}>Cancel edit</button>}
              </div>
            </form>

            <article className="ui-panel min-w-0" aria-busy={isLoading}>
              <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                <div><h2 className="ui-section-title">{title} register</h2>
                <p className="mt-1 text-xs text-slate" role="status">{isLoading ? "Loading records…" : `${records.length} record${records.length === 1 ? "" : "s"} loaded`}</p></div>
                <button className="ui-button" type="button" disabled={isLoading} onClick={() => void loadRecords()}>{isLoading ? "Loading…" : "Refresh"}</button>
              </div>
              {loadError && <p className="ui-alert mb-4" role="alert">{loadError} Use Refresh to try again.</p>}
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-line text-left text-sm">
                  <thead className="bg-warm text-xs font-semibold uppercase tracking-wider text-slate">
                    <tr>
                      {columns.map((column) => (
                        <th key={column.key} scope="col" className="whitespace-nowrap px-4 py-3">{column.label}</th>
                      ))}
                      {editable && <th scope="col" className="whitespace-nowrap px-4 py-3">Actions</th>}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                      {records.map((record, index) => (
                        <tr key={typeof record.id === "number" ? record.id : index} className="transition-colors hover:bg-warm/70">
                        {columns.map((column) => (
                          <td key={column.key} className="min-w-28 max-w-md whitespace-pre-wrap break-words px-4 py-4 align-top text-ink">
                            {typeof readCell(record, column.key) === "boolean" ? <span className="ui-badge">{column.key === "is_active" ? readCell(record, column.key) ? "Active" : "Inactive" : formatCell(readCell(record, column.key))}</span> : formatCell(readCell(record, column.key))}
                          </td>
                          ))}
                          {editable && (
                            <td className="whitespace-nowrap px-4 py-4 align-top">
                              <div className="flex flex-wrap gap-2">
                                <button
                                  className="ui-button px-3 py-2 text-xs"
                                  type="button"
                                  onClick={() => {
                                    if (!recordToForm || typeof record.id !== "number") return;
                                    setEditingId(record.id);
                                    setForm(recordToForm(record));
                                    setError(null);
                                    setMessage(null);
                                    setFieldErrors({});
                                    window.scrollTo({ top: 0, behavior: "smooth" });
                                  }}
                                >
                                  Edit
                                </button>
                                {recordActions?.activeField && typeof record.id === "number" && typeof readCell(record, recordActions.activeField) === "boolean" && (
                                  <button
                                    className="ui-button px-3 py-2 text-xs"
                                    type="button"
                                    onClick={() => void updateRecord(record.id as number, { [recordActions.activeField as string]: !readCell(record, recordActions.activeField as string) }, readCell(record, recordActions.activeField as string) ? "Record deactivated." : "Record activated.")}
                                  >
                                    {readCell(record, recordActions.activeField) ? "Deactivate" : "Activate"}
                                  </button>
                                )}
                                {recordActions?.defaultField && typeof record.id === "number" && readCell(record, recordActions.activeField ?? "is_active") === true && (
                                  readCell(record, recordActions.defaultField) === true ? (
                                    <button
                                      className="ui-button px-3 py-2 text-xs"
                                      type="button"
                                      onClick={() => void updateRecord(record.id as number, { [recordActions.defaultField as string]: false }, "Default supplier cleared.")}
                                    >
                                      Clear default
                                    </button>
                                  ) : (
                                    <button
                                      className="ui-button px-3 py-2 text-xs"
                                      type="button"
                                      onClick={() => void updateRecord(record.id as number, { [recordActions.defaultField as string]: true }, "Default supplier updated.")}
                                    >
                                      Set default
                                    </button>
                                  )
                                )}
                                {recordActions?.allowDelete && typeof record.id === "number" && (
                                  <button className="ui-button border-red-200 px-3 py-2 text-xs text-red-700" type="button" onClick={() => void deleteRecord(record.id as number)}>
                                    Delete
                                  </button>
                                )}
                              </div>
                            </td>
                          )}
                        </tr>
                      ))}
                    {!isLoading && !loadError && records.length === 0 && (
                      <tr>
                        <td className="ui-empty py-12" colSpan={columns.length + (editable ? 1 : 0)}>
                          <p className="font-semibold text-ink">No records yet</p>
                          <p className="mt-2 text-sm text-slate">Add your first record using the form above.</p>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {listPageSize && hasMore && <button className="ui-button mt-5" type="button" disabled={isLoading} onClick={() => void loadRecords(records.length)}>Load more {title.toLowerCase()}</button>}
            </article>
          </section>
        </div>
      </AppShell>
    </AuthGateStatus>
  );
}
