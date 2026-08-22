/**
 * Dev-only control plane for the backend stack.
 *
 * `npm run dev` already starts a Node process that outlives every page load, so the
 * dev server is the natural place to put "start the backend for me" - a browser tab
 * cannot run Docker, but the process serving the tab can.
 *
 * Mounted only by Vite's dev server, so none of this exists in a production build.
 */
import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Connect, Plugin, ViteDevServer } from 'vite'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

/**
 * The compose frontend container publishes host port 5173 - the same port Vite dev
 * wants. Starting it here would make `npm run dev` fail to bind, so the button
 * brings up the backend services only and the browser keeps talking to Vite.
 */
const SERVICES = ['postgres', 'redis', 'backend', 'worker', 'beat', 'flower']

// Mounted at the root in app/main.py, outside the versioned API prefix.
const BACKEND_HEALTH = 'http://localhost:8000/health'
const IS_WINDOWS = process.platform === 'win32'

type Phase = 'idle' | 'starting' | 'stopping'

let phase: Phase = 'idle'
let logLines: string[] = []

function log(line: string): void {
  const trimmed = line.replace(/\s+$/, '')
  if (!trimmed) return
  logLines.push(trimmed)
  // A long `docker compose up` on a cold cache prints thousands of layer lines;
  // only the tail is ever useful and the buffer must not grow without bound.
  if (logLines.length > 400) logLines = logLines.slice(-400)
}

interface RunResult {
  code: number
  stdout: string
  stderr: string
}

function run(command: string, args: string[], opts: { stream?: boolean } = {}): Promise<RunResult> {
  return new Promise((resolve) => {
    // spawn on Windows does not resolve PATHEXT, so `docker` alone would not be
    // found without a shell. Every argument here is a literal, never user input.
    const child = spawn(command, args, {
      cwd: ROOT,
      shell: IS_WINDOWS,
      windowsHide: true,
    })
    let stdout = ''
    let stderr = ''
    child.stdout?.on('data', (chunk: Buffer) => {
      const text = chunk.toString()
      stdout += text
      if (opts.stream) text.split('\n').forEach(log)
    })
    child.stderr?.on('data', (chunk: Buffer) => {
      const text = chunk.toString()
      stderr += text
      // Compose writes its progress to stderr, so this is normal output, not failure.
      if (opts.stream) text.split('\n').forEach(log)
    })
    child.on('error', (err) => {
      if (opts.stream) log(`! ${err.message}`)
      resolve({ code: -1, stdout, stderr: String(err) })
    })
    child.on('close', (code) => resolve({ code: code ?? -1, stdout, stderr }))
  })
}

async function backendUp(): Promise<boolean> {
  try {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 2000)
    const res = await fetch(BACKEND_HEALTH, { signal: controller.signal })
    clearTimeout(timer)
    return res.ok
  } catch {
    return false
  }
}

interface ServiceState {
  name: string
  state: string
  running: boolean
}

async function composePs(): Promise<ServiceState[]> {
  const res = await run('docker', ['compose', 'ps', '--format', 'json'])
  if (res.code !== 0) return []
  // Compose emits either one JSON array or newline-delimited objects depending on
  // version, so both shapes are accepted.
  const text = res.stdout.trim()
  if (!text) return []
  const rows: Record<string, unknown>[] = []
  try {
    const parsed = JSON.parse(text)
    if (Array.isArray(parsed)) rows.push(...parsed)
    else rows.push(parsed)
  } catch {
    for (const line of text.split('\n')) {
      if (!line.trim()) continue
      try {
        rows.push(JSON.parse(line))
      } catch {
        /* a partial line is not worth failing the whole status call */
      }
    }
  }
  return rows.map((r) => {
    const state = String(r.State ?? r.state ?? 'unknown')
    return {
      name: String(r.Service ?? r.Name ?? 'unknown'),
      state,
      running: state.toLowerCase().startsWith('running') || state.toLowerCase() === 'up',
    }
  })
}

async function status() {
  const version = await run('docker', ['version', '--format', '{{.Server.Version}}'])
  const dockerReady = version.code === 0
  const services = dockerReady ? await composePs() : []
  const running = services.filter((s) => s.running).map((s) => s.name)
  const api = await backendUp()
  return {
    phase,
    docker: {
      available: dockerReady,
      version: dockerReady ? version.stdout.trim() : null,
      error: dockerReady ? null : (version.stderr || 'Docker is not running.').slice(0, 300),
    },
    services,
    expected: SERVICES,
    // "ready" means the thing the UI actually needs: an API answering on 8000.
    ready: api,
    api_url: BACKEND_HEALTH,
    missing: SERVICES.filter((s) => !running.includes(s)),
    logs: logLines.slice(-120),
  }
}

function json(res: Parameters<Connect.NextHandleFunction>[1], body: unknown, code = 200): void {
  res.statusCode = code
  res.setHeader('Content-Type', 'application/json')
  res.end(JSON.stringify(body))
}

/** Only loopback callers may drive Docker; `server.host` can expose Vite to the LAN. */
function isLocal(req: Parameters<Connect.NextHandleFunction>[0]): boolean {
  const addr = req.socket.remoteAddress ?? ''
  return addr === '127.0.0.1' || addr === '::1' || addr === '::ffff:127.0.0.1'
}

export function devStackPlugin(): Plugin {
  return {
    name: 'prospectiq-devstack',
    apply: 'serve',
    configureServer(server: ViteDevServer) {
      server.middlewares.use('/__devstack', (req, res, next) => {
        const url = (req.url ?? '/').split('?')[0]

        if (!isLocal(req)) {
          json(res, { error: 'Only localhost may control the dev stack.' }, 403)
          return
        }

        if (url === '/status') {
          void status().then((s) => json(res, s))
          return
        }

        if (url === '/start' && req.method === 'POST') {
          if (phase !== 'idle') {
            void status().then((s) => json(res, s))
            return
          }
          phase = 'starting'
          logLines = []
          log('$ docker compose up -d ' + SERVICES.join(' '))
          void run('docker', ['compose', 'up', '-d', ...SERVICES], { stream: true })
            .then((r) => {
              log(r.code === 0 ? '✓ compose finished' : `! compose exited ${r.code}`)
            })
            .finally(() => {
              phase = 'idle'
            })
          // Answer immediately: a cold start pulls images and can take minutes,
          // and the UI polls /status for progress rather than holding a request open.
          json(res, { started: true })
          return
        }

        if (url === '/stop' && req.method === 'POST') {
          if (phase !== 'idle') {
            json(res, { stopped: false, busy: true })
            return
          }
          phase = 'stopping'
          log('$ docker compose stop ' + SERVICES.join(' '))
          void run('docker', ['compose', 'stop', ...SERVICES], { stream: true })
            .then((r) => log(r.code === 0 ? '✓ stopped' : `! stop exited ${r.code}`))
            .finally(() => {
              phase = 'idle'
            })
          json(res, { stopped: true })
          return
        }

        next()
      })
    },
  }
}
