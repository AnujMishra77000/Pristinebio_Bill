"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { apiRequest } from "@/app/lib/api";
import { normalizePassphrase } from "@/app/lib/auth";
import type { SessionResponse, User } from "@/app/lib/types";

export const securityButton = "ui-button-primary";
const inputClass = "ui-input mt-2 w-full min-w-0";
export const securityCard = "ui-panel min-w-0 space-y-5";
export function errorMessage(error: unknown): string { return error instanceof Error ? error.message : "Unable to complete this request. Try again."; }
export function SecurityError({ message }: { message: string | null }) { return message ? <p role="alert" className="ui-alert break-words">{message}</p> : null; }
export function SecurityField({ label, value, onChange, type = "text", autoComplete = "off", required = true }: { label: string; value: string; onChange: (value: string) => void; type?: string; autoComplete?: string; required?: boolean }) {
  return <label className="ui-label block min-w-0">{label}<input autoComplete={autoComplete} className={inputClass} onChange={event => onChange(event.target.value)} required={required} type={type} value={value} /></label>;
}
export function SecuritySection({ title, children }: { title: string; children: ReactNode }) { return <section className={securityCard}><h2 className="ui-section-title border-b border-line pb-4">{title}</h2>{children}</section>; }

export function PasswordChangeForm({ onDone, upgrade = false }: { onDone: (user: User) => void; upgrade?: boolean }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(null); setSuccess(false); setBusy(true);
    try {
      const normalized = normalizePassphrase(password);
      if (normalized !== confirmation.normalize("NFC")) throw new Error("Passphrases do not match.");
      const result = await apiRequest<SessionResponse>("/auth/password", { method: "POST", body: JSON.stringify({ current_password: currentPassword, new_password: normalized }) });
      setCurrentPassword(""); setPassword(""); setConfirmation(""); setSuccess(true); onDone(result.user);
    } catch (requestError) { setError(errorMessage(requestError)); } finally { setBusy(false); }
  }
  return (
    <form className="space-y-5" onSubmit={submit} noValidate aria-busy={busy}>
      <div><h2 className="text-lg font-semibold text-ink">{upgrade ? "Upgrade your password" : "Change password"}</h2><p className="mt-2 text-sm leading-6 text-slate">Use 6–10 characters, including spaces or Unicode. Changing your password revokes your previous sessions.</p></div>
      <SecurityField label="Current password" type="password" autoComplete="current-password" value={currentPassword} onChange={setCurrentPassword} />
      <SecurityField label="New passphrase" type="password" autoComplete="new-password" value={password} onChange={setPassword} />
      <SecurityField label="Confirm passphrase" type="password" autoComplete="new-password" value={confirmation} onChange={setConfirmation} />
      <SecurityError message={error} />
      {success && <p role="status" className="rounded-xl border border-line bg-warm-green p-4 text-sm text-peacock-deep">Password changed. Previous sessions revoked.</p>}
      <button type="submit" className={securityButton} disabled={busy}>{busy ? "Changing…" : "Change password"}</button>
    </form>
  );
}
