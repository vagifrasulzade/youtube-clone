import { useMutation, useQueryClient } from '@tanstack/react-query'

import { request } from '../../api/http'
import type { components } from '../../api/schema'
import { useRequireLogin } from '../../auth/useRequireLogin'
import { LikeIcon } from '../icons'

type VideoDetail = components['schemas']['VideoDetailOut']
type ReactionOut = components['schemas']['ReactionOut']
type SubscriptionOut = components['schemas']['SubscriptionOut']

export function ReactionButtons({ video }: { video: VideoDetail }) {
  const queryClient = useQueryClient()
  const requireLogin = useRequireLogin()
  const react = useMutation({
    mutationFn: (value: 'like' | 'dislike') =>
      video.my_reaction === value
        ? request<ReactionOut>(`/videos/${video.id}/reaction`, { method: 'DELETE' })
        : request<ReactionOut>(`/videos/${video.id}/reaction`, { method: 'PUT', json: { value } }),
    onSuccess: (counts) =>
      queryClient.setQueryData<VideoDetail>(['video', video.id], (old) => old && { ...old, ...counts }),
  })

  const click = (value: 'like' | 'dislike') => {
    if (requireLogin()) react.mutate(value)
  }
  const pressed = 'bg-yt-active'

  return (
    <div className="flex items-center rounded-full bg-yt-hover text-sm font-medium">
      <button
        type="button"
        aria-pressed={video.my_reaction === 'like'}
        disabled={react.isPending}
        onClick={() => click('like')}
        className={`flex items-center gap-2 rounded-l-full px-4 py-2 hover:bg-yt-active ${video.my_reaction === 'like' ? pressed : ''}`}
      >
        <LikeIcon size={20} fill={video.my_reaction === 'like' ? 'currentColor' : 'none'} />
        {video.like_count.toLocaleString('en')}
      </button>
      <span className="h-6 w-px bg-yt-border" />
      <button
        type="button"
        aria-label="Dislike"
        aria-pressed={video.my_reaction === 'dislike'}
        disabled={react.isPending}
        onClick={() => click('dislike')}
        className={`rounded-r-full px-4 py-2 hover:bg-yt-active ${video.my_reaction === 'dislike' ? pressed : ''}`}
      >
        <LikeIcon
          size={20}
          className="rotate-180"
          fill={video.my_reaction === 'dislike' ? 'currentColor' : 'none'}
        />
      </button>
    </div>
  )
}

interface SubscribeProps {
  handle: string
  subscribed: boolean
  /** Called with the server's new state so the page can update its counters. */
  onChange: (state: SubscriptionOut) => void
}

export function SubscribeButton({ handle, subscribed, onChange }: SubscribeProps) {
  const requireLogin = useRequireLogin()
  const toggle = useMutation({
    mutationFn: () =>
      request<SubscriptionOut>(`/channels/${encodeURIComponent(handle)}/subscription`, {
        method: subscribed ? 'DELETE' : 'PUT',
      }),
    onSuccess: onChange,
  })

  return (
    <button
      type="button"
      disabled={toggle.isPending}
      onClick={() => requireLogin() && toggle.mutate()}
      className={`rounded-full px-4 py-2 text-sm font-medium ${
        subscribed ? 'bg-yt-hover hover:bg-yt-active' : 'bg-yt-text text-white hover:bg-[#272727]'
      }`}
    >
      {subscribed ? 'Subscribed' : 'Subscribe'}
    </button>
  )
}
