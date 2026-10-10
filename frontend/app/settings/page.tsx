"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/app/components/AppShell";
import { PageHeader } from "@/app/components/PageHeader";
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
        <div className="workspace-page">
          <PageHeader icon="settings" eyebrow="Settings" title="Current user" description="Review your signed-in account and assigned seller profile access." />

          <section className="ui-panel mt-6 max-w-2xl">
            {error && <p className="ui-alert border-red-200 bg-red-50 text-red-800" role="alert">{error}</p>}
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
