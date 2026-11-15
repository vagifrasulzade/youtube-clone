import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'

import { describeError, getJson, request } from '../api/http'
import type { components } from '../api/schema'
import { durationLabel } from '../components/video/duration'
import { usePageTitle } from '../hooks/usePageTitle'

type StudioVideo = components['schemas']['VideoOwnerOut']
type StudioPage = components['schemas']['NumberedPage_VideoOwnerOut_']
type VideoDetail = components['schemas']['VideoDetailOut']
type Grant = components['schemas']['GrantOut']
type Visibility = components['schemas']['Visibility']
type Thumb = 'auto_1' | 'auto_2' | 'auto_3' | 'custom'

const STATUS_LABEL: Record<StudioVideo['status'], string> = {
  awaiting_upload: 'Upload not finished',
  queued: 'Queued',
  processing: 'Processing',
  ready: 'Ready',
  failed: 'Failed',
}

function Badge({ children, tone = 'gray' }: { children: string; tone?: 'gray' | 'red' }) {
  const color = tone === 'red' ? 'bg-[#fce8e6] text-[#c5221f]' : 'bg-yt-hover text-yt-muted'
  return <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${color}`}>{children}</span>
}

// --- list ------------------------------------------------------------------------------

export function StudioPage() {
  usePageTitle('Channel content')
  const [params, setParams] = useSearchParams()
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1)
  const q = params.get('q') ?? ''
  const [search, setSearch] = useState(q)

  const videos = useQuery({
    queryKey: ['studio', q, page],
    queryFn: () => getJson<StudioPage>('/studio/videos', { q, page: String(page), page_size: '20' }),
    // Videos that are still being processed change on their own: keep the list fresh.
    refetchInterval: (query) =>
      query.state.data?.items.some((v) => v.status === 'queued' || v.status === 'processing') ? 3000 : false,
  })
  const pages = videos.data ? Math.max(1, Math.ceil(videos.data.total / videos.data.page_size)) : 1

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Channel content</h1>
        <div className="flex gap-2">
          <form
            onSubmit={(event) => {
              event.preventDefault()
              setParams(search ? { q: search } : {})
            }}
          >
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Filter videos by title"
              placeholder="Filter by title"
              maxLength={100}
              className="rounded-full border border-yt-border px-4 py-2 text-sm outline-none focus:border-yt-blue"
            />
          </form>
          <Link to="/upload" className="rounded-full bg-yt-text px-4 py-2 text-sm font-medium text-white">
            Upload
          </Link>
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-yt-border">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="border-b border-yt-border text-xs text-yt-muted">
            <tr>
              <th className="p-3 font-medium">Video</th>
              <th className="p-3 font-medium">Visibility</th>
              <th className="p-3 font-medium">Status</th>
              <th className="p-3 font-medium">Date</th>
              <th className="p-3 text-right font-medium">Views</th>
              <th className="p-3 text-right font-medium">Comments</th>
              <th className="p-3 text-right font-medium">Likes</th>
            </tr>
          </thead>
          <tbody>
            {videos.data?.items.map((video) => (
              <tr key={video.id} className="border-b border-yt-border last:border-0 hover:bg-yt-hover/50">
                <td className="p-3">
                  <Link to={`/studio/video/${video.id}`} className="font-medium hover:underline">
                    {video.title}
                  </Link>
                  <p className="text-xs text-yt-muted">
                    {video.duration_seconds != null && durationLabel(video.duration_seconds)}
                    {video.original_filename && ` · ${video.original_filename}`}
                  </p>
                </td>
                <td className="p-3 capitalize">{video.visibility}</td>
                <td className="p-3">
                  <div className="flex flex-wrap items-center gap-1">
                    <Badge tone={video.status === 'failed' ? 'red' : 'gray'}>{STATUS_LABEL[video.status]}</Badge>
                    {video.is_hidden && <Badge tone="red">Hidden by moderators</Badge>}
                  </div>
                  {video.processing_error && <p className="mt-1 text-xs text-[#c5221f]">{video.processing_error}</p>}
                </td>
                <td className="p-3 text-yt-muted">
                  {new Date(video.published_at ?? video.created_at).toLocaleDateString('en', { dateStyle: 'medium' })}
                </td>
                <td className="p-3 text-right">{video.view_count.toLocaleString('en')}</td>
                <td className="p-3 text-right">{video.comment_count.toLocaleString('en')}</td>
                <td className="p-3 text-right">{video.like_count.toLocaleString('en')}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {videos.isPending && <div className="h-32 animate-pulse bg-yt-hover" />}
        {videos.isSuccess && videos.data.items.length === 0 && (
          <p className="p-10 text-center text-yt-muted">
            No videos yet.{' '}
            <Link to="/upload" className="font-medium text-yt-blue">
              Upload one
            </Link>
          </p>
        )}
      </div>

      {pages > 1 && (
        <div className="mt-4 flex items-center justify-end gap-3 text-sm">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setParams({ ...(q ? { q } : {}), page: String(page - 1) })}
            className="rounded-full px-3 py-1.5 hover:bg-yt-hover disabled:opacity-40"
          >
            Previous
          </button>
          <span>
            {page} / {pages}
          </span>
          <button
            type="button"
            disabled={page >= pages}
            onClick={() => setParams({ ...(q ? { q } : {}), page: String(page + 1) })}
            className="rounded-full px-3 py-1.5 hover:bg-yt-hover disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}

// --- edit ------------------------------------------------------------------------------

/** The viewer-bound media token of this page's stream URL (owner-only thumbnail picker). */
function mediaToken(streamUrl: string | null): string | null {
  return streamUrl ? new URL(streamUrl, window.location.origin).searchParams.get('t') : null
}

function Thumbnails({ video, onChanged }: { video: VideoDetail; onChanged: () => Promise<unknown> }) {
  const token = mediaToken(video.stream_url)
  const [error, setError] = useState<string | null>(null)
  const pick = useMutation({
    mutationFn: (thumbnail: Thumb) => request(`/videos/${video.id}`, { method: 'PATCH', json: { thumbnail } }),
    onSuccess: onChanged,
    onError: (err) => setError(describeError(err)),
  })
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request(`/videos/${video.id}/thumbnail`, { method: 'PUT', body: form })
    },
    onSuccess: onChanged,
    onError: (err) => setError(describeError(err)),
  })
  if (!token) return <p className="text-sm text-yt-muted">Thumbnails appear when processing is complete.</p>

  return (
    <div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {(['auto_1', 'auto_2', 'auto_3'] as const).map((choice, index) => (
          <button
            key={choice}
            type="button"
            onClick={() => pick.mutate(choice)}
            aria-label={`Use generated thumbnail ${index + 1}`}
            className="overflow-hidden rounded-lg border-2 border-transparent hover:border-yt-blue"
          >
            <img
              src={`/api/v1/media/videos/${video.id}/thumbnails/${choice}?t=${encodeURIComponent(token)}`}
              alt=""
              className="aspect-video w-full object-cover"
            />
          </button>
        ))}
        <label className="flex aspect-video cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-yt-border text-center text-xs text-yt-muted hover:border-yt-blue">
          Upload thumbnail
          <span>JPG, PNG or WebP, ≤ 2 MB</span>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) upload.mutate(file)
              event.target.value = ''
            }}
          />
        </label>
      </div>
      {video.thumbnail_url && (
        <p className="mt-2 flex items-center gap-2 text-xs text-yt-muted">
          Current:
          <img src={video.thumbnail_url} alt="Current thumbnail" className="h-12 rounded" />
        </p>
      )}
      {error && <p className="mt-2 text-xs text-[#c5221f]">{error}</p>}
    </div>
  )
}

function Sharing({ videoId }: { videoId: string }) {
  const queryClient = useQueryClient()
  const [handle, setHandle] = useState('')
  const [error, setError] = useState<string | null>(null)
  const grants = useQuery({
    queryKey: ['grants', videoId],
    queryFn: () => getJson<Grant[]>(`/videos/${videoId}/permissions`),
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['grants', videoId] })
  const add = useMutation({
    mutationFn: () =>
      request(`/videos/${videoId}/permissions`, {
        method: 'POST',
        json: { handle: handle.trim().replace(/^@/, '').toLowerCase() },
      }),
    onSuccess: () => {
      setHandle('')
      setError(null)
      return refresh()
    },
    onError: (err) => setError(describeError(err)),
  })
  const revoke = useMutation({
    mutationFn: (userId: string) => request(`/videos/${videoId}/permissions/${userId}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })

  return (
    <div>
      <p className="mb-2 text-sm text-yt-muted">Private videos can be watched only by you and the people listed here.</p>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          if (handle.trim()) add.mutate()
        }}
        className="flex gap-2"
      >
        <input
          value={handle}
          onChange={(event) => setHandle(event.target.value)}
          placeholder="@handle"
          aria-label="Handle to share with"
          className="flex-1 rounded-md border border-yt-border px-3 py-2 text-sm outline-none focus:border-yt-blue"
        />
        <button type="submit" className="rounded-full bg-yt-hover px-4 py-2 text-sm font-medium hover:bg-yt-active">
          Share
        </button>
      </form>
      {error && <p className="mt-1 text-xs text-[#c5221f]">{error}</p>}
      <ul className="mt-3 divide-y divide-yt-border text-sm">
        {grants.data?.map((grant) => (
          <li key={grant.user_id} className="flex items-center justify-between py-2">
            <span>
              {grant.name} <span className="text-yt-muted">@{grant.handle}</span>
            </span>
            <button
              type="button"
              onClick={() => revoke.mutate(grant.user_id)}
              className="rounded-full px-3 py-1 text-xs font-medium hover:bg-yt-hover"
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function StudioVideoPage() {
  const { id = '' } = useParams()
  // Keyed by id: unsaved edits of one video never carry over to the next.
  return <StudioVideoEditor key={id} id={id} />
}

function StudioVideoEditor({ id }: { id: string }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const detail = useQuery({
    queryKey: ['video', id],
    queryFn: () => getJson<VideoDetail>(`/videos/${encodeURIComponent(id)}`),
    retry: false,
  })
  usePageTitle(detail.data ? `Edit: ${detail.data.title}` : 'Video details')
  const [form, setForm] = useState<{ title: string; description: string; visibility: Visibility } | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const save = useMutation({
    // PATCH answers with the owner view (VideoOwnerOut), not the watch-page detail:
    // merge its fields, then refetch the detail (stream/thumbnail URLs, flags).
    mutationFn: (changes: NonNullable<typeof form>) =>
      request<StudioVideo>(`/videos/${encodeURIComponent(id)}`, { method: 'PATCH', json: changes }),
    onSuccess: (updated) => {
      queryClient.setQueryData<VideoDetail>(['video', id], (old) => old && { ...old, ...updated })
      void queryClient.invalidateQueries({ queryKey: ['video', id] })
      void queryClient.invalidateQueries({ queryKey: ['studio'] })
      setForm(null)
      setMessage('Changes saved')
    },
    onError: (err) => setMessage(describeError(err)),
  })
  const remove = useMutation({
    mutationFn: () => request(`/videos/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ['video', id] })
      void queryClient.invalidateQueries({ queryKey: ['studio'] })
      navigate('/studio', { replace: true })
    },
    onError: (err) => setMessage(describeError(err)),
  })

  if (detail.isPending) return <div className="m-6 h-64 animate-pulse rounded-xl bg-yt-hover" />
  if (detail.isError || !detail.data.can_edit) {
    return <p className="py-32 text-center text-xl font-medium">This video isn't available</p>
  }

  const video = detail.data
  const values = form ?? { title: video.title, description: video.description, visibility: video.visibility }
  const change = (patch: Partial<typeof values>) => setForm({ ...values, ...patch })
  const refetch = () => queryClient.invalidateQueries({ queryKey: ['video', id] })

  function submit(event: FormEvent) {
    event.preventDefault()
    setMessage(null)
    save.mutate(values)
  }

  return (
    <div className="mx-auto grid max-w-6xl gap-8 px-4 py-6 lg:grid-cols-[1fr_360px]">
      <div className="flex flex-col gap-8">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Video details</h1>
          <Link to="/studio" className="text-sm font-medium text-yt-blue">
            Back to content
          </Link>
        </div>

        <form onSubmit={submit} className="flex flex-col gap-4">
          <label className="block">
            <span className="mb-1 block text-sm font-medium">Title</span>
            <input
              required
              maxLength={100}
              value={values.title}
              onChange={(event) => change({ title: event.target.value })}
              className="w-full rounded-md border border-yt-border px-3 py-2 outline-none focus:border-yt-blue"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium">Description</span>
            <textarea
              rows={8}
              maxLength={5000}
              value={values.description}
              onChange={(event) => change({ description: event.target.value })}
              className="w-full rounded-md border border-yt-border px-3 py-2 outline-none focus:border-yt-blue"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium">Visibility</span>
            <select
              value={values.visibility}
              onChange={(event) => change({ visibility: event.target.value as Visibility })}
              className="rounded-md border border-yt-border px-3 py-2"
            >
              <option value="private">Private</option>
              <option value="unlisted">Unlisted</option>
              <option value="public">Public</option>
            </select>
          </label>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={!form || save.isPending}
              className="rounded-full bg-yt-blue px-5 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Save
            </button>
            {message && <span className="text-sm text-yt-muted">{message}</span>}
          </div>
        </form>

        <section>
          <h2 className="mb-2 font-medium">Thumbnail</h2>
          <Thumbnails video={video} onChanged={refetch} />
        </section>

        {video.visibility === 'private' && (
          <section>
            <h2 className="mb-2 font-medium">Shared with</h2>
            <Sharing videoId={video.id} />
          </section>
        )}
      </div>

      <aside className="flex flex-col gap-4">
        <div className="overflow-hidden rounded-xl bg-yt-hover">
          {video.stream_url ? (
            <video src={video.stream_url} poster={video.thumbnail_url ?? undefined} controls className="aspect-video w-full bg-black" />
          ) : (
            <div className="flex aspect-video items-center justify-center text-sm text-yt-muted">
              {STATUS_LABEL[video.status]}
            </div>
          )}
          <div className="p-3 text-sm">
            <Link to={`/watch?v=${video.id}`} className="font-medium text-yt-blue">
              Open watch page
            </Link>
            {video.is_hidden && <p className="mt-2 text-xs text-[#c5221f]">Hidden by moderators: only you and staff can see it.</p>}
          </div>
        </div>
        <button
          type="button"
          disabled={remove.isPending}
          onClick={() => window.confirm('Delete this video permanently? This cannot be undone.') && remove.mutate()}
          className="rounded-full border border-[#c5221f] px-4 py-2 text-sm font-medium text-[#c5221f] hover:bg-[#fce8e6]"
        >
          Delete video
        </button>
      </aside>
    </div>
  )
}
