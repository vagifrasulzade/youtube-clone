import { Link, Route, Routes } from 'react-router'

import { AppLayout } from './components/layout/AppLayout'
import { LoginPage, RegisterPage } from './pages/AuthPages'
import { ChannelPage } from './pages/ChannelPage'
import { HomePage } from './pages/HomePage'
import { PlaylistPage } from './pages/PlaylistPage'
import { SearchPage } from './pages/SearchPage'
import { WatchPage } from './pages/WatchPage'

function NotBuiltYet() {
  return (
    <div className="flex flex-col items-center gap-4 py-32 text-center">
      <p className="text-lg font-medium">This page isn't available yet</p>
      <Link to="/" className="rounded-full bg-yt-hover px-4 py-2 text-sm font-medium hover:bg-yt-active">
        Go to Home
      </Link>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="login" element={<LoginPage />} />
      <Route path="register" element={<RegisterPage />} />
      <Route element={<AppLayout />}>
        <Route index element={<HomePage />} />
        <Route path="watch" element={<WatchPage />} />
        <Route path="results" element={<SearchPage />} />
        <Route path="playlist" element={<PlaylistPage />} />
        {/* YouTube-style channel URLs: /@handle (validated inside the page). */}
        <Route path=":segment" element={<ChannelPage />} />
        <Route path="*" element={<NotBuiltYet />} />
      </Route>
    </Routes>
  )
}
