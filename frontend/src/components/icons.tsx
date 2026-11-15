// Inline SVG icons (24x24, currentColor). Paths drawn for this project.
import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & { size?: number }

function Icon({ size = 24, children, ...rest }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  )
}

export const MenuIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 6h18M3 12h18M3 18h18" />
  </Icon>
)

export const SearchIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="10.5" cy="10.5" r="6.5" />
    <path d="m20 20-4.8-4.8" />
  </Icon>
)

export const HomeIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 10.5 12 4l8 6.5V20h-5.5v-5.5h-5V20H4z" />
  </Icon>
)

export const SubscriptionsIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3" y="8" width="18" height="12" rx="2" />
    <path d="M6 5h12M8 2.5h8" />
    <path d="m10.5 11.5 4 2.5-4 2.5z" fill="currentColor" />
  </Icon>
)

export const HistoryIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3.5 12a8.5 8.5 0 1 0 2.5-6" />
    <path d="M3 4v4h4" />
    <path d="M12 7.5V12l3 2" />
  </Icon>
)

export const LikeIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M7 10v10H4V10zM7 10l4-7c1.5 0 2.5 1 2.2 2.6L12.6 9H19a2 2 0 0 1 2 2.3l-1.2 6.8A2.2 2.2 0 0 1 17.6 20H7" />
  </Icon>
)

export const PlaylistIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 6h12M3 11h12M3 16h7" />
    <path d="m15 14 6 3.5-6 3.5z" fill="currentColor" />
  </Icon>
)

export const ChannelIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2.5" />
    <circle cx="12" cy="10.5" r="2.5" />
    <path d="M7.5 17c1-2 2.6-3 4.5-3s3.5 1 4.5 3" />
  </Icon>
)

export const CreateIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
)

export const UserIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="9.5" />
    <circle cx="12" cy="10" r="3.2" />
    <path d="M6 18.5c1.4-2.3 3.5-3.5 6-3.5s4.6 1.2 6 3.5" />
  </Icon>
)

export const ShieldIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 3 4.5 6v5.5c0 4.6 3.1 8.2 7.5 9.5 4.4-1.3 7.5-4.9 7.5-9.5V6z" />
  </Icon>
)

export const EyeIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
    <circle cx="12" cy="12" r="3" />
  </Icon>
)

export const EyeOffIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M10.6 5.6c.5-.1.9-.1 1.4-.1 6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-2.6 3.4" />
    <path d="M6.6 6.6C4 8.3 2.5 12 2.5 12S6 18.5 12 18.5c1.9 0 3.6-.6 5-1.5" />
    <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
    <path d="m3 3 18 18" />
  </Icon>
)

/** The play badge used in the logo. */
export function PlayBadge({ size = 28 }: { size?: number }) {
  return (
    <svg width={size * 1.4} height={size} viewBox="0 0 28 20" aria-hidden="true">
      <rect width="28" height="20" rx="5" fill="var(--color-yt-red)" />
      <path d="M11 6v8l7-4z" fill="#fff" />
    </svg>
  )
}
