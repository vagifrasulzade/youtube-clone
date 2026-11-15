import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import { type Video, VideoCard } from './VideoCard'

const video: Video = {
  id: 'abcDEF12345',
  title: 'Azerbaijani plov recipe',
  thumbnail_url: '/api/v1/media/videos/abcDEF12345/thumbnail?v=1',
  duration_seconds: 125,
  view_count: 12345,
  published_at: '2026-11-10T12:00:00Z',
  channel: { id: '7a1b2c3d-0000-4000-8000-000000000000', handle: 'alice_cooks', name: 'Alice Cooks', avatar_url: null },
}

function renderCard() {
  return render(
    <MemoryRouter>
      <VideoCard video={video} />
    </MemoryRouter>,
  )
}

describe('VideoCard', () => {
  it('shows title, channel, duration badge and view count', () => {
    renderCard()

    expect(screen.getByRole('heading', { name: video.title })).toBeTruthy()
    expect(screen.getByText('Alice Cooks')).toBeTruthy()
    expect(screen.getByText('2:05')).toBeTruthy()
    expect(screen.getByText(/12,345 views/)).toBeTruthy()
  })

  it('links to the YouTube-style watch URL and the @handle channel URL', () => {
    renderCard()

    const hrefs = screen.getAllByRole('link').map((a) => a.getAttribute('href'))
    expect(hrefs).toContain('/watch?v=abcDEF12345')
    expect(hrefs).toContain('/@alice_cooks')
  })

  it('falls back to the channel initial when there is no avatar', () => {
    renderCard()

    expect(screen.getByText('A')).toBeTruthy()
  })
})
