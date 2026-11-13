let csrfToken: string | null = null;
export const AUTH_REQUIRED = "sverka:auth-required";

export function setCsrfToken(value: string | null) {
  csrfToken = value;
}

export async function authFetch(path: string, init: RequestInit = {}) {
  // Never attach a session's CSRF token to an arbitrary or external URL.
  const url = new URL(path, window.location.href);
  if (url.origin !== window.location.origin || !url.pathname.startsWith("/api/")) {
    throw new Error("Недопустимый адрес запроса.");
  }
  const headers = new Headers(init.headers);
  if (!["GET", "HEAD", "OPTIONS"].includes((init.method || "GET").toUpperCase())) {
    headers.set("X-Sverka-Request", "1");
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(url, { ...init, headers, credentials: "same-origin", redirect: "error" });
  if (response.status === 401 && url.pathname !== "/api/auth/login") {
    setCsrfToken(null);
    window.dispatchEvent(new Event(AUTH_REQUIRED));
  }
  return response;
}
