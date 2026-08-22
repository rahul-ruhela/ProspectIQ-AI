import { Loader2, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { useAuth } from '../store/auth'

export default function Login() {
  const { login, status } = useAuth()
  const navigate = useNavigate()
  const location = useLocation() as { state?: { from?: string } }
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (status === 'authenticated') {
    return <Navigate to={location.state?.from ?? '/'} replace />
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email.trim(), password)
      navigate(location.state?.from ?? '/', { replace: true })
    } catch (err) {
      setError(errorMessage(err, 'Could not sign in.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2.5">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-600 text-lg font-bold text-white">
              P
            </span>
            <div>
              <p className="font-semibold leading-tight">ProspectIQ AI</p>
              <p className="text-xs uppercase tracking-widest text-muted">AI Sales Department</p>
            </div>
          </div>

          <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
          <p className="mt-1 text-sm text-muted">
            Your AI sales team has been working. Let's see what it found.
          </p>

          <form className="mt-6 space-y-4" onSubmit={onSubmit}>
            <div>
              <label className="label" htmlFor="email">
                Work email
              </label>
              <input
                id="email"
                className="input"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
            <div>
              <label className="label" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                className="input"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>

            {error && (
              <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
                {error}
              </p>
            )}

            <button className="btn-primary w-full" disabled={busy}>
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              Sign in
            </button>
          </form>

          <p className="mt-6 text-sm text-muted">
            No account yet?{' '}
            <Link className="font-medium text-brand-600 hover:underline" to="/register">
              Create your organization
            </Link>
          </p>
        </div>
      </div>

      <div className="hidden bg-brand-950 p-12 text-white lg:flex lg:flex-col lg:justify-center">
        <h2 className="max-w-md text-3xl font-semibold leading-tight">
          A sales department that never sleeps — and never invents a fact.
        </h2>
        <ul className="mt-8 max-w-md space-y-4 text-sm text-brand-100">
          <li className="flex gap-3">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-brand-300" />
            <span>
              <strong className="font-semibold text-white">Every value is sourced.</strong> Each
              company, contact and technology carries the URL it came from, a confidence score and
              the date it was verified.
            </span>
          </li>
          <li className="flex gap-3">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-brand-300" />
            <span>
              <strong className="font-semibold text-white">Unknown stays unknown.</strong> When a
              decision maker cannot be established, the platform says so instead of guessing a name.
            </span>
          </li>
          <li className="flex gap-3">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-brand-300" />
            <span>
              <strong className="font-semibold text-white">You send the email.</strong> The AI
              prepares research, drafts and call scripts. Nothing goes out without your approval.
            </span>
          </li>
        </ul>
      </div>
    </div>
  )
}
