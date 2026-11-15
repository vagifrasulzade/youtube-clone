import { createContext, useContext } from 'react'

import type { components } from '../api/schema'

export type CurrentUser = components['schemas']['CurrentUserOut']
export type Role = CurrentUser['role']
export type RegisterInput = components['schemas']['RegisterRequest']

export interface AuthState {
  /** `loading` until the start-up refresh has answered; then `ready`. */
  status: 'loading' | 'ready'
  user: CurrentUser | null
  login: (email: string, password: string) => Promise<void>
  register: (input: RegisterInput) => Promise<void>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth must be used inside <AuthProvider>')
  return auth
}

const LEVEL: Record<Role, number> = { user: 1, moderator: 2, admin: 3 }

/** UI hint only: every permission is enforced by the API. */
export function hasRole(user: CurrentUser | null, minimum: Role): boolean {
  return user !== null && LEVEL[user.role] >= LEVEL[minimum]
}
