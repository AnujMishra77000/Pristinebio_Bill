"use client";

import { useEffect, useState, type FormEvent } from "react";
import { apiRequest } from "@/app/lib/api";
import { authStep, normalizePassphrase } from "@/app/lib/auth";
import type { SessionResponse, User } from "@/app/lib/types";
import { PasswordChangeForm, SecurityError, SecurityField, errorMessage, securityButton } from "./SecurityForms";

type AuthMode = "login" | "register" | "invite";

type AuthFlowProps = {
  onComplete: () => void;
  initialUser?: User | null;
  allowEntry?: boolean;
  initialMode?: AuthMode;
};

export function AuthFlow({ onComplete, initialUser = null, allowEntry = true, initialMode = "login" }: AuthFlowProps) {
  const [user, setUser] = useState<User | null>(initialUser);
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [invitation, setInvitation] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const step = authStep(user);

  useEffect(() => {
    if (initialUser && authStep(initialUser) !== "ready") setUser(initialUser);
  }, [initialUser]);

  useEffect(() => {
    if (!allowEntry) return;
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const token = fragment.get("invite")?.trim();
    if (token) { setInvitation(token); setMode("invite"); }
    if (window.location.hash) window.history.replaceState(null, "", window.location.pathname + window.location.search);
  }, [allowEntry, initialMode]);

  function authenticated(next: User) {
    setUser(next); setPassword(""); setConfirmation("");
    if (authStep(next) === "ready") onComplete();
  }
  function switchMode(next: "login" | "register") { setMode(next); setError(null); setPassword(""); setConfirmation(""); }
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      let path = "/auth/login";
      let payload: Record<string, string> = { email, password };
      if (mode === "register" || mode === "invite") {
        const normalized = normalizePassphrase(password);
        if (normalized !== confirmation.normalize("NFC")) throw new Error("Passphrases do not match.");
        if (!name.trim()) throw new Error("Full name is required.");
        payload = { full_name: name, password: normalized };
        if (mode === "register") { path = "/auth/register"; payload.email = email; }
        else { path = "/auth/invitations/accept"; if (!invitation) throw new Error("Invitation token is missing. Open the invitation link again."); payload.token = invitation; }
      }
      const result = await apiRequest<SessionResponse>(path, { method: "POST", body: JSON.stringify(payload) });
      setInvitation(null); authenticated(result.user);
    } catch (requestError) { setError(errorMessage(requestError)); } finally { setBusy(false); }
  }
  if (step === "password") return <PasswordChangeForm upgrade onDone={authenticated} />;
  if (step === "ready") return <p role="status">Secure access restored.</p>;
  return <div className="space-y-5">
    <h2 className="text-lg font-semibold">{mode === "invite" ? "Accept invitation" : mode === "register" ? "Register as Admin" : "Sign in"}</h2>
    {allowEntry && mode !== "invite" && <div className="flex flex-wrap gap-x-5 gap-y-2 border-b border-line pb-4">
      <button type="button" onClick={() => switchMode("login")} className={mode === "login" ? "text-sm font-semibold text-peacock" : "text-sm font-semibold text-slate hover:text-ink"}>Sign in</button>
      <button type="button" onClick={() => switchMode("register")} className={mode === "register" ? "text-sm font-semibold text-peacock" : "text-sm font-semibold text-slate hover:text-ink"}>Register as Admin</button>
    </div>}
    {mode === "login" && <p className="text-xs leading-5 text-slate">Use your account email and passphrase. Admin, Manager and Staff accounts use the same secure sign-in.</p>}
    {mode === "register" && <p className="text-xs leading-5 text-slate">Create an active Admin account. Multiple Admin registrations are currently allowed.</p>}
    <form onSubmit={submit} className="space-y-4" noValidate>
      {mode !== "login" && <SecurityField label="Full name" value={name} onChange={setName} autoComplete="name" />}
      {mode !== "invite" && <SecurityField label="Email" type="email" value={email} onChange={setEmail} autoComplete="email" />}
      <SecurityField label={mode === "login" ? "Password" : "New passphrase"} value={password} onChange={setPassword} type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} />
      {mode !== "login" && <><p className="text-xs leading-5 text-slate">Use 6–10 characters. Spaces and Unicode are allowed.</p><SecurityField label="Confirm passphrase" value={confirmation} onChange={setConfirmation} type="password" autoComplete="new-password" /></>}
      {mode === "invite" && <p className="text-xs leading-5 text-slate">Your Admin provided this invitation link for manual delivery.</p>}
      <SecurityError message={error} />
      <button type="submit" disabled={busy} className={`${securityButton} w-full`}>{busy ? "Please wait…" : mode === "register" ? "Create Admin account" : mode === "invite" ? "Accept invitation" : "Sign in"}</button>
    </form>
  </div>;
}
