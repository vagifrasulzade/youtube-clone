import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { getJson } from '../api/http'
import type { components } from '../api/schema'
import { PlaylistIcon } from '../components/icons'
import { Avatar } from '../components/ui/Avatar'
import { type Video, VideoCard, VideoCardSkeleton } from '../components/video/VideoCard'
import { SubscribeButton } from '../components/watch/WatchActions'
import { usePageTitle } from '../hooks/usePageTitle'

type Channel = components['schemas']['ChannelPageOut']
type PlaylistCard = components['schemas']['PlaylistCard']
type Sort = 'latest' | 'popular' | 'oldest'

interface VideoPage {
  items: Video[]
  next_cursor: string | null
}

function NotFound() {
  return (
    <div className="py-32 text-center">
      <p className="text-xl font-medium">This channel doesn't exist</p>
      <Link to="/" className="mt-4 inline-block rounded-full bg-yt-hover px-4 py-2 text-sm font-medium">
        Go to Home
      </Link>
    </div>
  )
}

function VideosTab({ handle }: { handle: string }) {
  const [sort, setSort] = useState<Sort>('latest')
  const videos = useInfiniteQuery({
    queryKey: ['channel-videos', handle, sort],
    queryFn: ({ pageParam }) =>
      getJson<VideoPage>(`/channels/${handle}/videos`, {
        sort,
        limit: '30',
        ...(pageParam ? { cursor: pageParam } : {}),
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  })
  const items = videos.data?.pages.flatMap((p) => p.items) ?? []

  return (
    <>
      <div className="mb-6 flex gap-3">
        {(['latest', 'popular', 'oldest'] as const).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setSort(value)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium capitalize ${
              sort === value ? 'bg-yt-text text-white' : 'bg-yt-hover hover:bg-yt-active'
            }`}
          >
            {value}
          </button>
        ))}
      </div>
      <div className="grid gap-x-4 gap-y-8 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        {items.map((video) => (
          <VideoCard key={video.id} video={video} />
        ))}
        {videos.isPending && Array.from({ length: 8 }, (_, i) => <VideoCardSkeleton key={i} />)}
      </div>
      {videos.isSuccess && items.length === 0 && (
        <p className="py-16 text-center text-yt-muted">This channel has no videos yet.</p>
      )}
      {videos.hasNextPage && (
        <div className="mt-8 text-center">
          <button
            type="button"
            onClick={() => void videos.fetchNextPage()}
            className="rounded-full bg-yt-hover px-4 py-2 text-sm font-medium hover:bg-yt-active"
          >
            Show more
          </button>
        </div>
      )}
    </>
  )
}

function PlaylistsTab({ handle }: { handle: string }) {
  const playlists = useQuery({
    queryKey: ['channel-playlists', handle],
    queryFn: () => getJson<PlaylistCard[]>(`/channels/${handle}/playlists`),
  })
  if (playlists.isSuccess && playlists.data.length === 0) {
    return <p className="py-16 text-center text-yt-muted">No playlists yet.</p>
  }
  return (
    <div className="grid gap-x-4 gap-y-8 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
      {playlists.data?.map((playlist) => (
        <Link key={playlist.id} to={`/playlist?list=${playlist.id}`} className="flex flex-col gap-2">
          <div className="relative aspect-video overflow-hidden rounded-xl bg-yt-hover">
            {playlist.thumbnail_url && (
              <img src={playlist.thumbnail_url} alt="" className="size-full object-cover" />
            )}
            <span className="absolute bottom-1.5 right-1.5 flex items-center gap-1 rounded bg-black/80 px-1.5 text-xs font-medium text-white">
              <PlaylistIcon size={14} />
              {playlist.video_count} videos
            </span>
          </div>
          <h3 className="font-medium">{playlist.title}</h3>
          <p className="text-sm text-yt-muted">View full playlist</p>
        </Link>
      ))}
    </div>
  )
}

export function ChannelPage() {
  const { segment = '' } = useParams()
  const handle = segment.startsWith('@') ? segment.slice(1).toLowerCase() : ''
  const [tab, setTab] = useState<'videos' | 'playlists'>('videos')
  const queryClient = useQueryClient()

  const channel = useQuery({
    queryKey: ['channel', handle],
    queryFn: () => getJson<Channel>(`/channels/${encodeURIComponent(handle)}`),
    enabled: handle.length >= 3,
    retry: false,
  })

  usePageTitle(channel.data?.name ?? null)

  if (!handle || channel.isError) return <NotFound />
  if (channel.isPending) return <div className="m-6 h-40 animate-pulse rounded-xl bg-yt-hover" />

  const c = channel.data
  return (
    <div className="mx-auto max-w-[1284px] px-4 py-4 sm:px-6">
      {c.banner_url && (
        <div className="aspect-[6.2/1] overflow-hidden rounded-xl bg-yt-hover">
          <img src={c.banner_url} alt="" className="size-full object-cover" />
        </div>
      )}

      <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-center">
        <Avatar name={c.name} url={c.avatar_url} size={160} />
        <div className="min-w-0">
          <h1 className="text-4xl font-bold">{c.name}</h1>
          <p className="mt-2 text-sm text-yt-muted">
            <span className="font-medium text-yt-text">@{c.handle}</span> ·{' '}
            {c.subscriber_count.toLocaleString('en')} subscribers · {c.video_count} videos
          </p>
          {c.description && <p className="mt-2 line-clamp-1 text-sm text-yt-muted">{c.description}</p>}
          <div className="mt-3">
            {c.is_owner ? (
              <Link to="/studio" className="rounded-full bg-yt-hover px-4 py-2 text-sm font-medium hover:bg-yt-active">
                Manage videos
              </Link>
            ) : (
              <SubscribeButton
                handle={c.handle}
                subscribed={c.is_subscribed}
                onChange={(state) =>
                  queryClient.setQueryData<Channel>(['channel', handle], (old) =>
                    old && { ...old, is_subscribed: state.subscribed, subscriber_count: state.subscriber_count },
                  )
                }
              />
            )}
          </div>
        </div>
      </div>

      <div role="tablist" className="mt-4 flex gap-6 border-b border-yt-border">
        {(['videos', 'playlists'] as const).map((value) => (
          <button
            key={value}
            role="tab"
            type="button"
            aria-selected={tab === value}
            onClick={() => setTab(value)}
            className={`pb-3 text-base font-medium capitalize ${
              tab === value ? 'border-b-2 border-yt-text' : 'text-yt-muted hover:text-yt-text'
            }`}
          >
            {value}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {tab === 'videos' ? <VideosTab handle={c.handle} /> : <PlaylistsTab handle={c.handle} />}
      </div>
    </div>
  )
}
