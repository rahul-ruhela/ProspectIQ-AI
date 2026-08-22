import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Ban, Pause, Play } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { cancelJob, getJob, listAgentLogs, listAgentTasks, pauseJob, resumeJob } from '../api/endpoints'
import {
  Card,
  EmptyState,
  ErrorState,
  formatDateTime,
  formatMoney,
  Loading,
  PageHeader,
  relativeTime,
  StatTile,
  StatusBadge,
  Table,
  titleCase,
} from '../components/ui'
import { useAuth } from '../store/auth'

export default function JobDetail() {
  const { id = '' } = useParams()
  const queryClient = useQueryClient()
  const { can } = useAuth()

  const job = useQuery({
    queryKey: ['job', id],
    queryFn: () => getJob(id),
    // Poll while the department is working so the page tracks progress live.
    refetchInterval: (query) =>
      ['queued', 'running'].includes(query.state.data?.status ?? '') ? 3_000 : false,
  })
  const tasks = useQuery({
    queryKey: ['job-tasks', id],
    queryFn: () => listAgentTasks({ research_job_id: id, page_size: 100 }),
    refetchInterval: 5_000,
  })
  const logs = useQuery({
    queryKey: ['job-logs', id],
    queryFn: () => listAgentLogs({ research_job_id: id, limit: 200 }),
    refetchInterval: 5_000,
  })

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['job', id] })
    void queryClient.invalidateQueries({ queryKey: ['jobs'] })
  }
  const cancel = useMutation({ mutationFn: () => cancelJob(id), onSuccess: invalidate })
  const pause = useMutation({ mutationFn: () => pauseJob(id), onSuccess: invalidate })
  const resume = useMutation({ mutationFn: () => resumeJob(id), onSuccess: invalidate })

  if (job.isLoading) return <Loading />
  if (job.isError) return <ErrorState message={errorMessage(job.error)} onRetry={() => void job.refetch()} />

  const j = job.data!
  const live = ['queued', 'running'].includes(j.status)
  const stages: string[] = (j.plan?.stages as string[]) ?? []

  return (
    <>
      <Link className="btn-ghost mb-3 -ml-2 text-sm" to="/jobs">
        <ArrowLeft className="h-4 w-4" />
        All jobs
      </Link>

      <PageHeader
        title="Research job"
        subtitle={j.plan?.interpretation as string | undefined}
        actions={
          can('researcher') && (
            <>
              {live && (
                <>
                  <button className="btn-secondary" onClick={() => pause.mutate()}>
                    <Pause className="h-4 w-4" />
                    Pause
                  </button>
                  <button className="btn-danger" onClick={() => cancel.mutate()}>
                    <Ban className="h-4 w-4" />
                    Cancel
                  </button>
                </>
              )}
              {['paused', 'failed'].includes(j.status) && (
                <button className="btn-primary" onClick={() => resume.mutate()}>
                  <Play className="h-4 w-4" />
                  Resume
                </button>
              )}
            </>
          )
        }
      />

      <div className="card mb-6 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <StatusBadge status={j.status} />
            <span className="text-sm font-medium">{j.current_stage ?? 'Queued'}</span>
          </div>
          <span className="text-sm tabular-nums text-muted">
            {Math.round(j.progress_percent)}% complete
          </span>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full surface-muted">
          <div
            className="h-full rounded-full bg-brand-600 transition-all duration-500"
            style={{ width: `${j.progress_percent}%` }}
          />
        </div>
        {j.error && (
          <p className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
            {j.error}
          </p>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatTile label="Discovered" value={j.companies_discovered} />
        <StatTile label="Verified" value={j.companies_verified} />
        <StatTile label="Rejected" value={j.companies_rejected} />
        <StatTile label="Qualified" value={j.prospects_qualified} tone="positive" />
        <StatTile label="Cost" value={formatMoney(j.cost_usd, 4)} />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card title="Research plan" description="Built by the CEO orchestrator">
          {stages.length ? (
            <ol className="space-y-2 text-sm">
              {stages.map((stage, index) => (
                <li key={stage} className="flex items-start gap-3">
                  <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full surface-muted text-[10px] font-semibold tabular-nums">
                    {index + 1}
                  </span>
                  <span>{titleCase(stage)}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-muted">No plan recorded.</p>
          )}
          <dl className="mt-5 space-y-2 border-t border-app pt-4 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-muted">Planner</dt>
              <dd>{(j.plan?.planner as string) ?? '—'}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted">Started</dt>
              <dd>{formatDateTime(j.started_at)}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted">Finished</dt>
              <dd>{formatDateTime(j.finished_at)}</dd>
            </div>
          </dl>
        </Card>

        <Card className="lg:col-span-2" title="Agent activity" bodyClassName="p-0">
          {!logs.data?.length ? (
            <EmptyState title="No activity yet" message="Logs appear as agents start working." />
          ) : (
            <ul className="max-h-[28rem] divide-y divide-[rgb(var(--border))] overflow-y-auto">
              {logs.data.map((log) => (
                <li key={log.id} className="flex items-start gap-3 px-5 py-2.5">
                  <span
                    className={
                      log.level === 'error'
                        ? 'mt-1.5 h-2 w-2 shrink-0 rounded-full bg-rose-500'
                        : log.level === 'warning'
                          ? 'mt-1.5 h-2 w-2 shrink-0 rounded-full bg-amber-500'
                          : 'mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand-500'
                    }
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm">{log.message}</p>
                    <p className="mt-0.5 text-xs text-muted">
                      {titleCase(log.agent_key)} · {relativeTime(log.created_at)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card className="mt-6" title="Agent tasks" bodyClassName="p-0">
        {!tasks.data?.items.length ? (
          <EmptyState title="No tasks dispatched yet" />
        ) : (
          <Table>
            <thead className="border-b border-app">
              <tr>
                <th className="th">#</th>
                <th className="th">Agent</th>
                <th className="th">Status</th>
                <th className="th">Confidence</th>
                <th className="th">Attempts</th>
                <th className="th">Finished</th>
                <th className="th">Error</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[rgb(var(--border))]">
              {tasks.data.items.map((task) => (
                <tr key={task.id} className="row-hover">
                  <td className="td tabular-nums text-muted">{task.sequence}</td>
                  <td className="td font-medium">{titleCase(task.agent_key)}</td>
                  <td className="td">
                    <StatusBadge status={task.status} />
                  </td>
                  <td className="td tabular-nums">
                    {task.confidence === null ? '—' : `${Math.round(task.confidence * 100)}%`}
                  </td>
                  <td className="td tabular-nums">
                    {task.attempts}/{task.max_attempts}
                  </td>
                  <td className="td text-sm text-muted">{relativeTime(task.finished_at)}</td>
                  <td className="td max-w-xs truncate text-sm text-rose-600">{task.error ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  )
}
