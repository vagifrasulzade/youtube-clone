/** "12:34" or "1:02:03" for a thumbnail duration badge. */
export function durationLabel(seconds: number | null | undefined): string {
  if (seconds == null) return ''
  const minutes = Math.floor(seconds / 60)
  const rest = String(Math.round(seconds) % 60).padStart(2, '0')
  return minutes >= 60
    ? `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}:${rest}`
    : `${minutes}:${rest}`
}
