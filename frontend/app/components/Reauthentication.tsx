"use client";

import { useEffect, useRef } from "react";
import { authStep } from "@/app/lib/auth";
import { AuthFlow } from "./AuthFlow";
import { useAuthStatus, useSessionState } from "./AuthGate";

export function Reauthentication() {
  const status = useAuthStatus();
  const state = useSessionState();
  const dialog = useRef<HTMLDialogElement>(null);
  const open = status !== "checking" && status !== "authenticated" && !state.explicitlyLoggedOut && state.reauthenticationRequired;
  useEffect(() => {
    const element = dialog.current;
    if (open && element && !element.open) element.showModal();
    else if (element?.open) element.close();
  }, [open]);
  const user = state.session?.user ?? null;
  return open ? <dialog ref={dialog} onCancel={event => event.preventDefault()} aria-label="Restore secure access" className="w-[calc(100%_-_2rem)] max-w-md space-y-5 rounded-2xl border border-slate-200 p-6 text-ink shadow-xl backdrop:bg-slate-950/50"><h1 className="text-xl font-semibold">Restore secure access</h1><p className="text-sm text-slate-500">Your work is still here. Sign in and complete security checks to continue.</p><AuthFlow allowEntry={false} initialUser={!state.reauthenticationRequired && authStep(user) !== "ready" ? user : null} onComplete={() => {}} /></dialog> : null;
}
