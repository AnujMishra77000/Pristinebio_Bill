"use client";

import type { useSavedBillLoader } from "@/app/lib/useSavedBillLoader";

export function SavedBillLoadError({ loader }: { loader: ReturnType<typeof useSavedBillLoader> }) {
  if (!loader.blocked) return null;
  return <div className="ui-alert mt-4" role={loader.error ? "alert" : "status"}>
    <p>{loader.error || "Loading the saved bill…"}</p>
    {loader.error && <button className="ui-button mt-3" type="button" disabled={loader.restarting} onClick={loader.retry}>Retry loading bill</button>}
    {loader.recovery && (loader.canRestart ? <div className="mt-4">
      <p className="text-sm">Restarting discards the old staged edits and starts from the latest confirmed bill. The previous working snapshot remains in audit history.</p>
      <label className="mt-3 block text-sm font-semibold">Restart reason<textarea aria-label="Restart reason" className="ui-input" rows={2} required disabled={loader.restarting} value={loader.restartReason} onChange={event => loader.setRestartReason(event.target.value)} /></label>
      <button className="ui-button mt-3" type="button" disabled={loader.restarting || !loader.restartReason.trim()} onClick={() => void loader.restart()}>{loader.restarting ? "Restarting correction…" : "Restart correction"}</button>
    </div> : <p className="mt-3 text-sm">Contact Manager/Admin to restart this correction from the latest confirmed bill.</p>)}
  </div>;
}
