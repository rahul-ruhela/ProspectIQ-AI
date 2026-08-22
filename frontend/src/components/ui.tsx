/** Shared presentational primitives: badges, states, tables, cards, modals. */
import clsx from 'clsx'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  HelpCircle,
  Inbox,
  Loader2,
  ShieldAlert,
  X,
} from 'lucide-react'
import { type ReactNode, useEffect } from 'react'
import type { Certainty, ScoreCategory, VerificationStatus } from '../api/types'

// --- text helpers ---------------------------------------------------------

export function titleCase(value: string | null | undefined): string {
  if (!value) return ''
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function formatMoney(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return '—'
  return `$${value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString()
}

export function relativeTime(value: string | null | undefined): string {
  if (!value) return '—'
  const then = new Date(value).getTime()
  if (Number.isNaN(then)) return '—'
  const seconds = Math.round((Date.now() - then) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days}d ago`
  return formatDate(value)
}

// --- badges ---------------------------------------------------------------

const SCORE_STYLES: Record<ScoreCategory, string> = {
  exceptional: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-400/20',
  high_priority: 'bg-sky-50 text-sky-700 ring-sky-600/20 dark:bg-sky-500/10 dark:text-sky-300 dark:ring-sky-400/20',
  medium: 'bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-400/20',
  low: 'bg-orange-50 text-orange-700 ring-orange-600/20 dark:bg-orange-500/10 dark:text-orange-300 dark:ring-orange-400/20',
  poor: 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-500/10 dark:text-slate-300 dark:ring-slate-400/20',
}

export function ScoreBadge({
  score,
  category,
}: {
  score: number | null | undefined
  category: ScoreCategory | null | undefined
}) {
  if (score === null || score === undefined) {
    return <span className="badge bg-slate-100 text-slate-500 ring-slate-500/20 dark:bg-slate-500/10 dark:text-slate-400">Not scored</span>
  }
  const cat = category ?? 'poor'
  return (
    <span className={clsx('badge tabular-nums', SCORE_STYLES[cat])}>
      {Math.round(score)}
      <span className="opacity-70">/100</span>
      <span className="hidden sm:inline">· {titleCase(cat)}</span>
    </span>
  )
}

const STATUS_STYLES: Record<string, string> = {
  verified: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-300',
  needs_verification: 'bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-300',
  unknown: 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-500/10 dark:text-slate-300',
  rejected: 'bg-rose-50 text-rose-700 ring-rose-600/20 dark:bg-rose-500/10 dark:text-rose-300',
}

export function VerificationBadge({ status }: { status: VerificationStatus }) {
  const icon =
    status === 'verified' ? (
      <CheckCircle2 className="h-3 w-3" />
    ) : status === 'rejected' ? (
      <ShieldAlert className="h-3 w-3" />
    ) : (
      <HelpCircle className="h-3 w-3" />
    )
  return (
    <span className={clsx('badge', STATUS_STYLES[status] ?? STATUS_STYLES.unknown)}>
      {icon}
      {titleCase(status)}
    </span>
  )
}

const CERTAINTY_STYLES: Record<Certainty, string> = {
  observed: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-300',
  likely: 'bg-sky-50 text-sky-700 ring-sky-600/20 dark:bg-sky-500/10 dark:text-sky-300',
  possible: 'bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-300',
  unknown: 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-500/10 dark:text-slate-300',
}

export function CertaintyBadge({ certainty }: { certainty: Certainty }) {
  return (
    <span className={clsx('badge', CERTAINTY_STYLES[certainty] ?? CERTAINTY_STYLES.unknown)}>
      {titleCase(certainty)}
    </span>
  )
}

const GENERIC_STATUS: Record<string, string> = {
  running: 'bg-brand-50 text-brand-700 ring-brand-600/20 dark:bg-brand-500/10 dark:text-brand-300',
  processing: 'bg-brand-50 text-brand-700 ring-brand-600/20 dark:bg-brand-500/10 dark:text-brand-300',
  queued: 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-500/10 dark:text-slate-300',
  pending: 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-500/10 dark:text-slate-300',
  assigned: 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-500/10 dark:text-slate-300',
  idle: 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-500/10 dark:text-slate-300',
  waiting: 'bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-300',
  paused: 'bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-300',
  completed: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-300',
  active: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-300',
  failed: 'bg-rose-50 text-rose-700 ring-rose-600/20 dark:bg-rose-500/10 dark:text-rose-300',
  cancelled: 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-500/10 dark:text-slate-300',
  skipped: 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-500/10 dark:text-slate-300',
  disabled: 'bg-slate-100 text-slate-500 ring-slate-500/20 dark:bg-slate-500/10 dark:text-slate-400',
  draft: 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-500/10 dark:text-slate-300',
  archived: 'bg-slate-100 text-slate-500 ring-slate-500/20 dark:bg-slate-500/10 dark:text-slate-400',
}

export function StatusBadge({ status, pulse }: { status: string; pulse?: boolean }) {
  const live = pulse ?? ['running', 'processing'].includes(status)
  return (
    <span className={clsx('badge', GENERIC_STATUS[status] ?? GENERIC_STATUS.idle)}>
      {live && <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />}
      {titleCase(status)}
    </span>
  )
}

export function ConfidenceMeter({ value }: { value: number | null | undefined }) {
  const pct = Math.round(Math.max(0, Math.min(1, value ?? 0)) * 100)
  const tone = pct >= 80 ? 'bg-emerald-500' : pct >= 55 ? 'bg-amber-500' : 'bg-rose-500'
  return (
    <span className="inline-flex items-center gap-2" title={`Confidence ${pct}%`}>
      <span className="h-1.5 w-14 rounded-full surface-muted overflow-hidden">
        <span className={clsx('block h-full rounded-full', tone)} style={{ width: `${pct}%` }} />
      </span>
      <span className="text-xs text-muted tabular-nums">{pct}%</span>
    </span>
  )
}

// --- layout pieces --------------------------------------------------------

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted max-w-3xl">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Card({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode
  description?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section className={clsx('card', className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-app px-5 py-4">
          <div className="min-w-0">
            {title && <h2 className="font-semibold">{title}</h2>}
            {description && <p className="text-sm text-muted mt-0.5">{description}</p>}
          </div>
          {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
        </header>
      )}
      <div className={clsx('p-5', bodyClassName)}>{children}</div>
    </section>
  )
}

export function StatTile({
  label,
  value,
  hint,
  icon,
  tone = 'default',
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  icon?: ReactNode
  tone?: 'default' | 'positive' | 'warning'
}) {
  return (
    <div className="card p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-muted">{label}</p>
        {icon && <span className="text-muted">{icon}</span>}
      </div>
      <p
        className={clsx(
          'mt-2 text-3xl font-semibold tabular-nums tracking-tight',
          tone === 'positive' && 'text-emerald-600 dark:text-emerald-400',
          tone === 'warning' && 'text-amber-600 dark:text-amber-400',
        )}
      >
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  )
}

// --- states ---------------------------------------------------------------

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-14 text-muted">
      <Loader2 className="h-5 w-5 animate-spin" />
      <span className="text-sm">{label}</span>
    </div>
  )
}

export function SkeletonRows({ rows = 5, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2 p-4">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3">
          {Array.from({ length: cols }).map((__, c) => (
            <div key={c} className="skeleton h-6 flex-1" />
          ))}
        </div>
      ))}
    </div>
  )
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-14 text-center">
      <AlertTriangle className="h-8 w-8 text-amber-500" />
      <p className="text-sm text-muted max-w-md">{message}</p>
      {onRetry && (
        <button className="btn-secondary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function EmptyState({
  title,
  message,
  action,
  icon,
}: {
  title: string
  message?: string
  action?: ReactNode
  icon?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <span className="text-muted">{icon ?? <Inbox className="h-8 w-8" />}</span>
      <p className="font-medium">{title}</p>
      {message && <p className="text-sm text-muted max-w-md">{message}</p>}
      {action}
    </div>
  )
}

// --- table + pagination ---------------------------------------------------

export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="table-wrap">
      <table className="w-full border-collapse">{children}</table>
    </div>
  )
}

export function Pagination({
  page,
  pages,
  total,
  pageSize,
  onChange,
}: {
  page: number
  pages: number
  total: number
  pageSize: number
  onChange: (page: number) => void
}) {
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)
  return (
    <div className="flex items-center justify-between gap-3 border-t border-app px-4 py-3 text-sm">
      <p className="text-muted">
        {from}–{to} of {total.toLocaleString()}
      </p>
      <div className="flex items-center gap-1">
        <button
          className="btn-ghost px-2"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span className="px-2 tabular-nums">
          {page} / {Math.max(1, pages)}
        </span>
        <button
          className="btn-ghost px-2"
          disabled={page >= pages}
          onClick={() => onChange(page + 1)}
          aria-label="Next page"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}

// --- modal ----------------------------------------------------------------

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  wide,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  footer?: ReactNode
  wide?: boolean
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4 sm:p-8">
      <div
        className={clsx(
          'card w-full animate-fade-in shadow-pop my-auto',
          wide ? 'max-w-3xl' : 'max-w-lg',
        )}
        role="dialog"
        aria-modal="true"
      >
        <header className="flex items-center justify-between border-b border-app px-5 py-4">
          <h2 className="font-semibold">{title}</h2>
          <button className="btn-ghost px-2" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="p-5">{children}</div>
        {footer && (
          <footer className="flex justify-end gap-2 border-t border-app px-5 py-4">{footer}</footer>
        )}
      </div>
    </div>
  )
}

// --- provenance -----------------------------------------------------------

/**
 * Renders the platform's core promise inline: value + where it came from + how
 * sure we are. Used everywhere a fact about the outside world is displayed.
 */
export function Provenance({
  source,
  sourceUrl,
  confidence,
  verifiedAt,
}: {
  source?: string | null
  sourceUrl?: string | null
  confidence?: number | null
  verifiedAt?: string | null
}) {
  if (!source && !sourceUrl) {
    return <span className="text-xs text-muted">No source recorded</span>
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
      {sourceUrl ? (
        <a
          href={sourceUrl}
          target="_blank"
          rel="noreferrer noopener"
          className="underline decoration-dotted underline-offset-2 hover:text-brand-600 break-all"
        >
          {source || sourceUrl}
        </a>
      ) : (
        <span>{source}</span>
      )}
      {confidence !== undefined && confidence !== null && <ConfidenceMeter value={confidence} />}
      {verifiedAt && <span>· verified {relativeTime(verifiedAt)}</span>}
    </span>
  )
}

/** Renders a value, or an explicit "Unknown" — never a blank that reads as data. */
export function ValueOrUnknown({ value }: { value: ReactNode }) {
  if (value === null || value === undefined || value === '' || value === 'Unknown') {
    return <span className="text-muted italic">Unknown</span>
  }
  return <>{value}</>
}
