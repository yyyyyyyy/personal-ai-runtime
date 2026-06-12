/** Auth token initialization — runs before React mounts. */

import { setAuthToken } from "./api/client";

const STORAGE_KEY = "auth_token";

export function initAuth(): void {
  const fromEnv = import.meta.env.VITE_AUTH_TOKEN?.trim();
  const fromStorage =
    typeof localStorage !== "undefined" ? localStorage.getItem(STORAGE_KEY)?.trim() : null;
  const token = fromEnv || fromStorage;
  if (token) {
    setAuthToken(token);
  }
}

export function saveAuthToken(token: string): void {
  const trimmed = token.trim();
  if (trimmed) {
    localStorage.setItem(STORAGE_KEY, trimmed);
    setAuthToken(trimmed);
  }
}

initAuth();
