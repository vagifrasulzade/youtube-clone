import { describe, expect, it, vi } from 'vitest'

import { HttpError, getJson } from './http'

function respond(status: number, body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  )
}

describe('getJson', () => {
  it('returns the parsed body and builds the query string', async () => {
    respond(200, { items: [], next_cursor: null })

    const data = await getJson('/videos', { limit: '24', cursor: 'a b' })

    expect(data).toEqual({ items: [], next_cursor: null })
    expect(fetch).toHaveBeenCalledWith('/api/v1/videos?limit=24&cursor=a+b')
  })

  it('turns the API error envelope into an HttpError', async () => {
    respond(404, { error: { code: 'video_not_found', message: 'Video not found', details: null } })

    const error = await getJson('/videos/x').catch((e: unknown) => e)

    expect(error).toBeInstanceOf(HttpError)
    expect(error).toMatchObject({ status: 404, code: 'video_not_found', message: 'Video not found' })
  })

  it('copes with a non-JSON error body', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('<html>502</html>', { status: 502 })))

    const error = await getJson('/videos').catch((e: unknown) => e)

    expect(error).toMatchObject({ status: 502, code: undefined })
  })
})
