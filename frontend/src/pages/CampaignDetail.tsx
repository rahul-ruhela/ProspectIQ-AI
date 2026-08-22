import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Loader2, Play, Rocket } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { errorMessage } from '../api/client'
import {
  campaignStats,
  getCampaign,
  listCompanies,
  listJobs,
  startResearch,
} from '../api/endpoints'
import {
  Card,
  EmptyState,
  ErrorState,
  formatMoney,
  Loading,
  Modal,
  PageHeader,
  relativeTime,
  ScoreBadge,
  StatTile,
  StatusBadge,
  Table,
  titleCase,
} from '../components/ui'
import { useAuth } from '../store/auth'

export default function CampaignDetail() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { can } = useAuth()
  const [startOpen, setStartOpen] = useState(false)
  const [maxCompanies, setMaxCompanies] = useState(25)
  const [error, setError] = useState<string | null>(null)

  const campaign = useQuery({ queryKey: ['campaign', id], queryFn: () => getCampaign(id) })
  const stats = useQuery({ queryKey: ['campaign-stats', id], queryFn: () => campaignStats(id) })
  const jobs = useQuery({
    queryKey: ['jobs', 'campaign', id],
    queryFn: () => listJobs({ campaign_id: id, page_size: 10 }),
    refetchInterval: 10_000,
  })
  const companies = useQuery({
    queryKey: ['companies', 'campaign', id],
    queryFn: () => listCompanies({ campaign_id: id, page_size: 10 }),
  })

  const start = useMutation({
    mutationFn: () => startResearch(id, { max_companies: maxCompanies }),
    onSuccess: (job) => {
      setStartOpen(false)
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
      navigate(`/jobs/${job.id}`)
    },
    onError: (err) => setError(errorMessage(err, 'Could not start research.')),
  })

  if (campaign.isLoading) return <Loading />
  if (campaign.isError) {
    return <ErrorState message={errorMessage(campaign.error)} onRetry={() => void campaign.refetch()} />
  }

  const c = campaign.data!
  const filters = c.filters

  return (
    <>
      <Link className="btn-ghost mb-3 -ml-2 text-sm" to="/campaigns">
        <ArrowLeft className="h-4 w-4" />
        All campaigns
      </Link>

      <PageHeader
        title={c.name}
        subtitle={c.objective ?? undefined}
        actions={
          can('researcher') && (
            <button className="btn-primary" onClick={() => setStartOpen(true)}>
              <Rocket className="h-4 w-4" />
              Start research
            </button>
          )
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatTile label="Status" value={<StatusBadge status={c.status} />} />
        <StatTile label="Companies found" value={stats.data?.companies ?? 0} />
        <StatTile label="Qualified" value={stats.data?.qualified ?? 0} tone="positive" />
        <StatTile
          label="Avg score"
          value={(stats.data?.avg_opportunity_score ?? 0).toFixed(0)}
        />
        <StatTile
          label="Spent"
          value={formatMoney(c.spent_usd, 3)}
          hint={`Budget ${formatMoney(c.budget_usd, 2)}`}
        />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card title="Targeting" className="lg:col-span-1">
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-muted">Countries</dt>
              <dd>{filters?.countries.join(', ') || 'None selected'}</dd>
            </div>
            <div>
              <dt className="text-muted">Industries</dt>
              <dd>{filters?.industries.map(titleCase).join(', ') || 'Any'}</dd>
            </div>
            <div>
              <dt className="text-muted">Cities</dt>
              <dd>{filters?.cities.join(', ') || 'Country-wide'}</dd>
            </div>
            <div>
              <dt className="text-muted">Services offered</dt>
              <dd>{c.offered_services.map(titleCase).join(', ') || 'All'}</dd>
            </div>
            <div>
              <dt className="text-muted">Minimum score to qualify</dt>
              <dd>{filters?.min_opportunity_score ?? 40}</dd>
            </div>
            <div>
              <dt className="text-muted">Requires a live website</dt>
              <dd>{filters?.require_website ? 'Yes' : 'No'}</dd>
            </div>
          </dl>
        </Card>

        <Card title="Research jobs" className="lg:col-span-2" bodyClassName="p-0">
          {!jobs.data?.items.length ? (
            <EmptyState
              title="No research runs yet"
              message="Click Start Research and the CEO orchestrator will assign work to the department."
              action={
                can('researcher') && (
                  <button className="btn-primary" onClick={() => setStartOpen(true)}>
                    <Play className="h-4 w-4" />
                    Start research
                  </button>
                )
              }
            />
          ) : (
            <Table>
              <thead className="border-b border-app">
                <tr>
                  <th className="th">Stage</th>
                  <th className="th">Status</th>
                  <th className="th">Found</th>
                  <th className="th">Qualified</th>
                  <th className="th">Cost</th>
                  <th className="th">Started</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[rgb(var(--border))]">
                {jobs.data.items.map((job) => (
                  <tr key={job.id} className="row-hover">
                    <td className="td">
                      <Link className="font-medium hover:text-brand-600" to={`/jobs/${job.id}`}>
                        {job.current_stage ?? 'Queued'}
                      </Link>
                    </td>
                    <td className="td">
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="td tabular-nums">{job.companies_discovered}</td>
                    <td className="td tabular-nums">{job.prospects_qualified}</td>
                    <td className="td tabular-nums">{formatMoney(job.cost_usd, 4)}</td>
                    <td className="td text-sm text-muted">{relativeTime(job.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      </div>

      <Card className="mt-6" title="Companies from this campaign" bodyClassName="p-0">
        {!companies.data?.items.length ? (
          <EmptyState title="No companies yet" />
        ) : (
          <Table>
            <thead className="border-b border-app">
              <tr>
                <th className="th">Company</th>
                <th className="th">Location</th>
                <th className="th">Score</th>
                <th className="th">Completeness</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[rgb(var(--border))]">
              {companies.data.items.map((company) => (
                <tr key={company.id} className="row-hover">
                  <td className="td">
                    <Link className="font-medium hover:text-brand-600" to={`/companies/${company.id}`}>
                      {company.name}
                    </Link>
                    <p className="text-xs text-muted">{company.domain}</p>
                  </td>
                  <td className="td text-sm">
                    {company.city ?? '—'}
                    {company.country_code ? `, ${company.country_code}` : ''}
                  </td>
                  <td className="td">
                    <ScoreBadge
                      score={company.opportunity_score}
                      category={company.opportunity_category}
                    />
                  </td>
                  <td className="td tabular-nums text-sm">
                    {Math.round(company.data_completeness * 100)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Modal
        open={startOpen}
        onClose={() => setStartOpen(false)}
        title="Start research"
        footer={
          <>
            <button className="btn-secondary" onClick={() => setStartOpen(false)}>
              Cancel
            </button>
            <button
              className="btn-primary"
              disabled={start.isPending}
              onClick={() => {
                setError(null)
                start.mutate()
              }}
            >
              {start.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Start research
            </button>
          </>
        }
      >
        <p className="text-sm text-muted">
          The CEO orchestrator will build a strategy, plan searches, discover businesses, crawl each
          website, find decision makers and contacts, detect buying signals, score the opportunity
          and write a report for every qualified prospect.
        </p>
        <div className="mt-4">
          <label className="label" htmlFor="max">
            Maximum companies to research
          </label>
          <input
            id="max"
            className="input"
            type="number"
            min={1}
            max={250}
            value={maxCompanies}
            onChange={(event) => setMaxCompanies(Number(event.target.value))}
          />
          <p className="mt-1 text-xs text-muted">
            Each company costs a handful of HTTP requests, and LLM tokens only if it qualifies.
          </p>
        </div>
        {error && (
          <p className="mt-4 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
            {error}
          </p>
        )}
      </Modal>
    </>
  )
}
