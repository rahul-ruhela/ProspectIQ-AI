import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { errorMessage } from '../api/client'
import { getAgent, listAgents, toggleAgent } from '../api/endpoints'
import {
  ErrorState,
  Loading,
  Modal,
  PageHeader,
  relativeTime,
  StatusBadge,
  titleCase,
} from '../components/ui'
import { useAuth } from '../store/auth'

export default function Agents() {
  const queryClient = useQueryClient()
  const { can } = useAuth()
  const [selected, setSelected] = useState<string | null>(null)

  const agents = useQuery({ queryKey: ['agents'], queryFn: listAgents })
  const detail = useQuery({
    queryKey: ['agent', selected],
    queryFn: () => getAgent(selected!),
    enabled: Boolean(selected),
  })

  const toggle = useMutation({
    mutationFn: ({ key, enabled }: { key: string; enabled: boolean }) => toggleAgent(key, enabled),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['agents'] }),
  })

  if (agents.isLoading) return <Loading label="Loading your AI employees…" />
  if (agents.isError) {
    return <ErrorState message={errorMessage(agents.error)} onRetry={() => void agents.refetch()} />
  }

  return (
    <>
      <PageHeader
        title="AI employees"
        subtitle="Fifteen specialists coordinated by the CEO orchestrator. Each declares a role, a goal, its tools and its input and output schema."
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {(agents.data ?? []).map((agent) => (
          <div key={agent.key} className="card flex flex-col p-5">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-3 min-w-0">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg surface-muted">
                  <Bot className="h-4 w-4" />
                </span>
                <div className="min-w-0">
                  <p className="truncate font-semibold">{agent.display_name}</p>
                  <p className="truncate text-xs text-muted">{agent.role}</p>
                </div>
              </div>
              <StatusBadge status={agent.is_enabled ? agent.status : 'disabled'} />
            </div>

            <p className="mt-3 flex-1 text-sm text-muted">{agent.goal}</p>

            <div className="mt-4 flex flex-wrap gap-1.5">
              {agent.tools.slice(0, 4).map((tool) => (
                <span key={tool} className="badge surface-muted text-muted ring-transparent">
                  {tool}
                </span>
              ))}
              {agent.tools.length > 4 && (
                <span className="badge surface-muted text-muted ring-transparent">
                  +{agent.tools.length - 4}
                </span>
              )}
            </div>

            <dl className="mt-4 grid grid-cols-3 gap-2 border-t border-app pt-3 text-center">
              <div>
                <dt className="text-xs text-muted">Runs</dt>
                <dd className="font-semibold tabular-nums">{agent.total_runs}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Failures</dt>
                <dd className="font-semibold tabular-nums">{agent.total_failures}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Confidence</dt>
                <dd className="font-semibold tabular-nums">
                  {Math.round(agent.avg_confidence * 100)}%
                </dd>
              </div>
            </dl>

            <div className="mt-4 flex items-center justify-between gap-2">
              <span className="text-xs text-muted">
                Last run {relativeTime(agent.last_run_at)} · {agent.model_tier} tier
              </span>
              <div className="flex items-center gap-1">
                <button className="btn-ghost text-sm" onClick={() => setSelected(agent.key)}>
                  Schema
                  <ChevronRight className="h-3.5 w-3.5" />
                </button>
                {can('admin') && (
                  <button
                    className="btn-secondary text-xs"
                    onClick={() => toggle.mutate({ key: agent.key, enabled: !agent.is_enabled })}
                  >
                    {agent.is_enabled ? 'Disable' : 'Enable'}
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      <Modal
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={detail.data?.display_name ?? 'Agent'}
        wide
      >
        {detail.isLoading ? (
          <Loading />
        ) : (
          <div className="space-y-4 text-sm">
            <div>
              <p className="text-muted">Goal</p>
              <p>{detail.data?.goal}</p>
            </div>
            <div>
              <p className="text-muted">Tools</p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {detail.data?.tools.map((tool) => (
                  <span key={tool} className="badge surface-muted text-muted ring-transparent">
                    {tool}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <p className="text-muted">Input schema</p>
              <pre className="mt-1 max-h-56 overflow-auto rounded-lg surface-muted p-3 text-xs">
                {JSON.stringify(detail.data?.input_schema, null, 2)}
              </pre>
            </div>
            <div>
              <p className="text-muted">Output schema</p>
              <pre className="mt-1 max-h-56 overflow-auto rounded-lg surface-muted p-3 text-xs">
                {JSON.stringify(detail.data?.output_schema, null, 2)}
              </pre>
            </div>
            <p className="text-xs text-muted">
              Model tier: {titleCase(detail.data?.model_tier ?? '')} — cheap models run on every
              company, the expensive tier only on qualified prospects.
            </p>
          </div>
        )}
      </Modal>
    </>
  )
}
