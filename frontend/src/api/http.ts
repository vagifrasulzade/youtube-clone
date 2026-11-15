// JSON client for /api/v1. Adds the in-memory access token when there is one, and on a
// 401 refreshes it once (via the HttpOnly cookie) and retries the request.

import { getAccessToken, notifySessionExpired, refreshAccessToken } from '../auth/session'

export interface FieldError {
  loc: (string | number)[]
  message: string
}

export class HttpError extends Error {
  readonly status: number
  readonly code: string | undefined
  readonly details: FieldError[]

  constructor(status: number, code: string | undefined, message: string, details: FieldError[] = []) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

/** A sentence for the UI: the API's message, or the first invalid field for a 422. */
export function describeError(error: unknown): string {
  if (!(error instanceof HttpError)) return 'Something went wrong. Check your connection and try again.'
  const [first] = error.details
  if (error.code === 'validation_error' && first) {
    const field = String(first.loc[first.loc.length - 1] ?? '').replace(/_/g, ' ')
    return field ? `${field}: ${first.message}` : first.message
  }
  return error.message
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  params?: Record<string, string | undefined>
  json?: unknown
  body?: FormData
}

async function parse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T
  if (response.ok) return (await response.json()) as T
  let code: string | undefined
  let message = `Request failed (${response.status})`
  let details: FieldError[] = []
  try {
    const body = (await response.json()) as {
      error?: { code?: string; message?: string; details?: unknown }
    }
    code = body.error?.code
    message = body.error?.message ?? message
    if (Array.isArray(body.error?.details)) details = body.error.details as FieldError[]
  } catch {
    // non-JSON error body: keep the generic message
  }
  throw new HttpError(response.status, code, message, details)
}

function buildUrl(path: string, params?: Record<string, string | undefined>): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== '') query.set(key, value)
  }
  const qs = query.toString()
  return `/api/v1${path}${qs ? `?${qs}` : ''}`
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = buildUrl(path, options.params)
  const send = (token: string | null) => {
    const headers = new Headers()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    let body: BodyInit | undefined = options.body
    if (options.json !== undefined) {
      headers.set('Content-Type', 'application/json')
      body = JSON.stringify(options.json)
    }
    return fetch(url, { method: options.method ?? 'GET', headers, body, credentials: 'same-origin' })
  }

  const token = getAccessToken()
  let response = await send(token)
  if (response.status === 401 && token) {
    const fresh = await refreshAccessToken()
    if (fresh) response = await send(fresh)
    else notifySessionExpired()
  }
  return parse<T>(response)
}

export function getJson<T>(path: string, params?: Record<string, string | undefined>): Promise<T> {
  return request<T>(path, { params })
}

export function postJson<T>(path: string, json?: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', json })
}
