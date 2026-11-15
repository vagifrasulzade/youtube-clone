import { Link, Route, Routes } from 'react-router'

import { AppLayout } from './components/layout/AppLayout'
import { RequireAuth } from './auth/RequireAuth'
import { LoginPage, RegisterPage } from './pages/AuthPages'
import {
  HistoryPage,
  LikedPage,
  PlaylistsPage,
  SharedPage,
  SubscriptionsFeedPage,
} from './pages/LibraryPages'
import { ChannelPage } from './pages/ChannelPage'
import { HomePage } from './pages/HomePage'
import { PlaylistPage } from './pages/PlaylistPage'
import { SearchPage } from './pages/SearchPage'
import { AdminPage, ModerationPage } from './pages/StaffPages'
import { StudioPage, StudioVideoPage } from './pages/StudioPages'
import { UploadPage } from './pages/UploadPage'
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
        <Route path="upload" element={<RequireAuth><UploadPage /></RequireAuth>} />
        <Route path="studio" element={<RequireAuth><StudioPage /></RequireAuth>} />
        <Route path="studio/video/:id" element={<RequireAuth><StudioVideoPage /></RequireAuth>} />
        <Route path="feed/subscriptions" element={<RequireAuth><SubscriptionsFeedPage /></RequireAuth>} />
        <Route path="feed/history" element={<RequireAuth><HistoryPage /></RequireAuth>} />
        <Route path="feed/shared" element={<RequireAuth><SharedPage /></RequireAuth>} />
        <Route path="playlist/liked" element={<RequireAuth><LikedPage /></RequireAuth>} />
        <Route path="playlists" element={<RequireAuth><PlaylistsPage /></RequireAuth>} />
        <Route path="moderation" element={<RequireAuth role="moderator"><ModerationPage /></RequireAuth>} />
        <Route path="admin" element={<RequireAuth role="admin"><AdminPage /></RequireAuth>} />
        {/* YouTube-style channel URLs: /@handle (validated inside the page). */}
        <Route path=":segment" element={<ChannelPage />} />
        <Route path="*" element={<NotBuiltYet />} />
      </Route>
    </Routes>
  )
}
