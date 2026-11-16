import { type FormEvent, type ReactNode, useId, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router'

import { describeError } from '../api/http'
import { useAuth } from '../auth/context'
import { safeNext } from '../auth/redirect'
import { APP_NAME } from '../brand'
import { EyeIcon, EyeOffIcon } from '../components/icons'
import { Logo } from '../components/ui/Logo'
import { usePageTitle } from '../hooks/usePageTitle'

function Card({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f0f4f9] px-4">
      <div className="w-full max-w-md rounded-3xl bg-white p-8 shadow-sm">
        <Link to="/" aria-label="Home" className="mb-6 flex items-center">
          <Logo size={24} />
        </Link>
        <h1 className="text-3xl">{title}</h1>
        <p className="mt-2 mb-6 text-yt-muted">{subtitle}</p>
        {children}
      </div>
    </div>
  )
}

function Field(props: {
  label: string
  name: string
  type?: string
  value: string
  onChange: (value: string) => void
  autoComplete?: string
  hint?: string
  minLength?: number
  maxLength?: number
  pattern?: string
}) {
  const { label, onChange, hint, type, ...input } = props
  const id = useId()
  const isPassword = type === 'password'
  const [visible, setVisible] = useState(false)
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium">
        {label}
      </label>
      <div className="relative">
        <input
          {...input}
          id={id}
          type={isPassword && visible ? 'text' : type}
          required
          onChange={(event) => onChange(event.target.value)}
          className={`w-full rounded-md border border-yt-border px-3 py-2.5 outline-none focus:border-yt-blue focus:ring-1 focus:ring-yt-blue ${
            isPassword ? 'pr-11' : ''
          }`}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            aria-label={visible ? 'Hide password' : 'Show password'}
            aria-pressed={visible}
            aria-controls={id}
            className="absolute inset-y-0 right-1 my-auto flex size-9 items-center justify-center rounded-full text-yt-muted hover:bg-yt-hover hover:text-yt-text"
          >
            {visible ? <EyeOffIcon size={20} /> : <EyeIcon size={20} />}
          </button>
        )}
      </div>
      {hint && <span className="mt-1 block text-xs text-yt-muted">{hint}</span>}
    </div>
  )
}

function Submit({ busy, children }: { busy: boolean; children: ReactNode }) {
  return (
    <button
      type="submit"
      disabled={busy}
      className="rounded-full bg-yt-blue px-6 py-2.5 text-sm font-medium text-white hover:bg-[#0556bf] disabled:opacity-60"
    >
      {busy ? 'Please wait…' : children}
    </button>
  )
}

export function LoginPage() {
  usePageTitle('Sign in')
  const { login, user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const next = safeNext((location.state as { from?: string } | null)?.from)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to={next} replace />

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email, password)
      navigate(next, { replace: true })
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="Sign in" subtitle={`to continue to ${APP_NAME}`}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Email" name="email" type="email" value={email} onChange={setEmail} autoComplete="email" />
        <Field
          label="Password"
          name="password"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
        />
        {error && (
          <p role="alert" className="text-sm text-[#d93025]">
            {error}
          </p>
        )}
        <div className="mt-2 flex items-center justify-between">
          <Link to="/register" state={location.state} className="text-sm font-medium text-yt-blue">
            Create account
          </Link>
          <Submit busy={busy}>Next</Submit>
        </div>
      </form>
    </Card>
  )
}

export function RegisterPage() {
  usePageTitle('Create account')
  const { register, user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const next = safeNext((location.state as { from?: string } | null)?.from)
  const [form, setForm] = useState({ display_name: '', handle: '', email: '', password: '' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to={next} replace />

  const set = (key: keyof typeof form) => (value: string) => setForm((f) => ({ ...f, [key]: value }))

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      // People often type the handle the way it is displayed ("@name").
      await register({ ...form, handle: form.handle.trim().replace(/^@/, '').toLowerCase() })
      navigate(next, { replace: true })
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="Create your account" subtitle="Your account comes with a channel">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field
          label="Channel name"
          name="display_name"
          value={form.display_name}
          onChange={set('display_name')}
          maxLength={50}
          autoComplete="nickname"
        />
        <Field
          label="Handle"
          name="handle"
          value={form.handle}
          onChange={set('handle')}
          pattern="@?[A-Za-z0-9._\-]{3,30}"
          hint="3–30 letters, numbers, dots, dashes or underscores. Your channel will be at /@handle."
          autoComplete="username"
        />
        <Field label="Email" name="email" type="email" value={form.email} onChange={set('email')} autoComplete="email" />
        <Field
          label="Password"
          name="password"
          type="password"
          value={form.password}
          onChange={set('password')}
          minLength={8}
          maxLength={128}
          hint="At least 8 characters"
          autoComplete="new-password"
        />
        {error && (
          <p role="alert" className="text-sm text-[#d93025]">
            {error}
          </p>
        )}
        <div className="mt-2 flex items-center justify-between">
          <Link to="/login" state={location.state} className="text-sm font-medium text-yt-blue">
            Sign in instead
          </Link>
          <Submit busy={busy}>Create account</Submit>
        </div>
      </form>
    </Card>
  )
}
