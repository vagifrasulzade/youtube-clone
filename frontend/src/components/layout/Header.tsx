import { Link } from 'react-router'

import { CreateIcon, MenuIcon } from '../icons'
import { Logo } from '../ui/Logo'
import { SearchBox } from './SearchBox'
import { UserMenu } from './UserMenu'

interface HeaderProps {
  onToggleSidebar: () => void
}

export function Header({ onToggleSidebar }: HeaderProps) {
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
        <Link to="/" aria-label="Home" className="flex items-center">
          <Logo size={20} />
        </Link>
      </div>

      <SearchBox />

      <div className="flex shrink-0 items-center gap-2">
        <Link
          to="/upload"
          className="hidden items-center gap-1 rounded-full bg-yt-hover px-3 py-2 text-sm font-medium hover:bg-yt-active sm:flex"
        >
          <CreateIcon size={20} />
          Create
        </Link>
        <UserMenu />
      </div>
    </header>
  )
}
