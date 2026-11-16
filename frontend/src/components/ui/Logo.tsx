import { APP_NAME } from '../../brand'
import { PlayBadge } from '../icons'

/**
 * "YouTube" with a small "CLONE" mark where YouTube shows its country code: it looks like
 * the original, but nobody can mistake this demo (and its sign-in page) for the real site.
 */
export function Logo({ size = 20 }: { size?: number }) {
  return (
    <span className="flex items-center gap-1" aria-label={APP_NAME}>
      <PlayBadge size={size} />
      <span className="text-xl font-bold tracking-tighter">YouTube</span>
      <sup className="-ml-0.5 self-start pt-1 text-[10px] font-medium uppercase text-yt-muted">clone</sup>
    </span>
  )
}
