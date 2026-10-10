"use client";

import type { SessionResponse, User } from "@/app/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const SESSION_STORAGE_KEY = "pristine-bio-billing.session";
export const SESSION_CHANGED_EVENT = "pristine-bio-billing.session-changed";
let refreshPromise: Promise<SessionResponse | null> | null = null;
let validationPromise: Promise<SessionResponse | null> | null = null;
let csrfPromise: Promise<string> | null = null;
let csrfToken: string | null = null;
let session: SessionResponse | null = null;
let reauthenticationRequired = false;
let explicitlyLoggedOut = false;
let sessionRevision = 0;
let csrfRevision = 0;
let channel: BroadcastChannel | null = null;
let initialized = false;
let validationError: string | null = null;

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) { super(message); this.name = "ApiError"; }
}

export function createIdempotencyKey(): string {
  if (typeof globalThis.crypto !== "undefined" && typeof globalThis.crypto.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  if (typeof globalThis.crypto !== "undefined" && typeof globalThis.crypto.getRandomValues === "function") {
    const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function formatApiDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return null;

  const messages = detail
    .map((item) => {
      if (typeof item === "string") return item;
      if (typeof item !== "object" || item === null) return null;

      const record = item as Record<string, unknown>;
      const message = typeof record.msg === "string" ? record.msg : null;
      if (!message) return null;

      const location = Array.isArray(record.loc)
        ? record.loc.filter((part): part is string | number => typeof part === "string" || typeof part === "number").join(".")
        : "";
      return location ? `${location}: ${message}` : message;
    })
    .filter((message): message is string => Boolean(message));

  return messages.length > 0 ? messages.join("; ") : null;
}

function initializeSession(): void {
  if (initialized || typeof window === "undefined") return;
  initialized = true;
  try { window.localStorage.removeItem(SESSION_STORAGE_KEY); } catch { /* Storage may be disabled. */ }
  if (typeof BroadcastChannel !== "undefined") {
    channel = new BroadcastChannel("pristine-bio-billing.session");
    channel.addEventListener("message", (event: MessageEvent<unknown>) => {
      const message = event.data as { type?: string } | null;
      if (message?.type === "logout") clearSession(false);
      else if (message?.type === "changed") {
        sessionRevision++;
        invalidateCsrf();
        void validateSession();
      }
    });
  }
}

// Compatibility name for existing consumers; metadata is now memory-only.
export function getStoredSession(): SessionResponse | null { initializeSession(); return session; }
export function getSessionState() {
  initializeSession();
  return { session, reauthenticationRequired, explicitlyLoggedOut, validationError };
}
export function isSessionReady(): boolean {
  const user = session?.user;
  return Boolean(user?.is_active && !user.password_change_required && !reauthenticationRequired);
}

function notifySessionChanged(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(SESSION_CHANGED_EVENT));
}

function acceptSession(next: SessionResponse): void {
  session = next;
  explicitlyLoggedOut = false;
  reauthenticationRequired = false;
  validationError = null;
  notifySessionChanged();
}

function invalidateCsrf(): void {
  csrfRevision++;
  csrfToken = null;
  csrfPromise = null;
}

function clearSession(broadcast = true): void {
  session = null;
  explicitlyLoggedOut = true;
  reauthenticationRequired = false;
  sessionRevision++;
  invalidateCsrf();
  notifySessionChanged();
  if (broadcast) channel?.postMessage({ type: "logout" });
}

export async function logoutSession(all = false): Promise<void> {
  await apiRequest(all ? "/auth/logout-all" : "/auth/logout", { method: "POST" });
  clearSession();
}

export async function revokeSession(id: string, current = false): Promise<void> {
  await apiRequest(`/auth/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (current) clearSession();
}

function apiUrl(path: string): string {
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

function networkApiError(path: string): ApiError {
  if (path.startsWith("/auth/register")) {
    return new ApiError(
      0,
      "Registration could not reach the billing server. Start the backend at http://localhost:8000 and try again."
    );
  }
  if (path.startsWith("/auth/login")) {
    return new ApiError(
      0,
      "Login could not reach the billing server. Start the backend at http://localhost:8000 and try again."
    );
  }
  return new ApiError(
    0,
    "The billing server could not be reached. Confirm the backend is running and try again."
  );
}

async function getCsrf(actionPath: string): Promise<string> {
  if (csrfToken) return csrfToken;
  if (csrfPromise) return csrfPromise;
  const revision = csrfRevision;
  const pending = (async () => {
    const response = await rawFetch("/auth/csrf", {}, actionPath);
    if (!response.ok) throw new ApiError(response.status, "Unable to establish request security. Try again.");
    const data = await response.json() as { csrf_token: string };
    if (!data.csrf_token) throw new ApiError(0, "Unable to establish request security. Try again.");
    if (revision !== csrfRevision) return getCsrf(actionPath);
    csrfToken = data.csrf_token;
    return csrfToken;
  })();
  csrfPromise = pending;
  try { return await pending; } finally { if (csrfPromise === pending) csrfPromise = null; }
}

async function rawFetch(path: string, options: RequestInit = {}, actionPath = path): Promise<Response> {
  try { return await fetch(apiUrl(path), { ...options, credentials: "include" }); }
  catch { throw networkApiError(actionPath); }
}

async function secureFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const headers = new Headers(options.headers);
  const method = (options.method ?? "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-CSRF-Token", await getCsrf(path));
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  return rawFetch(path, { ...options, headers });
}

async function sessionChanged(next: SessionResponse): Promise<void> {
  sessionRevision++;
  invalidateCsrf();
  acceptSession(next);
  channel?.postMessage({ type: "changed" });
  // Metadata is already usable if CSRF acquisition has a transient network failure.
  try { await getCsrf("/auth/csrf"); } catch { /* Unsafe requests retry CSRF acquisition. */ }
}

async function refreshAccessToken(): Promise<SessionResponse | null> {
  if (refreshPromise) return refreshPromise;
  const revision = sessionRevision;
  const refresh = async (): Promise<SessionResponse | null> => {
    try {
      // Another tab may have refreshed while this tab waited for the lock.
      const me = await rawFetch("/auth/me");
      if (revision !== sessionRevision && explicitlyLoggedOut) return null;
      if (me.ok) {
        const next = { user: await me.json() as User };
        acceptSession(next);
        return next;
      }
      if (me.status !== 401) return null;
      invalidateCsrf();
      const refreshRevision = sessionRevision;
      const response = await fetchWithAuth("/auth/refresh", { method: "POST" });
      if (!response.ok) return null;
      const next = await response.json() as SessionResponse;
      if (refreshRevision !== sessionRevision || !next.user) return null;
      await sessionChanged(next);
      return next;
    } catch { return null; }
  };
  refreshPromise = (async () => {
    if (typeof navigator !== "undefined" && navigator.locks) return navigator.locks.request("pristine-bio-billing.session-refresh", refresh);
    return refresh();
  })();
  try { return await refreshPromise; } finally { refreshPromise = null; }
}

async function fetchWithAuth(path: string, options: RequestInit = {}): Promise<Response> {
  initializeSession();
  let csrfRetried = false;
  const request = async () => {
    let response = await secureFetch(path, options);
    if (response.status === 403 && !csrfRetried) {
      const data = await response.clone().json().catch(() => null) as { detail?: string } | null;
      if (typeof data?.detail === "string" && data.detail.startsWith("CSRF validation failed")) {
        csrfRetried = true;
        invalidateCsrf();
        response = await secureFetch(path, options);
      }
    }
    return response;
  };
  let response = await request();
  const noRefresh = ["/auth/login", "/auth/register", "/auth/invitations/accept", "/auth/refresh", "/auth/csrf"].includes(path);
  if (response.status === 401 && !noRefresh) {
    const validatesSecret = path === "/auth/password" || path.startsWith("/auth/mfa/") || /^\/users\/\d+\/mfa-reset$/.test(path);
    if (validatesSecret) {
      const me = await rawFetch("/auth/me");
      // A bad code/password is an action error, not a lost cookie session.
      if (me.ok) return response;
    }
    if (await refreshAccessToken()) response = await request();
    if (response.status === 401) {
      reauthenticationRequired = true;
      notifySessionChanged();
    }
  }
  if (response.status === 403) {
    const data = await response.clone().json().catch(() => null) as { detail?: string } | null;
    if (["password_change_required", "mfa_enrollment_required", "mfa_verification_required"].includes(data?.detail ?? "")) {
      reauthenticationRequired = true;
      notifySessionChanged();
      void validateSession();
    }
  }
  return response;
}

export async function validateSession(): Promise<SessionResponse | null> {
  if (validationPromise) return validationPromise;
  const revision = sessionRevision;
  validationPromise = (async () => {
    try {
      const user = await apiRequest<User>("/auth/me");
      if (explicitlyLoggedOut && revision !== sessionRevision) return null;
      const next = { user };
      acceptSession(next);
      return next;
    } catch (error) {
      validationError = error instanceof ApiError ? error.message : "Unable to verify your session.";
      reauthenticationRequired = true;
      notifySessionChanged();
      return null;
    }
  })();
  try { return await validationPromise; } finally { validationPromise = null; }
}

export async function fetchFileBlob(path: string, options: RequestInit = {}): Promise<Blob> {
  const response = await fetchWithAuth(path, { ...options, cache: "no-store" });
  if (!response.ok) {
    let detail: unknown;
    let message = response.statusText || "File request failed";
    try {
      const body = await response.json();
      detail = body.detail;
      message = formatApiDetail(detail) || message;
    } catch { /* Keep the original HTTP error for non-JSON responses. */ }
    throw new ApiError(response.status, message, detail);
  }
  if (!response.headers.get("content-type")?.toLowerCase().includes("application/pdf")) {
    throw new ApiError(response.status, "The server did not return a valid PDF. Your bill remains saved; retry the preview.");
  }
  return response.blob();
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetchWithAuth(path, options);
  if (!response.ok) {
    let message = response.statusText || "Request failed";
    let errorDetail: unknown;
    try {
      const body: unknown = await response.json();
      if (typeof body === "object" && body !== null) {
        const record = body as Record<string, unknown>;
        errorDetail = record.detail;
        const detailMessage = formatApiDetail(record.detail);
        const apiMessage = record.message;
        if (detailMessage) message = detailMessage;
        else if (typeof record.detail === "object" && record.detail !== null && typeof (record.detail as Record<string, unknown>).message === "string") message = (record.detail as Record<string, string>).message;
        else if (typeof apiMessage === "string") message = apiMessage;
      }
    } catch { /* Preserve the response status text for non-JSON errors. */ }
    throw new ApiError(response.status, message, errorDetail);
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json() as T;
  const changedPaths = ["/auth/login", "/auth/register", "/auth/invitations/accept", "/auth/password"];
  if (changedPaths.includes(path)) {
    const next = data as SessionResponse;
    if (next.user) {
      await sessionChanged(next);
    }
  } else if (path.startsWith("/auth/mfa/")) {
    invalidateCsrf();
    try { await getCsrf(path); } catch { /* Next unsafe request retries acquisition. */ }
  }
  return data;
}

export async function downloadFile(path: string, filename: string): Promise<void> {
  const url = URL.createObjectURL(await fetchFileBlob(path));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function previewPdf(path: string, filename: string, autoPrint = false): Promise<void> {
  const previewWindow = window.open("", "_blank", "width=1200,height=900");
  if (!previewWindow) throw new ApiError(0, "Allow pop-ups to preview or print the PDF.");
  try {
    const url = URL.createObjectURL(await fetchFileBlob(path));
    previewWindow.document.write("<!doctype html><html><head><title>PDF preview</title></head><body></body></html>");
    previewWindow.document.close();
    const style = previewWindow.document.createElement("style");
    style.textContent = "body{margin:0;background:#eef1f6;font-family:Arial,sans-serif}.toolbar{position:sticky;top:0;z-index:1;display:flex;gap:8px;padding:12px 16px;background:#14213d}.toolbar a,.toolbar button{border:0;border-radius:8px;padding:9px 14px;font:600 13px Arial;cursor:pointer;text-decoration:none}.toolbar a{background:#fff;color:#14213d}.toolbar button{background:#6f8fe8;color:#fff}.preview{display:block;width:100%;height:calc(100vh - 64px);border:0;background:#fff}@media print{.toolbar{display:none}.preview{height:100vh}}";
    previewWindow.document.head.appendChild(style);
    const toolbar = previewWindow.document.createElement("div");
    toolbar.className = "toolbar";
    const downloadLink = previewWindow.document.createElement("a");
    downloadLink.href = url;
    downloadLink.download = filename;
    downloadLink.textContent = "Download PDF";
    const printButton = previewWindow.document.createElement("button");
    printButton.type = "button";
    printButton.textContent = "Print PDF";
    printButton.addEventListener("click", () => previewWindow.print());
    toolbar.append(downloadLink, printButton);
    const frame = previewWindow.document.createElement("iframe");
    frame.className = "preview";
    frame.title = filename;
    frame.src = url;
    previewWindow.document.body.append(toolbar, frame);
    previewWindow.addEventListener("beforeunload", () => URL.revokeObjectURL(url), { once: true });
    if (autoPrint) frame.addEventListener("load", () => previewWindow.setTimeout(() => previewWindow.print(), 800), { once: true });
  } catch (error) {
    previewWindow.close();
    throw error;
  }
}
