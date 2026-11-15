import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { CreateIcon, MenuIcon, PlayBadge, SearchIcon, UserIcon } from '../icons'

interface HeaderProps {
  onToggleSidebar: () => void
}

export function Header({ onToggleSidebar }: HeaderProps) {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [query, setQuery] = useState(params.get('search_query') ?? '')

  function submit(event: FormEvent) {
    event.preventDefault()
    const q = query.trim()
    if (q) navigate(`/results?search_query=${encodeURIComponent(q)}`)
  }

  return (
    <header className="fixed inset-x-0 top-0 z-30 flex h-14 items-center justify-between gap-4 bg-yt-bg px-4">
      <div className="flex shrink-0 items-center gap-4">
        <button
          type="button"
          onClick={onToggleSidebar}
          aria-label="Toggle guide"
          className="rounded-full p-2 hover:bg-yt-hover"
        >
          <MenuIcon />
        </button>
        <Link to="/" aria-label="Home" className="flex items-center gap-1">
          <PlayBadge size={20} />
          <span className="text-xl font-bold tracking-tighter">TubeClone</span>
        </Link>
      </div>

      <form onSubmit={submit} role="search" className="flex max-w-[640px] flex-1 items-center">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search"
          aria-label="Search"
          maxLength={100}
          className="h-10 w-full min-w-0 rounded-l-full border border-yt-border px-4 text-base outline-none focus:border-yt-blue"
        />
        <button
          type="submit"
          aria-label="Search"
          className="flex h-10 w-16 shrink-0 items-center justify-center rounded-r-full border border-l-0 border-yt-border bg-[#f8f8f8] hover:bg-yt-active"
        >
          <SearchIcon size={22} />
        </button>
      </form>

      <div className="flex shrink-0 items-center gap-2">
        <Link
          to="/upload"
          className="hidden items-center gap-1 rounded-full bg-yt-hover px-3 py-2 text-sm font-medium hover:bg-yt-active sm:flex"
        >
          <CreateIcon size={20} />
          Create
        </Link>
        <Link
          to="/login"
          className="flex items-center gap-2 rounded-full border border-yt-border px-3 py-1.5 text-sm font-medium text-yt-blue hover:bg-[#def1ff]"
        >
          <UserIcon size={22} />
          Sign in
        </Link>
      </div>
    </header>
  )
}
