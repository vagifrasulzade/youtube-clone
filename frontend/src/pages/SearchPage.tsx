import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router'

import { getJson } from '../api/http'
import { Avatar } from '../components/ui/Avatar'
import type { Video } from '../components/video/VideoCard'
import { durationLabel } from '../components/video/duration'

interface SearchPage {
  items: Video[]
  total: number
  page: number
  page_size: number
}

const SORTS = [
  { value: 'relevance', label: 'Relevance' },
  { value: 'date', label: 'Upload date' },
  { value: 'views', label: 'View count' },
] as const
const PAGE_SIZE = 20

function ResultRow({ video }: { video: Video }) {
  const watch = `/watch?v=${video.id}`
  return (
    <div className="flex flex-col gap-4 sm:flex-row">
      <Link
        to={watch}
        className="relative aspect-video w-full shrink-0 overflow-hidden rounded-xl bg-yt-hover sm:w-[360px]"
      >
        {video.thumbnail_url && (
          <img src={video.thumbnail_url} alt="" loading="lazy" className="size-full object-cover" />
        )}
        {video.duration_seconds != null && (
          <span className="absolute bottom-1.5 right-1.5 rounded bg-black/80 px-1 text-xs font-medium text-white">
            {durationLabel(video.duration_seconds)}
          </span>
        )}
      </Link>
      <div className="min-w-0">
        <Link to={watch}>
          <h3 className="line-clamp-2 text-lg leading-6">{video.title}</h3>
        </Link>
        <p className="text-xs text-yt-muted">
          {video.view_count.toLocaleString('en')} views
          {video.published_at &&
            ` · ${new Date(video.published_at).toLocaleDateString('en', { dateStyle: 'medium' })}`}
        </p>
        <Link to={`/@${video.channel.handle}`} className="my-3 flex items-center gap-2 text-xs text-yt-muted">
          <Avatar name={video.channel.name} url={video.channel.avatar_url} size={24} />
          {video.channel.name}
        </Link>
      </div>
    </div>
  )
}

export function SearchPage() {
  const [params, setParams] = useSearchParams()
  const q = (params.get('search_query') ?? '').trim()
  const sort = params.get('sort') ?? 'relevance'
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1)

  const results = useQuery({
    queryKey: ['search', q, sort, page],
    queryFn: () =>
      getJson<SearchPage>('/search', {
        q,
        sort,
        page: String(page),
        page_size: String(PAGE_SIZE),
      }),
    enabled: q.length > 0,
    placeholderData: keepPreviousData,
  })

  const update = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params)
    Object.entries(changes).forEach(([key, value]) => next.set(key, value))
    setParams(next)
  }
  const pages = results.data ? Math.ceil(results.data.total / PAGE_SIZE) : 0

  if (!q) return <p className="py-24 text-center text-yt-muted">Type something to search.</p>

  return (
    <div className="mx-auto max-w-[1100px] px-4 py-6">
      <div className="mb-6 flex gap-3">
        {SORTS.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => update({ sort: option.value, page: '1' })}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
              sort === option.value ? 'bg-yt-text text-white' : 'bg-yt-hover hover:bg-yt-active'
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {results.isError && <p role="alert">Search failed. Please try again.</p>}
      {results.isPending && <p className="text-yt-muted">Searching…</p>}
      {results.data && results.data.items.length === 0 && (
        <div className="py-20 text-center">
          <p className="text-lg font-medium">No results found</p>
          <p className="text-yt-muted">Try different keywords.</p>
        </div>
      )}

      <div className="flex flex-col gap-4">
        {results.data?.items.map((video) => <ResultRow key={video.id} video={video} />)}
      </div>

      {pages > 1 && (
        <nav aria-label="Pages" className="mt-8 flex justify-center gap-2">
          {Array.from({ length: Math.min(pages, 10) }, (_, i) => i + 1).map((n) => (
            <button
              key={n}
              type="button"
              aria-current={n === page ? 'page' : undefined}
              onClick={() => update({ page: String(n) })}
              className={`size-9 rounded-full text-sm ${n === page ? 'bg-yt-text text-white' : 'hover:bg-yt-hover'}`}
            >
              {n}
            </button>
          ))}
        </nav>
      )}
    </div>
  )
}
