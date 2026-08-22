import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertTriangle, Check, CheckCircle2, Loader2, Moon, Sun } from 'lucide-react'
import { useState } from 'react'
import { errorMessage } from '../api/client'
import { changePassword, systemStatus } from '../api/endpoints'
import { Card, PageHeader, titleCase } from '../components/ui'
import { useAuth } from '../store/auth'
import { useTheme } from '../store/theme'

export default function SettingsPage() {
  const { user } = useAuth()
  const { theme, toggle } = useTheme()
  const status = useQuery({ queryKey: ['system-status'], queryFn: systemStatus, retry: 1 })

  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const change = useMutation({
    mutationFn: () => changePassword(current, next),
    onSuccess: () => {
      setMessage('Password updated.')
      setError(null)
      setCurrent('')
      setNext('')
    },
    onError: (err) => {
      setError(errorMessage(err))
      setMessage(null)
    },
  })

  return (
    <>
      <PageHeader title="Settings" subtitle="Your profile, appearance and what the platform can currently do." />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Profile">
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-muted">Name</dt>
              <dd>{user?.full_name}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted">Email</dt>
              <dd>{user?.email}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted">Role</dt>
              <dd>{titleCase(user?.role ?? '')}</dd>
            </div>
          </dl>
        </Card>

        <Card title="Appearance">
          <button className="btn-secondary" onClick={toggle}>
            {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            Switch to {theme === 'dark' ? 'light' : 'dark'} mode
          </button>
          <p className="mt-3 text-sm text-muted">
            Your choice is remembered in this browser. Without one, the platform follows your
            operating system.
          </p>
        </Card>

        <Card title="Change password">
          <div className="space-y-4">
            <div>
              <label className="label" htmlFor="current">
                Current password
              </label>
              <input
                id="current"
                className="input"
                type="password"
                value={current}
                onChange={(event) => setCurrent(event.target.value)}
              />
            </div>
            <div>
              <label className="label" htmlFor="next">
                New password
              </label>
              <input
                id="next"
                className="input"
                type="password"
                value={next}
                onChange={(event) => setNext(event.target.value)}
              />
              <p className="mt-1 text-xs text-muted">At least 10 characters.</p>
            </div>
            {message && (
              <p className="flex items-center gap-2 text-sm text-emerald-600">
                <Check className="h-4 w-4" />
                {message}
              </p>
            )}
            {error && (
              <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
                {error}
              </p>
            )}
            <button
              className="btn-primary"
              disabled={!current || next.length < 10 || change.isPending}
              onClick={() => change.mutate()}
            >
              {change.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Update password
            </button>
          </div>
        </Card>

        <Card title="System capability" description="What the platform can do with its current configuration">
          {status.isLoading ? (
            <p className="text-sm text-muted">Checking…</p>
          ) : status.isError ? (
            <p className="text-sm text-muted">Could not reach the API.</p>
          ) : (
            <div className="space-y-4 text-sm">
              <div>
                <p className="font-medium">Report synthesis</p>
                <p className="mt-0.5 flex items-start gap-2 text-muted">
                  {status.data!.llm.available ? (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                  ) : (
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                  )}
                  {status.data!.llm.available
                    ? `${status.data!.llm.smart_model} for qualified prospects, ${status.data!.llm.cheap_model} for planning.`
                    : status.data!.llm.note}
                </p>
              </div>
              <div>
                <p className="font-medium">Discovery sources</p>
                <ul className="mt-1 space-y-1">
                  {status.data!.discovery_connectors.map((connector) => (
                    <li key={connector.slug} className="flex items-start gap-2 text-muted">
                      {connector.available ? (
                        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                      ) : (
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                      )}
                      <span>
                        <strong className="font-medium">{connector.name}</strong> — {connector.reason}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="font-medium">Crawling</p>
                <p className="mt-0.5 text-muted">
                  robots.txt {status.data!.respect_robots_txt ? 'respected' : 'ignored'} · JavaScript
                  rendering {status.data!.playwright_rendering ? 'enabled' : 'disabled'}
                </p>
              </div>
            </div>
          )}
        </Card>
      </div>
    </>
  )
}
