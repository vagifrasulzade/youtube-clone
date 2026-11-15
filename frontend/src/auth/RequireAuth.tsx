import type { ReactNode } from 'react'
import { Link, Navigate, useLocation } from 'react-router'

import { hasRole, type Role, useAuth } from './context'

/**
 * Route guard for pages that need an account (and optionally a role). This only decides
 * what to SHOW: the API checks every request itself and answers 401/403/404.
 */
export function RequireAuth({ role, children }: { role?: Role; children: ReactNode }) {
  const { status, user } = useAuth()
  const location = useLocation()

  if (status === 'loading') return <div className="m-6 h-40 animate-pulse rounded-xl bg-yt-hover" />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  if (role && !hasRole(user, role)) {
    return (
      <div className="flex flex-col items-center gap-3 py-32 text-center">
        <p className="text-xl font-medium">You don't have access to this page</p>
        <Link to="/" className="rounded-full bg-yt-hover px-4 py-2 text-sm font-medium">
          Go to Home
        </Link>
      </div>
    )
  }
  return children
}
