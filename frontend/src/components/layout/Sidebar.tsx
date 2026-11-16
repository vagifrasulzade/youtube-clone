import type { ComponentType } from 'react'
import { NavLink } from 'react-router'

import { hasRole, useAuth } from '../../auth/context'

import {
  ChannelIcon,
  HistoryIcon,
  HomeIcon,
  LikeIcon,
  PlaylistIcon,
  ShieldIcon,
  SubscriptionsIcon,
} from '../icons'

interface NavItem {
  to: string
  label: string
  icon: ComponentType<{ size?: number }>
}

const MAIN: NavItem[] = [
  { to: '/', label: 'Home', icon: HomeIcon },
  { to: '/feed/subscriptions', label: 'Subscriptions', icon: SubscriptionsIcon },
]

const YOU: NavItem[] = [
  { to: '/feed/history', label: 'History', icon: HistoryIcon },
  { to: '/playlists', label: 'Playlists', icon: PlaylistIcon },
  { to: '/studio', label: 'Your videos', icon: ChannelIcon },
  { to: '/playlist/liked', label: 'Liked videos', icon: LikeIcon },
  { to: '/feed/shared', label: 'Shared with you', icon: SubscriptionsIcon },
]

const MODERATION: NavItem = { to: '/moderation', label: 'Moderation', icon: ShieldIcon }
const ADMIN: NavItem = { to: '/admin', label: 'Admin', icon: ShieldIcon }

function rowClass({ isActive }: { isActive: boolean }) {
  return `flex h-10 items-center gap-6 rounded-lg px-3 text-sm ${
    isActive ? 'bg-yt-hover font-medium' : 'hover:bg-yt-hover'
  }`
}

function Section({ title, items }: { title?: string; items: NavItem[] }) {
  return (
    <div className="border-b border-yt-border/60 py-3">
      {title && <h3 className="px-3 pb-1 text-base font-medium">{title}</h3>}
      {items.map(({ to, label, icon: IconComponent }) => (
        <NavLink key={to} to={to} end className={rowClass}>
          <IconComponent size={22} />
          <span className="truncate">{label}</span>
        </NavLink>
      ))}
    </div>
  )
}

/** Full 240px guide (desktop expanded, and the mobile drawer). */
export function Sidebar() {
  const { user } = useAuth()
  // Shown by role as a convenience only; the API enforces access on every request.
  const staff = [
    ...(hasRole(user, 'moderator') ? [MODERATION] : []),
    ...(hasRole(user, 'admin') ? [ADMIN] : []),
  ]
  return (
    <nav aria-label="Guide" className="w-60 overflow-y-auto px-3">
      <Section items={MAIN} />
      <Section title="You" items={YOU} />
      {staff.length > 0 && <Section items={staff} />}
      <p className="px-3 py-4 text-xs text-yt-muted">
        YouTube Clone: a demo project, not affiliated with YouTube or Google.
      </p>
    </nav>
  )
}

/** Collapsed 72px guide: icon above a tiny label. */
export function MiniSidebar() {
  const items = [MAIN[0], MAIN[1], YOU[0], YOU[2]]
  return (
    <nav aria-label="Guide" className="w-[72px] px-1 pt-1">
      {items.map(({ to, label, icon: IconComponent }) => (
        <NavLink
          key={to}
          to={to}
          end
          className={({ isActive }) =>
            `flex flex-col items-center gap-1 rounded-lg py-4 text-[10px] hover:bg-yt-hover ${
              isActive ? 'font-medium' : ''
            }`
          }
        >
          <IconComponent size={22} />
          {label === 'Your videos' ? 'You' : label}
        </NavLink>
      ))}
    </nav>
  )
}
