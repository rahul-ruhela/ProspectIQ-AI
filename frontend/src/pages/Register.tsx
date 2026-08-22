import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { useAuth } from '../store/auth'

export default function Register() {
  const { register, status } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({
    full_name: '',
    organization_name: '',
    email: '',
    password: '',
  })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (status === 'authenticated') return <Navigate to="/" replace />

  const set = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }))

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (form.password.length < 10) {
      setError('Password must be at least 10 characters.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await register({ ...form, email: form.email.trim() })
      navigate('/', { replace: true })
    } catch (err) {
      setError(errorMessage(err, 'Could not create your account.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="mb-8 flex items-center gap-2.5">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-600 text-lg font-bold text-white">
            P
          </span>
          <div>
            <p className="font-semibold leading-tight">ProspectIQ AI</p>
            <p className="text-xs uppercase tracking-widest text-muted">AI Sales Department</p>
          </div>
        </div>

        <h1 className="text-2xl font-semibold tracking-tight">Create your organization</h1>
        <p className="mt-1 text-sm text-muted">
          The first account becomes the administrator and can invite the rest of the team.
        </p>

        <form className="mt-6 space-y-4" onSubmit={onSubmit}>
          <div>
            <label className="label" htmlFor="full_name">
              Your name
            </label>
            <input id="full_name" className="input" required value={form.full_name} onChange={set('full_name')} />
          </div>
          <div>
            <label className="label" htmlFor="organization_name">
              Organization
            </label>
            <input
              id="organization_name"
              className="input"
              required
              value={form.organization_name}
              onChange={set('organization_name')}
            />
          </div>
          <div>
            <label className="label" htmlFor="email">
              Work email
            </label>
            <input id="email" className="input" type="email" required value={form.email} onChange={set('email')} />
          </div>
          <div>
            <label className="label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              className="input"
              type="password"
              required
              minLength={10}
              value={form.password}
              onChange={set('password')}
            />
            <p className="mt-1 text-xs text-muted">At least 10 characters.</p>
          </div>

          {error && (
            <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
              {error}
            </p>
          )}

          <button className="btn-primary w-full" disabled={busy}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            Create organization
          </button>
        </form>

        <p className="mt-6 text-sm text-muted">
          Already have an account?{' '}
          <Link className="font-medium text-brand-600 hover:underline" to="/login">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
