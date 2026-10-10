"use client";

import { useEffect, useRef, useState } from "react";
import { apiRequest } from "./api";

type SavedBill = { id: number; document_type: string; version: number };
type Options<T extends SavedBill> = {
  collection: "/invoices" | "/purchase-orders";
  parameter: "invoice" | "order";
  documentType: string;
  authenticated: boolean;
  ready: boolean;
  document: T | null;
  busy: boolean;
  unsaved: boolean;
  hasWork: boolean;
  hydrate: (bill: T) => void;
  load?: (id: number, signal: AbortSignal) => Promise<T>;
};

/** Open a saved transaction, never silently replace work or fall back to POST. */
export function useSavedBillLoader<T extends SavedBill>(options: Options<T>) {
  const latest = useRef(options);
  latest.current = options;
  const [resolved, setResolved] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const force = useRef(false);

  useEffect(() => {
    if (!options.authenticated || !options.ready) return;
    const current = latest.current;
    const requested = new URLSearchParams(window.location.search).get(current.parameter);
    const forced = force.current;
    force.current = false;
    const raw = forced && current.document ? String(current.document.id) : requested;
    if (raw === null) { setResolved(true); setError(""); return; }
    const id = Number(raw);
    if (!/^[1-9]\d*$/.test(raw) || !Number.isSafeInteger(id)) {
      setResolved(false); setError("Invalid saved bill ID. Open the bill from its register."); return;
    }
    if (!forced && current.document?.id === id) { setResolved(true); setError(""); return; }
    if (current.busy) { setResolved(false); setError("A save is still running. Wait, then retry loading this bill."); return; }
    if (current.hasWork && current.unsaved && !window.confirm("Replace your current unsaved fields with the saved bill? Cancel keeps your current work.")) {
      // The URL must describe the work still visible, not the rejected target.
      window.history.replaceState(null, "", window.location.pathname);
      setResolved(true); setError(""); return;
    }
    let active = true;
    const controller = new AbortController();
    setResolved(false); setError("");
    void (current.load ? current.load(id, controller.signal) : apiRequest<T>(`${current.collection}/${id}`, { signal: controller.signal, cache: "no-store" }))
      .then((bill) => {
        if (!active) return;
        if (bill.id !== id || bill.document_type !== current.documentType) throw new Error("This bill belongs to a different billing section. Open it from the correct register.");
        if (!Number.isSafeInteger(bill.version) || bill.version <= 0) throw new Error("The saved bill has no valid revision. Reload it before editing.");
        current.hydrate(bill);
        setResolved(true);
      }).catch((failure) => {
        if (active) { setResolved(false); setError(failure instanceof Error ? failure.message : "Unable to load the saved bill. Your current work is retained."); }
      });
    return () => { active = false; controller.abort(); };
  }, [options.authenticated, options.ready, attempt]);

  return {
    blocked: !resolved || Boolean(error), error,
    retry: () => setAttempt((value) => value + 1),
    reloadLatest: () => { force.current = true; setAttempt((value) => value + 1); },
  };
}
