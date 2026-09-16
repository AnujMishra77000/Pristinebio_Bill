"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/app/components/AppShell";
import { AuthGateStatus, useAuthStatus } from "@/app/components/AuthGate";
import { ApiError, apiRequest } from "@/app/lib/api";
import type { User } from "@/app/lib/types";

export default function SettingsPage() {
  const authStatus = useAuthStatus();
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authStatus !== "authenticated") return;
    async function loadUser() {
      try {
        setUser(await apiRequest<User>("/auth/me"));
      } catch (requestError) {
        setError(requestError instanceof ApiError ? requestError.message : "Unable to load current user.");
      }
    }
    void loadUser();
  }, [authStatus]);

  return (
    <AuthGateStatus status={authStatus}>
      <AppShell>
        <div className="mx-auto max-w-[1440px] px-5 py-8 sm:px-8 lg:px-10 lg:py-10">
          <section>
            <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-[#6f8fe8]">Settings</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-ink sm:text-[40px]">Current user</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500 sm:text-[15px]">
              Review the signed-in user context returned by the Phase 1B authentication API.
            </p>
          </section>

          <section className="mt-8 max-w-2xl rounded-[22px] border border-slate-200/80 bg-white p-5 shadow-panel sm:p-6">
            {error && <p className="rounded-xl bg-[#fff0df] px-3.5 py-3 text-sm font-medium text-[#b46b22]">{error}</p>}
            {!error && !user && <p className="text-sm text-slate-500">Loading current user…</p>}
            {user && (
              <dl className="grid gap-4 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">Email</dt>
                  <dd className="mt-1 font-semibold text-ink">{user.email}</dd>
                </div>
                <div>
                  <dt className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">Full name</dt>
                  <dd className="mt-1 font-semibold text-ink">{user.full_name}</dd>
                </div>
                <div>
                  <dt className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">Role</dt>
                  <dd className="mt-1 font-semibold capitalize text-ink">{user.role}</dd>
                </div>
                <div>
                  <dt className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">Seller profile IDs</dt>
                  <dd className="mt-1 font-semibold text-ink">{user.branch_ids.length ? user.branch_ids.join(", ") : "All profiles / not assigned"}</dd>
                </div>
              </dl>
            )}
          </section>
        </div>
      </AppShell>
    </AuthGateStatus>
  );
}
