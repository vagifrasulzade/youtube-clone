// Session tokens (docs/security.md § 2).
//
// - The access token (15 min) lives only in this module's memory, never in localStorage:
//   a script injected into the page cannot read a stored credential, and a page reload
//   simply asks for a new one.
// - The refresh token is an HttpOnly, SameSite=Strict cookie scoped to /api/v1/auth.
//   JavaScript never sees it; the browser attaches it to /auth/refresh by itself.

let accessToken: string | null = null
// Bumped on every sign-in/sign-out: a refresh that answers after the user signed out
// (or in as someone else) must not bring the old session back.
let generation = 0
let pendingRefresh: Promise<string | null> | null = null
// Requests made while the start-up refresh is running wait for it, so the first page of
// a reload is fetched as the signed-in user (private videos, my_reaction, can_edit...).
let startup: Promise<unknown> = Promise.resolve()
const expiryListeners = new Set<() => void>()

export class TransientRefreshError extends Error {}

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null): void {
  generation += 1
  accessToken = token
}

/** Called when the server no longer accepts this browser's session. */
export function onSessionExpired(listener: () => void): () => void {
  expiryListeners.add(listener)
  return () => expiryListeners.delete(listener)
}

export function notifySessionExpired(): void {
  setAccessToken(null)
  expiryListeners.forEach((listener) => listener())
}

async function errorCode(response: Response): Promise<string | undefined> {
  try {
    return ((await response.json()) as { error?: { code?: string } }).error?.code
  } catch {
    return undefined
  }
}

async function callRefresh(): Promise<string | null> {
  const post = () => fetch('/api/v1/auth/refresh', { method: 'POST', credentials: 'same-origin' })
  let response = await post()
  // Another tab rotated the cookie a moment ago; the browser now holds the new one.
  if (response.status === 401 && (await errorCode(response.clone())) === 'refresh_superseded') {
    response = await post()
  }
  if (response.ok) return ((await response.json()) as { access_token: string }).access_token
  if (response.status === 401 || response.status === 403) return null // signed out or banned
  throw new TransientRefreshError(`Refresh failed (${response.status})`) // 429/5xx: try later
}

/**
 * One refresh at a time. Refresh tokens rotate and a replayed one revokes the whole
 * session family, so concurrent 401s (or React StrictMode's double mount) must share a
 * single request instead of each spending the cookie.
 *
 * Resolves to the new token, or `null` when the server rejects the cookie (signed out).
 * REJECTS when the server or network is briefly unavailable: that must not sign anyone out.
 */
export function refreshAccessToken(): Promise<string | null> {
  if (!pendingRefresh) {
    const startedAt = generation
    pendingRefresh = callRefresh()
      .then((token) => {
        if (generation !== startedAt) return accessToken // signed in/out meanwhile: ignore
        accessToken = token
        return token
      })
      .finally(() => {
        pendingRefresh = null
      })
  }
  return pendingRefresh
}

/** Lets sign-out wait for an in-flight refresh, so it revokes the newest cookie. */
export function settleRefresh(): Promise<unknown> {
  return (pendingRefresh ?? Promise.resolve()).catch(() => null)
}

/** The start-up refresh; other requests wait for it (see `waitForStartup`). */
export function restoreSession(): Promise<string | null> {
  const refresh = refreshAccessToken()
  startup = refresh.catch(() => null)
  return refresh
}

export function waitForStartup(): Promise<unknown> {
  return startup
}
