import { useQuery, useQueryClient } from '@tanstack/react-query'
import { type DragEvent, type FormEvent, useRef, useState } from 'react'
import { Link } from 'react-router'

import { describeError, request } from '../api/http'
import type { components } from '../api/schema'
import { CreateIcon } from '../components/icons'
import { usePageTitle } from '../hooks/usePageTitle'

type UploadCreated = components['schemas']['UploadCreatedOut']
type VideoStatus = components['schemas']['VideoStatusOut']
type Visibility = components['schemas']['Visibility']

// Same list as the API (services/uploads.py). Some browsers report no type for .mkv/.avi,
// so the extension decides then; the server checks again, plus magic bytes and ffprobe.
const TYPES_BY_EXTENSION: Record<string, string> = {
  mp4: 'video/mp4',
  m4v: 'video/mp4',
  mov: 'video/quicktime',
  webm: 'video/webm',
  mkv: 'video/x-matroska',
  avi: 'video/x-msvideo',
}
const MAX_BYTES = 2 * 1024 ** 3

function contentTypeOf(file: File): string | null {
  const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
  const fromExtension = TYPES_BY_EXTENSION[extension]
  if (!fromExtension) return null
  return Object.values(TYPES_BY_EXTENSION).includes(file.type) ? file.type : fromExtension
}

function titleFromFilename(name: string): string {
  return name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').trim().slice(0, 100) || 'Untitled video'
}

/** Presigned POST straight to object storage, with progress (fetch cannot report it). */
function postToStorage(upload: UploadCreated['upload'], file: File, onProgress: (p: number) => void) {
  return new Promise<void>((resolve, reject) => {
    const form = new FormData()
    Object.entries(upload.fields).forEach(([key, value]) => form.append(key, value))
    form.append('file', file) // must be the last field
    const xhr = new XMLHttpRequest()
    xhr.open('POST', upload.url)
    xhr.upload.onprogress = (event) => event.lengthComputable && onProgress(event.loaded / event.total)
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`Upload failed (${xhr.status})`))
    xhr.onerror = () => reject(new Error('Upload failed: network error'))
    xhr.send(form)
  })
}

type Phase = 'pick' | 'uploading' | 'processing'

export function UploadPage() {
  usePageTitle('Upload video')
  const input = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()
  const [phase, setPhase] = useState<Phase>('pick')
  const [videoId, setVideoId] = useState<string | null>(null)
  const [uploaded, setUploaded] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [details, setDetails] = useState({ title: '', description: '', visibility: 'private' as Visibility })
  const [saved, setSaved] = useState(false)

  const status = useQuery({
    queryKey: ['upload-status', videoId],
    queryFn: () => request<VideoStatus>(`/videos/${videoId}/status`),
    enabled: phase === 'processing' && videoId !== null,
    refetchInterval: (query) => {
      if (query.state.status === 'error') return false // e.g. the video was deleted
      const state = query.state.data?.status
      return state === 'ready' || state === 'failed' ? false : 2000
    },
  })

  async function start(file: File) {
    setError(null)
    const contentType = contentTypeOf(file)
    if (!contentType) return setError('Choose an MP4, MOV, WebM, MKV or AVI file.')
    if (file.size > MAX_BYTES) return setError('Files can be at most 2 GB.')
    const title = titleFromFilename(file.name)
    setDetails((d) => ({ ...d, title }))
    setPhase('uploading')
    try {
      const created = await request<UploadCreated>('/videos', {
        method: 'POST',
        json: { filename: file.name, content_type: contentType, size_bytes: file.size, title },
      })
      setVideoId(created.video.id)
      await postToStorage(created.upload, file, setUploaded)
      await request(`/videos/${created.video.id}/upload-complete`, { method: 'POST' })
      void queryClient.invalidateQueries({ queryKey: ['studio'] })
      setPhase('processing')
    } catch (err) {
      setError(err instanceof Error && !('status' in err) ? err.message : describeError(err))
      setPhase('pick')
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!videoId) return
    setError(null)
    try {
      await request(`/videos/${videoId}`, { method: 'PATCH', json: details })
      setSaved(true)
    } catch (err) {
      setError(describeError(err))
    }
  }

  const drop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    const file = event.dataTransfer.files[0]
    if (file) void start(file)
  }

  const state = status.data?.status
  const progressText =
    phase === 'uploading'
      ? `Uploading ${Math.round(uploaded * 100)}%`
      : state === 'ready'
        ? 'Processing complete'
        : state === 'failed'
          ? `Processing failed: ${status.data?.error ?? 'unknown error'}`
          : `Processing${status.data?.progress != null ? ` ${status.data.progress}%` : '…'}`

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold">Upload video</h1>

      {phase === 'pick' ? (
        <div
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={drop}
          className={`flex flex-col items-center gap-4 rounded-2xl border-2 border-dashed p-16 text-center ${
            dragging ? 'border-yt-blue bg-[#def1ff]' : 'border-yt-border'
          }`}
        >
          <div className="flex size-32 items-center justify-center rounded-full bg-yt-hover text-yt-muted">
            <CreateIcon size={56} />
          </div>
          <p className="text-lg">Drag and drop a video file to upload</p>
          <p className="text-sm text-yt-muted">Your video stays private until you publish it.</p>
          <button
            type="button"
            onClick={() => input.current?.click()}
            className="rounded-full bg-yt-text px-5 py-2.5 text-sm font-medium text-white"
          >
            Select file
          </button>
          <input
            ref={input}
            type="file"
            accept=".mp4,.m4v,.mov,.webm,.mkv,.avi,video/*"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) void start(file)
              event.target.value = ''
            }}
          />
          {error && (
            <p role="alert" className="text-sm text-[#d93025]">
              {error}
            </p>
          )}
        </div>
      ) : (
        <form onSubmit={save} className="grid gap-6 md:grid-cols-[1fr_280px]">
          <div className="flex flex-col gap-4">
            <label className="block">
              <span className="mb-1 block text-sm font-medium">Title (required)</span>
              <input
                required
                maxLength={100}
                value={details.title}
                onChange={(event) => setDetails({ ...details, title: event.target.value })}
                className="w-full rounded-md border border-yt-border px-3 py-2 outline-none focus:border-yt-blue"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium">Description</span>
              <textarea
                rows={6}
                maxLength={5000}
                value={details.description}
                onChange={(event) => setDetails({ ...details, description: event.target.value })}
                className="w-full rounded-md border border-yt-border px-3 py-2 outline-none focus:border-yt-blue"
              />
            </label>
            <fieldset>
              <legend className="mb-1 text-sm font-medium">Visibility</legend>
              {(['private', 'unlisted', 'public'] as const).map((value) => (
                <label key={value} className="mr-6 inline-flex items-center gap-2 text-sm capitalize">
                  <input
                    type="radio"
                    name="visibility"
                    checked={details.visibility === value}
                    onChange={() => setDetails({ ...details, visibility: value })}
                  />
                  {value}
                </label>
              ))}
            </fieldset>
            {error && (
              <p role="alert" className="text-sm text-[#d93025]">
                {error}
              </p>
            )}
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={!videoId}
                className="rounded-full bg-yt-blue px-5 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                Save
              </button>
              {saved && <span className="text-sm text-yt-muted">Saved</span>}
            </div>
          </div>

          <aside className="flex flex-col gap-3 rounded-xl bg-yt-hover p-4 text-sm">
            <p className="font-medium">{progressText}</p>
            <div className="h-1.5 overflow-hidden rounded-full bg-yt-border">
              <div
                className={`h-full ${state === 'failed' ? 'bg-[#d93025]' : 'bg-yt-blue'}`}
                style={{
                  width: `${phase === 'uploading' ? uploaded * 100 : state === 'ready' ? 100 : (status.data?.progress ?? 5)}%`,
                }}
              />
            </div>
            {state === 'ready' && videoId && (
              <Link to={`/watch?v=${videoId}`} className="font-medium text-yt-blue">
                Watch your video
              </Link>
            )}
            <Link to="/studio" className="font-medium text-yt-blue">
              Go to Studio
            </Link>
          </aside>
        </form>
      )}
    </div>
  )
}
