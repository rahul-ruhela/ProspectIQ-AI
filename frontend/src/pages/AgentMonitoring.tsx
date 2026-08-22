import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { errorMessage } from '../api/client'
import { departmentStatus, listAgentLogs, listAgentTasks } from '../api/endpoints'
import {
  Card,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  relativeTime,
  StatTile,
  StatusBadge,
  Table,
  titleCase,
} from '../components/ui'

const LEVELS = ['all', 'info', 'warning', 'error'] as const

export default function AgentMonitoring() {
  const [level, setLevel] = useState<(typeof LEVELS)[number]>('all')
  const [agentKey, setAgentKey] = useState('')

  const status = useQuery({
    queryKey: ['dept-status'],
    queryFn: departmentStatus,
    refetchInterval: 5_000,
  })
  const tasks = useQuery({
    queryKey: ['agent-tasks', agentKey],
    queryFn: () => listAgentTasks({ page_size: 50, ...(agentKey ? { agent_key: agentKey } : {}) }),
    refetchInterval: 5_000,
  })
  const logs = useQuery({
    queryKey: ['agent-logs', level, agentKey],
    queryFn: () =>
      listAgentLogs({
        limit: 200,
        ...(level === 'all' ? {} : { level }),
        ...(agentKey ? { agent_key: agentKey } : {}),
      }),
    refetchInterval: 5_000,
  })

  if (status.isLoading) return <Loading label="Connecting to the department…" />
  if (status.isError) {
    return <ErrorState message={errorMessage(status.error)} onRetry={() => void status.refetch()} />
  }

  const s = status.data!

  return (
    <>
      <PageHeader
        title="Agent monitoring"
        subtitle="Live status of every AI employee, the task queue and the execution log. Refreshes every 5 seconds."
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Running tasks" value={s.running_tasks} />
        <StatTile label="Pending tasks" value={s.pending_tasks} />
        <StatTile
          label="Failures (24h)"
          value={s.failed_tasks_24h}
          tone={s.failed_tasks_24h > 0 ? 'warning' : 'default'}
        />
        <StatTile label="Active jobs" value={s.active_jobs} />
      </div>

      <Card className="mt-6" title="Employee status" bodyClassName="p-0">
        <Table>
          <thead className="border-b border-app">
            <tr>
              <th className="th">Agent</th>
              <th className="th">Status</th>
              <th className="th">Runs</th>
              <th className="th">Failures</th>
              <th className="th">Avg confidence</th>
              <th className="th">Avg duration</th>
              <th className="th">Last run</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[rgb(var(--border))]">
            {s.agents.map((agent) => (
              <tr
                key={agent.key}
                className={
                  agentKey === agent.key ? 'surface-muted cursor-pointer' : 'row-hover cursor-pointer'
                }
                onClick={() => setAgentKey(agentKey === agent.key ? '' : agent.key)}
              >
                <td className="td font-medium">{agent.display_name}</td>
                <td className="td">
                  <StatusBadge status={agent.is_enabled ? agent.status : 'disabled'} />
                </td>
                <td className="td tabular-nums">{agent.total_runs}</td>
                <td className="td tabular-nums">{agent.total_failures}</td>
                <td className="td tabular-nums">{Math.round(agent.avg_confidence * 100)}%</td>
                <td className="td tabular-nums">{agent.avg_duration_ms} ms</td>
                <td className="td text-sm text-muted">{relativeTime(agent.last_run_at)}</td>
              </tr>
            ))}
          </tbody>
        </Table>
        {agentKey && (
          <p className="border-t border-app px-4 py-2 text-xs text-muted">
            Filtering tasks and logs by {titleCase(agentKey)} — click the row again to clear.
          </p>
        )}
      </Card>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card title="Task queue" bodyClassName="p-0">
          {!tasks.data?.items.length ? (
            <EmptyState title="No tasks" />
          ) : (
            <ul className="max-h-[26rem] divide-y divide-[rgb(var(--border))] overflow-y-auto">
              {tasks.data.items.map((task) => (
                <li key={task.id} className="flex items-center gap-3 px-5 py-2.5">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{titleCase(task.agent_key)}</p>
                    <p className="text-xs text-muted">
                      attempt {task.attempts}/{task.max_attempts} · {relativeTime(task.created_at)}
                      {task.error ? ` · ${task.error}` : ''}
                    </p>
                  </div>
                  <StatusBadge status={task.status} />
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title="Execution log"
          actions={
            <div className="flex gap-1">
              {LEVELS.map((value) => (
                <button
                  key={value}
                  className={value === level ? 'btn-primary px-2 py-1 text-xs' : 'btn-ghost px-2 py-1 text-xs'}
                  onClick={() => setLevel(value)}
                >
                  {titleCase(value)}
                </button>
              ))}
            </div>
          }
          bodyClassName="p-0"
        >
          {!logs.data?.length ? (
            <EmptyState title="No log entries" />
          ) : (
            <ul className="max-h-[26rem] divide-y divide-[rgb(var(--border))] overflow-y-auto">
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
    </>
  )
}
