"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { apiRequest, getStoredSession, SESSION_CHANGED_EVENT } from "@/app/lib/api";

export type AuthStatus = "checking" | "authenticated" | "unauthenticated";

export function useAuthStatus(): AuthStatus {
  const [status, setStatus] = useState<AuthStatus>("checking");

  useEffect(() => {
    let isMounted = true;

    function validateSession() {
      const session = getStoredSession();
      if (!session?.access_token) {
        if (isMounted) setStatus("unauthenticated");
        return;
      }

      if (isMounted) setStatus("authenticated");
      void apiRequest("/auth/me").catch(() => {
        // Keep the session until the user explicitly logs out.
      });
    }

    void validateSession();
    window.addEventListener(SESSION_CHANGED_EVENT, validateSession);
    window.addEventListener("storage", validateSession);
    return () => {
      isMounted = false;
      window.removeEventListener(SESSION_CHANGED_EVENT, validateSession);
      window.removeEventListener("storage", validateSession);
    };
  }, []);

  return status;
}

export function AuthGateStatus({ children, status }: { children: ReactNode; status: AuthStatus }) {
  if (status === "authenticated") return <>{children}</>;
  if (status === "checking") {
    return <div className="flex min-h-screen items-center justify-center bg-[#f7f8fb] px-5 text-center"><div className="rounded-2xl border border-slate-200/80 bg-white px-6 py-5 shadow-panel"><p className="text-sm font-semibold text-ink">Checking secure session…</p></div></div>;
  }
  return <div className="flex min-h-screen items-center justify-center bg-[#f7f8fb] px-5 text-center"><div className="rounded-2xl border border-slate-200/80 bg-white px-6 py-5 shadow-panel"><p className="text-sm font-semibold text-ink">Sign in to continue</p><Link href="/login" className="mt-3 inline-block text-sm font-semibold text-[#6276bd] hover:text-ink">Go to login →</Link></div></div>;
}

export function AuthGate({ children }: { children: ReactNode }) {
  return <AuthGateStatus status={useAuthStatus()}>{children}</AuthGateStatus>;
}
