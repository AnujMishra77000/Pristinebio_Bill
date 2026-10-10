"use client";

import { useCallback, useMemo, useRef, useState, useSyncExternalStore, type Dispatch, type SetStateAction } from "react";
import { getSessionState, SESSION_CHANGED_EVENT } from "./api";

export type InvoiceKind = "sales" | "reagent" | "purchase" | "reagent-purchase";
export const INVOICE_ENTRY_INVALIDATED_EVENT = "pristine-bio-billing.invoice-entry-invalidated";
const entries = new Map<InvoiceKind, InvoiceEntrySession>();
let ownerId: number | null = null;
let listening = false;
let deletionChannel: BroadcastChannel | null = null;

/** Same-tab memory only: no browser storage, tokens, PDF blobs or server-global data. */
export class InvoiceEntrySession {
  active = true;
  private values = new Map<string, unknown>();
  private listeners = new Set<() => void>();
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  has(key: string) { return this.active && this.values.has(key); }
  read<T>(key: string, initial: T): T {
    if (!this.active) return initial;
    if (!this.values.has(key)) this.values.set(key, initial);
    return this.values.get(key) as T;
  }
  write<T>(key: string, value: T) {
    if (!this.active || (this.values.has(key) && Object.is(this.values.get(key), value))) return;
    this.values.set(key, value);
    this.listeners.forEach((listener) => listener());
  }
  ref<T>(key: string, initial: T): { current: T } {
    const read = () => this.read(key, initial);
    const write = (value: T) => this.write(key, value);
    return {
      get current() { return read(); },
      set current(value: T) { write(value); },
    };
  }
  dispose() {
    this.active = false;
    this.values.clear();
    this.listeners.forEach((listener) => listener());
    this.listeners.clear();
  }
}

function clearEntries() {
  entries.forEach((entry) => entry.dispose());
  entries.clear(); ownerId = null;
}
export function getInvoiceEntrySession(userId: number, kind: InvoiceKind) {
  if (typeof window === "undefined") throw new Error("Invoice entry sessions are browser-only.");
  listenForInvalidation();
  if (ownerId !== userId) { clearEntries(); ownerId = userId; }
  let entry = entries.get(kind);
  if (entry?.read("submission.completed", false) && !entry.read("submission.busy", false)) {
    entry.dispose(); entries.delete(kind); entry = undefined;
  }
  if (!entry) { entry = new InvoiceEntrySession(); entries.set(kind, entry); }
  return entry;
}

function invalidateMatchingInvoice(id: number, purchaseOrder = false) {
  entries.forEach((entry, kind) => {
    if ((kind === "purchase" || kind === "reagent-purchase") !== purchaseOrder) return;
    if (entry.read<{ id: number } | null>("submission.document", null)?.id !== id) return;
    entry.dispose(); entries.delete(kind);
    if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(INVOICE_ENTRY_INVALIDATED_EVENT, { detail: { kind } }));
  });
}

function listenForInvalidation() {
  if (typeof window === "undefined") return;
  if (!listening) {
    // Kept for the tab lifetime, so logout clears work even with no entry mounted.
    window.addEventListener(SESSION_CHANGED_EVENT, () => {
      const { session, explicitlyLoggedOut } = getSessionState();
      if (explicitlyLoggedOut || (session && (session.user.id !== ownerId || !session.user.is_active))) clearEntries();
    });
    if (typeof BroadcastChannel !== "undefined") {
      try {
        // Same-origin tab notification contains only an ID, never bill fields.
        deletionChannel = new BroadcastChannel("pristine-bio-billing.invoice-deletion");
        deletionChannel.addEventListener("message", (event: MessageEvent<unknown>) => {
          const data = event.data as { type?: unknown; id?: unknown } | null;
          if ((data?.type === "invoice-deleted" || data?.type === "purchase-order-deleted") && typeof data.id === "number" && Number.isSafeInteger(data.id) && data.id > 0) invalidateMatchingInvoice(data.id, data.type === "purchase-order-deleted");
        });
      } catch { /* Same-tab invalidation remains available without channels. */ }
    }
    listening = true;
  }
}

/** Call only after the server confirms permanent invoice deletion. */
export function invalidateInvoiceEntrySession(id: number) {
  if (!Number.isSafeInteger(id) || id <= 0) return;
  listenForInvalidation();
  invalidateMatchingInvoice(id);
  try { deletionChannel?.postMessage({ type: "invoice-deleted", id }); }
  catch { /* Closed/unavailable channels must not turn confirmed deletion into failure. */ }
}
/** Clear only PO entries after confirmed removal, never same-ID invoices. */
export function invalidatePurchaseOrderEntrySession(id: number) {
  if (!Number.isSafeInteger(id) || id <= 0) return;
  listenForInvalidation();
  invalidateMatchingInvoice(id, true);
  try { deletionChannel?.postMessage({ type: "purchase-order-deleted", id }); }
  catch { /* Confirmed deletion remains successful without a channel. */ }
}
export function discardInvoiceEntrySession(userId: number, kind: InvoiceKind) {
  if (ownerId !== userId) return;
  entries.get(kind)?.dispose(); entries.delete(kind);
}

const noSubscription = () => () => {};
export function useInvoiceEntryValue<T>(entry: InvoiceEntrySession | undefined, key: string, initial: T | (() => T)): [T, Dispatch<SetStateAction<T>>] {
  const [fallback, setFallback] = useState(initial);
  const value = useSyncExternalStore(entry?.subscribe ?? noSubscription,
    () => entry ? entry.read(key, fallback) : fallback, () => fallback);
  const setValue = useCallback<Dispatch<SetStateAction<T>>>((next) => {
    if (!entry) { setFallback(next); return; }
    if (!entry.active) return;
    const current = entry.read(key, fallback);
    entry.write(key, typeof next === "function" ? (next as (previous: T) => T)(current) : next);
  }, [entry, key, fallback]);
  return [value, setValue];
}

export function useInvoiceEntryRef<T>(entry: InvoiceEntrySession | undefined, key: string, initial: T) {
  const fallback = useRef(initial);
  return useMemo(() => entry ? entry.ref(key, initial) : fallback, [entry, key, initial]);
}
