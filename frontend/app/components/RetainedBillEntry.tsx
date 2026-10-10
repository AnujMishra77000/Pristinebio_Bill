"use client";

import { useEffect, useState, type ReactNode } from "react";
import { AuthGateStatus, useAuthStatus, useSessionState, type AuthStatus } from "./AuthGate";
import { getInvoiceEntrySession, INVOICE_ENTRY_INVALIDATED_EVENT, type InvoiceEntrySession, type InvoiceKind } from "../lib/invoiceEntrySession";

type EntryProps = { entry: InvoiceEntrySession; authStatus: AuthStatus };

/** Authenticated, same-tab PO memory; no sensitive browser persistence. */
export function RetainedBillEntry({ kind, children }: { kind: InvoiceKind; children: (props: EntryProps) => ReactNode }) {
  const authStatus = useAuthStatus();
  const { session } = useSessionState();
  const [epoch, setEpoch] = useState(0);
  useEffect(() => {
    const recover = (event: Event) => {
      if ((event as CustomEvent<{ kind?: string }>).detail?.kind === kind) setEpoch(value => value + 1);
    };
    window.addEventListener(INVOICE_ENTRY_INVALIDATED_EVENT, recover);
    return () => window.removeEventListener(INVOICE_ENTRY_INVALIDATED_EVENT, recover);
  }, [kind]);
  return <AuthGateStatus status={authStatus}>{session?.user.is_active &&
    <MemoryEntry key={`${session.user.id}:${kind}:${epoch}`} userId={session.user.id} kind={kind} authStatus={authStatus}>{children}</MemoryEntry>}
  </AuthGateStatus>;
}

function MemoryEntry({ userId, kind, authStatus, children }: { userId: number; kind: InvoiceKind; authStatus: AuthStatus; children: (props: EntryProps) => ReactNode }) {
  const [entry] = useState(() => getInvoiceEntrySession(userId, kind));
  return children({ entry, authStatus });
}
