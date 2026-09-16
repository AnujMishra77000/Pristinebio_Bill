"use client";

import type { TokenResponse } from "@/app/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const SESSION_STORAGE_KEY = "pristine-bio-billing.session";
export const SESSION_CHANGED_EVENT = "pristine-bio-billing.session-changed";
let refreshPromise: Promise<TokenResponse | null> | null = null;

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); this.name = "ApiError"; }
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

export function getStoredSession(): TokenResponse | null {
  if (typeof window === "undefined") return null;
  const value = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (!value) return null;
  try { return JSON.parse(value) as TokenResponse; } catch { return null; }
}

function notifySessionChanged(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(SESSION_CHANGED_EVENT));
}

export function storeSession(session: TokenResponse): void {
  window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  notifySessionChanged();
}

export function clearSession(): void {
  window.localStorage.removeItem(SESSION_STORAGE_KEY);
  notifySessionChanged();
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

async function refreshAccessToken(): Promise<TokenResponse | null> {
  const session = getStoredSession();
  const refreshToken = session?.refresh_token;
  if (!refreshToken) return null;
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    try {
      const response = await fetch(apiUrl("/auth/refresh"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!response.ok) return null;
      const refreshed = (await response.json()) as TokenResponse;
      if (!refreshed.access_token) return null;
      const currentSession = getStoredSession();
      if (currentSession?.refresh_token !== refreshToken) return null;
      const nextSession: TokenResponse = {
        ...currentSession,
        ...refreshed,
        refresh_token: refreshed.refresh_token ?? refreshToken,
        user: refreshed.user ?? currentSession.user,
      };
      storeSession(nextSession);
      return nextSession;
    } catch {
      return null;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

async function fetchWithAuth(path: string, options: RequestInit = {}): Promise<Response> {
  const headers = new Headers(options.headers);
  const session = getStoredSession();
  if (session?.access_token) headers.set("Authorization", `Bearer ${session.access_token}`);

  let response: Response;
  try {
    response = await fetch(apiUrl(path), { ...options, headers });
  } catch {
    throw networkApiError(path);
  }

  const authEndpoint = path.startsWith("/auth/login") || path.startsWith("/auth/register") || path.startsWith("/auth/refresh");
  if (response.status !== 401 || authEndpoint) return response;

  const refreshed = await refreshAccessToken();
  if (!refreshed?.access_token) return response;
  const retryHeaders = new Headers(options.headers);
  retryHeaders.set("Authorization", `Bearer ${refreshed.access_token}`);
  try {
    return await fetch(apiUrl(path), { ...options, headers: retryHeaders });
  } catch {
    throw networkApiError(path);
  }
}

async function fetchFileBlob(path: string): Promise<Blob> {
  const response = await fetchWithAuth(path);
  if (!response.ok) throw new ApiError(response.status, response.statusText || "File request failed");
  return response.blob();
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetchWithAuth(path, options);
  if (!response.ok) {
    let message = response.statusText || "Request failed";
    try {
      const body: unknown = await response.json();
      if (typeof body === "object" && body !== null) {
        const record = body as Record<string, unknown>;
        const detailMessage = formatApiDetail(record.detail);
        const apiMessage = record.message;
        if (detailMessage) message = detailMessage;
        else if (typeof apiMessage === "string") message = apiMessage;
      }
    } catch { /* Preserve the response status text for non-JSON errors. */ }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
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
