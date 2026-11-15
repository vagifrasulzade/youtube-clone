import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { Link } from 'react-router'

import { describeError, getJson, request } from '../api/http'
import type { components } from '../api/schema'
import { PlaylistIcon } from '../components/icons'
import { type Video, VideoCard, VideoCardSkeleton } from '../components/video/VideoCard'
import { usePageTitle } from '../hooks/usePageTitle'

type PlaylistCard = components['schemas']['PlaylistCard']
type Visibility = components['schemas']['Visibility']

const GRID = 'grid gap-x-4 gap-y-10 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4'

function VideoGrid({ title, videos, pending, empty }: { title: string; videos?: Video[]; pending: boolean; empty: string }) {
  return (
    <div className="px-4 py-6 sm:px-6">
      <h1 className="mb-6 text-2xl font-bold">{title}</h1>
      <div className={GRID}>
        {videos?.map((video) => <VideoCard key={video.id} video={video} />)}
        {pending && Array.from({ length: 8 }, (_, i) => <VideoCardSkeleton key={i} />)}
      </div>
      {!pending && videos?.length === 0 && <p className="py-16 text-center text-yt-muted">{empty}</p>}
    </div>
  )
}

export function SubscriptionsFeedPage() {
  usePageTitle('Subscriptions')
  const feed = useInfiniteQuery({
    queryKey: ['feed', 'subscriptions'],
    queryFn: ({ pageParam }) =>
      getJson<{ items: Video[]; next_cursor: string | null }>('/me/feed/subscriptions', {
        limit: '24',
        cursor: pageParam ?? undefined,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  })
  return (
    <>
      <VideoGrid
        title="Latest from your subscriptions"
        videos={feed.data?.pages.flatMap((p) => p.items)}
        pending={feed.isPending}
        empty="Subscribe to channels to see their newest videos here."
      />
      {feed.hasNextPage && (
        <div className="pb-8 text-center">
          <button type="button" onClick={() => void feed.fetchNextPage()} className="rounded-full bg-yt-hover px-4 py-2 text-sm font-medium">
            Show more
          </button>
        </div>
      )}
    </>
  )
}

export function HistoryPage() {
  usePageTitle('Watch history')
  const queryClient = useQueryClient()
  const history = useQuery({ queryKey: ['history'], queryFn: () => getJson<Video[]>('/me/history') })
  const clear = useMutation({
    mutationFn: () => request('/me/history', { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['history'] }),
  })
  return (
    <div>
      <VideoGrid title="Watch history" videos={history.data} pending={history.isPending} empty="Videos you watch appear here." />
      {Boolean(history.data?.length) && (
        <div className="px-6 pb-8">
          <button
            type="button"
            disabled={clear.isPending}
            onClick={() => window.confirm('Clear all watch history?') && clear.mutate()}
            className="rounded-full bg-yt-hover px-4 py-2 text-sm font-medium hover:bg-yt-active"
          >
            Clear all watch history
          </button>
        </div>
      )}
    </div>
  )
}

export function LikedPage() {
  usePageTitle('Liked videos')
  const liked = useQuery({ queryKey: ['liked'], queryFn: () => getJson<Video[]>('/me/liked') })
  return <VideoGrid title="Liked videos" videos={liked.data} pending={liked.isPending} empty="Videos you like appear here." />
}

export function SharedPage() {
  usePageTitle('Shared with you')
  const shared = useQuery({ queryKey: ['shared'], queryFn: () => getJson<Video[]>('/me/shared') })
  return (
    <VideoGrid
      title="Shared with you"
      videos={shared.data}
      pending={shared.isPending}
      empty="Private videos that others share with you appear here."
    />
  )
}

export function PlaylistsPage() {
  usePageTitle('Playlists')
  const queryClient = useQueryClient()
  const playlists = useQuery({ queryKey: ['my-playlists'], queryFn: () => getJson<PlaylistCard[]>('/me/playlists') })
  const [title, setTitle] = useState('')
  const [visibility, setVisibility] = useState<Visibility>('private')
  const create = useMutation({
    mutationFn: () => request('/playlists', { method: 'POST', json: { title, visibility } }),
    onSuccess: () => {
      setTitle('')
      return queryClient.invalidateQueries({ queryKey: ['my-playlists'] })
    },
  })
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (title.trim()) create.mutate()
  }

  return (
    <div className="px-4 py-6 sm:px-6">
      <h1 className="mb-4 text-2xl font-bold">Playlists</h1>
      <form onSubmit={submit} className="mb-8 flex flex-wrap items-center gap-2">
        <input
          value={title}
          maxLength={150}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="New playlist title"
          className="w-72 rounded-full border border-yt-border px-4 py-2 text-sm outline-none focus:border-yt-blue"
        />
        <select
          value={visibility}
          onChange={(event) => setVisibility(event.target.value as Visibility)}
          className="rounded-full border border-yt-border px-3 py-2 text-sm"
        >
          <option value="private">Private</option>
          <option value="unlisted">Unlisted</option>
          <option value="public">Public</option>
        </select>
        <button type="submit" disabled={create.isPending} className="rounded-full bg-yt-text px-4 py-2 text-sm font-medium text-white">
          Create
        </button>
        {create.error && <span className="text-sm text-[#c5221f]">{describeError(create.error)}</span>}
      </form>
      <div className={GRID}>
        {playlists.data?.map((playlist) => (
          <Link key={playlist.id} to={`/playlist?list=${playlist.id}`} className="flex flex-col gap-2">
            <div className="relative aspect-video overflow-hidden rounded-xl bg-yt-hover">
              {playlist.thumbnail_url && <img src={playlist.thumbnail_url} alt="" className="size-full object-cover" />}
              <span className="absolute bottom-1.5 right-1.5 flex items-center gap-1 rounded bg-black/80 px-1.5 text-xs font-medium text-white">
                <PlaylistIcon size={14} />
                {playlist.video_count} videos
              </span>
            </div>
            <h3 className="font-medium">{playlist.title}</h3>
            <p className="text-sm capitalize text-yt-muted">{playlist.visibility} · View full playlist</p>
          </Link>
        ))}
      </div>
      {playlists.isSuccess && playlists.data.length === 0 && (
        <p className="py-16 text-center text-yt-muted">Create a playlist, then save videos to it from the watch page.</p>
      )}
    </div>
  )
}
