"use client";

import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/app/components/AppShell";
import { AuthGateStatus, useAuthStatus } from "@/app/components/AuthGate";
import { PageHeader } from "@/app/components/PageHeader";
import { PasswordChangeForm, SecurityError, SecuritySection, errorMessage, securityButton } from "@/app/components/SecurityForms";
import { apiRequest, logoutSession, revokeSession } from "@/app/lib/api";
import type { AuthSession } from "@/app/lib/types";

export default function SecurityPage() {
  const status = useAuthStatus();
  const [sessions, setSessions] = useState<AuthSession[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(async () => {
    try { setSessions(await apiRequest("/auth/sessions")); }
    catch (requestError) { setError(errorMessage(requestError)); }
  }, []);
  useEffect(() => { if (status === "authenticated") void load(); }, [status, load]);
  async function revoke(item: AuthSession) {
    setBusy(true); setError(null); setMessage(null);
    try {
      await revokeSession(item.id, item.current);
      if (!item.current) { setMessage("Session revoked."); await load(); }
    } catch (requestError) { setError(errorMessage(requestError)); } finally { setBusy(false); }
  }
  async function logoutAll() {
    setBusy(true); setError(null);
    try { await logoutSession(true); } catch (requestError) { setError(errorMessage(requestError)); } finally { setBusy(false); }
  }
  return <AuthGateStatus status={status}><AppShell><div className="workspace-page"><PageHeader icon="security" eyebrow="Account control" title="Security" description="Manage your password and active sessions." /><SecurityError message={error} />{message && <p role="status">{message}</p>}<div className="grid gap-6 md:grid-cols-2"><SecuritySection title="Account password"><PasswordChangeForm onDone={() => void load()} /></SecuritySection><SecuritySection title="Active sessions"><ul className="space-y-4">{sessions.map(item => <li key={item.id} className="space-y-2 rounded-xl border border-slate-200 p-3"><p className="break-all font-mono text-xs">{item.id}</p><p className="text-sm font-semibold">{item.current ? "This session" : "Other session"}</p><p className="text-xs text-slate-500">Created {item.created_at}<br />Last used {item.last_seen_at}<br />Expires {item.expires_at}</p><button type="button" className={securityButton} disabled={busy} aria-label={`Revoke session ${item.id}`} onClick={() => void revoke(item)}>{item.current ? "Log out this session" : "Revoke session"}</button></li>)}</ul><button type="button" className={securityButton} disabled={busy} onClick={() => void logoutAll()}>Log out all sessions</button></SecuritySection></div></div></AppShell></AuthGateStatus>;
}
