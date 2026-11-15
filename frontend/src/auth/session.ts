// Session tokens (docs/security.md § 2).
//
// - The access token (15 min) lives only in this module's memory, never in localStorage:
//   a script injected into the page cannot read a stored credential, and a page reload
//   simply asks for a new one.
// - The refresh token is an HttpOnly, SameSite=Strict cookie scoped to /api/v1/auth.
//   JavaScript never sees it; the browser attaches it to /auth/refresh by itself.

let accessToken: string | null = null
let pendingRefresh: Promise<string | null> | null = null
const expiryListeners = new Set<() => void>()

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null): void {
  accessToken = token
}

/** Called when a refresh fails: the server no longer recognises this browser's session. */
export function onSessionExpired(listener: () => void): () => void {
  expiryListeners.add(listener)
  return () => expiryListeners.delete(listener)
}

export function notifySessionExpired(): void {
  accessToken = null
  expiryListeners.forEach((listener) => listener())
}

/**
 * One refresh at a time. Refresh tokens rotate and a replayed one revokes the whole
 * session family, so concurrent 401s (or React StrictMode's double mount) must share a
 * single request instead of each spending the cookie.
 */
export function refreshAccessToken(): Promise<string | null> {
  pendingRefresh ??= fetch('/api/v1/auth/refresh', { method: 'POST', credentials: 'same-origin' })
    .then(async (response) =>
      response.ok ? ((await response.json()) as { access_token: string }).access_token : null,
    )
    .catch(() => null)
    .then((token) => {
      accessToken = token
      return token
    })
    .finally(() => {
      pendingRefresh = null
    })
  return pendingRefresh
}
