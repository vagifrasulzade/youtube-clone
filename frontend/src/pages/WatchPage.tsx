import { useQuery } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { HttpError, getJson, postJson } from '../api/http'
import type { components } from '../api/schema'
import { LikeIcon } from '../components/icons'
import { Avatar } from '../components/ui/Avatar'
import type { Video } from '../components/video/VideoCard'
import { durationLabel } from '../components/video/duration'

type VideoDetail = components['schemas']['VideoDetailOut']

function Unavailable() {
  return (
    <div className="flex flex-col items-center gap-3 py-32 text-center">
      <p className="text-xl font-medium">This video isn't available</p>
      <p className="text-yt-muted">It may be private, removed or the link is wrong.</p>
      <Link to="/" className="mt-2 rounded-full bg-yt-hover px-4 py-2 text-sm font-medium">
        Go to Home
      </Link>
    </div>
  )
}

function RelatedItem({ video }: { video: Video }) {
  return (
    <Link to={`/watch?v=${video.id}`} className="flex gap-2">
      <div className="relative aspect-video w-[168px] shrink-0 overflow-hidden rounded-lg bg-yt-hover">
        {video.thumbnail_url && (
          <img src={video.thumbnail_url} alt="" loading="lazy" className="size-full object-cover" />
        )}
        {video.duration_seconds != null && (
          <span className="absolute bottom-1 right-1 rounded bg-black/80 px-1 text-xs text-white">
            {durationLabel(video.duration_seconds)}
          </span>
        )}
      </div>
      <div className="min-w-0">
        <h4 className="line-clamp-2 text-sm font-medium leading-snug">{video.title}</h4>
        <p className="mt-1 truncate text-xs text-yt-muted">{video.channel.name}</p>
        <p className="text-xs text-yt-muted">{video.view_count.toLocaleString('en')} views</p>
      </div>
    </Link>
  )
}

function Description({ video }: { video: VideoDetail }) {
  const [open, setOpen] = useState(false)
  const date = video.published_at
    ? new Date(video.published_at).toLocaleDateString('en', { dateStyle: 'medium' })
    : ''
  return (
    <div className="mt-3 rounded-xl bg-yt-hover p-3 text-sm">
      <p className="font-medium">
        {video.view_count.toLocaleString('en')} views {date && `· ${date}`}
      </p>
      <p className={`mt-1 whitespace-pre-wrap break-words ${open ? '' : 'line-clamp-2'}`}>
        {video.description || 'No description.'}
      </p>
      {video.description.length > 120 && (
        <button type="button" onClick={() => setOpen((v) => !v)} className="mt-1 font-medium">
          {open ? 'Show less' : '...more'}
        </button>
      )}
    </div>
  )
}

export function WatchPage() {
  const [params] = useSearchParams()
  const id = params.get('v') ?? ''
  const counted = useRef<string | null>(null)

  const detail = useQuery({
    queryKey: ['video', id],
    queryFn: () => getJson<VideoDetail>(`/videos/${encodeURIComponent(id)}`),
    enabled: id.length === 11,
    retry: (count, error) => !(error instanceof HttpError && error.status === 404) && count < 1,
  })
  const related = useQuery({
    queryKey: ['related', id],
    queryFn: () => getJson<Video[]>(`/videos/${encodeURIComponent(id)}/related`, { limit: '20' }),
    enabled: detail.isSuccess,
  })

  if (id.length !== 11 || detail.isError) return <Unavailable />
  if (detail.isPending) {
    return (
      <div className="mx-auto max-w-[1280px] p-6">
        <div className="aspect-video animate-pulse rounded-xl bg-yt-hover" />
      </div>
    )
  }

  const video = detail.data
  const countView = () => {
    if (counted.current === video.id) return
    counted.current = video.id
    void postJson(`/videos/${video.id}/views`).catch(() => undefined)
  }

  return (
    <div className="mx-auto flex max-w-[1750px] flex-col gap-6 px-4 py-6 lg:flex-row lg:px-6">
      <section className="min-w-0 flex-1">
        <div className="aspect-video overflow-hidden rounded-xl bg-black">
          {video.stream_url ? (
            <video
              key={video.id}
              src={video.stream_url}
              poster={video.thumbnail_url ?? undefined}
              controls
              autoPlay
              playsInline
              onPlaying={countView}
              className="size-full"
            />
          ) : (
            <p className="flex size-full items-center justify-center text-white">
              This video is still processing.
            </p>
          )}
        </div>

        <h1 className="mt-3 text-xl font-bold leading-7">{video.title}</h1>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Link to={`/@${video.channel.handle}`}>
              <Avatar name={video.channel.name} url={video.channel.avatar_url} size={40} />
            </Link>
            <div>
              <Link to={`/@${video.channel.handle}`} className="font-medium">
                {video.channel.name}
              </Link>
              <p className="text-xs text-yt-muted">
                {video.channel.subscriber_count.toLocaleString('en')} subscribers
              </p>
            </div>
            <Link
              to="/login"
              className="ml-3 rounded-full bg-yt-text px-4 py-2 text-sm font-medium text-white hover:bg-[#272727]"
            >
              Subscribe
            </Link>
          </div>

          <div className="flex items-center rounded-full bg-yt-hover text-sm font-medium">
            <Link to="/login" className="flex items-center gap-2 rounded-l-full px-4 py-2 hover:bg-yt-active">
              <LikeIcon size={20} />
              {video.like_count.toLocaleString('en')}
            </Link>
            <span className="h-6 w-px bg-yt-border" />
            <Link to="/login" aria-label="Dislike" className="rounded-r-full px-4 py-2 hover:bg-yt-active">
              <LikeIcon size={20} className="rotate-180" />
            </Link>
          </div>
        </div>

        <Description video={video} />

        <h2 className="mt-6 text-xl font-bold">{video.comment_count.toLocaleString('en')} Comments</h2>
      </section>

      <aside className="flex w-full flex-col gap-3 lg:w-[402px] lg:shrink-0">
        {related.data?.map((item) => <RelatedItem key={item.id} video={item} />)}
        {related.isPending &&
          Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="flex animate-pulse gap-2">
              <div className="aspect-video w-[168px] rounded-lg bg-yt-hover" />
              <div className="flex-1 space-y-2">
                <div className="h-3 rounded bg-yt-hover" />
                <div className="h-3 w-1/2 rounded bg-yt-hover" />
              </div>
            </div>
          ))}
      </aside>
    </div>
  )
}
