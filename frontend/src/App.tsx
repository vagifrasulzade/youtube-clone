import { Link, Route, Routes } from 'react-router'

import { AppLayout } from './components/layout/AppLayout'
import { HomePage } from './pages/HomePage'

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
      <Route element={<AppLayout />}>
        <Route index element={<HomePage />} />
        <Route path="*" element={<NotBuiltYet />} />
      </Route>
    </Routes>
  )
}
