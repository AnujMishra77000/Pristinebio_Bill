"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { getSessionState, isSessionReady, validateSession, SESSION_CHANGED_EVENT } from "@/app/lib/api";
import { AuthFlow } from "./AuthFlow";

export type AuthStatus = "checking" | "authenticated" | "unauthenticated";

export function useAuthStatus(): AuthStatus {
  const [status, setStatus] = useState<AuthStatus>("checking");

  useEffect(() => {
    let isMounted = true;

    function updateStatus() { if (isMounted) setStatus(isSessionReady() ? "authenticated" : "unauthenticated"); }
    window.addEventListener(SESSION_CHANGED_EVENT, updateStatus);
    void validateSession().then(updateStatus);
    return () => {
      isMounted = false;
      window.removeEventListener(SESSION_CHANGED_EVENT, updateStatus);
    };
  }, []);

  return status;
}

export function AuthGateStatus({ children, status }: { children: ReactNode; status: AuthStatus }) {
  const [hasAuthenticated, setHasAuthenticated] = useState(false);
  useEffect(() => { if (status === "authenticated") setHasAuthenticated(true); }, [status]);
  const state = getSessionState();
  if (!state.explicitlyLoggedOut && (status === "authenticated" || hasAuthenticated)) return <>{children}</>;
  if (status === "checking") {
    return <div className="flex min-h-screen items-center justify-center bg-warm px-5 text-center"><div className="ui-panel px-6 py-5"><p className="text-sm font-semibold text-ink">Checking secure session…</p></div></div>;
  }
  return <div className="flex min-h-screen items-center justify-center bg-warm px-5"><div className="ui-panel w-full max-w-md">{state.session && !state.reauthenticationRequired ? <AuthFlow initialUser={state.session.user} allowEntry={false} onComplete={() => {}} /> : <><p className="text-sm font-semibold text-ink">Sign in to continue</p>{state.validationError && <p className="mt-3 text-sm text-slate">{state.validationError}</p>}<Link href="/login" className="mt-3 inline-block text-sm font-semibold text-peacock hover:text-ink">Go to login →</Link></>}</div></div>;
}

export function useSessionState() {
  const [state, setState] = useState(getSessionState);
  useEffect(() => {
    const update = () => setState(getSessionState());
    update();
    window.addEventListener(SESSION_CHANGED_EVENT, update);
    return () => window.removeEventListener(SESSION_CHANGED_EVENT, update);
  }, []);
  return state;
}

export function AuthGate({ children }: { children: ReactNode }) {
  return <AuthGateStatus status={useAuthStatus()}>{children}</AuthGateStatus>;
}
