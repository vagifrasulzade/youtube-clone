import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router'

import { ErrorBoundary } from '../ErrorBoundary'
import { Header } from './Header'
import { MiniSidebar, Sidebar } from './Sidebar'

const WIDE = '(min-width: 1312px)'

/**
 * YouTube layout: fixed 56px header; on wide screens the guide toggles between the
 * full 240px sidebar and the 72px mini guide; on narrower screens the menu button
 * opens the full guide as an overlay drawer.
 */
export function AppLayout() {
  const [isWide, setIsWide] = useState(() => window.matchMedia(WIDE).matches)
  const [expanded, setExpanded] = useState(true)
  // The drawer remembers the page it was opened on, so navigating closes it.
  const [drawerPath, setDrawerPath] = useState<string | null>(null)
  const location = useLocation()
  const drawerOpen = drawerPath === location.pathname

  useEffect(() => {
    const query = window.matchMedia(WIDE)
    const onChange = () => setIsWide(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  const toggle = () =>
    isWide ? setExpanded((v) => !v) : setDrawerPath(drawerOpen ? null : location.pathname)
  const showFull = isWide && expanded

  return (
    <div className="min-h-screen">
      <Header onToggleSidebar={toggle} />

      <aside className="fixed bottom-0 left-0 top-14 z-20 hidden overflow-y-auto bg-yt-bg sm:block">
        {showFull ? <Sidebar /> : <MiniSidebar />}
      </aside>

      {drawerOpen && !isWide && (
        <div className="fixed inset-0 z-40" role="dialog" aria-modal="true">
          <button
            type="button"
            aria-label="Close guide"
            className="absolute inset-0 bg-black/50"
            onClick={() => setDrawerPath(null)}
          />
          <div className="absolute inset-y-0 left-0 bg-yt-bg pt-14 shadow-xl">
            <Sidebar />
          </div>
        </div>
      )}

      <main className={`pt-14 ${showFull ? 'sm:pl-60' : 'sm:pl-[72px]'}`}>
        <ErrorBoundary key={location.pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  )
}
