// Minimal JSON helpers for public (anonymous) endpoints.

export class HttpError extends Error {
  readonly status: number
  readonly code: string | undefined

  constructor(status: number, code: string | undefined, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function parse<T>(response: Response): Promise<T> {
  if (response.ok) return (await response.json()) as T
  let code: string | undefined
  let message = `Request failed (${response.status})`
  try {
    const body = (await response.json()) as { error?: { code?: string; message?: string } }
    code = body.error?.code
    message = body.error?.message ?? message
  } catch {
    // non-JSON error body: keep the generic message
  }
  throw new HttpError(response.status, code, message)
}

export async function getJson<T>(path: string, params?: Record<string, string>): Promise<T> {
  const query = params ? `?${new URLSearchParams(params)}` : ''
  return parse<T>(await fetch(`/api/v1${path}${query}`))
}

export async function postJson<T>(path: string): Promise<T> {
  return parse<T>(await fetch(`/api/v1${path}`, { method: 'POST' }))
}
