import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'

import { AuthContext, type AuthState, type CurrentUser } from './context'
import { safeNext } from './redirect'
import { RequireAuth } from './RequireAuth'

describe('safeNext', () => {
  it.each([
    ['/watch?v=abc', '/watch?v=abc'],
    ['/studio', '/studio'],
    ['https://evil.example', '/'],
    ['//evil.example', '/'],
    ['/\\evil.example', '/'],
    ['javascript:alert(1)', '/'],
    [undefined, '/'],
  ])('%s -> %s', (input, expected) => {
    expect(safeNext(input)).toBe(expected)
  })
})

function user(role: CurrentUser['role']): CurrentUser {
  return {
    id: 'u1',
    email: 'a@example.com',
    role,
    created_at: '2026-11-15T00:00:00Z',
    channel: { id: 'c1', handle: 'alice', name: 'Alice', avatar_url: null },
  }
}

function renderGuarded(auth: Partial<AuthState>, role?: CurrentUser['role']) {
  const value: AuthState = {
    status: 'ready',
    user: null,
    login: async () => undefined,
    register: async () => undefined,
    logout: async () => undefined,
    ...auth,
  }
  render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={['/admin']}>
        <Routes>
          <Route path="/login" element={<p>login page</p>} />
          <Route
            path="/admin"
            element={
              <RequireAuth role={role}>
                <p>secret page</p>
              </RequireAuth>
            }
          />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

describe('RequireAuth', () => {
  it('sends anonymous visitors to sign in', () => {
    renderGuarded({ user: null })
    expect(screen.getByText('login page')).toBeTruthy()
    expect(screen.queryByText('secret page')).toBeNull()
  })

  it('hides role-gated pages from users without the role', () => {
    renderGuarded({ user: user('moderator') }, 'admin')
    expect(screen.getByText("You don't have access to this page")).toBeTruthy()
    expect(screen.queryByText('secret page')).toBeNull()
  })

  it('shows the page to users with the role', () => {
    renderGuarded({ user: user('admin') }, 'admin')
    expect(screen.getByText('secret page')).toBeTruthy()
  })

  it('waits for the session check before deciding', () => {
    renderGuarded({ status: 'loading', user: null })
    expect(screen.queryByText('login page')).toBeNull()
    expect(screen.queryByText('secret page')).toBeNull()
  })
})
