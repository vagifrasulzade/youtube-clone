const COLORS = ['#5c6bc0', '#26a69a', '#ef6c00', '#8e24aa', '#00897b', '#d81b60', '#3949ab']

function colorFor(name: string): string {
  let hash = 0
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) | 0
  return COLORS[Math.abs(hash) % COLORS.length]
}

interface AvatarProps {
  name: string
  url: string | null | undefined
  size?: number
}

/** Channel avatar; falls back to a colored circle with the first letter (like YouTube). */
export function Avatar({ name, url, size = 36 }: AvatarProps) {
  const style = { width: size, height: size }
  if (url) {
    return <img src={url} alt="" style={style} className="shrink-0 rounded-full object-cover" />
  }
  return (
    <div
      style={{ ...style, backgroundColor: colorFor(name), fontSize: size * 0.42 }}
      className="flex shrink-0 items-center justify-center rounded-full font-medium text-white"
    >
      {name.charAt(0).toUpperCase()}
    </div>
  )
}
