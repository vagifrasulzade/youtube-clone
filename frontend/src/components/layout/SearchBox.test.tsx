import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import { SearchBox } from './SearchBox'

function CurrentUrl() {
  const location = useLocation()
  return <output data-testid="url">{location.pathname + location.search}</output>
}

function setup(suggestions: string[]) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(suggestions), { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <SearchBox />
        <Routes>
          <Route path="*" element={<CurrentUrl />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { fetchMock, user: userEvent.setup() }
}

describe('SearchBox', () => {
  it('shows server suggestions while typing', async () => {
    const { fetchMock, user } = setup(['plov recipe', 'plov in Baku'])

    await user.type(screen.getByRole('combobox'), 'plov')

    expect(await screen.findByRole('option', { name: 'plov recipe' })).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/search/suggestions?q=plov',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('submits the typed query to the results page', async () => {
    const { user } = setup([])

    await user.type(screen.getByRole('combobox'), 'guitar lesson{Enter}')

    expect(screen.getByTestId('url').textContent).toBe('/results?search_query=guitar%20lesson')
  })

  it('selects a suggestion with the keyboard', async () => {
    const { user } = setup(['plov recipe', 'plov in Baku'])
    const input = screen.getByRole('combobox')

    await user.type(input, 'plov')
    await screen.findByRole('option', { name: 'plov in Baku' })
    await user.keyboard('{ArrowDown}{ArrowDown}{Enter}')

    await waitFor(() =>
      expect(screen.getByTestId('url').textContent).toBe('/results?search_query=plov%20in%20Baku'),
    )
  })

  it('does not search for blank input', async () => {
    const { user } = setup([])

    await user.type(screen.getByRole('combobox'), '   {Enter}')

    expect(screen.getByTestId('url').textContent).toBe('/')
  })
})
