import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import { AuthContext, type AuthState } from '../auth/context'
import { LoginPage, RegisterPage } from './AuthPages'

const auth: AuthState = {
  status: 'ready',
  user: null,
  login: async () => undefined,
  register: async () => undefined,
  logout: async () => undefined,
}

function renderPage(page: React.ReactNode) {
  render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter>{page}</MemoryRouter>
    </AuthContext.Provider>,
  )
}

describe.each([
  ['sign in', <LoginPage key="login" />],
  ['create account', <RegisterPage key="register" />],
])('%s password field', (_name, page) => {
  it('is hidden by default and can be shown and hidden again', () => {
    renderPage(page)
    const input = screen.getByLabelText('Password') as HTMLInputElement
    expect(input.type).toBe('password')

    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(input.type).toBe('text')

    const hide = screen.getByRole('button', { name: 'Hide password' })
    expect(hide.getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(hide)
    expect(input.type).toBe('password')
  })

  it('does not submit the form when toggled', () => {
    renderPage(page)
    expect(screen.getByRole('button', { name: 'Show password' }).getAttribute('type')).toBe('button')
  })
})
