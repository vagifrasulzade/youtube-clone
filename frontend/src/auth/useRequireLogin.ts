import { useCallback } from 'react'
import { useLocation, useNavigate } from 'react-router'

import { useAuth } from './context'

/**
 * For buttons that need an account (like, subscribe, comment): returns `true` when the
 * user is signed in; otherwise sends them to sign in and back here afterwards.
 */
export function useRequireLogin(): () => boolean {
  const { user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  return useCallback(() => {
    if (user) return true
    navigate('/login', { state: { from: location.pathname + location.search } })
    return false
  }, [user, navigate, location.pathname, location.search])
}
