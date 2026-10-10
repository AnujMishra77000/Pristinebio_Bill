"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { AppIcon } from "@/app/components/AppIcon";
import { apiRequest } from "@/app/lib/api";
import type { Supplier } from "@/app/lib/types";

export function InvoiceSupplierPicker({ profileId, selected, onChange, validationError }: {
  profileId: number | null;
  selected: Supplier | null | undefined;
  onChange: (supplier: Supplier | null) => void;
  validationError: string | null;
}) {
  const [query, setQuery] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selection = useRef(selected);
  selection.current = selected;

  useEffect(() => {
    if (!profileId) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true);
      setError(null);
      const params = new URLSearchParams({ branch_id: String(profileId), active_only: "true", limit: "100" });
      if (query.trim()) params.set("search", query.trim());
      try {
        const records = await apiRequest<Supplier[]>(`/suppliers?${params}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        const active = records.filter((supplier) => supplier.is_active && supplier.branch_id === profileId);
        setSuppliers(active);
        // Prefill only once. Searches, refreshes and retries must not replace a choice.
        if (selection.current === undefined) onChange(active.find((supplier) => supplier.is_default) ?? null);
      } catch (failure) {
        if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "Unable to load suppliers. Refresh and try again.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, query ? 250 : 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [profileId, query, refresh, onChange]);

  const options = selected && !suppliers.some((supplier) => supplier.id === selected.id)
    ? [selected, ...suppliers] : suppliers;
  const pickupAddress = selected && [selected.address.address_line1, selected.address.address_line2,
    selected.address.city, selected.address.state, selected.address.postal_code].filter(Boolean).join(", ");

  return (
    <section aria-labelledby="invoice-supplier-heading" className="mt-6 rounded-xl border border-line bg-warm p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="invoice-supplier-heading" className="flex items-center gap-2 text-base font-bold text-ink">
          <AppIcon name="suppliers" size={18} /> Supplier selection
        </h2>
        <Link href="/suppliers" target="_blank" rel="noopener noreferrer" className="text-sm font-semibold text-peacock underline underline-offset-4">
          Manage suppliers
        </Link>
      </div>
      <p className="mt-2 text-xs text-slate-500">Choose the pickup supplier for this bill. Your company registered address stays unchanged.</p>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="invoice-supplier-search" className="text-xs font-semibold text-slate-500">Search suppliers by name</label>
          <div className="mt-2 flex gap-2">
            <input id="invoice-supplier-search" type="search" maxLength={255} className="ui-input mt-0 min-w-0 flex-1" value={query}
              onChange={(event) => setQuery(event.target.value)} placeholder="Enter supplier name"
              onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); setRefresh((value) => value + 1); } }} />
            <button type="button" aria-label="Search suppliers" className="ui-button shrink-0 px-3" onClick={() => setRefresh((value) => value + 1)}>
              <AppIcon name="search" size={16} />
            </button>
          </div>
        </div>
        <div>
          <label htmlFor="invoice-supplier-choice" className="text-xs font-semibold text-slate-500">Supplier</label>
          <select id="invoice-supplier-choice" className="ui-input" value={selected?.id ?? ""} disabled={!profileId || selected === undefined}
            aria-invalid={Boolean(validationError)} aria-describedby={validationError ? "invoice-supplier-validation" : undefined}
            onChange={(event) => onChange(options.find((supplier) => String(supplier.id) === event.target.value) ?? null)}>
            <option value="">{selected === undefined ? "Loading suppliers…" : "No pickup supplier"}</option>
            {options.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.name}{supplier.is_default ? " (default)" : ""}</option>)}
          </select>
          {validationError && <p id="invoice-supplier-validation" role="alert" className="mt-2 text-sm text-red-700">{validationError}</p>}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button type="button" className="ui-button text-xs" onClick={() => setRefresh((value) => value + 1)}>Refresh suppliers</button>
        {loading && <span role="status" className="text-xs text-slate-500">Loading suppliers…</span>}
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      {selected ? (
        <div className="mt-4 break-words rounded-lg border border-line bg-white p-3 text-sm">
          <p className="font-semibold text-ink">{selected.name}</p>
          <p className="mt-1 text-slate-600">Pickup Address: {pickupAddress}</p>
          {selected.gstin && <p className="mt-1 text-slate-600">GSTIN: {selected.gstin}</p>}
          {selected.phone && <p className="mt-1 text-slate-600">Contact: {selected.phone}</p>}
        </div>
      ) : selected === null && !loading && !error && (
        <p className="mt-3 text-sm text-slate-500">{suppliers.length ? "No pickup supplier selected." : query.trim() ? "No suppliers match this search." : "No active suppliers yet. Add one in Manage suppliers, then refresh."}</p>
      )}
    </section>
  );
}
