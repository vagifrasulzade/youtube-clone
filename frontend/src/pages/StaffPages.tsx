import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, type ReactNode, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { describeError, getJson, request } from '../api/http'
import type { components } from '../api/schema'
import { useAuth } from '../auth/context'
import { usePageTitle } from '../hooks/usePageTitle'

type Report = components['schemas']['ReportOut']
type ReportStatus = components['schemas']['ReportStatus']
type Action = components['schemas']['ModerationActionOut']
type AdminUser = components['schemas']['AdminUserOut']
type StudioVideo = components['schemas']['VideoOwnerOut']
type Numbered<T> = { items: T[]; total: number; page: number; page_size: number }
interface Stats {
  users: number
  banned_users: number
  videos_by_status: Record<string, number>
  views_total: number
  storage_bytes: number
  open_reports: number
  signups_7d: number
}

/** A required note for audited actions. `null` when the moderator cancels. */
function askNote(label: string): string | null {
  const note = window.prompt(label)?.trim()
  return note ? note.slice(0, 1000) : null
}

function Tabs<T extends string>({ value, options, onChange }: { value: T; options: [T, string][]; onChange: (v: T) => void }) {
  return (
    <div role="tablist" className="mb-6 flex gap-6 border-b border-yt-border">
      {options.map(([key, label]) => (
        <button
          key={key}
          role="tab"
          type="button"
          aria-selected={value === key}
          onClick={() => onChange(key)}
          className={`pb-3 text-sm font-medium ${value === key ? 'border-b-2 border-yt-text' : 'text-yt-muted hover:text-yt-text'}`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

function Pager({ data, page, onPage }: { data?: Numbered<unknown>; page: number; onPage: (p: number) => void }) {
  if (!data) return null
  const pages = Math.max(1, Math.ceil(data.total / data.page_size))
  if (pages <= 1) return null
  return (
    <div className="mt-4 flex items-center justify-end gap-3 text-sm">
      <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)} className="rounded-full px-3 py-1.5 hover:bg-yt-hover disabled:opacity-40">
        Previous
      </button>
      <span>
        {page} / {pages}
      </span>
      <button type="button" disabled={page >= pages} onClick={() => onPage(page + 1)} className="rounded-full px-3 py-1.5 hover:bg-yt-hover disabled:opacity-40">
        Next
      </button>
    </div>
  )
}

function Table({ head, children, empty }: { head: string[]; children: ReactNode; empty: boolean }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-yt-border">
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead className="border-b border-yt-border text-xs text-yt-muted">
          <tr>
            {head.map((h) => (
              <th key={h} className="p-3 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-yt-border">{children}</tbody>
      </table>
      {empty && <p className="p-8 text-center text-yt-muted">Nothing here.</p>}
    </div>
  )
}

const small = 'rounded-full px-3 py-1 text-xs font-medium hover:bg-yt-hover disabled:opacity-40'
const date = (iso: string) => new Date(iso).toLocaleString('en', { dateStyle: 'medium', timeStyle: 'short' })

function ErrorLine({ error }: { error: unknown }) {
  return error ? <p className="mb-3 text-sm text-[#c5221f]">{describeError(error)}</p> : null
}

// --- moderation ------------------------------------------------------------------------

function ReportsTab() {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<ReportStatus>('open')
  const [page, setPage] = useState(1)
  const reports = useQuery({
    queryKey: ['reports', status, page],
    queryFn: () => getJson<Numbered<Report>>('/moderation/reports', { status, page: String(page) }),
  })
  const act = useMutation({
    mutationFn: ({ report, kind }: { report: Report; kind: 'hide' | 'keep' | 'dismiss' }) => {
      const note = askNote(kind === 'dismiss' ? 'Why is this report dismissed?' : 'Resolution note (kept in the audit log)')
      if (!note) return Promise.resolve(null)
      return kind === 'dismiss'
        ? request(`/moderation/reports/${report.id}/dismiss`, { method: 'POST', json: { note } })
        : request(`/moderation/reports/${report.id}/resolve`, { method: 'POST', json: { note, hide_video: kind === 'hide' } })
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['reports'] }),
  })

  return (
    <>
      <div className="mb-4 flex gap-2">
        {(['open', 'resolved', 'dismissed'] as const).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => {
              setStatus(value)
              setPage(1)
            }}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium capitalize ${status === value ? 'bg-yt-text text-white' : 'bg-yt-hover'}`}
          >
            {value}
          </button>
        ))}
      </div>
      <ErrorLine error={act.error} />
      <Table head={['Video', 'Reason', 'Details', 'Reported', status === 'open' ? 'Actions' : 'Note']} empty={reports.data?.items.length === 0}>
        {reports.data?.items.map((report) => (
          <tr key={report.id}>
            <td className="p-3">
              <Link to={`/watch?v=${report.video_id}`} className="font-mono text-yt-blue hover:underline">
                {report.video_id}
              </Link>
            </td>
            <td className="p-3 capitalize">{report.reason}</td>
            <td className="max-w-xs p-3 text-yt-muted">{report.details || '—'}</td>
            <td className="p-3 text-yt-muted">{date(report.created_at)}</td>
            <td className="p-3">
              {report.status === 'open' ? (
                <div className="flex flex-wrap gap-1">
                  <button type="button" disabled={act.isPending} onClick={() => act.mutate({ report, kind: 'hide' })} className={`${small} text-[#c5221f]`}>
                    Hide video
                  </button>
                  <button type="button" disabled={act.isPending} onClick={() => act.mutate({ report, kind: 'keep' })} className={small}>
                    Resolve, keep
                  </button>
                  <button type="button" disabled={act.isPending} onClick={() => act.mutate({ report, kind: 'dismiss' })} className={small}>
                    Dismiss
                  </button>
                </div>
              ) : (
                <span className="text-yt-muted">{report.resolution_note}</span>
              )}
            </td>
          </tr>
        ))}
      </Table>
      <Pager data={reports.data} page={page} onPage={setPage} />
    </>
  )
}

function VideoActionForm() {
  const queryClient = useQueryClient()
  const [value, setValue] = useState('')
  const [done, setDone] = useState<string | null>(null)
  const act = useMutation({
    mutationFn: (kind: 'hide' | 'restore') => {
      // Accept a bare id or a watch URL (…/watch?v=<id>).
      const id = value.match(/[?&]v=([\w-]{11})/)?.[1] ?? value.trim()
      const note = askNote(kind === 'hide' ? 'Why is this video hidden?' : 'Why is this video restored?')
      if (!note) return Promise.resolve(null)
      return request(`/moderation/videos/${encodeURIComponent(id)}/${kind}`, { method: 'POST', json: { note } }).then(() => kind)
    },
    onSuccess: (kind) => {
      if (kind) setDone(kind === 'hide' ? 'Video hidden' : 'Video restored')
      return queryClient.invalidateQueries()
    },
  })
  const submit = (event: FormEvent) => event.preventDefault()
  return (
    <form onSubmit={submit} className="mb-6 flex flex-wrap items-center gap-2 rounded-xl bg-yt-hover p-4 text-sm">
      <input
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Video id or watch URL"
        className="min-w-64 flex-1 rounded-md border border-yt-border bg-white px-3 py-2 outline-none focus:border-yt-blue"
      />
      <button type="button" disabled={!value.trim() || act.isPending} onClick={() => act.mutate('hide')} className="rounded-full bg-[#c5221f] px-4 py-2 font-medium text-white disabled:opacity-50">
        Hide
      </button>
      <button type="button" disabled={!value.trim() || act.isPending} onClick={() => act.mutate('restore')} className="rounded-full bg-white px-4 py-2 font-medium disabled:opacity-50">
        Restore
      </button>
      {done && !act.error && <span className="text-yt-muted">{done}</span>}
      {act.error && <span className="text-[#c5221f]">{describeError(act.error)}</span>}
    </form>
  )
}

function AuditTab() {
  const [page, setPage] = useState(1)
  const actions = useQuery({
    queryKey: ['audit', page],
    queryFn: () => getJson<Numbered<Action>>('/moderation/actions', { page: String(page) }),
  })
  return (
    <>
      <Table head={['When', 'Action', 'Target', 'Reason / details']} empty={actions.data?.items.length === 0}>
        {actions.data?.items.map((entry) => (
          <tr key={entry.id}>
            <td className="p-3 text-yt-muted">{date(entry.created_at)}</td>
            <td className="p-3 font-medium">{entry.action.replace(/_/g, ' ')}</td>
            <td className="p-3">
              {entry.target_type === 'video' ? (
                <Link to={`/watch?v=${entry.target_id}`} className="font-mono text-yt-blue hover:underline">
                  {entry.target_id}
                </Link>
              ) : (
                <span className="font-mono text-xs">
                  {entry.target_type} {entry.target_id}
                </span>
              )}
            </td>
            <td className="max-w-sm p-3 text-xs text-yt-muted">
              {entry.reason}
              {entry.details && Object.keys(entry.details).length > 0 && (
                <span className="block truncate">{JSON.stringify(entry.details)}</span>
              )}
            </td>
          </tr>
        ))}
      </Table>
      <Pager data={actions.data} page={page} onPage={setPage} />
    </>
  )
}

export function ModerationPage() {
  usePageTitle('Moderation')
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'audit' ? 'audit' : 'reports'
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <h1 className="mb-4 text-2xl font-bold">Moderation</h1>
      <VideoActionForm />
      <Tabs
        value={tab}
        options={[
          ['reports', 'Reports'],
          ['audit', 'Audit log'],
        ]}
        onChange={(value) => setParams(value === 'reports' ? {} : { tab: value })}
      />
      {tab === 'reports' ? <ReportsTab /> : <AuditTab />}
    </div>
  )
}

// --- admin -----------------------------------------------------------------------------

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-yt-border p-4">
      <p className="text-xs text-yt-muted">{label}</p>
      <p className="mt-1 text-2xl font-bold">{typeof value === 'number' ? value.toLocaleString('en') : value}</p>
    </div>
  )
}

function StatsPanel() {
  const stats = useQuery({ queryKey: ['admin-stats'], queryFn: () => getJson<Stats>('/admin/stats') })
  const s = stats.data
  if (!s) return <div className="mb-6 h-24 animate-pulse rounded-xl bg-yt-hover" />
  const gib = (s.storage_bytes / 1024 ** 3).toFixed(2)
  return (
    <div className="mb-8 grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatCard label="Users" value={s.users} />
      <StatCard label="New users (7 days)" value={s.signups_7d} />
      <StatCard label="Banned users" value={s.banned_users} />
      <StatCard label="Open reports" value={s.open_reports} />
      <StatCard label="Ready videos" value={s.videos_by_status.ready ?? 0} />
      <StatCard label="Processing / queued" value={(s.videos_by_status.processing ?? 0) + (s.videos_by_status.queued ?? 0)} />
      <StatCard label="Total views" value={s.views_total} />
      <StatCard label="Playback storage" value={`${gib} GiB`} />
    </div>
  )
}

function UsersTab() {
  const { user: me } = useAuth()
  const queryClient = useQueryClient()
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const users = useQuery({
    queryKey: ['admin-users', search, page],
    queryFn: () => getJson<Numbered<AdminUser>>('/admin/users', { q: search || undefined, page: String(page) }),
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['admin-users'] })
  const role = useMutation({
    mutationFn: ({ id, value }: { id: string; value: 'user' | 'moderator' }) =>
      request(`/admin/users/${id}/role`, { method: 'PATCH', json: { role: value } }),
    onSuccess: refresh,
  })
  const ban = useMutation({
    mutationFn: ({ target, lift }: { target: AdminUser; lift: boolean }) => {
      const note = askNote(lift ? `Why is @${target.handle} unbanned?` : `Why is @${target.handle} banned?`)
      if (!note) return Promise.resolve(null)
      return lift
        ? request(`/admin/users/${target.id}/unban`, { method: 'POST', json: { note } })
        : request(`/admin/users/${target.id}/ban`, { method: 'POST', json: { reason: note } })
    },
    onSuccess: refresh,
  })

  return (
    <>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          setSearch(q.trim())
          setPage(1)
        }}
        className="mb-4"
      >
        <input
          value={q}
          onChange={(event) => setQ(event.target.value)}
          placeholder="Search by email or handle"
          maxLength={100}
          className="w-80 rounded-full border border-yt-border px-4 py-2 text-sm outline-none focus:border-yt-blue"
        />
      </form>
      <ErrorLine error={role.error ?? ban.error} />
      <Table head={['User', 'Email', 'Role', 'Joined', 'Status', '']} empty={users.data?.items.length === 0}>
        {users.data?.items.map((u) => {
          const self = u.id === me?.id
          return (
            <tr key={u.id}>
              <td className="p-3">
                <Link to={`/@${u.handle}`} className="font-medium hover:underline">
                  {u.name}
                </Link>
                <span className="block text-xs text-yt-muted">@{u.handle}</span>
              </td>
              <td className="p-3 text-yt-muted">{u.email}</td>
              <td className="p-3">
                {u.role === 'admin' || self ? (
                  <span className="capitalize">{u.role}</span>
                ) : (
                  <select
                    value={u.role}
                    disabled={role.isPending}
                    onChange={(event) => role.mutate({ id: u.id, value: event.target.value as 'user' | 'moderator' })}
                    className="rounded-md border border-yt-border px-2 py-1"
                  >
                    <option value="user">User</option>
                    <option value="moderator">Moderator</option>
                  </select>
                )}
              </td>
              <td className="p-3 text-yt-muted">{new Date(u.created_at).toLocaleDateString('en', { dateStyle: 'medium' })}</td>
              <td className="p-3">
                {u.banned_at ? (
                  <span className="text-[#c5221f]" title={u.ban_reason ?? undefined}>
                    Banned
                  </span>
                ) : (
                  'Active'
                )}
              </td>
              <td className="p-3 text-right">
                {!self && u.role !== 'admin' && (
                  <button
                    type="button"
                    disabled={ban.isPending}
                    onClick={() => ban.mutate({ target: u, lift: Boolean(u.banned_at) })}
                    className={`${small} ${u.banned_at ? '' : 'text-[#c5221f]'}`}
                  >
                    {u.banned_at ? 'Unban' : 'Ban'}
                  </button>
                )}
              </td>
            </tr>
          )
        })}
      </Table>
      <Pager data={users.data} page={page} onPage={setPage} />
    </>
  )
}

function VideosTab() {
  const queryClient = useQueryClient()
  const [hiddenOnly, setHiddenOnly] = useState(false)
  const [page, setPage] = useState(1)
  const videos = useQuery({
    queryKey: ['admin-videos', hiddenOnly, page],
    queryFn: () =>
      getJson<Numbered<StudioVideo>>('/admin/videos', { hidden: hiddenOnly ? 'true' : undefined, page: String(page) }),
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['admin-videos'] })
  const act = useMutation({
    mutationFn: ({ video, kind }: { video: StudioVideo; kind: 'hide' | 'restore' | 'delete' }) => {
      if (kind === 'delete') {
        if (!window.confirm(`Delete "${video.title}" permanently? This is audited.`)) return Promise.resolve(null)
        return request(`/admin/videos/${video.id}`, { method: 'DELETE' })
      }
      const note = askNote(kind === 'hide' ? 'Why is this video hidden?' : 'Why is this video restored?')
      if (!note) return Promise.resolve(null)
      return request(`/moderation/videos/${video.id}/${kind}`, { method: 'POST', json: { note } })
    },
    onSuccess: refresh,
  })

  return (
    <>
      <label className="mb-4 flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={hiddenOnly}
          onChange={(event) => {
            setHiddenOnly(event.target.checked)
            setPage(1)
          }}
        />
        Hidden videos only
      </label>
      <ErrorLine error={act.error} />
      <Table head={['Video', 'Status', 'Visibility', 'Views', '']} empty={videos.data?.items.length === 0}>
        {videos.data?.items.map((video) => (
          <tr key={video.id}>
            <td className="p-3">
              <Link to={`/watch?v=${video.id}`} className="font-medium hover:underline">
                {video.title}
              </Link>
              {video.is_hidden && <span className="ml-2 text-xs text-[#c5221f]">hidden</span>}
            </td>
            <td className="p-3">{video.status}</td>
            <td className="p-3 capitalize">{video.visibility}</td>
            <td className="p-3">{video.view_count.toLocaleString('en')}</td>
            <td className="p-3 text-right">
              <button
                type="button"
                disabled={act.isPending}
                onClick={() => act.mutate({ video, kind: video.is_hidden ? 'restore' : 'hide' })}
                className={small}
              >
                {video.is_hidden ? 'Restore' : 'Hide'}
              </button>
              <button type="button" disabled={act.isPending} onClick={() => act.mutate({ video, kind: 'delete' })} className={`${small} text-[#c5221f]`}>
                Delete
              </button>
            </td>
          </tr>
        ))}
      </Table>
      <Pager data={videos.data} page={page} onPage={setPage} />
    </>
  )
}

export function AdminPage() {
  usePageTitle('Admin')
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'videos' ? 'videos' : 'users'
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <h1 className="mb-4 text-2xl font-bold">Admin</h1>
      <StatsPanel />
      <Tabs
        value={tab}
        options={[
          ['users', 'Users'],
          ['videos', 'Videos'],
        ]}
        onChange={(value) => setParams(value === 'users' ? {} : { tab: value })}
      />
      {tab === 'users' ? <UsersTab /> : <VideosTab />}
    </div>
  )
}
