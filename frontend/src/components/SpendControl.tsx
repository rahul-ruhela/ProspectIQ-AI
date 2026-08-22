/**
 * Operator control over paid LLM spend.
 *
 * The platform prefers free-tier models and only reaches for a paid one when the
 * free quota is spent. This panel decides whether it may do that at all, and caps
 * how far it can go — with live meters, because a limit you cannot see your position
 * against is not really a control.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { errorMessage } from '../api/client'
import { getSpendPolicy, updateSpendPolicy } from '../api/endpoints'
import type { SpendStatus } from '../api/types'
import { Card, Loading } from './ui'

// Presets covering the realistic range: a token experiment through a working month.
const DAILY_PRESETS = [0.5, 1, 5, 20]
const MONTHLY_PRESETS = [5, 20, 50, 100]

function money(value: number, digits = 2): string {
  return `$${value.toFixed(digits)}`
}

export default function SpendControl() {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const status = useQuery({
    queryKey: ['spend-policy'],
    queryFn: getSpendPolicy,
    // Spend moves while a research job runs, so the meters track it.
    refetchInterval: 10_000,
  })

  const save = useMutation({
    mutationFn: updateSpendPolicy,
    onSuccess: (data) => {
      setError(null)
      queryClient.setQueryData(['spend-policy'], data)
    },
    onError: (err) => setError(errorMessage(err, 'Could not save the spend limit.')),
  })

  if (status.isLoading) return <Loading label="Loading spend policy…" />
  if (status.isError) {
    return (
      <Card title="Paid AI spend">
        <p className="text-sm text-rose-600 dark:text-rose-400">
          {errorMessage(status.error)}
        </p>
      </Card>
    )
  }

  const s = status.data!
  const p = s.policy

  return (
    <Card
      title="Paid AI spend"
      description="Free models are always used first. These limits cap what may be spent when the free quota runs out."
      actions={
        <span
          className={[
            'rounded-full px-2.5 py-1 text-xs font-medium',
            s.paid_available
              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300'
              : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
          ].join(' ')}
        >
          {s.paid_available ? 'Paid enabled' : 'Free only'}
        </span>
      }
    >
      <div className="space-y-6">
        <label className="flex cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            className="mt-1 h-4 w-4 rounded"
            checked={p.allow_paid}
            onChange={(e) => save.mutate({ allow_paid: e.target.checked })}
            disabled={save.isPending}
          />
          <span>
            <span className="block text-sm font-medium">Allow paid models</span>
            <span className="block text-xs text-muted">
              When the free tier is exhausted, fall back to paid models instead of the
              rules engine — never beyond the limits below.
            </span>
          </span>
        </label>

        {s.blocked_reason ? (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
            {s.blocked_reason}
          </p>
        ) : null}
        {error ? (
          <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
            {error}
          </p>
        ) : null}

        <LimitRow
          label="Daily limit"
          hint="Resets at UTC midnight"
          presets={DAILY_PRESETS}
          value={p.daily_limit_usd}
          spent={s.spent_today_usd}
          pct={s.daily_used_pct}
          remaining={s.daily_remaining_usd}
          alertAt={p.alert_threshold_pct}
          disabled={save.isPending}
          onChange={(v) => save.mutate({ daily_limit_usd: v })}
        />

        <LimitRow
          label="Monthly limit"
          hint="Calendar month, UTC"
          presets={MONTHLY_PRESETS}
          value={p.monthly_limit_usd}
          spent={s.spent_month_usd}
          pct={s.monthly_used_pct}
          remaining={s.monthly_remaining_usd}
          alertAt={p.alert_threshold_pct}
          disabled={save.isPending}
          onChange={(v) => save.mutate({ monthly_limit_usd: v })}
        />

        <div>
          <div className="mb-2 flex items-baseline justify-between">
            <span className="text-sm font-medium">Warn at</span>
            <span className="text-sm tabular-nums text-muted">{p.alert_threshold_pct}%</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {[50, 75, 80, 90].map((pct) => (
              <button
                key={pct}
                type="button"
                disabled={save.isPending}
                onClick={() => save.mutate({ alert_threshold_pct: pct })}
                className={[
                  'rounded-lg border px-3 py-1.5 text-sm transition',
                  p.alert_threshold_pct === pct
                    ? 'border-brand-500 bg-brand-50 font-medium text-brand-700 dark:bg-brand-500/15 dark:text-brand-300'
                    : 'border-app hover:surface-muted',
                ].join(' ')}
              >
                {pct}%
              </button>
            ))}
          </div>
        </div>

        <ModelChains status={s} />
      </div>
    </Card>
  )
}

function LimitRow({
  label,
  hint,
  presets,
  value,
  spent,
  pct,
  remaining,
  alertAt,
  disabled,
  onChange,
}: {
  label: string
  hint: string
  presets: number[]
  value: number
  spent: number
  pct: number
  remaining: number
  alertAt: number
  disabled: boolean
  onChange: (value: number) => void
}) {
  const [custom, setCustom] = useState(String(value))
  // Keep the box in step when a preset changes the value elsewhere.
  useEffect(() => setCustom(String(value)), [value])

  const over = pct >= 100
  const warning = !over && alertAt > 0 && pct >= alertAt

  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium">
          {label}
          <span className="ml-2 text-xs font-normal text-muted">{hint}</span>
        </span>
        <span className="text-sm tabular-nums text-muted">
          {money(spent, 4)} of {money(value)}
        </span>
      </div>

      <div className="h-2 overflow-hidden rounded-full surface-muted">
        <div
          className={[
            'h-full rounded-full transition-all duration-500',
            over ? 'bg-rose-500' : warning ? 'bg-amber-500' : 'bg-emerald-500',
          ].join(' ')}
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </div>
      <p
        className={[
          'mt-1 text-xs',
          over
            ? 'text-rose-600 dark:text-rose-400'
            : warning
              ? 'text-amber-600 dark:text-amber-400'
              : 'text-muted',
        ].join(' ')}
      >
        {over ? 'Limit reached — paid calls are blocked.' : `${money(remaining, 4)} remaining`}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {presets.map((preset) => (
          <button
            key={preset}
            type="button"
            disabled={disabled}
            onClick={() => onChange(preset)}
            className={[
              'rounded-lg border px-3 py-1.5 text-sm transition',
              value === preset
                ? 'border-brand-500 bg-brand-50 font-medium text-brand-700 dark:bg-brand-500/15 dark:text-brand-300'
                : 'border-app hover:surface-muted',
            ].join(' ')}
          >
            {money(preset)}
          </button>
        ))}
        <span className="flex items-center gap-1">
          <span className="text-sm text-muted">$</span>
          <input
            type="number"
            min={0}
            step="0.01"
            value={custom}
            disabled={disabled}
            onChange={(e) => setCustom(e.target.value)}
            onBlur={() => {
              const next = Number(custom)
              if (Number.isFinite(next) && next >= 0 && next !== value) onChange(next)
              else setCustom(String(value))
            }}
            className="w-24 rounded-lg border border-app bg-transparent px-2 py-1.5 text-sm tabular-nums"
          />
        </span>
      </div>
    </div>
  )
}

function ModelChains({ status }: { status: SpendStatus }) {
  return (
    <div className="border-t border-app pt-4">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">
        Model order
      </p>
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        {status.free_chain.map((model) => (
          <span
            key={model}
            className="rounded-md bg-emerald-100 px-2 py-1 font-medium text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"
          >
            {model}
          </span>
        ))}
        {status.paid_chain.length > 0 ? (
          <>
            <span className="px-1 text-muted">then</span>
            {status.paid_chain.map((model) => (
              <span
                key={model}
                className="rounded-md bg-amber-100 px-2 py-1 font-medium text-amber-800 dark:bg-amber-500/15 dark:text-amber-300"
              >
                {model}
              </span>
            ))}
          </>
        ) : (
          <span className="px-1 text-muted">— no paid fallback active</span>
        )}
      </div>
    </div>
  )
}
