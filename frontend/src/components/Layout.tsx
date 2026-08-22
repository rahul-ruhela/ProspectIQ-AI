/** Application shell: header, sidebar, main content and footer. */
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  Activity,
  BarChart3,
  Bell,
  Bot,
  Building2,
  ChevronDown,
  FileText,
  Kanban,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Search,
  Settings,
  Shield,
  Sun,
  Target,
  Users,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { listCompanies, listJobs, systemStatus } from '../api/endpoints'
import { useAuth } from '../store/auth'
import { useTheme } from '../store/theme'
import type { UserRole } from '../api/types'

interface NavItem {
  to: string
  label: string
  icon: typeof LayoutDashboard
  minRole?: UserRole
  end?: boolean
}

const NAV: Array<{ section: string; items: NavItem[] }> = [
  {
    section: 'Operate',
    items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
      { to: '/campaigns', label: 'Campaigns', icon: Target },
      { to: '/jobs', label: 'Research Jobs', icon: Activity },
    ],
  },
  {
    section: 'AI Department',
    items: [
      { to: '/agents', label: 'AI Employees', icon: Bot },
      { to: '/monitoring', label: 'Agent Monitoring', icon: Activity },
    ],
  },
  {
    section: 'Intelligence',
    items: [
      { to: '/companies', label: 'Companies', icon: Building2 },
      { to: '/prospects', label: 'Prospects', icon: Users },
      { to: '/reports', label: 'AI Reports', icon: FileText },
    ],
  },
  {
    section: 'Revenue',
    items: [
      { to: '/crm', label: 'CRM', icon: Kanban },
      { to: '/analytics', label: 'Analytics', icon: BarChart3 },
    ],
  },
  {
    section: 'System',
    items: [
      { to: '/admin', label: 'Administration', icon: Shield, minRole: 'admin' },
      { to: '/settings', label: 'Settings', icon: Settings },
    ],
  },
]

function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2.5 min-w-0">
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-brand-600 text-white font-bold">
        P
      </span>
      <span className="min-w-0">
        <span className="block truncate font-semibold leading-tight">ProspectIQ</span>
        <span className="block text-[10px] uppercase tracking-widest text-muted leading-tight">
          AI Sales Dept
        </span>
      </span>
    </Link>
  )
}

function GlobalSearch() {
  const [term, setTerm] = useState('')
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const boxRef = useRef<HTMLDivElement>(null)

  const { data } = useQuery({
    queryKey: ['global-search', term],
    queryFn: () => listCompanies({ q: term, page_size: 6, include_rejected: true }),
    enabled: term.trim().length >= 2,
    staleTime: 15_000,
  })

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  return (
    <div ref={boxRef} className="relative w-full max-w-md">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
      <input
        className="input pl-9"
        placeholder="Search companies, domains…"
        value={term}
        onChange={(event) => {
          setTerm(event.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
      />
      {open && term.trim().length >= 2 && (
        <div className="absolute z-40 mt-2 w-full card overflow-hidden shadow-pop">
          {!data?.items.length ? (
            <p className="px-4 py-3 text-sm text-muted">No matching companies.</p>
          ) : (
            <ul>
              {data.items.map((company) => (
                <li key={company.id}>
                  <button
                    className="w-full px-4 py-2.5 text-left row-hover"
                    onClick={() => {
                      navigate(`/companies/${company.id}`)
                      setOpen(false)
                      setTerm('')
                    }}
                  >
                    <span className="block truncate text-sm font-medium">{company.name}</span>
                    <span className="block truncate text-xs text-muted">
                      {company.domain ?? 'No domain'} · {company.country_code ?? '—'}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function Notifications() {
  const [open, setOpen] = useState(false)
  const { data } = useQuery({
    queryKey: ['jobs', 'header'],
    queryFn: () => listJobs({ page_size: 5 }),
    refetchInterval: 20_000,
  })
  const active = data?.items.filter((job) => ['queued', 'running'].includes(job.status)) ?? []

  return (
    <div className="relative">
      <button
        className="btn-ghost relative px-2"
        onClick={() => setOpen((v) => !v)}
        aria-label="Notifications"
      >
        <Bell className="h-5 w-5" />
        {active.length > 0 && (
          <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-brand-500" />
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-80 card shadow-pop">
          <p className="border-b border-app px-4 py-2.5 text-sm font-medium">Recent research jobs</p>
          {!data?.items.length ? (
            <p className="px-4 py-3 text-sm text-muted">Nothing running.</p>
          ) : (
            <ul className="max-h-72 overflow-y-auto">
              {data.items.map((job) => (
                <li key={job.id} className="border-b border-app px-4 py-3 last:border-0">
                  <Link
                    to={`/jobs/${job.id}`}
                    onClick={() => setOpen(false)}
                    className="block text-sm"
                  >
                    <span className="font-medium">{job.current_stage ?? job.status}</span>
                    <span className="mt-0.5 block text-xs text-muted">
                      {job.prospects_qualified} qualified · {Math.round(job.progress_percent)}%
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function UserMenu() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const initials = useMemo(
    () =>
      (user?.full_name ?? '?')
        .split(' ')
        .slice(0, 2)
        .map((part) => part[0]?.toUpperCase() ?? '')
        .join(''),
    [user?.full_name],
  )

  return (
    <div className="relative">
      <button className="btn-ghost gap-2 px-2" onClick={() => setOpen((v) => !v)}>
        <span className="grid h-7 w-7 place-items-center rounded-full bg-brand-600 text-xs font-semibold text-white">
          {initials}
        </span>
        <span className="hidden sm:block max-w-[9rem] truncate text-sm">{user?.full_name}</span>
        <ChevronDown className="h-4 w-4" />
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-56 card shadow-pop">
          <div className="border-b border-app px-4 py-3">
            <p className="truncate text-sm font-medium">{user?.full_name}</p>
            <p className="truncate text-xs text-muted">{user?.email}</p>
            <p className="mt-1 text-xs text-muted capitalize">{user?.role?.replace('_', ' ')}</p>
          </div>
          <button
            className="w-full px-4 py-2.5 text-left text-sm row-hover"
            onClick={() => {
              setOpen(false)
              navigate('/settings')
            }}
          >
            <Settings className="mr-2 inline h-4 w-4" />
            Settings
          </button>
          <button
            className="w-full px-4 py-2.5 text-left text-sm text-rose-600 row-hover"
            onClick={() => {
              logout()
              navigate('/login')
            }}
          >
            <LogOut className="mr-2 inline h-4 w-4" />
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { can } = useAuth()
  return (
    <nav className="flex h-full flex-col gap-6 overflow-y-auto px-3 py-5">
      {NAV.map((group) => {
        const items = group.items.filter((item) => !item.minRole || can(item.minRole))
        if (!items.length) return null
        return (
          <div key={group.section}>
            <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-widest text-muted">
              {group.section}
            </p>
            <ul className="space-y-0.5">
              {items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      clsx(
                        'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                        isActive
                          ? 'bg-brand-600 text-white'
                          : 'text-muted hover:surface-muted hover:text-inherit',
                      )
                    }
                  >
                    <item.icon className="h-4 w-4 shrink-0" />
                    <span className="truncate">{item.label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </nav>
  )
}

function Footer() {
  const { data } = useQuery({
    queryKey: ['system-status'],
    queryFn: systemStatus,
    staleTime: 60_000,
    retry: 1,
  })
  const healthy = data?.discovery_available
  return (
    <footer className="border-t border-app px-6 py-3 text-xs text-muted">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span>© {new Date().getFullYear()} ProspectIQ AI · v{data?.version ?? '1.0.0'}</span>
        <span className="flex flex-wrap items-center gap-4">
          <span className="flex items-center gap-1.5">
            <span
              className={clsx(
                'h-2 w-2 rounded-full',
                healthy === undefined ? 'bg-slate-400' : healthy ? 'bg-emerald-500' : 'bg-amber-500',
              )}
            />
            {healthy === undefined
              ? 'Checking system…'
              : healthy
                ? 'Discovery online'
                : 'No discovery connector configured'}
          </span>
          <span>
            AI reports:{' '}
            {data?.llm.available ? data.llm.smart_model : 'rules engine (no API key)'}
          </span>
          <span>Outreach requires human approval</span>
        </span>
      </div>
    </footer>
  )
}

export default function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const { theme, toggle } = useTheme()

  return (
    <div className="flex h-full flex-col">
      <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-app surface px-4 py-2.5 sm:px-6">
        <button
          className="btn-ghost px-2 lg:hidden"
          onClick={() => setMobileOpen(true)}
          aria-label="Open navigation"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="hidden w-56 shrink-0 lg:block">
          <Logo />
        </div>
        <div className="lg:hidden">
          <Logo />
        </div>
        <div className="ml-auto flex flex-1 items-center justify-end gap-2">
          <div className="hidden flex-1 justify-end md:flex">
            <GlobalSearch />
          </div>
          <button
            className="btn-ghost px-2"
            onClick={toggle}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          </button>
          <Notifications />
          <UserMenu />
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-60 shrink-0 border-r border-app surface lg:block">
          <Sidebar />
        </aside>

        {mobileOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div
              className="absolute inset-0 bg-slate-900/50"
              onClick={() => setMobileOpen(false)}
            />
            <aside className="absolute left-0 top-0 h-full w-64 surface border-r border-app">
              <div className="flex items-center justify-between px-4 py-3 border-b border-app">
                <Logo />
                <button className="btn-ghost px-2" onClick={() => setMobileOpen(false)}>
                  <X className="h-4 w-4" />
                </button>
              </div>
              <Sidebar onNavigate={() => setMobileOpen(false)} />
            </aside>
          </div>
        )}

        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8">
            <Outlet />
          </div>
          <Footer />
        </main>
      </div>
    </div>
  )
}
