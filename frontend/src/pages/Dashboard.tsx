import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  Bot,
  Building2,
  CalendarClock,
  CheckCircle2,
  DollarSign,
  Gauge,
  Handshake,
  PhoneCall,
  Plus,
  Sparkles,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { errorMessage } from '../api/client'
import {
  analyticsOverview,
  dashboardMetrics,
  departmentStatus,
  listCompanies,
  listJobs,
  systemStatus,
} from '../api/endpoints'
import { OrdinalBarChart, TrendChart } from '../components/charts'
import {
  Card,
  EmptyState,
  ErrorState,
  formatMoney,
  Loading,
  PageHeader,
  relativeTime,
  ScoreBadge,
  StatTile,
  StatusBadge,
  titleCase,
} from '../components/ui'

const SCORE_ORDER = ['exceptional', 'high_priority', 'medium', 'low', 'poor']

export default function Dashboard() {
  const metrics = useQuery({ queryKey: ['dashboard'], queryFn: dashboardMetrics })
  const overview = useQuery({ queryKey: ['analytics', 30], queryFn: () => analyticsOverview(30) })
  const dept = useQuery({
    queryKey: ['dept-status'],
    queryFn: departmentStatus,
    refetchInterval: 15_000,
  })
  const topProspects = useQuery({
    queryKey: ['top-prospects'],
    queryFn: () => listCompanies({ page_size: 6, sort_by: 'opportunity_score', sort_dir: 'desc' }),
  })
  const jobs = useQuery({ queryKey: ['jobs', 'dash'], queryFn: () => listJobs({ page_size: 4 }) })
  const status = useQuery({ queryKey: ['system-status'], queryFn: systemStatus, retry: 1 })

  if (metrics.isLoading) return <Loading label="Loading your department…" />
  if (metrics.isError) {
    return (
      <ErrorState message={errorMessage(metrics.error)} onRetry={() => void metrics.refetch()} />
    )
  }

  const m = metrics.data!
  const scoreData = SCORE_ORDER.filter((key) => overview.data?.score_distribution?.[key]).map(
    (key) => ({ label: titleCase(key), count: overview.data!.score_distribution[key] }),
  )
  const trendData = (overview.data?.discovery_trend ?? []).map((point) => ({
    date: point.date.slice(5),
    value: point.value,
  }))

  const noDiscovery = status.data && !status.data.discovery_available

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle="What your AI sales department found, and what needs a human next."
        actions={
          <>
            <Link className="btn-secondary" to="/crm">
              <Handshake className="h-4 w-4" />
              Open CRM
            </Link>
            <Link className="btn-primary" to="/campaigns">
              <Plus className="h-4 w-4" />
              New campaign
            </Link>
          </>
        }
      />

      {noDiscovery && (
        <div className="card mb-6 border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-500/30 dark:bg-amber-500/10">
          <p className="font-medium text-amber-800 dark:text-amber-200">
            No discovery connector is available.
          </p>
          <p className="mt-1 text-amber-700 dark:text-amber-300">
            Research jobs will find nothing until one is configured. Enable OpenStreetMap or add a
            search API key in <Link className="underline" to="/admin">Administration</Link>.
          </p>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Companies researched"
          value={m.companies_total.toLocaleString()}
          hint={`${m.companies_new_7d} added in the last 7 days`}
          icon={<Building2 className="h-4 w-4" />}
        />
        <StatTile
          label="Qualified prospects"
          value={m.qualified_total.toLocaleString()}
          hint={`${m.ready_to_contact} ready for a human to contact`}
          icon={<CheckCircle2 className="h-4 w-4" />}
          tone="positive"
        />
        <StatTile
          label="Average opportunity"
          value={m.avg_opportunity_score.toFixed(0)}
          hint="Across all non-rejected companies"
          icon={<Gauge className="h-4 w-4" />}
        />
        <StatTile
          label="Cost per prospect"
          value={formatMoney(m.cost_per_prospect_usd, 3)}
          hint={`${formatMoney(m.spend_30d_usd)} spent in 30 days`}
          icon={<DollarSign className="h-4 w-4" />}
        />
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Active research jobs"
          value={m.active_jobs}
          hint={`${dept.data?.running_tasks ?? 0} agent tasks running`}
          icon={<Activity className="h-4 w-4" />}
        />
        <StatTile
          label="Contacted"
          value={m.contacted_total}
          hint="By a human, tracked in the CRM"
          icon={<PhoneCall className="h-4 w-4" />}
        />
        <StatTile
          label="Customers won"
          value={m.customers_total}
          icon={<Handshake className="h-4 w-4" />}
          tone="positive"
        />
        <StatTile
          label="Follow-ups due"
          value={m.follow_ups_due}
          hint="Next 7 days"
          icon={<CalendarClock className="h-4 w-4" />}
          tone={m.follow_ups_due > 0 ? 'warning' : 'default'}
        />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card
          className="lg:col-span-2"
          title="Companies discovered per day"
          description="Last 30 days"
          bodyClassName="pt-2"
        >
          {trendData.length ? (
            <TrendChart data={trendData} />
          ) : (
            <EmptyState
              title="No discovery activity yet"
              message="Start a campaign and the discovery agent will begin filling this in."
            />
          )}
        </Card>

        <Card title="Opportunity distribution" description="Non-rejected companies by tier">
          {scoreData.length ? (
            <OrdinalBarChart data={scoreData} height={220} />
          ) : (
            <EmptyState title="Nothing scored yet" />
          )}
        </Card>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card
          className="lg:col-span-2"
          title="Highest-scoring prospects"
          actions={
            <Link className="btn-ghost text-sm" to="/prospects">
              View all
            </Link>
          }
          bodyClassName="p-0"
        >
          {!topProspects.data?.items.length ? (
            <EmptyState
              title="No prospects yet"
              message="Create a campaign and click Start Research."
              action={
                <Link className="btn-primary" to="/campaigns">
                  <Sparkles className="h-4 w-4" />
                  Create a campaign
                </Link>
              }
            />
          ) : (
            <ul className="divide-y divide-[rgb(var(--border))]">
              {topProspects.data.items.map((company) => (
                <li key={company.id}>
                  <Link
                    to={`/companies/${company.id}`}
                    className="flex items-center gap-4 px-5 py-3.5 row-hover"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{company.name}</p>
                      <p className="truncate text-xs text-muted">
                        {company.domain ?? 'No domain'} · {company.city ?? 'Unknown city'}
                        {company.country_code ? `, ${company.country_code}` : ''}
                      </p>
                    </div>
                    <ScoreBadge
                      score={company.opportunity_score}
                      category={company.opportunity_category}
                    />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <div className="space-y-4">
          <Card
            title="AI department"
            description={`${dept.data?.agents.filter((a) => a.is_enabled).length ?? 0} employees on duty`}
            actions={
              <Link className="btn-ghost text-sm" to="/monitoring">
                Monitor
              </Link>
            }
            bodyClassName="p-0"
          >
            <ul className="divide-y divide-[rgb(var(--border))]">
              {(dept.data?.agents ?? []).slice(0, 6).map((agent) => (
                <li key={agent.key} className="flex items-center gap-3 px-5 py-2.5">
                  <Bot className="h-4 w-4 shrink-0 text-muted" />
                  <span className="min-w-0 flex-1 truncate text-sm">{agent.display_name}</span>
                  <StatusBadge status={agent.is_enabled ? agent.status : 'disabled'} />
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Recent jobs" bodyClassName="p-0">
            {!jobs.data?.items.length ? (
              <p className="px-5 py-6 text-sm text-muted">No research jobs yet.</p>
            ) : (
              <ul className="divide-y divide-[rgb(var(--border))]">
                {jobs.data.items.map((job) => (
                  <li key={job.id}>
                    <Link to={`/jobs/${job.id}`} className="block px-5 py-3 row-hover">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm font-medium">
                          {job.current_stage ?? 'Queued'}
                        </span>
                        <StatusBadge status={job.status} />
                      </div>
                      <p className="mt-1 text-xs text-muted">
                        {job.prospects_qualified} qualified · {job.companies_discovered} found ·{' '}
                        {relativeTime(job.created_at)}
                      </p>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  )
}
