import axios, { AxiosError, type AxiosInstance } from 'axios'
import type { TokenPair } from './types'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'
const STORAGE_KEY = 'prospectiq.auth'

interface StoredAuth {
  access_token: string
  refresh_token: string
}

export function readStoredAuth(): StoredAuth | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as StoredAuth) : null
  } catch {
    return null
  }
}

export function writeStoredAuth(tokens: TokenPair | null): void {
  try {
    if (tokens) {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          access_token: tokens.access_token,
          refresh_token: tokens.refresh_token,
        }),
      )
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
  } catch {
    /* storage can be unavailable in private windows; the session still works in memory */
  }
}

export const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 120_000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const auth = readStoredAuth()
  if (auth?.access_token) {
    config.headers.Authorization = `Bearer ${auth.access_token}`
  }
  return config
})

let refreshInFlight: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const auth = readStoredAuth()
  if (!auth?.refresh_token) return null
  try {
    const { data } = await axios.post<TokenPair>(`${BASE_URL}/auth/refresh`, {
      refresh_token: auth.refresh_token,
    })
    writeStoredAuth(data)
    return data.access_token
  } catch {
    writeStoredAuth(null)
    return null
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (typeof error.config & { _retried?: boolean }) | undefined
    const isAuthCall = original?.url?.includes('/auth/login') || original?.url?.includes('/auth/refresh')

    if (error.response?.status === 401 && original && !original._retried && !isAuthCall) {
      original._retried = true
      // Collapse parallel 401s into a single refresh so one expiry doesn't
      // fire a refresh per in-flight request.
      refreshInFlight = refreshInFlight ?? refreshAccessToken()
      const token = await refreshInFlight
      refreshInFlight = null
      if (token) {
        original.headers = original.headers ?? {}
        ;(original.headers as Record<string, string>).Authorization = `Bearer ${token}`
        return api(original)
      }
      writeStoredAuth(null)
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

/** Turn any API failure into a message a user can act on. */
export function errorMessage(error: unknown, fallback = 'Something went wrong'): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail.length) {
      const first = detail[0] as { loc?: string[]; msg?: string }
      const field = first.loc?.slice(1).join('.') ?? ''
      return field ? `${field}: ${first.msg}` : (first.msg ?? fallback)
    }
    if (error.code === 'ECONNABORTED') return 'The request timed out.'
    if (!error.response) return 'Cannot reach the API. Is the backend running?'
    return `${error.response.status} ${error.response.statusText}`
  }
  return error instanceof Error ? error.message : fallback
}

export default api
