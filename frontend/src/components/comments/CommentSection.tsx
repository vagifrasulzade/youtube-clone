import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { Link } from 'react-router'

import { describeError, getJson, request } from '../../api/http'
import type { components } from '../../api/schema'
import { useAuth } from '../../auth/context'
import { useRequireLogin } from '../../auth/useRequireLogin'
import { Avatar } from '../ui/Avatar'
import { timeAgo } from '../video/timeAgo'

type Comment = components['schemas']['CommentOut']
type Page = { items: Comment[]; next_cursor: string | null }
type Sort = 'newest' | 'oldest'

const MAX_LENGTH = 10_000

/** Refetch everything that shows this video's comments or its comment count. */
function useRefreshComments(videoId: string) {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ['comments', videoId] }),
      queryClient.invalidateQueries({ queryKey: ['replies', videoId] }),
      queryClient.invalidateQueries({ queryKey: ['video', videoId] }),
    ])
}

function Composer(props: {
  placeholder: string
  submitLabel: string
  initial?: string
  autoFocus?: boolean
  onSubmit: (body: string) => Promise<unknown>
  onCancel?: () => void
}) {
  const { user } = useAuth()
  const [body, setBody] = useState(props.initial ?? '')
  const [focused, setFocused] = useState(Boolean(props.autoFocus || props.initial))
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!body.trim()) return
    setBusy(true)
    setError(null)
    try {
      await props.onSubmit(body)
      setBody('')
      setFocused(false)
      props.onCancel?.()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const cancel = () => {
    setBody(props.initial ?? '')
    setFocused(false)
    setError(null)
    props.onCancel?.()
  }

  return (
    <form onSubmit={submit} className="flex gap-3">
      {user && !props.initial && <Avatar name={user.channel.name} url={user.channel.avatar_url} size={40} />}
      <div className="min-w-0 flex-1">
        <textarea
          value={body}
          rows={1}
          maxLength={MAX_LENGTH}
          autoFocus={props.autoFocus}
          placeholder={props.placeholder}
          aria-label={props.placeholder}
          onFocus={() => setFocused(true)}
          onChange={(event) => setBody(event.target.value)}
          className="field-sizing-content w-full resize-none border-b border-yt-border bg-transparent pb-1 text-sm outline-none focus:border-yt-text"
        />
        {error && (
          <p role="alert" className="mt-1 text-xs text-[#d93025]">
            {error}
          </p>
        )}
        {focused && (
          <div className="mt-2 flex justify-end gap-2">
            <button type="button" onClick={cancel} className="rounded-full px-4 py-2 text-sm font-medium hover:bg-yt-hover">
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy || !body.trim()}
              className="rounded-full bg-yt-blue px-4 py-2 text-sm font-medium text-white disabled:bg-yt-hover disabled:text-yt-muted"
            >
              {props.submitLabel}
            </button>
          </div>
        )}
      </div>
    </form>
  )
}

function CommentItem({ comment, videoId }: { comment: Comment; videoId: string }) {
  const refresh = useRefreshComments(videoId)
  const requireLogin = useRequireLogin()
  const [editing, setEditing] = useState(false)
  const [replying, setReplying] = useState(false)
  const [showReplies, setShowReplies] = useState(false)
  const remove = useMutation({
    mutationFn: () => request<void>(`/comments/${comment.id}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })
  const isTopLevel = comment.parent_id === null
  const size = isTopLevel ? 40 : 24

  return (
    <div className="flex gap-3">
      <Link to={`/@${comment.author.handle}`} className="shrink-0">
        <Avatar name={comment.author.name} url={comment.author.avatar_url} size={size} />
      </Link>
      <div className="min-w-0 flex-1">
        <p className="text-xs">
          <Link
            to={`/@${comment.author.handle}`}
            className={`font-medium ${comment.is_video_owner ? 'rounded-full bg-[#888] px-1.5 py-0.5 text-white' : ''}`}
          >
            @{comment.author.handle}
          </Link>{' '}
          <span className="text-yt-muted">
            {timeAgo(comment.created_at)}
            {comment.edited_at && ' (edited)'}
          </span>
        </p>

        {editing ? (
          <div className="mt-1">
            <Composer
              placeholder="Edit your comment"
              submitLabel="Save"
              initial={comment.body}
              autoFocus
              onSubmit={(body) =>
                request(`/comments/${comment.id}`, { method: 'PATCH', json: { body } }).then(refresh)
              }
              onCancel={() => setEditing(false)}
            />
          </div>
        ) : (
          <p className="mt-0.5 whitespace-pre-wrap break-words text-sm">{comment.body}</p>
        )}

        {!editing && (
          <div className="mt-1 flex items-center gap-1 text-xs font-medium">
            {isTopLevel && (
              <button
                type="button"
                onClick={() => requireLogin() && setReplying(true)}
                className="rounded-full px-3 py-1.5 hover:bg-yt-hover"
              >
                Reply
              </button>
            )}
            {comment.can_edit && (
              <button type="button" onClick={() => setEditing(true)} className="rounded-full px-3 py-1.5 hover:bg-yt-hover">
                Edit
              </button>
            )}
            {comment.can_delete && (
              <button
                type="button"
                disabled={remove.isPending}
                onClick={() => window.confirm('Delete this comment permanently?') && remove.mutate()}
                className="rounded-full px-3 py-1.5 hover:bg-yt-hover"
              >
                Delete
              </button>
            )}
          </div>
        )}

        {replying && (
          <div className="mt-2">
            <Composer
              placeholder="Add a reply…"
              submitLabel="Reply"
              autoFocus
              onSubmit={async (body) => {
                await request(`/videos/${videoId}/comments`, {
                  method: 'POST',
                  json: { body, parent_id: comment.id },
                })
                setShowReplies(true)
                await refresh()
              }}
              onCancel={() => setReplying(false)}
            />
          </div>
        )}

        {isTopLevel && comment.reply_count > 0 && (
          <button
            type="button"
            onClick={() => setShowReplies((v) => !v)}
            className="mt-1 rounded-full px-3 py-1.5 text-sm font-medium text-yt-blue hover:bg-[#def1ff]"
          >
            {showReplies ? '▲' : '▼'} {comment.reply_count} {comment.reply_count === 1 ? 'reply' : 'replies'}
          </button>
        )}
        {showReplies && <Replies parentId={comment.id} videoId={videoId} />}
      </div>
    </div>
  )
}

function Replies({ parentId, videoId }: { parentId: string; videoId: string }) {
  const replies = useInfiniteQuery({
    queryKey: ['replies', videoId, parentId],
    queryFn: ({ pageParam }) =>
      getJson<Page>(`/comments/${parentId}/replies`, { limit: '20', cursor: pageParam ?? undefined }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  })
  return (
    <div className="mt-2 flex flex-col gap-4">
      {replies.data?.pages.flatMap((p) => p.items).map((reply) => (
        <CommentItem key={reply.id} comment={reply} videoId={videoId} />
      ))}
      {replies.hasNextPage && (
        <button
          type="button"
          onClick={() => void replies.fetchNextPage()}
          className="self-start rounded-full px-3 py-1.5 text-sm font-medium text-yt-blue hover:bg-[#def1ff]"
        >
          Show more replies
        </button>
      )}
    </div>
  )
}

export function CommentSection({ videoId, count }: { videoId: string; count: number }) {
  const { user } = useAuth()
  const refresh = useRefreshComments(videoId)
  const [sort, setSort] = useState<Sort>('newest')
  const comments = useInfiniteQuery({
    queryKey: ['comments', videoId, sort],
    queryFn: ({ pageParam }) =>
      getJson<Page>(`/videos/${videoId}/comments`, { sort, limit: '20', cursor: pageParam ?? undefined }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  })
  const items = comments.data?.pages.flatMap((p) => p.items) ?? []

  return (
    <section className="mt-6" aria-label="Comments">
      <div className="mb-6 flex items-center gap-8">
        <h2 className="text-xl font-bold">
          {count.toLocaleString('en')} {count === 1 ? 'Comment' : 'Comments'}
        </h2>
        <label className="flex items-center gap-2 text-sm font-medium">
          Sort by
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value as Sort)}
            className="rounded-lg bg-yt-hover px-2 py-1"
          >
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
          </select>
        </label>
      </div>

      {user ? (
        <Composer
          placeholder="Add a comment…"
          submitLabel="Comment"
          onSubmit={(body) =>
            request(`/videos/${videoId}/comments`, { method: 'POST', json: { body } }).then(refresh)
          }
        />
      ) : (
        <p className="text-sm text-yt-muted">
          <Link to="/login" state={{ from: `/watch?v=${videoId}` }} className="font-medium text-yt-blue">
            Sign in
          </Link>{' '}
          to comment.
        </p>
      )}

      <div className="mt-6 flex flex-col gap-6">
        {items.map((comment) => (
          <CommentItem key={comment.id} comment={comment} videoId={videoId} />
        ))}
        {comments.isPending && <div className="h-16 animate-pulse rounded-xl bg-yt-hover" />}
        {comments.hasNextPage && (
          <button
            type="button"
            onClick={() => void comments.fetchNextPage()}
            disabled={comments.isFetchingNextPage}
            className="self-start rounded-full bg-yt-hover px-4 py-2 text-sm font-medium hover:bg-yt-active"
          >
            Show more comments
          </button>
        )}
      </div>
    </section>
  )
}
