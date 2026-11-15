import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router'

import { getJson } from '../api/http'
import type { components } from '../api/schema'
import { Avatar } from '../components/ui/Avatar'
import { durationLabel } from '../components/video/duration'

type Playlist = components['schemas']['PlaylistOut']
type Entry = components['schemas']['PlaylistEntry']

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function EntryRow({ entry, index }: { entry: Entry; index: number }) {
  const video = entry.video
  if (!video) {
    // The viewer may not watch this one (private/hidden): never show its real title.
    return (
      <div className="flex items-center gap-3 rounded-xl p-2 opacity-60">
        <span className="w-6 text-center text-sm text-yt-muted">{index + 1}</span>
        <div className="aspect-video w-40 shrink-0 rounded-lg bg-yt-hover" />
        <p className="text-sm">{entry.title}</p>
      </div>
    )
  }
  return (
    <Link to={`/watch?v=${video.id}`} className="flex items-center gap-3 rounded-xl p-2 hover:bg-yt-hover">
      <span className="w-6 text-center text-sm text-yt-muted">{index + 1}</span>
      <div className="relative aspect-video w-40 shrink-0 overflow-hidden rounded-lg bg-yt-hover">
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
        <h3 className="line-clamp-2 text-base font-medium">{video.title}</h3>
        <p className="truncate text-xs text-yt-muted">
          {video.channel.name} · {video.view_count.toLocaleString('en')} views
        </p>
      </div>
    </Link>
  )
}

export function PlaylistPage() {
  const [params] = useSearchParams()
  const id = params.get('list') ?? ''

  const playlist = useQuery({
    queryKey: ['playlist', id],
    queryFn: () => getJson<Playlist>(`/playlists/${id}`),
    enabled: UUID_RE.test(id),
    retry: false,
  })

  if (!UUID_RE.test(id) || playlist.isError) {
    return (
      <div className="py-32 text-center">
        <p className="text-xl font-medium">This playlist isn't available</p>
        <Link to="/" className="mt-4 inline-block rounded-full bg-yt-hover px-4 py-2 text-sm font-medium">
          Go to Home
        </Link>
      </div>
    )
  }
  if (playlist.isPending) return <div className="m-6 h-96 animate-pulse rounded-2xl bg-yt-hover" />

  const p = playlist.data
  const playable = p.entries.filter((e) => e.video)
  const cover = playable[0]?.video?.thumbnail_url

  return (
    <div className="mx-auto flex max-w-[1500px] flex-col gap-6 p-4 lg:flex-row lg:p-6">
      <section className="flex shrink-0 flex-col gap-4 rounded-2xl bg-gradient-to-b from-[#3d4a5c] to-[#1f2733] p-6 text-white lg:sticky lg:top-20 lg:h-fit lg:w-[360px]">
        <div className="aspect-video overflow-hidden rounded-xl bg-black/30">
          {cover && <img src={cover} alt="" className="size-full object-cover" />}
        </div>
        <h1 className="text-2xl font-bold">{p.title}</h1>
        <Link to={`/@${p.channel.handle}`} className="flex items-center gap-2 text-sm font-medium">
          <Avatar name={p.channel.name} url={p.channel.avatar_url} size={24} />
          {p.channel.name}
        </Link>
        <p className="text-xs text-white/70">
          {p.visibility === 'public' ? 'Public' : p.visibility === 'unlisted' ? 'Unlisted' : 'Private'}{' '}
          · {p.entries.length} videos
        </p>
        {p.description && <p className="whitespace-pre-wrap text-sm text-white/80">{p.description}</p>}
        {playable[0]?.video && (
          <Link
            to={`/watch?v=${playable[0].video.id}`}
            className="rounded-full bg-white py-2 text-center text-sm font-medium text-yt-text hover:bg-white/90"
          >
            Play all
          </Link>
        )}
      </section>

      <section className="min-w-0 flex-1">
        {p.entries.length === 0 && <p className="py-16 text-center text-yt-muted">No videos in this playlist yet.</p>}
        {p.entries.map((entry, index) => (
          <EntryRow key={entry.video?.id ?? `hidden-${entry.position}`} entry={entry} index={index} />
        ))}
      </section>
    </div>
  )
}
