import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { errorMessage } from '../api/client'
import { analyticsOverview } from '../api/endpoints'
import { CategoryBarChart, OrdinalBarChart, TrendChart } from '../components/charts'
import {
  Card,
  EmptyState,
  ErrorState,
  formatMoney,
  Loading,
  PageHeader,
  Table,
  titleCase,
} from '../components/ui'

const RANGES = [7, 30, 90, 180] as const
const SCORE_ORDER = ['exceptional', 'high_priority', 'medium', 'low', 'poor']

export default function Analytics() {
  const [days, setDays] = useState<(typeof RANGES)[number]>(30)
  const query = useQuery({
    queryKey: ['analytics', days],
    queryFn: () => analyticsOverview(days),
  })

  if (query.isLoading) return <Loading />
  if (query.isError) {
    return <ErrorState message={errorMessage(query.error)} onRetry={() => void query.refetch()} />
  }

  const data = query.data!
  const trend = data.discovery_trend.map((p) => ({ date: p.date.slice(5), value: p.value }))
  const costs = data.cost_trend.map((p) => ({ date: p.date.slice(5), value: p.value }))
  const scores = SCORE_ORDER.filter((key) => data.score_distribution[key]).map((key) => ({
    label: titleCase(key),
    count: data.score_distribution[key],
  }))
  const funnel = data.pipeline_funnel.map((row) => ({
    label: titleCase(row.stage),
    count: row.count,
  }))
  const industries = data.top_industries.map((row) => ({
    label: titleCase(String(row.industry)),
    value: Number(row.companies),
    avg: Number(row.avg_score),
  }))
  const countries = data.top_countries.map((row) => ({
    label: String(row.country),
    value: Number(row.companies),
  }))
  const technologies = data.top_technologies.map((row) => ({
    label: String(row.technology),
    value: Number(row.companies),
  }))

  return (
    <>
      <PageHeader
        title="Analytics"
        subtitle="Where your prospects come from, how they score, and what the department costs."
        actions={
          <div className="flex gap-1">
            {RANGES.map((value) => (
              <button
                key={value}
                className={value === days ? 'btn-primary' : 'btn-secondary'}
                onClick={() => setDays(value)}
              >
                {value}d
              </button>
            ))}
          </div>
        }
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Companies discovered per day" description={`Last ${days} days`}>
          {trend.length ? <TrendChart data={trend} /> : <EmptyState title="No data in this range" />}
        </Card>
        <Card title="LLM spend per day" description={`Last ${days} days, USD`}>
          {costs.length ? (
            <TrendChart
              data={costs}
              slot={1}
              valueFormatter={(value) => formatMoney(Number(value), 4)}
            />
          ) : (
            <EmptyState title="No spend recorded" />
          )}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Opportunity distribution" description="Companies by scoring tier">
          {scores.length ? <OrdinalBarChart data={scores} /> : <EmptyState title="Nothing scored" />}
        </Card>
        <Card title="Pipeline funnel" description="Prospects at each CRM stage">
          {funnel.some((f) => f.count > 0) ? (
            <OrdinalBarChart data={funnel} height={320} />
          ) : (
            <EmptyState title="Pipeline is empty" />
          )}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card title="Top industries" description="By company count">
          {industries.length ? (
            <CategoryBarChart data={industries} />
          ) : (
            <EmptyState title="No industries yet" />
          )}
        </Card>
        <Card title="Top countries" description="By company count">
          {countries.length ? (
            <CategoryBarChart data={countries} slot={1} />
          ) : (
            <EmptyState title="No countries yet" />
          )}
        </Card>
        <Card title="Most common technology" description="Across researched companies">
          {technologies.length ? (
            <CategoryBarChart data={technologies} slot={2} />
          ) : (
            <EmptyState title="No technology detected yet" />
          )}
        </Card>
      </div>

      <Card className="mt-4" title="Agent performance" bodyClassName="p-0">
        {!data.agent_performance.length ? (
          <EmptyState title="No agent activity yet" />
        ) : (
          <Table>
            <thead className="border-b border-app">
              <tr>
                <th className="th">Agent</th>
                <th className="th">Tasks</th>
                <th className="th">Average confidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[rgb(var(--border))]">
              {data.agent_performance.map((row) => (
                <tr key={String(row.agent)} className="row-hover">
                  <td className="td font-medium">{titleCase(String(row.agent))}</td>
                  <td className="td tabular-nums">{row.tasks}</td>
                  <td className="td tabular-nums">
                    {Math.round(Number(row.avg_confidence) * 100)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  )
}
