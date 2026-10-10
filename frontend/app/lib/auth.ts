import type { User } from "./types";

export function normalizePassphrase(value: string): string {
  const normalized = value.normalize("NFC");
  const length = Array.from(normalized).length;
  if (length < 6 || length > 10) throw new Error("Use a passphrase of 6–10 characters. Spaces and Unicode are allowed.");
  return normalized;
}

export function authStep(user: User | null): "login" | "password" | "ready" {
  if (!user?.is_active) return "login";
  if (user.password_change_required) return "password";
  return "ready";
}
