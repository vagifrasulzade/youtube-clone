import { Link } from 'react-router'

import type { components } from '../../api/schema'
import { Avatar } from '../ui/Avatar'
import { durationLabel } from './duration'

export type Video = components['schemas']['VideoCard']

export function VideoCard({ video }: { video: Video }) {
  const watch = `/watch?v=${video.id}`
  return (
    <article className="flex flex-col gap-3">
      <Link to={watch} className="relative block aspect-video overflow-hidden rounded-xl bg-yt-hover">
        {video.thumbnail_url && (
          <img
            src={video.thumbnail_url}
            alt=""
            loading="lazy"
            className="size-full object-cover transition-transform duration-300 hover:scale-105"
          />
        )}
        {video.duration_seconds != null && (
          <span className="absolute bottom-1.5 right-1.5 rounded bg-black/80 px-1 text-xs font-medium text-white">
            {durationLabel(video.duration_seconds)}
          </span>
        )}
      </Link>
      <div className="flex gap-3">
        <Link to={`/@${video.channel.handle}`} aria-label={video.channel.name}>
          <Avatar name={video.channel.name} url={video.channel.avatar_url} />
        </Link>
        <div className="min-w-0">
          <Link to={watch}>
            <h3 className="line-clamp-2 text-base font-medium leading-snug">{video.title}</h3>
          </Link>
          <Link
            to={`/@${video.channel.handle}`}
            className="mt-1 block truncate text-sm text-yt-muted hover:text-yt-text"
          >
            {video.channel.name}
          </Link>
          <p className="text-sm text-yt-muted">
            {video.view_count.toLocaleString('en')} views
            {video.published_at && (
              <> · {new Date(video.published_at).toLocaleDateString('en', { dateStyle: 'medium' })}</>
            )}
          </p>
        </div>
      </div>
    </article>
  )
}

export function VideoCardSkeleton() {
  return (
    <div className="flex animate-pulse flex-col gap-3" aria-hidden="true">
      <div className="aspect-video rounded-xl bg-yt-hover" />
      <div className="flex gap-3">
        <div className="size-9 rounded-full bg-yt-hover" />
        <div className="flex-1 space-y-2">
          <div className="h-4 w-11/12 rounded bg-yt-hover" />
          <div className="h-3 w-2/3 rounded bg-yt-hover" />
        </div>
      </div>
    </div>
  )
}
