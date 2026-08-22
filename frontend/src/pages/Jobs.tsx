import { useQuery } from '@tanstack/react-query'
import { Activity } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { listJobs } from '../api/endpoints'
import type { JobStatus } from '../api/types'
import {
  Card,
  EmptyState,
  ErrorState,
  formatMoney,
  Pagination,
  PageHeader,
  relativeTime,
  SkeletonRows,
  StatusBadge,
  Table,
} from '../components/ui'

const STATUSES: Array<JobStatus | 'all'> = [
  'all',
  'queued',
  'running',
  'completed',
  'failed',
  'cancelled',
]

export default function Jobs() {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<JobStatus | 'all'>('all')

  const query = useQuery({
    queryKey: ['jobs', page, status],
    queryFn: () =>
      listJobs({ page, page_size: 25, ...(status === 'all' ? {} : { job_status: status }) }),
    refetchInterval: 10_000,
  })

  return (
    <>
      <PageHeader
        title="Research jobs"
        subtitle="Every run of the AI department, with live progress and its full cost."
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {STATUSES.map((value) => (
          <button
            key={value}
            className={value === status ? 'btn-primary' : 'btn-secondary'}
            onClick={() => {
              setStatus(value)
              setPage(1)
            }}
          >
            {value === 'all' ? 'All' : value.charAt(0).toUpperCase() + value.slice(1)}
          </button>
        ))}
      </div>

      <Card bodyClassName="p-0">
        {query.isLoading ? (
          <SkeletonRows rows={6} cols={7} />
        ) : query.isError ? (
          <ErrorState message={errorMessage(query.error)} onRetry={() => void query.refetch()} />
        ) : !query.data?.items.length ? (
          <EmptyState
            title="No research jobs"
            message="Start research from a campaign to see it here."
            icon={<Activity className="h-8 w-8" />}
            action={
              <Link className="btn-primary" to="/campaigns">
                Go to campaigns
              </Link>
            }
          />
        ) : (
          <>
            <Table>
              <thead className="border-b border-app">
                <tr>
                  <th className="th">Stage</th>
                  <th className="th">Status</th>
                  <th className="th">Progress</th>
                  <th className="th">Found</th>
                  <th className="th">Rejected</th>
                  <th className="th">Qualified</th>
                  <th className="th">Cost</th>
                  <th className="th">Started</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[rgb(var(--border))]">
                {query.data.items.map((job) => (
                  <tr key={job.id} className="row-hover">
                    <td className="td">
                      <Link className="font-medium hover:text-brand-600" to={`/jobs/${job.id}`}>
                        {job.current_stage ?? 'Queued'}
                      </Link>
                      {job.error && (
                        <p className="mt-0.5 max-w-sm truncate text-xs text-rose-600">{job.error}</p>
                      )}
                    </td>
                    <td className="td">
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="td w-40">
                      <div className="flex items-center gap-2">
                        <span className="h-1.5 flex-1 overflow-hidden rounded-full surface-muted">
                          <span
                            className="block h-full rounded-full bg-brand-600"
                            style={{ width: `${job.progress_percent}%` }}
                          />
                        </span>
                        <span className="text-xs tabular-nums text-muted">
                          {Math.round(job.progress_percent)}%
                        </span>
                      </div>
                    </td>
                    <td className="td tabular-nums">{job.companies_discovered}</td>
                    <td className="td tabular-nums text-muted">{job.companies_rejected}</td>
                    <td className="td tabular-nums font-medium">{job.prospects_qualified}</td>
                    <td className="td tabular-nums">{formatMoney(job.cost_usd, 4)}</td>
                    <td className="td text-sm text-muted">{relativeTime(job.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pagination
              page={query.data.page}
              pages={query.data.pages}
              total={query.data.total}
              pageSize={query.data.page_size}
              onChange={setPage}
            />
          </>
        )}
      </Card>
    </>
  )
}
