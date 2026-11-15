import { useInfiniteQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'

import { type Video, VideoCard, VideoCardSkeleton } from '../components/video/VideoCard'
import { usePageTitle } from '../hooks/usePageTitle'

interface FeedPage {
  items: Video[]
  next_cursor: string | null
}

async function fetchFeed(cursor: string | null): Promise<FeedPage> {
  const params = new URLSearchParams({ limit: '24' })
  if (cursor) params.set('cursor', cursor)
  const response = await fetch(`/api/v1/videos?${params}`)
  if (!response.ok) throw new Error(`Feed request failed (${response.status})`)
  return response.json()
}

const GRID = 'grid gap-x-4 gap-y-10 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 min-[2200px]:grid-cols-5'

export function HomePage() {
  usePageTitle(null)
  const feed = useInfiniteQuery({
    queryKey: ['feed', 'home'],
    queryFn: ({ pageParam }) => fetchFeed(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  })
  const sentinel = useRef<HTMLDivElement>(null)

  // Infinite scroll: load the next page when the sentinel scrolls into view.
  useEffect(() => {
    const node = sentinel.current
    if (!node) return
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && feed.hasNextPage && !feed.isFetchingNextPage) {
        void feed.fetchNextPage()
      }
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [feed])

  const videos = feed.data?.pages.flatMap((page) => page.items) ?? []

  return (
    <div className="px-4 pb-10 pt-6 sm:px-6">
      <div className="mb-6 flex gap-3 overflow-x-auto">
        {['All', 'Recently uploaded'].map((chip, index) => (
          <span
            key={chip}
            className={`shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium ${
              index === 0 ? 'bg-yt-text text-white' : 'bg-yt-hover'
            }`}
          >
            {chip}
          </span>
        ))}
      </div>

      {feed.isError && (
        <div role="alert" className="py-24 text-center">
          <p className="text-lg font-medium">Something went wrong</p>
          <button
            type="button"
            onClick={() => void feed.refetch()}
            className="mt-4 rounded-full bg-yt-hover px-4 py-2 text-sm font-medium hover:bg-yt-active"
          >
            Try again
          </button>
        </div>
      )}

      {!feed.isError && (
        <div className={GRID}>
          {videos.map((video) => (
            <VideoCard key={video.id} video={video} />
          ))}
          {(feed.isPending || feed.isFetchingNextPage) &&
            Array.from({ length: 8 }, (_, i) => <VideoCardSkeleton key={`s${i}`} />)}
        </div>
      )}

      {feed.isSuccess && videos.length === 0 && (
        <p className="py-24 text-center text-yt-muted">No videos yet. Be the first to upload one!</p>
      )}

      <div ref={sentinel} className="h-px" />
    </div>
  )
}
