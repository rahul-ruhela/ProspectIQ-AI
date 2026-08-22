/**
 * Chart primitives.
 *
 * Colours come from a validated palette: categorical slots are assigned in fixed
 * order (never cycled), ordered magnitudes use a single-hue ordinal ramp, and both
 * light and dark steps were validated against their own surface rather than flipped.
 */
import { useEffect, useState, type ReactNode } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useTheme } from '../store/theme'

/** Categorical slots, in fixed assignment order. Capped at three by the all-pairs gate. */
export const SERIES = {
  light: ['#2a78d6', '#eb6834', '#1baf7a'],
  dark: ['#3987e5', '#d95926', '#199e70'],
}

/**
 * Ordinal ramp for ordered magnitudes (score tiers, funnel stages).
 * Light stops at step 250 and dark at step 600 so the step nearest the
 * surface still clears 2:1 contrast.
 */
export const ORDINAL = {
  light: ['#184f95', '#256abf', '#3987e5', '#5598e7', '#86b6ef'],
  dark: ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#184f95'],
}

export function useChartTheme() {
  const theme = useTheme((state) => state.theme)
  const dark = theme === 'dark'
  return {
    dark,
    series: dark ? SERIES.dark : SERIES.light,
    ordinal: dark ? ORDINAL.dark : ORDINAL.light,
    gridLine: dark ? '#273041' : '#e2e8f0',
    text: dark ? '#94a3b8' : '#64748b',
    surface: dark ? '#111621' : '#ffffff',
    border: dark ? '#273041' : '#e2e8f0',
  }
}

/** Recharts remounts on container resize; this keeps SSR-less first paint stable. */
export function ChartFrame({ height = 240, children }: { height?: number; children: ReactNode }) {
  const [ready, setReady] = useState(false)
  useEffect(() => setReady(true), [])
  if (!ready) return <div className="skeleton w-full" style={{ height }} />
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        {children as never}
      </ResponsiveContainer>
    </div>
  )
}

function TooltipBox({
  active,
  payload,
  label,
  valueFormatter,
}: {
  active?: boolean
  payload?: Array<{ name?: string; value?: number | string; color?: string }>
  label?: string | number
  valueFormatter?: (value: number | string) => string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="card px-3 py-2 shadow-pop text-xs">
      {label !== undefined && <p className="font-medium mb-1">{label}</p>}
      {payload.map((entry, index) => (
        <p key={index} className="flex items-center gap-2">
          <span
            className="h-2 w-2 rounded-full"
            style={{ background: entry.color ?? 'currentColor' }}
          />
          <span className="text-muted">{entry.name}</span>
          <span className="ml-auto font-medium tabular-nums">
            {valueFormatter ? valueFormatter(entry.value ?? 0) : entry.value}
          </span>
        </p>
      ))}
    </div>
  )
}

/** Single-series trend. One series needs no legend — the card title names it. */
export function TrendChart({
  data,
  height = 220,
  slot = 0,
  valueFormatter,
  xKey = 'date',
  yKey = 'value',
}: {
  data: Array<Record<string, string | number>>
  height?: number
  slot?: 0 | 1 | 2
  valueFormatter?: (value: number | string) => string
  xKey?: string
  yKey?: string
}) {
  const theme = useChartTheme()
  const color = theme.series[slot]
  const gradientId = `trend-${slot}-${theme.dark ? 'd' : 'l'}`

  return (
    <ChartFrame height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.28} />
            <stop offset="100%" stopColor={color} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={theme.gridLine} strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey={xKey}
          tick={{ fill: theme.text, fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          minTickGap={24}
        />
        <YAxis
          tick={{ fill: theme.text, fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          width={48}
          allowDecimals={false}
        />
        <Tooltip
          content={<TooltipBox valueFormatter={valueFormatter} />}
          cursor={{ stroke: theme.text, strokeDasharray: '3 3' }}
        />
        <Area
          type="monotone"
          dataKey={yKey}
          name="Value"
          stroke={color}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
          dot={false}
          activeDot={{ r: 4, strokeWidth: 2, stroke: theme.surface }}
        />
      </AreaChart>
    </ChartFrame>
  )
}

/** Ordered categories (score tiers, funnel stages) on a single-hue ordinal ramp. */
export function OrdinalBarChart({
  data,
  height = 240,
  layout = 'vertical',
  xKey = 'label',
  yKey = 'count',
  valueFormatter,
}: {
  data: Array<Record<string, string | number>>
  height?: number
  /** 'vertical' draws horizontal bars (category on the y-axis). */
  layout?: 'vertical' | 'horizontal'
  xKey?: string
  yKey?: string
  valueFormatter?: (value: number | string) => string
}) {
  const theme = useChartTheme()
  const bandOnY = layout === 'vertical'
  const tick = { fill: theme.text, fontSize: 11 }

  // Recharts discovers axes among its DIRECT children, so both axes are always
  // rendered and only their props switch. Wrapping them in a fragment makes
  // Recharts silently drop the axes, and the scale along with them.
  return (
    <ChartFrame height={height}>
      <BarChart
        data={data}
        layout={bandOnY ? 'vertical' : 'horizontal'}
        margin={{ top: 8, right: 24, left: bandOnY ? 8 : -18, bottom: 0 }}
      >
        <CartesianGrid
          stroke={theme.gridLine}
          strokeDasharray="3 3"
          horizontal={!bandOnY}
          vertical={bandOnY}
        />
        <XAxis
          type={bandOnY ? 'number' : 'category'}
          dataKey={bandOnY ? undefined : xKey}
          tick={tick}
          tickLine={false}
          axisLine={false}
          allowDecimals={false}
        />
        <YAxis
          type={bandOnY ? 'category' : 'number'}
          dataKey={bandOnY ? xKey : undefined}
          tick={tick}
          tickLine={false}
          axisLine={false}
          width={bandOnY ? 116 : 48}
          allowDecimals={false}
        />
        <Tooltip
          content={<TooltipBox valueFormatter={valueFormatter} />}
          cursor={{ fill: theme.dark ? '#ffffff10' : '#0f172a08' }}
        />
        <Bar dataKey={yKey} name="Count" radius={4} barSize={bandOnY ? 16 : 26}>
          {data.map((_, index) => (
            <Cell
              key={index}
              fill={theme.ordinal[Math.min(index, theme.ordinal.length - 1)]}
              stroke={theme.surface}
              strokeWidth={2}
            />
          ))}
        </Bar>
      </BarChart>
    </ChartFrame>
  )
}

/** Unordered categories (industries, countries, technologies) — one hue, no rank colouring. */
export function CategoryBarChart({
  data,
  height = 260,
  xKey = 'label',
  yKey = 'value',
  slot = 0,
  valueFormatter,
}: {
  data: Array<Record<string, string | number>>
  height?: number
  xKey?: string
  yKey?: string
  slot?: 0 | 1 | 2
  valueFormatter?: (value: number | string) => string
}) {
  const theme = useChartTheme()
  return (
    <ChartFrame height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 8, right: 24, left: 8, bottom: 0 }}>
        <CartesianGrid stroke={theme.gridLine} strokeDasharray="3 3" horizontal={false} />
        <XAxis
          type="number"
          tick={{ fill: theme.text, fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          allowDecimals={false}
        />
        <YAxis
          type="category"
          dataKey={xKey}
          tick={{ fill: theme.text, fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          width={140}
        />
        <Tooltip
          content={<TooltipBox valueFormatter={valueFormatter} />}
          cursor={{ fill: theme.dark ? '#ffffff10' : '#0f172a08' }}
        />
        <Bar
          dataKey={yKey}
          name="Companies"
          fill={theme.series[slot]}
          radius={4}
          barSize={16}
          stroke={theme.surface}
          strokeWidth={2}
        />
      </BarChart>
    </ChartFrame>
  )
}
