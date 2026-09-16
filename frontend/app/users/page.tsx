"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { AppShell } from "@/app/components/AppShell";
import { AuthGateStatus, useAuthStatus } from "@/app/components/AuthGate";
import { ApiError, apiRequest } from "@/app/lib/api";
import type { Branch as SellerProfile, User, UserRole } from "@/app/lib/types";

type CreatableRole = Extract<UserRole, "manager" | "staff">;

const initialForm = {
  email: "",
  full_name: "",
  password: "",
  role: "staff" as CreatableRole,
  branch_ids: [] as number[],
  is_active: true,
};

function formatSellerProfiles(user: User) {
  return user.branch_ids.length ? user.branch_ids.join(", ") : "All / not assigned";
}

export default function UsersPage() {
  const authStatus = useAuthStatus();
  const [users, setUsers] = useState<User[]>([]);
  const [sellerProfiles, setSellerProfiles] = useState<SellerProfile[]>([]);
  const [form, setForm] = useState(initialForm);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [loadedUsers, loadedSellerProfiles] = await Promise.all([
        apiRequest<User[]>("/users"),
        apiRequest<SellerProfile[]>("/branches"),
      ]);
      setUsers(loadedUsers);
      setSellerProfiles(loadedSellerProfiles);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to load users.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authStatus !== "authenticated") return;
    void loadData();
  }, [authStatus, loadData]);

  function toggleBranch(branchId: number) {
    setForm((current) => ({
      ...current,
      branch_ids: current.branch_ids.includes(branchId)
        ? current.branch_ids.filter((id) => id !== branchId)
        : [...current.branch_ids, branchId],
    }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      await apiRequest("/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      setForm(initialForm);
      await loadData();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to create user.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthGateStatus status={authStatus}>
      <AppShell>
        <div className="mx-auto max-w-[1440px] px-5 py-8 sm:px-8 lg:px-10 lg:py-10">
          <section>
            <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-[#6f8fe8]">Access control</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-ink sm:text-[40px]">Users</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500 sm:text-[15px]">
              Admins register with the master password. Staff and Manager accounts are then created here and can be assigned to the active Seller/GST profile.
            </p>
          </section>

          <section className="mt-8 grid gap-6 xl:grid-cols-[0.9fr_1.4fr]">
            <form onSubmit={handleSubmit} className="rounded-[22px] border border-slate-200/80 bg-white p-5 shadow-panel sm:p-6">
              <h2 className="text-lg font-semibold tracking-tight text-ink">Create Staff / Manager</h2>
              <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
                <label className="text-xs font-semibold text-slate-500">
                  Full name
                  <input className="mt-1.5 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-ink outline-none transition-colors focus:border-[#6f8fe8]" onChange={(event) => setForm((current) => ({ ...current, full_name: event.target.value }))} required value={form.full_name} />
                </label>
                <label className="text-xs font-semibold text-slate-500">
                  Email
                  <input className="mt-1.5 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-ink outline-none transition-colors focus:border-[#6f8fe8]" onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))} required type="email" value={form.email} />
                </label>
                <label className="text-xs font-semibold text-slate-500">
                  Password
                  <input className="mt-1.5 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-ink outline-none transition-colors focus:border-[#6f8fe8]" minLength={6} maxLength={6} onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))} required type="password" value={form.password} />
                </label>
                <label className="text-xs font-semibold text-slate-500">
                  Role
                  <select className="mt-1.5 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-ink outline-none transition-colors focus:border-[#6f8fe8]" onChange={(event) => setForm((current) => ({ ...current, role: event.target.value as CreatableRole }))} value={form.role}>
                    <option value="staff">Staff</option>
                    <option value="manager">Manager</option>
                  </select>
                </label>
                <label className="flex items-center gap-3 rounded-xl border border-slate-200 px-3.5 py-3 text-sm font-medium text-slate-600">
                  <input checked={form.is_active} className="h-4 w-4 rounded border-slate-300" onChange={(event) => setForm((current) => ({ ...current, is_active: event.target.checked }))} type="checkbox" />
                  Active
                </label>
              </div>

              <div className="mt-5">
                <p className="text-xs font-semibold text-slate-500">Allowed Seller/GST profiles</p>
                <div className="mt-2 grid gap-2">
                  {sellerProfiles.map((profile) => (
                    <label key={profile.id} className="flex items-center gap-3 rounded-xl border border-slate-200 px-3.5 py-3 text-sm font-medium text-slate-600">
                      <input checked={form.branch_ids.includes(profile.id)} className="h-4 w-4 rounded border-slate-300" onChange={() => toggleBranch(profile.id)} type="checkbox" />
                      <span>{profile.name} · {profile.gstin}</span>
                    </label>
                  ))}
                  {!isLoading && sellerProfiles.length === 0 && <p className="rounded-xl bg-slate-50 px-3.5 py-3 text-sm text-slate-400">Create the Seller/GST profile before assigning users.</p>}
                </div>
              </div>

              {error && <p className="mt-4 rounded-xl bg-[#fff0df] px-3.5 py-3 text-sm font-medium text-[#b46b22]">{error}</p>}
              <button className="mt-6 w-full rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-[#243653] disabled:cursor-not-allowed disabled:opacity-60" disabled={isSubmitting} type="submit">
                {isSubmitting ? "Creating…" : "Create user"}
              </button>
            </form>

            <article className="overflow-hidden rounded-[22px] border border-slate-200/80 bg-white shadow-panel">
              <div className="border-b border-slate-100 px-5 py-4 sm:px-6">
                <h2 className="text-lg font-semibold tracking-tight text-ink">Users</h2>
                <p className="mt-1 text-xs text-slate-400">{isLoading ? "Loading…" : `${users.length} user${users.length === 1 ? "" : "s"}`}</p>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-100 text-left text-sm">
                  <thead className="bg-slate-50 text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
                    <tr>
                      <th className="px-5 py-3 sm:px-6">Name</th>
                      <th className="px-5 py-3 sm:px-6">Email</th>
                      <th className="px-5 py-3 sm:px-6">Role</th>
                      <th className="px-5 py-3 sm:px-6">Active</th>
                      <th className="px-5 py-3 sm:px-6">Seller profile IDs</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {users.map((user) => (
                      <tr key={user.id}>
                        <td className="px-5 py-4 font-semibold text-ink sm:px-6">{user.full_name}</td>
                        <td className="px-5 py-4 text-slate-600 sm:px-6">{user.email}</td>
                        <td className="px-5 py-4 capitalize text-slate-600 sm:px-6">{user.role}</td>
                        <td className="px-5 py-4 text-slate-600 sm:px-6">{user.is_active ? "Yes" : "No"}</td>
                        <td className="px-5 py-4 text-slate-600 sm:px-6">{formatSellerProfiles(user)}</td>
                      </tr>
                    ))}
                    {!isLoading && users.length === 0 && (
                      <tr>
                        <td className="px-5 py-10 text-center text-sm text-slate-400 sm:px-6" colSpan={5}>No users yet.</td>
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
