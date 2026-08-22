import { create } from 'zustand'
import { readStoredAuth, writeStoredAuth } from '../api/client'
import * as apiFns from '../api/endpoints'
import type { User, UserRole } from '../api/types'

const ROLE_RANK: Record<UserRole, number> = {
  admin: 40,
  researcher: 30,
  sales_user: 20,
  viewer: 10,
}

interface AuthState {
  user: User | null
  status: 'idle' | 'loading' | 'authenticated' | 'anonymous'
  error: string | null
  login: (email: string, password: string) => Promise<void>
  register: (payload: {
    email: string
    password: string
    full_name: string
    organization_name: string
  }) => Promise<void>
  logout: () => void
  bootstrap: () => Promise<void>
  can: (minimum: UserRole) => boolean
}

export const useAuth = create<AuthState>((set, get) => ({
  user: null,
  status: 'idle',
  error: null,

  async login(email, password) {
    set({ status: 'loading', error: null })
    try {
      const result = await apiFns.login(email, password)
      writeStoredAuth(result.tokens)
      set({ user: result.user, status: 'authenticated' })
    } catch (error) {
      set({ status: 'anonymous' })
      throw error
    }
  },

  async register(payload) {
    set({ status: 'loading', error: null })
    try {
      const result = await apiFns.register(payload)
      writeStoredAuth(result.tokens)
      set({ user: result.user, status: 'authenticated' })
    } catch (error) {
      set({ status: 'anonymous' })
      throw error
    }
  },

  logout() {
    writeStoredAuth(null)
    set({ user: null, status: 'anonymous' })
  },

  /** Restore a session from stored tokens on first paint. */
  async bootstrap() {
    if (!readStoredAuth()) {
      set({ status: 'anonymous' })
      return
    }
    set({ status: 'loading' })
    try {
      const user = await apiFns.me()
      set({ user, status: 'authenticated' })
    } catch {
      writeStoredAuth(null)
      set({ user: null, status: 'anonymous' })
    }
  },

  can(minimum) {
    const role = get().user?.role
    if (!role) return false
    return ROLE_RANK[role] >= ROLE_RANK[minimum]
  },
}))
