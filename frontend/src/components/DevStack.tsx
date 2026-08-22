/**
 * Dev-only gate that starts the backend stack from the browser.
 *
 * Without it, `npm run dev` renders a login page that cannot reach an API, and the
 * only cue is a failed network request. This blocks the app behind one button until
 * the API answers, and reports what Docker is actually doing while it comes up.
 *
 * The endpoints live in the Vite dev server (see `frontend/devstack.plugin.ts`) and
 * do not exist in a production build, so this component renders nothing there.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

interface ServiceState {
  name: string
  state: string
  running: boolean
}

interface StackStatus {
  phase: 'idle' | 'starting' | 'stopping'
  docker: { available: boolean; version: string | null; error: string | null }
  services: ServiceState[]
  expected: string[]
  ready: boolean
  api_url: string
  missing: string[]
  logs: string[]
}

const POLL_IDLE_MS = 4000
const POLL_BUSY_MS = 1500

export default function DevStack({ children }: { children: React.ReactNode }) {
  // import.meta.env.DEV is compiled to a literal, so the whole gate drops out of a
  // production bundle rather than shipping dead code.
  if (!import.meta.env.DEV) return <>{children}</>
  return <DevStackGate>{children}</DevStackGate>
}

function DevStackGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<StackStatus | null>(null)
  const [starting, setStarting] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const [showLogs, setShowLogs] = useState(false)
  const logRef = useRef<HTMLPreElement>(null)

  const poll = useCallback(async () => {
    try {
      const res = await fetch('/__devstack/status')
      if (!res.ok) return null
      const data = (await res.json()) as StackStatus
      setStatus(data)
      return data
    } catch {
      // The plugin is missing (production preview, or a custom dev server). Treat
      // that as "not our business" rather than blocking the app forever.
      setStatus(null)
      setDismissed(true)
      return null
    }
  }, [])

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>
    let cancelled = false

    const loop = async () => {
      const data = await poll()
      if (cancelled) return
      const busy = starting || data?.phase !== 'idle'
      timer = setTimeout(loop, busy ? POLL_BUSY_MS : POLL_IDLE_MS)
    }
    void loop()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [poll, starting])

  // Once the API answers, stop showing the gate for the rest of the session.
  useEffect(() => {
    if (status?.ready) setStarting(false)
  }, [status?.ready])

  useEffect(() => {
    if (showLogs && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [status?.logs, showLogs])

  const start = async () => {
    setStarting(true)
    setShowLogs(true)
    await fetch('/__devstack/start', { method: 'POST' })
    void poll()
  }

  if (dismissed || status?.ready) return <>{children}</>
  if (!status) return <>{children}</>

  const busy = starting || status.phase === 'starting'
  const dockerDown = !status.docker.available

  return (
    <div className="min-h-screen bg-slate-950 px-4 py-10 text-slate-100">
      <div className="mx-auto w-full max-w-2xl space-y-6">
        <header className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-widest text-sky-400">
            ProspectIQ · local development
          </p>
          <h1 className="text-2xl font-semibold">The backend is not running yet</h1>
          <p className="text-sm text-slate-400">
            The UI is live on this page, but it needs the API on{' '}
            <code className="rounded bg-slate-800 px-1.5 py-0.5 text-xs">localhost:8000</code>.
            Start the whole stack — Postgres, Redis, API, workers — with one button.
          </p>
        </header>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 shadow-xl">
          {dockerDown ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-amber-400">
                <span className="h-2 w-2 rounded-full bg-amber-400" />
                <span className="text-sm font-medium">Docker Desktop is not running</span>
              </div>
              <p className="text-sm text-slate-400">
                Start Docker Desktop, then this panel will pick it up automatically.
              </p>
              {status.docker.error ? (
                <pre className="overflow-x-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-500">
                  {status.docker.error}
                </pre>
              ) : null}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-2 text-sm text-slate-300">
                  <span className="h-2 w-2 rounded-full bg-emerald-400" />
                  Docker {status.docker.version} ready
                </div>
                <button
                  type="button"
                  onClick={() => void start()}
                  disabled={busy}
                  className="rounded-lg bg-sky-500 px-5 py-2.5 text-sm font-semibold text-white shadow transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
                >
                  {busy ? 'Starting…' : 'Start backend'}
                </button>
              </div>

              <ul className="grid gap-2 sm:grid-cols-2">
                {status.expected.map((name) => {
                  const svc = status.services.find((s) => s.name === name)
                  const up = Boolean(svc?.running)
                  return (
                    <li
                      key={name}
                      className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm"
                    >
                      <span
                        className={[
                          'h-2 w-2 rounded-full',
                          up ? 'bg-emerald-400' : busy ? 'animate-pulse bg-sky-400' : 'bg-slate-600',
                        ].join(' ')}
                      />
                      <span className="font-medium text-slate-200">{name}</span>
                      <span className="ml-auto text-xs text-slate-500">
                        {svc?.state ?? 'stopped'}
                      </span>
                    </li>
                  )
                })}
              </ul>

              {busy ? (
                <p className="text-xs text-slate-500">
                  First run pulls images and builds the API — this can take a few minutes.
                  Progress appears below.
                </p>
              ) : null}
            </div>
          )}
        </div>

        {status.logs.length > 0 ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900/60">
            <button
              type="button"
              onClick={() => setShowLogs((v) => !v)}
              className="flex w-full items-center justify-between px-4 py-3 text-sm text-slate-300"
            >
              <span>Docker output</span>
              <span className="text-xs text-slate-500">{showLogs ? 'hide' : 'show'}</span>
            </button>
            {showLogs ? (
              <pre
                ref={logRef}
                className="max-h-64 overflow-auto border-t border-slate-800 px-4 py-3 text-xs leading-relaxed text-slate-400"
              >
                {status.logs.join('\n')}
              </pre>
            ) : null}
          </div>
        ) : null}

        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="text-xs text-slate-500 underline underline-offset-4 hover:text-slate-300"
        >
          Skip — I run the backend myself
        </button>
      </div>
    </div>
  )
}
