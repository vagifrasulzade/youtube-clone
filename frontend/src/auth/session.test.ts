import { afterEach, describe, expect, it, vi } from 'vitest'

import { request } from '../api/http'
import { getAccessToken, onSessionExpired, refreshAccessToken, setAccessToken } from './session'

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

function authHeader(call: unknown[]): string | null {
  const init = call[1] as RequestInit | undefined
  return new Headers(init?.headers).get('Authorization')
}

afterEach(() => {
  setAccessToken(null)
  vi.unstubAllGlobals()
})

describe('refreshAccessToken', () => {
  it('shares one request between concurrent callers', async () => {
    const fetchMock = vi.fn(async () => json(200, { access_token: 'fresh' }))
    vi.stubGlobal('fetch', fetchMock)

    const tokens = await Promise.all([refreshAccessToken(), refreshAccessToken(), refreshAccessToken()])

    expect(tokens).toEqual(['fresh', 'fresh', 'fresh'])
    expect(fetchMock).toHaveBeenCalledTimes(1) // a rotating refresh token is spent once
    expect(getAccessToken()).toBe('fresh')
  })

  it('clears the token when the cookie is no longer valid', async () => {
    setAccessToken('old')
    vi.stubGlobal('fetch', vi.fn(async () => json(401, { error: { code: 'invalid_refresh' } })))

    expect(await refreshAccessToken()).toBeNull()
    expect(getAccessToken()).toBeNull()
  })
})

describe('request', () => {
  it('sends the access token and retries once after refreshing on 401', async () => {
    setAccessToken('expired')
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(401, { error: { code: 'token_expired', message: 'Expired' } }))
      .mockResolvedValueOnce(json(200, { access_token: 'fresh' })) // POST /auth/refresh
      .mockResolvedValueOnce(json(200, { ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    expect(await request('/me/liked')).toEqual({ ok: true })

    expect(authHeader(fetchMock.mock.calls[0])).toBe('Bearer expired')
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/auth/refresh')
    expect(authHeader(fetchMock.mock.calls[2])).toBe('Bearer fresh')
  })

  it('ends the session when the refresh fails', async () => {
    setAccessToken('expired')
    const expired = vi.fn()
    const stop = onSessionExpired(expired)
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(json(401, { error: { code: 'token_expired', message: 'Expired' } }))
        .mockResolvedValueOnce(json(401, { error: { code: 'invalid_refresh', message: 'No' } })),
    )

    await expect(request('/me/liked')).rejects.toMatchObject({ status: 401 })
    expect(expired).toHaveBeenCalledOnce()
    expect(getAccessToken()).toBeNull()
    stop()
  })

  it('does not try to refresh for anonymous requests', async () => {
    const fetchMock = vi.fn(async () => json(401, { error: { code: 'not_authenticated', message: 'x' } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(request('/me/liked')).rejects.toMatchObject({ status: 401 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(authHeader(fetchMock.mock.calls[0])).toBeNull()
  })

  it('sends JSON bodies and accepts 204', async () => {
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(
      async () => new Response(null, { status: 204 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(request('/comments/1', { method: 'DELETE' })).resolves.toBeUndefined()
    await request('/videos/x/reaction', { method: 'PUT', json: { value: 'like' } })

    const init = fetchMock.mock.calls[1][1] as RequestInit
    expect(init.method).toBe('PUT')
    expect(init.body).toBe('{"value":"like"}')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
  })
})
