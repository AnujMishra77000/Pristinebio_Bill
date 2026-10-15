"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ApiError, apiRequest, getStoredSession } from "./api";

type SavedBill = { id: number; document_type: string; version: number; correction?: unknown };
type Recovery = { id: number; currentVersion: number; correctionVersion: number };
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
  load?: (id: number, signal: AbortSignal, path: string) => Promise<T>;
};

/** Open a saved transaction, never silently replace work or fall back to POST. */
export function useSavedBillLoader<T extends SavedBill>(options: Options<T>) {
  const search = useSearchParams().toString();
  const latest = useRef(options);
  latest.current = options;
  const [resolved, setResolved] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const force = useRef(false);
  const [recovery, setRecovery] = useState<Recovery | null>(null);
  const [restartReason, setRestartReason] = useState("");
  const [restarting, setRestarting] = useState(false);
  const restartingRef = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const reviewer = () => ["admin", "manager"].includes(getStoredSession()?.user.role ?? "");

  const hydrate = useCallback((bill: T, current: Options<T>, id: number) => {
    if (bill.id !== id || bill.document_type !== current.documentType) throw new Error("This bill belongs to a different billing section. Open it from the correct register.");
    if (!Number.isSafeInteger(bill.version) || bill.version <= 0) throw new Error("The saved bill has no valid revision. Reload it before editing.");
    current.hydrate(bill); setResolved(true); setError(""); setRecovery(null);
  }, []);
  function recordFailure(failure: unknown, id: number, correction: boolean) {
    setResolved(false); setError(failure instanceof Error ? failure.message : "Unable to load the saved bill. Your current work is retained.");
    const detail = failure instanceof ApiError ? failure.detail as Record<string, unknown> | null : null;
    if (correction && failure instanceof ApiError && failure.status === 409 && detail?.correction_base_changed === true &&
      Number.isSafeInteger(detail.current_version) && Number(detail.current_version) > 0 && Number.isSafeInteger(detail.correction_version) && Number(detail.correction_version) > 0) {
      setRecovery({ id, currentVersion: Number(detail.current_version), correctionVersion: Number(detail.correction_version) });
    } else setRecovery(null);
  }

  useEffect(() => {
    if (!options.authenticated || !options.ready) return;
    const current = latest.current;
    const query = new URLSearchParams(search);
    const requested = query.get(current.parameter);
    const forced = force.current;
    const correction = forced && current.document ? Boolean(current.document.correction) : query.get("correction") === "1";
    force.current = false;
    const raw = forced && current.document ? String(current.document.id) : requested;
    if (raw === null) { setResolved(true); setError(""); return; }
    const id = Number(raw);
    if (!/^[1-9]\d*$/.test(raw) || !Number.isSafeInteger(id)) {
      setResolved(false); setError("Invalid saved bill ID. Open the bill from its register."); return;
    }
    if (!forced && current.document?.id === id && Boolean(current.document.correction) === correction) { setResolved(true); setError(""); return; }
    if (current.busy) { force.current = forced; setResolved(false); setError("A save is still running. Wait, then retry loading this bill."); return; }
    if (current.hasWork && current.unsaved && !window.confirm("Replace your current unsaved fields with the saved bill? Cancel keeps your current work.")) {
      // The URL must describe the work still visible, not the rejected target.
      const retained = current.document;
      window.history.replaceState(null, "", `${window.location.pathname}${retained ? `?${current.parameter}=${retained.id}${retained.correction ? "&correction=1" : ""}` : ""}`);
      setResolved(true); setError(""); return;
    }
    let active = true;
    const controller = new AbortController();
    setResolved(false); setError(""); setRecovery(null);
    const path = `${current.collection}/${id}${correction ? "/correction?edit=1" : ""}`;
    void (current.load ? current.load(id, controller.signal, path) : apiRequest<T>(path, { signal: controller.signal, cache: "no-store" }))
      .then((bill) => {
        if (!active) return;
        hydrate(bill, current, id);
      }).catch((failure) => {
        if (active) recordFailure(failure, id, correction);
      });
    return () => { active = false; controller.abort(); };
  }, [options.authenticated, options.ready, options.busy, attempt, hydrate, search]);

  async function restart() {
    if (!recovery || !latest.current.authenticated || !reviewer()) { setError("Ask Manager/Admin to restart this stale correction."); return; }
    if (restartingRef.current || latest.current.busy) return;
    if (!restartReason.trim()) { setError("Enter a restart reason before restarting this correction."); return; }
    if (!window.confirm("Discard the old staged correction edits and restart from the current confirmed bill? The old working snapshot will remain in the audit history.")) return;
    const current = latest.current;
    restartingRef.current = true; setRestarting(true);
    try {
      const bill = await apiRequest<T>(`${current.collection}/${recovery.id}/correction/restart`, { method: "POST", body: JSON.stringify({ expected_version: recovery.currentVersion, correction_version: recovery.correctionVersion, reason: restartReason.trim() }) });
      if (mounted.current && latest.current.authenticated) { hydrate(bill, current, recovery.id); setRestartReason(""); force.current = true; setAttempt(value => value + 1); }
    } catch (failure) { if (mounted.current) recordFailure(failure, recovery.id, true); }
    finally { restartingRef.current = false; if (mounted.current) setRestarting(false); }
  }

  return {
    blocked: !resolved || Boolean(error), error,
    recovery, canRestart: Boolean(recovery && reviewer()), restartReason, setRestartReason, restarting, restart,
    retry: () => setAttempt((value) => value + 1),
    reloadLatest: () => { force.current = true; setAttempt((value) => value + 1); },
  };
}
