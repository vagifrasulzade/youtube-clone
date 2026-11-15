import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from 'react'

import { HttpError, describeError, getJson, request } from '../../api/http'
import type { components } from '../../api/schema'
import { useRequireLogin } from '../../auth/useRequireLogin'

type ReportReason = components['schemas']['ReportReason']
type PlaylistCard = components['schemas']['PlaylistCard']

const REASONS: [ReportReason, string][] = [
  ['spam', 'Spam or misleading'],
  ['sexual', 'Sexual content'],
  ['violent', 'Violent or repulsive content'],
  ['hateful', 'Hateful or abusive content'],
  ['harassment', 'Harassment or bullying'],
  ['harmful', 'Harmful or dangerous acts'],
  ['misinformation', 'Misinformation'],
  ['copyright', 'Infringes my rights'],
  ['other', 'Other'],
]

/** A small modal built on <dialog>: focus trapping and Escape come from the browser. */
function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])
  return (
    <dialog ref={ref} onClose={onClose} className="m-auto w-full max-w-md rounded-xl p-6 backdrop:bg-black/50">
      <h2 className="mb-4 text-lg font-medium">{title}</h2>
      {children}
    </dialog>
  )
}

const pill = 'rounded-full bg-yt-hover px-4 py-2 text-sm font-medium hover:bg-yt-active'

export function ReportButton({ videoId }: { videoId: string }) {
  const requireLogin = useRequireLogin()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState<ReportReason | null>(null)
  const [details, setDetails] = useState('')
  const [result, setResult] = useState<string | null>(null)
  const report = useMutation({
    mutationFn: () => request(`/videos/${videoId}/reports`, { method: 'POST', json: { reason, details } }),
    onSuccess: () => setResult('Thanks for reporting. Our moderators will review this video.'),
    onError: (err) =>
      setResult(err instanceof HttpError && err.status === 409 ? 'You have already reported this video.' : describeError(err)),
  })
  const close = () => {
    setOpen(false)
    setReason(null)
    setDetails('')
    setResult(null)
  }
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (reason) report.mutate()
  }

  return (
    <>
      <button type="button" onClick={() => requireLogin() && setOpen(true)} className={pill}>
        Report
      </button>
      <Modal open={open} onClose={close} title="Report video">
        {result ? (
          <div className="flex flex-col gap-4">
            <p className="text-sm">{result}</p>
            <button type="button" onClick={close} className="self-end rounded-full px-4 py-2 text-sm font-medium text-yt-blue">
              Close
            </button>
          </div>
        ) : (
          <form onSubmit={submit} className="flex flex-col gap-2">
            <fieldset className="flex flex-col gap-2">
            <legend className="sr-only">What is the problem?</legend>
            {REASONS.map(([value, label]) => (
              <label key={value} className="flex items-center gap-3 text-sm">
                <input type="radio" name="reason" checked={reason === value} onChange={() => setReason(value)} />
                {label}
              </label>
            ))}
            </fieldset>
            <textarea
              value={details}
              maxLength={1000}
              rows={3}
              onChange={(event) => setDetails(event.target.value)}
              placeholder="Details (optional)"
              aria-label="Details (optional)"
              className="mt-2 rounded-md border border-yt-border p-2 text-sm outline-none focus:border-yt-blue"
            />
            <div className="mt-2 flex justify-end gap-2">
              <button type="button" onClick={close} className="rounded-full px-4 py-2 text-sm font-medium hover:bg-yt-hover">
                Cancel
              </button>
              <button
                type="submit"
                disabled={!reason || report.isPending}
                className="rounded-full bg-yt-blue px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                Report
              </button>
            </div>
          </form>
        )}
      </Modal>
    </>
  )
}

export function SaveToPlaylistButton({ videoId }: { videoId: string }) {
  const requireLogin = useRequireLogin()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const playlists = useQuery({
    queryKey: ['my-playlists'],
    queryFn: () => getJson<PlaylistCard[]>('/me/playlists'),
    enabled: open,
  })
  const add = useMutation({
    mutationFn: (playlist: PlaylistCard) =>
      request(`/playlists/${playlist.id}/videos`, { method: 'POST', json: { video_id: videoId } }).then(() => playlist),
    onSuccess: (playlist) => {
      setMessage(`Saved to ${playlist.title}`)
      return queryClient.invalidateQueries({ queryKey: ['my-playlists'] })
    },
    onError: (err) => setMessage(describeError(err)),
  })
  const close = () => {
    setOpen(false)
    setMessage(null)
  }

  return (
    <>
      <button type="button" onClick={() => requireLogin() && setOpen(true)} className={pill}>
        Save
      </button>
      <Modal open={open} onClose={close} title="Save video to…">
        <div className="flex flex-col gap-1">
          {playlists.data?.map((playlist) => (
            <button
              key={playlist.id}
              type="button"
              disabled={add.isPending}
              onClick={() => add.mutate(playlist)}
              className="rounded-lg px-3 py-2 text-left text-sm hover:bg-yt-hover"
            >
              {playlist.title} <span className="text-xs capitalize text-yt-muted">· {playlist.visibility}</span>
            </button>
          ))}
          {playlists.isSuccess && playlists.data.length === 0 && (
            <p className="text-sm text-yt-muted">You have no playlists yet. Create one on the Playlists page.</p>
          )}
          {message && <p className="mt-2 text-sm">{message}</p>}
          <button type="button" onClick={close} className="mt-2 self-end rounded-full px-4 py-2 text-sm font-medium text-yt-blue">
            Done
          </button>
        </div>
      </Modal>
    </>
  )
}
