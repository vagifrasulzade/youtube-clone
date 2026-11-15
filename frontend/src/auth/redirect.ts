/**
 * Where to go after signing in. Only same-site paths are accepted, so a crafted `from`
 * (https://evil.example, //evil.example, /\evil.example) cannot turn the login page into
 * an open redirect. Browsers treat a backslash like a slash in URLs.
 */
export function safeNext(value: unknown): string {
  if (typeof value !== 'string' || !value.startsWith('/')) return '/'
  if (value.startsWith('//') || value.startsWith('/\\')) return '/'
  return value
}
