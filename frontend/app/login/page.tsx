"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, apiRequest, storeSession } from "@/app/lib/api";
import type { TokenResponse, User } from "@/app/lib/types";

type AuthMode = "login" | "register";

function isPasswordStrong(password: string): boolean {
  return (
    password.length === 6 &&
    /[a-z]/.test(password) &&
    /[A-Z]/.test(password) &&
    /\d/.test(password)
  );
}

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<AuthMode>("login");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [masterPassword, setMasterPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function switchMode(nextMode: AuthMode) {
    setMode(nextMode);
    setError(null);
    setSuccess(null);
    setPassword("");
    setConfirmPassword("");
    setMasterPassword("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      if (mode === "login") {
        const session = await apiRequest<TokenResponse>("/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });
        storeSession(session);
        router.push("/");
        return;
      }

      if (!isPasswordStrong(password)) {
        setError("Password must be exactly 6 characters and include uppercase, lowercase, and a number.");
        return;
      }
      if (password !== confirmPassword) {
        setError("Passwords do not match.");
        return;
      }

      await apiRequest<User>("/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          full_name: fullName,
          password,
          master_password: masterPassword,
        }),
      });
      setSuccess("Admin registration completed. You can sign in now.");
      setMode("login");
      setFullName("");
      setPassword("");
      setConfirmPassword("");
      setMasterPassword("");
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Unable to continue.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f7f8fb] px-5 text-ink">
      <form onSubmit={handleSubmit} className="w-full max-w-md rounded-[22px] border border-slate-200/80 bg-white p-6 shadow-panel">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-[14px] bg-ink text-sm font-bold text-white shadow-sm">PB</span>
          <div>
            <p className="text-lg font-bold tracking-tight text-ink">Pristine Bio Billing</p>
            <p className="mt-0.5 text-xs text-slate-400">Secure access for company billing operations.</p>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-2 rounded-2xl bg-slate-100 p-1">
          <button
            className={`rounded-xl px-3 py-2 text-sm font-semibold transition-colors ${mode === "login" ? "bg-white text-ink shadow-sm" : "text-slate-500 hover:text-ink"}`}
            onClick={() => switchMode("login")}
            type="button"
          >
            Sign in
          </button>
          <button
            className={`rounded-xl px-3 py-2 text-sm font-semibold transition-colors ${mode === "register" ? "bg-white text-ink shadow-sm" : "text-slate-500 hover:text-ink"}`}
            onClick={() => switchMode("register")}
            type="button"
          >
            Register
          </button>
        </div>

        {mode === "register" && (
          <label className="mt-6 block text-xs font-semibold text-slate-500">
            Full name
            <input
              autoComplete="name"
              className="mt-1.5 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-ink outline-none transition-colors focus:border-[#6f8fe8]"
              onChange={(event) => setFullName(event.target.value)}
              required
              type="text"
              value={fullName}
            />
          </label>
        )}

        <label className="mt-7 block text-xs font-semibold text-slate-500">
          Email
          <input
            autoComplete="email"
            className="mt-1.5 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-ink outline-none transition-colors focus:border-[#6f8fe8]"
            onChange={(event) => setEmail(event.target.value)}
            required
            type="email"
            value={email}
          />
        </label>

        <label className="mt-4 block text-xs font-semibold text-slate-500">
          Password
          <input
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            className="mt-1.5 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-ink outline-none transition-colors focus:border-[#6f8fe8]"
            onChange={(event) => setPassword(event.target.value)}
            required
            minLength={6}
            maxLength={6}
            type="password"
            value={password}
          />
        </label>

        {mode === "register" && (
          <>
            <p className="mt-2 text-xs leading-5 text-slate-400">
              Use exactly 6 characters with uppercase, lowercase, and a number.
            </p>
            <label className="mt-4 block text-xs font-semibold text-slate-500">
              Confirm password
              <input
                autoComplete="new-password"
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-ink outline-none transition-colors focus:border-[#6f8fe8]"
                onChange={(event) => setConfirmPassword(event.target.value)}
                required
                minLength={6}
                maxLength={6}
                type="password"
                value={confirmPassword}
              />
            </label>
            <label className="mt-4 block text-xs font-semibold text-slate-500">
              Master password
              <input
                autoComplete="off"
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-ink outline-none transition-colors focus:border-[#6f8fe8]"
                onChange={(event) => setMasterPassword(event.target.value)}
                required
                type="password"
                value={masterPassword}
              />
            </label>
            <p className="mt-2 text-xs leading-5 text-slate-400">
              Only people with the company master password can register as Admin. Staff accounts are created by Admin after login.
            </p>
          </>
        )}

        {error && <p className="mt-4 rounded-xl bg-[#fff0df] px-3.5 py-3 text-sm font-medium text-[#b46b22]">{error}</p>}
        {success && <p className="mt-4 rounded-xl bg-[#ecfdf3] px-3.5 py-3 text-sm font-medium text-[#287a4c]">{success}</p>}

        <button
          className="mt-6 w-full rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-[#243653] disabled:cursor-not-allowed disabled:opacity-60"
          disabled={isSubmitting}
          type="submit"
        >
          {isSubmitting ? "Please wait…" : mode === "login" ? "Sign in" : "Submit registration"}
        </button>
      </form>
    </main>
  );
}
