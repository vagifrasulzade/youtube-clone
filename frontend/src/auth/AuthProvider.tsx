import { useQueryClient } from '@tanstack/react-query'
import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'

import { getJson, postJson } from '../api/http'
import type { components } from '../api/schema'
import { AuthContext, type AuthState, type CurrentUser, type RegisterInput } from './context'
import { onSessionExpired, refreshAccessToken, setAccessToken } from './session'

type TokenResponse = components['schemas']['TokenResponse']

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<AuthState['status']>('loading')
  const [user, setUser] = useState<CurrentUser | null>(null)

  // Responses depend on who is asking (private videos, my_reaction, can_edit...):
  // after every sign-in or sign-out, refetch instead of showing another user's view.
  const startSession = useCallback(
    (session: TokenResponse | null) => {
      setAccessToken(session?.access_token ?? null)
      setUser(session?.user ?? null)
      void queryClient.resetQueries()
    },
    [queryClient],
  )

  useEffect(() => {
    let cancelled = false
    void (async () => {
      const token = await refreshAccessToken()
      const me = token ? await getJson<CurrentUser>('/auth/me').catch(() => null) : null
      if (cancelled) return
      setUser(me)
      setStatus('ready')
    })()
    const stop = onSessionExpired(() => setUser(null))
    return () => {
      cancelled = true
      stop()
    }
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      status,
      user,
      login: async (email, password) => {
        startSession(await postJson<TokenResponse>('/auth/login', { email, password }))
      },
      register: async (input: RegisterInput) => {
        startSession(await postJson<TokenResponse>('/auth/register', input))
      },
      logout: async () => {
        await postJson<void>('/auth/logout').catch(() => undefined) // signed out locally anyway
        startSession(null)
      },
    }),
    [status, user, startSession],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
