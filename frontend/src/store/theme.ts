import { create } from 'zustand'

type Theme = 'light' | 'dark'
const STORAGE_KEY = 'prospectiq.theme'

function readTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch {
    /* private windows can block storage; fall through to the system preference */
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark')
  try {
    localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    /* non-fatal */
  }
}

interface ThemeState {
  theme: Theme
  toggle: () => void
  init: () => void
}

export const useTheme = create<ThemeState>((set, get) => ({
  theme: 'light',
  toggle() {
    const next: Theme = get().theme === 'dark' ? 'light' : 'dark'
    applyTheme(next)
    set({ theme: next })
  },
  init() {
    const theme = readTheme()
    applyTheme(theme)
    set({ theme })
  },
}))
