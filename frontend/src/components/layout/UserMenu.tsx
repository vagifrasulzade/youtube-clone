import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'

import { hasRole, useAuth } from '../../auth/context'
import { ChannelIcon, ShieldIcon, UserIcon } from '../icons'
import { Avatar } from '../ui/Avatar'

export function UserMenu() {
  const { status, user, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (!box.current?.contains(event.target as Node)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => event.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  if (status === 'loading') return <div className="size-8 rounded-full bg-yt-hover" aria-hidden="true" />

  if (!user) {
    return (
      <Link
        to="/login"
        state={{ from: location.pathname + location.search }}
        className="flex items-center gap-2 rounded-full border border-yt-border px-3 py-1.5 text-sm font-medium text-yt-blue hover:bg-[#def1ff]"
      >
        <UserIcon size={22} />
        Sign in
      </Link>
    )
  }

  const item = 'flex items-center gap-4 px-4 py-2 text-sm hover:bg-yt-hover'
  const go = () => setOpen(false)

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        aria-label="Account menu"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="rounded-full"
      >
        <Avatar name={user.channel.name} url={user.channel.avatar_url} size={32} />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-11 w-72 overflow-hidden rounded-xl bg-white py-2 shadow-[0_4px_32px_rgba(0,0,0,0.1)]"
        >
          <div className="flex gap-4 border-b border-yt-border px-4 pt-2 pb-4">
            <Avatar name={user.channel.name} url={user.channel.avatar_url} size={40} />
            <div className="min-w-0">
              <p className="truncate font-medium">{user.channel.name}</p>
              <p className="truncate text-sm">@{user.channel.handle}</p>
            </div>
          </div>
          <Link role="menuitem" to={`/@${user.channel.handle}`} onClick={go} className={item}>
            <ChannelIcon /> Your channel
          </Link>
          <Link role="menuitem" to="/studio" onClick={go} className={item}>
            <ChannelIcon /> Studio
          </Link>
          {hasRole(user, 'moderator') && (
            <Link role="menuitem" to="/moderation" onClick={go} className={item}>
              <ShieldIcon /> Moderation
            </Link>
          )}
          {hasRole(user, 'admin') && (
            <Link role="menuitem" to="/admin" onClick={go} className={item}>
              <ShieldIcon /> Admin
            </Link>
          )}
          <button
            type="button"
            role="menuitem"
            onClick={async () => {
              setOpen(false)
              await logout()
              navigate('/')
            }}
            className={`${item} w-full border-t border-yt-border`}
          >
            <UserIcon /> Sign out
          </button>
        </div>
      )}
    </div>
  )
}
